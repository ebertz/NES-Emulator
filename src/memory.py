class Memory:
	def __init__(self, size):
		self.memory = [0 for i in range(size)]

	def write(self, address, value):
		self.memory[address] = value

	def read(self, address):
		return self.memory[address]

	def peek(self, address):
		return self.memory[address]

	def read16(self, address):
		if address == 0xFF:
			return self.memory[address] + (self.memory[0] << 8)
		return self.memory[address] + (self.memory[address + 1] << 8)

	def peek16(self, address):
		if address == 0xFF:
			return self.memory[address] + (self.memory[0] << 8)
		return self.memory[address] + (self.memory[address + 1] << 8)

	def write16(self, address, value):
		self.memory[address] = value & 0xFF
		next_address = 0 if address == 0xFF else address + 1
		self.memory[next_address] = (value >> 8) & 0xFF