<!-- GITHUB ISSUE TRACKING METADATA -->
<!-- Issue Key: N4T3 -->
<!-- Last Updated: 2026-09-29T16:40:00-05:00 -->
<!-- Description Hash: n/a (factory ticket) -->
<!-- Spec Version: 1.1 -->
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
  `cpu.cycles` is re-based from PPU dots to **CPU cycles** (R5), the bus protocol gains
  side-effect-free `peek`/`peek16` for the debug trace (R1), and `CPU` unit tests move
  onto the real `Bus` with their incorrect assertions corrected (R8).
- **Non-goals:** background/sprite rendering, PPU VRAM/nametable mirroring through
  `$2006/$2007` beyond what exists, APU sound, mapper IRQs, MMC2, odd-frame dot skip,
  the cwd-relative `log.txt` the CPU opens, `BRK`'s pushed-status B bit (unchanged).

References: [nesdev CPU memory map](https://www.nesdev.org/wiki/CPU_memory_map),
[PPU registers](https://www.nesdev.org/wiki/PPU_registers),
[OAM DMA](https://www.nesdev.org/wiki/PPU_registers#OAMDMA),
[Standard controller](https://www.nesdev.org/wiki/Standard_controller),
[NMI](https://www.nesdev.org/wiki/NMI), [PPU frame timing](https://www.nesdev.org/wiki/PPU_frame_timing).

## Current State

### Implemented (verified 2026-09-29 at `40ae131`)

- `src/bus.py`, `src/console.py`, `src/controller.py`, `src/apu.py` exist and satisfy
  R1–R8 as amended in v1.1. `Memory.loadROM` is gone; `CPU(bus)` has no `memory`
  attribute.
- `cpu.cycles` counts **CPU cycles** everywhere: `execute` adds the table value, branch
  and page-cross penalties add `1`/`crossPageCycles` unscaled, `service_interrupts` adds
  `7`. `logOperation` prints `(cycles * 3) % 341` as `CYC`.
- From `src/`: `python3 -m compileall -q . && python3 -m unittest discover -s tests` →
  135 run, **0 failures**. `ROMTests.testROM` asserts the 5000-line nestest match.

### Pre-ticket baseline (verified 2026-09-29 at `3accc50`, historical)

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
- Root cause of most of the 22 failures: the tests assert CPU-cycle deltas (e.g. a taken
  branch is `+3`) while `cpu.cycles` was in PPU dots; the rest assert values that
  contradict 6502 semantics (see R8).

## Requirements

### R1 — CPU memory is an injected bus

- `CPU.__init__(self, bus)` takes the object it reads and writes through and stores it as
  `self.bus`. `CPU` constructs no memory of its own and no longer accepts a cartridge.
- The **bus protocol** is six methods, all required:
  `read(addr) -> int`, `write(addr, value) -> None`, `read16(addr) -> int`,
  `write16(addr, value) -> None`, `peek(addr) -> int`, `peek16(addr) -> int`.
  `bus.Bus` (R2) satisfies it. Any future bus must implement all six:
  `CPU.peek`/`CPU.peek16` call `bus.peek`/`bus.peek16` unconditionally, and
  `CPU()` defaults to `debug = True`, so a bus without `peek` raises `AttributeError`
  on the first traced instruction.
- `peek`/`peek16` return the byte(s) `read`/`read16` would return **without any side
  effect**: no PPUSTATUS vblank/`w` clear, no controller shift, no open-bus update, no
  mapper state change. `peek16` uses the same `$00FF → $0000` wrap as `read16`.
- Every CPU/addressing-mode access that goes through `cpu.memory` today goes through
  `cpu.bus` instead. The attribute `memory` is removed from `CPU` (one name, one path).
- Execution paths (`fetch`, operand fetch, stack) use `read`/`write`. Trace-only paths
  (`logOperation` and every `AddressingMode.format`) use only `cpu.peek`/`cpu.peek16`,
  so enabling the trace never changes emulated state.
- `Memory.loadROM` is deleted; cartridge bytes are served live by the mapper through
  `Bus` (R2), never copied.
- The obsolete flat `memory.Memory` store is deleted. CPU execution uses the NES
  `Bus`; standalone CPU tests use the same production bus path (R8).

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
- `peek` follows the same table but routes `$2000-$3FFF` to `ppu.peek_register(reg)`,
  `$4016/$4017` to `controllers[n].peek()`, and leaves the open-bus latch untouched.
  `$4000-$4015` APU reads and cartridge reads are already side-effect-free and are shared.
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
- `peek_register(reg: int) -> int`: the value `read_register(reg)` would return, with no
  state change (vblank, `w`, and the data latch are untouched).
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
  `dma_stall_cycles = 513` (CPU cycles) for the scheduler (R5); the scheduler adds 1 when
  `cpu.cycles` (a CPU-cycle count, R5) is odd at the time the stall is consumed, for 513
  or 514 total.

### R5 — `Console` wires and schedules (new module `src/console.py`)

`console.Console(cartridge=None)` constructs, in this order: `PPU()`, `APU()`,
two `Controller()`s, `Bus(ppu, apu, controllers, cartridge)`, `CPU(bus)`. They are exposed as
`console.cpu`, `console.ppu`, `console.apu`, `console.bus`, `console.controllers`.
`Console` owns no emulated state beyond these references; it is the only place the
components are wired.

- `reset()`: `cpu.PC = bus.read16(0xFFFC)`, `cpu.I = 1`. (Callers may overwrite `PC`
  afterward, as the nestest harness sets `$C000`.)
- **Unit:** `cpu.cycles` is measured in **CPU cycles** (not PPU dots). Every increment
  is unscaled: `execute` adds the opcode table's cycle count, taken branches add `1`
  (or `crossPageCycles` = `2` on a page cross), page-crossing reads add
  `getCrossPageCycles` (`0`/`1`), `service_interrupts` adds `7`, and the scheduler adds
  the DMA stall. Nothing in the CPU multiplies by 3. Consumers that need PPU time
  multiply by 3 themselves; the trace's `CYC` column is `(cpu.cycles * 3) % 341`.
- `step() -> int`: advances exactly one CPU "unit of work" and returns the **CPU cycles**
  it consumed:
  1. Record `before = cpu.cycles`.
  2. If `bus.dma_stall_cycles` is non-zero: `stall = dma_stall_cycles + (before & 1)`,
     clear `dma_stall_cycles`, `cpu.cycles += stall`.
  3. Else if `cpu.service_interrupts()` returns `True` (R6): done (7 CPU cycles).
  4. Else: `cpu.fetch()`.
  5. `elapsed = cpu.cycles - before`. Call `ppu.step()` exactly `3 × elapsed` times.
  6. Sample interrupt lines: `cpu.set_nmi_line(ppu.nmi_line)`,
     `cpu.set_irq_line(apu.irq_line)`.
  7. Return `elapsed`.
- Invariant: over any sequence of `step()` calls, PPU dots advanced `== 3 × Σ` returned
  values `== 3 ×` the change in `cpu.cycles`. A scheduler written against this spec must
  never treat `cpu.cycles` as dots (that would run the PPU at 1/3 speed).
- `run_frame()`: calls `step()` until `ppu`'s frame counter increments. It is a
  convenience for later frontend tickets and must terminate for a CPU spinning in a loop.

### R6 — Interrupt lines on the CPU

- `CPU.set_nmi_line(level: bool)`: edge-detected; a low→high transition latches
  `nmi_pending`. Holding the line high does not re-trigger.
- `CPU.set_irq_line(level: bool)`: level-sensitive; stored as `irq_line`.
- `CPU.service_interrupts() -> bool` (called by `Console.step` step 2): if `nmi_pending`,
  clear it and vector through `$FFFA`; else if `irq_line and not I`, vector through `$FFFE`.
  Vectoring = push PCH, PCL of the current `PC`, then status with bit 5 set and B clear
  (even if the `B` flag is currently 1); set `I = 1`; `PC = bus.read16(vector)`;
  `cycles += 7` (CPU cycles, R5). Returns whether it serviced one.
- CPU corrections made in this ticket (required for the bus-backed CPU tests and the
  strengthened nestest assertion in R8):
  - `brk` pushes return address `PC + 2` (hardware skips BRK's padding byte), then
    status, then sets `B = 1` and `PC = bus.read16($FFFE)`. The pushed status B bit is
    unchanged from before (it reflects the current `B` flag).
  - `php` pushes status with B (bit 4) set.
  - `tsx` loads `SP & 0xFF` (the CPU stores `SP` as `$01xx`).
  - The trace's `P:` column prints status with B masked off, matching nestest's format.

### R7 — Controllers and APU stub (new modules `src/controller.py`, `src/apu.py`)

- `controller.Controller`: `buttons` (8-bit int, bit order A, B, Select, Start, Up, Down,
  Left, Right from bit 0), set by the frontend. `write(value)`: strobe = `value & 1`; while
  strobe is high the shift register reloads from `buttons`. `read()`: returns bit 0 of the
  shift register (A while strobed), then shifts; after 8 reads returns 1. `peek()`
  returns the bit `read()` would return without shifting.
- `apu.APU`: `read_register(addr)` returns 0 for `$4015` (and open-bus-free 0 for others);
  `write_register(addr, value)` stores the value in a 32-byte register file without side
  effects; `irq_line` property is always `False`. It must not raise for any `$4000-$4017`.

### R8 — Call-site wiring and existing tests

- `test_rom`'s NROM-128 check moves from `CPU(cartridge).memory.read(...)` to
  `Console(cartridge).bus.read(0x8000/0xC000)` (same expected values).
- `ROMTests.testROM` runs nestest through `Console(ROM(path))` (i.e. through `Bus`), sets
  `console.cpu.PC = 0xC000` and `SP = $01FD` (nestest's reset state), and loops
  `console.step()` 5000 times. It must **assert** (not print) that the first 5000 log
  lines match `nestest.log.txt` on PC and on the register/timing segment
  (`A`, `X`, `Y`, `P`, `SP` low byte, `CYC`).
- `AddressingModeTests` / `InstructionTests` run on the **real `Bus`**: `CPU(Bus(PPU(),
  APU(), controllers, ROM(synthetic NROM)))` with an IRQ/BRK vector at `$FFFE` pointing
  at work RAM `$0600`. Fixtures are relocated from `$2000`/`$3000`/`$FFFE` to RAM
  (`$0600`/`$0700`, zero-page pointer tables) so that no scratch access hits PPU
  registers or ROM. `$1000` operand addresses remain and are RAM mirrors of `$0000`.
- Assertions that contradicted 6502 semantics are corrected, not preserved:

  | Test | Old expectation | New expectation | Why |
  |---|---|---|---|
  | `jsr` pushed return | `0x1003` | `0x1002` | JSR pushes return address − 1 |
  | `rti` after `brk` PC | `0x1001` | `0x1002` | BRK returns to `PC + 2` (R6) |
  | `rti` restored status | `0x0F` | `0x2F` | bit 5 always reads as 1 |
  | `plp` of `0xDF` | `0xDF` | `0xFF` | bit 5 always reads as 1 |
  | `relative` target | `0x1010` | `0x1012` | target is `PC + 2 + offset` |
  | `indirect` read | dereferenced byte | 16-bit pointer at the indirect address | `Indirect.read` returns the pointer (JMP-style) |
  | `implied` read | `None` | `0` | base `AddressingMode.read` returns 0 |
  | `brk` target | `$2000` from written vector | `$0600` from cartridge vector | `$FFFE` is ROM on the real bus |

- Branch and flag tests that previously failed only because `cpu.cycles` was in dots now
  pass unchanged, because `cpu.cycles` is in CPU cycles (R5).
- All tests in the suite pass; there is no accepted failure baseline.

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
- **`cpu.cycles` in CPU cycles (reverses v1.0's "keep dots").** The existing timing
  tests already assert CPU-cycle deltas, the PPU/DMA/NMI timing is naturally expressed
  per CPU cycle, and the dot scaling was applied inconsistently (some penalties
  unscaled). One unit in the CPU and one `× 3` in the scheduler and trace removes that
  class of bug. The trace computes `CYC` from `cycles * 3`, so nestest still matches.
- **Side-effect-free `peek` in the bus protocol.** On the real bus, reading `$2002` or
  `$4016` changes state. The debug trace reads operands before execution, so it must not
  use `read`, or turning the trace on would change emulation. `peek` is a real
  production method used by the trace, not a test seam.
- **CPU unit tests on the real `Bus` (reverses v1.0's flat-`Memory` harness).** The
  acceptance criterion says "existing CPU unit tests still pass with a bus-backed
  memory". Running them on the production `Bus` meets that literally, and it exercises
  RAM mirroring and cartridge vectors. There is no parallel flat-memory CPU harness.
- **Fix wrong assertions rather than freeze them.** Keeping a 22-failure baseline hid
  real regressions. Each corrected assertion in R8 is justified by 6502 behavior or by
  the address map.
- **Governing decisions:** neither the `emulator-core` nor the `tests` LEAF doc has a
  "Governing decision:" line. The design is consistent with emulator-core's Public
  Contract ("Callers construct a CPU with injected memory/ROM") and with
  `docs/code/patterns.md` "Bus as the memory map".

## Subsystem Impact

- **Affected subsystems:** `emulator-core` (new `bus.py`, `console.py`, `controller.py`,
  `apu.py`; edits to `cpu.py`, `addressing.py`, `ppu.py`; deletion of `memory.py`);
  `tests` (new
  `test_bus.py`/`test_console.py` or equivalent; `test_cpu.py` and `test_rom.py` wiring).
- **Boundary crossings:** only `tests → emulator-core`, which already exists. No new edges.
- **New subsystems:** none. Bus/console/controller/APU stay in `emulator-core`, as its
  Purpose already anticipates ("a clocked PPU/APU/bus").
- **Catalog impact (same PR as the code):** `docs/architecture/overview.md` Source File
  Catalog adds `src/bus.py`, `src/console.py`, `src/controller.py`, `src/apu.py` under
  emulator-core and the new test module(s) under tests. The catalog is already stale:
  `src/mapper.py`, `src/tests/test_rom.py`, and `src/log.txt` from N4T2 are missing,
  and it lists `src/nestest.log.txt` under core. Fix both in that PR.
  `sub-systems/emulator-core.md` Anchor Files gains the four modules and removes
  `memory.py`.

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
- Trace purity: with `debug = True`, stepping an instruction that follows a vblank does
  not clear PPUSTATUS vblank before the instruction runs, and stepping near `$4016`
  reads does not shift the controller; only the instruction's own `read` does.
- Interrupt stack frame: NMI and IRQ push status with B clear even when `B == 1`.
- `python3 -m compileall -q .` succeeds from `src/` (now includes `ppu.py`).

## Verification

From `src/`: `python3 -m compileall -q . && python3 -m unittest discover -s tests -v`.
Pass criterion: compileall exits 0 and the unittest run reports **0 failures and 0
errors** (135 tests at `40ae131`). This includes `ROMTests.testROM` asserting its
5000-line match through `Console`/`Bus`, the relocated/corrected CPU tests (R8), and the
bus/console/interrupt tests.

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
- The processor now counts time in its own cycles instead of graphics-chip steps.
  This reverses the first draft of this spec on purpose. It fixes timing that was
  counted at the wrong scale for some instructions. Any later code that reads the
  processor's cycle counter must multiply by 3 to get graphics-chip time.
- The existing processor tests now run on the full NES wiring. Their data was moved to
  addresses that are real memory on an NES, and eight expectations that were wrong
  about how the 6502 behaves were corrected. The whole suite now passes, where 22 tests
  failed before. Because expectations changed, a reviewer should check the corrections
  table, not just the green run.
- A few processor behaviors changed to match real hardware: the return address saved by
  the software-interrupt instruction, the flag byte saved by "push status", and the
  stack-pointer copy instruction. Programs that relied on the old, wrong behavior will
  act differently.
- The debug trace now reads memory through a "look without touching" path. Any future
  memory wiring must provide that path too, or the trace will crash.
- The one-time copy of cartridge data into memory is removed. Cartridge bytes are now
  read live from the cartridge. This is what makes bank-switching cartridges (Punch-Out)
  possible later.
- Sprite-memory copies (DMA) happen instantly with the time cost added afterward. This
  has no visible effect until sprites are drawn.

## Changelog

### Version 1.1 - 2026-09-29
**Source Issue:** N4T3 (review finding N4T3-REV-1)
**Change Type:** Major

**Changes:**
- R1: bus protocol is six methods, adding side-effect-free `peek`/`peek16`. The debug
  trace and `AddressingMode.format` use only `peek`. Missing `peek` is fatal with the
  default `debug = True`.
- R2/R3/R7: `Bus.peek` routing, `PPU.peek_register`, `Controller.peek`.
- R4/R5: `cpu.cycles` is re-based to CPU cycles. All CPU increments are unscaled.
  `step()` clocks the PPU `3 × elapsed` times and returns `elapsed`. The DMA odd-cycle
  check uses CPU cycles. The trace prints `CYC` as `(cycles * 3) % 341`.
- R6: `service_interrupts` adds 7 (not `7 * 3`). Pushed status clears B unconditionally.
  `brk` now pushes `PC + 2`. `php` pushes B set. `tsx` masks SP. Trace masks B in `P:`.
- R8: CPU unit tests run on the real `Bus` with RAM-relocated fixtures and a
  cartridge IRQ vector. Eight incorrect assertions are corrected (table in R8). The
  nestest harness sets `SP = $01FD` and also asserts A/X/Y/P/SP.
- Current State: adds the implemented state at `40ae131` (135 tests, 0 failures). The
  `3accc50` baseline is kept, labeled as historical.
- Design Decisions, Verification, Test Expectations, and Plain-English hand-off are
  updated to match. The 22-failure baseline is replaced by "0 failures".

**Impact:** No code change required. This brings the spec in line with the code at
`40ae131`. Follow-on tickets (PPU rendering, frontend) must implement `peek`/`peek16`
on any bus and treat `cpu.cycles` as CPU cycles.

---

### Version 1.0 - 2026-09-29
**Source Issue:** N4T3
**Change Type:** Major

**Changes:**
- Initial specification: injected CPU bus, `Bus` memory map with RAM mirrors, PPU register
  dispatch, OAM DMA, controllers, APU stub, cartridge passthrough, `Console` scheduler at
  3 PPU dots per CPU cycle, NMI/IRQ lines, compiling PPU with vblank timing.

**Impact:** Requires code changes in `emulator-core` and test changes in `tests`.

---
