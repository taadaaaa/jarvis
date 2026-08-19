"""Text-to-speech using macOS's built-in `say` command.

Zero-dependency and instant. Swap this class for ElevenLabs / OpenAI TTS /
Kokoro later if you want a more natural voice - the interface is just
say(text) and stop().

Try voices with:  say -v '?'      (Samantha and Daniel are decent defaults)
"""

import subprocess


class Speaker:
    def __init__(self, voice="Samantha", rate=190):
        self.voice = voice
        self.rate = rate
        self._proc = None

    def say(self, text: str):
        self.stop()
        self._proc = subprocess.Popen(
            ["say", "-v", self.voice, "-r", str(self.rate), text]
        )
        self._proc.wait()
        self._proc = None

    def stop(self):
        if self._proc and self._proc.poll() is None:
            self._proc.terminate()
            self._proc = None
