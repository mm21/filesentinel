"""
Implementation of file abstraction.
"""

from functools import cached_property
from os import stat_result
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .archive import Archive


class File:
    """
    Core abstraction of archive file.
    """

    __path: Path
    """
    Absolute path to file nested in archive root.
    """

    __archive: Archive
    """
    Containing archive.
    """

    def __init__(self, path: Path, archive: Archive):
        self.__path = path
        self.__archive = archive

    @property
    def path(self) -> Path:
        return self.__path

    @property
    def rel_path(self) -> Path:
        return self.__path.relative_to(self.__archive.root)

    @cached_property
    def manifest_path(self) -> Path:
        """
        Folder for this file content within manifest folder.
        """
        return self.__archive.manifest.map_digest(self.digest)

    @cached_property
    def par2_path(self) -> Path:
        """
        Path to redundancy data.
        """
        return self.manifest_path / f"redundancy.par2"

    @cached_property
    def stat(self) -> stat_result:
        return self.__path.stat()

    @cached_property
    def size(self) -> int:
        return self.stat.st_size

    @cached_property
    def digest(self) -> str:
        """
        SHA-256 digest of file as hex.
        """
        ...
