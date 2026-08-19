"""
Jarvis - macOS menu bar voice assistant.

Flow:  hotkey toggle -> record -> whisper STT -> LLM (Claude or Ollama) -> TTS

Menu bar icon doubles as the status indicator:
  🎙️ idle   🔴 listening   🧠 thinking   🔊 speaking
"""

import threading

import rumps
from pynput import keyboard

from audio import Recorder, list_input_devices
from stt import Transcriber
from brain import Brain
from tts import Speaker
import config


class JarvisApp(rumps.App):
    def __init__(self):
        super().__init__("🎙️", quit_button="Quit Jarvis")

        self.recorder = Recorder(samplerate=16000)
        self.transcriber = Transcriber(model_size=config.WHISPER_MODEL)
        self.brain = Brain(
            provider=config.PROVIDER,
            model=config.MODEL,
            mode=config.DEFAULT_MODE,
        )
        self.speaker = Speaker(voice=config.TTS_VOICE)

        self.is_recording = False
        self.busy = False
        self.input_device = None  # None = default microphone

        # --- Menu -----------------------------------------------------
        self.mode_items = {}
        mode_menu = []
        for mode in config.MODES:
            item = rumps.MenuItem(mode.title(), callback=self.set_mode)
            item.state = mode == config.DEFAULT_MODE
            self.mode_items[mode] = item
            mode_menu.append(item)

        self.source_items = {}
        source_menu = []
        for label in ("Microphone", "System Audio (BlackHole)"):
            item = rumps.MenuItem(label, callback=self.set_source)
            item.state = label == "Microphone"
            self.source_items[label] = item
            source_menu.append(item)

        self.menu = [
            rumps.MenuItem(
                f"Toggle Listening ({config.HOTKEY_LABEL})",
                callback=lambda _: self.toggle(),
            ),
            None,
            ("Mode", mode_menu),
            ("Audio Source", source_menu),
            rumps.MenuItem("Clear Conversation", callback=self.clear_history),
            None,
        ]

        # --- Global hotkey ---------------------------------------------
        self.hotkeys = keyboard.GlobalHotKeys({config.HOTKEY: self.toggle})
        self.hotkeys.start()

    # --- Menu callbacks ------------------------------------------------

    def set_mode(self, sender):
        for name, item in self.mode_items.items():
            item.state = item is sender
            if item is sender:
                self.brain.set_mode(name)
        rumps.notification("Jarvis", "Mode changed", f"Now in {sender.title} mode")

    def set_source(self, sender):
        for label, item in self.source_items.items():
            item.state = item is sender
        if "BlackHole" in sender.title:
            device = next(
                (i for i, name in list_input_devices() if "blackhole" in name.lower()),
                None,
            )
            if device is None:
                rumps.notification(
                    "Jarvis",
                    "BlackHole not found",
                    "Install it with: brew install blackhole-2ch (see README)",
                )
                self.source_items["Microphone"].state = True
                sender.state = False
                return
            self.input_device = device
        else:
            self.input_device = None

    def clear_history(self, _):
        self.brain.clear()
        rumps.notification("Jarvis", "Conversation cleared", "")

    # --- Core loop -------------------------------------------------------

    def toggle(self):
        """Hotkey / menu entry point. Start or stop a listening session."""
        if self.busy:
            # Pressing the hotkey while Jarvis is speaking interrupts it.
            self.speaker.stop()
            return
        if not self.is_recording:
            self.is_recording = True
            self.title = "🔴"
            self.recorder.start(device=self.input_device)
        else:
            self.is_recording = False
            self.title = "🧠"
            audio = self.recorder.stop()
            threading.Thread(target=self.process, args=(audio,), daemon=True).start()

    def process(self, audio):
        self.busy = True
        try:
            text = self.transcriber.transcribe(audio)
            if not text.strip():
                self.title = "🎙️"
                return

            print(f"[you] {text}")
            reply = self.brain.respond(text)
            print(f"[jarvis] {reply}")

            self.title = "🔊"
            self.speaker.say(reply)
        except Exception as e:
            print(f"[error] {e}")
            rumps.notification("Jarvis", "Error", str(e))
        finally:
            self.title = "🎙️"
            self.busy = False


if __name__ == "__main__":
    JarvisApp().run()
