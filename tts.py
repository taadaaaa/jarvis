"""Text-to-speech. Two backends, chosen by TTS_PROVIDER in config.py:

  - "say":        macOS built-in voice. Free, instant, robotic.
  - "elevenlabs": ElevenLabs API. Natural voice; needs ELEVENLABS_API_KEY
                  in .env. Falls back to `say` per-utterance on any API
                  error (bad key, quota, offline), so Jarvis never goes mute.

Both run a background worker: feed() queues sentences and returns
immediately, wait() blocks until playback finishes, stop() interrupts
mid-word and drops the queue. Callers use make_speaker().
"""

import os
import queue
import subprocess
import tempfile
import threading

import requests

import config


class _BaseSpeaker:
    """Queue + worker shared by all backends. Subclasses implement
    _start_proc(text) -> subprocess.Popen of something playing audio."""

    def __init__(self):
        self._queue = queue.Queue()
        self._proc = None
        self._skip = False  # set by stop(); dropped by the next feed()
        self._lock = threading.Lock()
        threading.Thread(target=self._worker, daemon=True).start()

    def feed(self, text: str):
        """Queue text to be spoken after whatever is already playing."""
        if not text.strip():
            return
        with self._lock:
            self._skip = False
        self._queue.put(text)

    def say(self, text: str):
        """Speak text and block until finished (non-streaming path)."""
        self.feed(text)
        self.wait()

    def wait(self):
        """Block until everything queued has been spoken (or stopped)."""
        self._queue.join()

    def stop(self):
        """Interrupt: drop queued text and kill the current utterance."""
        try:
            while True:
                self._queue.get_nowait()
                self._queue.task_done()
        except queue.Empty:
            pass
        with self._lock:
            self._skip = True
            if self._proc and self._proc.poll() is None:
                self._proc.terminate()

    def _worker(self):
        while True:
            text = self._queue.get()
            try:
                # _start_proc may be slow (API download): run it outside the
                # lock, then re-check skip before playing.
                proc = self._start_proc(text)
                with self._lock:
                    if self._skip:
                        proc.terminate()
                        continue
                    self._proc = proc
                proc.wait()
            except Exception as e:
                print(f"[tts error] {e}")
            finally:
                with self._lock:
                    self._proc = None
                self._queue.task_done()

    def _start_proc(self, text):
        raise NotImplementedError


class SaySpeaker(_BaseSpeaker):
    def __init__(self, voice="Samantha", rate=190):
        self.voice = voice
        self.rate = rate
        super().__init__()

    def _start_proc(self, text):
        return subprocess.Popen(
            ["say", "-v", self.voice, "-r", str(self.rate), text]
        )


class ElevenLabsSpeaker(_BaseSpeaker):
    def __init__(self, api_key, voice_id, model_id, fallback_voice="Samantha"):
        self.api_key = api_key
        self.voice_id = voice_id
        self.model_id = model_id
        self.fallback = fallback_voice
        super().__init__()

    def _start_proc(self, text):
        try:
            r = requests.post(
                f"https://api.elevenlabs.io/v1/text-to-speech/{self.voice_id}",
                params={"output_format": "mp3_44100_128"},
                headers={"xi-api-key": self.api_key},
                json={"text": text, "model_id": self.model_id},
                timeout=30,
            )
            r.raise_for_status()
            f = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
            f.write(r.content)
            f.close()
            # afplay is built into macOS; -q 1 = high quality resampling
            return subprocess.Popen(["afplay", "-q", "1", f.name])
        except Exception as e:
            detail = ""
            if getattr(e, "response", None) is not None:
                detail = f" ({e.response.text[:200]})"
            print(f"[elevenlabs error, falling back to say] {e}{detail}")
            return subprocess.Popen(["say", "-v", self.fallback, text])


def make_speaker():
    """Build the speaker configured in config.py."""
    if config.TTS_PROVIDER == "elevenlabs":
        key = os.environ.get("ELEVENLABS_API_KEY")
        if key:
            return ElevenLabsSpeaker(
                api_key=key,
                voice_id=config.ELEVENLABS_VOICE_ID,
                model_id=config.ELEVENLABS_MODEL,
                fallback_voice=config.TTS_VOICE,
            )
        print("[tts] ELEVENLABS_API_KEY not set - using macOS voice instead")
    return SaySpeaker(voice=config.TTS_VOICE)


# Backwards-compatible name (older code imported Speaker directly)
Speaker = SaySpeaker
