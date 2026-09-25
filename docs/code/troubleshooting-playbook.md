# Troubleshooting Playbook

## Symptom: every CPU test raises FileNotFoundError

**Cause:** ROM path is cwd-relative or CPU opens nestest implicitly.
**Fix:** inject ROM; resolve nestest from `Path(__file__)` in tests.

## Symptom: `python3 -m compileall` fails on `ppu.py`

**Cause:** syntax error (e.g. missing `:` on `__init__`).
**Fix:** make PPU parse even if rendering is still a stub.

## Symptom: unittest passes only when cwd is `src/`

**Cause:** discovery or imports assume that cwd.
**Fix:** document `cd src && python3 -m unittest discover -s tests -v` as the
gate; avoid cwd-dependent opens in library code.

## Symptom: Punch-Out boots as garbage tiles or crashes on bank switch

**Cause:** missing or wrong Mapper 9 CHR latches / PRG window.
**Fix:** implement MMC2 per nesdev; cover FD/FE latches with synthetic CHR tests.

## Symptom: factory intake refuses the repository as a skeleton

**Cause:** ADLC overview lacks Source Roots/Catalog, or docs still contain the
generator stub marker.
**Fix:** keep real docs under `docs/` committed; re-run onboard-repo and promote.
