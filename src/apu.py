from collections import deque


CPU_FREQUENCY = 1_789_773
PCM_BUFFER_CAPACITY = 44_100
LENGTH_TABLE = (
    10, 254, 20, 2, 40, 4, 80, 6, 160, 8, 60, 10, 14, 12, 26, 14,
    12, 16, 24, 18, 48, 20, 96, 22, 192, 24, 72, 26, 16, 28, 32, 30,
)
DUTY_TABLE = (
    (0, 1, 0, 0, 0, 0, 0, 0),
    (0, 1, 1, 0, 0, 0, 0, 0),
    (0, 1, 1, 1, 1, 0, 0, 0),
    (1, 0, 0, 1, 1, 1, 1, 1),
)
TRIANGLE_TABLE = tuple(range(15, -1, -1)) + tuple(range(16))
NOISE_PERIODS = (4, 8, 16, 32, 64, 96, 128, 160, 202, 254, 380, 508, 762, 1016, 2034, 4068)
DMC_PERIODS = (428, 380, 340, 320, 286, 254, 226, 214, 190, 160, 142, 128, 106, 85, 72, 54)


class Envelope:
    def __init__(self):
        self.loop = False
        self.constant = False
        self.period = 0
        self.start = False
        self.divider = 0
        self.decay = 0

    def configure(self, value):
        self.loop = bool(value & 0x20)
        self.constant = bool(value & 0x10)
        self.period = value & 0x0F

    def clock(self):
        if self.start:
            self.start = False
            self.decay = 15
            self.divider = self.period
        elif self.divider:
            self.divider -= 1
        else:
            self.divider = self.period
            if self.decay:
                self.decay -= 1
            elif self.loop:
                self.decay = 15

    @property
    def volume(self):
        return self.period if self.constant else self.decay


class Pulse:
    def __init__(self, channel):
        self.channel = channel
        self.enabled = False
        self.length = 0
        self.duty = 0
        self.sequence = 0
        self.timer_period = 0
        self.timer = 0
        self.envelope = Envelope()
        self.sweep_enabled = False
        self.sweep_period = 0
        self.sweep_negate = False
        self.sweep_shift = 0
        self.sweep_reload = False
        self.sweep_divider = 0

    def write(self, register, value):
        if register == 0:
            self.duty = value >> 6
            self.envelope.configure(value)
        elif register == 1:
            self.sweep_enabled = bool(value & 0x80)
            self.sweep_period = (value >> 4) & 7
            self.sweep_negate = bool(value & 8)
            self.sweep_shift = value & 7
            self.sweep_reload = True
        elif register == 2:
            self.timer_period = (self.timer_period & 0x700) | value
        else:
            self.timer_period = (self.timer_period & 0xFF) | ((value & 7) << 8)
            if self.enabled:
                self.length = LENGTH_TABLE[value >> 3]
            self.sequence = 0
            self.envelope.start = True

    def clock_timer(self):
        if self.timer:
            self.timer -= 1
        else:
            self.timer = self.timer_period
            self.sequence = (self.sequence + 1) & 7

    def clock_length(self):
        if self.length and not self.envelope.loop:
            self.length -= 1

    def _sweep_target(self):
        change = self.timer_period >> self.sweep_shift
        if self.sweep_negate:
            return self.timer_period - change - (1 if self.channel == 1 else 0)
        return self.timer_period + change

    def clock_sweep(self):
        if (
            self.sweep_divider == 0
            and self.sweep_enabled
            and self.sweep_shift
            and self.timer_period >= 8
            and self._sweep_target() <= 0x7FF
        ):
            self.timer_period = self._sweep_target()
        if self.sweep_divider == 0 or self.sweep_reload:
            self.sweep_divider = self.sweep_period
            self.sweep_reload = False
        else:
            self.sweep_divider -= 1

    @property
    def output(self):
        if (
            not self.enabled
            or not self.length
            or self.timer_period < 8
            or self._sweep_target() > 0x7FF
            or not DUTY_TABLE[self.duty][self.sequence]
        ):
            return 0
        return self.envelope.volume


class Triangle:
    def __init__(self):
        self.enabled = False
        self.length = 0
        self.control = False
        self.linear_reload_value = 0
        self.linear = 0
        self.linear_reload = False
        self.timer_period = 0
        self.timer = 0
        self.sequence = 0

    def write(self, register, value):
        if register == 0:
            self.control = bool(value & 0x80)
            self.linear_reload_value = value & 0x7F
        elif register == 2:
            self.timer_period = (self.timer_period & 0x700) | value
        elif register == 3:
            self.timer_period = (self.timer_period & 0xFF) | ((value & 7) << 8)
            if self.enabled:
                self.length = LENGTH_TABLE[value >> 3]
            self.linear_reload = True

    def clock_timer(self):
        if self.timer:
            self.timer -= 1
        else:
            self.timer = self.timer_period
            if self.length and self.linear and self.timer_period > 1:
                self.sequence = (self.sequence + 1) & 31

    def clock_linear(self):
        if self.linear_reload:
            self.linear = self.linear_reload_value
        elif self.linear:
            self.linear -= 1
        if not self.control:
            self.linear_reload = False

    def clock_length(self):
        if self.length and not self.control:
            self.length -= 1

    @property
    def output(self):
        if not self.enabled or not self.length or not self.linear:
            return 0
        return TRIANGLE_TABLE[self.sequence]


class Noise:
    def __init__(self):
        self.enabled = False
        self.length = 0
        self.mode = False
        self.timer_period = NOISE_PERIODS[0]
        self.timer = 0
        self.shift = 1
        self.envelope = Envelope()

    def write(self, register, value):
        if register == 0:
            self.envelope.configure(value)
        elif register == 2:
            self.mode = bool(value & 0x80)
            self.timer_period = NOISE_PERIODS[value & 0x0F]
        elif register == 3:
            if self.enabled:
                self.length = LENGTH_TABLE[value >> 3]
            self.envelope.start = True

    def clock_timer(self):
        if self.timer:
            self.timer -= 1
        else:
            self.timer = self.timer_period
            tap = 6 if self.mode else 1
            feedback = (self.shift & 1) ^ ((self.shift >> tap) & 1)
            self.shift = (self.shift >> 1) | (feedback << 14)

    def clock_length(self):
        if self.length and not self.envelope.loop:
            self.length -= 1

    @property
    def output(self):
        if not self.enabled or not self.length or self.shift & 1:
            return 0
        return self.envelope.volume


class DMC:
    def __init__(self, memory_reader):
        self.memory_reader = memory_reader
        self.enabled = False
        self.irq_enabled = False
        self.loop = False
        self.irq = False
        self.timer_period = DMC_PERIODS[0]
        self.timer = 0
        self.output = 0
        self.sample_address = 0xC000
        self.sample_length = 1
        self.current_address = 0xC000
        self.bytes_remaining = 0
        self.sample_buffer = None
        self.shift = 0
        self.bits_remaining = 8
        self.silence = True

    def restart(self):
        self.current_address = self.sample_address
        self.bytes_remaining = self.sample_length

    def _fill_buffer(self):
        if self.sample_buffer is not None or not self.bytes_remaining:
            return
        self.sample_buffer = self.memory_reader(self.current_address) & 0xFF
        self.current_address = 0x8000 if self.current_address == 0xFFFF else self.current_address + 1
        self.bytes_remaining -= 1
        if not self.bytes_remaining:
            if self.loop:
                self.restart()
            elif self.irq_enabled:
                self.irq = True

    def clock_timer(self):
        self._fill_buffer()
        if self.timer:
            self.timer -= 1
            return
        self.timer = self.timer_period
        if not self.silence:
            if self.shift & 1 and self.output <= 125:
                self.output += 2
            elif not self.shift & 1 and self.output >= 2:
                self.output -= 2
        self.shift >>= 1
        self.bits_remaining -= 1
        if not self.bits_remaining:
            self.bits_remaining = 8
            if self.sample_buffer is None:
                self.silence = True
            else:
                self.silence = False
                self.shift = self.sample_buffer
                self.sample_buffer = None


class APU:
    """Clocked NTSC 2A03 audio unit producing signed 16-bit mono PCM."""

    def __init__(self, sample_rate=44_100, memory_reader=None):
        if sample_rate <= 0:
            raise ValueError("sample_rate must be positive")
        self.sample_rate = sample_rate
        self.memory_reader = memory_reader or (lambda _address: 0)
        self.pulse1 = Pulse(1)
        self.pulse2 = Pulse(2)
        self.triangle = Triangle()
        self.noise = Noise()
        self.dmc = DMC(lambda address: self.memory_reader(address))
        self._registers = bytearray(0x20)
        # Frontends are expected to drain once per rendered frame. Keep a
        # bounded fallback so a paused or absent frontend cannot exhaust RAM.
        self.samples = deque(maxlen=PCM_BUFFER_CAPACITY)
        self._cycles = 0
        self._frame_cycle = 0
        self._sample_phase = 0
        self._five_step = False
        self._frame_irq_inhibit = False
        self._frame_irq = False

    def read_register(self, addr):
        if addr & 0xFFFF != 0x4015:
            return 0
        status = (
            (bool(self.pulse1.length) << 0)
            | (bool(self.pulse2.length) << 1)
            | (bool(self.triangle.length) << 2)
            | (bool(self.noise.length) << 3)
            | (bool(self.dmc.bytes_remaining) << 4)
            | (self._frame_irq << 6)
            | (self.dmc.irq << 7)
        )
        self._frame_irq = False
        return status

    def write_register(self, addr, value):
        addr &= 0xFFFF
        value &= 0xFF
        if 0x4000 <= addr <= 0x4017:
            self._registers[addr & 0x1F] = value
        if 0x4000 <= addr <= 0x4003:
            self.pulse1.write(addr - 0x4000, value)
        elif 0x4004 <= addr <= 0x4007:
            self.pulse2.write(addr - 0x4004, value)
        elif addr in (0x4008, 0x400A, 0x400B):
            self.triangle.write(addr - 0x4008, value)
        elif addr in (0x400C, 0x400E, 0x400F):
            self.noise.write(addr - 0x400C, value)
        elif addr == 0x4010:
            self.dmc.irq_enabled = bool(value & 0x80)
            self.dmc.loop = bool(value & 0x40)
            self.dmc.timer_period = DMC_PERIODS[value & 0x0F]
            if not self.dmc.irq_enabled:
                self.dmc.irq = False
        elif addr == 0x4011:
            self.dmc.output = value & 0x7F
        elif addr == 0x4012:
            self.dmc.sample_address = 0xC000 | (value << 6)
        elif addr == 0x4013:
            self.dmc.sample_length = (value << 4) | 1
        elif addr == 0x4015:
            self._write_status(value)
        elif addr == 0x4017:
            self._write_frame_counter(value)

    def _write_status(self, value):
        channels = (self.pulse1, self.pulse2, self.triangle, self.noise)
        for bit, channel in enumerate(channels):
            channel.enabled = bool(value & (1 << bit))
            if not channel.enabled:
                channel.length = 0
        self.dmc.enabled = bool(value & 0x10)
        self.dmc.irq = False
        if not self.dmc.enabled:
            self.dmc.bytes_remaining = 0
        elif not self.dmc.bytes_remaining:
            self.dmc.restart()

    def _write_frame_counter(self, value):
        self._five_step = bool(value & 0x80)
        self._frame_irq_inhibit = bool(value & 0x40)
        if self._frame_irq_inhibit:
            self._frame_irq = False
        self._frame_cycle = 0
        if self._five_step:
            self._clock_quarter_frame()
            self._clock_half_frame()

    def _clock_quarter_frame(self):
        self.pulse1.envelope.clock()
        self.pulse2.envelope.clock()
        self.noise.envelope.clock()
        self.triangle.clock_linear()

    def _clock_half_frame(self):
        self.pulse1.clock_length()
        self.pulse2.clock_length()
        self.triangle.clock_length()
        self.noise.clock_length()
        self.pulse1.clock_sweep()
        self.pulse2.clock_sweep()

    def _clock_frame_counter(self):
        self._frame_cycle += 1
        if self._five_step:
            if self._frame_cycle in (7457, 22371):
                self._clock_quarter_frame()
            elif self._frame_cycle in (14913, 37281):
                self._clock_quarter_frame()
                self._clock_half_frame()
            if self._frame_cycle >= 37281:
                self._frame_cycle = 0
        else:
            if self._frame_cycle in (7457, 22371):
                self._clock_quarter_frame()
            elif self._frame_cycle in (14913, 29829):
                self._clock_quarter_frame()
                self._clock_half_frame()
                if self._frame_cycle == 29829 and not self._frame_irq_inhibit:
                    self._frame_irq = True
            if self._frame_cycle >= 29829:
                self._frame_cycle = 0

    @staticmethod
    def mix_sample(pulse1, pulse2, triangle, noise, dmc):
        pulse_sum = pulse1 + pulse2
        pulse = 0.0 if not pulse_sum else 95.88 / (8128.0 / pulse_sum + 100.0)
        tnd_input = triangle / 8227.0 + noise / 12241.0 + dmc / 22638.0
        tnd = 0.0 if not tnd_input else 159.79 / (1.0 / tnd_input + 100.0)
        return max(-32768, min(32767, round((pulse + tnd) * 32767)))

    def _emit_sample(self):
        self.samples.append(
            self.mix_sample(
                self.pulse1.output,
                self.pulse2.output,
                self.triangle.output,
                self.noise.output,
                self.dmc.output,
            )
        )

    def step(self, cycles=1):
        if cycles < 0:
            raise ValueError("cycles must not be negative")
        for _ in range(cycles):
            self._cycles += 1
            self._clock_frame_counter()
            self.triangle.clock_timer()
            self.noise.clock_timer()
            self.dmc.clock_timer()
            if not self._cycles & 1:
                self.pulse1.clock_timer()
                self.pulse2.clock_timer()
            self._sample_phase += self.sample_rate
            if self._sample_phase >= CPU_FREQUENCY:
                self._sample_phase -= CPU_FREQUENCY
                self._emit_sample()

    def drain_samples(self):
        result = list(self.samples)
        self.samples.clear()
        return result

    @property
    def irq_line(self):
        return self._frame_irq or self.dmc.irq
