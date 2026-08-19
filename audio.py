"""Audio capture. Works with the default mic or any input device
(e.g. AirPods, or BlackHole for system audio).

Records at the device's NATIVE sample rate and resamples afterwards -
forcing a rate on some devices (AirPods mics run at 24kHz) yields audio
stamped with the wrong rate, which turns speech into sludge for Whisper.
"""

import time

import numpy as np
import sounddevice as sd

# Rates real devices actually use; measured rates get snapped to these.
_COMMON_RATES = [8000, 16000, 22050, 24000, 32000, 44100, 48000]


def list_input_devices():
    """Return [(index, name)] for all devices that can record."""
    return [
        (i, d["name"])
        for i, d in enumerate(sd.query_devices())
        if d["max_input_channels"] > 0
    ]


class Recorder:
    def __init__(self, samplerate=16000):
        self.target_rate = samplerate
        self._native_rate = samplerate
        self._frames = []
        self._stream = None

    def start(self, device=None):
        self._frames = []
        self._first_frame_at = None

        def callback(indata, frames, time_info, status):
            if self._first_frame_at is None:
                self._first_frame_at = time.monotonic()
            self._frames.append(indata.copy())

        # No samplerate arg: open at the device's native rate.
        self._stream = sd.InputStream(
            channels=1,
            dtype="float32",
            device=device,
            callback=callback,
        )
        self._native_rate = float(self._stream.samplerate)
        self._stream.start()

    def stop(self) -> np.ndarray:
        """Stop recording; return mono float32 audio at target_rate."""
        if self._stream:
            self._stream.stop()
            self._stream.close()
            self._stream = None
        if not self._frames:
            return np.zeros(0, dtype=np.float32)
        audio = np.concatenate(self._frames).flatten()

        # Some drivers (AirPods) lie about the rate: they report one but
        # deliver frames at another. Measure the effective rate from wall
        # clock and trust it over the reported one when they disagree.
        elapsed = time.monotonic() - (self._first_frame_at or 0)
        if self._first_frame_at and elapsed > 0.5:
            measured = len(audio) / elapsed
            snapped = min(_COMMON_RATES, key=lambda r: abs(r - measured))
            if abs(snapped - measured) / snapped < 0.15 and snapped != self._native_rate:
                self._native_rate = float(snapped)

        if self._native_rate != self.target_rate:
            n = int(len(audio) * self.target_rate / self._native_rate)
            audio = np.interp(
                np.linspace(0, len(audio) - 1, n),
                np.arange(len(audio)),
                audio,
            ).astype(np.float32)
        return audio
