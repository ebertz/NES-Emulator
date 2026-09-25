# 6502 addressing modes
# http://www.obelisk.me.uk/6502/addressing.html#ZPX
# http://nesdev.com/NESDoc.pdf

class AddressingMode:
	def __init__(self, size, cpu, crossPageCycles):
		self.cpu = cpu
		self.size = size
		self.crossPageCycles = crossPageCycles

	def read(self, address):
		return 0

	def write(self, address, value):
		pass

	def get(self):
		return self.read(self.cpu.PC + 1)

	def set(self, value):
		return self.write(self.cpu.PC + 1, value)

	def getCrossPageCycles(self, address):
		return 0

	def format(self):
		return ''

class Implied(AddressingMode):
	def __init__(self, cpu):
		super().__init__(1, cpu, 0)

	def read(self, address):
		return None

class Immediate(AddressingMode):
	def __init__(self, cpu):
		super().__init__(2, cpu, 0)

	def read(self, address):
		return self.cpu.memory.read(address)

	def format(self):
		return '#${:02x}'.format(self.get())

class Accumulator(AddressingMode):
	def __init__(self, cpu):
		super().__init__(1, cpu, 0)

	def read(self, address):
		return self.cpu.A

	def write(self, address, value):
		self.cpu.A = value & 0xFF

class ZeroPage(AddressingMode):
	def __init__(self, cpu):
		super().__init__(2, cpu, 0)

	def read(self, address):
		return self.cpu.memory.read(self.cpu.memory.read(address) & 0xFF)

	def write(self, address, value):
		self.cpu.memory.write(self.cpu.memory.read(address) & 0xFF, value)

	def format(self):
		return '${:02x}'.format(self.cpu.memory.read(self.cpu.PC + 1))

class ZeroPageX(AddressingMode):
	def __init__(self, cpu):
		super().__init__(2, cpu, 0)

	def read(self, address):
		return self.cpu.memory.read((self.cpu.memory.read(address) + self.cpu.X) & 0xFF)

	def write(self, address, value):
		self.cpu.memory.write((self.cpu.memory.read(address) + self.cpu.X) & 0xFF, value)

class ZeroPageY(AddressingMode):
	def __init__(self, cpu):
		super().__init__(2, cpu, 0)

	def read(self, address):
		return self.cpu.memory.read((self.cpu.memory.read(address) + self.cpu.Y) & 0xFF)

	def write(self, address, value):
		self.cpu.memory.write((self.cpu.memory.read(address) + self.cpu.Y) & 0xFF, value)

class Absolute(AddressingMode):
	def __init__(self, cpu):
		super().__init__(3, cpu, 0)

	def read(self, address):
		return self.cpu.memory.read(self.cpu.memory.read16(address))

	def write(self, address, value):
		self.cpu.memory.write(self.cpu.memory.read16(address), value)

	def format(self):
		return '${:04x}'.format(self.get())

class AbsoluteX(AddressingMode):
	def __init__(self, cpu):
		super().__init__(3, cpu, 1)

	def read(self, address):
		return self.cpu.memory.read(self.cpu.memory.read16(address) + self.cpu.X)

	def write(self, address, value):
		self.cpu.memory.write(self.cpu.memory.read16(address) + self.cpu.X, value)

	def getCrossPageCycles(self, address):
		a = self.cpu.memory.read16(address)
		if (a + self.cpu.X) >> 8 != a >> 8:
			return 1
		return 0

	def format(self):
		return '${:04x}'.format(self.get())

class AbsoluteY(AddressingMode):
	def __init__(self, cpu):
		super().__init__(3, cpu, 1)

	def read(self, address):
		return self.cpu.memory.read((self.cpu.memory.read16(address) + self.cpu.Y) % 0x10000)

	def write(self, address, value):
		self.cpu.memory.write(self.cpu.memory.read16(address)+ self.cpu.Y, value)

	def getCrossPageCycles(self, address):
		a = self.cpu.memory.read16(address)
		if (a + self.cpu.Y) >> 8 != a >> 8:
			return 1
		return 0

	def format(self):
		return '${:04x}'.format(self.get())

class Indirect(AddressingMode):
	def __init__(self, cpu):
		super().__init__(3, cpu, 0)

	def read(self, address):
		indirect_address = self.cpu.memory.read16(address)
		return self.cpu.memory.read(self.cpu.memory.read16(indirect_address))

	def format(self):
		return '${:04x}'.format(self.get())
# X is added before indirection
class IndirectX(AddressingMode):
	def __init__(self, cpu):
		super().__init__(2, cpu, 0)

	def read(self, address):
		indirect_address = (self.cpu.memory.read(address) + self.cpu.X) % 0x100
		return self.cpu.memory.read(self.cpu.memory.read16(indirect_address))

	def write(self, address, value):
		indirect_address = (self.cpu.memory.read(address) + self.cpu.X) % 0x100
		self.cpu.memory.write(self.cpu.memory.read16(indirect_address), value)

	def format(self):
		return '${:04x}'.format(self.get())
# Y is added after indirection
class IndirectY(AddressingMode):
	def __init__(self, cpu):
		super().__init__(2, cpu, 1)

	def read(self, address):
		indirect_address = self.cpu.memory.read(address) 
		return self.cpu.memory.read((self.cpu.memory.read16(indirect_address) + self.cpu.Y) % 0x10000)

	def write(self, address, value):
		indirect_address = self.cpu.memory.read16(self.cpu.memory.read(address))
		self.cpu.memory.write((indirect_address + self.cpu.Y) % 0x10000, value)

	def getCrossPageCycles(self, address):
		indirect_address = self.cpu.memory.read(address)
		if indirect_address == 0xFF: return 1
		if self.cpu.memory.read(indirect_address) == 0xFF: return 1 
		return 0

	def format(self):
		return '${:04x}'.format(self.get())

class Relative(AddressingMode):
	def __init__(self, cpu):
		super().__init__(0, cpu, 2) #TODO: check branch behavior

	def read(self, address):
		offset = self.cpu.memory.read(address)
		if offset > 0x7F: offset -= 256
		return (self.cpu.PC + offset + 2) & 0xFFFF
	
	def format(self):
		return '${:04x}'.format(self.get())

class JumpAbsolute(AddressingMode):
	def __init__(self, cpu):
		super().__init__(0, cpu, 0)

	def read(self, address):
		return self.cpu.memory.read16(address)

	def format(self):
		return '${:04x}'.format(self.get())

class JumpIndirect(AddressingMode):
	def __init__(self, cpu):
		super().__init__(0, cpu, 0)

	def read(self, address):
		indirect_address = self.cpu.memory.read16(address)
		#simulate a known CPU bug
		if indirect_address & 0xFF == 0xFF:
			return self.cpu.memory.read(indirect_address) + (self.cpu.memory.read(indirect_address & 0xFF00) << 8)

		return self.cpu.memory.read16(indirect_address)

	def format(self):
		return '${:04x}'.format(self.get())

class NONE(AddressingMode):
	def __init__(self, cpu):
		super().__init__(0, cpu, 0)