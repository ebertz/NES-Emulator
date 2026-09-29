from mapper import Mirroring


class PPU:
    """NES picture processing unit register, memory, and timing state."""

    FRAME_WIDTH = 256
    FRAME_HEIGHT = 240

    def __init__(self, mapper=None):
        self.mapper = mapper
        self.ctrl = 0
        self.mask = 0
        self.oamaddr = 0
        self.oam = bytearray(256)
        self.v = 0
        self.t = 0
        self.x = 0
        self.w = 0
        self.scanline = 0
        self.dot = 0
        self.frame = 0
        self.vblank = False
        self.sprite_zero_hit = False
        self.sprite_overflow = False
        self.nametable_ram = bytearray(0x1000)
        self.palette_ram = bytearray(0x20)
        self.frame_buffer = bytearray(self.FRAME_WIDTH * self.FRAME_HEIGHT)
        self._data_latch = 0
        self._read_buffer = 0
        self._scanline_v = 0

    @property
    def nmi_line(self):
        return self.vblank and bool(self.ctrl & 0x80)

    def read_vram(self, addr):
        """Read the PPU address space without register side effects."""
        addr &= 0x3FFF
        if addr < 0x2000:
            if self.mapper is None:
                return 0
            return self.mapper.ppu_read(addr)
        if addr < 0x3F00:
            return self.nametable_ram[self._nametable_index(addr)]
        return self.palette_ram[self._palette_index(addr)]

    def write_vram(self, addr, value):
        """Write the PPU address space without register side effects."""
        addr &= 0x3FFF
        value &= 0xFF
        if addr < 0x2000:
            if self.mapper is not None:
                self.mapper.ppu_write(addr, value)
            return
        if addr < 0x3F00:
            self.nametable_ram[self._nametable_index(addr)] = value
            return
        self.palette_ram[self._palette_index(addr)] = value & 0x3F

    def read_register(self, reg):
        reg &= 0x07
        if reg == 2:
            value = self.peek_register(reg)
            self.vblank = False
            self.w = 0
            self._data_latch = value
            return value
        if reg == 4:
            value = self.oam[self.oamaddr]
            self._data_latch = value
            return value
        if reg == 7:
            addr = self.v & 0x3FFF
            if addr < 0x3F00:
                value = self._read_buffer
                self._read_buffer = self.read_vram(addr)
            else:
                palette_value = self.read_vram(addr)
                palette_mask = 0x30 if self.mask & 0x01 else 0x3F
                value = (
                    (self._data_latch & 0xC0)
                    | (palette_value & palette_mask)
                )
                self._read_buffer = self.read_vram(addr - 0x1000)
            self._increment_v()
            self._data_latch = value
            return value
        return self._data_latch

    def peek_register(self, reg):
        """Read a CPU-visible register without changing PPU state."""
        reg &= 0x07
        if reg == 2:
            return (
                (int(self.vblank) << 7)
                | (int(self.sprite_zero_hit) << 6)
                | (int(self.sprite_overflow) << 5)
                | (self._data_latch & 0x1F)
            )
        if reg == 4:
            return self.oam[self.oamaddr]
        if reg == 7:
            addr = self.v & 0x3FFF
            if addr < 0x3F00:
                return self._read_buffer
            palette_mask = 0x30 if self.mask & 0x01 else 0x3F
            return (
                (self._data_latch & 0xC0)
                | (self.read_vram(addr) & palette_mask)
            )
        return self._data_latch

    def write_register(self, reg, value):
        reg &= 0x07
        value &= 0xFF
        self._data_latch = value
        if reg == 0:
            self.ctrl = value
            self.t = (self.t & ~0x0C00) | ((value & 0x03) << 10)
        elif reg == 1:
            self.mask = value
        elif reg == 3:
            self.oamaddr = value
        elif reg == 4:
            self.oam[self.oamaddr] = value
            self.oamaddr = (self.oamaddr + 1) & 0xFF
        elif reg == 5:
            if self.w == 0:
                self.t = (self.t & ~0x001F) | (value >> 3)
                self.x = value & 0x07
                self.w = 1
            else:
                self.t = (
                    (self.t & ~0x73E0)
                    | ((value & 0x07) << 12)
                    | ((value & 0xF8) << 2)
                )
                self.w = 0
        elif reg == 6:
            if self.w == 0:
                self.t = (self.t & 0x00FF) | ((value & 0x3F) << 8)
                self.w = 1
            else:
                self.t = (self.t & 0x7F00) | value
                self.v = self.t
                self.w = 0
        elif reg == 7:
            self.write_vram(self.v, value)
            self._increment_v()

    def write_oam_dma(self, page):
        for offset, value in enumerate(page):
            self.oam[(self.oamaddr + offset) & 0xFF] = value

    def step(self):
        if (
            self.scanline == 261
            and self.dot == 339
            and self.frame & 1
            and self.mask & 0x18
        ):
            self.scanline = 0
            self.dot = 0
            self.frame += 1
            return

        self.dot += 1
        if self.dot > 340:
            self.dot = 0
            self.scanline += 1
            if self.scanline > 261:
                self.scanline = 0
                self.frame += 1

        if self.scanline == 241 and self.dot == 1:
            self.vblank = True
        elif self.scanline == 261 and self.dot == 1:
            self.vblank = False
            self.sprite_zero_hit = False
            self.sprite_overflow = False

        if self.scanline < self.FRAME_HEIGHT and self.dot == 1:
            self._scanline_v = (
                (self.v & ~0x041F)
                | (self.t & 0x041F)
            )

        if self.scanline < self.FRAME_HEIGHT and 1 <= self.dot <= 256:
            self._render_background_pixel(self.dot - 1, self.scanline)

        if self.mask & 0x18 and (self.scanline < 240 or self.scanline == 261):
            if self.dot in range(8, 257, 8) or self.dot in (328, 336):
                self._increment_coarse_x()
            if self.dot == 256:
                self._increment_fine_y()
            elif self.dot == 257:
                self._copy_horizontal_scroll()
            elif self.scanline == 261 and 280 <= self.dot <= 304:
                self._copy_vertical_scroll()

    def _render_background_pixel(self, x, y):
        backdrop = self.read_vram(0x3F00)
        buffer_index = y * self.FRAME_WIDTH + x
        if not self.mask & 0x08 or (x < 8 and not self.mask & 0x02):
            self.frame_buffer[buffer_index] = backdrop
            return

        v = self._scanline_v
        scrolled_x = ((v & 0x001F) << 3) + self.x + x
        tile_x = (scrolled_x & 0xFF) >> 3
        fine_x = scrolled_x & 0x07
        nametable_x = ((v >> 10) & 1) ^ ((scrolled_x >> 8) & 1)
        nametable_y = (v >> 11) & 1
        tile_y = (v >> 5) & 0x1F
        fine_y = (v >> 12) & 0x07

        nametable_base = 0x2000 | (nametable_y << 11) | (nametable_x << 10)
        tile = self.read_vram(nametable_base | (tile_y << 5) | tile_x)
        attribute = self.read_vram(
            nametable_base
            | 0x03C0
            | ((tile_y >> 2) << 3)
            | (tile_x >> 2)
        )
        attribute_shift = ((tile_y & 0x02) << 1) | (tile_x & 0x02)
        palette = (attribute >> attribute_shift) & 0x03

        pattern_addr = (
            ((self.ctrl & 0x10) << 8)
            | (tile << 4)
            | fine_y
        )
        bit = 7 - fine_x
        pattern = (
            ((self.read_vram(pattern_addr) >> bit) & 1)
            | (((self.read_vram(pattern_addr + 8) >> bit) & 1) << 1)
        )
        palette_addr = 0x3F00 if pattern == 0 else 0x3F00 + palette * 4 + pattern
        palette_mask = 0x30 if self.mask & 0x01 else 0x3F
        self.frame_buffer[buffer_index] = (
            self.read_vram(palette_addr) & palette_mask
        )

    def _increment_coarse_x(self):
        if (self.v & 0x001F) == 31:
            self.v &= ~0x001F
            self.v ^= 0x0400
        else:
            self.v += 1

    def _increment_fine_y(self):
        if self.v & 0x7000 != 0x7000:
            self.v += 0x1000
            return

        self.v &= ~0x7000
        coarse_y = (self.v & 0x03E0) >> 5
        if coarse_y == 29:
            coarse_y = 0
            self.v ^= 0x0800
        elif coarse_y == 31:
            coarse_y = 0
        else:
            coarse_y += 1
        self.v = (self.v & ~0x03E0) | (coarse_y << 5)

    def _copy_horizontal_scroll(self):
        self.v = (self.v & ~0x041F) | (self.t & 0x041F)

    def _copy_vertical_scroll(self):
        self.v = (self.v & ~0x7BE0) | (self.t & 0x7BE0)

    def _increment_v(self):
        increment = 32 if self.ctrl & 0x04 else 1
        self.v = (self.v + increment) & 0x7FFF

    def _nametable_index(self, addr):
        mirrored = (addr - 0x2000) & 0x0FFF
        table = mirrored >> 10
        offset = mirrored & 0x03FF
        mirroring = (
            Mirroring.HORIZONTAL
            if self.mapper is None
            else self.mapper.mirroring
        )
        if mirroring == Mirroring.HORIZONTAL:
            return (table >> 1) * 0x400 + offset
        if mirroring == Mirroring.VERTICAL:
            return (table & 1) * 0x400 + offset
        if mirroring == Mirroring.FOUR_SCREEN:
            return table * 0x400 + offset
        raise ValueError(f"Unsupported nametable mirroring: {mirroring!r}")

    @staticmethod
    def _palette_index(addr):
        index = addr & 0x1F
        if index in (0x10, 0x14, 0x18, 0x1C):
            return index & 0x0F
        return index
