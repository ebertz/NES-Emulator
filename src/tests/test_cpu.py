import unittest
import os, sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from cpu import *

class InstructionTests(unittest.TestCase):
	def setUp(self):
		self.cpu = CPU()

	def tearDown(self):
		pass


	def test_address_zero_page(self):
		self.cpu.memory.write(0x0010, 5)
		assert self.cpu.address_zero_page(0x10) == 5

	def test_address_zero_page_x(self):
		self.cpu.memory.write(0x0015, 5)
		self.cpu.X = 5
		assert self.cpu.address_zero_page_x(0x10) == 5

	def test_address_zero_page_y(self):
		self.cpu.memory.write(0x0015, 5)
		self.cpu.Y = 5
		assert self.cpu.address_zero_page_y(0x10) == 5

	def test_address_absolute(self):
		self.cpu.memory.write(0x1000, 5)
		assert self.cpu.address_absolute(0x1000) == 5

	def test_address_absolute_x(self):
		self.cpu.memory.write(0x1005, 5)
		self.cpu.X = 5
		assert self.cpu.address_absolute_x(0x1000) == 5	

	def test_address_absolute_y(self):
		self.cpu.memory.write(0x1005, 5)
		self.cpu.Y = 5
		assert self.cpu.address_absolute_y(0x1000) == 5			

	def test_address_indirect(self):
		self.cpu.memory.write(0x1000, 0x00)
		self.cpu.memory.write(0x1001, 0x20)
		self.cpu.memory.write(0x2000, 5)
		assert self.cpu.address_indirect(0x1000) == 5

	def test_address_indirect_x(self):
		self.cpu.memory.write(0x1000, 0x00)
		self.cpu.memory.write(0x1001, 0x20)
		self.cpu.memory.write(0x2000, 5)
		self.cpu.X = 1
		assert self.cpu.address_indirect_x(0x0FFF) == 5
	
	def test_address_indirect_y(self):
		self.cpu.memory.write(0x1000, 0x00)
		self.cpu.memory.write(0x1001, 0x20)
		self.cpu.memory.write(0x2000, 5)
		self.cpu.Y = 1
		assert self.cpu.address_indirect_y(0x0FFF) == 5

	def test_address_implied(self):
		assert self.cpu.address_none(0x1000) == None

	def test_address_accumulator(self):
		self.cpu.A = 5
		assert self.cpu.address_accumulator(0x1000) == 5

	def test_address_immediate(self):
		assert self.cpu.address_immediate(0x10) == 0x10	

	def test_address_relative(self):
		assert self.cpu.address_relative(0x10) == 0x10	

	def test_0x00(self):
		self.cpu.execute(*self.cpu.instructions[0x00])
		assert True


if __name__ == '__main__':
	unittest.main()