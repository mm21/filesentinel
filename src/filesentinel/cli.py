"""
CLI implementation: a thin Typer layer over the core framework.
"""

from __future__ import annotations

import logging
import sys
from fnmatch import fnmatch
from pathlib import Path
from typing import Optional

import rich.traceback
import typer
from rich.logging import RichHandler
from rich.table import Table

from .archive import Archive
from .manifest import Par2Change, PendingChange
from .utils import console

rich.traceback.install(show_locals=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    handlers=[
        RichHandler(
            rich_tracebacks=True,
            console=console,
            show_level=True,
            show_time=True,
            show_path=False,
        )
    ],
)

app = typer.Typer(
    rich_markup_mode="rich",
    no_args_is_help=True,
    add_completion=False,
)

_logger = logging.getLogger(__name__)


ROOT_ARG = typer.Argument(
    ...,
    exists=True,
    file_okay=False,
    dir_okay=True,
    resolve_path=True,
    help="Path to archive folder root",
)


@app.callback()
def main(
    ctx: typer.Context,
    manifest: Optional[Path] = typer.Option(
        None, "--manifest", "-m", help="Path to manifest folder"
    ),
    config: Optional[Path] = typer.Option(
        None, "--config", "-c", help="Path to config YAML file"
    ),
):
    """
    FileSentinel: File archiving utility
    """
    ctx.obj = {"manifest": manifest, "config": config}


@app.command("list", help="List files in the manifest (no scan)")
def list_cmd(
    ctx: typer.Context,
    root: Path = ROOT_ARG,
    depth: Optional[int] = typer.Option(None, "--depth", "-d"),
    paths: list[str] = typer.Argument(None),
):
    archive = _get_archive(ctx, root)
    entries = archive.manifest.entries
    entry_names = list(entries.keys())
    paths = paths or []

    table = Table(title=f"{len(entries)} file(s) in manifest")
    table.add_column("path")
    table.add_column("size", justify="right")
    table.add_column("digest")

    for rel, fm in entries.items():
        if not _filter_paths(rel, paths):
            continue
        if depth is not None and rel.count("/") > depth:
            continue
        end_section = entry_names[-1] == rel
        table.add_row(
            rel, _format_size(fm.size), fm.digest[:12], end_section=end_section
        )
    table.add_row("total", _format_size(sum(fm.size for fm in entries.values())), "-")
    console.print(table)


@app.command(help="Scan archive and report differences from manifest")
def scan(
    ctx: typer.Context,
    root: Path = ROOT_ARG,
    fast: bool = typer.Option(False, "--fast", help="Skip hashing if size+mtime match"),
    verify: bool = typer.Option(
        False, "--verify", help="Exit with error code if archive differs from manifest"
    ),
    apply: bool = typer.Option(
        False,
        "--apply",
        help="Update manifest with detected changes",
    ),
    par2: bool = typer.Option(
        False,
        "--par2",
        help="Also create/verify par2 redundancy files",
    ),
    yes: bool = typer.Option(
        False, "-y", "--yes", help="Skip confirmation when applying"
    ),
    paths: list[str] = typer.Argument(None),
):
    archive = _get_archive(ctx, root)
    changes = archive.scan(fast=fast)
    par2_changes = archive.scan_par2() if par2 else []
    if paths:
        changes = [c for c in changes if _filter_paths(_change_path(c), paths)]
    _render_changes(changes)
    if par2:
        _render_par2_changes(par2_changes)
    sha_changed = _render_manifest_sha_status(archive)
    if verify and (changes or par2_changes or sha_changed):
        sys.exit(1)
    if apply and (changes or par2_changes):
        if not yes:
            typer.confirm("Proceed with update?", abort=True)
        if changes:
            archive.apply(changes, par2=par2)
        if par2_changes:
            archive.apply_par2(par2_changes)
        archive.manifest.update_index_sha()
        console.print("[green]manifest updated[/green]")


@app.command(help="Repair corrupted (edited) files using par2 redundancy data")
def repair(ctx: typer.Context, root: Path = ROOT_ARG):
    archive = _get_archive(ctx, root)
    changes = archive.scan()
    _render_changes(changes)
    if not changes:
        return
    report = archive.repair(changes)
    for p in report.repaired:
        _logger.info("repaired %s", p)
    for p in report.extraneous:
        _logger.warning("extraneous %s", p)
    for p in report.unrepairable:
        _logger.error("unrepairable %s", p)
    if not report.ok:
        sys.exit(1)


@app.command(help="Rip a disk to .iso and add it to the archive")
def rip(
    ctx: typer.Context,
    root: Path = ROOT_ARG,
    src: Path = typer.Argument(..., help="Source disk device."),
    dest: Path = typer.Argument(
        ..., help="Destination .iso path relative to archive root."
    ),
    parents: bool = typer.Option(
        False, "--parents", help="Create parent folders if missing."
    ),
):
    archive = _get_archive(ctx, root)
    f = archive.rip_disk(src, dest, create_parents=parents)
    console.print(f"[green]ripped[/green] {f.rel_path}")


def _get_archive(ctx: typer.Context, root: Path) -> Archive:
    opts = ctx.obj
    return Archive(root, manifest_path=opts["manifest"], config_path=opts["config"])


def _change_path(ch: PendingChange) -> str:
    if ch.new is not None:
        return ch.new.rel_path.as_posix()
    assert ch.old is not None
    return ch.old.path


def _filter_paths(rel: str, paths: list[str]) -> bool:
    if not paths:
        return True
    return any(fnmatch(rel, p) for p in paths)


def _format_size(n: int) -> str:
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if n < 1024:
            return f"{n:.1f} {unit}" if unit != "B" else f"{n} B"
        n /= 1024  # type: ignore[assignment]
    return f"{n:.1f} PiB"


def _render_par2_changes(changes: list[Par2Change]) -> None:
    if not changes:
        return
    table = Table(title=f"{len(changes)} pending par2 change(s)")
    table.add_column("change")
    table.add_column("content digest")
    table.add_column("par2 file")
    table.add_column("digest")
    for ch in changes:
        match ch.change_type:
            case "add":
                assert ch.new is not None
                table.add_row(
                    "[green]par2-add[/green]",
                    ch.content_digest[:12],
                    ch.name,
                    ch.new.digest[:12],
                )
            case "delete":
                assert ch.old is not None
                table.add_row(
                    "[red]par2-delete[/red]",
                    ch.content_digest[:12],
                    ch.name,
                    ch.old.digest[:12],
                )
            case "edit":
                assert ch.old is not None and ch.new is not None
                table.add_row(
                    "[magenta]par2-edit[/magenta]",
                    ch.content_digest[:12],
                    ch.name,
                    f"{ch.old.digest[:12]} -> {ch.new.digest[:12]}",
                )
    console.print(table)


def _render_manifest_sha_status(archive: Archive) -> bool:
    """
    Print the manifest.yaml sidecar SHA status.

    Returns True iff changed/mismatched.
    """
    m = archive.manifest
    current = m.compute_index_sha()
    recorded = m.read_index_sha()
    if current is None:
        if recorded is None:
            return False
        console.print("[red]manifest.yaml: missing[/red] (sidecar present)")
        return True
    if recorded is None:
        console.print(
            f"[magenta]manifest.yaml: changed[/magenta] "
            f"(no sidecar; current={current[:12]})"
        )
        return True
    if current == recorded:
        console.print(f"[green]manifest.yaml: unchanged[/green] ({current[:12]})")
        return False
    console.print(
        f"[magenta]manifest.yaml: changed[/magenta] "
        f"({recorded[:12]} -> {current[:12]})"
    )
    return True


def _render_changes(changes: list[PendingChange]) -> None:
    if not changes:
        console.print("[green]archive matches manifest[/green]")
        return
    table = Table(title=f"{len(changes)} pending change(s)")
    table.add_column("change")
    table.add_column("path")
    table.add_column("digest")
    for ch in changes:
        match ch.change_type:
            case "add":
                assert ch.new is not None
                table.add_row(
                    "[green]add[/green]", ch.new.rel_path.as_posix(), ch.new.digest[:12]
                )
            case "delete":
                assert ch.old is not None
                table.add_row("[red]delete[/red]", ch.old.path, ch.old.digest[:12])
            case "move":
                assert ch.old is not None and ch.new is not None
                table.add_row(
                    "[yellow]move[/yellow]",
                    f"{ch.old.path} -> {ch.new.rel_path.as_posix()}",
                    ch.new.digest[:12],
                )
            case "edit":
                assert ch.old is not None and ch.new is not None
                table.add_row(
                    "[magenta]edit[/magenta]",
                    ch.new.rel_path.as_posix(),
                    f"{ch.old.digest[:12]} -> {ch.new.digest[:12]}",
                )
    console.print(table)
    counts = {"add": 0, "edit": 0, "delete": 0, "move": 0}
    for ch in changes:
        counts[ch.change_type] += 1
    console.print(
        f"[green]add[/green]: {counts['add']}  "
        f"[magenta]edit[/magenta]: {counts['edit']}  "
        f"[red]delete[/red]: {counts['delete']}  "
        f"[yellow]move[/yellow]: {counts['move']}"
    )


if __name__ == "__main__":
    app()
