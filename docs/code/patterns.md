# Patterns

## Inject dependencies into the CPU

Construct the CPU with memory/ROM supplied by the caller or test. Do not open
`nestest.nes` at import or in `__init__` unless the caller asked for it.

## Resolve fixtures from the test file

```python
from pathlib import Path
ROM = Path(__file__).resolve().parent / "testROMs" / "nestest.nes"
```

## Bus as the memory map

CPU reads/writes go through a bus that owns RAM mirrors, PPU registers, OAM DMA,
controllers, APU, and cartridge space. Keep PPU/APU behind narrow methods so
tickets can stub then fill in.

## Mapper protocol

Cartridges expose cpu_read/write and ppu_read/write plus mirroring. NROM first;
MMC2 (mapper 9) observes PPU pattern fetches for FD/FE latches.

## Headless frontend for CI

Interactive Pygame is for operators. Automated checks use a headless
`--frames N --dump path` path that does not require a display.
