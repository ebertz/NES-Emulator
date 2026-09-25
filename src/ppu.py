#PPU Memory Map
# Addr range	Size	Description
# $0000-$0FFF	$1000	Pattern table 0
# $1000-$1FFF	$1000	Pattern Table 1
# $2000-$23FF	$0400	Nametable 0
# $2400-$27FF	$0400	Nametable 1
# $2800-$2BFF	$0400	Nametable 2
# $2C00-$2FFF	$0400	Nametable 3
# $3000-$3EFF	$0F00	Mirrors of $2000-$2EFF
# $3F00-$3F1F	$0020	Palette RAM indexes
# $3F20-$3FFF	$00E0	Mirrors of $3F00-$3F1F


import memory

class PPU:
	def __init__(self, nes):
		self.nes = nes
		self.memory = memory.Memory(0x4000)
		self.cpuMemory = self.nes.cpu.memory
		self.scanline = 0
		self.cycle = 0

		self.shift16_1 = 0
		self.shift16_2 = 0

		# PPUCTRL ($2000)
		self.flag_nmi_enable = 0
		self.flag_master_slave = 0
		self.flag_sprite_size = 0
		self.flag_background_table = 0
		self.flag_sprite_table = 0
		self.flag_increment_mode = 0
		self.flag_nametable_select = 0

		# PPUMASK ($2001)
		self.flag_blue_tint = 0
		self.flag_green_tint = 0
		self.flag_red_tint = 0
		self.flag_show_sprites = 0
		self.flag_show_background = 0
		self.flag_show_left_sprites = 0
		self.flag_show_left_background = 0
		self.flag_grayscale = 0

		# PPUSTATUS ($2002)
		self.ppustatus = 0 #TODO: flags?
		self.flag_sprite_zero_hit = 0
		self.flag_sprite_overflow = 0

		# OAMADDR ($2003)
		self.oamaddr = 0

		# OAMDATA ($2004)
		self.oamdata = 0

		# PPUSCROLL ($2005)
		self.ppuscroll = 0

		# PPUADDR ($2006)
		#16-bit address of VRAM to access
		self.ppuaddr = 0
		self.ppuaddrBuffer = 0
		self.addressLatch = 0

		# PPUDATA ($2007)
		self.ppudata = 0

		# OAMDMA ($4014)
		self.oamdma = 0


	def read(self, address):
		return self.memory[address]

	def write(self, address, value):
		self.memory[address] = value & 0xFF

	def step(self):
		renderLine = self.scanline < 240
		vBlankLine = self.scanline == 241
		preRenderLine = self.scanline == 261
		renderingEnabled = self.flag_show_background or self.flag_show_sprites

		if preRenderLine:
			pass

		if renderingEnabled:
			if renderLine:
				if  1 <= self.cycle <= 256:
					self.renderPixel()

				#fetch Name Table byte
				self.fetchNameTableByte()
				#fetch Attribute Table byte
				self.fetchAttributeTableByte()
				#fetch Low Tile byte
				self.fetchLowTileByte()
				#fetch High Tile byte
				self.fetchHighTileByte()

				#cycle 256,257 inc X and Y
				pass 

			if self.cycle == 257:
				self.evaluateSprites() #TODO

		#do nothing on scanlines 240, 242-260 ??

		elif vBlankLine:
			# set vblank
			pass

		# TODO: advance to next frame
		elif preRenderLine:
			# TODO: load first two tiles of next scanline
			if self.cycle == 340:
				self.cycle = -1
				self.scanline = 0

		# advance to next scanline
		if self.cycle >= 340:
			self.scanline += 1
			self.cycle = -1

		self.cycle += 1

	def renderPixel(self):
		raise NotImplementedError('renderPixel not implemented')

	def fetchNameTableByte(self):
		raise NotImplementedError('fetchNameTableByte not implemented')

	def fetchAttributeTableByte(self):
		raise NotImplementedError('fetchAttributeTableByte not implemented')

	def fetchLowTileByte(self):
		raise NotImplementedError('fetchLowTileByte not implemented')

	def fetchHighTileByte(self):
		raise NotImplementedError('fetchHighTileByte not implemented')


	def readRegister(self, address):
		#PPUSTATUS
		if address == 0x2002:
			return self.read_ppustatus()
		#OAMDATA
		if address == 0x2004:
			return self.read_oamdata()
		#PPUDATA
		if address == 0x2007:
			return self.read_ppudata()

	def writeRegister(self,address):
		# PPUCTRL
		if address == 0x2000:
			return self.write_ppuctrl()
		#PPUMASK
		if address == 0x2001:
			return self.write_ppumask()
		#OAMADDR
		if address == 0x2003:
			return self.write_oamaddr()
		#OAMDATA
		if address == 0x2004:
			return self.write_oamdata()
		#PPUSCROLL
		if address == 0x2005:
			return self.write_ppuscroll()
		#PPUADDR
		if address == 0x2006:
			return self.write_ppuaddr()
		#PPUDATA
		if address == 0x2007:
			return self.write_ppudata()
		#OAMDMA
		if address == 0x4014:
			return self.write_oamdma()

	def read_ppustatus(self):
		self.addressLatch = 0
		pass
	def read_oamdata(self):
		pass
	def read_ppudata(self):
		self.inc_ppuaddr()
		pass
	def write_ppuctrl(self):
		pass
	def write_ppumask(self):
		pass
	def write_oamaddr(self):
		pass
	def write_oamdata(self):
		pass
	def write_ppuscroll(self):
		pass
	def write_ppuaddr(self, value):
		if self.addressLatch == 0:
			# t: ..FEDCBA ........ = d: ..FEDCBA
			# t: .X...... ........ = 0
			# w:                   = 1
			self.ppuaddrBuffer = self.ppuaddrBuffer & 0x80FF
			self.ppuaddrBuffer |= (value & 0x3F) << 8
			self.addressLatch = 1
		else:
			# t: ........ HGFEDCBA = d: HGFEDCBA
			# v                    = t
			# w:                   = 0	
			self.ppuaddrBuffer = (self.ppuaddrBuffer & 0xFF00) | (value & 0xFF)
			self.ppuaddr = self.ppuaddrBuffer
			self.addressLatch = 0

	def write_ppudata(self):
		self.inc_ppuaddr()
		pass
	def write_oamdma(self):
		pass

	def inc_ppuaddr(self):
		if self.flag_increment_mode == 0:
			self.ppuaddr += 1
		else:
			self.ppuaddr += 32

