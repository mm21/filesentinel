"""
CLI implementation.

TODO:

root options:
- manifest: Path
    - path to manifest folder, defaults to [root]/.manifest
- config: Path
    - path to config yaml, defaults to [manifest]/config.yaml

root arguments:
- root: Path
    - root folder of archive tree

subcommands:
- list
    - load manifest (doesn't scan folder)
    - list files and size of each in alphabetical order, along with folders and their
    total size
    - options:
        - depth: only recurse to this depth
    - arguments:
        - optional list of glob paths relative to archive root, filter output to these
        paths if passed
- scan
    - scan archive folder, load manifest, aggregate files added/changed/deleted
    - list added/changed/deleted files in alphabetical order and show state
    (added/changed/deleted)
    - options:
        - verify: exit with error code if archive folder not consistent with
        manifest (any files added/changed/deleted)
            - uses both hash check and par2 verify
    - arguments:
        - optional list of glob paths relative to archive root, filter output to these
        paths if passed
- rehash
    - perform steps in scan command
    - optionally prompt user to proceed with updating (option -y/--yes to skip prompt)
    - update manifest
- repair
    - perform steps in scan command
    - use par2 redundancy data to repair any files detected to be corrupted (changed)
    - error logs + fail at end if any files added/deleted or failed to be repaired
- rip
    - helper to rip an iso from a disk drive and add it to the archive
    - fails if file already exists
    - options:
        - parents: create parent folders if not existing
    - arguments:
        - path to source drive
        - relative path to destination .iso file
"""
