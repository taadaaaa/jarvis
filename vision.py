"""Screen vision: capture the display and ask a multimodal model about it.

Used by the look_at_screen tool. Provider is picked automatically:
Claude vision when ANTHROPIC_API_KEY is set, otherwise a local Ollama
vision model (VISION_MODEL in config, default gemma3:4b).

The app needs macOS Screen Recording permission the first time.
"""

import base64
import os
import subprocess
import tempfile

import requests

import config

_VOICE_HINT = " Answer concisely for text-to-speech, 2-4 sentences."


def capture_screen() -> str:
    """Screenshot the main display to a temp png, downscaled for the model.

    Returns the png path; caller (or describe_screen) deletes it.
    """
    f = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
    f.close()
    subprocess.run(
        ["screencapture", "-x", "-C", f.name], check=True, timeout=15
    )
    # Downscale so the longest side is <= 1344px - plenty for the model,
    # much cheaper to encode.
    subprocess.run(
        ["sips", "-Z", "1344", f.name],
        capture_output=True,
        timeout=15,
    )
    return f.name


def describe_screen(question: str) -> str:
    """Capture the screen and answer a question about it."""
    path = capture_screen()
    try:
        with open(path, "rb") as fp:
            png = fp.read()
        b64 = base64.b64encode(png).decode()
        prompt = question.strip() + _VOICE_HINT
        if os.environ.get("ANTHROPIC_API_KEY"):
            return _ask_claude(prompt, b64)
        return _ask_ollama(prompt, b64)
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


def _ask_claude(prompt: str, b64: str) -> str:
    import anthropic

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=500,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/png",
                            "data": b64,
                        },
                    },
                    {"type": "text", "text": prompt},
                ],
            }
        ],
    )
    return "".join(b.text for b in response.content if b.type == "text")


def _ask_ollama(prompt: str, b64: str) -> str:
    model = getattr(config, "VISION_MODEL", "gemma3:4b")
    try:
        response = requests.post(
            "http://localhost:11434/api/chat",
            json={
                "model": model,
                "messages": [
                    {"role": "user", "content": prompt, "images": [b64]}
                ],
                "stream": False,
            },
            timeout=120,
        )
        if response.status_code == 404:
            return (
                "The vision model is still downloading, try again in a few "
                "minutes."
            )
        response.raise_for_status()
        return response.json()["message"]["content"]
    except requests.RequestException as e:
        body = getattr(getattr(e, "response", None), "text", "") or ""
        if "not found" in body.lower():
            return (
                "The vision model is still downloading, try again in a few "
                "minutes."
            )
        return f"Could not analyze the screen: {e}"
