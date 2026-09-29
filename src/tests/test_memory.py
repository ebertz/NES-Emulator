import os
import sys
import unittest

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from harness import CPUHarness  # noqa: E402
from memory import Memory  # noqa: E402


class MemoryTests(unittest.TestCase):
    def test_peek_and_peek16_match_reads(self):
        memory = Memory(0x10000)
        memory.write(0x0040, 0x34)
        memory.write(0x0041, 0x12)

        self.assertEqual(memory.peek(0x0040), memory.read(0x0040))
        self.assertEqual(memory.peek16(0x0040), memory.read16(0x0040))
        self.assertEqual(memory.peek16(0x0040), 0x1234)

    def test_write16_preserves_zero_page_wrap(self):
        memory = Memory(0x10000)

        memory.write16(0x00FF, 0x1234)

        self.assertEqual(memory.read(0x00FF), 0x34)
        self.assertEqual(memory.read(0x0000), 0x12)
        self.assertEqual(memory.read16(0x00FF), 0x1234)

    def test_16_bit_access_wraps_at_end_of_memory(self):
        memory = Memory(0x10000)

        memory.write16(0xFFFF, 0x5678)

        self.assertEqual(memory.read(0xFFFF), 0x78)
        self.assertEqual(memory.read(0x0000), 0x56)
        self.assertEqual(memory.read16(0xFFFF), 0x5678)
        self.assertEqual(memory.peek16(0xFFFF), 0x5678)

    def test_cpu_harness_executes_through_flat_memory_bus(self):
        harness = CPUHarness()
        self.addCleanup(harness.close)
        harness.cpu.debug = False
        harness.memory.write(0x0000, 0xA9)
        harness.memory.write(0x0001, 0x7F)

        harness.cpu.fetch()

        self.assertIs(harness.cpu.bus, harness.memory)
        self.assertEqual(harness.cpu.A, 0x7F)
        self.assertEqual(harness.cpu.PC, 0x0002)


if __name__ == "__main__":
    unittest.main()
