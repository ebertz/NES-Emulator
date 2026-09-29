import hashlib
import os
import sys
import unittest

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from apu import APU, CPU_FREQUENCY  # noqa: E402
from console import Console  # noqa: E402


def configured_apu():
    apu = APU(sample_rate=CPU_FREQUENCY, memory_reader=lambda _address: 0xAA)
    apu.write_register(0x4015, 0x1F)
    apu.write_register(0x4000, 0xDF)
    apu.write_register(0x4002, 0x08)
    apu.write_register(0x4003, 0x08)
    apu.write_register(0x4004, 0x9A)
    apu.write_register(0x4006, 0x10)
    apu.write_register(0x4007, 0x08)
    apu.write_register(0x4008, 0x81)
    apu.write_register(0x400A, 0x02)
    apu.write_register(0x400B, 0x08)
    apu.write_register(0x400C, 0x1C)
    apu.write_register(0x400E, 0x00)
    apu.write_register(0x400F, 0x08)
    apu.write_register(0x4010, 0x0F)
    apu.write_register(0x4011, 0x40)
    apu.write_register(0x4012, 0x00)
    apu.write_register(0x4013, 0x00)
    return apu


class APURegisterTests(unittest.TestCase):
    def test_status_reports_and_disable_clears_length_counters(self):
        apu = APU()
        apu.write_register(0x4015, 0x0F)
        for address in (0x4003, 0x4007, 0x400B, 0x400F):
            apu.write_register(address, 0x08)

        self.assertEqual(apu.read_register(0x4015) & 0x0F, 0x0F)

        apu.write_register(0x4015, 0x05)
        self.assertEqual(apu.read_register(0x4015) & 0x0F, 0x05)
        self.assertEqual(apu.pulse2.length, 0)
        self.assertEqual(apu.noise.length, 0)

    def test_frame_irq_is_reported_and_status_read_acknowledges_it(self):
        apu = APU()
        apu.step(29_829)

        self.assertTrue(apu.irq_line)
        self.assertEqual(apu.read_register(0x4015) & 0x40, 0x40)
        self.assertFalse(apu.irq_line)
        self.assertEqual(apu.read_register(0x4015) & 0x40, 0)

    def test_frame_irq_inhibit_prevents_irq(self):
        apu = APU()
        apu.write_register(0x4017, 0x40)
        apu.step(60_000)
        self.assertFalse(apu.irq_line)

    def test_invalid_sample_rate_and_negative_cycles_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "sample_rate must be positive"):
            APU(sample_rate=0)
        with self.assertRaisesRegex(ValueError, "cycles must not be negative"):
            APU().step(-1)

    def test_unknown_channel_name_is_rejected_without_losing_samples(self):
        apu = configured_apu()
        apu.step(2)
        with self.assertRaisesRegex(ValueError, "unknown APU channel"):
            apu.drain_channel_samples("square")
        self.assertEqual(len(apu.channel_samples["pulse1"]), 2)


class APUSynthesisTests(unittest.TestCase):
    EXPECTED_DIGESTS = {
        "pulse1": "73c73196608c9504d9101606db316e2add110290da4fac5b6eeaa06ddee9c581",
        "pulse2": "b0845948884a66f78049c8ee0951e28285876a3ffcafd9aea7404d929b5cee4a",
        "triangle": "345066b3e2cf435c1ab0d5f7a573932661dff3dd9cc84e3f0bae4442dea48c3a",
        "noise": "29e8c1af2a144db4da597e26fec34c116870a5955d00ca20aa95b72e71e63cc3",
        "dmc": "2352410e3702f2c4a72a572501ba8a003233edc4a7c9c2daa110b868074fe958",
    }

    def test_fixture_program_produces_deterministic_channel_buffers(self):
        apu = configured_apu()
        apu.step(8_000)

        for channel, expected in self.EXPECTED_DIGESTS.items():
            samples = apu.drain_channel_samples(channel)
            digest = hashlib.sha256(bytes(samples)).hexdigest()
            self.assertEqual(digest, expected, channel)
            self.assertTrue(any(samples), channel)

    def test_mixer_produces_bounded_signed_pcm_and_silence_is_zero(self):
        self.assertEqual(APU.mix_sample(0, 0, 0, 0, 0), 0)
        values = [
            APU.mix_sample(15, 0, 0, 0, 0),
            APU.mix_sample(0, 15, 15, 15, 127),
            APU.mix_sample(15, 15, 15, 15, 127),
        ]
        self.assertTrue(all(isinstance(value, int) for value in values))
        self.assertTrue(all(-32768 <= value <= 32767 for value in values))
        self.assertEqual(values, sorted(values))

    def test_dmc_fetches_sample_memory_and_raises_irq_at_sample_end(self):
        reads = []

        def read(address):
            reads.append(address)
            return 0xFF

        apu = APU(sample_rate=CPU_FREQUENCY, memory_reader=read)
        apu.write_register(0x4010, 0x8F)
        apu.write_register(0x4012, 0x20)
        apu.write_register(0x4013, 0x00)
        apu.write_register(0x4015, 0x10)
        apu.step(1)

        self.assertEqual(reads, [0xC800])
        self.assertTrue(apu.irq_line)
        self.assertEqual(apu.read_register(0x4015) & 0x80, 0x80)

        apu.write_register(0x4015, 0)
        self.assertFalse(apu.irq_line)

    def test_drain_returns_pcm_once(self):
        apu = configured_apu()
        apu.step(8)
        samples = apu.drain_samples()

        self.assertEqual(len(samples), 8)
        self.assertEqual(apu.drain_samples(), [])

    def test_console_clocks_apu_for_each_elapsed_cpu_cycle(self):
        console = Console()
        self.addCleanup(console.cpu.logFile.close)
        console.cpu.debug = False
        console.apu.sample_rate = CPU_FREQUENCY
        console.bus.write(0, 0xEA)

        cycles = console.step()

        self.assertEqual(len(console.apu.drain_samples()), cycles)


if __name__ == "__main__":
    unittest.main()
