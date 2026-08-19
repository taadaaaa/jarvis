"""Audio capture. Works with the default mic or any input device
(e.g. BlackHole for system audio)."""

import numpy as np
import sounddevice as sd


def list_input_devices():
    """Return [(index, name)] for all devices that can record."""
    return [
        (i, d["name"])
        for i, d in enumerate(sd.query_devices())
        if d["max_input_channels"] > 0
    ]


class Recorder:
    def __init__(self, samplerate=16000):
        self.samplerate = samplerate
        self._frames = []
        self._stream = None

    def start(self, device=None):
        self._frames = []

        def callback(indata, frames, time, status):
            self._frames.append(indata.copy())

        self._stream = sd.InputStream(
            samplerate=self.samplerate,
            channels=1,
            dtype="float32",
            device=device,
            callback=callback,
        )
        self._stream.start()

    def stop(self) -> np.ndarray:
        """Stop recording and return mono float32 audio at self.samplerate."""
        if self._stream:
            self._stream.stop()
            self._stream.close()
            self._stream = None
        if not self._frames:
            return np.zeros(0, dtype=np.float32)
        return np.concatenate(self._frames).flatten()
