class Memory:
	def __init__(self, size):
		self.memory = [0 for i in range(size)]
		self.cartridge = None

	def write(self, address, value):
		if self.cartridge is not None and 0x8000 <= address <= 0xFFFF:
			self.cartridge.cpu_write(address, value)
			return
		self.memory[address] = value

	def read(self, address):
		if self.cartridge is not None and 0x8000 <= address <= 0xFFFF:
			return self.cartridge.cpu_read(address)
		return self.memory[address]

	def read16(self, address):
		if address == 0xFF:
			return self.memory[address] + (self.memory[0] << 8)
		return self.memory[address] + (self.memory[address + 1] << 8)

	def write16(self, address, value):
		if address == 0xFF: 
			self.memory[address] + value & 0xFF
			self.memory[0x00] = (value >> 8) & 0xFF
		self.memory[address] = value & 0xFF
		self.memory[address + 1] = (value >> 8) & 0xFF

	def loadROM(self, rom):
		self.cartridge = rom
		self.memory[0x8000:0x10000] = [
			rom.cpu_read(address) for address in range(0x8000, 0x10000)
		]
		