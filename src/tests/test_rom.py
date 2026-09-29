import tempfile
import unittest
from pathlib import Path

from cpu import CPU
from rom import CHR_BANK_SIZE, PRG_BANK_SIZE, Mapper0, ROM


def make_image(
    prg_banks=1,
    chr_banks=1,
    flags6=0,
    flags7=0,
    trainer=b"",
    prg=None,
    chr_data=None,
):
    header = (
        b"NES\x1a"
        + bytes((prg_banks, chr_banks, flags6, flags7))
        + bytes(8)
    )
    if prg is None:
        prg = bytes(PRG_BANK_SIZE * prg_banks)
    if chr_data is None:
        chr_data = bytes(CHR_BANK_SIZE * chr_banks)
    return header + trainer + prg + chr_data


class ROMTests(unittest.TestCase):
    def load_image(self, image):
        temporary_file = tempfile.NamedTemporaryFile(suffix=".nes")
        temporary_file.write(image)
        temporary_file.flush()
        self.addCleanup(temporary_file.close)
        return ROM(Path(temporary_file.name))

    def test_parses_ines_fields_and_skips_trainer(self):
        trainer = bytes((0xEE,)) * 512
        prg = bytes((0x11,)) * PRG_BANK_SIZE
        chr_data = bytes((0x22,)) * CHR_BANK_SIZE

        cartridge = self.load_image(
            make_image(
                flags6=0x05,
                trainer=trainer,
                prg=prg,
                chr_data=chr_data,
            )
        )

        self.assertEqual(0, cartridge.mapper)
        self.assertEqual("vertical", cartridge.mirroring)
        self.assertEqual(1, cartridge.prg_rom_size)
        self.assertEqual(1, cartridge.chr_rom_size)
        self.assertTrue(cartridge.has_trainer)
        self.assertEqual(trainer, cartridge.trainer)
        self.assertEqual(0x11, cartridge.prg_rom[0])
        self.assertEqual(0x22, cartridge.chr_rom[0])

    def test_parses_four_screen_mirroring(self):
        cartridge = self.load_image(make_image(flags6=0x08))

        self.assertEqual("four-screen", cartridge.mirroring)

    def test_mapper_zero_mirrors_16_kib_prg(self):
        prg = bytes(range(256)) * (PRG_BANK_SIZE // 256)
        cartridge = self.load_image(make_image(prg=prg))

        self.assertEqual(cartridge.cpu_read(0x8000), cartridge.cpu_read(0xC000))
        self.assertEqual(cartridge.cpu_read(0xBFFF), cartridge.cpu_read(0xFFFF))

    def test_mapper_zero_maps_32_kib_prg_without_mirroring(self):
        prg = bytes((0x10,)) * PRG_BANK_SIZE + bytes((0x20,)) * PRG_BANK_SIZE
        cartridge = self.load_image(make_image(prg_banks=2, prg=prg))

        self.assertEqual(0x10, cartridge.cpu_read(0x8000))
        self.assertEqual(0x20, cartridge.cpu_read(0xC000))

    def test_mapper_zero_maps_chr_rom(self):
        chr_data = bytes((0x31,)) * CHR_BANK_SIZE
        cartridge = self.load_image(make_image(chr_data=chr_data))

        self.assertEqual(0x31, cartridge.ppu_read(0x0000))
        cartridge.ppu_write(0x0000, 0x77)
        self.assertEqual(0x31, cartridge.ppu_read(0x0000))

    def test_mapper_zero_provides_writable_chr_ram(self):
        cartridge = self.load_image(make_image(chr_banks=0))

        cartridge.ppu_write(0x1FFF, 0x1FF)

        self.assertEqual(0xFF, cartridge.ppu_read(0x1FFF))

    def test_cpu_loads_cartridge_from_filesystem_path(self):
        with tempfile.NamedTemporaryFile(suffix=".nes") as image_file:
            image_file.write(
                make_image(prg=bytes((0xA5,)) * PRG_BANK_SIZE)
            )
            image_file.flush()

            cpu = CPU(Path(image_file.name))
            self.addCleanup(cpu.logFile.close)

            self.assertEqual(0xA5, cpu.memory.read(0x8000))
            self.assertEqual(0xA5, cpu.memory.read(0xC000))

    def test_rejects_unsupported_mapper_with_mapper_id(self):
        with self.assertRaisesRegex(ValueError, "Unsupported mapper id 9"):
            self.load_image(make_image(flags6=0x90))

    def test_rejects_missing_magic(self):
        with self.assertRaisesRegex(ValueError, "missing NES magic"):
            self.load_image(b"BAD!" + bytes(12))

    def test_rejects_short_header(self):
        with self.assertRaisesRegex(ValueError, "missing NES magic"):
            self.load_image(b"NES\x1a")

    def test_rejects_nes_2_header(self):
        with self.assertRaisesRegex(ValueError, "Unsupported NES 2.0"):
            self.load_image(make_image(flags7=0x08))

    def test_rejects_truncated_trainer(self):
        header = b"NES\x1a" + bytes((1, 1, 0x04, 0)) + bytes(8)
        with self.assertRaisesRegex(ValueError, "truncated trainer"):
            self.load_image(header + bytes(511))

    def test_rejects_truncated_prg_rom(self):
        with self.assertRaisesRegex(ValueError, "truncated PRG ROM"):
            self.load_image(make_image(prg=bytes(PRG_BANK_SIZE - 1), chr_data=b""))

    def test_rejects_truncated_chr_rom(self):
        with self.assertRaisesRegex(ValueError, "truncated CHR ROM"):
            self.load_image(make_image(chr_data=bytes(CHR_BANK_SIZE - 1)))

    def test_rejects_invalid_nrom_prg_size(self):
        with self.assertRaisesRegex(ValueError, "16 KiB or 32 KiB"):
            self.load_image(make_image(prg_banks=0))

    def test_rejects_invalid_nrom_chr_size(self):
        with self.assertRaisesRegex(ValueError, "8 KiB of CHR"):
            self.load_image(make_image(chr_banks=2))

    def test_mapper_zero_rejects_addresses_outside_its_ranges(self):
        mapper = Mapper0(bytes(PRG_BANK_SIZE), bytes(CHR_BANK_SIZE))

        with self.assertRaisesRegex(ValueError, r"\$8000-\$FFFF"):
            mapper.cpu_read(0x7FFF)
        with self.assertRaisesRegex(ValueError, r"\$8000-\$FFFF"):
            mapper.cpu_write(0x10000, 0)
        with self.assertRaisesRegex(ValueError, r"\$0000-\$1FFF"):
            mapper.ppu_read(0x2000)
        with self.assertRaisesRegex(ValueError, r"\$0000-\$1FFF"):
            mapper.ppu_write(-1, 0)


if __name__ == "__main__":
    unittest.main()
