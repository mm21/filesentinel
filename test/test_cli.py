from pathlib import Path

from typer.testing import CliRunner

from filekeeper.cli import app

from .conftest import needs_par2

runner = CliRunner()


@needs_par2
def test_e2e_corrupt_and_repair(archive_root: Path):
    # initial population
    r = runner.invoke(app, ["-r", str(archive_root), "rehash", "-y"])
    assert r.exit_code == 0, r.output
    assert (archive_root / ".filekeeper" / "manifest.yaml").exists()

    # clean scan
    r = runner.invoke(app, ["-r", str(archive_root), "scan", "--verify"])
    assert r.exit_code == 0, r.output

    # corrupt
    target = archive_root / "a.txt"
    original = target.read_bytes()
    target.write_bytes(original + b"X")

    # scan reports edit; --verify exits non-zero
    r = runner.invoke(app, ["-r", str(archive_root), "scan", "--verify"])
    assert r.exit_code == 1
    assert "edit" in r.output

    # repair restores
    r = runner.invoke(app, ["-r", str(archive_root), "repair"])
    assert r.exit_code == 0, r.output
    assert target.read_bytes() == original

    # verify clean again
    r = runner.invoke(app, ["-r", str(archive_root), "scan", "--verify"])
    assert r.exit_code == 0


def test_list_command(archive_root: Path):
    # no manifest yet -> empty list
    r = runner.invoke(app, ["-r", str(archive_root), "list"])
    assert r.exit_code == 0
