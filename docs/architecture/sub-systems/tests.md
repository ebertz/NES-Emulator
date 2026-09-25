# tests

Automated checks and legal fixtures for the emulator core.

## Purpose

Prove CPU correctness against nestest and, as tickets land, bus/PPU/mapper/APU
and frontend behavior — without shipping commercial ROMs.

## Anchor Files

- `src/tests/test_cpu.py` — CPU unit and nestest log compare
- `src/tests/testROMs/nestest.nes` — redistributable nestest fixture
- `src/tests/__init__.py` — package marker

## Public Contract

- From `src/`, `python3 -m unittest discover -s tests -v` is the automated gate.
- New tickets add sibling test modules under `src/tests/`; they stay in this
  subsystem until a later catalog split is warranted.

## Key Invariants

- Fixtures under `testROMs/` are redistributable only (nestest, optional blargg /
  Holy Mapperel when vendored).
- Tests resolve fixture paths relative to the test file, not cwd.

## Security Posture

- No network fetches of ROMs in default unit tests.
- Never assert against a Punch-Out path inside the repo.

## Failure Modes

- Cwd-dependent ROM opens produce FileNotFound across the suite.
- Committing a `.nes` outside the allowlisted fixture paths is a defect.
