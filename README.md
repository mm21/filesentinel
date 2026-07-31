# FileSentinel

Integrity monitoring and repair toolkit for long-term file archives

[![Python versions](https://img.shields.io/pypi/pyversions/filesentinel.svg)](https://pypi.org/project/filesentinel)
[![PyPI](https://img.shields.io/pypi/v/filesentinel?color=%2334D058&label=pypi%20package)](https://pypi.org/project/filesentinel)
[![Tests](./badges/tests.svg?dummy=8484744)]()
[![Coverage](./badges/cov.svg?dummy=8484744)]()
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

- [FileSentinel](#filesentinel)
  - [Motivation](#motivation)
  - [Getting started](#getting-started)
  - [Concepts](#concepts)
    - [Archive layout](#archive-layout)
    - [Change types](#change-types)
  - [CLI](#cli)
    - [`list`](#list)
    - [`scan`](#scan)
    - [`repair`](#repair)
    - [`rip`](#rip)
  - [Redundancy data](#redundancy-data)
  - [Manifest integrity](#manifest-integrity)
  - [Configuration](#configuration)
  - [Python API](#python-api)

## Motivation

Files sitting on disk for years quietly rot: a bit flips, a drive develops a bad sector, a sync tool truncates a file. Nothing reports an error &mdash; the file is simply no longer what you put there. Backups don't necessarily help, since a corrupted file gets faithfully backed up right over the good copy once the corruption goes unnoticed long enough.

FileSentinel treats an archive folder as content to be watched rather than merely stored. It records a SHA-256 manifest of every file and tells you exactly what changed since the last time you looked. If you opt into redundancy, it stores [par2](https://github.com/Parchive/par2cmdline) recovery data alongside the manifest so corrupted files can be repaired in place, without restoring from a backup.

Intentional changes are just as important as unintentional ones: adding, deleting, and renaming files are all reported, and renames are detected as `move` operations by digest rather than showing up as an unrelated delete/add pair.

## Getting started

First, install from PyPI:

```bash
pip install trilium-alchemy
```

No system-level dependencies are required for the core functionality. FileSentinel just needs the `par2` binary on `PATH` for redundancy and repair, and `ddrescue` if you want to rip disks:

```bash
sudo apt install par2 gddrescue
```

Point it at a folder to take an initial snapshot, optionally creating par2 redundancy data as it goes:

```bash
filesentinel scan --apply --par2 /path/to/archive
```

Later, check whether anything has changed:

```bash
filesentinel scan /path/to/archive
```

And if a file has been corrupted, restore it from redundancy data:

```bash
filesentinel repair /path/to/archive
```

## Concepts

### Archive layout

An archive is simply a folder of files, plus a manifest folder holding everything FileSentinel maintains:

```
archive/
├── docs/
│   └── report.pdf
├── photo.jpg
└── .filesentinel/
    ├── config.yaml
    ├── manifest.yaml
    ├── manifest.yaml.sha256
    └── tree/
        └── ab/
            └── cd/
                └── abcd1234.../
                    ├── redundancy.par2
                    └── redundancy.vol000+01.par2
```

The `.filesentinel` folder is excluded from scans. It can also live outside the archive root entirely &mdash; pass `--manifest` to keep it on separate media, for example when the archive itself is read-only or lives on removable storage.

Redundancy data is content-addressed: par2 sets live under `tree/` keyed by the digest of the file they protect, sharded 2 levels deep to keep directory sizes manageable. Identical files therefore share a single par2 set, and moving or renaming a file doesn't invalidate its redundancy data.

### Change types

A scan compares the files on disk against the manifest and reports:

| Change   | Meaning                                                       |
| -------- | ------------------------------------------------------------- |
| `add`    | File on disk, not in the manifest                              |
| `delete` | File in the manifest, missing from disk                        |
| `move`   | A delete and an add with the same digest, paired up            |
| `edit`   | Same path, different content: possible corruption       |

If a file is marked with `edit`, it means the content no longer matches what was recorded. If you did not change the file yourself, this is exactly the case `repair` addresses.

## CLI

Global options apply to all commands and come before the command name:

```bash
filesentinel --manifest /media/backup/archive-manifest scan /path/to/archive
```

- `--manifest`, `-m`: path to the manifest folder (default: `<root>/.filesentinel`)
- `--config`, `-c`: path to the config file (default: `<manifest>/config.yaml`)

Most commands accept trailing glob patterns to restrict the paths considered, matched against archive-relative posix paths:

```bash
filesentinel scan /path/to/archive 'docs/*.pdf'
```

### `list`

Show the manifest contents without touching the disk:

```bash
filesentinel list /path/to/archive
```

Use `--depth`/`-d` to limit how deep into the tree to report.

### `scan`

Walk the archive, hash its files, and report differences from the manifest:

```bash
filesentinel scan /path/to/archive
```

- `--fast`: skip hashing for files whose size and mtime both match the manifest. Much faster for large archives, but blind to corruption that preserves both &mdash; use it for routine checks, not for integrity audits.
- `--par2`: also scan the par2 redundancy data itself for damage, and maintain it when combined with `--apply`.
- `--apply`: update the manifest to reflect the detected changes, prompting first unless `-y`/`--yes` is given.
- `--verify`: exit with a nonzero status if anything differs, for use in cron jobs and CI.

Applying with `--par2` keeps redundancy data in sync: par2 sets are created for new content and dropped once no manifest entry references their digest.

### `repair`

Scan the archive and restore files reported as `edit` from their par2 sets:

```bash
filesentinel repair /path/to/archive
```

Each repaired file has its par2 set rebuilt afterward, since `par2 repair` consumes it. Files that are missing outright, or whose damage exceeds the available redundancy, are reported as unrepairable and cause a nonzero exit status. Files on disk but not in the manifest are reported as extraneous and left alone.

### `rip`

Rip a disk to an `.iso` inside the archive and add it to the manifest, using `ddrescue` with a conservative two-pass strategy (a fast pass without scraping, then a scraping pass with retries only if needed):

```bash
filesentinel rip /path/to/archive /dev/sr0 discs/backup-2015.iso --parents
```

## Redundancy data

Par2 redundancy is optional and off by default, since generating it costs time and disk space proportional to the archive. Without it, FileSentinel still detects corruption &mdash; it just can't undo it.

The recovery target defaults to 10% of file size, meaning roughly that fraction of a file can be damaged and still recovered. Raise it for irreplaceable data or media you don't trust; lower it if space is tight.

Because the par2 files are themselves subject to the same rot they protect against, their digests are recorded in the manifest too. `scan --par2` verifies them, and `scan --par2 --apply` rebuilds any set that has drifted &mdash; from the current archive file, after confirming that file still matches its recorded digest. If it doesn't, the rebuild is refused: the user data is suspect and should go through `repair` first.

## Manifest integrity

The manifest is the reference against which everything else is judged, so it gets a sidecar of its own: `manifest.yaml.sha256`, written whenever changes are applied. Every scan reports whether the manifest still matches its sidecar.

An unexpected mismatch means the manifest itself was modified or damaged, and its verdict about your files can't be trusted &mdash; worth noticing before concluding that a hundred files were edited.

## Configuration

Optional `config.yaml`, living in the manifest folder by default:

```yaml
# par2 redundancy target, as a percentage of file size
recovery_pct: 10

# glob patterns to exclude from scans, relative to the archive root
ignore_globs:
  - "**/*.tmp"
  - "cache/**"
```

## Python API

The CLI is a thin layer over the `Archive` class, which is usable directly:

```python
from pathlib import Path
from filesentinel import Archive

archive = Archive(Path("/path/to/archive"))

# report differences from the manifest
changes = archive.scan()
for change in changes:
    print(change.change_type, change.new or change.old)

# commit them, maintaining par2 data
archive.apply(changes, par2=True)
archive.manifest.update_index_sha()

# repair corrupted files
report = archive.repair(archive.scan())
assert report.ok
```

`Archive.verify()` is a convenience for the common case: it returns `True` only if a full scan of both files and par2 data comes back clean.
