class Memory:
    def __init__(self, size):
        self.memory = [0 for _ in range(size)]

    def write(self, address, value):
        self.memory[address] = value & 0xFF

    def read(self, address):
        return self.memory[address]

    def peek(self, address):
        return self.memory[address]

    def _next_address(self, address):
        if address == 0x00FF:
            return 0
        return (address + 1) % len(self.memory)

    def read16(self, address):
        return self.read(address) | (self.read(self._next_address(address)) << 8)

    def peek16(self, address):
        return self.peek(address) | (self.peek(self._next_address(address)) << 8)

    def write16(self, address, value):
        self.write(address, value)
        self.write(self._next_address(address), value >> 8)
