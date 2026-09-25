import unittest
import os, sys
from io import StringIO
from pathlib import Path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from cpu import *

TEST_DIR = Path(__file__).resolve().parent
NESTEST_ROM = TEST_DIR / 'testROMs' / 'nestest.nes'
NESTEST_LOG = TEST_DIR.parent / 'nestest.log.txt'

class AddressingModeTests(unittest.TestCase):
	def setUp(self):
		self.cpu = CPU()

	def test_address_zero_page_read(self):
		self.cpu.memory.write(0x10, 5)
		self.cpu.memory.write(0x1000, 0x10)
		assert self.cpu.zeroPage.read(0x1000) == 5

	def test_address_zero_page_x_read(self):
		self.cpu.memory.write(0x15, 5)
		self.cpu.memory.write(0x1000, 0x10)
		self.cpu.X = 5
		assert self.cpu.zeroPageX.read(0x1000) == 5

	def test_address_zero_page_y_read(self):
		self.cpu.memory.write(0x15, 5)
		self.cpu.memory.write(0x1000, 0x10)
		self.cpu.Y = 5
		assert self.cpu.zeroPageY.read(0x1000) == 5

	def test_address_absolute_read(self):
		self.cpu.memory.write16(0x1000, 0x2000)
		self.cpu.memory.write(0x2000, 5)
		assert self.cpu.absolute.read(0x1000) == 5

	def test_address_absolute_x_read(self):
		self.cpu.memory.write16(0x1000, 0x2000)
		self.cpu.memory.write(0x2010, 0x5)
		self.cpu.X = 0x10
		assert self.cpu.absoluteX.read(0x1000) == 0x5	

	def test_address_absolute_y_read(self):
		self.cpu.memory.write(0x1000, 0x2000)
		self.cpu.memory.write(0x2010, 0x5)
		self.cpu.Y = 0x10
		assert self.cpu.absoluteY.read(0x1000) == 0x5			

	def test_address_indirect_read(self):
		self.cpu.memory.write16(0x1000, 0x2000)
		self.cpu.memory.write16(0x2000, 0x3000)
		self.cpu.memory.write(0x3000, 0x5)
		assert self.cpu.indirect.read(0x1000) == 0x5

	def test_address_indirect_x_read(self):
		self.cpu.memory.write(0x1000, 0x20)
		self.cpu.memory.write16(0x30, 0x3000)
		self.cpu.memory.write(0x3000, 0x5)
		self.cpu.X = 0x10
		assert self.cpu.indirectX.read(0x1000) == 0x5
	
	def test_address_indirect_y_read(self):
		self.cpu.memory.write(0x1000, 0x20)
		self.cpu.memory.write16(0x20, 0x3000)
		self.cpu.memory.write(0x3010, 0x5)
		self.cpu.Y = 0x10
		assert self.cpu.indirectY.read(0x1000) == 0x5

	def test_address_implied_read(self):
		assert self.cpu.implied.read(0x1000) == None

	def test_address_accumulator_read(self):
		self.cpu.A = 5
		assert self.cpu.accumulator.read(0x1000) == 5

	def test_address_immediate_read(self):
		self.cpu.memory.write(0x1000, 0x10)
		assert self.cpu.immediate.read(0x1000) == 0x10	

	def test_address_relative_read(self):
		self.cpu.PC = 0x1000
		self.cpu.memory.write(0x1001, 0x10)
		assert self.cpu.relative.read(0x1001) == 0x1012

# !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!

	def test_address_zero_page_write(self):
		self.cpu.memory.write(0x1000, 0x10)
		self.cpu.zeroPage.write(0x1000, 0x5)
		assert self.cpu.memory.read(0x10) == 0x5

	def test_address_zero_page_x_write(self):
		self.cpu.memory.write(0x1000, 0xFF)
		self.cpu.X = 0x1
		self.cpu.zeroPageX.write(0x1000, 0x5)
		assert self.cpu.memory.read(0x00) == 0x5

	def test_address_zero_page_y_write(self):
		self.cpu.memory.write(0x1000, 0xFF)
		self.cpu.Y = 0x1
		self.cpu.zeroPageY.write(0x1000, 0x5)
		assert self.cpu.memory.read(0x00) == 0x5

	def test_address_absolute_write(self):
		self.cpu.memory.write16(0x1000, 0x2000)
		self.cpu.absolute.write(0x1000, 0x5)
		assert self.cpu.memory.read(0x2000) == 0x5

	def test_address_absolute_x_write(self):
		self.cpu.memory.write16(0x1000, 0x2000)
		self.cpu.X = 0x10
		self.cpu.absoluteX.write(0x1000, 0x5)
		assert self.cpu.memory.read(0x2010) == 0x5

	def test_address_absolute_y_write(self):
		self.cpu.memory.write16(0x1000, 0x2000)
		self.cpu.Y = 0x10
		self.cpu.absoluteY.write(0x1000, 0x5)
		assert self.cpu.memory.read(0x2010) == 0x5			

	def test_address_indirect_x_write(self):
		self.cpu.memory.write(0x1000, 0x20)
		self.cpu.X = 0x10
		self.cpu.memory.write16(0x30, 0x3000)
		self.cpu.indirectX.write(0x1000, 0x5)
		assert self.cpu.memory.read(0x3000) == 0x5

	def test_address_indirect_y_write(self):
		self.cpu.memory.write(0x1000, 0x20)
		self.cpu.memory.write16(0x20, 0x3000)
		self.cpu.Y = 0x10
		self.cpu.indirectY.write(0x1000, 0x5)
		assert self.cpu.memory.read(0x3010) == 0x5

	def test_address_accumulator_write(self):
		self.cpu.accumulator.write(0, 0xFF)
		assert self.cpu.A == 0xFF

	def test_address_absolute_x_crosspage(self):
		self.cpu.memory.write16(0x1000, 0x10FF)
		self.cpu.memory.write(0x1100, 0x5)
		self.cpu.X = 0x1
		assert self.cpu.absoluteX.read(0x1000) == 0x5
		assert self.cpu.absoluteX.getCrossPageCycles(0x1000) == 1

	def test_address_absolute_x_no_crosspage(self):
		self.cpu.memory.write16(0x1000, 0x2000)
		self.cpu.memory.write(0x2001, 0x5)
		self.cpu.X = 0x1
		assert self.cpu.absoluteX.read(0x1000) == 0x5
		assert self.cpu.absoluteX.getCrossPageCycles(0x1000) == 0

	def test_address_absolute_y_crosspage(self):
		self.cpu.memory.write16(0x1000, 0x10FF)
		self.cpu.memory.write(0x1100, 0x5)
		self.cpu.Y = 0x1
		assert self.cpu.absoluteY.read(0x1000) == 0x5
		assert self.cpu.absoluteY.getCrossPageCycles(0x1000) == 1

	def test_address_absolute_y_no_crosspage(self):
		self.cpu.memory.write16(0x1000, 0x2000)
		self.cpu.memory.write(0x2001, 0x5)
		self.cpu.Y = 0x1
		assert self.cpu.absoluteY.read(0x1000) == 0x5
		assert self.cpu.absoluteY.getCrossPageCycles(0x1000) == 0

	def test_address_indirect_y_crosspage(self):
		self.cpu.memory.write(0x1000, 0x20)
		self.cpu.memory.write16(0x20, 0x2FFF)
		self.cpu.memory.write(0x3000, 0x5)
		self.cpu.Y = 0x1
		assert self.cpu.indirectY.read(0x1000) == 0x5
		assert self.cpu.indirectY.getCrossPageCycles(0x1000) == 1

	def test_address_indirect_y_no_crosspage(self):
		self.cpu.memory.write(0x1000, 0x20)
		self.cpu.memory.write16(0x20, 0x3000)
		self.cpu.memory.write(0x3010, 0x5)
		self.cpu.Y = 0x10
		assert self.cpu.indirectY.read(0x1000) == 0x5
		assert self.cpu.indirectY.getCrossPageCycles(0x1000) == 0

class InstructionTests(unittest.TestCase):
	def setUp(self):
		self.cpu = CPU()

	def tearDown(self):
		pass

	def test_memory_read16(self):
		self.cpu.memory.write(0x1000, 0x34)
		self.cpu.memory.write(0x1001, 0x12)
		assert self.cpu.memory.read16(0x1000) == 0x1234

	def test_memory_write16(self):
		self.cpu.memory.write16(0x1000, 0x1234)
		assert self.cpu.memory.read(0x1000) == 0x34
		assert self.cpu.memory.read(0x1001) == 0x12


	def test_adc(self): #0x69
		self.cpu.A = 0xFF
		self.cpu.PC = 0x1000
		self.cpu.memory.write(0x1001, 1)
		self.cpu.execute(*self.cpu.instructions[0x69])
		assert self.cpu.A == 0x00
		assert self.cpu.C == 1
		assert self.cpu.N == 0
		assert self.cpu.Z == 1
		assert self.cpu.PC == 0x1002

	def test_branch_fail(self):
		initCycles = self.cpu.cycles
		self.cpu.PC=0x1000
		self.cpu.C = 1
		self.cpu.memory.write(0x1001, 0x10)
		self.cpu.execute(*self.cpu.instructions[0x90])
		assert self.cpu.PC == 0x1002
		assert self.cpu.cycles == initCycles + 2

	
	def test_branch_successful(self):
		initCycles = self.cpu.cycles
		self.cpu.PC=0x1000
		self.cpu.C = 0
		self.cpu.memory.write(0x1001, 0x10)
		self.cpu.execute(*self.cpu.instructions[0x90])
		assert self.cpu.PC == 0x1012
		assert self.cpu.cycles == initCycles + 3


	def test_branch_page_cross(self):
		initCycles = self.cpu.cycles
		self.cpu.PC= 0x10F0
		self.cpu.C = 0
		self.cpu.memory.write(0x10F1, 0x10)
		self.cpu.execute(*self.cpu.instructions[0x90])
		assert self.cpu.PC == 0x1102
		assert self.cpu.cycles == initCycles + 4

	def test_brk(self):
		self.cpu.PC = 0x1000
		self.cpu.memory.write16(0xFFFE, 0x2000)
		self.cpu.execute(*self.cpu.instructions[0x00])
		assert self.cpu.PC == 0x2000

	def test_bit_test(self):
		print('TODO: test_bit')
		self.cpu.PC = 0x1000
		self.cpu.memory.write(0x1001, 0x50)
		self.cpu.memory.write(0x50, 0xFF)
		self.cpu.execute(*self.cpu.instructions[0x24])
		assert self.cpu.V == 1
		assert self.cpu.N == 1
		assert self.cpu.Z == 1

	def test_clc(self):
		initCycles = self.cpu.cycles
		self.cpu.C = 1
		self.cpu.PC = 0x1000
		self.cpu.execute(*self.cpu.instructions[0x18])
		assert self.cpu.C == 0
		assert self.cpu.cycles == initCycles + 2
		assert self.cpu.PC == 0x1001

	def test_cld(self):
		initCycles = self.cpu.cycles
		self.cpu.D = 1
		self.cpu.PC = 0x1000
		self.cpu.execute(*self.cpu.instructions[0xd8])
		assert self.cpu.D == 0
		assert self.cpu.cycles == initCycles + 2
		assert self.cpu.PC == 0x1001

	def test_cli(self):
		initCycles = self.cpu.cycles
		self.cpu.I = 1
		self.cpu.PC = 0x1000
		self.cpu.execute(*self.cpu.instructions[0x58])
		assert self.cpu.I == 0
		assert self.cpu.cycles == initCycles + 2
		assert self.cpu.PC == 0x1001

	def test_clv(self):
		initCycles = self.cpu.cycles
		self.cpu.V = 1
		self.cpu.PC = 0x1000
		self.cpu.execute(*self.cpu.instructions[0xb8])
		assert self.cpu.V == 0
		assert self.cpu.cycles == initCycles + 2
		assert self.cpu.PC == 0x1001

	def test_cmp(self):
		#test zero result
		initCycles = self.cpu.cycles
		self.cpu.PC = 0x1000
		self.cpu.A = 0x10
		self.cpu.memory.write(0x1001, 0x10)		
		self.cpu.execute(*self.cpu.instructions[0xc9])
		assert self.cpu.Z
		assert self.cpu.C
		assert not self.cpu.N
		#test negative result
		self.cpu.PC = 0x1000
		self.cpu.A = 0x10
		self.cpu.memory.write(0x1001, 0x11)
		self.cpu.execute(*self.cpu.instructions[0xc9])
		assert not self.cpu.Z
		assert not self.cpu.C
		assert self.cpu.N

	def test_cpx(self):
		#test zero result
		initCycles = self.cpu.cycles
		self.cpu.PC = 0x1000
		self.cpu.X = 0x10
		self.cpu.memory.write(0x1001, 0x10)		
		self.cpu.execute(*self.cpu.instructions[0xe0])
		assert self.cpu.Z
		assert self.cpu.C
		assert not self.cpu.N
		#test negative result
		self.cpu.PC = 0x1000
		self.cpu.X = 0x10
		self.cpu.memory.write(0x1001, 0x11)
		self.cpu.execute(*self.cpu.instructions[0xe0])
		assert not self.cpu.Z
		assert not self.cpu.C
		assert self.cpu.N

	def test_cpy(self):
		#test zero result
		initCycles = self.cpu.cycles
		self.cpu.PC = 0x1000
		self.cpu.Y = 0x10
		self.cpu.memory.write(0x1001, 0x10)		
		self.cpu.execute(*self.cpu.instructions[0xc0])
		assert self.cpu.Z
		assert self.cpu.C
		assert not self.cpu.N
		#test negative result
		self.cpu.PC = 0x1000
		self.cpu.Y = 0x10
		self.cpu.memory.write(0x1001, 0x11)
		self.cpu.execute(*self.cpu.instructions[0xc0])
		assert not self.cpu.Z
		assert not self.cpu.C
		assert self.cpu.N

	def test_dec(self):
		self.cpu.PC = 0x1000
		self.cpu.memory.write16(0x1001, 0x2000)
		self.cpu.memory.write(0x2000, 0x5)
		self.cpu.execute(*self.cpu.instructions[0xce])
		assert self.cpu.memory.read(0x2000) == 0x4
		assert not self.cpu.Z
		assert not self.cpu.N

	def test_dex(self):
		self.cpu.X = 0x5
		self.cpu.execute(*self.cpu.instructions[0xca])
		assert self.cpu.X == 0x4
		assert not self.cpu.Z
		assert not self.cpu.N
	
	def test_dey(self):
		self.cpu.Y = 0x5
		self.cpu.execute(*self.cpu.instructions[0x88])
		assert self.cpu.Y == 0x4
		assert not self.cpu.Z
		assert not self.cpu.N

	def test_eor(self):
		self.cpu.A = 0b01010101
		self.cpu.memory.write(0x2000, 0b10101010)
		self.cpu.memory.write16(0x1001, 0x2000)
		self.cpu.PC = 0x1000
		self.cpu.execute(*self.cpu.instructions[0x4d])
		assert self.cpu.A == 0b11111111	

	def test_inc(self):
		self.cpu.PC = 0x1000
		self.cpu.memory.write16(0x1001, 0x2000)
		self.cpu.memory.write(0x2000, 0x5)
		self.cpu.execute(*self.cpu.instructions[0xee])
		assert self.cpu.memory.read(0x2000) == 0x6
		assert not self.cpu.Z
		assert not self.cpu.N
	
	def test_inx(self):
		self.cpu.X = 0x5
		self.cpu.execute(*self.cpu.instructions[0xe8])
		assert self.cpu.X == 0x6
		assert not self.cpu.Z
		assert not self.cpu.N
	
	def test_iny(self):
		self.cpu.Y = 0x5
		self.cpu.execute(*self.cpu.instructions[0xc8])
		assert self.cpu.Y == 0x6
		assert not self.cpu.Z
		assert not self.cpu.N

	def test_jmp(self):
		self.cpu.PC = 0x1000
		self.cpu.memory.write16(0x1001, 0x2000)
		self.cpu.execute(*self.cpu.instructions[0x4c])
		assert self.cpu.PC == 0x2000

	def test_jsr(self):
		self.cpu.PC = 0x1000
		self.cpu.memory.write16(0x1001, 0x2000)
		self.cpu.execute(*self.cpu.instructions[0x20])
		assert self.cpu.popStack() + (self.cpu.popStack() << 8) == 0x1002
		assert self.cpu.PC == 0x2000

	def test_lda(self):
		self.cpu.PC = 0x1000
		self.cpu.memory.write(0x1001, 0x10)
		self.cpu.execute(*self.cpu.instructions[0xa9])
		assert self.cpu.A == 0x10
		assert not self.cpu.N
		assert not self.cpu.Z

	def test_ldx(self):
		self.cpu.PC = 0x1000
		self.cpu.memory.write(0x1001, 0x10)
		self.cpu.execute(*self.cpu.instructions[0xa2])
		assert self.cpu.X == 0x10
		assert not self.cpu.N
		assert not self.cpu.Z

	def test_ldy(self):
		self.cpu.PC = 0x1000
		self.cpu.memory.write(0x1001, 0x10)
		self.cpu.execute(*self.cpu.instructions[0xa0])
		assert self.cpu.Y == 0x10
		assert not self.cpu.N
		assert not self.cpu.Z

	def test_lsr(self):
		self.cpu.A = 0b00001111
		self.cpu.execute(*self.cpu.instructions[0x4a])
		assert self.cpu.A == 0b00000111
		assert not self.cpu.Z
		assert not self.cpu.N
		assert self.cpu.C

	def test_nop(self):
		self.cpu.PC = 0x1000
		self.cpu.execute(*self.cpu.instructions[0xea])
		assert self.cpu.PC == 0x1001


	def test_ora(self):
		self.cpu.A = 0b01010101
		self.cpu.memory.write(0x2000, 0b10101010)
		self.cpu.memory.write16(0x1001, 0x2000)
		self.cpu.PC = 0x1000
		self.cpu.execute(*self.cpu.instructions[0x0d])
		assert self.cpu.A == 0b11111111

	def test_pha(self):
		self.cpu.SP = 0x1FF
		self.cpu.A = 0x5
		self.cpu.execute(*self.cpu.instructions[0x48])
		assert self.cpu.SP == 0x1FE
		assert self.cpu.memory.read(0x1FF) == 0x5

	def test_php(self):
		self.cpu.SP = 0x1FF
		self.cpu.setProcessorStatus(0xFF)
		self.cpu.execute(*self.cpu.instructions[0x08])
		assert self.cpu.SP == 0x1FE
		assert self.cpu.memory.read(0x1FF) == self.cpu.getProcessorStatus()

	def test_pla(self):
		init_sp = self.cpu.SP
		self.cpu.pushStack(0x5)
		self.cpu.execute(*self.cpu.instructions[0x68])
		assert self.cpu.A == 0x5
		assert self.cpu.SP == init_sp

	def test_plp(self):
		init_sp = self.cpu.SP
		self.cpu.pushStack(0xdf)
		self.cpu.execute(*self.cpu.instructions[0x28])
		assert self.cpu.getProcessorStatus() == 0xff
		assert self.cpu.SP == init_sp

	def test_rol(self):
		self.cpu.C = 0
		self.cpu.A = 0b11111111
		self.cpu.execute(*self.cpu.instructions[0x2a])
		assert self.cpu.A == 0b11111110
		assert self.cpu.C == 1

	def test_ror(self):
		self.cpu.C = 0
		self.cpu.A = 0b11111111
		self.cpu.execute(*self.cpu.instructions[0x6a])
		assert self.cpu.A == 0b01111111
		assert self.cpu.C == 1

	def test_rti(self):
		self.cpu.PC = 0x1000
		self.cpu.memory.write16(0xFFFE, 0x2000)
		self.cpu.setProcessorStatus(0x0F)
		self.cpu.execute(*self.cpu.instructions[0x00])
		assert self.cpu.PC == 0x2000
		self.cpu.execute(*self.cpu.instructions[0x40])
		assert self.cpu.PC == 0x1002
		assert self.cpu.getProcessorStatus() == 0x2F


	def test_rts(self):
		self.cpu.PC = 0x1000
		self.cpu.memory.write16(0x1001, 0x2000)
		self.cpu.execute(*self.cpu.instructions[0x20])
		self.cpu.execute(*self.cpu.instructions[0x60])
		assert self.cpu.PC == 0x1003


	def test_sbc(self):
		self.cpu.C = 1
		self.cpu.A = 0x7F
		self.cpu.PC = 0x1000
		self.cpu.memory.write(0x1001, 0x8A)
		self.cpu.execute(*self.cpu.instructions[0xe9])
		assert self.cpu.C == 0
		assert self.cpu.N == 1
		assert self.cpu.Z == 0
		assert self.cpu.V == 1
		assert self.cpu.PC == 0x1002

	def test_sec(self):
		initCycles = self.cpu.cycles
		self.cpu.C = 0
		self.cpu.execute(*self.cpu.instructions[0x38])
		assert self.cpu.C
		assert self.cpu.cycles == initCycles + 2

	def test_sed(self):
		initCycles = self.cpu.cycles
		self.cpu.D = 0
		self.cpu.execute(*self.cpu.instructions[0xf8])
		assert self.cpu.D
		assert self.cpu.cycles == initCycles + 2

	def test_sei(self):
		initCycles = self.cpu.cycles
		self.cpu.I = 0
		self.cpu.execute(*self.cpu.instructions[0x78])
		assert self.cpu.I
		assert self.cpu.cycles == initCycles + 2

	def test_sta(self):
		self.cpu.A = 0x5
		self.cpu.PC = 0x1000
		self.cpu.memory.write(0x1001, 0x10)
		self.cpu.execute(*self.cpu.instructions[0x85])
		assert self.cpu.memory.read(0x10) == 0x5

	def test_stx(self):
		self.cpu.X = 0x5
		self.cpu.PC = 0x1000
		self.cpu.memory.write(0x1001, 0x10)
		self.cpu.execute(*self.cpu.instructions[0x86])
		assert self.cpu.memory.read(0x10) == 0x5

	def test_sty(self):
		self.cpu.Y = 0x5
		self.cpu.PC = 0x1000
		self.cpu.memory.write(0x1001, 0x10)
		self.cpu.execute(*self.cpu.instructions[0x84])
		assert self.cpu.memory.read(0x10) == 0x5

	def test_tax(self):
		self.cpu.A = 0x5
		self.cpu.execute(*self.cpu.instructions[0xaa])
		assert self.cpu.X == 0x5
		assert not self.cpu.N
		assert not self.cpu.Z

	def test_tay(self):
		self.cpu.A = 0x5
		self.cpu.execute(*self.cpu.instructions[0xa8])
		assert self.cpu.Y == 0x5
		assert not self.cpu.N
		assert not self.cpu.Z

	def test_tsx(self):
		self.cpu.SP = 0xFF
		self.cpu.execute(*self.cpu.instructions[0xba])
		assert self.cpu.X == 0xFF
		assert self.cpu.N
		assert not self.cpu.Z

	def test_txa(self):
		self.cpu.X = 0xFF
		self.cpu.execute(*self.cpu.instructions[0x8a])
		assert self.cpu.A == 0xFF
		assert self.cpu.N
		assert not self.cpu.Z

	def test_txs(self):
		self.cpu.X = 0xFF
		self.cpu.execute(*self.cpu.instructions[0x9a])
		assert self.cpu.SP == 0x1FF

	def test_tya(self):
		self.cpu.Y = 0xFF
		self.cpu.execute(*self.cpu.instructions[0x98])
		assert self.cpu.A == 0xFF
		assert self.cpu.N
		assert not self.cpu.Z

class ROMTests(unittest.TestCase):
	def testROM(self):
		actualOutput = StringIO()
		cpu = CPU(NESTEST_ROM, actualOutput)
		cpu.PC = 0xc000
		for _ in range(5000):
			cpu.fetch()

		actual_lines = actualOutput.getvalue().splitlines(keepends=True)
		self.assertEqual(len(actual_lines), 5000)
		with NESTEST_LOG.open() as expectedOutput:
			expected_lines = expectedOutput.readlines()
			for line, (actualLine, expectedLine) in enumerate(
				zip(actual_lines, expected_lines), start=1
			):
				self.assertEqual(actualLine[0:4], expectedLine[0:4], line)
				self.assertEqual(
					actualLine[actualLine.index('CYC'):],
					expectedLine[expectedLine.index('CYC'):],
					line,
				)
if __name__ == '__main__':
	unittest.main()
