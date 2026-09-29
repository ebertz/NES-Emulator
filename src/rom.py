"""iNES cartridge loading and mapper implementations."""

from os import PathLike
from typing import Union


HEADER_SIZE = 16
TRAINER_SIZE = 512
PRG_BANK_SIZE = 0x4000
CHR_BANK_SIZE = 0x2000


class Mapper0:
    """NROM cartridge mapping for 16/32 KiB PRG and 8 KiB CHR."""

    def __init__(self, prg_rom, chr_data, chr_is_ram=False):
        if len(prg_rom) not in (PRG_BANK_SIZE, 2 * PRG_BANK_SIZE):
            raise ValueError(
                "Mapper 0 requires 16 KiB or 32 KiB of PRG ROM"
            )
        if len(chr_data) != CHR_BANK_SIZE:
            raise ValueError("Mapper 0 requires 8 KiB of CHR ROM or RAM")

        self._prg_rom = prg_rom
        self._chr_data = chr_data
        self._chr_is_ram = chr_is_ram

    def cpu_read(self, address):
        if not 0x8000 <= address <= 0xFFFF:
            raise ValueError("Mapper 0 CPU address must be in $8000-$FFFF")
        return self._prg_rom[(address - 0x8000) % len(self._prg_rom)]

    def cpu_write(self, address, value):
        if not 0x8000 <= address <= 0xFFFF:
            raise ValueError("Mapper 0 CPU address must be in $8000-$FFFF")
        # NROM PRG is read-only.

    def ppu_read(self, address):
        if not 0x0000 <= address <= 0x1FFF:
            raise ValueError("Mapper 0 PPU address must be in $0000-$1FFF")
        return self._chr_data[address]

    def ppu_write(self, address, value):
        if not 0x0000 <= address <= 0x1FFF:
            raise ValueError("Mapper 0 PPU address must be in $0000-$1FFF")
        if self._chr_is_ram:
            self._chr_data[address] = value & 0xFF


class ROM:
    """Load an iNES 1.0 image and expose its mapper interface."""

    def __init__(self, filepath: Union[str, PathLike]):
        with open(filepath, "rb") as rom_file:
            header = rom_file.read(HEADER_SIZE)
            if len(header) != HEADER_SIZE or header[:4] != b"NES\x1a":
                raise ValueError("Invalid iNES ROM: missing NES magic header")

            flags6 = header[6]
            flags7 = header[7]
            if flags7 & 0x0C == 0x08:
                raise ValueError("Unsupported NES 2.0 ROM; expected iNES 1.0")

            self.prg_rom_size = header[4]
            self.chr_rom_size = header[5]
            self.mapper = (flags7 & 0xF0) | (flags6 >> 4)
            self.has_trainer = bool(flags6 & 0x04)
            if flags6 & 0x08:
                self.mirroring = "four-screen"
            elif flags6 & 0x01:
                self.mirroring = "vertical"
            else:
                self.mirroring = "horizontal"

            if self.mapper != 0:
                raise ValueError(f"Unsupported mapper id {self.mapper}")

            self.trainer = (
                self._read_exact(rom_file, TRAINER_SIZE, "trainer")
                if self.has_trainer
                else b""
            )
            self.prg_rom = self._read_exact(
                rom_file,
                PRG_BANK_SIZE * self.prg_rom_size,
                "PRG ROM",
            )
            chr_size = CHR_BANK_SIZE * self.chr_rom_size
            self.chr_rom = self._read_exact(rom_file, chr_size, "CHR ROM")

        chr_is_ram = self.chr_rom_size == 0
        chr_data = bytearray(CHR_BANK_SIZE) if chr_is_ram else self.chr_rom
        self._mapper = Mapper0(self.prg_rom, chr_data, chr_is_ram)

    @staticmethod
    def _read_exact(rom_file, size, section):
        data = rom_file.read(size)
        if len(data) != size:
            raise ValueError(
                f"Invalid iNES ROM: truncated {section} "
                f"(expected {size} bytes, found {len(data)})"
            )
        return data

    def cpu_read(self, address):
        return self._mapper.cpu_read(address)

    def cpu_write(self, address, value):
        self._mapper.cpu_write(address, value)

    def ppu_read(self, address):
        return self._mapper.ppu_read(address)

    def ppu_write(self, address, value):
        self._mapper.ppu_write(address, value)
