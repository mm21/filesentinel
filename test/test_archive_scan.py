import os
import time
from pathlib import Path

from filekeeper import Archive

from .conftest import needs_par2


def _types(changes) -> list[str]:
    return sorted(c.change_type for c in changes)


@needs_par2
def test_initial_scan_all_adds(archive: Archive):
    changes = archive.scan()
    assert _types(changes) == ["add", "add", "add"]


@needs_par2
def test_clean_after_apply(archive: Archive):
    archive.apply(archive.scan())
    assert archive.scan() == []
    assert archive.verify() is True


@needs_par2
def test_edit_detected(archive_root: Path):
    a = Archive(archive_root)
    a.apply(a.scan())

    (archive_root / "a.txt").write_bytes(b"DIFFERENT\n")

    a2 = Archive(archive_root)
    changes = a2.scan()
    assert len(changes) == 1
    assert changes[0].change_type == "edit"
    assert changes[0].new
    assert changes[0].new.rel_path.as_posix() == "a.txt"


@needs_par2
def test_move_detected(archive_root: Path):
    a = Archive(archive_root)
    a.apply(a.scan())

    (archive_root / "a.txt").rename(archive_root / "renamed.txt")

    a2 = Archive(archive_root)
    changes = a2.scan()
    assert len(changes) == 1
    assert changes[0].change_type == "move"
    assert changes[0].old
    assert changes[0].new
    assert changes[0].old.path == "a.txt"
    assert changes[0].new.rel_path.as_posix() == "renamed.txt"


@needs_par2
def test_delete_detected(archive_root: Path):
    a = Archive(archive_root)
    a.apply(a.scan())

    (archive_root / "a.txt").unlink()

    a2 = Archive(archive_root)
    changes = a2.scan()
    assert len(changes) == 1
    assert changes[0].change_type == "delete"
    assert changes[0].old
    assert changes[0].old.path == "a.txt"


@needs_par2
def test_apply_records_par2_files(archive: Archive):
    archive.apply(archive.scan())
    # every referenced content digest has a recorded par2 set
    for fm in archive.manifest.entries.values():
        par2_dir = archive.manifest.map_digest(fm.digest)
        on_disk = sorted(p.name for p in par2_dir.iterdir() if p.is_file())
        recorded = sorted(archive.manifest.par2_sets[fm.digest])
        assert on_disk == recorded


@needs_par2
def test_scan_par2_detects_deleted_par2_file(archive_root: Path):
    a = Archive(archive_root)
    a.apply(a.scan())

    digest = next(iter(a.manifest.entries.values())).digest
    par2_dir = a.manifest.map_digest(digest)
    victim = next(p for p in par2_dir.iterdir() if p.name.endswith(".par2"))
    victim.unlink()

    a2 = Archive(archive_root)
    changes = a2.scan_par2()
    assert any(c.change_type == "delete" and c.name == victim.name for c in changes)


@needs_par2
def test_scan_par2_detects_modified_par2_file(archive_root: Path):
    a = Archive(archive_root)
    a.apply(a.scan())

    digest = next(iter(a.manifest.entries.values())).digest
    par2_dir = a.manifest.map_digest(digest)
    victim = next(p for p in par2_dir.iterdir() if p.name.endswith(".par2"))
    victim.write_bytes(b"corrupted")

    a2 = Archive(archive_root)
    changes = a2.scan_par2()
    assert any(c.change_type == "edit" and c.name == victim.name for c in changes)


@needs_par2
def test_apply_par2_rebuilds(archive_root: Path):
    a = Archive(archive_root)
    a.apply(a.scan())

    digest = next(iter(a.manifest.entries.values())).digest
    par2_dir = a.manifest.map_digest(digest)
    victim = next(p for p in par2_dir.iterdir() if p.name.endswith(".par2"))
    victim.unlink()

    a2 = Archive(archive_root)
    par2_changes = a2.scan_par2()
    assert par2_changes
    a2.apply_par2(par2_changes)

    a3 = Archive(archive_root)
    assert a3.scan_par2() == []
    assert a3.verify() is True


@needs_par2
def test_fast_mode_uses_size_mtime(archive_root: Path):
    a = Archive(archive_root)
    a.apply(a.scan())

    target = archive_root / "a.txt"
    # bump mtime without changing content
    new_mtime = time.time() + 60
    os.utime(target, (new_mtime, new_mtime))

    a2 = Archive(archive_root)
    fast_changes = a2.scan(fast=True)
    # fast mode trusts stat: mtime mismatch -> emit edit even though content matches
    assert len(fast_changes) == 1
    assert fast_changes[0].change_type == "edit"

    # full mode rehashes -> sees content unchanged
    full_changes = a2.scan(fast=False)
    assert full_changes == []
