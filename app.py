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
from handsfree import HandsFreeListener
from stt import Transcriber
from brain import Brain
from tts import make_speaker
from window import ChatWindow
import config
import tools

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
        self.handsfree = None  # HandsFreeListener when hands-free mode is on
        tools.SWITCH_BRAIN_HOOK = self.switch_brain

        # --- Command Center window ---------------------------------------
        self.window = ChatWindow.alloc().init().setup(
            on_talk=self.toggle, on_command=self.on_command
        )
        self.brain.on_tool = lambda name, result: self.window.add_tool(
            f"{name}: {result[:140]}"
        )
        self.window.start_stats()
        threading.Timer(2.0, self.push_info).start()

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

        self.hf_item = rumps.MenuItem("Hands-Free Mode", callback=self.toggle_handsfree)

        brain_menu = []
        for label, target in self.list_brains():
            item = rumps.MenuItem(label, callback=self.set_brain_from_menu)
            item.target_name = target
            brain_menu.append(item)

        self.menu = [
            rumps.MenuItem(
                f"Toggle Listening ({config.HOTKEY_LABEL})",
                callback=lambda _: self.toggle(),
            ),
            self.hf_item,
            rumps.MenuItem("Show Command Center", callback=lambda _: self.window.show()),
            None,
            ("Mode", mode_menu),
            ("Brain", brain_menu),
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

    def on_command(self, cmd: str, target=None):
        if cmd == "interrupt":
            self.brain.cancel()
            self.speaker.stop()
        elif cmd == "clear":
            self.clear_history(None)
        elif cmd == "handsfree":
            self.toggle_handsfree(None)
        elif cmd == "brain" and target:
            self.switch_brain(target)

    # --- Brain switching --------------------------------------------------

    def list_brains(self):
        """[(label, target)] for the menu: installed Ollama models + Claude."""
        import requests as _rq

        brains = []
        try:
            tags = _rq.get("http://localhost:11434/api/tags", timeout=2).json()
            for m in tags.get("models", []):
                brains.append((m["name"].split(":")[0].title() + " (local)", m["name"]))
        except Exception:
            brains.append(("Llama3.1 (local)", "llama3.1"))
        from brain import CLAUDE_CLI

        if CLAUDE_CLI:
            brains.append(("Claude Code (your account)", "claude-code"))
        brains.append(("Claude (API)", "claude"))
        return brains

    def set_brain_from_menu(self, sender):
        self.switch_brain(sender.target_name)

    def switch_brain(self, target: str) -> str:
        result = self.brain.switch(target)
        self.window.add_note(result)
        threading.Thread(target=self.push_info, daemon=True).start()
        return result

    # --- Hands-free mode ----------------------------------------------------

    def toggle_handsfree(self, _):
        if self.handsfree:
            self.handsfree.stop()
            self.handsfree = None
        else:
            self.handsfree = HandsFreeListener(
                on_utterance=self.on_utterance,
                is_paused=lambda: self.busy or self.is_recording,
                device=self.input_device,
            )
            self.handsfree.start()
        on = self.handsfree is not None
        self.hf_item.state = on
        self.window.set_handsfree(on)
        wake = f' Say "{config.WAKE_WORD}" to get my attention.' if config.WAKE_WORD and on else ""
        self.window.add_note(f"Hands-free mode {'on' if on else 'off'}.{wake}")
        if on:
            self.speaker.feed("Hands-free mode on.")
        else:
            self.speaker.feed("Hands-free mode off.")

    def on_utterance(self, audio):
        """A hands-free utterance finished. Transcribe, gate on the wake
        word, and respond - unless Jarvis is already mid-conversation."""
        if self.busy or self.is_recording:
            return
        self.busy = True
        try:
            text = self.transcriber.transcribe(audio)
            if not text.strip():
                return
            if config.WAKE_WORD and config.WAKE_WORD.lower() not in text.lower():
                print(f"[ignored - no wake word] {text}")
                return
            self.set_state("thinking")
            self._converse(text)
        except Exception as e:
            print(f"[error] {e}")
            self.window.add_note(f"Error: {e}")
        finally:
            self.set_state("idle")
            self.busy = False

    def push_info(self):
        """Populate the Core Systems panel with real component status."""
        import os

        import requests as _rq

        cards = []
        current = self.brain.model or "llama3.1"
        try:
            tags = _rq.get("http://localhost:11434/api/tags", timeout=2).json()
            for m in tags.get("models", []):
                name = m["name"]
                active = self.brain.provider == "ollama" and (
                    name == current or name.split(":")[0] == current.split(":")[0]
                )
                cards.append(
                    {
                        "name": name.split(":")[0].title(),
                        "status": "Local · tap to use",
                        "on": True,
                        "target": name,
                        "active": active,
                    }
                )
        except Exception:
            cards.append({"name": "Ollama", "status": "Offline", "on": False})
        from brain import CLAUDE_CLI

        if CLAUDE_CLI:
            cards.append(
                {
                    "name": "Claude Code",
                    "status": "Your account · tap to use",
                    "on": True,
                    "target": "claude-code",
                    "active": self.brain.provider == "claude-code",
                }
            )
        claude_linked = bool(os.environ.get("ANTHROPIC_API_KEY"))
        cards.append(
            {
                "name": "Claude API",
                "status": ("Linked · tap to use" if claude_linked else "Not linked"),
                "on": claude_linked,
                "target": "claude",
                "active": self.brain.provider == "anthropic",
            }
        )
        cards.append(
            {
                "name": "ElevenLabs",
                "status": "Connected" if os.environ.get("ELEVENLABS_API_KEY") else "Not linked",
                "on": bool(os.environ.get("ELEVENLABS_API_KEY")),
            }
        )
        cards.append(
            {"name": "Whisper", "status": f"Local · {config.WHISPER_MODEL}", "on": True}
        )
        cards.append(
            {"name": "Vision", "status": f"Local · {config.VISION_MODEL}", "on": True}
        )
        self.window.set_info(
            {"cards": cards, "mode": self.brain.mode.title(), "operator": "Matt"}
        )

    # --- Menu callbacks ------------------------------------------------

    def set_mode(self, sender):
        for name, item in self.mode_items.items():
            item.state = item is sender
            if item is sender:
                self.brain.set_mode(name)
        self.window.add_note(f"Mode: {sender.title}")
        self.window.set_info({"cards": None, "mode": sender.title})

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
            threading.Thread(target=self.process, args=(audio,), daemon=True).start()

    def process(self, audio):
        self.busy = True
        try:
            text = self.transcriber.transcribe(audio)
            if not text.strip():
                self.window.add_note("(heard nothing)")
                return
            self._converse(text)
        except Exception as e:
            print(f"[error] {e}")
            self.window.add_note(f"Error: {e}")
        finally:
            self.set_state("idle")
            self.busy = False

    def _converse(self, text):
        """Shared reply path: stream sentences to the speaker and window."""
        print(f"[you] {text}")
        self.window.add_user(text)
        sentences = []
        for sentence in self.brain.respond_stream(text):
            if not sentences:
                self.set_state("speaking")
            sentences.append(sentence)
            self.window.add_reply(sentence)
            self.speaker.feed(sentence)
        self.speaker.wait()
        print(f"[jarvis] {' '.join(sentences)}")


if __name__ == "__main__":
    # Regular app: Dock icon + windows. (The menu bar item still works.)
    from AppKit import NSApplication, NSApplicationActivationPolicyRegular

    NSApplication.sharedApplication().setActivationPolicy_(
        NSApplicationActivationPolicyRegular
    )
    app = JarvisApp()
    app.window.show()
    app.run()
