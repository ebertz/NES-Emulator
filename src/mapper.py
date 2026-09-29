from abc import ABC, abstractmethod
from enum import Enum


class ROMFormatError(ValueError):
    """Raised when a cartridge image does not conform to the iNES format."""


class UnsupportedMapperError(ValueError):
    """Raised when no mapper implementation is registered for a cartridge."""

    def __init__(self, mapper_id: int):
        self.mapper_id = mapper_id
        supported = ", ".join(str(value) for value in sorted(MAPPER_REGISTRY))
        super().__init__(
            f"Unsupported iNES mapper {mapper_id} (supported: {supported})"
        )


class Mirroring(Enum):
    HORIZONTAL = "horizontal"
    VERTICAL = "vertical"
    FOUR_SCREEN = "four-screen"


class Mapper(ABC):
    @property
    @abstractmethod
    def mirroring(self) -> Mirroring:
        """Return the cartridge's current nametable mirroring mode."""

    @abstractmethod
    def cpu_read(self, addr: int) -> int:
        """Read from cartridge space in the CPU address map."""

    @abstractmethod
    def cpu_write(self, addr: int, value: int) -> None:
        """Write to cartridge space in the CPU address map."""

    @abstractmethod
    def ppu_read(self, addr: int) -> int:
        """Read from cartridge pattern-table space."""

    @abstractmethod
    def ppu_write(self, addr: int, value: int) -> None:
        """Write to cartridge pattern-table space."""


class NROM(Mapper):
    def __init__(self, header, prg_rom: bytes, chr_rom: bytes):
        if header.prg_rom_banks not in (1, 2):
            raise ROMFormatError(
                "Mapper 0 requires 1 or 2 PRG ROM banks; "
                f"got {header.prg_rom_banks}"
            )
        if header.chr_rom_banks not in (0, 1):
            raise ROMFormatError(
                "Mapper 0 requires 0 or 1 CHR ROM banks; "
                f"got {header.chr_rom_banks}"
            )

        self._mirroring = header.mirroring
        self._prg = bytes(prg_rom)
        self._chr_is_ram = header.chr_rom_banks == 0
        self._chr = bytearray(0x2000) if self._chr_is_ram else bytes(chr_rom)

    @property
    def mirroring(self) -> Mirroring:
        return self._mirroring

    def cpu_read(self, addr: int) -> int:
        if 0x4020 <= addr < 0x8000:
            return 0
        if 0x8000 <= addr <= 0xFFFF:
            return self._prg[(addr - 0x8000) % len(self._prg)]
        raise ValueError(f"CPU cartridge address out of range: {addr:#06x}")

    def cpu_write(self, addr: int, value: int) -> None:
        if 0x4020 <= addr <= 0xFFFF:
            return
        raise ValueError(f"CPU cartridge address out of range: {addr:#06x}")

    def ppu_read(self, addr: int) -> int:
        if 0 <= addr <= 0x1FFF:
            return self._chr[addr]
        raise ValueError(f"PPU pattern address out of range: {addr:#06x}")

    def ppu_write(self, addr: int, value: int) -> None:
        if not 0 <= addr <= 0x1FFF:
            raise ValueError(f"PPU pattern address out of range: {addr:#06x}")
        if self._chr_is_ram:
            self._chr[addr] = value & 0xFF


MAPPER_REGISTRY = {0: NROM}


def create_mapper(header, prg_rom: bytes, chr_rom: bytes) -> Mapper:
    mapper_class = MAPPER_REGISTRY.get(header.mapper)
    if mapper_class is None:
        raise UnsupportedMapperError(header.mapper)
    return mapper_class(header, prg_rom, chr_rom)
