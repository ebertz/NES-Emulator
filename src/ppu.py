class PPU:
    """Register and timing skeleton for the NES picture processing unit."""

    def __init__(self):
        self.ctrl = 0
        self.mask = 0
        self.oamaddr = 0
        self.oam = bytearray(256)
        self.w = 0
        self.scanline = 0
        self.dot = 0
        self.frame = 0
        self.vblank = False
        self.sprite_zero_hit = False
        self.sprite_overflow = False
        self._data_latch = 0
        self._ppuaddr = 0
        self._ppuaddr_latch = 0

    @property
    def nmi_line(self):
        return self.vblank and bool(self.ctrl & 0x80)

    def read_register(self, reg):
        reg &= 0x07
        if reg == 2:
            value = (
                (int(self.vblank) << 7)
                | (int(self.sprite_zero_hit) << 6)
                | (int(self.sprite_overflow) << 5)
                | (self._data_latch & 0x1F)
            )
            self.vblank = False
            self.w = 0
            self._data_latch = value
            return value
        if reg == 4:
            value = self.oam[self.oamaddr]
            self._data_latch = value
            return value
        if reg == 7:
            return self._data_latch
        return self._data_latch

    def write_register(self, reg, value):
        reg &= 0x07
        value &= 0xFF
        self._data_latch = value
        if reg == 0:
            self.ctrl = value
        elif reg == 1:
            self.mask = value
        elif reg == 3:
            self.oamaddr = value
        elif reg == 4:
            self.oam[self.oamaddr] = value
            self.oamaddr = (self.oamaddr + 1) & 0xFF
        elif reg == 5:
            self.w ^= 1
        elif reg == 6:
            if self.w == 0:
                self._ppuaddr_latch = (value & 0x3F) << 8
            else:
                self._ppuaddr_latch = (
                    (self._ppuaddr_latch & 0xFF00) | value
                )
                self._ppuaddr = self._ppuaddr_latch
            self.w ^= 1
        elif reg == 7:
            self._increment_ppuaddr()

    def write_oam_dma(self, page):
        for offset, value in enumerate(page):
            self.oam[(self.oamaddr + offset) & 0xFF] = value

    def step(self):
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

    def _increment_ppuaddr(self):
        increment = 32 if self.ctrl & 0x04 else 1
        self._ppuaddr = (self._ppuaddr + increment) & 0x3FFF
