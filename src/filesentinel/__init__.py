"""
FileSentinel: Integrity monitoring and repair toolkit for long-term file archives.
"""

__submodules__ = [
    "archive",
    "config",
    "file",
    "manifest",
]

# isort: off
# <AUTOGEN_INIT>
from .archive import (
    RepairReport,
    Archive,
)
from .config import (
    ConfigModel,
)
from .file import (
    File,
)
from .manifest import (
    ChangeType,
    Par2ChangeType,
    FileModel,
    Par2FileModel,
    Par2SetModel,
    ManifestModel,
    PendingChange,
    Par2Change,
    Manifest,
)

__all__ = [
    "RepairReport",
    "Archive",
    "ConfigModel",
    "File",
    "ChangeType",
    "Par2ChangeType",
    "FileModel",
    "Par2FileModel",
    "Par2SetModel",
    "ManifestModel",
    "PendingChange",
    "Par2Change",
    "Manifest",
]
# </AUTOGEN_INIT>
