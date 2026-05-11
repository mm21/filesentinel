from pathlib import Path

from filekeeper import Archive, FileModel, Par2FileModel
from filekeeper.manifest import Manifest


def test_map_digest_layout(archive: Archive):
    m = archive.manifest
    digest = "aabbccdd" + "0" * 56
    p = m.map_digest(digest)
    rel = p.relative_to(m.tree_root)
    assert rel.parts == ("aa", "bb", digest)


def test_load_save_roundtrip(tmp_path: Path, archive: Archive):
    m = archive.manifest
    fm = FileModel(path="x/y.txt", digest="d" * 64, size=10, mtime=1.5)
    m.entries["x/y.txt"] = fm
    m.save()

    fresh = Manifest(m.path)
    fresh.load()
    assert fresh.entries == {"x/y.txt": fm}


def test_par2_sets_roundtrip(archive: Archive):
    m = archive.manifest
    digest = "a" * 64
    files = [
        Par2FileModel(name="redundancy.par2", digest="b" * 64),
        Par2FileModel(name="redundancy.vol0+1.par2", digest="c" * 64),
    ]
    m.set_par2_files(digest, files)
    m.save()

    fresh = Manifest(m.path)
    fresh.load()
    assert fresh.par2_sets == {digest: {f.name: f for f in files}}
