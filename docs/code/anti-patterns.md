# Anti-Patterns

## Hard-coding nestest into construction

WRONG: `CPU.__init__` always loads `tests/testROMs/nestest.nes`.
RIGHT: inject ROM/memory; tests pass an explicit path.

## Committing Punch-Out or other commercial ROMs

WRONG: add `punchout.nes` to the repo for "easier testing".
RIGHT: operator supplies the ROM locally; docs say so; gitignore `*.nes`
except allowlisted fixtures.

## Treating Mapper 0 as enough for Punch-Out

WRONG: ship NROM-only and call Punch-Out done.
RIGHT: implement iNES mapper 9 (MMC2) including CHR latches.

## Cwd-relative fixture opens in library code

WRONG: `open("tests/testROMs/nestest.nes")` from a module.
RIGHT: paths relative to `__file__` in tests; library code takes paths as args.

## Editing generated ADLC bundle stubs instead of repo docs

WRONG: hand-edit onboard-repo output to clear the generator stub marker phrase.
RIGHT: keep authoritative prose in `docs/` in this repository and re-onboard.
