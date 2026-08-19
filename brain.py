"""The brain: sends transcribed text to an LLM and returns the reply.

Two providers, switchable in config.py:
  - "anthropic": Claude via the Anthropic API (needs ANTHROPIC_API_KEY in .env)
  - "ollama":    any local model served by Ollama (http://localhost:11434)
"""

import os

import requests
from dotenv import load_dotenv

import config

load_dotenv()


class Brain:
    def __init__(self, provider="anthropic", model=None, mode="assistant"):
        self.provider = provider
        self.model = model
        self.history = []  # [{"role": "user"/"assistant", "content": str}]
        self.set_mode(mode)

        if provider == "anthropic":
            import anthropic

            self.client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    def set_mode(self, mode: str):
        self.mode = mode
        self.system_prompt = config.MODES[mode]

    def clear(self):
        self.history = []

    def respond(self, text: str) -> str:
        self.history.append({"role": "user", "content": text})
        # Keep context from growing unbounded
        self.history = self.history[-config.MAX_HISTORY_TURNS * 2 :]

        if self.provider == "anthropic":
            reply = self._anthropic()
        elif self.provider == "ollama":
            reply = self._ollama()
        else:
            raise ValueError(f"Unknown provider: {self.provider}")

        self.history.append({"role": "assistant", "content": reply})
        return reply

    def _anthropic(self) -> str:
        response = self.client.messages.create(
            model=self.model or "claude-sonnet-4-6",
            max_tokens=1000,
            system=self.system_prompt,
            messages=self.history,
        )
        return "".join(b.text for b in response.content if b.type == "text")

    def _ollama(self) -> str:
        response = requests.post(
            "http://localhost:11434/api/chat",
            json={
                "model": self.model or "llama3.1",
                "messages": [{"role": "system", "content": self.system_prompt}]
                + self.history,
                "stream": False,
            },
            timeout=120,
        )
        response.raise_for_status()
        return response.json()["message"]["content"]
