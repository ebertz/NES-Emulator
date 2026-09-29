class APU:
    """Register-level APU placeholder until audio emulation is implemented."""

    def __init__(self):
        self._registers = bytearray(0x20)

    def read_register(self, addr):
        return 0

    def write_register(self, addr, value):
        self._registers[addr & 0x1F] = value & 0xFF

    @property
    def irq_line(self):
        return False
