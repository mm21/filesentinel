"""
Implementation of archive abstraction.
"""

from __future__ import annotations

import logging
import shutil
from dataclasses import dataclass, field
from fnmatch import fnmatch
from pathlib import Path
from typing import Iterator, Sequence

from rich.progress import (
    BarColumn,
    DownloadColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
    TransferSpeedColumn,
)

from .config import ConfigModel
from .file import File
from .manifest import Manifest, PendingChange
from .utils import console, par2_create, par2_repair, rip_disk

DEFAULT_MANIFEST_DIRNAME = ".filekeeper"
DEFAULT_CONFIG_FILENAME = "config.yaml"

_logger = logging.getLogger(__name__)


@dataclass
class RepairReport:
    """
    Outcome of a repair operation.
    """

    repaired: list[str] = field(default_factory=list)
    """
    Paths whose content was restored from par2.
    """

    unrepairable: list[str] = field(default_factory=list)
    """
    Paths that could not be repaired (e.g. deleted, par2 missing/insufficient).
    """

    extraneous: list[str] = field(default_factory=list)
    """
    Paths present on disk but not in the manifest.
    """

    @property
    def ok(self) -> bool:
        return not self.unrepairable


class Archive:
    """
    Core abstraction of an archive folder.

    Consists of:

    - Root folder of archive files (a folder named `.filekeeper` is ignored).
    - Manifest folder, which holds `manifest.yaml` and the digest-keyed
      `tree/` of par2 redundancy data. May be placed outside the archive root.
    - Optional `config.yaml` (default location: inside the manifest folder).
    """

    __root: Path
    __manifest_path: Path
    __config_path: Path
    __config: ConfigModel
    __manifest: Manifest

    def __init__(
        self,
        root: Path,
        manifest_path: Path | None = None,
        config_path: Path | None = None,
    ):
        self.__root = root.resolve()
        self.__manifest_path = (
            manifest_path.resolve()
            if manifest_path is not None
            else self.__root / DEFAULT_MANIFEST_DIRNAME
        )
        self.__config_path = (
            config_path.resolve()
            if config_path is not None
            else self.__manifest_path / DEFAULT_CONFIG_FILENAME
        )
        self.__config = ConfigModel.from_yaml(self.__config_path)
        self.__manifest = Manifest(self.__manifest_path, self)
        self.__manifest.load()

    @property
    def root(self) -> Path:
        return self.__root

    @property
    def manifest(self) -> Manifest:
        return self.__manifest

    @property
    def config(self) -> ConfigModel:
        return self.__config

    @property
    def manifest_path(self) -> Path:
        return self.__manifest_path

    def walk(self) -> Iterator[Path]:
        """
        Yield absolute paths of files under root, skipping the manifest folder and any
        matching configured ignore globs.
        """
        manifest_inside_root = self.__manifest_path.is_relative_to(self.__root)
        for dirpath, dirnames, filenames in self.__root.walk():
            dirnames.sort()
            filenames.sort()
            if manifest_inside_root and dirpath == self.__root:
                dirnames[:] = [d for d in dirnames if d != DEFAULT_MANIFEST_DIRNAME]
            for name in filenames:
                full = dirpath / name
                rel = full.relative_to(self.__root).as_posix()
                if any(fnmatch(rel, g) for g in self.__config.ignore_globs):
                    continue
                yield full

    def scan(self, *, fast: bool = False) -> list[PendingChange]:
        """
        Walk the archive and return changes vs the loaded manifest.
        """
        on_disk: dict[str, File] = {}
        with console.status("[cyan]scanning[/cyan]") as status:
            last_dir: Path | None = None
            for path in self.walk():
                parent = path.parent
                if parent != last_dir:
                    rel_dir = (
                        parent.relative_to(self.__root)
                        if parent != self.__root
                        else Path(".")
                    )
                    status.update(f"[cyan]scanning[/cyan] {rel_dir}")
                    last_dir = parent
                file = File(path, self)
                on_disk[file.rel_path.as_posix()] = file
        on_disk = {p: on_disk[p] for p in sorted(on_disk)}

        if not fast:
            # first pass to load digests since it may be slow
            total_bytes = sum(f.size for f in on_disk.values())
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                DownloadColumn(),
                TimeElapsedColumn(),
                TransferSpeedColumn(),
                console=console,
                transient=True,
            ) as progress:
                task = progress.add_task("hashing", total=total_bytes)
                for file in on_disk.values():
                    progress.update(task, description=f"hashing {file.rel_path}")
                    file.load_digest()
                    progress.advance(task, file.size)

        entries = self.__manifest.entries
        adds: list[PendingChange] = []
        deletes: list[PendingChange] = []
        edits: list[PendingChange] = []

        for rel, file in on_disk.items():
            old = entries.get(rel)
            if old is None:
                adds.append(PendingChange("add", new=file))
                continue
            if fast:
                if file.size == old.size and file.mtime == old.mtime:
                    continue
                edits.append(PendingChange("edit", new=file, old=old))
                continue
            if file.digest == old.digest:
                continue
            edits.append(PendingChange("edit", new=file, old=old))

        for rel, old in entries.items():
            if rel not in on_disk:
                deletes.append(PendingChange("delete", old=old))

        # pair (delete, add) with matching digest -> move
        moves: list[PendingChange] = []
        deletes_by_digest: dict[str, list[PendingChange]] = {}
        for ch in deletes:
            assert ch.old is not None
            deletes_by_digest.setdefault(ch.old.digest, []).append(ch)

        remaining_adds: list[PendingChange] = []
        for ch in adds:
            assert ch.new is not None
            bucket = deletes_by_digest.get(ch.new.digest)
            if bucket:
                del_ch = bucket.pop(0)
                moves.append(PendingChange("move", new=ch.new, old=del_ch.old))
            else:
                remaining_adds.append(ch)
        remaining_deletes = [ch for chs in deletes_by_digest.values() for ch in chs]

        result = remaining_adds + remaining_deletes + moves + edits
        result.sort(key=_change_sort_key)
        return result

    def apply(self, changes: Sequence[PendingChange]) -> None:
        """
        Apply changes to the manifest and update par2 redundancy data on disk.
        """
        # which digests will remain referenced after applying changes?
        future_digests = {fm.digest for fm in self.__manifest.entries.values()}
        for ch in changes:
            if ch.change_type in ("delete", "edit", "move") and ch.old is not None:
                # old digest may or may not still be referenced — recompute below
                pass
            if ch.new is not None:
                future_digests.add(ch.new.digest)

        # tentatively remove old digests then re-add what survives
        # (recompute properly after apply)
        self.__manifest.apply(changes)
        live_digests = {fm.digest for fm in self.__manifest.entries.values()}

        # par2 churn
        for ch in changes:
            match ch.change_type:
                case "add" | "edit":
                    assert ch.new is not None
                    par2_dir = self.__manifest.map_digest(ch.new.digest)
                    if not par2_dir.exists():
                        _logger.info("par2 create %s", ch.new.rel_path)
                        par2_create(
                            ch.new.path,
                            par2_dir,
                            recovery_pct=self.__config.recovery_pct,
                        )
                case "delete":
                    pass
                case "move":
                    pass

            # drop unreferenced par2 dir for old digest
            if ch.old is not None and ch.old.digest not in live_digests:
                old_dir = self.__manifest.map_digest(ch.old.digest)
                if old_dir.exists():
                    _logger.info("par2 drop %s", ch.old.digest[:12])
                    shutil.rmtree(old_dir)

        self.__manifest.save()

    def repair(self, changes: Sequence[PendingChange]) -> RepairReport:
        """
        Use par2 redundancy to repair files reported as edited (suspected corruption).

        Files that are missing or extraneous are reported but cannot be repaired here.
        """
        report = RepairReport()
        for ch in changes:
            match ch.change_type:
                case "edit":
                    assert ch.old is not None and ch.new is not None
                    par2_dir = self.__manifest.map_digest(ch.old.digest)
                    ok = par2_repair(ch.new.path, par2_dir)
                    if ok:
                        report.repaired.append(ch.new.rel_path.as_posix())
                    else:
                        report.unrepairable.append(ch.new.rel_path.as_posix())
                case "delete":
                    assert ch.old is not None
                    report.unrepairable.append(ch.old.path)
                case "add":
                    assert ch.new is not None
                    report.extraneous.append(ch.new.rel_path.as_posix())
                case "move":
                    pass
        return report

    def verify(self) -> bool:
        """
        Return True iff a full scan (no fast-path) yields no pending changes.
        """
        return not self.scan()

    def rip_disk(
        self,
        src_disk: Path,
        dest_iso: Path,
        *,
        create_parents: bool = False,
    ) -> File:
        """
        Rip a disk to `dest_iso` (relative to archive root) and add it to the manifest.
        """
        target = (self.__root / dest_iso).resolve()
        if not target.is_relative_to(self.__root):
            raise ValueError(f"dest_iso must be inside archive root: {dest_iso}")
        if target.exists():
            raise FileExistsError(target)
        if not target.parent.exists():
            if not create_parents:
                raise FileNotFoundError(target.parent)
            target.parent.mkdir(parents=True, exist_ok=True)
        rip_disk(src_disk, target)
        f = File(target, self)
        self.apply([PendingChange("add", new=f)])
        return f


_CHANGE_ORDER = {"add": 0, "delete": 1, "move": 2, "edit": 3}


def _change_sort_key(ch: PendingChange) -> tuple[int, str]:
    if ch.new is not None:
        path = ch.new.rel_path.as_posix()
    else:
        assert ch.old is not None
        path = ch.old.path
    return (_CHANGE_ORDER[ch.change_type], path)
