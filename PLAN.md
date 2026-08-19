# PLAN.md — Jarvis roadmap

## Vision
A Jarvis-style voice assistant on macOS I can toggle with a hotkey, that
answers questions, spars with me in debate mode, and can listen to system
audio (videos, calls) and suggest responses. Built to learn from — I read
and understand every change.

## Architecture (current)
```
⌥Space toggle → audio.py (record) → stt.py (Whisper) → brain.py (LLM) → tts.py (say)
                          app.py = menu bar shell + state icon
                          config.py = all knobs (modes, hotkey, provider)
```

## Phases

### Phase 1 — Solid foundation (now)
Get the starter running reliably: mic input, all three modes, Claude API
provider, BlackHole system-audio capture verified end to end.

### Phase 2 — Feels fast
Latency is the whole game for a voice assistant.
- Stream LLM responses; start speaking sentence 1 while the rest generates
- Investigate smaller/faster Whisper settings vs. accuracy tradeoff
- Interrupt handling polish (barge-in)

### Phase 3 — Feels alive
- Wake word ("Hey Jarvis") via openWakeWord — replace/augment the hotkey
- Better voice: swap tts.py backend (ElevenLabs or similar), keep `say` as fallback
- Floating overlay indicator (Siri-style orb) instead of just menu bar icon

### Phase 4 — Actually does things
- Tool calling: give the brain tools (open apps, read clipboard, web search)
- Live listener mode: continuous chunked transcription of system audio
  instead of toggle recording

## Non-goals (for now)
- Windows/Linux support
- Packaging as a signed .app
- Multi-user anything
