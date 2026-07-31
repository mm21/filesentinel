from pathlib import Path

from typer.testing import CliRunner

from filesentinel import Archive
from filesentinel.cli import app

from .conftest import needs_par2

runner = CliRunner()


def test_scan_apply_creates_no_par2_by_default(archive_root: Path):
    root = str(archive_root)
    r = runner.invoke(app, ["scan", root, "--apply", "-y"])
    assert r.exit_code == 0, r.output
    assert (archive_root / ".filesentinel" / "manifest.yaml").exists()

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
    assert (archive_root / ".filesentinel" / "manifest.yaml").exists()

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


def test_apply_writes_manifest_sha_sidecar(archive_root: Path):
    root = str(archive_root)
    r = runner.invoke(app, ["scan", root, "--apply", "-y"])
    assert r.exit_code == 0, r.output

    a = Archive(archive_root)
    assert a.manifest.index_path.exists()
    assert a.manifest.index_sha_path.exists()
    assert a.manifest.read_index_sha() == a.manifest.compute_index_sha()


def test_scan_prints_unchanged_after_apply(archive_root: Path):
    root = str(archive_root)
    r = runner.invoke(app, ["scan", root, "--apply", "-y"])
    assert r.exit_code == 0, r.output

    r = runner.invoke(app, ["scan", root])
    assert r.exit_code == 0, r.output
    assert "manifest.yaml: unchanged" in r.output


def test_verify_passes_when_sidecar_matches(archive_root: Path):
    root = str(archive_root)
    r = runner.invoke(app, ["scan", root, "--apply", "-y"])
    assert r.exit_code == 0, r.output

    r = runner.invoke(app, ["scan", root, "--verify"])
    assert r.exit_code == 0, r.output
    assert "manifest.yaml: unchanged" in r.output


def test_verify_fails_when_manifest_tampered(archive_root: Path):
    root = str(archive_root)
    r = runner.invoke(app, ["scan", root, "--apply", "-y"])
    assert r.exit_code == 0, r.output

    a = Archive(archive_root)
    # tamper with manifest.yaml (append a trailing comment so it remains valid YAML
    # and does not register any user-file changes)
    with a.manifest.index_path.open("a", encoding="utf-8") as f:
        f.write("# tampered\n")

    r = runner.invoke(app, ["scan", root, "--verify"])
    assert r.exit_code == 1
    assert "manifest.yaml: changed" in r.output


def test_verify_fails_when_sidecar_missing(archive_root: Path):
    root = str(archive_root)
    r = runner.invoke(app, ["scan", root, "--apply", "-y"])
    assert r.exit_code == 0, r.output

    a = Archive(archive_root)
    a.manifest.index_sha_path.unlink()

    r = runner.invoke(app, ["scan", root, "--verify"])
    assert r.exit_code == 1
    assert "manifest.yaml: changed" in r.output


def test_apply_refreshes_sidecar_after_change(archive_root: Path):
    root = str(archive_root)
    r = runner.invoke(app, ["scan", root, "--apply", "-y"])
    assert r.exit_code == 0, r.output

    a = Archive(archive_root)
    old_sha = a.manifest.read_index_sha()
    assert old_sha is not None

    # introduce a real user-file change so apply rewrites the manifest
    (archive_root / "new.txt").write_bytes(b"new content\n")
    r = runner.invoke(app, ["scan", root, "--apply", "-y"])
    assert r.exit_code == 0, r.output

    a = Archive(archive_root)
    new_sha = a.manifest.read_index_sha()
    assert new_sha is not None
    assert new_sha != old_sha
    assert new_sha == a.manifest.compute_index_sha()
