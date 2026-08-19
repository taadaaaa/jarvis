# Jarvis 🎙️

A macOS menu bar voice assistant. Press a hotkey, talk, get a spoken reply from Claude (or a local model). Can also listen to **system audio** — videos, calls, other people — and help you respond.

## How it works

```
⌥Space toggle → record audio → Whisper (local STT) → Claude API or Ollama → macOS TTS
```

The menu bar icon shows state: 🎙️ idle → 🔴 listening → 🧠 thinking → 🔊 speaking.

## Setup

```bash
cd jarvis
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

**If using Claude (default):** create a `.env` file:

```
ANTHROPIC_API_KEY=sk-ant-...
```

Get a key at console.anthropic.com. (Note: this uses the API, which is billed separately from a Claude.ai subscription — pay-per-use, and voice chats cost pennies.)

**If using a local model instead:** install [Ollama](https://ollama.com), run `ollama pull llama3.1`, and in `config.py` set `PROVIDER = "ollama"`.

## Run it

```bash
python app.py
```

macOS will prompt for two permissions the first time:

1. **Microphone** — for recording you.
2. **Accessibility / Input Monitoring** (System Settings → Privacy & Security) — required for the global hotkey to work. Grant it to your terminal app (Terminal/iTerm/VS Code).

Then: press **⌥ Space**, speak, press **⌥ Space** again. Jarvis thinks, then talks. Press the hotkey while it's speaking to interrupt it.

The first run downloads the Whisper model (~150 MB), so give it a minute.

## Modes (menu bar → Mode)

- **Assistant** — general quick answers
- **Debate** — pushes back on your arguments, flags fallacies, helps you sharpen points
- **Listener** — assumes the audio is *someone else* (a video, a call) and suggests responses/rebuttals for you

## Listening to system audio (videos, calls)

macOS apps can't hear system audio directly — you need a free virtual audio driver:

```bash
brew install blackhole-2ch
```

Then in **Audio MIDI Setup** (built into macOS):

1. Click **+** → **Create Multi-Output Device**; check both your speakers *and* BlackHole 2ch.
2. Set that Multi-Output Device as your Mac's sound output (so you still hear everything).

Now in Jarvis: **menu bar → Audio Source → System Audio (BlackHole)**, switch to **Listener** mode, and toggle recording while the video/call plays. Jarvis will transcribe what it hears and suggest a response.

Switch back to **Microphone** to talk to it yourself.

## Customizing

Everything lives in `config.py`:

- Add new modes (they're just system prompts)
- Change the hotkey, Whisper model size, TTS voice (`say -v '?'` lists voices)
- Swap `MODEL` to any Claude model or Ollama model

## Upgrade ideas (roughly in order of payoff)

1. **Better voice** — swap `tts.py` for ElevenLabs or OpenAI TTS (the `Speaker` class is designed to be replaced).
2. **Wake word** ("Hey Jarvis") — add [openWakeWord](https://github.com/dscripka/openWakeWord) or Porcupine so you don't need the hotkey.
3. **Streaming replies** — stream the LLM response and start speaking the first sentence while the rest generates; cuts perceived latency a lot.
4. **Tools** — give Claude tool definitions (open apps, search web, read clipboard) so Jarvis can *do* things, not just talk.
5. **Live listener mode** — continuously transcribe system audio in chunks instead of toggle-based recording.
