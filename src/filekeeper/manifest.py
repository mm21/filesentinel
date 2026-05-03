"""
Implementation of file manifest.
"""

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Literal, Sequence

import yaml
from pydantic import BaseModel

if TYPE_CHECKING:
    from .archive import Archive
    from .file import File

_LOGGER = logging.getLogger(__name__)

INDEX_FILENAME = "manifest.yaml"
TREE_DIRNAME = "tree"

type ChangeType = Literal["add", "delete", "move", "edit"]


class FileModel(BaseModel):
    """
    Manifest entry for one file.
    """

    path: str
    """
    Path relative to archive root, in posix form.
    """

    digest: str
    """
    SHA-256 hex digest.
    """

    size: int
    mtime: float


class ManifestModel(BaseModel):
    """
    Model used to load/store the manifest index file.
    """

    version: int = 1
    files: list[FileModel] = []


@dataclass
class PendingChange:
    """
    A change pending application to the manifest.

    - `add`    : `new` only
    - `delete` : `old` only
    - `move`   : both, `old.digest == new.digest`
    - `edit`   : both, `old.path == new.path`
    """

    change_type: ChangeType
    new: "File | None" = None
    old: "FileModel | None" = None


class Manifest:
    """
    Manifest of files in an archive folder.
    """

    __path: Path
    __archive: "Archive"
    __model: ManifestModel
    __entries: dict[str, FileModel]

    def __init__(self, path: Path, archive: "Archive"):
        self.__path = path
        self.__archive = archive
        self.__model = ManifestModel()
        self.__entries = {}

    @property
    def path(self) -> Path:
        return self.__path

    @property
    def index_path(self) -> Path:
        return self.__path / INDEX_FILENAME

    @property
    def tree_root(self) -> Path:
        return self.__path / TREE_DIRNAME

    @property
    def entries(self) -> dict[str, FileModel]:
        """
        Manifest entries keyed by relative path (posix).
        """
        return self.__entries

    def load(self) -> None:
        """
        Load the manifest from disk.

        No-op if the index file does not exist.
        """
        if not self.index_path.exists():
            self.__model = ManifestModel()
            self.__entries = {}
            return
        with self.index_path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        self.__model = ManifestModel.model_validate(data)
        self.__entries = {fm.path: fm for fm in self.__model.files}

    def save(self) -> None:
        """
        Write the manifest to disk atomically.
        """
        self.__path.mkdir(parents=True, exist_ok=True)
        self.__model.files = sorted(self.__entries.values(), key=lambda f: f.path)
        tmp = self.index_path.with_suffix(".yaml.tmp")
        with tmp.open("w", encoding="utf-8") as f:
            yaml.safe_dump(
                self.__model.model_dump(),
                f,
                sort_keys=False,
                default_flow_style=False,
            )
        os.replace(tmp, self.index_path)

    def map_digest(self, digest: str) -> Path:
        """
        Map a digest to its leaf folder under the prefix tree.

        The leaf folder name is the full digest, prefixed by `depth` levels of
        2-char buckets (e.g. `tree/aa/bb/aabbccdd...`).
        """
        depth = self.__archive.config.prefix_tree_depth
        if len(digest) < depth * 2:
            raise ValueError(f"digest too short for depth {depth}: {digest}")
        parts = [digest[i * 2 : (i + 1) * 2] for i in range(depth)]
        return self.tree_root.joinpath(*parts, digest)

    def apply(self, changes: Sequence[PendingChange]) -> None:
        """
        Apply changes to the in-memory entry map.

        Caller is responsible for `save()` to persist.
        """
        for ch in changes:
            match ch.change_type:
                case "add":
                    assert ch.new is not None
                    self.__entries[ch.new.rel_path.as_posix()] = ch.new.to_model()
                case "delete":
                    assert ch.old is not None
                    self.__entries.pop(ch.old.path, None)
                case "move":
                    assert ch.old is not None and ch.new is not None
                    self.__entries.pop(ch.old.path, None)
                    self.__entries[ch.new.rel_path.as_posix()] = ch.new.to_model()
                case "edit":
                    assert ch.old is not None and ch.new is not None
                    self.__entries[ch.new.rel_path.as_posix()] = ch.new.to_model()
