"""
General utilities: hashing, par2 redundancy, disk ripping.
"""

from __future__ import annotations

import hashlib
import logging
import shutil
import subprocess
from pathlib import Path

from rich.console import Console

PAR2_BASENAME = "redundancy"
"""
Basename used for the par2 set inside each tree leaf folder.

The full index file lands as `<dir>/redundancy.par2`.
"""

SHA256_SUFFIX = ".sha256"
"""
Suffix used for sidecar files storing the SHA-256 of a par2 redundancy file.

Sidecar content is `sha256sum -c`-compatible: `<hex>  <basename>\\n`.
"""

console = Console()
_logger = logging.getLogger(__name__)


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


def write_sha256_sidecars(par2_dir: Path) -> None:
    """
    Write a `<file>.sha256` sidecar for every non-sidecar file in `par2_dir`.

    Existing sidecars are overwritten.
    """
    for f in _iter_par2_files(par2_dir):
        digest = sha256_file(f)
        sidecar = f.with_name(f.name + SHA256_SUFFIX)
        tmp = sidecar.with_name(sidecar.name + ".tmp")
        tmp.write_text(f"{digest}  {f.name}\n", encoding="utf-8")
        tmp.replace(sidecar)


def verify_sha256_sidecars(par2_dir: Path) -> list[str]:
    """
    Verify each non-sidecar file in `par2_dir` matches its `<file>.sha256`.

    Returns a list of human-readable problems (missing sidecar, missing target, digest
    mismatch, malformed sidecar). Empty list means OK.
    """
    problems: list[str] = []
    if not par2_dir.exists():
        return [f"missing par2 dir: {par2_dir}"]
    files = _iter_par2_files(par2_dir)
    seen_sidecars: set[Path] = set()
    for f in files:
        sidecar = f.with_name(f.name + SHA256_SUFFIX)
        if not sidecar.exists():
            problems.append(f"missing sidecar: {sidecar}")
            continue
        seen_sidecars.add(sidecar)
        try:
            line = sidecar.read_text(encoding="utf-8").strip()
            expected = line.split()[0]
        except (OSError, IndexError):
            problems.append(f"malformed sidecar: {sidecar}")
            continue
        actual = sha256_file(f)
        if actual != expected:
            problems.append(f"sha256 mismatch: {f}")
    # report orphan sidecars (sidecar present but target missing)
    for s in par2_dir.iterdir():
        if s.is_file() and s.suffix == SHA256_SUFFIX and s not in seen_sidecars:
            problems.append(f"orphan sidecar: {s}")
    return problems


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
        _get_par2_bin(),
        "create",
        "-q",
        f"-r{recovery_pct}",
        f"-a{base}",
        f"-B{src.parent}",
        src.name,
    ]
    _logger.debug("par2 create: %s", cmd)
    subprocess.run(cmd, check=True, capture_output=True, cwd=src.parent)


def par2_verify(src: Path, par2_dir: Path) -> bool:
    """
    Verify `src` against par2 set in `par2_dir`.

    Returns True on success.
    """
    index = par2_dir / f"{PAR2_BASENAME}.par2"
    if not index.exists():
        return False
    cmd = [_get_par2_bin(), "verify", "-q", f"-B{src.parent}", str(index)]
    _logger.debug("par2 verify: %s", cmd)
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
    cmd = [_get_par2_bin(), "repair", "-q", "-p", f"-B{src.parent}", str(index)]
    _logger.debug("par2 repair: %s", cmd)
    result = subprocess.run(cmd, capture_output=True, cwd=src.parent)
    return result.returncode == 0


def rip_disk(src_disk: Path, dest_iso: Path) -> None:
    """
    Rip a disk to .iso file using `ddrescue`.
    """
    binary = shutil.which("ddrescue")
    if binary is None:
        raise RuntimeError("ddrescue binary not found on PATH")
    map_path = dest_iso.with_suffix(dest_iso.suffix + ".map")
    base = [binary, "-b", "2048"]
    args = [str(src_disk), str(dest_iso), str(map_path)]

    _logger.info("ripping (pass 1, no scrape) %s -> %s", src_disk, dest_iso)
    result = subprocess.run(base + ["-n"] + args)
    if result.returncode == 0:
        return

    _logger.info("ripping (pass 2, scrape + retry) %s -> %s", src_disk, dest_iso)
    subprocess.run(base + ["-d", "-r", "3"] + args, check=True)


def _get_par2_bin() -> str:
    binary = shutil.which("par2")
    if binary is None:
        raise RuntimeError("par2 binary not found on PATH")
    return binary


def _iter_par2_files(par2_dir: Path) -> list[Path]:
    return sorted(
        p for p in par2_dir.iterdir() if p.is_file() and p.suffix != SHA256_SUFFIX
    )
