import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from console import Console  # noqa: E402
from mapper import (  # noqa: E402
    Mirroring,
    ROMFormatError,
    UnsupportedMapperError,
    create_mapper,
)
from rom import INESHeader, ROM, parse_header  # noqa: E402


def make_header(prg_banks=1, chr_banks=1, flags6=0, flags7=0, tail=b"\0" * 4):
    return (
        b"NES\x1a"
        + bytes((prg_banks, chr_banks, flags6, flags7))
        + b"\0" * 4
        + tail
    )


def make_ines(prg=b"\0" * 0x4000, chr_data=b"\0" * 0x2000, **header):
    return make_header(
        prg_banks=len(prg) // 0x4000,
        chr_banks=len(chr_data) // 0x2000,
        **header,
    ) + prg + chr_data


class HeaderTests(unittest.TestCase):
    def test_parses_ines_fields(self):
        header = parse_header(make_header(2, 0, flags6=0x23, flags7=0x40))

        self.assertEqual(header.prg_rom_banks, 2)
        self.assertEqual(header.chr_rom_banks, 0)
        self.assertEqual(header.mirroring, Mirroring.VERTICAL)
        self.assertTrue(header.has_battery)
        self.assertFalse(header.has_trainer)
        self.assertEqual(header.mapper, 0x42)
        self.assertFalse(header.is_nes2)

    def test_four_screen_overrides_vertical_mirroring(self):
        header = parse_header(make_header(flags6=0x09))
        self.assertEqual(header.mirroring, Mirroring.FOUR_SCREEN)

    def test_detects_nes2_header(self):
        header = parse_header(make_header(flags7=0x08))
        self.assertTrue(header.is_nes2)

    def test_masks_diskdude_mapper_bits(self):
        header = parse_header(
            make_header(flags6=0x10, flags7=0xF0, tail=b"Dude")
        )
        self.assertEqual(header.mapper, 1)

    def test_nes2_does_not_mask_mapper_when_header_tail_is_nonzero(self):
        # Regression: DiskDude masking applies only to iNES 1.0 headers.
        header = parse_header(
            make_header(flags6=0x10, flags7=0x48, tail=b"\x01\x02\x03\x04")
        )
        self.assertTrue(header.is_nes2)
        self.assertEqual(header.mapper, 0x41)

    def test_rejects_short_header(self):
        with self.assertRaisesRegex(ROMFormatError, "expected 16 bytes"):
            parse_header(b"NES\x1a")

    def test_rejects_missing_magic(self):
        with self.assertRaisesRegex(ROMFormatError, "iNES magic is missing"):
            parse_header(b"BAD!" + b"\0" * 12)


class ROMLoaderTests(unittest.TestCase):
    def write_rom(self, data):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / "synthetic.nes"
        path.write_bytes(data)
        return path

    def test_loads_from_pathlike_and_exposes_compatibility_sizes(self):
        cartridge = ROM(self.write_rom(make_ines()))

        self.assertEqual(cartridge.prg_rom_size, 1)
        self.assertEqual(cartridge.chr_rom_size, 1)
        self.assertIsNone(cartridge.trainer)
        self.assertEqual(cartridge.mapper.mirroring, Mirroring.HORIZONTAL)

    def test_bus_reads_mapper_prg_from_both_nrom128_windows(self):
        prg = b"\xA5" + b"\0" * (0x4000 - 1)
        cartridge = ROM(self.write_rom(make_ines(prg=prg)))

        console = Console(cartridge)

        self.assertEqual(console.bus.read(0x8000), 0xA5)
        self.assertEqual(console.bus.read(0xC000), 0xA5)
        console.cpu.logFile.close()

    def test_skips_and_retains_trainer(self):
        trainer = bytes((index & 0xFF for index in range(512)))
        prg = b"\xA5" + b"\0" * (0x4000 - 1)
        image = make_header(flags6=0x04) + trainer + prg + b"\0" * 0x2000

        cartridge = ROM(self.write_rom(image))

        self.assertEqual(cartridge.trainer, trainer)
        self.assertEqual(cartridge.prg_rom[0], 0xA5)

    def test_rejects_truncated_image_with_expected_and_actual_sizes(self):
        path = self.write_rom(make_header() + b"\0")
        with self.assertRaisesRegex(
            ROMFormatError, r"expected 24592 bytes, got 17"
        ):
            ROM(path)

    def test_rejects_zero_prg_banks(self):
        path = self.write_rom(make_header(prg_banks=0, chr_banks=0))
        with self.assertRaisesRegex(ROMFormatError, "at least one PRG ROM bank"):
            ROM(path)

    def test_surfaces_unsupported_mapper_id(self):
        path = self.write_rom(make_ines(flags6=0x90))
        with self.assertRaisesRegex(
            UnsupportedMapperError, "Unsupported iNES mapper 9"
        ) as raised:
            ROM(path)
        self.assertEqual(raised.exception.mapper_id, 9)


class NROMTests(unittest.TestCase):
    def header(self, prg_banks=1, chr_banks=1):
        return INESHeader(
            prg_rom_banks=prg_banks,
            chr_rom_banks=chr_banks,
            mirroring=Mirroring.VERTICAL,
            has_battery=False,
            has_trainer=False,
            mapper=0,
            is_nes2=False,
        )

    def test_nrom128_mirrors_prg_and_ignores_cpu_writes(self):
        mapper = create_mapper(
            self.header(), bytes(range(256)) * 64, b"\0" * 0x2000
        )
        before = mapper.cpu_read(0x8001)

        mapper.cpu_write(0x8001, 0xFF)

        self.assertEqual(mapper.cpu_read(0x8001), before)
        self.assertEqual(mapper.cpu_read(0x8001), mapper.cpu_read(0xC001))
        self.assertEqual(mapper.cpu_read(0x6000), 0)

    def test_nrom256_maps_prg_linearly(self):
        prg = b"\x11" * 0x4000 + b"\x22" * 0x4000
        mapper = create_mapper(self.header(prg_banks=2), prg, b"\0" * 0x2000)
        self.assertEqual(mapper.cpu_read(0x8000), 0x11)
        self.assertEqual(mapper.cpu_read(0xC000), 0x22)

    def test_chr_rom_is_read_only(self):
        mapper = create_mapper(self.header(), b"\0" * 0x4000, b"\x37" * 0x2000)
        mapper.ppu_write(0x10, 0x99)
        self.assertEqual(mapper.ppu_read(0x10), 0x37)

    def test_chr_ram_is_writable_and_masks_values(self):
        mapper = create_mapper(
            self.header(chr_banks=0), b"\0" * 0x4000, b""
        )
        mapper.ppu_write(0x10, 0x1FF)
        self.assertEqual(mapper.ppu_read(0x10), 0xFF)

    def test_rejects_invalid_nrom_bank_counts(self):
        with self.assertRaisesRegex(ROMFormatError, "Mapper 0.*3"):
            create_mapper(self.header(prg_banks=3), b"\0" * 0xC000, b"")
        with self.assertRaisesRegex(ROMFormatError, "Mapper 0.*2"):
            create_mapper(
                self.header(chr_banks=2), b"\0" * 0x4000, b"\0" * 0x4000
            )

    def test_rejects_addresses_outside_mapper_space(self):
        mapper = create_mapper(self.header(), b"\0" * 0x4000, b"\0" * 0x2000)
        with self.assertRaisesRegex(ValueError, "CPU cartridge address"):
            mapper.cpu_read(0x401F)
        with self.assertRaisesRegex(ValueError, "CPU cartridge address"):
            mapper.cpu_write(0x1000, 0)
        with self.assertRaisesRegex(ValueError, "PPU pattern address"):
            mapper.ppu_read(0x2000)
        with self.assertRaisesRegex(ValueError, "PPU pattern address"):
            mapper.ppu_write(-1, 0)


if __name__ == "__main__":
    unittest.main()
