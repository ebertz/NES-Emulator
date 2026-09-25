"""iNES 1.0 cartridge loading and mapper implementations."""

INES_HEADER_SIZE = 16
PRG_BANK_SIZE = 0x4000
CHR_BANK_SIZE = 0x2000
TRAINER_SIZE = 512

MIRROR_HORIZONTAL = "horizontal"
MIRROR_VERTICAL = "vertical"
MIRROR_FOUR_SCREEN = "four-screen"


class UnsupportedMapperError(ValueError):
    """Raised when a cartridge uses a mapper the emulator cannot provide."""


class Mapper0:
    """NROM cartridge mapping for 16/32 KiB PRG and 8 KiB CHR."""

    def __init__(self, prg_rom, chr_rom, mirroring):
        if len(prg_rom) not in (PRG_BANK_SIZE, PRG_BANK_SIZE * 2):
            raise ValueError(
                "Mapper 0 requires 16 KB or 32 KB of PRG ROM"
            )
        if len(chr_rom) not in (0, CHR_BANK_SIZE):
            raise ValueError("Mapper 0 requires 0 KB or 8 KB of CHR ROM")

        self.prg_rom = bytes(prg_rom)
        self.chr = bytearray(chr_rom or bytes(CHR_BANK_SIZE))
        self.has_chr_ram = not chr_rom
        self.mirroring = mirroring

    def cpu_read(self, address):
        if not 0x8000 <= address <= 0xFFFF:
            raise ValueError(
                "Mapper 0 CPU address must be in $8000-$FFFF"
            )
        return self.prg_rom[(address - 0x8000) % len(self.prg_rom)]

    def cpu_write(self, address, value):
        if not 0x8000 <= address <= 0xFFFF:
            raise ValueError(
                "Mapper 0 CPU address must be in $8000-$FFFF"
            )
        # NROM has no writable registers or PRG RAM in this implementation.

    def ppu_read(self, address):
        if not 0 <= address <= 0x1FFF:
            raise ValueError(
                "Mapper 0 PPU address must be in $0000-$1FFF"
            )
        return self.chr[address]

    def ppu_write(self, address, value):
        if not 0 <= address <= 0x1FFF:
            raise ValueError(
                "Mapper 0 PPU address must be in $0000-$1FFF"
            )
        if self.has_chr_ram:
            self.chr[address] = value & 0xFF


class ROM:
    """Load an iNES 1.0 image from a filesystem path."""

    def __init__(self, filepath):
        with open(filepath, "rb") as rom_file:
            header = self._read_exact(
                rom_file, INES_HEADER_SIZE, "iNES header"
            )
            if header[:4] != b"NES\x1a":
                raise ValueError("Invalid iNES ROM")

            flags6 = header[6]
            flags7 = header[7]
            if flags7 & 0x0C == 0x08:
                raise ValueError("NES 2.0 ROMs are not supported")

            self.prg_rom_size = header[4]
            self.chr_rom_size = header[5]
            self.prg_rom_size_bytes = self.prg_rom_size * PRG_BANK_SIZE
            self.chr_rom_size_bytes = self.chr_rom_size * CHR_BANK_SIZE
            self.mapper_id = (flags7 & 0xF0) | (flags6 >> 4)
            self.mapper_number = self.mapper_id
            self.mapper = self.mapper_id
            self.mirroring = self._parse_mirroring(flags6)
            self.has_trainer = bool(flags6 & 0x04)

            if self.mapper_id != 0:
                raise UnsupportedMapperError(
                    f"Unsupported mapper {self.mapper_id}"
                )

            self.trainer = (
                self._read_exact(rom_file, TRAINER_SIZE, "trainer")
                if self.has_trainer
                else None
            )
            self.prg_rom = self._read_exact(
                rom_file, self.prg_rom_size_bytes, "PRG ROM"
            )
            self.chr_rom = self._read_exact(
                rom_file, self.chr_rom_size_bytes, "CHR ROM"
            )

        self.mapper = Mapper0(
            self.prg_rom, self.chr_rom, self.mirroring
        )

    @staticmethod
    def _parse_mirroring(flags6):
        if flags6 & 0x08:
            return MIRROR_FOUR_SCREEN
        if flags6 & 0x01:
            return MIRROR_VERTICAL
        return MIRROR_HORIZONTAL

    @staticmethod
    def _read_exact(rom_file, size, section):
        data = rom_file.read(size)
        if len(data) != size:
            raise ValueError(
                f"Invalid iNES ROM: truncated {section} "
                f"(expected {size} bytes, got {len(data)})"
            )
        return data

    def cpu_read(self, address):
        return self.mapper.cpu_read(address)

    def cpu_write(self, address, value):
        self.mapper.cpu_write(address, value)

    def ppu_read(self, address):
        return self.mapper.ppu_read(address)

    def ppu_write(self, address, value):
        self.mapper.ppu_write(address, value)
