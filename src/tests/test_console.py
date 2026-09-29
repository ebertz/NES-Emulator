import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from apu import APU  # noqa: E402
from bus import Bus  # noqa: E402
from controller import Controller  # noqa: E402
from console import Console  # noqa: E402
from cpu import CPU  # noqa: E402
from memory import Memory  # noqa: E402
from ppu import PPU  # noqa: E402
from rom import ROM  # noqa: E402
from test_rom import make_ines  # noqa: E402


def _prg_with_cpu_vectors(*, reset=0x8000, nmi=0x9000, irq=0x9100):
    prg = bytearray(b"\xEA" * 0x4000)
    jmp = bytes([0x4C, reset & 0xFF, (reset >> 8) & 0xFF])
    prg[0:3] = jmp
    prg[nmi - 0x8000 : nmi - 0x8000 + 3] = jmp
    prg[0x3FFA : 0x3FFC] = bytes((nmi & 0xFF, (nmi >> 8) & 0xFF))
    prg[0x3FFC : 0x3FFE] = bytes((reset & 0xFF, (reset >> 8) & 0xFF))
    prg[0x3FFE : 0x4000] = bytes((irq & 0xFF, (irq >> 8) & 0xFF))
    return bytes(prg)


def _console_with_vectors(**vectors):
    directory = tempfile.TemporaryDirectory()
    path = Path(directory.name) / "vectors.nes"
    path.write_bytes(make_ines(prg=_prg_with_cpu_vectors(**vectors)))
    console = Console(ROM(path))
    console.cpu.debug = False
    console._vector_rom_dir = directory
    return console


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

    def test_debug_trace_does_not_read_ppu_status_before_instruction(self):
        self.console = Console()
        self.console.cpu.A = 0xFF
        self.console.ppu.vblank = True
        self.console.bus.write(0x0000, 0x2C)
        self.console.bus.write(0x0001, 0x02)
        self.console.bus.write(0x0002, 0x20)

        self.console.step()

        self.assertEqual(self.console.cpu.N, 1)
        self.assertFalse(self.console.ppu.vblank)

    def test_debug_trace_does_not_shift_controller_before_instruction(self):
        self.console = Console()
        self.console.controllers[0].buttons = 0b00000001
        self.console.bus.write(0x4016, 1)
        self.console.bus.write(0x4016, 0)
        self.console.bus.write(0x0000, 0xAD)
        self.console.bus.write(0x0001, 0x16)
        self.console.bus.write(0x0002, 0x40)

        self.console.step()

        self.assertEqual(self.console.cpu.A & 1, 1)


class ConsoleInterruptIntegrationTests(unittest.TestCase):
    """NMI/IRQ through Console.step(), not direct CPU line manipulation."""

    NMI_HANDLER = 0x9000
    IRQ_HANDLER = 0x9100

    def tearDown(self):
        if hasattr(self, "console"):
            self.console.cpu.logFile.close()
            if hasattr(self.console, "_vector_rom_dir"):
                self.console._vector_rom_dir.cleanup()

    def test_ppu_nmi_line_requires_vblank_and_ctrl_bit7(self):
        ppu = PPU()
        ppu.vblank = True
        ppu.ctrl = 0x00
        self.assertFalse(ppu.nmi_line)
        ppu.ctrl = 0x80
        self.assertTrue(ppu.nmi_line)

    def test_step_wires_ppu_nmi_to_cpu_and_vectors_once_per_frame(self):
        self.console = _console_with_vectors(nmi=self.NMI_HANDLER)
        self.console.reset()
        self.console.bus.write(0x2000, 0x80)

        nmi_entries = 0
        for _ in range(2):
            frame = self.console.ppu.frame
            frame_entries = 0
            while self.console.ppu.frame == frame:
                previous_pc = self.console.cpu.PC
                self.console.step()
                if (
                    self.console.cpu.PC == self.NMI_HANDLER
                    and previous_pc != self.NMI_HANDLER
                ):
                    frame_entries += 1
                    nmi_entries += 1
                    self.assertEqual(self.console.cpu.I, 1)
                    sp = self.console.cpu.SP
                    pcl = self.console.bus.read(sp + 2)
                    pch = self.console.bus.read(sp + 3)
                    return_pc = pcl | (pch << 8)
                    self.assertGreaterEqual(return_pc, 0x8000)
                    self.assertLess(return_pc, 0x8100)
            self.assertEqual(frame_entries, 1)

        self.assertEqual(nmi_entries, 2)

    def test_step_does_not_nmi_when_ppu_ctrl_nmi_disabled(self):
        self.console = _console_with_vectors(nmi=self.NMI_HANDLER)
        self.console.reset()
        self.console.bus.write(0x2000, 0x00)

        self.console.run_frame()

        self.assertEqual(self.console.cpu.PC, 0x8000)

    def test_step_samples_apu_irq_when_interrupts_unmasked(self):
        class IrqAssertingAPU:
            @property
            def irq_line(self):
                return True

            def read_register(self, addr):
                return 0

            def write_register(self, addr, value):
                pass

        self.console = _console_with_vectors(irq=self.IRQ_HANDLER)
        self.console.reset()
        self.console.apu = IrqAssertingAPU()
        self.console.cpu.I = 0

        self.console.step()
        self.console.step()
        self.assertEqual(self.console.cpu.PC, self.IRQ_HANDLER)

    def test_step_ignores_apu_irq_while_cpu_interrupts_masked(self):
        class IrqAssertingAPU:
            @property
            def irq_line(self):
                return True

            def read_register(self, addr):
                return 0

            def write_register(self, addr, value):
                pass

        self.console = _console_with_vectors(irq=self.IRQ_HANDLER)
        self.console.reset()
        self.console.apu = IrqAssertingAPU()
        self.console.cpu.I = 1

        for _ in range(4):
            self.console.step()

        self.assertEqual(self.console.cpu.PC, 0x8000)
        self.assertNotEqual(self.console.cpu.PC, self.IRQ_HANDLER)


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
