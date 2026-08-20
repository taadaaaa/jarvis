"""Hands-free voice mode: an always-on microphone with energy-based VAD.

Two layers so the logic is testable without a microphone:

  - SpeechDetector: pure numpy. feed() it audio chunks of any size; it
    tracks a rolling noise floor, detects speech segments (with pre-roll),
    and calls on_utterance(audio) when one ends.
  - HandsFreeListener: wraps a sounddevice input stream around a detector,
    pauses cleanly while Jarvis is busy (so he doesn't hear himself), and
    delivers utterances resampled to 16kHz on a worker thread.

Tunables live in config.py (all optional, sane defaults here):
  VAD_FRAME_SEC, VAD_START_SEC, VAD_END_SEC, VAD_PREROLL_SEC,
  VAD_MIN_UTTERANCE_SEC, VAD_MAX_UTTERANCE_SEC, VAD_NOISE_FLOOR,
  VAD_THRESHOLD_MULT, VAD_MIN_THRESHOLD
"""

import collections
import queue
import threading
import time

import numpy as np
import sounddevice as sd

import config

# Rates real devices actually use; measured rates get snapped to these
# (same trick as audio.py - AirPods report one rate and deliver another).
_COMMON_RATES = [8000, 16000, 22050, 24000, 32000, 44100, 48000]


class SpeechDetector:
    """Frame-based energy VAD. Feed arbitrary chunks of float32 mono audio
    at `samplerate`; on_utterance(audio) fires with the complete utterance
    (pre-roll and trailing hangover included) at that same rate."""

    def __init__(self, samplerate, on_utterance):
        sr = float(samplerate)
        self.samplerate = sr
        self.on_utterance = on_utterance

        frame_sec = getattr(config, "VAD_FRAME_SEC", 0.03)
        self.frame_len = max(1, int(sr * frame_sec))
        self.start_need = max(1, round(getattr(config, "VAD_START_SEC", 0.1) / frame_sec))
        self.end_need = max(1, round(getattr(config, "VAD_END_SEC", 1.0) / frame_sec))
        preroll = max(1, round(getattr(config, "VAD_PREROLL_SEC", 0.3) / frame_sec))
        self.min_samples = int(getattr(config, "VAD_MIN_UTTERANCE_SEC", 0.4) * sr)
        self.max_samples = int(getattr(config, "VAD_MAX_UTTERANCE_SEC", 30.0) * sr)
        self.floor_init = getattr(config, "VAD_NOISE_FLOOR", 0.003)
        self.mult = getattr(config, "VAD_THRESHOLD_MULT", 4.0)
        self.min_thresh = getattr(config, "VAD_MIN_THRESHOLD", 0.01)

        self._ring = collections.deque(maxlen=preroll)
        self.reset()

    @property
    def threshold(self):
        return max(self._floor * self.mult, self.min_thresh)

    def reset(self):
        """Drop all state, including buffered audio and the noise floor."""
        self._pending = np.zeros(0, dtype=np.float32)
        self._floor = self.floor_init
        self._clear_speech()

    def _clear_speech(self):
        self._ring.clear()
        self._hot = 0
        self._silence = 0
        self._speech = []
        self._speech_samples = 0
        self._in_speech = False

    def feed(self, chunk: np.ndarray):
        if chunk.ndim > 1:
            chunk = chunk[:, 0]
        self._pending = np.concatenate([self._pending, chunk.astype(np.float32, copy=False)])
        while len(self._pending) >= self.frame_len:
            frame = self._pending[: self.frame_len]
            self._pending = self._pending[self.frame_len :]
            self._frame(frame)

    def _frame(self, frame):
        rms = float(np.sqrt(np.mean(frame * frame)))
        hot = rms > self.threshold

        if not self._in_speech:
            self._ring.append(frame)
            if hot:
                self._hot += 1
                if self._hot >= self.start_need:
                    # Speech confirmed: start the utterance from the pre-roll
                    # ring (which already contains the triggering frames).
                    self._speech = list(self._ring)
                    self._speech_samples = sum(len(f) for f in self._speech)
                    self._silence = 0
                    self._in_speech = True
            else:
                self._hot = 0
                # Adapt the noise floor only while idle and quiet.
                self._floor = 0.95 * self._floor + 0.05 * rms
        else:
            self._speech.append(frame)
            self._speech_samples += len(frame)
            self._silence = 0 if hot else self._silence + 1
            if self._silence >= self.end_need or self._speech_samples >= self.max_samples:
                self._finish()

    def _finish(self):
        audio = np.concatenate(self._speech) if self._speech else np.zeros(0, np.float32)
        voiced = self._speech_samples - self._silence * self.frame_len
        self._clear_speech()
        if voiced >= self.min_samples and self.on_utterance:
            self.on_utterance(audio)


class HandsFreeListener:
    """Always-on microphone. Calls on_utterance(audio_16k) on a worker
    thread for every detected speech segment. is_paused() is polled from
    the audio callback: while True, incoming audio is discarded and the
    detector reset (so Jarvis's own voice never becomes an utterance)."""

    def __init__(self, on_utterance, is_paused=lambda: False, device=None, target_rate=16000):
        self.on_utterance = on_utterance
        self.is_paused = is_paused
        self.device = device
        self.target_rate = target_rate
        self._stream = None
        self._detector = None
        self._queue = queue.Queue()
        self._running = False
        self._reported_rate = float(target_rate)
        self._first_at = None
        self._sample_count = 0

    @property
    def running(self):
        return self._running

    def start(self, device=None):
        if self._stream is not None:
            return
        if device is not None:
            self.device = device
        self._first_at = None
        self._sample_count = 0
        self._queue = queue.Queue()

        def callback(indata, frames, time_info, status):
            data = indata[:, 0] if indata.ndim > 1 else indata
            if self._first_at is None:
                self._first_at = time.monotonic()
            self._sample_count += len(data)
            if self.is_paused():
                self._detector._clear_speech()
                return
            self._detector.feed(data.copy())

        self._stream = sd.InputStream(
            channels=1, dtype="float32", device=self.device, callback=callback
        )
        self._reported_rate = float(self._stream.samplerate)
        self._detector = SpeechDetector(self._reported_rate, self._queue.put)
        self._running = True
        threading.Thread(target=self._drain, daemon=True).start()
        self._stream.start()

    def stop(self):
        self._running = False
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None

    def _effective_rate(self):
        """Reported rate, corrected by wall-clock measurement when the
        driver is lying by a recognizable margin."""
        rate = self._reported_rate
        if self._first_at:
            elapsed = time.monotonic() - self._first_at
            if elapsed > 2.0:
                measured = self._sample_count / elapsed
                snapped = min(_COMMON_RATES, key=lambda r: abs(r - measured))
                if abs(snapped - measured) / snapped < 0.15:
                    rate = float(snapped)
        return rate

    def _drain(self):
        while self._running:
            try:
                audio = self._queue.get(timeout=0.5)
            except queue.Empty:
                continue
            rate = self._effective_rate()
            if rate != self.target_rate and len(audio):
                n = int(len(audio) * self.target_rate / rate)
                audio = np.interp(
                    np.linspace(0, len(audio) - 1, n),
                    np.arange(len(audio)),
                    audio,
                ).astype(np.float32)
            try:
                self.on_utterance(audio)
            except Exception as e:
                print(f"[handsfree error] {e}")
