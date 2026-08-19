"""Speech-to-text via faster-whisper (runs locally, no API needed).

Model sizes: tiny.en (fastest) / base.en (good default) / small.en (better)
The first run downloads the model (~150MB for base.en).
"""

import numpy as np
from faster_whisper import WhisperModel


class Transcriber:
    def __init__(self, model_size="base.en"):
        self.model = WhisperModel(model_size, device="cpu", compute_type="int8")

    def transcribe(self, audio: np.ndarray) -> str:
        if audio.size == 0:
            return ""
        segments, _ = self.model.transcribe(audio, beam_size=5, vad_filter=True)
        return " ".join(seg.text.strip() for seg in segments)
