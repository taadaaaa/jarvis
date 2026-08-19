"""All the knobs in one place."""

# --- LLM provider ---------------------------------------------------------
# "anthropic" -> Claude API (put ANTHROPIC_API_KEY in a .env file)
# "ollama"    -> local model via Ollama (install from ollama.com, then
#                `ollama pull llama3.1`)
PROVIDER = "anthropic"
MODEL = None  # None = provider default (claude-sonnet-4-6 / llama3.1)

# --- Speech ---------------------------------------------------------------
WHISPER_MODEL = "base.en"  # tiny.en | base.en | small.en
TTS_VOICE = "Samantha"     # run `say -v '?'` to list available voices

# --- Hotkey ---------------------------------------------------------------
# pynput syntax. <alt> is the Option key on macOS.
HOTKEY = "<alt>+<space>"
HOTKEY_LABEL = "⌥ Space"

# --- Conversation ---------------------------------------------------------
MAX_HISTORY_TURNS = 12  # user+assistant pairs kept in context

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
