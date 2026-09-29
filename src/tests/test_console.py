import os
import sys
import unittest

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from apu import APU  # noqa: E402
from bus import Bus  # noqa: E402
from controller import Controller  # noqa: E402
from console import Console  # noqa: E402
from cpu import CPU  # noqa: E402
from memory import Memory  # noqa: E402
from ppu import PPU  # noqa: E402


class BusTests(unittest.TestCase):
    def setUp(self):
        self.ppu = PPU()
        self.controllers = (Controller(), Controller())
        self.bus = Bus(self.ppu, APU(), self.controllers)

    def test_ram_and_ppu_registers_are_mirrored(self):
        self.bus.write(0x0003, 0xA5)
        self.assertEqual(self.bus.read(0x1803), 0xA5)

        self.bus.write(0x3FF8, 0x80)
        self.assertEqual(self.ppu.ctrl, 0x80)

    def test_oam_dma_copies_full_bus_page_and_requests_stall(self):
        for offset in range(256):
            self.bus.write(0x0200 + offset, offset)
        self.bus.write(0x2003, 0x40)

        self.bus.write(0x4014, 0x02)

        self.assertEqual(self.ppu.oam[0x40], 0)
        self.assertEqual(self.ppu.oam[0x3F], 0xFF)
        self.assertEqual(self.bus.dma_stall_cycles, 513)

    def test_controllers_shift_buttons_then_return_one(self):
        self.controllers[0].buttons = 0b10100101
        self.bus.write(0x4016, 1)
        self.bus.write(0x4016, 0)

        bits = [self.bus.read(0x4016) & 1 for _ in range(10)]

        self.assertEqual(bits, [1, 0, 1, 0, 0, 1, 0, 1, 1, 1])


class ConsoleTests(unittest.TestCase):
    def tearDown(self):
        if hasattr(self, "console"):
            self.console.cpu.logFile.close()

    def test_step_clocks_three_ppu_dots_per_cpu_cycle(self):
        self.console = Console()
        self.console.cpu.debug = False
        self.console.bus.write(0, 0xEA)

        cycles = self.console.step()

        self.assertEqual(cycles, 2)
        self.assertEqual(self.console.ppu.dot, 6)

    def test_dma_stall_is_consumed_by_scheduler(self):
        self.console = Console()
        self.console.cpu.debug = False
        self.console.bus.write(0x4014, 0)

        cycles = self.console.step()

        self.assertEqual(cycles, 513)
        self.assertEqual(self.console.bus.dma_stall_cycles, 0)
        self.assertEqual(
            self.console.ppu.scanline * 341 + self.console.ppu.dot,
            513 * 3,
        )


class InterruptTests(unittest.TestCase):
    def setUp(self):
        self.memory = Memory(0x10000)
        self.cpu = CPU(self.memory)
        self.cpu.debug = False

    def tearDown(self):
        self.cpu.logFile.close()

    def test_nmi_is_edge_latched_and_vectors(self):
        self.memory.write16(0xFFFA, 0x3456)
        self.cpu.PC = 0x1234
        self.cpu.set_nmi_line(True)
        self.cpu.set_nmi_line(True)

        serviced = self.cpu.service_interrupts()

        self.assertTrue(serviced)
        self.assertEqual(self.cpu.PC, 0x3456)
        self.assertFalse(self.cpu.service_interrupts())

    def test_masked_irq_waits_until_interrupts_are_enabled(self):
        self.memory.write16(0xFFFE, 0x4567)
        self.cpu.set_irq_line(True)
        self.assertFalse(self.cpu.service_interrupts())

        self.cpu.I = 0

        self.assertTrue(self.cpu.service_interrupts())
        self.assertEqual(self.cpu.PC, 0x4567)


if __name__ == "__main__":
    unittest.main()
