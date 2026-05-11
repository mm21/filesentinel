import hashlib
from pathlib import Path

from filekeeper.utils import (
    sha256_file,
    verify_sha256_sidecars,
    write_sha256_sidecars,
)


def test_sha256_file_matches_hashlib(tmp_path: Path):
    p = tmp_path / "f.bin"
    data = b"hello world\n" * 1000
    p.write_bytes(data)
    assert sha256_file(p) == hashlib.sha256(data).hexdigest()


def test_sha256_file_chunk_independence(tmp_path: Path):
    p = tmp_path / "f.bin"
    p.write_bytes(b"x" * (65536 * 3 + 7))
    assert sha256_file(p, chunk=4096) == sha256_file(p, chunk=65536)


def test_sha256_sidecars_write_and_verify(tmp_path: Path):
    d = tmp_path / "par2"
    d.mkdir()
    (d / "redundancy.par2").write_bytes(b"index")
    (d / "redundancy.vol0+1.par2").write_bytes(b"vol")
    write_sha256_sidecars(d)
    assert (d / "redundancy.par2.sha256").exists()
    assert (d / "redundancy.vol0+1.par2.sha256").exists()
    # sidecar should be sha256sum -c compatible
    line = (d / "redundancy.par2.sha256").read_text()
    assert line.strip() == f"{sha256_file(d / 'redundancy.par2')}  redundancy.par2"
    assert verify_sha256_sidecars(d) == []


def test_sha256_sidecars_detect_mismatch(tmp_path: Path):
    d = tmp_path / "par2"
    d.mkdir()
    f = d / "redundancy.par2"
    f.write_bytes(b"original")
    write_sha256_sidecars(d)
    f.write_bytes(b"tampered")
    problems = verify_sha256_sidecars(d)
    assert len(problems) == 1 and "mismatch" in problems[0]


def test_sha256_sidecars_detect_missing(tmp_path: Path):
    d = tmp_path / "par2"
    d.mkdir()
    (d / "redundancy.par2").write_bytes(b"x")
    problems = verify_sha256_sidecars(d)
    assert len(problems) == 1 and "missing sidecar" in problems[0]


def test_sha256_sidecars_detect_orphan(tmp_path: Path):
    d = tmp_path / "par2"
    d.mkdir()
    (d / "redundancy.par2").write_bytes(b"x")
    write_sha256_sidecars(d)
    (d / "redundancy.par2").unlink()
    problems = verify_sha256_sidecars(d)
    assert len(problems) == 1 and "orphan" in problems[0]
