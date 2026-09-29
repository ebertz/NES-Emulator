class Bus:
    """CPU-visible NES address bus."""

    def __init__(self, ppu, apu, controllers, cartridge=None):
        self.ppu = ppu
        self.apu = apu
        self.controllers = controllers
        self.cartridge = cartridge
        self.ram = bytearray(0x800)
        self.dma_stall_cycles = 0
        self._open_bus = 0

    def read(self, addr):
        value = self._read(addr, side_effects=True)
        self._open_bus = value & 0xFF
        return self._open_bus

    def peek(self, addr):
        """Inspect the bus without changing device or open-bus state."""
        return self._read(addr, side_effects=False) & 0xFF

    def _read(self, addr, side_effects):
        addr &= 0xFFFF
        if addr <= 0x1FFF:
            value = self.ram[addr & 0x7FF]
        elif addr <= 0x3FFF:
            if side_effects:
                value = self.ppu.read_register(addr & 0x07)
            else:
                value = self.ppu.peek_register(addr & 0x07)
        elif 0x4000 <= addr <= 0x4013 or addr == 0x4015:
            value = self.apu.read_register(addr)
        elif addr == 0x4016:
            controller = self.controllers[0]
            bit = controller.read() if side_effects else controller.peek()
            value = (self._open_bus & 0xE0) | bit
        elif addr == 0x4017:
            controller = self.controllers[1]
            bit = controller.read() if side_effects else controller.peek()
            value = (self._open_bus & 0xE0) | bit
        elif addr >= 0x4020 and self.cartridge is not None:
            value = self.cartridge.mapper.cpu_read(addr)
        else:
            value = self._open_bus
        return value

    def write(self, addr, value):
        addr &= 0xFFFF
        value &= 0xFF
        self._open_bus = value
        if addr <= 0x1FFF:
            self.ram[addr & 0x7FF] = value
        elif addr <= 0x3FFF:
            self.ppu.write_register(addr & 0x07, value)
        elif addr == 0x4014:
            page = bytes(self.read((value << 8) | offset) for offset in range(256))
            self.ppu.write_oam_dma(page)
            self.dma_stall_cycles = 513
        elif addr == 0x4016:
            for controller in self.controllers:
                controller.write(value)
        elif 0x4000 <= addr <= 0x4017 and addr != 0x4016:
            self.apu.write_register(addr, value)
        elif addr >= 0x4020 and self.cartridge is not None:
            self.cartridge.mapper.cpu_write(addr, value)

    def read16(self, addr):
        addr &= 0xFFFF
        next_addr = 0 if addr == 0x00FF else (addr + 1) & 0xFFFF
        return self.read(addr) | (self.read(next_addr) << 8)

    def peek16(self, addr):
        addr &= 0xFFFF
        next_addr = 0 if addr == 0x00FF else (addr + 1) & 0xFFFF
        return self.peek(addr) | (self.peek(next_addr) << 8)

    def write16(self, addr, value):
        addr &= 0xFFFF
        self.write(addr, value)
        self.write((addr + 1) & 0xFFFF, value >> 8)
