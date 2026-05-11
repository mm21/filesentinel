import hashlib
from pathlib import Path

from filekeeper.utils import iter_par2_files, sha256_file


def test_sha256_file_matches_hashlib(tmp_path: Path):
    p = tmp_path / "f.bin"
    data = b"hello world\n" * 1000
    p.write_bytes(data)
    assert sha256_file(p) == hashlib.sha256(data).hexdigest()


def test_sha256_file_chunk_independence(tmp_path: Path):
    p = tmp_path / "f.bin"
    p.write_bytes(b"x" * (65536 * 3 + 7))
    assert sha256_file(p, chunk=4096) == sha256_file(p, chunk=65536)


def test_iter_par2_files_sorted(tmp_path: Path):
    d = tmp_path / "par2"
    d.mkdir()
    (d / "redundancy.vol0+1.par2").write_bytes(b"vol")
    (d / "redundancy.par2").write_bytes(b"idx")
    files = iter_par2_files(d)
    assert [f.name for f in files] == ["redundancy.par2", "redundancy.vol0+1.par2"]
