import sys
import time
from pathlib import Path

# Project root ah Python path la add pannurom (app folder import panna)
sys.path.append(str(Path(__file__).resolve().parent.parent))

import ollama
from app.core.config import settings


def main():
    print(f"Assistant Name : {settings.assistant_name}")
    print(f"Model          : {settings.ollama_model}")
    print(f"Ollama URL     : {settings.ollama_base_url}")
    print("-" * 40)

    client = ollama.Client(host=settings.ollama_base_url)

    messages = [
        {
            "role": "system",
            "content": f"You are {settings.assistant_name}, a helpful personal AI assistant. Keep answers short.",
        },
        {"role": "user", "content": "Introduce yourself in 2 lines."},
    ]

    start = time.time()
    print("Streaming response:\n")

    # stream=True => words oru oru ah varum (ChatGPT maadhiri)
    for chunk in client.chat(
        model=settings.ollama_model, messages=messages, stream=True
    ):
        print(chunk["message"]["content"], end="", flush=True)

    print(f"\n\nTime taken: {time.time() - start:.2f} seconds")


if __name__ == "__main__":
    main()