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

import json
import os
import re
import threading
from datetime import datetime

import requests
from dotenv import load_dotenv

import config
import tools

load_dotenv()

# Split after sentence-ending punctuation followed by whitespace.
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


class Brain:
    def __init__(self, provider="anthropic", model=None, mode="assistant"):
        self.provider = provider
        self.model = model
        self.history = []  # [{"role": "user"/"assistant", "content": str}]
        self.on_tool = None  # optional callback(name, result) for UI updates
        self._cancelled = threading.Event()
        self.set_mode(mode)

        if provider == "anthropic":
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

    def set_mode(self, mode: str):
        self.mode = mode
        self.system_prompt = config.MODES[mode]

    def clear(self):
        self.history = []

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
            "You have tools to open apps, read the clipboard, set the volume, "
            "check the weather, and look things up on Wikipedia. Use a tool "
            "only when the request actually requires one; for chat and "
            "questions you can answer yourself, just reply conversationally "
            "as normal. After a tool returns, answer out loud based on the "
            "result; don't narrate the mechanics."
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
        acc_text, acc_calls = "", []
        with requests.post(
            "http://localhost:11434/api/chat",
            json={
                "model": self.model or "llama3.1",
                "messages": [{"role": "system", "content": self._system()}] + msgs,
                "tools": tools.ollama_tools(),
                "stream": True,
            },
            stream=True,
            timeout=120,
        ) as response:
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
