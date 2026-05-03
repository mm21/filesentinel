"""
Implementation of archive abstraction.
"""

from pathlib import Path

from filekeeper.config import ConfigModel

from .manifest import Manifest


class Archive:
    """
    Core abstraction of archive folder.

    Consists of the following:

    - Root folder of archive files (a folder called `.filekeeper` is ignored)
    - Manifest (may be placed outside of archive)
    - Optional config file as `config.yaml` (default location, can be overridden in CLI)
    """

    __root: Path
    """
    Path to archive root folder.
    """

    __config: ConfigModel

    __manifest: Manifest
    """
    Manifest of files.
    """

    def __init__(self, root: Path, config_path: Path, manifest_path: Path):
        self.__root = root
        self.__config = ConfigModel.from_yaml(config_path)
        self.__manifest = Manifest(manifest_path, self)

    @property
    def root(self) -> Path:
        return self.__root

    @property
    def manifest(self) -> Manifest:
        return self.__manifest
