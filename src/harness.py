from cpu import CPU
from memory import Memory


class CPUHarness:
    """Standalone 6502 harness backed by flat memory instead of the NES bus."""

    def __init__(self, memory_size=0x10000):
        self.memory = Memory(memory_size)
        self.cpu = CPU(self.memory)

    def close(self):
        self.cpu.logFile.close()
