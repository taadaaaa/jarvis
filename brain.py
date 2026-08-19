"""The brain: sends transcribed text to an LLM and returns the reply.

Replies stream: respond_stream() yields complete sentences as the model
generates them, so the speaker can start talking before the full reply
exists. cancel() aborts an in-flight generation (hotkey interrupt).

The model can also act: tools.py defines things Jarvis can do (open apps,
check weather, ...). Each turn runs an agent loop - the model may call
tools, get the results back, and continue, up to MAX_TOOL_ROUNDS.

Two providers, switchable in config.py:
  - "anthropic": Claude via the Anthropic API (needs ANTHROPIC_API_KEY in .env)
  - "ollama":    any local model served by Ollama (http://localhost:11434)
"""

import glob
import json
import os
import re
import shutil
import subprocess
import threading
from datetime import datetime

import requests
from dotenv import load_dotenv

import config
import tools

# Explicit path: the app bundle's cwd is not the project folder.
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

# Split after sentence-ending punctuation followed by whitespace.
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


def find_claude_cli():
    """Locate the Claude Code CLI (app bundles get a minimal PATH)."""
    path = shutil.which("claude")
    if path:
        return path
    candidates = glob.glob(
        os.path.expanduser("~/.nvm/versions/node/*/bin/claude")
    ) + [
        os.path.expanduser("~/.claude/local/claude"),
        "/opt/homebrew/bin/claude",
        "/usr/local/bin/claude",
    ]
    return next((c for c in sorted(candidates, reverse=True) if os.path.exists(c)), None)


CLAUDE_CLI = find_claude_cli()


class Brain:
    def __init__(self, provider="anthropic", model=None, mode="assistant"):
        self.provider = provider
        self.model = model
        self.history = []  # [{"role": "user"/"assistant", "content": str}]
        self.on_tool = None  # optional callback(name, result) for UI updates
        self._cancelled = threading.Event()
        self._cc_session = None  # Claude Code conversation id (--resume)
        self.set_mode(mode)

        if provider == "anthropic":
            self._ensure_anthropic()

    def _ensure_anthropic(self):
        """Create the Anthropic client on demand (also for runtime switches)."""
        if getattr(self, "client", None) is not None:
            return
        import anthropic

        key = os.environ.get("ANTHROPIC_API_KEY")
        if not key:
            raise RuntimeError(
                "ANTHROPIC_API_KEY is not set. Create a .env file in the "
                "project folder containing:\n\n"
                "    ANTHROPIC_API_KEY=sk-ant-...\n\n"
                "(get a key at console.anthropic.com), or set "
                'PROVIDER = "ollama" in config.py to use a local model.'
            )
        self.client = anthropic.Anthropic(api_key=key)

    def switch(self, target: str) -> str:
        """Switch provider/model at runtime. Returns a spoken-friendly result.

        target: 'claude'/'anthropic', 'ollama', or an Ollama model name.
        """
        t = (target or "").lower().strip()
        if t in ("claude-code", "claude code", "my claude", "my claude account", "claude account", "subscription"):
            if not CLAUDE_CLI:
                return "I can't find the Claude Code app on this Mac."
            self.provider = "claude-code"
            self.model = None
            return "Switched to Claude Code, using your Claude account."
        if t in ("claude", "anthropic", "claude api"):
            if not os.environ.get("ANTHROPIC_API_KEY"):
                return (
                    "I can't switch to Claude: no Anthropic API key is set. "
                    "Add ANTHROPIC_API_KEY to the .env file first."
                )
            self._ensure_anthropic()
            self.provider = "anthropic"
            self.model = None
            return "Switched to Claude."
        try:
            tags = requests.get(
                "http://localhost:11434/api/tags", timeout=3
            ).json()
            available = [m["name"] for m in tags.get("models", [])]
        except Exception:
            return "I can't switch to a local model: Ollama isn't responding."
        if t in ("ollama", "local", "llama"):
            self.provider = "ollama"
            self.model = None
            return "Switched to the local model, llama 3.1."
        match = next(
            (m for m in available if m == t or m.split(":")[0] == t), None
        )
        if match is None:
            names = ", ".join(m.split(":")[0] for m in available) or "none"
            return f"I don't have a model called {target}. Available: {names}."
        self.provider = "ollama"
        self.model = match
        return f"Switched to {match.split(':')[0]}."

    def set_mode(self, mode: str):
        self.mode = mode
        self.system_prompt = config.MODES[mode]

    def clear(self):
        self.history = []
        self._cc_session = None

    def cancel(self):
        """Abort the current respond_stream() at the next chunk."""
        self._cancelled.set()

    def respond(self, text: str) -> str:
        return " ".join(self.respond_stream(text))

    def _system(self) -> str:
        """System prompt plus facts the model can't know on its own.

        LLMs have no clock - without this they confidently invent dates.
        """
        now = datetime.now().strftime("%A, %B %d, %Y, %I:%M %p").replace(" 0", " ")
        return (
            f"{self.system_prompt}\n\nThe current date and time is {now}.\n"
            "You have tools to open apps and URLs, LOOK AT THE USER'S SCREEN "
            "(use look_at_screen whenever they ask about anything visible - "
            "a video, a game, an error, a document), check the current "
            "browser tab, search the web, Wikipedia, and their local files, "
            "read files and the clipboard, check weather, set volume, and "
            "switch AI models. Use a tool only when the request actually "
            "requires one; for chat and questions you can answer yourself, "
            "just reply conversationally as normal. After a tool returns, "
            "answer out loud based on the result; don't narrate the mechanics."
        )

    def respond_stream(self, text: str):
        """Yield the reply sentence-by-sentence, running tools as needed.

        Whatever was generated before a cancel() still lands in history, so
        the conversation stays consistent with what was actually spoken.
        Tool-call records stay local to the turn; history keeps only the
        plain text that was spoken.
        """
        self._cancelled.clear()
        self.history.append({"role": "user", "content": text})
        # Keep context from growing unbounded
        self.history = self.history[-config.MAX_HISTORY_TURNS * 2 :]

        msgs = list(self.history)  # working copy, accumulates tool records
        spoken = []
        try:
            for _ in range(config.MAX_TOOL_ROUNDS):
                if self.provider == "anthropic":
                    round_gen = self._anthropic_round(msgs)
                elif self.provider == "ollama":
                    round_gen = self._ollama_round(msgs)
                elif self.provider == "claude-code":
                    round_gen = self._claude_code_round(msgs)
                else:
                    raise ValueError(f"Unknown provider: {self.provider}")

                # Sentence-split the round's text; capture its tool calls
                # (a generator's return value) from StopIteration.
                buffer = ""
                calls = []
                while True:
                    try:
                        chunk = next(round_gen)
                    except StopIteration as stop:
                        calls = stop.value or []
                        break
                    if self._cancelled.is_set():
                        round_gen.close()
                        break
                    buffer += chunk
                    *complete, buffer = _SENTENCE_END.split(buffer)
                    for sentence in complete:
                        if sentence.strip():
                            spoken.append(sentence)
                            yield sentence
                if buffer.strip() and not self._cancelled.is_set():
                    spoken.append(buffer.strip())
                    yield buffer.strip()

                if not calls or self._cancelled.is_set():
                    break
                results = [
                    (call_id, name, tools.execute(name, args))
                    for call_id, name, args in calls
                ]
                for _, name, result in results:
                    print(f"[tool] {name} -> {result[:200]}")
                    if self.on_tool:
                        self.on_tool(name, result)
                self._append_results(msgs, results)
        finally:
            # The API requires alternating roles, so never leave a user
            # message unanswered - even if the reply was cut off early.
            reply = " ".join(spoken) or "[interrupted]"
            self.history.append({"role": "assistant", "content": reply})

    # --- Providers. Each round-generator yields text chunks and returns a
    # --- list of (call_id, tool_name, args) for any tool calls it made.

    def _anthropic_round(self, msgs):
        with self.client.messages.stream(
            model=self.model or "claude-sonnet-4-6",
            max_tokens=1000,
            system=self._system(),
            tools=tools.anthropic_tools(),
            messages=msgs,
        ) as stream:
            yield from stream.text_stream
            final = stream.get_final_message()
        msgs.append({"role": "assistant", "content": final.content})
        if final.stop_reason == "tool_use":
            return [
                (b.id, b.name, dict(b.input))
                for b in final.content
                if b.type == "tool_use"
            ]
        return []

    def _ollama_round(self, msgs):
        payload = {
            "model": self.model or "llama3.1",
            "messages": [{"role": "system", "content": self._system()}] + msgs,
            "tools": tools.ollama_tools(),
            "stream": True,
        }
        response = requests.post(
            "http://localhost:11434/api/chat", json=payload, stream=True, timeout=120
        )
        if response.status_code == 400 and "tool" in response.text.lower():
            # Model without tool support (e.g. gemma3): chat-only fallback.
            payload.pop("tools")
            response = requests.post(
                "http://localhost:11434/api/chat", json=payload, stream=True, timeout=120
            )
        acc_text, acc_calls = "", []
        with response:
            response.raise_for_status()
            for line in response.iter_lines():
                if not line:
                    continue
                data = json.loads(line)
                message = data.get("message", {})
                if content := message.get("content"):
                    acc_text += content
                    yield content
                if calls := message.get("tool_calls"):
                    acc_calls.extend(calls)
                if data.get("done"):
                    break
        assistant = {"role": "assistant", "content": acc_text}
        if acc_calls:
            assistant["tool_calls"] = acc_calls
        msgs.append(assistant)
        return [
            (None, c["function"]["name"], c["function"].get("arguments") or {})
            for c in acc_calls
        ]

    def _claude_code_round(self, msgs):
        """One turn through the Claude Code CLI (the user's Claude account).

        Claude Code brings its own read-only tools (files, web search), so
        Jarvis's tool loop is bypassed - this round always returns [].
        Conversation continuity comes from --resume with the session id.
        """
        prompt = msgs[-1]["content"]
        system = (
            f"{self.system_prompt}\n\n"
            "You are the brain of Jarvis, a voice assistant on the user's "
            "Mac, running through Claude Code. You may read files and search "
            "the web when helpful. Replies are spoken aloud by TTS: keep "
            "them conversational, concise, and free of markdown or code "
            "unless asked."
        )
        cmd = [
            CLAUDE_CLI, "-p", prompt,
            "--output-format", "stream-json",
            "--verbose", "--include-partial-messages",
            "--append-system-prompt", system,
            "--allowedTools", "Read", "Glob", "Grep", "WebSearch", "WebFetch",
        ]
        if self._cc_session:
            cmd += ["--resume", self._cc_session]
        env = dict(os.environ)
        env["PATH"] = os.path.dirname(CLAUDE_CLI) + ":" + env.get("PATH", "")
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            cwd=os.path.expanduser("~"),
            env=env,
        )
        try:
            for line in proc.stdout:
                try:
                    obj = json.loads(line)
                except ValueError:
                    continue
                if sid := obj.get("session_id"):
                    self._cc_session = sid
                if obj.get("type") == "stream_event":
                    event = obj.get("event", {})
                    delta = event.get("delta", {})
                    if delta.get("type") == "text_delta":
                        yield delta["text"]
                elif obj.get("type") == "result":
                    break
        finally:
            if proc.poll() is None:
                proc.terminate()
        return []

    def _append_results(self, msgs, results):
        if self.provider == "anthropic":
            msgs.append(
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": call_id,
                            "content": result,
                        }
                        for call_id, _, result in results
                    ],
                }
            )
        else:
            for _, _, result in results:
                msgs.append({"role": "tool", "content": result})
