import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cpu import CPU
from ppu import PPU
from rom import (
    CHR_BANK_SIZE,
    MIRROR_FOUR_SCREEN,
    MIRROR_HORIZONTAL,
    MIRROR_VERTICAL,
    PRG_BANK_SIZE,
    Mapper0,
    ROM,
    UnsupportedMapperError,
)


def ines_image(
    prg_banks=1,
    chr_banks=1,
    flags6=0,
    flags7=0,
    trainer=None,
    prg=None,
    chr_data=None,
):
    header = (
        b"NES\x1a"
        + bytes((prg_banks, chr_banks, flags6, flags7))
        + bytes(8)
    )
    prg = prg if prg is not None else bytes(PRG_BANK_SIZE * prg_banks)
    chr_data = (
        chr_data
        if chr_data is not None
        else bytes(CHR_BANK_SIZE * chr_banks)
    )
    return header + (trainer or b"") + prg + chr_data


class ROMHeaderTests(unittest.TestCase):
    def load_image(self, image):
        temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(temporary_directory.cleanup)
        path = Path(temporary_directory.name) / "synthetic.nes"
        path.write_bytes(image)
        return ROM(path)

    def test_parses_ines_header_fields_from_path(self):
        cartridge = self.load_image(
            ines_image(flags6=0x01, prg_banks=1, chr_banks=1)
        )

        self.assertEqual(cartridge.mapper_id, 0)
        self.assertEqual(cartridge.prg_rom_size, 1)
        self.assertEqual(cartridge.chr_rom_size, 1)
        self.assertEqual(cartridge.prg_rom_size_bytes, PRG_BANK_SIZE)
        self.assertEqual(cartridge.chr_rom_size_bytes, CHR_BANK_SIZE)
        self.assertEqual(cartridge.mirroring, MIRROR_VERTICAL)
        self.assertFalse(cartridge.has_trainer)
        self.assertIsNone(cartridge.trainer)

    def test_parses_horizontal_and_four_screen_mirroring(self):
        cases = (
            (0x00, MIRROR_HORIZONTAL),
            (0x09, MIRROR_FOUR_SCREEN),
        )
        for flags6, expected in cases:
            with self.subTest(flags6=flags6):
                self.assertEqual(
                    self.load_image(ines_image(flags6=flags6)).mirroring,
                    expected,
                )

    def test_reads_and_skips_trainer_before_prg_rom(self):
        trainer = bytes((index % 256 for index in range(512)))
        prg = bytes((0xA5,)) + bytes(PRG_BANK_SIZE - 1)
        cartridge = self.load_image(
            ines_image(flags6=0x04, trainer=trainer, prg=prg)
        )

        self.assertTrue(cartridge.has_trainer)
        self.assertEqual(cartridge.trainer, trainer)
        self.assertEqual(cartridge.cpu_read(0x8000), 0xA5)

    def test_exposes_chr_rom_through_ppu_read_after_load(self):
        chr_data = bytes((0x31,)) + bytes(CHR_BANK_SIZE - 2) + bytes((0x7F,))
        cartridge = self.load_image(ines_image(chr_data=chr_data))

        self.assertEqual(cartridge.ppu_read(0x0000), 0x31)
        self.assertEqual(cartridge.ppu_read(0x1FFF), 0x7F)

    def test_chr_ram_write_read_round_trip_when_no_chr_rom(self):
        cartridge = self.load_image(ines_image(chr_banks=0))

        cartridge.ppu_write(0x1FFF, 0xA5)

        self.assertEqual(cartridge.ppu_read(0x1FFF), 0xA5)

    def test_maps_32_kib_prg_through_cpu_read_after_load(self):
        prg = bytes((0x11,)) * PRG_BANK_SIZE + bytes((0x22,)) * PRG_BANK_SIZE
        cartridge = self.load_image(ines_image(prg_banks=2, prg=prg))

        self.assertEqual(cartridge.cpu_read(0x8000), 0x11)
        self.assertEqual(cartridge.cpu_read(0xC000), 0x22)
        self.assertEqual(cartridge.cpu_read(0xFFFF), 0x22)

    def test_rejects_unsupported_mapper_with_mapper_id(self):
        with self.assertRaisesRegex(
            UnsupportedMapperError, r"^Unsupported mapper 9$"
        ):
            self.load_image(ines_image(flags6=0x90))

    def test_rejects_mapper_id_from_flags7_high_nibble(self):
        # Regression: mapper_id must include (flags7 & 0xF0), not flags6 alone.
        with self.assertRaisesRegex(
            UnsupportedMapperError, r"^Unsupported mapper 16$"
        ):
            self.load_image(ines_image(flags7=0x10))

    def test_rejects_combined_mapper_id_from_flags6_and_flags7(self):
        # flags6=0x90 → low nibble 9; flags7=0x10 → high nibble 1 → mapper 25.
        with self.assertRaisesRegex(
            UnsupportedMapperError, r"^Unsupported mapper 25$"
        ):
            self.load_image(ines_image(flags6=0x90, flags7=0x10))

    def test_rejects_nes_2_header(self):
        with self.assertRaisesRegex(
            ValueError, r"^NES 2\.0 ROMs are not supported$"
        ):
            self.load_image(ines_image(flags7=0x08))

    def test_rejects_truncated_sections(self):
        valid = ines_image()
        cases = (
            (valid[:10], "iNES header"),
            (ines_image(flags6=0x04)[:100], "trainer"),
            (valid[:100], "PRG ROM"),
            (valid[:-1], "CHR ROM"),
        )
        for image, section in cases:
            with self.subTest(section=section):
                with self.assertRaisesRegex(
                    ValueError, rf"truncated {section}"
                ):
                    self.load_image(image)


class Mapper0Tests(unittest.TestCase):
    def test_maps_16_kib_prg_to_both_cpu_banks(self):
        prg = bytes((index % 256 for index in range(PRG_BANK_SIZE)))
        mapper = Mapper0(prg, bytes(CHR_BANK_SIZE), MIRROR_HORIZONTAL)

        self.assertEqual(mapper.cpu_read(0x8000), prg[0])
        self.assertEqual(mapper.cpu_read(0xBFFF), prg[-1])
        self.assertEqual(mapper.cpu_read(0xC000), prg[0])
        self.assertEqual(mapper.cpu_read(0xFFFF), prg[-1])

    def test_maps_32_kib_prg_without_mirroring(self):
        prg = bytes((0x11,)) * PRG_BANK_SIZE + bytes((0x22,)) * PRG_BANK_SIZE
        mapper = Mapper0(prg, bytes(CHR_BANK_SIZE), MIRROR_HORIZONTAL)

        self.assertEqual(mapper.cpu_read(0x8000), 0x11)
        self.assertEqual(mapper.cpu_read(0xBFFF), 0x11)
        self.assertEqual(mapper.cpu_read(0xC000), 0x22)
        self.assertEqual(mapper.cpu_read(0xFFFF), 0x22)

    def test_maps_chr_rom_and_ignores_writes(self):
        chr_data = bytes((0x31,)) + bytes(CHR_BANK_SIZE - 2) + bytes((0x7F,))
        mapper = Mapper0(bytes(PRG_BANK_SIZE), chr_data, MIRROR_VERTICAL)

        mapper.ppu_write(0x0000, 0x99)

        self.assertEqual(mapper.ppu_read(0x0000), 0x31)
        self.assertEqual(mapper.ppu_read(0x1FFF), 0x7F)
        self.assertEqual(mapper.mirroring, MIRROR_VERTICAL)

    def test_allocates_writable_chr_ram_when_chr_rom_is_absent(self):
        mapper = Mapper0(bytes(PRG_BANK_SIZE), b"", MIRROR_HORIZONTAL)

        mapper.ppu_write(0x1FFF, 0x1FF)

        self.assertEqual(mapper.ppu_read(0x1FFF), 0xFF)

    def test_rejects_invalid_nrom_sizes(self):
        with self.assertRaisesRegex(ValueError, "16 KB or 32 KB"):
            Mapper0(bytes(1), bytes(CHR_BANK_SIZE), MIRROR_HORIZONTAL)
        with self.assertRaisesRegex(ValueError, "0 KB or 8 KB"):
            Mapper0(bytes(PRG_BANK_SIZE), bytes(1), MIRROR_HORIZONTAL)

    def test_rejects_addresses_outside_cartridge_ranges(self):
        mapper = Mapper0(
            bytes(PRG_BANK_SIZE), bytes(CHR_BANK_SIZE), MIRROR_HORIZONTAL
        )
        operations = (
            (mapper.cpu_read, (0x7FFF,), "CPU"),
            (mapper.cpu_write, (0x10000, 0), "CPU"),
            (mapper.ppu_read, (0x2000,), "PPU"),
            (mapper.ppu_write, (-1, 0), "PPU"),
        )
        for operation, arguments, address_space in operations:
            with self.subTest(operation=operation.__name__):
                with self.assertRaisesRegex(ValueError, address_space):
                    operation(*arguments)

    def test_cpu_loads_mapper_zero_prg_mapping(self):
        prg = bytes((0x44,)) * PRG_BANK_SIZE
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "synthetic.nes"
            path.write_bytes(ines_image(prg=prg))

            cpu = CPU(path)

        self.assertEqual(cpu.memory.read(0x8000), 0x44)
        self.assertEqual(cpu.memory.read(0xC000), 0x44)

    def test_cpu_memory_routes_cartridge_writes_to_mapper(self):
        prg = bytes((0x44,)) * PRG_BANK_SIZE
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "synthetic.nes"
            path.write_bytes(ines_image(prg=prg))
            cpu = CPU(path)

            cpu.memory.write(0x8000, 0x99)

        self.assertEqual(cpu.memory.read(0x8000), 0x44)

    def test_ppu_routes_pattern_table_access_through_cartridge(self):
        chr_data = bytes((0x31,)) + bytes(CHR_BANK_SIZE - 1)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "synthetic.nes"
            path.write_bytes(ines_image(chr_data=chr_data))
            cpu = CPU(path)
            ppu = PPU(SimpleNamespace(cpu=cpu))

            ppu.write(0x0000, 0x99)

        self.assertEqual(ppu.read(0x0000), 0x31)

    def test_ppu_routes_pattern_table_writes_to_chr_ram(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "synthetic.nes"
            path.write_bytes(ines_image(chr_banks=0))
            cpu = CPU(path)
            ppu = PPU(SimpleNamespace(cpu=cpu))

            ppu.write(0x1FFF, 0xA5)

        self.assertEqual(ppu.read(0x1FFF), 0xA5)


if __name__ == "__main__":
    unittest.main()
