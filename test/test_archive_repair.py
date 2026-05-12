from pathlib import Path

from filekeeper import Archive

from .conftest import needs_par2


@needs_par2
def test_repair_restores_corrupted_file(archive_root: Path):
    a = Archive(archive_root)
    a.apply(a.scan(), par2=True)

    target = archive_root / "sub" / "c.txt"
    original = target.read_bytes()

    # corrupt by appending bytes
    target.write_bytes(original + b"CORRUPTION")

    a2 = Archive(archive_root)
    changes = a2.scan()
    assert len(changes) == 1 and changes[0].change_type == "edit"

    report = a2.repair(changes)
    assert report.ok
    assert report.repaired == ["sub/c.txt"]
    assert target.read_bytes() == original

    a3 = Archive(archive_root)
    assert a3.verify() is True


@needs_par2
def test_repair_reports_deletes_as_unrepairable(archive_root: Path):
    a = Archive(archive_root)
    a.apply(a.scan(), par2=True)

    (archive_root / "a.txt").unlink()

    a2 = Archive(archive_root)
    changes = a2.scan()
    report = a2.repair(changes)
    assert not report.ok
    assert "a.txt" in report.unrepairable
