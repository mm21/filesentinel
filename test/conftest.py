import shutil
from pathlib import Path

import pytest

from filesentinel import Archive

PAR2_AVAILABLE = shutil.which("par2") is not None
needs_par2 = pytest.mark.skipif(not PAR2_AVAILABLE, reason="par2 binary not available")


@pytest.fixture
def archive_root(tmp_path: Path) -> Path:
    root = tmp_path / "arch"
    root.mkdir()
    (root / "a.txt").write_bytes(b"alpha\n")
    (root / "b.txt").write_bytes(b"beta beta\n")
    sub = root / "sub"
    sub.mkdir()
    (sub / "c.txt").write_bytes(b"gamma" * 100)
    return root


@pytest.fixture
def archive(archive_root: Path) -> Archive:
    return Archive(archive_root)
