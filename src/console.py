from apu import APU
from bus import Bus
from controller import Controller
from cpu import CPU
from ppu import PPU


class Console:
    """Owns component wiring and advances the console clock."""

    def __init__(self, cartridge=None):
        self.ppu = PPU()
        self.apu = APU()
        self.controllers = (Controller(), Controller())
        self.bus = Bus(self.ppu, self.apu, self.controllers, cartridge)
        self.cpu = CPU(self.bus)

    def reset(self):
        self.cpu.PC = self.bus.read16(0xFFFC)
        self.cpu.I = 1

    def step(self):
        cycles_before = self.cpu.cycles
        if self.bus.dma_stall_cycles:
            stall = self.bus.dma_stall_cycles
            if (cycles_before // 3) & 1:
                stall += 1
            self.bus.dma_stall_cycles = 0
            self.cpu.cycles += stall * 3
        elif not self.cpu.service_interrupts():
            self.cpu.fetch()

        dots = self.cpu.cycles - cycles_before
        for _ in range(dots):
            self.ppu.step()

        self.cpu.set_nmi_line(self.ppu.nmi_line)
        self.cpu.set_irq_line(self.apu.irq_line)
        return dots // 3

    def run_frame(self):
        frame = self.ppu.frame
        while self.ppu.frame == frame:
            self.step()
