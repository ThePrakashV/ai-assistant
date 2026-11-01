import asyncio
import json

import websockets

URL = "ws://127.0.0.1:8000/ws/chat"


async def main():
    async with websockets.connect(URL) as ws:
        ready = json.loads(await ws.recv())
        name = ready.get("assistant", "Assistant")
        print(f"Connected to {name}. Type 'exit' to quit, '/reset' to clear memory.")

        while True:
            # input() blocking so thread la run pannurom
            text = await asyncio.to_thread(input, "\nYou: ")
            text = text.strip()

            if text.lower() in {"exit", "quit"}:
                break

            if text == "/reset":
                payload = {"type": "reset"}
            else:
                payload = {"type": "message", "text": text}

            await ws.send(json.dumps(payload))
            print(f"{name}: ", end="", flush=True)

            # done / error / reset_ok varaikkum messages padikkirom
            while True:
                data = json.loads(await ws.recv())

                if data["type"] == "token":
                    print(data["text"], end="", flush=True)
                elif data["type"] == "done":
                    print(f"\n[{data['seconds']}s]")
                    break
                elif data["type"] == "reset_ok":
                    print("Memory cleared.")
                    break
                elif data["type"] == "error":
                    print(f"\n[ERROR] {data['message']}")
                    break


if __name__ == "__main__":
    asyncio.run(main())