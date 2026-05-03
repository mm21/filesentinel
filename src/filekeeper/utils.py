"""
General utilities: hashing, par2 redundancy, disk ripping.
"""

import hashlib
import logging
import shutil
import subprocess
from pathlib import Path

_LOGGER = logging.getLogger(__name__)

PAR2_BASENAME = "redundancy"
"""
Basename used for the par2 set inside each tree leaf folder.

The full index file lands as `<dir>/redundancy.par2`.
"""


def sha256_file(path: Path, *, chunk: int = 65536) -> str:
    """
    Compute the SHA-256 hex digest of a file by streaming.
    """
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            buf = f.read(chunk)
            if not buf:
                break
            h.update(buf)
    return h.hexdigest()


def _par2_bin() -> str:
    binary = shutil.which("par2")
    if binary is None:
        raise RuntimeError("par2 binary not found on PATH")
    return binary


def par2_create(
    src: Path,
    par2_dir: Path,
    *,
    recovery_pct: int,
) -> None:
    """
    Create par2 redundancy set for `src` inside `par2_dir`.
    """
    par2_dir.mkdir(parents=True, exist_ok=True)
    base = par2_dir / PAR2_BASENAME
    cmd = [
        _par2_bin(),
        "create",
        "-q",
        f"-r{recovery_pct}",
        f"-a{base}",
        f"-B{src.parent}",
        src.name,
    ]
    _LOGGER.debug("par2 create: %s", cmd)
    subprocess.run(cmd, check=True, capture_output=True, cwd=src.parent)


def par2_verify(src: Path, par2_dir: Path) -> bool:
    """
    Verify `src` against par2 set in `par2_dir`.

    Returns True on success.
    """
    index = par2_dir / f"{PAR2_BASENAME}.par2"
    if not index.exists():
        return False
    cmd = [_par2_bin(), "verify", "-q", f"-B{src.parent}", str(index)]
    _LOGGER.debug("par2 verify: %s", cmd)
    result = subprocess.run(cmd, capture_output=True, cwd=src.parent)
    return result.returncode == 0


def par2_repair(src: Path, par2_dir: Path) -> bool:
    """
    Repair `src` using par2 set in `par2_dir`.

    Returns True on success.
    """
    index = par2_dir / f"{PAR2_BASENAME}.par2"
    if not index.exists():
        return False
    cmd = [_par2_bin(), "repair", "-q", "-p", f"-B{src.parent}", str(index)]
    _LOGGER.debug("par2 repair: %s", cmd)
    result = subprocess.run(cmd, capture_output=True, cwd=src.parent)
    return result.returncode == 0


def rip_disk(src_disk: Path, dest_iso: Path) -> None:
    """
    Rip a disk to .iso file using `ddrescue`.
    """
    binary = shutil.which("ddrescue")
    if binary is None:
        raise RuntimeError("ddrescue binary not found on PATH")
    log_path = dest_iso.with_suffix(dest_iso.suffix + ".log")
    cmd = [binary, "-b", "2048", "-n", str(src_disk), str(dest_iso), str(log_path)]
    _LOGGER.info("ripping %s -> %s", src_disk, dest_iso)
    subprocess.run(cmd, check=True)
