from dataclasses import dataclass
from os import PathLike

from mapper import Mirroring, ROMFormatError, create_mapper


INES_HEADER_SIZE = 16
TRAINER_SIZE = 512
PRG_BANK_SIZE = 0x4000
CHR_BANK_SIZE = 0x2000


@dataclass(frozen=True)
class INESHeader:
    prg_rom_banks: int
    chr_rom_banks: int
    mirroring: Mirroring
    has_battery: bool
    has_trainer: bool
    mapper: int
    is_nes2: bool


def parse_header(data: bytes) -> INESHeader:
    """Parse the fixed-width portion of an iNES header without performing I/O."""
    if len(data) < INES_HEADER_SIZE:
        raise ROMFormatError(
            f"iNES header is too short: expected 16 bytes, got {len(data)}"
        )

    header = data[:INES_HEADER_SIZE]
    if header[:4] != b"NES\x1a":
        raise ROMFormatError("iNES magic is missing")

    flags6 = header[6]
    flags7 = header[7]
    is_nes2 = flags7 & 0x0C == 0x08
    if not is_nes2 and any(header[12:16]):
        flags7 &= 0x0F

    if flags6 & 0x08:
        mirroring = Mirroring.FOUR_SCREEN
    elif flags6 & 0x01:
        mirroring = Mirroring.VERTICAL
    else:
        mirroring = Mirroring.HORIZONTAL

    return INESHeader(
        prg_rom_banks=header[4],
        chr_rom_banks=header[5],
        mirroring=mirroring,
        has_battery=bool(flags6 & 0x02),
        has_trainer=bool(flags6 & 0x04),
        mapper=(flags7 & 0xF0) | (flags6 >> 4),
        is_nes2=is_nes2,
    )


class ROM:
    def __init__(self, path: str | PathLike):
        with open(path, "rb") as rom_file:
            data = rom_file.read()

        self.header = parse_header(data)
        if self.header.prg_rom_banks == 0:
            raise ROMFormatError("iNES ROM must contain at least one PRG ROM bank")

        trainer_size = TRAINER_SIZE if self.header.has_trainer else 0
        prg_size = PRG_BANK_SIZE * self.header.prg_rom_banks
        chr_size = CHR_BANK_SIZE * self.header.chr_rom_banks
        expected_size = INES_HEADER_SIZE + trainer_size + prg_size + chr_size
        if len(data) < expected_size:
            raise ROMFormatError(
                "iNES image is truncated: "
                f"expected {expected_size} bytes, got {len(data)}"
            )

        offset = INES_HEADER_SIZE
        if self.header.has_trainer:
            self.trainer = data[offset : offset + TRAINER_SIZE]
            offset += TRAINER_SIZE
        else:
            self.trainer = None

        self.prg_rom = data[offset : offset + prg_size]
        offset += prg_size
        self.chr_rom = data[offset : offset + chr_size]
        self.prg_rom_size = self.header.prg_rom_banks
        self.chr_rom_size = self.header.chr_rom_banks
        self.mapper = create_mapper(self.header, self.prg_rom, self.chr_rom)
