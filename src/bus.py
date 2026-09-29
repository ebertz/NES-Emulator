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
        addr &= 0xFFFF
        if addr <= 0x1FFF:
            value = self.ram[addr & 0x7FF]
        elif addr <= 0x3FFF:
            value = self.ppu.read_register(addr & 0x07)
        elif 0x4000 <= addr <= 0x4013 or addr == 0x4015:
            value = self.apu.read_register(addr)
        elif addr == 0x4016:
            value = (self._open_bus & 0xE0) | self.controllers[0].read()
        elif addr == 0x4017:
            value = (self._open_bus & 0xE0) | self.controllers[1].read()
        elif addr >= 0x4020 and self.cartridge is not None:
            value = self.cartridge.mapper.cpu_read(addr)
        else:
            value = self._open_bus
        self._open_bus = value & 0xFF
        return self._open_bus

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

    def write16(self, addr, value):
        addr &= 0xFFFF
        self.write(addr, value)
        self.write((addr + 1) & 0xFFFF, value >> 8)
