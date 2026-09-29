# emulator-core

Python NES console core: 6502 CPU, addressing helpers, flat memory helpers,
iNES ROM loading, and a PPU module that must at least compile and accept
register traffic.

## Purpose

Own the code that turns a cartridge image into a bus-connected, clocked
CPU/PPU/APU console. Punch-Out requires Mapper 9 (MMC2); the
current tree exposes the mapper interface with Mapper 0 for nestest.

## Anchor Files

- `src/addressing.py` — addressing-mode helpers
- `src/apu.py` — register-level APU stub and IRQ line
- `src/bus.py` — CPU address map, RAM mirrors, and OAM DMA
- `src/console.py` — component wiring and cycle scheduler
- `src/controller.py` — serial controller port
- `src/cpu.py` — 6502 CPU and instruction decode/execute
- `src/harness.py` — standalone CPU wiring backed by flat memory
- `src/mapper.py` — cartridge mapper interface and NROM implementation
- `src/memory.py` — flat byte store for CPU-only harnesses
- `src/ppu.py` — PPU skeleton (must compile; rendering is later tickets)
- `src/rom.py` — path-based iNES header and cartridge loader

## Public Contract

- Callers construct a CPU with an injected bus; `Console` wires the NES bus and
  `CPUHarness` wires the supported flat-memory CPU-only configuration.
- ROM loading accepts a filesystem path and will grow a mapper interface.
- Commercial ROMs are never committed; nestest stays under `src/tests/testROMs/`.

## Key Invariants

- Python 3 only; `python3 -m compileall` over `src/` must succeed.
- CPU unit tests compare against `src/nestest.log.txt` when ROMTests run.
- No copyrighted Punch-Out (or other commercial) ROM in the tree.

## Security Posture

- Trust boundary: local process only; no network services.
- Sensitive data: none expected. Do not commit operator-supplied ROMs.
- Log hygiene: avoid dumping full ROM bytes to logs.

## Failure Modes

- Unsupported cartridge hardware is rejected with its iNES mapper id.
- Syntax errors in `ppu.py` fail compileall and block the suite.
- Incorrect iNES flags select the wrong mirroring or mapper implementation.
