from pathlib import Path

from filekeeper import Archive, FileModel
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

    fresh = Manifest(m.path, archive)
    fresh.load()
    assert fresh.entries == {"x/y.txt": fm}
