"""
Implementation of file manifest.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Literal, Sequence

import yaml
from pydantic import BaseModel

from .utils import sha256_file

if TYPE_CHECKING:
    from .file import File


INDEX_FILENAME = "manifest.yaml"
INDEX_SHA_FILENAME = f"{INDEX_FILENAME}.sha256"
TREE_DIRNAME = "tree"
TREE_DEPTH = 2

type ChangeType = Literal["add", "edit", "delete", "move"]
type Par2ChangeType = Literal["add", "edit", "delete"]


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


class Par2FileModel(BaseModel):
    """
    Manifest entry for one par2 redundancy file.
    """

    name: str
    """
    Basename of the par2 file within its par2 dir.
    """

    digest: str
    """
    SHA-256 hex digest of the par2 file's contents.
    """


class Par2SetModel(BaseModel):
    """
    The par2 redundancy set for one content digest.
    """

    digest: str
    """
    Content digest (SHA-256) of the source file the set protects.
    """

    files: list[Par2FileModel] = []


class ManifestModel(BaseModel):
    """
    Model used to load/store the manifest index file.
    """

    version: int = 2
    files: list[FileModel] = []
    par2_sets: list[Par2SetModel] = []


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
    new: File | None = None
    old: FileModel | None = None


@dataclass
class Par2Change:
    """
    A change detected in a par2 redundancy set.

    - `add`    : `new` only — par2 file present on disk, not in manifest
    - `delete` : `old` only — par2 file recorded in manifest, missing on disk
    - `edit`   : both — par2 file on disk differs from recorded digest
    """

    change_type: Par2ChangeType
    content_digest: str
    name: str
    new: Par2FileModel | None = None
    old: Par2FileModel | None = None


class Manifest:
    """
    Manifest of files in an archive folder.
    """

    __path: Path
    __model: ManifestModel
    __entries: dict[str, FileModel]
    __par2_sets: dict[str, dict[str, Par2FileModel]]

    def __init__(self, path: Path):
        self.__path = path
        self.__model = ManifestModel()
        self.__entries = {}
        self.__par2_sets = {}

    @property
    def path(self) -> Path:
        return self.__path

    @property
    def index_path(self) -> Path:
        return self.__path / INDEX_FILENAME

    @property
    def index_sha_path(self) -> Path:
        return self.__path / INDEX_SHA_FILENAME

    @property
    def tree_root(self) -> Path:
        return self.__path / TREE_DIRNAME

    @property
    def entries(self) -> dict[str, FileModel]:
        """
        Manifest entries keyed by relative path (posix).
        """
        return self.__entries

    @property
    def par2_sets(self) -> dict[str, dict[str, Par2FileModel]]:
        """
        Par2 file records keyed by content digest, then by par2 file basename.
        """
        return self.__par2_sets

    def load(self) -> None:
        """
        Load the manifest from disk.

        No-op if the index file does not exist.
        """
        if not self.index_path.exists():
            self.__model = ManifestModel()
            self.__entries = {}
            self.__par2_sets = {}
            return
        with self.index_path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        self.__model = ManifestModel.model_validate(data)
        self.__entries = {fm.path: fm for fm in self.__model.files}
        self.__par2_sets = {
            ps.digest: {pf.name: pf for pf in ps.files} for ps in self.__model.par2_sets
        }

    def save(self) -> None:
        """
        Write the manifest to disk atomically.
        """
        self.__path.mkdir(parents=True, exist_ok=True)
        self.__model.files = sorted(self.__entries.values(), key=lambda f: f.path)
        self.__model.par2_sets = [
            Par2SetModel(
                digest=d,
                files=sorted(self.__par2_sets[d].values(), key=lambda f: f.name),
            )
            for d in sorted(self.__par2_sets)
        ]
        tmp = self.index_path.with_suffix(".yaml.tmp")
        with tmp.open("w", encoding="utf-8") as f:
            yaml.safe_dump(
                self.__model.model_dump(),
                f,
                sort_keys=False,
                default_flow_style=False,
            )
        os.replace(tmp, self.index_path)

    def compute_index_sha(self) -> str | None:
        """
        SHA-256 hex digest of the on-disk manifest index, or None if it does not exist.
        """
        if not self.index_path.exists():
            return None
        return sha256_file(self.index_path)

    def read_index_sha(self) -> str | None:
        """
        Recorded SHA-256 from the sidecar file, or None if the sidecar does not exist.
        """
        if not self.index_sha_path.exists():
            return None
        return self.index_sha_path.read_text(encoding="utf-8").strip()

    def update_index_sha(self) -> str:
        """
        Recompute the manifest index SHA-256 and atomically write it to the sidecar.

        Returns the new digest. Requires the index to exist on disk.
        """
        digest = sha256_file(self.index_path)
        tmp = self.index_sha_path.with_suffix(".sha256.tmp")
        tmp.write_text(digest + "\n", encoding="utf-8")
        os.replace(tmp, self.index_sha_path)
        return digest

    def map_digest(self, digest: str) -> Path:
        """
        Map a digest to its leaf folder under the prefix tree.

        The leaf folder name is the full digest, prefixed by `depth` levels of
        2-char buckets (e.g. `tree/aa/bb/aabbccdd...`).
        """
        assert len(digest) >= TREE_DEPTH * 2
        parts = [digest[i * 2 : (i + 1) * 2] for i in range(TREE_DEPTH)]
        return self.tree_root.joinpath(*parts, digest)

    def set_par2_files(
        self, content_digest: str, files: Sequence[Par2FileModel]
    ) -> None:
        """
        Record the par2 file set for a content digest, replacing any prior entry.
        """
        self.__par2_sets[content_digest] = {f.name: f for f in files}

    def drop_par2_set(self, content_digest: str) -> None:
        """
        Remove the par2 file set for a content digest.
        """
        self.__par2_sets.pop(content_digest, None)

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
                    del self.__entries[ch.old.path]
                case "move":
                    assert ch.old is not None and ch.new is not None
                    del self.__entries[ch.old.path]
                    self.__entries[ch.new.rel_path.as_posix()] = ch.new.to_model()
                case "edit":
                    assert ch.old is not None and ch.new is not None
                    self.__entries[ch.new.rel_path.as_posix()] = ch.new.to_model()
        self.__entries = {p: self.__entries[p] for p in sorted(self.__entries)}
