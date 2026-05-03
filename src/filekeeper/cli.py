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
from rich.console import Console
from rich.logging import RichHandler
from rich.table import Table

from .archive import Archive
from .manifest import PendingChange

rich.traceback.install(show_locals=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    handlers=[
        RichHandler(
            rich_tracebacks=True,
            console=Console(highlight=False),
            show_level=True,
            show_time=True,
            show_path=False,
        )
    ],
)

_LOGGER = logging.getLogger(__name__)
_console = Console(highlight=False)

app = typer.Typer(
    rich_markup_mode="rich",
    no_args_is_help=True,
    add_completion=False,
)


@app.callback()
def main(
    ctx: typer.Context,
    root: Path = typer.Option(
        ...,
        "--root",
        "-r",
        exists=True,
        file_okay=False,
        dir_okay=True,
        resolve_path=True,
        help="Path to archive folder root",
    ),
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
    ctx.obj = Archive(root, manifest_path=manifest, config_path=config)


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
        _console.print("[green]archive matches manifest[/green]")
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
    _console.print(table)


@app.command("list", help="List files in the manifest (no scan)")
def list_cmd(
    ctx: typer.Context,
    depth: Optional[int] = typer.Option(None, "--depth", "-d"),
    paths: list[str] = typer.Argument(None),
):
    archive: Archive = ctx.obj
    entries = archive.manifest.entries
    paths = paths or []

    table = Table(title=f"{len(entries)} file(s) in manifest")
    table.add_column("path")
    table.add_column("size", justify="right")
    table.add_column("digest")
    for rel in sorted(entries):
        if not _filter_paths(rel, paths):
            continue
        if depth is not None and rel.count("/") > depth:
            continue
        fm = entries[rel]
        table.add_row(rel, _format_size(fm.size), fm.digest[:12])
    _console.print(table)


# TODO: --apply, -y/--yes, absorb functionality of `rehash` and then delete `rehash`
@app.command(help="Scan archive and report differences from manifest")
def scan(
    ctx: typer.Context,
    fast: bool = typer.Option(False, "--fast", help="Skip rehash if size+mtime match"),
    verify: bool = typer.Option(
        False, "--verify", help="Exit with error code if archive differs from manifest"
    ),
    paths: list[str] = typer.Argument(None),
):
    archive: Archive = ctx.obj
    changes = archive.scan(fast=fast)
    if paths:
        changes = [c for c in changes if _filter_paths(_change_path(c), paths)]
    _render_changes(changes)
    if verify and changes:
        sys.exit(1)


@app.command(help="Scan, then update manifest and par2 redundancy")
def rehash(
    ctx: typer.Context,
    fast: bool = typer.Option(False, "--fast"),
    yes: bool = typer.Option(False, "-y", "--yes", help="Skip confirmation."),
):
    archive: Archive = ctx.obj
    changes = archive.scan(fast=fast)
    _render_changes(changes)
    if not changes:
        return
    if not yes:
        typer.confirm("Proceed with update?", abort=True)
    archive.apply(changes)
    _console.print("[green]manifest updated[/green]")


@app.command(help="Repair corrupted (edited) files using par2 redundancy data")
def repair(ctx: typer.Context):
    archive: Archive = ctx.obj
    changes = archive.scan()
    _render_changes(changes)
    if not changes:
        return
    report = archive.repair(changes)
    for p in report.repaired:
        _LOGGER.info("repaired %s", p)
    for p in report.extraneous:
        _LOGGER.warning("extraneous %s", p)
    for p in report.unrepairable:
        _LOGGER.error("unrepairable %s", p)
    if not report.ok:
        sys.exit(1)


@app.command(help="Rip a disk to .iso and add it to the archive")
def rip(
    ctx: typer.Context,
    src: Path = typer.Argument(..., help="Source disk device."),
    dest: Path = typer.Argument(
        ..., help="Destination .iso path relative to archive root."
    ),
    parents: bool = typer.Option(
        False, "--parents", help="Create parent folders if missing."
    ),
):
    archive: Archive = ctx.obj
    f = archive.rip_disk(src, dest, create_parents=parents)
    _console.print(f"[green]ripped[/green] {f.rel_path}")


def _change_path(ch: PendingChange) -> str:
    if ch.new is not None:
        return ch.new.rel_path.as_posix()
    assert ch.old is not None
    return ch.old.path


if __name__ == "__main__":
    app()
