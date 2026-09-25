# https://wiki.nesdev.com/w/index.php/INES

class ROM:
	def __init__(self, filepath):
		with open(filepath, 'rb') as rom_file:
			header = bytearray(rom_file.read(16))

			if header[0:3] != b'NES':
				raise ValueError('Invalid iNES ROM')
			self.prg_rom_size = header[4]
			self.chr_rom_size = header[5]
			self.prg_rom = rom_file.read(0x4000 * self.prg_rom_size)
			self.chr_rom = rom_file.read(0x2000 * self.chr_rom_size)

		# TODO: handle flags from header[6:10]

#print("{:02x}".format(self.data[i]))
