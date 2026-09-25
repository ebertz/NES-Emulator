# Conventions

## Language

- Python 3.11+ for local play; CI and unit tests run under the operator's
  `python3`.
- Package layout lives under `src/`. Prefer `python -m nes_emulator` once the
  frontend ticket lands; until then tests run from `src/`.

## Naming

- Modules are short nouns (`cpu`, `ppu`, `rom`, `bus`).
- Tests are `test_<area>.py` under `src/tests/`.

## Git

- Never commit commercial ROMs. Keep `*.nes` ignored except the nestest fixture
  under `src/tests/testROMs/`.
- Prefer small, reviewable PRs that match one factory ticket's touchSet.

## Verification

Default automated command from `src/`:

```sh
python3 -m compileall -q . && python3 -m unittest discover -s tests -v
```
