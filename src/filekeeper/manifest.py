"""
Implementation of file manifest.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Literal, Sequence

from pydantic import BaseModel

if TYPE_CHECKING:
    from .archive import Archive
    from .file import File

PREFIX_TREE_DEPTH = 2
"""
Depth of prefix tree indexed by file's SHA-256 hash.
"""


type ChangeType = Literal["add", "update", "delete", "move"]


@dataclass
class PendingChange:
    """ """

    file: File
    change_type: ChangeType


class Manifest:
    """
    Manifest of files in archive folder.
    """

    __path: Path
    """
    Path to manifest folder.
    """

    __archive: Archive
    """
    Corresponding archive.
    """

    __files: list[File]
    """
    List of files in manifest, sorted alphabetically.
    """

    def __init__(self, path: Path, archive: Archive):
        self.__path = path
        self.__archive = archive

    @property
    def path(self) -> Path:
        return self.__path

    @property
    def tree_root(self) -> Path:
        """
        Path to prefix tree root.
        """
        return self.__path / "tree"

    def get_changes(self) -> list[PendingChange]:
        """ """
        ...

    def commit_changes(self, changes: Sequence[PendingChange]):
        """ """
        ...

    def map_digest(self, digest: str) -> Path:
        """
        Map digest value to its location in the prefix tree.
        """
        ...


class FileModel(BaseModel):

    path: str
    """
    Path relative to archive root.
    """

    digest: str
    """
    File's SHA-256 hash value.
    """


class ManifestModel(BaseModel):
    """
    Model used to load/store manifest to/from .yaml file.
    """
