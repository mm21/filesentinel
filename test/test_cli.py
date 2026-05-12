from pathlib import Path

from typer.testing import CliRunner

from filekeeper import Archive
from filekeeper.cli import app

from .conftest import needs_par2

runner = CliRunner()


def test_scan_apply_creates_no_par2_by_default(archive_root: Path):
    root = str(archive_root)
    r = runner.invoke(app, ["scan", root, "--apply", "-y"])
    assert r.exit_code == 0, r.output
    assert (archive_root / ".filekeeper" / "manifest.yaml").exists()

    a = Archive(archive_root)
    assert a.manifest.par2_sets == {}
    assert not a.manifest.tree_root.exists()

    # clean scan without --par2 verifies fine
    r = runner.invoke(app, ["scan", root, "--verify"])
    assert r.exit_code == 0, r.output


def test_scan_verify_ignores_par2_without_flag(archive_root: Path):
    root = str(archive_root)
    # populate with par2
    r = runner.invoke(app, ["scan", root, "--apply", "--par2", "-y"])
    assert r.exit_code == 0, r.output

    a = Archive(archive_root)
    digest = next(iter(a.manifest.entries.values())).digest
    par2_dir = a.manifest.map_digest(digest)
    victim = next(p for p in par2_dir.iterdir() if p.name.endswith(".par2"))
    victim.unlink()

    # verify without --par2 ignores the par2 damage
    r = runner.invoke(app, ["scan", root, "--verify"])
    assert r.exit_code == 0, r.output

    # verify with --par2 catches it
    r = runner.invoke(app, ["scan", root, "--verify", "--par2"])
    assert r.exit_code == 1
    assert "par2-delete" in r.output


@needs_par2
def test_scan_apply_with_par2_creates_redundancy(archive_root: Path):
    root = str(archive_root)
    r = runner.invoke(app, ["scan", root, "--apply", "--par2", "-y"])
    assert r.exit_code == 0, r.output

    a = Archive(archive_root)
    assert a.manifest.par2_sets
    for fm in a.manifest.entries.values():
        par2_dir = a.manifest.map_digest(fm.digest)
        assert par2_dir.exists()
        on_disk = sorted(p.name for p in par2_dir.iterdir() if p.is_file())
        recorded = sorted(a.manifest.par2_sets[fm.digest])
        assert on_disk == recorded


@needs_par2
def test_e2e_corrupt_and_repair(archive_root: Path):
    root = str(archive_root)
    # initial population with par2
    r = runner.invoke(app, ["scan", root, "--apply", "--par2", "-y"])
    assert r.exit_code == 0, r.output
    assert (archive_root / ".filekeeper" / "manifest.yaml").exists()

    # clean scan
    r = runner.invoke(app, ["scan", root, "--verify", "--par2"])
    assert r.exit_code == 0, r.output

    # corrupt
    target = archive_root / "a.txt"
    original = target.read_bytes()
    target.write_bytes(original + b"X")

    # scan reports edit; --verify exits non-zero
    r = runner.invoke(app, ["scan", root, "--verify"])
    assert r.exit_code == 1
    assert "edit" in r.output

    # repair restores
    r = runner.invoke(app, ["repair", root])
    assert r.exit_code == 0, r.output
    assert target.read_bytes() == original

    # verify clean again
    r = runner.invoke(app, ["scan", root, "--verify", "--par2"])
    assert r.exit_code == 0


def test_list_command(archive_root: Path):
    # no manifest yet -> empty list
    r = runner.invoke(app, ["list", str(archive_root)])
    assert r.exit_code == 0
