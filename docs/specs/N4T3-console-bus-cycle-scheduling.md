<!-- GITHUB ISSUE TRACKING METADATA -->
<!-- Issue Key: N4T3 -->
<!-- Last Updated: 2026-09-29T15:20:00-05:00 -->
<!-- Description Hash: n/a (factory ticket) -->
<!-- Spec Version: 1.0 -->
<!-- END METADATA -->

# N4T3 — Console bus + cycle scheduling

## Reviewer's Guide

- **Problem:** `cpu.CPU` owns a flat 64 KB `memory.Memory` and copies PRG into it once at
  construction (`Memory.loadROM`). Nothing routes `$2000-$2007` to the PPU, `$4014` does
  nothing, there are no controllers or APU registers, and nothing clocks the PPU. `ppu.py`
  does not even compile (`def __init__(self, nes)` has no colon; `if self.cycle >= 340`
  likewise), so `compileall` fails today.
- **Change:** a `Bus` that owns the CPU address map, a `Console` that wires CPU/PPU/APU
  stub/controllers/cartridge together and schedules 3 PPU dots per CPU cycle, NMI/IRQ
  input lines on the CPU, and a PPU that compiles and implements just enough registers
  (CTRL, STATUS, OAMADDR, OAMDATA, OAM DMA target, vblank timing) to drive NMI.
- **Non-goals:** background/sprite rendering, PPU VRAM/nametable mirroring through
  `$2006/$2007` beyond what exists, APU sound, mapper IRQs, MMC2, odd-frame dot skip,
  fixing the CPU's pre-existing cycle-count inconsistencies or the 22 pre-existing CPU
  test failures, the cwd-relative `log.txt` the CPU opens.

References: [nesdev CPU memory map](https://www.nesdev.org/wiki/CPU_memory_map),
[PPU registers](https://www.nesdev.org/wiki/PPU_registers),
[OAM DMA](https://www.nesdev.org/wiki/PPU_registers#OAMDMA),
[Standard controller](https://www.nesdev.org/wiki/Standard_controller),
[NMI](https://www.nesdev.org/wiki/NMI), [PPU frame timing](https://www.nesdev.org/wiki/PPU_frame_timing).

## Current State (verified 2026-09-29 at `3accc50`)

- `CPU.__init__(self, cartridge=None)` builds `memory.Memory(0x10000)` and, if given a
  cartridge, calls `Memory.loadROM` (copies `mapper.cpu_read($8000-$FFFF)`).
- All CPU memory traffic goes through `cpu.memory.read/write/read16` from `cpu.py`
  (stack, `fetch`, `brk`, `logOperation`) and `addressing.py` (every mode). `write16` is
  used only by tests. `Memory.read16($00FF)` wraps the high byte to `$0000`.
- Some addressing modes compute addresses above `$FFFF` without masking
  (`AbsoluteX.read/write`, `AbsoluteY.write`); flat memory tolerates this only when the
  sum stays under `0x10000`.
- `cpu.cycles` is counted in **PPU dots**: `execute` adds `cycles * 3`; branch and most
  page-cross penalties add `3 * n`. (`adc`/`_and` add an unscaled page-cross cycle —
  pre-existing, out of scope.) `logOperation` prints `cycles % 341` as `CYC`.
- `ppu.py` fails `compileall`; `PPU.__init__` dereferences `self.nes` before assigning it.
- Test baseline from `src/`: `python3 -m unittest discover -s tests` → 99 run,
  **22 failures** (9 in `AddressingModeTests`: implied/indirect/indirect_x/indirect_y/
  relative; 13 in `InstructionTests`: branch ×3, clc/cld/cli/clv/sec/sed/sei, jsr, plp, rti).
- nestest baseline: `CPU(ROM(nestest))`, `PC=$C000`, 5000 `fetch()` calls complete with no
  exception and the first 5000 log lines match `nestest.log.txt` on both the PC column
  and the `CYC` field. (`ROMTests.testROM` prints instead of asserting, so it reports OK
  regardless.)
- `AddressingModeTests` / `InstructionTests` use scratch addresses anywhere in 64 KB
  (`$1000`, `$2000`, `$3000`, `$FFFE`, …). On a real NES map those are RAM mirrors, PPU
  registers, and cartridge ROM, so these tests cannot run unchanged against `Bus`.

## Requirements

### R1 — CPU memory is an injected bus

- `CPU.__init__(self, bus)` takes the object it reads and writes through and stores it as
  `self.bus`. `CPU` constructs no memory of its own and no longer accepts a cartridge.
- The **bus protocol** is: `read(addr) -> int`, `write(addr, value) -> None`,
  `read16(addr) -> int`, `write16(addr, value) -> None`. Both `bus.Bus` (R2) and
  `memory.Memory` satisfy it.
- Every CPU/addressing-mode access that goes through `cpu.memory` today goes through
  `cpu.bus` instead. The attribute `memory` is removed from `CPU` (one name, one path).
- `Memory.loadROM` is deleted; cartridge bytes are served live by the mapper through
  `Bus` (R2), never copied.
- `memory.Memory` stays as a plain flat byte store. It is a valid bus for CPU-only
  harnesses (instruction-semantics unit tests, standalone 6502 test programs); it is not
  used by `Console`.

### R2 — `Bus` owns the CPU address map (new module `src/bus.py`)

`bus.Bus(ppu, apu, controllers, cartridge=None)` where `controllers` is a 2-sequence and
`cartridge` is a `rom.ROM` (or `None`). `Bus` owns the 2 KB internal RAM (`bytearray(0x800)`,
zeroed); it owns no other state except the pending DMA stall (R4) and the last value
driven on the data bus (open bus, see below).

Every `read`/`write` first masks `addr &= 0xFFFF` and writes mask `value &= 0xFF`.

| CPU range | Read | Write |
|---|---|---|
| `$0000-$1FFF` | `ram[addr & 0x7FF]` | `ram[addr & 0x7FF] = value` |
| `$2000-$3FFF` | `ppu.read_register(addr & 0x7)` | `ppu.write_register(addr & 0x7, value)` |
| `$4014` | open bus | OAM DMA (R4) |
| `$4016` | `controllers[0].read()` | strobe: `controllers[0].write(value)` and `controllers[1].write(value)` |
| `$4017` | `controllers[1].read()` | `apu.write_register(addr, value)` (frame counter) |
| `$4000-$4013`, `$4015` | `apu.read_register(addr)` | `apu.write_register(addr, value)` |
| `$4018-$401F` | open bus | ignored |
| `$4020-$FFFF` | `cartridge.mapper.cpu_read(addr)`; open bus if no cartridge | `cartridge.mapper.cpu_write(addr, value)`; ignored if no cartridge |

- **Open bus:** `Bus` remembers the last byte read or written; unmapped reads return it.
  Controller reads return `(open_bus & 0xE0) | bit` (bit 0 = serial data).
- `read16(addr)` = `read(addr) | read(next) << 8` where `next = 0x0000` when `addr == 0x00FF`
  (preserves `Memory.read16`'s zero-page wrap, which `IndirectY` and others rely on),
  else `(addr + 1) & 0xFFFF`. `write16` writes low then high byte at `addr`, `(addr+1) & 0xFFFF`.
- `Bus` performs no side effects on construction and does no I/O.

### R3 — PPU compiles and exposes a narrow register/timing surface

`ppu.PPU()` takes no constructor arguments and must pass `compileall`. It owns: register
latches, `oam` (`bytearray(256)`), the `w` write toggle, `scanline`/`dot` counters, a
frame counter, the vblank flag, and its NMI output. Required surface:

- `read_register(reg: int) -> int` / `write_register(reg: int, value: int) -> None`,
  `reg` in `0..7` (`$2000+reg`).
  - `$2000` PPUCTRL write: store; bit 7 = NMI enable.
  - `$2001` PPUMASK write: store.
  - `$2002` PPUSTATUS read: returns `vblank << 7` in bit 7 (plus sprite-0/overflow bits,
    currently 0) with low 5 bits from the PPU's internal data latch; **clears vblank and
    resets `w`**.
  - `$2003` OAMADDR write: store. `$2004` OAMDATA read: `oam[oamaddr]`; write:
    `oam[oamaddr] = value; oamaddr = (oamaddr + 1) & 0xFF`.
  - `$2005`/`$2006` writes toggle `w` (existing PPUADDR latch logic may stay);
    `$2007` read/write may remain stubbed but must not raise.
  - Every register write updates the internal data latch; write-only register reads
    return that latch.
- `write_oam_dma(page: bytes)` (length 256): copies into `oam` starting at `oamaddr`,
  wrapping (`oam[(oamaddr + i) & 0xFF] = page[i]`), matching hardware's 256 `$2004` writes.
  `oamaddr` ends unchanged.
- `step()` advances one dot: `dot` 0..340, `scanline` 0..261 (261 = pre-render), then wraps
  to scanline 0 and increments the frame counter. At scanline 241 dot 1 set vblank; at
  scanline 261 dot 1 clear vblank (and sprite flags). **`step()` never raises**; rendering
  fetch helpers are no-ops in this ticket even when PPUMASK enables rendering.
- `nmi_line` (read-only property): `vblank and ctrl.bit7`. Enabling bit 7 while vblank is
  set therefore raises the line immediately (hardware behavior).
- PPU holds no reference to the CPU, the bus, or `Console`.

### R4 — OAM DMA via `$4014`

- A write of `N` to `$4014` builds a 256-byte page by `Bus.read((N << 8) | i)` for
  `i = 0..255` (full bus, so RAM, mirrors, and cartridge pages all work) and calls
  `ppu.write_oam_dma(page)`.
- The copy is completed synchronously inside the write. `Bus` then records
  `dma_stall_cycles = 513` for the scheduler (R5); the scheduler adds 1 when the CPU cycle
  count at the time of the stall is odd, for 513 or 514 total.

### R5 — `Console` wires and schedules (new module `src/console.py`)

`console.Console(cartridge=None)` constructs, in this order: `PPU()`, `APU()`,
two `Controller()`s, `Bus(ppu, apu, controllers, cartridge)`, `CPU(bus)`. They are exposed as
`console.cpu`, `console.ppu`, `console.apu`, `console.bus`, `console.controllers`.
`Console` owns no emulated state beyond these references; it is the only place the
components are wired.

- `reset()`: `cpu.PC = bus.read16(0xFFFC)`, `cpu.I = 1`. (Callers may overwrite `PC`
  afterward, as the nestest harness sets `$C000`.)
- `step() -> int`: advances exactly one CPU "unit of work" and returns the **CPU cycles**
  it consumed:
  1. If `bus.dma_stall_cycles` is non-zero: consume it (plus the odd-cycle extra), clear it.
  2. Else if the CPU has a pending NMI or an unmasked IRQ (R6): service it (7 CPU cycles).
  3. Else: `cpu.fetch()`.
  4. Let `dots = cpu.cycles_after - cpu.cycles_before` (for step 1, the scheduler adds
     `3 × stall` to `cpu.cycles` itself so the unit stays PPU dots). Call `ppu.step()`
     exactly `dots` times. Return `dots // 3`.
  5. Sample interrupt lines: `cpu.set_nmi_line(ppu.nmi_line)`,
     `cpu.set_irq_line(apu.irq_line)`.
- `cpu.cycles` stays measured in PPU dots, so the nestest `CYC` trace column is unchanged.
  The PPU advances 3 dots per CPU cycle as accounted by the CPU; correcting
  the CPU's pre-existing mis-scaled penalties is out of scope.
- `run_frame()`: calls `step()` until `ppu`'s frame counter increments. It is a
  convenience for later frontend tickets and must terminate for a CPU spinning in a loop.

### R6 — Interrupt lines on the CPU

- `CPU.set_nmi_line(level: bool)`: edge-detected; a low→high transition latches
  `nmi_pending`. Holding the line high does not re-trigger.
- `CPU.set_irq_line(level: bool)`: level-sensitive; stored as `irq_line`.
- `CPU.service_interrupts() -> bool` (called by `Console.step` step 2): if `nmi_pending`,
  clear it and vector through `$FFFA`; else if `irq_line and not I`, vector through `$FFFE`.
  Vectoring = push PCH, PCL, then status with bit 5 set and B clear; set `I = 1`;
  `PC = bus.read16(vector)`; `cycles += 7 * 3`. Returns whether it serviced one.
- `brk` behavior is unchanged in this ticket.

### R7 — Controllers and APU stub (new modules `src/controller.py`, `src/apu.py`)

- `controller.Controller`: `buttons` (8-bit int, bit order A, B, Select, Start, Up, Down,
  Left, Right from bit 0), set by the frontend. `write(value)`: strobe = `value & 1`; while
  strobe is high the shift register reloads from `buttons`. `read()`: returns bit 0 of the
  shift register (A while strobed), then shifts; after 8 reads returns 1.
- `apu.APU`: `read_register(addr)` returns 0 for `$4015` (and open-bus-free 0 for others);
  `write_register(addr, value)` stores the value in a 32-byte register file without side
  effects; `irq_line` property is always `False`. It must not raise for any `$4000-$4017`.

### R8 — Call-site wiring and existing tests

- `test_rom`'s NROM-128 check moves from `CPU(cartridge).memory.read(...)` to
  `Console(cartridge).bus.read(0x8000/0xC000)` (same expected values).
- `ROMTests.testROM` runs nestest through `Console(ROM(path))` (i.e. through `Bus`), sets
  `console.cpu.PC = 0xC000`, and loops `console.step()`. It must **assert** (not print) that
  5000 instructions execute without exception and the first 5000 log lines match
  `nestest.log.txt` on PC and `CYC`, which is the current baseline.
- `AddressingModeTests` / `InstructionTests` construct `CPU(memory.Memory(0x10000))` and
  switch `cpu.memory` → `cpu.bus`. Test logic is otherwise unchanged, and the pass/fail
  set must equal the 22-failure baseline.

## Design Decisions

- **One state owner per region:** RAM → `Bus`; OAM, vblank, and PPU latches → `PPU`;
  PRG/CHR → mapper; button state → `Controller`; interrupt latch → `CPU`. `Console` only
  wires and sequences. Nothing copies cartridge bytes (removes N4T2's flat-copy stopgap).
- **Register-level PPU seam (`read_register`/`write_register(reg)` + `write_oam_dma`)**
  per `docs/code/patterns.md` "Keep PPU/APU behind narrow methods". The PPU never calls
  back into the bus, so it is testable standalone.
- **DMA copies synchronously, stall accounted by the scheduler:** keeps `Bus` free of
  clocking. Real DMA interleaves with PPU dots, but no observable difference exists
  until sprite rendering lands.
- **Keep `cpu.cycles` in PPU dots:** changing units would rewrite every timing test and the
  nestest `CYC` comparison. The scheduler reads the delta instead.
- **Flat `Memory` for instruction-semantics tests.** These tests check opcode behavior,
  not the NES memory map. Moving their fixtures to real NES addresses would rewrite most
  of `test_cpu.py`, and `$FFFE`-vector tests would need a writable cartridge. Injecting
  a flat bus is a real production configuration (a CPU-only harness), not a test-only
  branch. The acceptance criterion "existing CPU unit tests still pass with a bus-backed
  memory" is therefore met this way: every CPU access goes through an injected bus, and
  nestest runs through the real `Bus`.
- **Governing decisions:** neither the `emulator-core` nor the `tests` LEAF doc has a
  "Governing decision:" line. The design is consistent with emulator-core's Public
  Contract ("Callers construct a CPU with injected memory/ROM") and with
  `docs/code/patterns.md` "Bus as the memory map".

## Subsystem Impact

- **Affected subsystems:** `emulator-core` (new `bus.py`, `console.py`, `controller.py`,
  `apu.py`; edits to `cpu.py`, `addressing.py`, `memory.py`, `ppu.py`); `tests` (new
  `test_bus.py`/`test_console.py` or equivalent; `test_cpu.py` and `test_rom.py` wiring).
- **Boundary crossings:** only `tests → emulator-core`, which already exists. No new edges.
- **New subsystems:** none. Bus/console/controller/APU stay in `emulator-core`, as its
  Purpose already anticipates ("a clocked PPU/APU/bus").
- **Catalog impact (same PR as the code):** `docs/architecture/overview.md` Source File
  Catalog adds `src/bus.py`, `src/console.py`, `src/controller.py`, `src/apu.py` under
  emulator-core and the new test module(s) under tests. The catalog is already stale:
  `src/mapper.py`, `src/tests/test_rom.py`, and `src/log.txt` from N4T2 are missing,
  and it lists `src/nestest.log.txt` under core. Fix both in that PR.
  `sub-systems/emulator-core.md` Anchor Files gains the four modules, and `memory.py`'s
  description becomes "flat byte store / CPU-only bus".

## Test Expectations (acceptance only — test agent owns test code)

Tests must use a synthetic NROM cartridge (built via `rom.ROM` on a temp file or via
`mapper.NROM` directly) or no cartridge. No new `.nes` file is committed.

- RAM: write `$0000-$07FF`, read back at `+$0800/+$1000/+$1800`, and the reverse.
- PPU dispatch: writes to `$2000` and `$3FF8` both reach PPUCTRL (mirror every 8).
  Reading `$2002` returns bit 7 set after vblank begins, then clear on the second read.
  `$2003`/`$2004` write sequence fills OAM with auto-increment.
- OAM DMA: fill RAM `$0200-$02FF` with a pattern, set OAMADDR, write `$02` to `$4014`.
  OAM equals the pattern rotated by OAMADDR; `dma_stall_cycles == 513` before the next
  `step()`; that step returns 513 or 514 and advances the PPU by 3× that.
  A DMA from a cartridge page (`$80`) also works.
- Scheduling: after `Console.step()` over a known opcode (e.g. NOP `$EA`, 2 CPU cycles),
  the PPU has advanced exactly 6 dots. Over N steps, total PPU dots == 3 × Σ returned
  cycles. Vblank begins after 241×341+1 dots from power-on.
- NMI: with PPUCTRL bit 7 set and a synthetic vector at `$FFFA`, running until vblank
  services the NMI exactly once per frame (PC lands on the vector target, stack has
  PC/P, `I == 1`). With bit 7 clear, no NMI. IRQ: a line held high with `I == 1` is ignored;
  with `I == 0` it vectors through `$FFFE`.
- Controllers: strobe 1→0, then 8 reads of `$4016` return the `buttons` bits in A…Right
  order, then 1s. `$4017` reads controller 2.
- APU stub: writes to every `$4000-$4013`, `$4015`, `$4017` do not raise. `$4015` reads 0.
- Cartridge: `$8000` and `$C000` reads come from the mapper live (NROM-128 mirror). With no
  cartridge, reads do not raise.
- `python3 -m compileall -q .` succeeds from `src/` (now includes `ppu.py`).

## Verification

From `src/`: `python3 -m compileall -q . && python3 -m unittest discover -s tests -v`.
Pass criterion: compileall exits 0. The 77 previously passing tests still pass, with
`ROMTests.testROM` now asserting its 5000-line match through `Console`/`Bus`. New
bus/console tests pass. The failure set is exactly the 22 pre-existing failures listed in
Current State.

## Plain-English Hand-off

**What this spec does:** The emulated console gets real wiring. The processor now talks
to memory, the graphics chip, the sound chip (placeholder), the two controllers, and the
cartridge the way a real NES does. The graphics chip is clocked three steps for every
processor step, so it can signal the start of each video frame back to the processor.

**Tradeoffs:**
- Nothing is drawn on screen yet. The graphics chip only keeps time and reports "frame
  started". Pictures come in a later ticket.
- Sound registers accept writes and do nothing. Games that wait on sound-chip interrupts
  will not see one yet.
- The existing processor instruction tests keep running against a simple flat 64 KB
  memory, not the full NES wiring. Only the nestest program run goes through the real
  wiring. This avoids rewriting most of the test file, but means those tests do not
  exercise the NES address layout.
- The processor's existing timing quirks (a few instructions count page-crossing
  penalties at the wrong scale) are kept as-is, so graphics timing inherits them.
  nestest timing still matches for the first 5000 instructions.
- The one-time copy of cartridge data into memory is removed. Cartridge bytes are now
  read live from the cartridge. This is what makes bank-switching cartridges (Punch-Out)
  possible later.
- Sprite-memory copies (DMA) happen instantly with the time cost added afterward. This
  has no visible effect until sprites are drawn.

## Changelog

### Version 1.0 - 2026-09-29
**Source Issue:** N4T3
**Change Type:** Major

**Changes:**
- Initial specification: injected CPU bus, `Bus` memory map with RAM mirrors, PPU register
  dispatch, OAM DMA, controllers, APU stub, cartridge passthrough, `Console` scheduler at
  3 PPU dots per CPU cycle, NMI/IRQ lines, compiling PPU with vblank timing.

**Impact:** Requires code changes in `emulator-core` and test changes in `tests`.

---
