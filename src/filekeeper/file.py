"""
Implementation of file abstraction.
"""

from __future__ import annotations

from functools import cached_property
from os import stat_result
from pathlib import Path
from typing import TYPE_CHECKING

from .utils import sha256_file

if TYPE_CHECKING:
    from .archive import Archive
    from .manifest import FileModel


class File:
    """
    Core abstraction of an archive file currently present on disk.
    """

    __path: Path
    __archive: Archive
    __digest: str | None = None

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
        Folder containing this file's redundancy data within the manifest tree.
        """
        return self.__archive.manifest.map_digest(self.digest)

    @cached_property
    def par2_path(self) -> Path:
        """
        Path to the par2 index file for this file's redundancy set.
        """
        from .utils import PAR2_BASENAME

        return self.manifest_path / f"{PAR2_BASENAME}.par2"

    @cached_property
    def stat(self) -> stat_result:
        return self.__path.stat()

    @cached_property
    def size(self) -> int:
        return self.stat.st_size

    @cached_property
    def mtime(self) -> float:
        return self.stat.st_mtime

    @cached_property
    def digest(self) -> str:
        """
        SHA-256 digest of file as hex.
        """
        if not self.__digest:
            self.load_digest()
        assert self.__digest
        return self.__digest

    def load_digest(self):
        """
        Read SHA-256 digest from file.
        """
        if self.__digest is None:
            self.__digest = sha256_file(self.__path)

    def to_model(self) -> "FileModel":
        from .manifest import FileModel

        return FileModel(
            path=self.rel_path.as_posix(),
            digest=self.digest,
            size=self.size,
            mtime=self.mtime,
        )
