class Controller:
    """NES serial controller port."""

    def __init__(self):
        self.buttons = 0
        self._strobe = 0
        self._shift_register = 0

    def write(self, value):
        previous_strobe = self._strobe
        self._strobe = value & 1
        if self._strobe or previous_strobe:
            self._shift_register = self.buttons & 0xFF

    def read(self):
        if self._strobe:
            self._shift_register = self.buttons & 0xFF
        value = self._shift_register & 1
        if not self._strobe:
            self._shift_register = (self._shift_register >> 1) | 0x80
        return value
