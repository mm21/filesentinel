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
from .manifest import PendingChange
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
    FileKeeper: File archiving utility
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
        help="Update manifest and par2 redundancy with detected changes",
    ),
    yes: bool = typer.Option(
        False, "-y", "--yes", help="Skip confirmation when applying"
    ),
    paths: list[str] = typer.Argument(None),
):
    archive = _get_archive(ctx, root)
    changes = archive.scan(fast=fast)
    if paths:
        changes = [c for c in changes if _filter_paths(_change_path(c), paths)]
    _render_changes(changes)
    if verify:
        par2_report = archive.verify_par2_integrity()
        for problem in par2_report.problems:
            _logger.error("par2 integrity: %s", problem)
        if not par2_report.ok:
            console.print(
                f"[red]par2 integrity failed ({len(par2_report.problems)} problem(s))[/red]"
            )
        else:
            console.print("[green]par2 integrity ok[/green]")
        if changes or not par2_report.ok:
            sys.exit(1)
    if apply and changes:
        if not yes:
            typer.confirm("Proceed with update?", abort=True)
        archive.apply(changes)
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


if __name__ == "__main__":
    app()
