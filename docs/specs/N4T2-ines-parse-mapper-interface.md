<!-- GITHUB ISSUE TRACKING METADATA -->
<!-- Issue Key: N4T2 -->
<!-- Last Updated: 2026-09-29T14:49:00-05:00 -->
<!-- Description Hash: n/a (factory ticket) -->
<!-- Spec Version: 1.0 -->
<!-- END METADATA -->

# N4T2 — iNES 1.0 parse + mapper interface (Mapper 0 / NROM)

## Reviewer's Guide

- **Problem:** `src/rom.py` opens a hard-coded, cwd-relative `tests/testROMs/nestest.nes`,
  checks only the `NES` magic (and only `print`s on failure), and copies PRG/CHR without
  reading flags 6/7. There is no mapper abstraction, so no path exists to MMC2 (mapper 9).
- **Change:** path-taking loader, a pure iNES 1.0 header parser, a mapper protocol with
  one implementation (NROM), and a clear error for any other mapper id.
- **Non-goals:** MMC2 / mapper 9 (later ticket), NES 2.0 extended fields, a real CPU bus,
  PPU nametable mirroring hardware, PRG RAM at `$6000-$7FFF`, fixing the 22 pre-existing
  CPU test failures.

References: [nesdev iNES](https://www.nesdev.org/wiki/INES), [nesdev NROM](https://www.nesdev.org/wiki/NROM).

## Current State (verified 2026-09-29)

- `rom.ROM()` takes no arguments; module constant `filepath = 'tests/testROMs/nestest.nes'`.
- `cpu.CPU.__init__` calls `self.memory.loadROM(rom.ROM())` unconditionally.
- `memory.Memory.loadROM(rom)` copies `rom.prg_rom` to `$C000` only (no `$8000` mirror).
- nestest header: `4E 45 53 1A 01 01 00 00 00…` → 1×16 KB PRG, 1×8 KB CHR, mapper 0,
  horizontal mirroring, no trainer, no battery.
- Baseline from `src/`: `python3 -m unittest discover -s tests` → 80 run, **22 failures**
  (AddressingModeTests indirect/implied/relative, InstructionTests branch/flag/jsr/plp/rti).
  These are pre-existing and out of scope; this ticket must not change the pass/fail set
  except by adding new passing tests.

## Requirements

### R1 — Loader takes a filesystem path

- `rom.ROM(path)` (accepts `str` or `os.PathLike`) reads the file at `path`. The module-level
  `filepath` constant is removed; `rom.py` performs no I/O at import.
- The file is opened with a context manager (no leaked handle on error).
- Resulting object exposes at least: `header` (R2), `trainer` (`bytes` of length 512 or
  `None`), `prg_rom` (`bytes`), `chr_rom` (`bytes`, empty when CHR ROM size is 0), and
  `mapper` (a Mapper instance, R5/R6).
- Backward-compatible attributes `prg_rom_size` / `chr_rom_size` (bank counts) remain
  available, derived from `header`.

### R2 — iNES 1.0 header parse (pure function)

`rom.parse_header(data: bytes) -> INESHeader` operates on the first 16 bytes only and does
no I/O, so it is unit-testable with synthetic byte strings. `INESHeader` is an immutable
record (e.g. frozen dataclass) with:

| Field | Source | Notes |
|---|---|---|
| `prg_rom_banks` | byte 4 | units of 16 KB |
| `chr_rom_banks` | byte 5 | units of 8 KB; 0 ⇒ board uses CHR RAM |
| `mirroring` | flags 6 bit 0, bit 3 | `Mirroring.HORIZONTAL` (bit0=0), `Mirroring.VERTICAL` (bit0=1); bit 3 set ⇒ `Mirroring.FOUR_SCREEN` regardless of bit 0 |
| `has_battery` | flags 6 bit 1 | parsed, not acted on |
| `has_trainer` | flags 6 bit 2 | drives R3 |
| `mapper` | flags 6 bits 4-7 (low nibble), flags 7 bits 4-7 (high nibble) | `(flags7 & 0xF0) \| (flags6 >> 4)` |
| `is_nes2` | flags 7 bits 2-3 == `0b10` | detection only |

Header rules:

- Bytes 0-3 MUST equal `b"NES\x1A"`; otherwise raise `rom.ROMFormatError` (subclass of
  `ValueError`) with a message saying the iNES magic is missing. No `print`.
- Fewer than 16 bytes ⇒ `ROMFormatError`.
- NES 2.0 headers are accepted and parsed with the 1.0 field layout above (`is_nes2=True`);
  NES 2.0 extension bytes are ignored.
- Legacy "DiskDude!" garbage: when `is_nes2` is false and any of bytes 12-15 is non-zero,
  the flags 7 high nibble is treated as 0 when computing `mapper` (nesdev recommendation).

### R3 — Trainer skip

When `has_trainer` is set, the 512 bytes following the header are read into `trainer` and
PRG ROM begins at offset `16 + 512`; otherwise PRG begins at offset 16 and `trainer` is
`None`. The trainer is not mapped into CPU space in this ticket.

### R4 — Size validation

- PRG length = `16384 × prg_rom_banks`, CHR length = `8192 × chr_rom_banks`, read sequentially
  after header (+ trainer).
- If the file is shorter than header + trainer + PRG + CHR ⇒ `ROMFormatError` naming the
  expected and actual byte counts. Trailing bytes beyond that (e.g. PlayChoice data) are
  ignored.
- `prg_rom_banks == 0` ⇒ `ROMFormatError` (iNES 1.0 has no valid zero-PRG image).

### R5 — Mapper protocol (new module `src/mapper.py`)

A base class `Mapper` defining the cartridge interface every future mapper (incl. MMC2)
implements:

- `cpu_read(addr: int) -> int` / `cpu_write(addr: int, value: int) -> None` — CPU `$4020-$FFFF` space.
- `ppu_read(addr: int) -> int` / `ppu_write(addr: int, value: int) -> None` — PPU `$0000-$1FFF` pattern space.
- `mirroring` property returning the `Mirroring` value (MMC2 will change it at runtime,
  so it is a property, not a constructor-frozen field on the header).

Construction goes through one factory: `mapper.create_mapper(header, prg_rom, chr_rom) -> Mapper`,
backed by a registry `{mapper_id: class}` so MMC2 is a one-line registration later.
`ROM.__init__` obtains its `mapper` only through this factory.

`Mirroring` lives in one place (either module) and is imported by the other; do not
define it twice.

### R6 — Mapper 0 (NROM) behavior per nesdev

- **PRG:** `cpu_read(addr)` for `$8000 ≤ addr ≤ $FFFF` returns
  `prg_rom[(addr - 0x8000) % len(prg_rom)]`. Hence NROM-128 (16 KB) mirrors at `$8000` and
  `$C000`; NROM-256 (32 KB) maps linearly.
- `cpu_write` to `$8000-$FFFF` is ignored (ROM).
- Addresses `$4020-$7FFF`: `cpu_read` returns 0 and `cpu_write` is ignored (no PRG RAM in
  this ticket).
- **CHR:** `ppu_read(addr)` for `$0000-$1FFF` returns `chr[addr]`. With `chr_rom_banks == 1`
  the backing store is CHR ROM and `ppu_write` is ignored. With `chr_rom_banks == 0` the
  mapper allocates 8 KB of zeroed CHR RAM and `ppu_write` stores `value & 0xFF`.
- **Validation:** NROM accepts only `prg_rom_banks ∈ {1, 2}` and `chr_rom_banks ∈ {0, 1}`;
  anything else ⇒ `ROMFormatError` naming mapper 0 and the offending bank count.
- `mirroring` returns the header's mirroring (fixed for NROM).

### R7 — Unsupported mappers

`create_mapper` with an id not in the registry raises `mapper.UnsupportedMapperError`
(subclass of `ValueError`) carrying `mapper_id` as an attribute and a message containing
the decimal id, e.g. `Unsupported iNES mapper 9 (supported: 0)`. The error surfaces from
`rom.ROM(path)` unchanged (not swallowed, not printed).

### R8 — Call-site wiring (nestest still loads)

- `cpu.CPU.__init__(self, cartridge=None)`: when a cartridge (a `rom.ROM`) is supplied it is
  loaded via `memory.loadROM`; when omitted, no ROM is loaded and no file is opened.
  `CPU` must not name or resolve a nestest path.
- `memory.Memory.loadROM(cartridge)` fills `$8000-$FFFF` by calling
  `cartridge.mapper.cpu_read(addr)` for each address (flat-memory stopgap until the bus
  ticket; the mapper remains the single source of cartridge bytes). For nestest this
  places PRG at both `$8000` and `$C000`.
- Any existing test that needs nestest constructs `rom.ROM(<path resolved from the test
  file via Path(__file__)>)` and passes it to `CPU(...)` (per `docs/code/patterns.md`).

## Design Decisions

- **Pure parser + thin loader:** `parse_header` has no I/O so header edge cases are tested
  with literal byte strings; `ROM(path)` is the only I/O point (patterns.md "library code
  takes paths as args").
- **Registry factory, one construction path:** avoids per-caller `if mapper == 0` branches
  that MMC2 would have to duplicate.
- **Optional cartridge on `CPU`:** a real injection point, not a test-only seam; production
  callers (future frontend) pass the operator's ROM. Removes the anti-pattern "Hard-coding
  nestest into construction".
- **Governing decisions:** no "Governing decision:" line exists in the
  `emulator-core` or `tests` LEAF docs; this design is consistent with their Public
  Contract ("ROM loading accepts a filesystem path and will grow a mapper interface",
  "Callers construct a CPU with injected memory/ROM").

## Subsystem Impact

- **Affected subsystems:** `emulator-core` (`rom.py` rewrite, new `mapper.py`, small
  edits to `cpu.py` and `memory.py`); `tests` (new `src/tests/test_rom.py`, ROMTests setup
  change in `test_cpu.py`).
- **Boundary crossings:** only `tests → emulator-core`, which already exists. No new edges.
- **New subsystems:** none.
- **Catalog impact:** `docs/architecture/overview.md` Source File Catalog must gain
  `src/mapper.py` under emulator-core and `src/tests/test_rom.py` under tests in the same
  PR that creates them; `sub-systems/emulator-core.md` Anchor Files gains `src/mapper.py`
  and its Failure Modes line about hard-coded paths can be updated once fixed.

## Test Expectations (acceptance only — test agent owns test code)

- All fixtures are synthetic: headers built as byte literals, tiny ROM images written to a
  temporary directory. No commercial ROM; no new `.nes` committed.
- Coverage must demonstrate: each header field in R2 (incl. four-screen override, mapper
  high/low nibble combination, NES 2.0 detection, DiskDude masking); bad magic; short
  header; truncated body; trainer skip (PRG first byte is the byte after the 512-byte
  trainer); NROM-128 mirroring (`cpu_read(0x8000) == cpu_read(0xC000)`); NROM-256 linear
  mapping (`cpu_read(0xC000) == prg[0x4000]`); PRG writes ignored; CHR ROM read-only; CHR RAM
  writable; NROM bank-count rejection; unsupported mapper error message contains the id
  and `mapper_id` attribute is set.
- nestest loads through `rom.ROM(path)` with a `__file__`-relative path and yields
  mapper 0, 1 PRG bank, 1 CHR bank, horizontal mirroring, no trainer.

## Verification

From `src/`: `python3 -m compileall -q . && python3 -m unittest discover -s tests -v`.
Pass criterion: the 58 previously passing tests still pass, new ROM/mapper tests pass, and
the failure set is exactly the 22 pre-existing failures listed in Current State.

## Plain-English Hand-off

**What this spec does:** The emulator will read the header of any standard NES cartridge
file you point it at, understand which kind of cartridge hardware it describes, and run the
simplest kind (the one the built-in CPU test program uses). Any other cartridge type is
refused with a message saying exactly which type it was.

**Tradeoffs:**
- Punch-Out (mapper 9) will still not run after this; it now fails immediately with a
  clear "unsupported mapper 9" message instead of silently loading garbage.
- Creating the CPU no longer automatically loads the test program; anything that wants it
  must now ask for it explicitly.
- The test program's code will now also appear at a second address range where real
  hardware mirrors it; this matches real hardware but is a visible change in memory.
- Memory is still a flat copy of the cartridge until a later ticket adds a proper bus, so
  cartridge hardware that switches banks at runtime cannot work yet.
- The 22 existing CPU test failures are not addressed here.

## Changelog

### Version 1.0 - 2026-09-29
**Source Issue:** N4T2
**Change Type:** Major

**Changes:**
- Initial specification: path-based iNES 1.0 loader, header parser, trainer skip, mapper
  protocol with NROM, unsupported-mapper error, CPU/memory wiring.

**Impact:** Requires code changes in `emulator-core` and new tests in `tests`.

---
