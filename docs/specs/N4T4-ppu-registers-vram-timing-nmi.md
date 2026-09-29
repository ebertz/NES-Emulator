<!-- GITHUB ISSUE TRACKING METADATA -->
<!-- Issue Key: N4T4 -->
<!-- Last Updated: 2026-09-29T17:30:00-05:00 -->
<!-- Description Hash: n/a (factory ticket) -->
<!-- Spec Version: 1.0 -->
<!-- END METADATA -->

# N4T4 — PPU registers / VRAM / timing / NMI

## Reviewer's Guide

- **Problem:** The ticket text says `src/ppu.py` does not compile. That is stale. N4T3
  made it compile and gave it just enough registers (CTRL, STATUS, OAMADDR, OAMDATA,
  OAM DMA) and vblank timing to drive NMI. It still has no PPU address space. There is no
  nametable RAM, no palette RAM, and no pattern-table access through the mapper.
  `$2007` only increments the address, and reads return the I/O latch instead of the read
  buffer. `$2005` only flips `w`. `$2006` builds a private `_ppuaddr` with no `t`/`x`.
  There is no odd-frame dot skip.
- **Change:** The PPU owns 2 KB nametable RAM (CIRAM) and 32 bytes of palette RAM, and it
  reads the cartridge's pattern tables and live mirroring mode through the injected
  mapper. It implements the loopy `v`/`t`/`x`/`w` register semantics for
  `$2000/$2002/$2005/$2006/$2007`, the buffered `$2007` read with the palette exception,
  palette mirroring, and nesdev frame timing: vblank set and cleared, NMI line, and the
  odd-frame skip. `Console` passes the cartridge mapper to the PPU.
- **Non-goals:** background/sprite rendering and pixel output. Also out: dot-level scroll
  updates during rendering (coarse-X/Y increments, the dot-257 horizontal copy, the
  pre-render vertical copy) and the `$2007`-during-rendering increment glitch. Also
  out: sprite-0 hit and overflow detection (the flags stay 0 except where they are
  cleared), the `$2002` read/vblank-set race suppression, the power-up/reset register
  warm-up ignore window, open-bus decay, `$2004` reads during rendering, MMC2 latches,
  and single-screen mirroring modes.

References: [PPU registers](https://www.nesdev.org/wiki/PPU_registers),
[PPU scrolling](https://www.nesdev.org/wiki/PPU_scrolling),
[PPU memory map](https://www.nesdev.org/wiki/PPU_memory_map),
[Mirroring](https://www.nesdev.org/wiki/Mirroring),
[PPU palettes](https://www.nesdev.org/wiki/PPU_palettes),
[PPU frame timing](https://www.nesdev.org/wiki/PPU_frame_timing),
[NMI](https://www.nesdev.org/wiki/NMI).

## Current State (verified 2026-09-29 at `f54c4f7`)

- `ppu.PPU()` takes no arguments and compiles. Attributes: `ctrl`, `mask`, `oamaddr`,
  `oam`, `w`, `scanline`, `dot`, `frame`, `vblank`, `sprite_zero_hit`,
  `sprite_overflow`, `_data_latch`, `_ppuaddr`, `_ppuaddr_latch`. `nmi_line` is a
  property returning `vblank and ctrl & 0x80`.
- `read_register(7)` returns `_data_latch` (not a read buffer). `write_register(7, v)`
  only increments `_ppuaddr` by 1 or 32. No memory is read or written.
- `write_register(5, v)` flips `w` and stores nothing. `write_register(6, v)` builds
  `_ppuaddr` from two writes sharing `w`. `read_register(2)` clears `vblank` and `w`.
- `step()`: 341 dots × 262 scanlines, vblank set at (241, 1), vblank and sprite flags
  cleared at (261, 1). There is no odd-frame skip.
- `Console.__init__` builds `PPU()` and hands the cartridge only to `Bus`. The PPU never
  sees the mapper. `Console.step()` calls `ppu.step()` `3 × elapsed` times and then
  `cpu.set_nmi_line(ppu.nmi_line)`, and the CPU latches NMI on a rising edge.
- `mapper.Mapper` already exposes `ppu_read`/`ppu_write` for `$0000-$1FFF` and a live
  `mirroring` property (`HORIZONTAL`, `VERTICAL`, `FOUR_SCREEN`).
- From `src/`: `python3 -m compileall -q . && python3 -m unittest discover -s tests` →
  **142 run, 0 failures**. `test_console.py::test_ppu_status_read_resets_write_toggle_for_ppuaddr`
  asserts on the private `ppu._ppuaddr`, which this ticket removes (see R9).

## Requirements

### R1 — Construction and state ownership

- `ppu.PPU(mapper=None)`. `mapper` is a `mapper.Mapper` (or any object with
  `ppu_read`, `ppu_write`, `mirroring`). `PPU()` with no argument stays valid.
- `Console.__init__` constructs `PPU(cartridge.mapper if cartridge is not None else None)`.
  `Bus` is unchanged.
- The PPU owns, in addition to its N4T3 state:
  - `v` (15-bit current VRAM address), `t` (15-bit temporary address), `x` (3-bit fine X),
    and the existing `w`. All four are public attributes, and all are zero at power-on.
  - Nametable RAM: `bytearray(0x1000)`, zeroed. Only the first 2 KB is addressed unless
    the mapper reports `FOUR_SCREEN` (R3).
  - Palette RAM: `bytearray(32)`, zeroed.
  - The `$2007` read buffer (private), zero at power-on.
- `_ppuaddr` and `_ppuaddr_latch` are removed. `v` is the single current-address state,
  with no parallel copy.
- The PPU never calls into `Bus` or the CPU. Its only outward dependency is the mapper.

### R2 — PPU address space: `read_vram(addr)` / `write_vram(addr, value)`

These are public production methods, used by `$2007` now and by the renderer later.
They take `addr &= 0x3FFF` and `value &= 0xFF`. They have no side effects beyond the
byte stored: no buffer update, no `v` increment, no I/O latch update.

| PPU range | Target |
|---|---|
| `$0000-$1FFF` | `mapper.ppu_read(addr)` / `mapper.ppu_write(addr, value)`; with no mapper, reads return 0 and writes are ignored |
| `$2000-$2FFF` | nametable RAM through mirroring (R3) |
| `$3000-$3EFF` | mirror of `$2000-$2EFF` (`addr - 0x1000`) |
| `$3F00-$3FFF` | palette RAM (R4) |

### R3 — Nametable mirroring

Let `n = (addr - 0x2000) & 0x0FFF`, where `table = n >> 10` (0–3) and `offset = n & 0x3FF`.
Read `mapper.mirroring` **on every access**, never caching it at construction, because
later mappers (MMC2) switch mirroring at runtime. The physical index is:

| Mode | `$2000` | `$2400` | `$2800` | `$2C00` | Physical index |
|---|---|---|---|---|---|
| `HORIZONTAL` | A | A | B | B | `(table >> 1) * 0x400 + offset` |
| `VERTICAL` | A | B | A | B | `(table & 1) * 0x400 + offset` |
| `FOUR_SCREEN` | A | B | C | D | `table * 0x400 + offset` |

With no mapper, use `HORIZONTAL`. Any other mirroring value raises `ValueError` naming
the value. No current mapper produces one, so this is a programming error, not a
runtime path.

### R4 — Palette RAM and mirroring

- Palette index: `i = addr & 0x1F`. If `i` is `0x10`, `0x14`, `0x18`, or `0x1C`, use
  `i & 0x0F`. This applies to reads **and** writes. `$3F20-$3FFF` mirrors `$3F00-$3F1F`.
- Writes store `value & 0x3F` (palette RAM is 6 bits wide).
- `read_vram` on palette space returns the stored 6-bit value. The CPU-visible `$2007`
  read (R6) adds the grayscale mask and the open-bus upper bits.

### R5 — Register writes (`write_register(reg, value)`)

Every write stores `value` in the I/O latch (existing `_data_latch` behavior). Bit
notation below is for the 15-bit `t`/`v`: `yyy NN YYYYY XXXXX`.

| Reg | Effect |
|---|---|
| `$2000` PPUCTRL | `ctrl = value`; `t = (t & ~0x0C00) \| ((value & 0x03) << 10)` |
| `$2001` PPUMASK | `mask = value` |
| `$2003`/`$2004` | unchanged from N4T3 |
| `$2005` PPUSCROLL, `w == 0` | `t = (t & ~0x001F) \| (value >> 3)`; `x = value & 0x07`; `w = 1` |
| `$2005` PPUSCROLL, `w == 1` | `t = (t & ~0x73E0) \| ((value & 0x07) << 12) \| ((value & 0xF8) << 2)`; `w = 0` |
| `$2006` PPUADDR, `w == 0` | `t = (t & 0x00FF) \| ((value & 0x3F) << 8)` (bit 14 cleared); `w = 1` |
| `$2006` PPUADDR, `w == 1` | `t = (t & 0x7F00) \| value`; `v = t`; `w = 0` |
| `$2007` PPUDATA | `write_vram(v & 0x3FFF, value)`, then increment `v` (R7) |

`$2005` and `$2006` share the single `w`. A `$2002` read resets it to 0 (R6).

### R6 — Register reads (`read_register(reg)`) and `peek_register(reg)`

- `$2002` PPUSTATUS: returns `vblank << 7 | sprite_zero_hit << 6 | sprite_overflow << 5 |
  (_data_latch & 0x1F)`. Side effects: `vblank = False`, `w = 0`, latch = returned value.
  `t`, `v`, and `x` are untouched.
- `$2004`: unchanged from N4T3.
- `$2007` PPUDATA, with `addr = v & 0x3FFF`:
  - `addr < 0x3F00`: return the **old** read buffer, then set buffer = `read_vram(addr)`.
  - `addr >= 0x3F00` (palette): return the palette byte immediately, as
    `(_data_latch & 0xC0) | (pal & (0x30 if mask & 0x01 else 0x3F))`. Set buffer =
    `read_vram(addr - 0x1000)`, which is the nametable byte "underneath" the palette.
  - Then increment `v` (R7) and set latch = returned value.
- Write-only registers (`$2000`, `$2001`, `$2003`, `$2005`, `$2006`) return the latch
  (unchanged).
- `peek_register(reg)` returns exactly what `read_register(reg)` would return, with
  **no** state change: no vblank/`w` clear, no buffer refill, no `v` increment, no latch
  update. For `$2007` that is the current buffer (non-palette) or the masked palette
  value (palette). This keeps the N4T3 debug-trace purity guarantee.

### R7 — `v` increment on `$2007` access

`v = (v + (32 if ctrl & 0x04 else 1)) & 0x7FFF`. Memory accesses always use
`v & 0x3FFF`. This ticket always uses the plain increment, even while rendering is
enabled. The rendering-time coarse-X/Y glitch belongs to the renderer ticket.

### R8 — Frame timing, status clears, NMI

- The dot/scanline/frame counters stay as in N4T3: dots 0–340, scanlines 0–261, where
  261 is pre-render.
- **Vblank set:** on the `step()` that reaches scanline 241, dot 1, set `vblank = True`.
- **Pre-render clear:** on the `step()` that reaches scanline 261, dot 1, clear `vblank`,
  `sprite_zero_hit`, and `sprite_overflow`.
- **`$2002` clear:** R6.
- **Odd-frame skip:** when `mask & 0x18` is nonzero (rendering enabled) and `frame` is
  odd, the `step()` from scanline 261 dot 339 goes directly to scanline 0 dot 0 and
  increments `frame`, so that frame is 89,341 dots instead of 89,342. Evaluate the
  rendering-enabled check at that dot.
- **NMI output:** `nmi_line` stays a read-only property equal to
  `vblank and bool(ctrl & 0x80)`. Its consequences are part of the contract, and the CPU's
  existing rising-edge latch turns them into NMIs:
  - With PPUCTRL bit 7 set, vblank start raises the line. That gives exactly one NMI per
    frame.
  - Setting bit 7 (0→1) while `vblank` is still set raises the line, so an NMI happens
    mid-vblank. Clearing and re-setting bit 7 during vblank produces another one.
  - A `$2002` read during vblank lowers the line. No new NMI occurs until the next vblank.
- `step()` never raises, including with rendering enabled in PPUMASK and with no mapper.

### R9 — Existing test migration (test agent)

`test_ppu_status_read_resets_write_toggle_for_ppuaddr` must assert `ppu.v == 0x1234`
instead of `ppu._ppuaddr`. Nothing else in the existing suite depends on removed state.

## Design Decisions

- **The PPU owns CIRAM, palette, and v/t/x/w, and the mapper owns CHR and mirroring.**
  This is one owner per region, matching N4T3's ownership table. Mirroring is read live
  from the mapper, so MMC2 (Punch-Out) needs no PPU change to switch it.
- **The mapper is injected into the PPU constructor with an optional default.** This is a
  real production seam: `Console` passes the cartridge's mapper. Standalone PPU tests use
  `PPU()` or a real `NROM` built from a synthetic header, so no mocks of PPU internals
  are needed.
- **`read_vram`/`write_vram` are public.** The renderer ticket needs side-effect-free PPU
  bus access for fetches, so these are not test-only hooks. Tests use them to arrange and
  observe VRAM directly without driving `$2006/$2007`.
- **The four-screen extra 2 KB lives in the PPU's buffer.** On real hardware it sits on
  the cartridge. Allocating 4 KB in the PPU keeps a single nametable owner until a mapper
  actually supplies its own VRAM. That mapper ticket should move ownership, not duplicate
  it.
- **The odd-frame skip is included, even though N4T3 listed it as a non-goal.** It is
  frame timing, which is this ticket's scope, and it is observable to timing-sensitive
  games. It only triggers with rendering enabled, so nestest and existing tests are
  unaffected.
- **The `$2002`/vblank race and the warm-up window are excluded.** `Console` runs a whole
  CPU instruction before catching the PPU up, so register accesses are not dot-accurate.
  Specifying a one-dot race would promise accuracy the scheduler cannot deliver.
  Revisit if the scheduler becomes per-cycle.
- **Governing decisions:** neither the `emulator-core` nor the `tests` LEAF doc carries a
  "Governing decision:" line. The design is consistent with `docs/code/patterns.md`
  ("Keep PPU/APU behind narrow methods"; "Mapper protocol … ppu_read/write plus
  mirroring") and with the N4T3 spec's R3 surface, which this spec extends and does not
  replace.

## Subsystem Impact

- **Affected subsystems:** `emulator-core` (edits `src/ppu.py` and `src/console.py`, and
  the mapper wiring only) and `tests` (new `src/tests/test_ppu.py`, plus the one
  assertion migration in `test_console.py`).
- **Boundary crossings:** `ppu → mapper` is intra-subsystem (both are `emulator-core`).
  `tests → emulator-core` already exists. There are no new edges.
- **New subsystems:** none.
- **Catalog impact (same PR as the code):** `docs/architecture/overview.md` Source File
  Catalog adds `src/tests/test_ppu.py` under tests. `sub-systems/tests.md` Anchor Files
  adds `test_ppu.py`. In `sub-systems/emulator-core.md`, change the `src/ppu.py` anchor
  description to "PPU registers, VRAM/palette, scroll latches, frame timing, NMI
  (rendering is later tickets)". Remove its Failure Modes line about `ppu.py` syntax
  errors, or reword it so it no longer claims that failure is current.

## Test Expectations (acceptance only — test agent owns test code)

No renderer is needed. Use `PPU()` or `PPU(NROM(...))` with a synthetic header and CHR
RAM (`chr_rom_banks == 0`) or CHR ROM. Commit no `.nes` file.

- **Vblank timing:** from power-on, after `241*341` steps `vblank` is False and
  `peek_register(2) & 0x80 == 0`. After one more step it is True. Vblank stays set
  through scanline 260. At (261, 1), vblank, sprite 0 hit, and overflow (preset True)
  are all clear.
- **`$2002` read:** returns bit 7 set once and clears `vblank`. A second read returns
  bit 7 clear. The read resets `w`, and the low 5 bits come from the last written value.
- **NMI:** with `ctrl = 0x80`, `nmi_line` rises exactly at vblank start. With bit 7
  clear it never rises. Writing `$2000 = 0x80` during vblank raises it. A `$2002` read
  lowers it. Through `Console` with synthetic vectors, one NMI per frame (existing tests
  keep passing).
- **Odd-frame skip:** with `mask = 0x08`, an even frame takes 89,342 steps and the next
  (odd) frame takes 89,341. With `mask = 0`, both take 89,342.
- **Scroll registers:** run the sequence `$2000 = 0x00`, a `$2002` read,
  `$2005 = 0x7D`, `$2005 = 0x5E`, `$2006 = 0x3D`, and `$2006 = 0xF0`. The
  `t`/`x`/`v`/`w` values must match the nesdev "PPU scrolling" worked example at each
  step. That covers the `t` bits, `x = 5`, the `v = t` copy, and `w` toggling.
  Separately, `$2000 = 0x03` sets `t` bits 10–11 without touching other `t` bits.
- **Shared `w`:** one `$2005` write followed by one `$2006` write counts as the second
  write of the pair. After a `$2002` read, the next `$2006` write is again a first write.
- **`$2006` high byte:** writing `0xFF` stores `0x3F` in bits 8–13 and clears bit 14.
- **PPUDATA write/read:** `$2006 = $21, $08`, then `$2007` writes `A`, `B`. Reset `v`
  and read `$2007` three times. The results are `stale-buffer`, `A`, `B`.
  `ctrl` bit 2 gives a +32 stride. `v` wraps at `0x7FFF`, and access uses `& 0x3FFF`.
- **Palette read bypass:** with `$3F00` set to `0x2C` and the nametable byte at `$2F00`
  set to `0x77`, a `$2007` read at `$3F00` returns `0x2C` immediately (upper two bits
  from the latch). The next non-palette read returns buffer `0x77`. With `mask & 1`,
  the palette read returns `0x2C & 0x30`.
- **Palette mirroring:** a write at `$3F10` is read back at `$3F00` and vice versa, and
  likewise for `$14/$04`, `$18/$08`, and `$1C/$0C`. `$3F05` and `$3F15` are distinct.
  `$3F25` aliases `$3F05`. Writes are stored `& 0x3F`.
- **Nametable mirroring:** for each of `HORIZONTAL`, `VERTICAL`, and `FOUR_SCREEN` (and
  no mapper, which uses horizontal), writes at `$2000/$2400/$2800/$2C00 + k` alias per
  R3. `$3000-$3EFF` aliases `$2000-$2EFF`.
- **Pattern tables:** with an NROM CHR-RAM mapper, `$2007` writes at `$0000-$1FFF` land
  in the mapper (`mapper.ppu_read` sees them). With CHR ROM, writes are ignored. With no
  mapper, reads return 0 and nothing raises.
- **Peek purity:** `peek_register(7)` and `peek_register(2)` change none of `v`, the
  buffer, `vblank`, `w`, or the latch.
- **Console wiring:** `Console(cartridge).ppu` reads CHR through that cartridge's mapper.

## Verification

From `src/`: `python3 -m compileall -q . && python3 -m unittest discover -s tests -v`.
Pass: compileall exits 0, and the run reports **0 failures and 0 errors**, with more
than 142 tests including the new `test_ppu.py`. `ROMTests.testROM` (nestest) still
matches 5000 lines.

## Plain-English Hand-off

**What this spec does:** The graphics chip gets its own memory for the screen layout and
colors, and it reads tile graphics from the cartridge. It now correctly handles the
registers games use to set scroll position, write graphics data, and wait for the start
of each frame. It signals the processor at the start of each frame when the game asks
for that.

**Tradeoffs:**
- Still nothing is drawn. This ticket makes the graphics chip's memory and timing correct
  so the drawing ticket can build on it.
- Scroll values are stored correctly, but the mid-frame scroll updates that happen while
  drawing are left to the drawing ticket. Split-screen effects will not work until then.
- The chip now skips one step every other frame while drawing is enabled, as real
  hardware does. N4T3 deliberately left this out. Adding it here is on purpose. It only
  applies once a game turns drawing on, so current tests are unaffected.
- A few exact-timing quirks are deliberately not emulated: reading the status register on
  the exact moment a frame starts, and ignoring writes right after power-on. The emulator
  runs a whole processor instruction at a time, so it cannot honor them precisely. Most
  games do not depend on them.
- One existing test checked a hidden internal field that is now replaced by the
  documented address register. That test is updated to check the documented field.
- Four-screen cartridges' extra screen memory is kept inside the graphics chip for now,
  instead of on the cartridge where it lives physically. The result is the same. A later
  mapper that needs it on the cartridge will move it.

## Changelog

### Version 1.0 - 2026-09-29
**Source Issue:** N4T4
**Change Type:** Major

**Changes:**
- Initial specification: mapper-injected PPU, nametable RAM with live mirroring, palette
  RAM with nesdev mirroring, `read_vram`/`write_vram`, loopy `v`/`t`/`x`/`w` register
  semantics, buffered `$2007` reads with the palette bypass, vblank/pre-render timing,
  odd-frame skip, NMI line contract, and `Console` wiring.
- Corrects the ticket's stale premise: `ppu.py` already compiles (N4T3).

**Impact:** Requires code changes in `emulator-core` (`ppu.py`, `console.py`) and tests
(`test_ppu.py`, one assertion in `test_console.py`).

---
