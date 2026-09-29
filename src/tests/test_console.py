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

    def test_ram_mirrors_across_cpu_ranges(self):
        for base in (0x0000, 0x0800, 0x1000, 0x1800):
            value = (base >> 8) ^ 0x5A
            self.bus.write(base + 0x003, value)
            for mirror in (0x0003, 0x0803, 0x1003, 0x1803):
                self.assertEqual(
                    self.bus.read(mirror),
                    value,
                    f"write ${base + 0x003:04X}, read ${mirror:04X}",
                )

    def test_ram_mirror_write_at_high_page_reads_back_at_low_page(self):
        self.bus.write(0x17FF, 0x3C)
        self.assertEqual(self.bus.read(0x07FF), 0x3C)
        self.assertEqual(self.bus.read(0x0FFF), 0x3C)

    def test_ppu_registers_are_mirrored_every_eight_bytes(self):
        self.bus.write(0x2000, 0x80)
        self.assertEqual(self.ppu.ctrl, 0x80)

        self.bus.write(0x3FF8, 0x55)
        self.assertEqual(self.ppu.ctrl, 0x55)

    def test_ppu_status_vblank_bit_clears_on_second_read(self):
        self.ppu.vblank = True
        first = self.bus.read(0x2002)
        second = self.bus.read(0x2002)

        self.assertEqual(first & 0x80, 0x80)
        self.assertEqual(second & 0x80, 0)
        self.assertFalse(self.ppu.vblank)

    def test_ppu_status_read_resets_write_toggle_for_ppuaddr(self):
        self.bus.write(0x2005, 0x00)
        self.assertEqual(self.ppu.w, 1)

        self.bus.read(0x2002)

        self.bus.write(0x2006, 0x12)
        self.bus.write(0x2006, 0x34)
        self.assertEqual(self.ppu.v, 0x1234)

    def test_oamdata_write_auto_increments_oamaddr(self):
        self.bus.write(0x2003, 0x10)
        for value in range(4):
            self.bus.write(0x2004, 0xA0 + value)

        self.assertEqual(self.ppu.oam[0x10:0x14], bytes([0xA0, 0xA1, 0xA2, 0xA3]))
        self.assertEqual(self.ppu.oamaddr, 0x14)

    def test_oam_dma_copies_full_bus_page_and_requests_stall(self):
        for offset in range(256):
            self.bus.write(0x0200 + offset, offset)
        self.bus.write(0x2003, 0x40)

        self.bus.write(0x4014, 0x02)

        self.assertEqual(self.ppu.oam[0x40], 0)
        self.assertEqual(self.ppu.oam[0x3F], 0xFF)
        self.assertEqual(self.bus.dma_stall_cycles, 513)

    def test_oam_dma_from_cartridge_page(self):
        prg = bytearray(b"\x00" * 0x4000)
        for index in range(256):
            prg[index] = (0xC0 + index) & 0xFF
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / "dma.nes"
        path.write_bytes(make_ines(prg=bytes(prg)))
        bus = Bus(PPU(), APU(), (Controller(), Controller()), ROM(path))
        bus.write(0x2003, 0x00)

        bus.write(0x4014, 0x80)

        expected = bytes((0xC0 + index) & 0xFF for index in range(256))
        self.assertEqual(bytes(bus.ppu.oam), expected)
        self.assertEqual(bus.dma_stall_cycles, 513)

    def test_apu_registers_accept_writes_and_status_reads_zero(self):
        apu = APU()
        bus = Bus(PPU(), apu, (Controller(), Controller()))
        for addr in range(0x4000, 0x4014):
            bus.write(addr, addr & 0xFF)
            self.assertEqual(apu._registers[addr & 0x1F], addr & 0xFF)
        bus.write(0x4015, 0xEE)
        bus.write(0x4017, 0x77)
        self.assertEqual(apu._registers[0x15], 0xEE)
        self.assertEqual(apu._registers[0x17], 0x77)
        self.assertEqual(bus.read(0x4015), 0)

    def test_controllers_shift_buttons_then_return_one(self):
        self.controllers[0].buttons = 0b10100101
        self.bus.write(0x4016, 1)
        self.bus.write(0x4016, 0)

        bits = [self.bus.read(0x4016) & 1 for _ in range(10)]

        self.assertEqual(bits, [1, 0, 1, 0, 0, 1, 0, 1, 1, 1])

    def test_controller_reads_preserve_open_bus_upper_bits(self):
        self.controllers[0].buttons = 0b00000001
        self.bus.write(0x4016, 1)
        self.bus.write(0x4016, 0)
        self.bus.write(0x0100, 0xA5)

        value = self.bus.read(0x4016)

        self.assertEqual(value, 0xA1)

    def test_strobe_on_4016_applies_to_both_controller_ports(self):
        self.controllers[0].buttons = 0b00000001
        self.controllers[1].buttons = 0b00000010
        self.bus.write(0x4016, 1)
        self.bus.write(0x4016, 0)

        port_one = self.bus.read(0x4016) & 1
        port_two = self.bus.read(0x4017) & 1

        self.assertEqual(port_one, 1)
        self.assertEqual(port_two, 0)

    def test_4017_reads_player_two_controller_not_player_one(self):
        self.controllers[0].buttons = 0b00000001
        self.controllers[1].buttons = 0b00000010
        self.bus.write(0x4016, 1)
        self.bus.write(0x4016, 0)

        player_one_bits = [self.bus.read(0x4016) & 1 for _ in range(8)]
        player_two_bits = [self.bus.read(0x4017) & 1 for _ in range(8)]

        self.assertEqual(player_one_bits, [1, 0, 0, 0, 0, 0, 0, 0])
        self.assertEqual(player_two_bits, [0, 1, 0, 0, 0, 0, 0, 0])

    def test_controller_latches_buttons_on_strobe_falling_edge(self):
        # Regression N4T3-REV-CTRL-STROBE-UNPINNED: reload must use buttons at strobe 0,
        # not the snapshot taken when strobe was raised.
        self.controllers[0].buttons = 0b00000001
        self.bus.write(0x4016, 1)
        self.controllers[0].buttons = 0b00000010
        self.bus.write(0x4016, 0)

        bits = [self.bus.read(0x4016) & 1 for _ in range(8)]

        self.assertEqual(bits, [0, 1, 0, 0, 0, 0, 0, 0])

    def test_controller_while_strobe_high_returns_live_button_a_bit(self):
        self.bus.write(0x4016, 1)
        self.controllers[0].buttons = 0b00000001
        self.assertEqual(self.bus.read(0x4016) & 1, 1)

        self.controllers[0].buttons = 0b00000000
        self.assertEqual(self.bus.read(0x4016) & 1, 0)
        self.assertEqual(self.bus.read(0x4016) & 1, 0)

    def test_cartridge_space_without_cartridge_uses_open_bus(self):
        # Regression N4T3-REV-1: guard `cartridge is not None` must stay on _read/_write.
        self.bus.write(0x8000, 0x5A)
        self.assertEqual(self.bus.read(0x8000), 0x5A)

        self.bus.write(0x0100, 0x77)
        self.assertEqual(self.bus.read(0xFFFF), 0x77)

    def test_cartridge_space_write_without_cartridge_does_not_raise(self):
        self.bus.write(0x8000, 0x99)

    def test_cartridge_space_write_reaches_mapper_cpu_write(self):
        prg = b"\xA5" + b"\0" * (0x4000 - 1)
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / "nrom.nes"
        path.write_bytes(make_ines(prg=prg))
        cartridge = ROM(path)
        bus = Bus(PPU(), APU(), (Controller(), Controller()), cartridge)
        writes = []
        original_write = cartridge.mapper.cpu_write

        def capture_cpu_write(addr, value):
            writes.append((addr, value))
            original_write(addr, value)

        cartridge.mapper.cpu_write = capture_cpu_write

        bus.write(0x8000, 0x55)

        self.assertEqual(writes, [(0x8000, 0x55)])

    def test_wrapped_cpu_address_hits_ram_not_cartridge(self):
        # Regression N4T3-REV-ADDR-MASK: _read/_write must mask to 16 bits before decode.
        # Without it, 0x10010 routes to mapper.cpu_read and raises on NROM.
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / "nrom.nes"
        path.write_bytes(make_ines())
        bus = Bus(PPU(), APU(), (Controller(), Controller()), ROM(path))
        bus.write(0x0010, 0xAB)

        self.assertEqual(bus.read(0x10010), 0xAB)

        bus.write(0x10010, 0xCD)
        self.assertEqual(bus.read(0x0010), 0xCD)
        self.assertEqual(bus.read(0x1010), 0xCD)

    def test_disabled_io_read_with_cartridge_uses_open_bus(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / "nrom.nes"
        path.write_bytes(make_ines())
        bus = Bus(PPU(), APU(), (Controller(), Controller()), ROM(path))
        bus.write(0x0000, 0xA5)

        self.assertEqual(bus.read(0x4018), 0xA5)

    def test_disabled_io_write_with_cartridge_is_ignored(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / "nrom.nes"
        path.write_bytes(make_ines())
        bus = Bus(PPU(), APU(), (Controller(), Controller()), ROM(path))

        bus.write(0x401F, 0x3C)

        self.assertEqual(bus.read(0x4018), 0x3C)


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

    def test_step_accumulates_ppu_dots_as_three_times_returned_cycles(self):
        self.console = Console()
        self.console.cpu.debug = False
        self.console.bus.write(0, 0xEA)
        self.console.bus.write(1, 0xEA)

        total_cycles = 0
        for _ in range(5):
            total_cycles += self.console.step()

        self.assertEqual(
            self.console.ppu.scanline * 341 + self.console.ppu.dot,
            total_cycles * 3,
        )

    def test_vblank_begins_after_one_full_pre_vblank_frame(self):
        ppu = PPU()
        target_dots = 241 * 341 + 1
        for _ in range(target_dots - 1):
            ppu.step()
        self.assertFalse(ppu.vblank)
        ppu.step()
        self.assertTrue(ppu.vblank)

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

    def test_dma_stall_adds_one_cycle_when_dma_starts_on_odd_cpu_cycle(self):
        # Regression: hardware adds +1 stall when $4014 is serviced on an odd cycle.
        self.console = Console()
        self.console.cpu.debug = False
        self.console.cpu.cycles = 1
        self.console.bus.write(0x4014, 0)

        cycles = self.console.step()

        self.assertEqual(cycles, 514)
        self.assertEqual(self.console.bus.dma_stall_cycles, 0)
        self.assertEqual(
            self.console.ppu.scanline * 341 + self.console.ppu.dot,
            514 * 3,
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
            sp_at_frame_start = self.console.cpu.SP
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
            self.assertEqual(
                self.console.cpu.SP,
                sp_at_frame_start - 3 * frame_entries,
            )

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
        self._rom_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self._rom_dir.cleanup)
        prg = bytearray(b"\x00" * 0x4000)
        prg[0x3FFA : 0x3FFC] = bytes((0x56, 0x34))
        prg[0x3FFE : 0x4000] = bytes((0x67, 0x45))
        path = Path(self._rom_dir.name) / "interrupt-vectors.nes"
        path.write_bytes(make_ines(prg=bytes(prg)))
        self.bus = Bus(
            PPU(),
            APU(),
            (Controller(), Controller()),
            ROM(path),
        )
        self.cpu = CPU(self.bus)
        self.cpu.debug = False

    def tearDown(self):
        self.cpu.logFile.close()

    def test_fixture_uses_system_bus(self):
        self.assertIsInstance(self.cpu.bus, Bus)

    def test_nmi_is_edge_latched_and_vectors(self):
        self.cpu.PC = 0x1234
        self.cpu.set_nmi_line(True)
        self.cpu.set_nmi_line(True)

        serviced = self.cpu.service_interrupts()

        self.assertTrue(serviced)
        self.assertEqual(self.cpu.PC, 0x3456)
        self.assertFalse(self.cpu.service_interrupts())

    def test_nmi_does_not_retrigger_while_line_stays_high(self):
        # Regression: level-triggered NMI would set pending every sample while high.
        self.cpu.PC = 0x1234
        self.cpu.set_nmi_line(True)
        self.assertTrue(self.cpu.service_interrupts())
        self.cpu.set_nmi_line(True)
        self.assertFalse(self.cpu.service_interrupts())

    def test_nmi_rearms_after_line_falls_then_rises(self):
        self.cpu.PC = 0x1234
        self.cpu.set_nmi_line(True)
        self.assertTrue(self.cpu.service_interrupts())
        self.cpu.set_nmi_line(False)
        self.cpu.set_nmi_line(True)
        self.assertTrue(self.cpu.service_interrupts())
        self.assertEqual(self.cpu.PC, 0x3456)

    def test_masked_irq_waits_until_interrupts_are_enabled(self):
        self.cpu.set_irq_line(True)
        self.assertFalse(self.cpu.service_interrupts())

        self.cpu.I = 0

        self.assertTrue(self.cpu.service_interrupts())
        self.assertEqual(self.cpu.PC, 0x4567)

    def _pushed_status_after_interrupt(self):
        return self.bus.read(self.cpu.SP + 1)

    def test_nmi_stack_frame_clears_b_when_b_was_set(self):
        # Regression N4T3-R1: NMI must not push B=1 (would look like a BRK frame).
        self.cpu.PC = 0x1234
        self.cpu.execute(*self.cpu.instructions[0x00])
        self.assertEqual(self.cpu.B, 1)

        self.cpu.set_nmi_line(True)
        self.assertTrue(self.cpu.service_interrupts())

        pushed_p = self._pushed_status_after_interrupt()
        self.assertEqual(pushed_p & 0x10, 0)
        self.assertEqual(pushed_p & 0x20, 0x20)

    def test_irq_stack_frame_clears_b_when_b_was_set(self):
        # Regression N4T3-R1: IRQ must not push B=1 (would look like a BRK frame).
        self.cpu.PC = 0x1234
        self.cpu.execute(*self.cpu.instructions[0x00])
        self.assertEqual(self.cpu.B, 1)
        self.cpu.I = 0

        self.cpu.set_irq_line(True)
        self.assertTrue(self.cpu.service_interrupts())

        pushed_p = self._pushed_status_after_interrupt()
        self.assertEqual(pushed_p & 0x10, 0)
        self.assertEqual(pushed_p & 0x20, 0x20)


if __name__ == "__main__":
    unittest.main()
