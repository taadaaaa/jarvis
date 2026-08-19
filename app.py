"""
Jarvis - macOS voice assistant.

Flow:  hotkey toggle -> record -> whisper STT -> LLM (Claude or Ollama) -> TTS

A chat window shows the conversation; the menu bar icon doubles as a
status indicator:  🎙️ idle   🔴 listening   🧠 thinking   🔊 speaking
"""

import threading

import rumps
from pynput import keyboard

from audio import Recorder, list_input_devices
from stt import Transcriber
from brain import Brain
from tts import make_speaker
from window import ChatWindow
import config

STATE_ICONS = {"idle": "🎙️", "listening": "🔴", "thinking": "🧠", "speaking": "🔊"}


class JarvisApp(rumps.App):
    def __init__(self):
        super().__init__("🎙️ Jarvis", quit_button="Quit Jarvis")

        self.recorder = Recorder(samplerate=16000)
        self.transcriber = Transcriber(model_size=config.WHISPER_MODEL)
        self.brain = Brain(
            provider=config.PROVIDER,
            model=config.MODEL,
            mode=config.DEFAULT_MODE,
        )
        self.speaker = make_speaker()

        self.is_recording = False
        self.busy = False
        self.input_device = None  # None = default microphone

        # --- Chat window ------------------------------------------------
        self.window = ChatWindow.alloc().init().setup(on_talk=self.toggle)
        self.brain.on_tool = lambda name, result: self.window.add_note(
            f"🔧 {name}: {result[:120]}"
        )

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
            rumps.MenuItem("Show Chat Window", callback=lambda _: self.window.show()),
            None,
            ("Mode", mode_menu),
            ("Audio Source", source_menu),
            rumps.MenuItem("Clear Conversation", callback=self.clear_history),
            None,
        ]

        # --- Global hotkey ---------------------------------------------
        self.hotkeys = keyboard.GlobalHotKeys({config.HOTKEY: self.toggle})
        self.hotkeys.start()

        # Audible startup confirmation.
        self.speaker.feed("Jarvis is ready.")

    def set_state(self, state: str):
        self.title = f"{STATE_ICONS[state]} Jarvis"
        self.window.set_state(state)

    # --- Menu callbacks ------------------------------------------------

    def set_mode(self, sender):
        for name, item in self.mode_items.items():
            item.state = item is sender
            if item is sender:
                self.brain.set_mode(name)
        self.window.add_note(f"Mode: {sender.title}")

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
        self.window.add_note("Conversation cleared")

    # --- Core loop -------------------------------------------------------

    def toggle(self):
        """Hotkey / button / menu entry point. Start or stop listening."""
        if self.busy:
            # Interrupt: cancel the in-flight generation and any speech.
            self.brain.cancel()
            self.speaker.stop()
            return
        if not self.is_recording:
            self.is_recording = True
            self.set_state("listening")
            self.recorder.start(device=self.input_device)
        else:
            self.is_recording = False
            self.set_state("thinking")
            audio = self.recorder.stop()
            peak = float(abs(audio).max()) if audio.size else 0.0
            self.window.add_note(
                f"debug: {audio.size} samples, {audio.size / 16000:.1f}s, "
                f"peak {peak:.4f}, rate {self.recorder._native_rate:.0f}"
            )
            threading.Thread(target=self.process, args=(audio,), daemon=True).start()

    def process(self, audio):
        self.busy = True
        try:
            text = self.transcriber.transcribe(audio)
            if not text.strip():
                self.window.add_note("(heard nothing)")
                return

            print(f"[you] {text}")
            self.window.add_user(text)
            # Stream: start speaking the first sentence while the rest
            # of the reply is still generating.
            sentences = []
            for sentence in self.brain.respond_stream(text):
                if not sentences:
                    self.set_state("speaking")
                sentences.append(sentence)
                self.window.add_reply(sentence)
                self.speaker.feed(sentence)
            self.speaker.wait()
            print(f"[jarvis] {' '.join(sentences)}")
        except Exception as e:
            print(f"[error] {e}")
            self.window.add_note(f"Error: {e}")
        finally:
            self.set_state("idle")
            self.busy = False


if __name__ == "__main__":
    # Regular app: Dock icon + windows. (The menu bar item still works.)
    from AppKit import NSApplication, NSApplicationActivationPolicyRegular

    NSApplication.sharedApplication().setActivationPolicy_(
        NSApplicationActivationPolicyRegular
    )
    app = JarvisApp()
    app.window.show()
    app.run()
