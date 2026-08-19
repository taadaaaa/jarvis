"""All the knobs in one place."""

# --- LLM provider ---------------------------------------------------------
# "anthropic" -> Claude API (put ANTHROPIC_API_KEY in a .env file)
# "ollama"    -> local model via Ollama (install from ollama.com, then
#                `ollama pull llama3.1`)
PROVIDER = "ollama"  # switch to "anthropic" anytime (needs ANTHROPIC_API_KEY in .env)
MODEL = None  # None = provider default (claude-sonnet-4-6 / llama3.1)

# --- Speech ---------------------------------------------------------------
WHISPER_MODEL = "base.en"  # tiny.en | base.en | small.en

# Voice output. "elevenlabs" needs ELEVENLABS_API_KEY in .env and falls
# back to the macOS voice on any API problem.
TTS_PROVIDER = "elevenlabs"           # "elevenlabs" | "say"
TTS_VOICE = "Samantha"                # macOS voice (`say -v '?'` lists them)
# Premade "Adam" - free tier OK. The community voice Matt picked
# (bfGb7JTLUnZebZRiFYyq, "Adam - AI Narrative Story Voice") needs a paid
# ElevenLabs plan for API use; swap the ID back if you upgrade.
ELEVENLABS_VOICE_ID = "pNInz6obpgDQGcFmaJgB"
ELEVENLABS_MODEL = "eleven_flash_v2_5"        # fast+cheap; try eleven_multilingual_v2 for quality

# --- Hotkey ---------------------------------------------------------------
# pynput syntax. <alt> is the Option key on macOS.
HOTKEY = "<alt>+<space>"
HOTKEY_LABEL = "⌥ Space"

# --- Conversation ---------------------------------------------------------
MAX_HISTORY_TURNS = 12  # user+assistant pairs kept in context
MAX_TOOL_ROUNDS = 5     # max tool-call rounds per turn (see tools.py)

# --- Modes ------------------------------------------------------------------
# Add your own! Each mode is just a system prompt.
MODES = {
    "assistant": (
        "You are Jarvis, a voice assistant. Your replies will be read aloud "
        "by text-to-speech, so keep them conversational, concise (2-4 "
        "sentences unless asked for more), and free of markdown, bullet "
        "points, or formatting. Be direct and useful."
    ),
    "debate": (
        "You are a sharp debate partner and coach. The user is practicing "
        "argumentation. When they make a point, either (a) steelman the "
        "opposing side and push back with the strongest counterargument, or "
        "(b) if they ask for help, give them the most persuasive framing and "
        "evidence for their position. Point out logical fallacies when you "
        "hear them. Replies are read aloud: keep them punchy, spoken-word "
        "style, no formatting, under 5 sentences."
    ),
    "listener": (
        "You are listening to audio from a video, meeting, or another person "
        "(not the user themselves). The transcript you receive is what was "
        "said in that audio. Summarize the key claims being made and suggest "
        "a smart, concise response or rebuttal the user could give. Replies "
        "are read aloud: no formatting, be brief and concrete."
    ),
}
DEFAULT_MODE = "assistant"
