import hashlib
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from console import Console  # noqa: E402
from mapper import Mirroring, create_mapper  # noqa: E402
from ppu import PPU  # noqa: E402
from rom import INESHeader, ROM  # noqa: E402
from test_rom import make_ines  # noqa: E402


_UNSUPPORTED_MIRRORING = object()


class _StubMapperUnsupportedMirroring:
    """Mapper whose mirroring is not a Mirroring enum member (PPU must refuse)."""

    @property
    def mirroring(self):
        return _UNSUPPORTED_MIRRORING

    def ppu_read(self, addr):
        return 0

    def ppu_write(self, addr, value):
        pass


def _nrom_mapper(mirroring=Mirroring.HORIZONTAL, chr_banks=0):
    header = INESHeader(
        prg_rom_banks=1,
        chr_rom_banks=chr_banks,
        mirroring=mirroring,
        has_battery=False,
        has_trainer=False,
        mapper=0,
        is_nes2=False,
    )
    chr_data = b"" if chr_banks == 0 else b"\0" * 0x2000
    return create_mapper(header, b"\0" * 0x4000, chr_data)


def _dots_per_frame(ppu):
    """Count step() calls from (0,0) until frame increments."""
    start_frame = ppu.frame
    steps = 0
    while ppu.frame == start_frame:
        ppu.step()
        steps += 1
    return steps


def _advance_to(ppu, scanline, dot):
    while ppu.scanline != scanline or ppu.dot != dot:
        ppu.step()


def _run_one_frame(ppu):
    start_frame = ppu.frame
    while ppu.frame == start_frame:
        ppu.step()


def _fill_tile_pattern(mapper, tile_index=0, plane0=0xFF, plane1=0x00):
    base = tile_index * 16
    for row in range(8):
        mapper.ppu_write(base + row, plane0)
        mapper.ppu_write(base + 8 + row, plane1)


def _setup_uniform_nametable(ppu, tile=0, attribute=0):
    for offset in range(960):
        ppu.write_vram(0x2000 + offset, tile)
    for offset in range(64):
        ppu.write_vram(0x23C0 + offset, attribute)


def _enable_background_rendering(ppu, mask=0x0A):
    ppu.ctrl = 0
    ppu.mask = mask
    ppu.t = 0
    ppu.v = 0
    ppu.scanline = 0
    ppu.dot = 0


# Synthetic CHR/nametable fixture: solid tile 0 -> palette entry 1 (0x30).
_BACKGROUND_BACKDROP = 0x0F
_BACKGROUND_TILE_COLOR = 0x30
_BACKGROUND_FRAME_SHA256 = (
    "ef8a2e28b8c80ce812becd0228bd36632f6b3bd10e75bf022e470a332ad68184"
)


def _idle_nrom_ines():
    """CHR-RAM cartridge whose reset vector lands in an all-NOP PRG bank."""
    prg = bytearray([0xEA] * 0x4000)
    prg[-4] = 0x00
    prg[-3] = 0x80
    return make_ines(prg=bytes(prg), chr_data=b"")


class PPUBackgroundRenderingTests(unittest.TestCase):
    def _ppu_with_chr_ram(self):
        mapper = _nrom_mapper(chr_banks=0)
        return PPU(mapper), mapper

    def test_visible_scanline_fills_256_background_pixels(self):
        ppu, mapper = self._ppu_with_chr_ram()
        _fill_tile_pattern(mapper, plane0=0xFF)
        _setup_uniform_nametable(ppu)
        ppu.write_vram(0x3F00, _BACKGROUND_BACKDROP)
        ppu.write_vram(0x3F01, _BACKGROUND_TILE_COLOR)
        _enable_background_rendering(ppu, mask=0x0A)
        _run_one_frame(ppu)

        row = ppu.frame_buffer[0:256]
        self.assertEqual(len(row), 256)
        self.assertEqual(bytes(row), bytes([_BACKGROUND_TILE_COLOR] * 256))

    def test_left_column_mask_keeps_backdrop_in_first_eight_pixels(self):
        ppu, mapper = self._ppu_with_chr_ram()
        _fill_tile_pattern(mapper, plane0=0xFF)
        _setup_uniform_nametable(ppu)
        ppu.write_vram(0x3F00, _BACKGROUND_BACKDROP)
        ppu.write_vram(0x3F01, _BACKGROUND_TILE_COLOR)
        _enable_background_rendering(ppu, mask=0x08)
        _run_one_frame(ppu)

        self.assertEqual(bytes(ppu.frame_buffer[0:8]), bytes([_BACKGROUND_BACKDROP] * 8))
        self.assertEqual(ppu.frame_buffer[8], _BACKGROUND_TILE_COLOR)

    def test_fine_x_scroll_shifts_pattern_fetch_within_tile(self):
        ppu, mapper = self._ppu_with_chr_ram()
        _fill_tile_pattern(mapper, plane0=0x81)
        _setup_uniform_nametable(ppu)
        ppu.write_vram(0x3F00, _BACKGROUND_BACKDROP)
        ppu.write_vram(0x3F01, _BACKGROUND_TILE_COLOR)
        _enable_background_rendering(ppu, mask=0x0A)
        ppu.read_register(2)
        ppu.write_register(5, 0x00)
        ppu.write_register(5, 0x00)
        _run_one_frame(ppu)
        self.assertEqual(ppu.frame_buffer[0], _BACKGROUND_TILE_COLOR)

        ppu, mapper = self._ppu_with_chr_ram()
        _fill_tile_pattern(mapper, plane0=0x81)
        _setup_uniform_nametable(ppu)
        ppu.write_vram(0x3F00, _BACKGROUND_BACKDROP)
        ppu.write_vram(0x3F01, _BACKGROUND_TILE_COLOR)
        _enable_background_rendering(ppu, mask=0x0A)
        ppu.read_register(2)
        ppu.write_register(5, 0x05)
        ppu.write_register(5, 0x00)
        _run_one_frame(ppu)
        self.assertEqual(ppu.frame_buffer[0], _BACKGROUND_BACKDROP)

    def test_attribute_byte_selects_sub_palette_for_tile_quadrant(self):
        ppu, mapper = self._ppu_with_chr_ram()
        _fill_tile_pattern(mapper, plane0=0xFF)
        _setup_uniform_nametable(ppu, attribute=0x02)
        ppu.write_vram(0x3F00, _BACKGROUND_BACKDROP)
        ppu.write_vram(0x3F01, _BACKGROUND_TILE_COLOR)
        ppu.write_vram(0x3F09, 0x55)
        _enable_background_rendering(ppu, mask=0x0A)
        _run_one_frame(ppu)

        self.assertEqual(ppu.frame_buffer[0], 0x15)

    def test_first_frame_buffer_sha256_matches_synthetic_fixture(self):
        ppu, mapper = self._ppu_with_chr_ram()
        _fill_tile_pattern(mapper, plane0=0xFF)
        _setup_uniform_nametable(ppu)
        ppu.write_vram(0x3F00, _BACKGROUND_BACKDROP)
        ppu.write_vram(0x3F01, _BACKGROUND_TILE_COLOR)
        _enable_background_rendering(ppu, mask=0x0A)
        _run_one_frame(ppu)

        digest = hashlib.sha256(bytes(ppu.frame_buffer)).hexdigest()
        self.assertEqual(digest, _BACKGROUND_FRAME_SHA256)

    def test_console_run_frame_produces_same_background_frame_hash(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / "background_fixture.nes"
        path.write_bytes(_idle_nrom_ines())
        console = Console(ROM(path))
        mapper = console.bus.cartridge.mapper
        _fill_tile_pattern(mapper, plane0=0xFF)
        _setup_uniform_nametable(console.ppu)
        console.ppu.write_vram(0x3F00, _BACKGROUND_BACKDROP)
        console.ppu.write_vram(0x3F01, _BACKGROUND_TILE_COLOR)
        _enable_background_rendering(console.ppu, mask=0x0A)
        console.reset()

        console.run_frame()

        digest = hashlib.sha256(bytes(console.ppu.frame_buffer)).hexdigest()
        self.assertEqual(digest, _BACKGROUND_FRAME_SHA256)


class PPUVblankTimingTests(unittest.TestCase):
    def test_vblank_sets_at_scanline_241_dot_1(self):
        ppu = PPU()
        for _ in range(241 * 341):
            ppu.step()
        self.assertFalse(ppu.vblank)
        self.assertEqual(ppu.peek_register(2) & 0x80, 0)
        ppu.step()
        self.assertTrue(ppu.vblank)
        self.assertEqual(ppu.peek_register(2) & 0x80, 0x80)

    def test_vblank_stays_set_through_scanline_260(self):
        ppu = PPU()
        _advance_to(ppu, 260, 340)
        self.assertTrue(ppu.vblank)

    def test_pre_render_clears_vblank_and_sprite_flags(self):
        ppu = PPU()
        ppu.sprite_zero_hit = True
        ppu.sprite_overflow = True
        _advance_to(ppu, 260, 340)
        self.assertTrue(ppu.vblank)
        _advance_to(ppu, 261, 1)
        self.assertFalse(ppu.vblank)
        self.assertFalse(ppu.sprite_zero_hit)
        self.assertFalse(ppu.sprite_overflow)


class PPUStatusReadTests(unittest.TestCase):
    def test_status_read_clears_vblank_and_w_preserves_low_bits(self):
        ppu = PPU()
        ppu.vblank = True
        ppu.write_register(0, 0xAB)
        ppu.w = 1

        first = ppu.read_register(2)
        second = ppu.read_register(2)

        self.assertEqual(first & 0x80, 0x80)
        self.assertEqual(first & 0x1F, 0x0B)
        self.assertEqual(second & 0x80, 0)
        self.assertFalse(ppu.vblank)
        self.assertEqual(ppu.w, 0)


class PPUNMILineTests(unittest.TestCase):
    def test_nmi_line_rises_only_with_ctrl_bit7_at_vblank(self):
        ppu = PPU()
        ppu.ctrl = 0x80
        self.assertFalse(ppu.nmi_line)
        ppu.vblank = True
        self.assertTrue(ppu.nmi_line)

    def test_enabling_nmi_mid_vblank_raises_line(self):
        ppu = PPU()
        ppu.vblank = True
        ppu.ctrl = 0x00
        self.assertFalse(ppu.nmi_line)
        ppu.write_register(0, 0x80)
        self.assertTrue(ppu.nmi_line)

    def test_status_read_during_vblank_lowers_nmi_line(self):
        ppu = PPU()
        ppu.ctrl = 0x80
        ppu.vblank = True
        self.assertTrue(ppu.nmi_line)
        ppu.read_register(2)
        self.assertFalse(ppu.nmi_line)


class PPUOddFrameSkipTests(unittest.TestCase):
    def test_odd_frame_skips_one_dot_when_rendering_enabled(self):
        ppu = PPU()
        ppu.mask = 0x08
        even_steps = _dots_per_frame(ppu)
        self.assertEqual(even_steps, 89_342)
        odd_steps = _dots_per_frame(ppu)
        self.assertEqual(odd_steps, 89_341)

    def test_no_skip_when_rendering_disabled(self):
        ppu = PPU()
        ppu.mask = 0x00
        first = _dots_per_frame(ppu)
        second = _dots_per_frame(ppu)
        self.assertEqual(first, 89_342)
        self.assertEqual(second, 89_342)


class PPUScrollRegisterTests(unittest.TestCase):
    def test_nesdev_scrolling_worked_example(self):
        ppu = PPU()
        ppu.write_register(0, 0x00)
        ppu.read_register(2)
        self.assertEqual((ppu.t, ppu.x, ppu.v, ppu.w), (0, 0, 0, 0))

        ppu.write_register(5, 0x7D)
        self.assertEqual((ppu.t, ppu.x, ppu.w), (0x000F, 5, 1))

        ppu.write_register(5, 0x5E)
        self.assertEqual((ppu.t, ppu.w), (0x616F, 0))

        ppu.write_register(6, 0x3D)
        self.assertEqual((ppu.t, ppu.w), (0x3D6F, 1))

        ppu.write_register(6, 0xF0)
        self.assertEqual((ppu.t, ppu.v, ppu.w), (0x3DF0, 0x3DF0, 0))

    def test_ppuctrl_updates_nametable_bits_in_t(self):
        ppu = PPU()
        ppu.t = 0x1234
        ppu.write_register(0, 0x03)
        expected = (0x1234 & ~0x0C00) | ((0x03 & 0x03) << 10)
        self.assertEqual(ppu.t, expected)

    def test_shared_w_between_scroll_and_addr(self):
        ppu = PPU()
        ppu.write_register(5, 0x00)
        self.assertEqual(ppu.w, 1)
        ppu.write_register(6, 0x12)
        self.assertEqual(ppu.v, 0x0012)
        self.assertEqual(ppu.w, 0)
        ppu.read_register(2)
        ppu.write_register(6, 0x12)
        ppu.write_register(6, 0x34)
        self.assertEqual(ppu.v, 0x1234)

    def test_ppuaddr_high_write_masks_to_six_bits_and_clears_bit_14(self):
        ppu = PPU()
        ppu.t = 0x7FFF
        ppu.write_register(6, 0xFF)
        self.assertEqual(ppu.t, 0x3FFF)
        self.assertEqual(ppu.w, 1)


class PPUPpuDataTests(unittest.TestCase):
    def _set_v(self, ppu, addr):
        ppu.write_register(6, (addr >> 8) & 0xFF)
        ppu.write_register(6, addr & 0xFF)

    def test_buffered_read_returns_stale_then_written_bytes(self):
        ppu = PPU()
        self._set_v(ppu, 0x2108)
        ppu.write_register(7, ord("A"))
        ppu.write_register(7, ord("B"))
        self._set_v(ppu, 0x2108)
        self.assertEqual(ppu.read_register(7), 0)
        self.assertEqual(ppu.read_register(7), ord("A"))
        self.assertEqual(ppu.read_register(7), ord("B"))

    def test_ctrl_bit2_selects_32_byte_v_increment(self):
        ppu = PPU()
        ppu.ctrl = 0x04
        self._set_v(ppu, 0x2000)
        ppu.write_register(7, 0x01)
        self.assertEqual(ppu.v, 0x2020)

    def test_v_wraps_at_15_bits_after_ppudata_write(self):
        ppu = PPU()
        ppu.v = 0x7FFF
        ppu.write_register(7, 0x55)
        self.assertEqual(ppu.v, 0)


class PPUVram14BitMaskTests(unittest.TestCase):
    """Regression: read_vram/write_vram must mask to 14 bits before decode."""

    def test_read_vram_masks_chr_fetch_above_0x4000(self):
        mapper = _nrom_mapper(chr_banks=0)
        ppu = PPU(mapper)
        mapper.ppu_write(0x0010, 0xBE)
        self.assertEqual(ppu.read_vram(0x4010), 0xBE)
        self.assertEqual(mapper.ppu_read(0x0010), 0xBE)

    def test_ppudata_write_at_v_0x4010_targets_chr_not_nametable(self):
        mapper = _nrom_mapper(chr_banks=0)
        ppu = PPU(mapper)
        ppu.v = 0x4010
        ppu.write_register(7, 0xDE)
        self.assertEqual(mapper.ppu_read(0x0010), 0xDE)
        self.assertEqual(ppu.read_vram(0x2000), 0)

    def test_ppudata_write_at_v_0x6005_targets_same_nametable_as_0x2005(self):
        ppu = PPU()
        ppu.v = 0x6005
        ppu.write_register(7, 0x42)
        self.assertEqual(ppu.read_vram(0x2005), 0x42)
        self.assertEqual(ppu.read_vram(0x6005), 0x42)


class PPUPaletteTests(unittest.TestCase):
    def test_palette_read_bypasses_buffer_and_refills_from_nametable_mirror(self):
        ppu = PPU()
        ppu.write_vram(0x3F00, 0x2C)
        ppu.write_vram(0x2F00, 0x77)
        ppu._data_latch = 0xC0
        ppu.write_register(6, 0x3F)
        ppu.write_register(6, 0x00)

        self.assertEqual(ppu.read_register(7), 0x2C)

        ppu.write_register(6, 0x21)
        ppu.write_register(6, 0x00)
        self.assertEqual(ppu.read_register(7), 0x77)

    def test_grayscale_mask_on_palette_read(self):
        ppu = PPU()
        ppu.mask = 0x01
        ppu.write_vram(0x3F00, 0x2C)
        ppu._data_latch = 0x00
        ppu.write_register(6, 0x3F)
        ppu.write_register(6, 0x00)
        self.assertEqual(ppu.read_register(7) & 0x3F, 0x2C & 0x30)

    def test_palette_mirroring_pairs(self):
        ppu = PPU()
        pairs = ((0x3F10, 0x3F00), (0x3F14, 0x3F04), (0x3F18, 0x3F08), (0x3F1C, 0x3F0C))
        for alias, primary in pairs:
            ppu.write_vram(alias, 0x3A)
            self.assertEqual(ppu.read_vram(primary), 0x3A)
            ppu.write_vram(primary, 0x15)
            self.assertEqual(ppu.read_vram(alias), 0x15)

    def test_palette_indices_five_and_fifteen_are_distinct(self):
        ppu = PPU()
        ppu.write_vram(0x3F05, 0x0A)
        ppu.write_vram(0x3F15, 0x0B)
        self.assertEqual(ppu.read_vram(0x3F05), 0x0A)
        self.assertEqual(ppu.read_vram(0x3F15), 0x0B)
        ppu.write_vram(0x3F25, 0x1C)
        self.assertEqual(ppu.read_vram(0x3F05), 0x1C)

    def test_palette_writes_store_six_bits(self):
        ppu = PPU()
        ppu.write_vram(0x3F00, 0xFF)
        self.assertEqual(ppu.read_vram(0x3F00), 0x3F)


class PPUNametableMirroringTests(unittest.TestCase):
    def _assert_table_alias(self, ppu, bases, k, expected_physical):
        for table_base in bases:
            addr = table_base + k
            ppu.write_vram(addr, (addr >> 4) & 0xFF)
        for table_base in bases:
            addr = table_base + k
            self.assertEqual(
                ppu.read_vram(addr),
                ppu.read_vram(expected_physical + k),
                f"table {table_base:#06x} should alias {expected_physical:#06x}",
            )

    def test_horizontal_mirroring(self):
        ppu = PPU(_nrom_mapper(Mirroring.HORIZONTAL))
        k = 0x42
        self._assert_table_alias(ppu, (0x2000, 0x2400), k, 0x2000)
        self._assert_table_alias(ppu, (0x2800, 0x2C00), k, 0x2800)

    def test_vertical_mirroring(self):
        ppu = PPU(_nrom_mapper(Mirroring.VERTICAL))
        k = 0x33
        self._assert_table_alias(ppu, (0x2000, 0x2800), k, 0x2000)
        self._assert_table_alias(ppu, (0x2400, 0x2C00), k, 0x2400)

    def test_four_screen_uses_distinct_tables(self):
        ppu = PPU(_nrom_mapper(Mirroring.FOUR_SCREEN))
        for base in (0x2000, 0x2400, 0x2800, 0x2C00):
            ppu.write_vram(base, base >> 8)
        self.assertEqual(ppu.read_vram(0x2000), 0x20)
        self.assertEqual(ppu.read_vram(0x2400), 0x24)
        self.assertEqual(ppu.read_vram(0x2800), 0x28)
        self.assertEqual(ppu.read_vram(0x2C00), 0x2C)

    def test_no_mapper_defaults_to_horizontal(self):
        ppu = PPU()
        ppu.write_vram(0x2400, 0xAA)
        self.assertEqual(ppu.read_vram(0x2000), 0xAA)

    def test_high_nametable_mirror_band(self):
        ppu = PPU()
        ppu.write_vram(0x2005, 0x11)
        self.assertEqual(ppu.read_vram(0x3005), 0x11)

    def test_unsupported_mirroring_raises_on_nametable_read(self):
        ppu = PPU(_StubMapperUnsupportedMirroring())
        with self.assertRaises(ValueError) as ctx:
            ppu.read_vram(0x2000)
        self.assertIn(repr(_UNSUPPORTED_MIRRORING), str(ctx.exception))

    def test_unsupported_mirroring_raises_on_nametable_write(self):
        ppu = PPU(_StubMapperUnsupportedMirroring())
        with self.assertRaises(ValueError) as ctx:
            ppu.write_vram(0x2000, 1)
        self.assertIn(repr(_UNSUPPORTED_MIRRORING), str(ctx.exception))


class PPUPatternTableTests(unittest.TestCase):
    def test_chr_ram_accepts_ppudata_writes(self):
        mapper = _nrom_mapper(chr_banks=0)
        ppu = PPU(mapper)
        ppu.write_register(6, 0x00)
        ppu.write_register(6, 0x10)
        ppu.write_register(7, 0xDE)
        self.assertEqual(mapper.ppu_read(0x0010), 0xDE)

    def test_chr_rom_ignores_ppudata_writes(self):
        mapper = _nrom_mapper(chr_banks=1)
        mapper._chr = b"\x37" * 0x2000
        ppu = PPU(mapper)
        ppu.write_register(6, 0x00)
        ppu.write_register(6, 0x00)
        ppu.write_register(7, 0x99)
        self.assertEqual(mapper.ppu_read(0x0000), 0x37)

    def test_no_mapper_reads_zero_without_error(self):
        ppu = PPU()
        self.assertEqual(ppu.read_vram(0x0100), 0)
        ppu.write_vram(0x0100, 0x55)
        self.assertEqual(ppu.read_vram(0x0100), 0)


class PPUPeekPurityTests(unittest.TestCase):
    def test_peek_register_does_not_mutate_state(self):
        ppu = PPU()
        ppu.v = 0x2108
        ppu.vblank = True
        ppu.w = 1
        ppu._read_buffer = 0x42
        ppu._data_latch = 0xAB
        snapshot = (
            ppu.v,
            ppu.vblank,
            ppu.w,
            ppu._read_buffer,
            ppu._data_latch,
        )
        ppu.peek_register(2)
        ppu.peek_register(7)
        self.assertEqual(
            (ppu.v, ppu.vblank, ppu.w, ppu._read_buffer, ppu._data_latch),
            snapshot,
        )


class PPUConsoleWiringTests(unittest.TestCase):
    def test_console_ppu_uses_cartridge_mapper_for_pattern_tables(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / "chr_ram.nes"
        path.write_bytes(make_ines(chr_data=b""))
        console = Console(ROM(path))
        console.ppu.write_register(6, 0x00)
        console.ppu.write_register(6, 0x05)
        console.ppu.write_register(7, 0xBE)
        self.assertEqual(console.bus.cartridge.mapper.ppu_read(0x0005), 0xBE)


if __name__ == "__main__":
    unittest.main()
