# Nova - Local Voice AI Assistant

A local, privacy-first personal voice assistant (Bixby / Google Assistant style) that runs on a normal laptop (8-12 GB RAM). Speech recognition, the LLM, memory, and voice biometrics all run on your machine. Only weather, currency, and Wikipedia lookups use the internet, and you can switch those off with Offline mode.

You can rename the assistant by changing `ASSISTANT_NAME` in `.env`.

## Features

| Area | What works |
|------|-----------|
| Voice in | Wake word ("Hey Jarvis" placeholder), continuous listening, Silero VAD, faster-whisper STT |
| Voice out | Piper TTS, speech speed + volume control |
| Understanding | Intent classification (MiniLM embeddings), entity extraction (LLM JSON + grounding check) |
| Skills | Weather, time/date, calculator, unit + currency conversion, Wikipedia search, timers, reminders, alarms, voice settings |
| Agentic | LangGraph agent, multi-step request planner, parallel execution, retry, partial-failure handling |
| Memory | Short-term (Redis), long-term facts (FAISS), Document Q&A (RAG) |
| Monitoring | Live Plotly dashboard (step timeline, latency, RAM/CPU), MLflow run tracking |
| Clients | Web app + PWA (text + mic), optional Electron desktop shell |
| Security | Encryption at rest (Fernet), OS keyring master key, HMAC-chained audit log, permissions, offline mode, rate limit, privacy dashboard (export/delete), voice biometrics |

## Architecture

```
                         +----------------------------+
   Browser / PWA ------->|  FastAPI + WebSocket       |
   Electron shell        |  (app/server.py)           |
   Voice script          +-------------+--------------+
   (wake_chat.py)                      |
                                       v
  Mic -> Wake word -> VAD -> [Speaker verify] -> Whisper STT
                                       |
                                       v
                    +------------------------------------+
                    |  Task Orchestrator (LangGraph)     |
                    |  plan -> execute (parallel) -> sum |
                    +------------------+-----------------+
                                       |
                                       v
                    +------------------------------------+
                    |  Agent (LangGraph)                 |
                    |  understand -> skill  or  chat     |
                    +--------+-----------------+---------+
                             |                 |
                   +---------v-----+   +-------v---------------+
                   | Skills        |   | LLM chat (Ollama)     |
                   | weather, timer|   | + facts + RAG context |
                   | calc, units...|   +-------+---------------+
                   +---------------+           |
                                       +-------v---------+
                                       | Memory          |
                                       | Redis (short)   |
                                       | FAISS (long/RAG)|
                                       +-----------------+
   Reply -> Piper TTS -> Speaker / WAV to browser

   Side services (Docker): Redis | MLflow | Dashboard (Plotly)
   Security layer: encryption, audit log, permissions, rate limit
```

## Tech Stack

Python 3.11, FastAPI, WebSocket, Pydantic, Ollama (`llama3.2:3b`), faster-whisper, Silero VAD, openWakeWord, Piper TTS, WeSpeaker (ONNX), sentence-transformers, FAISS, LangGraph, Redis, Docker Compose, MLflow, Plotly, PyTorch (CPU), TorchAudio, ONNX Runtime, cryptography, keyring, Electron (optional).

## Requirements

- Windows 10/11 (commands below are for CMD), Python 3.11
- 8-12 GB RAM
- [Ollama](https://ollama.com) installed
- Docker Desktop (for Redis, MLflow, dashboard)
- A microphone for voice mode

## Setup

```
git clone https://github.com/<your-username>/<repo-name>.git
cd <repo-name>

python -m venv venv
venv\Scripts\activate

pip install torch==2.4.1 torchaudio==2.4.1 --index-url https://download.pytorch.org/whl/cpu
pip install -r requirements.txt
pip check

copy .env.example .env
```

Download models:

```
ollama pull llama3.2:3b

mkdir models\piper
cd models\piper
python -m piper.download_voices en_US-lessac-medium
cd ..\..

python -c "import openwakeword.utils as u; u.download_models()"
python scripts\download_speaker_model.py
```

Start the Docker services and add the sample document:

```
docker compose up -d --build
mkdir data\docs
copy examples\home_notes.txt data\docs\home_notes.txt
python scripts\ingest_docs.py
python scripts\make_icons.py
```

## Run

| What | Command |
|------|---------|
| Web assistant (http://127.0.0.1:8010) | `uvicorn app.server:app --host 127.0.0.1 --port 8010` |
| Voice assistant (wake word, mic) | `python scripts\wake_chat.py` |
| Text test of the agent | `python scripts\test_orchestrator.py` |
| Live dashboard | http://127.0.0.1:8001/dashboard |
| MLflow | http://127.0.0.1:5001 |
| Privacy dashboard | http://127.0.0.1:8010/privacy |
| Desktop shell (optional) | `cd clients\desktop` then `npm install` and `npm start` |

Do not run `wake_chat.py` and the web server at the same time (RAM doubles and both would fire the same timers).

After `pip install -r requirements.txt`, if you get a wake word `NO_SUCHFILE` error, run the wake word model download again.

## Voice biometrics (optional)

```
python scripts\speaker_tool.py enroll
python scripts\speaker_tool.py calibrate --genuine 8
```

Then set `SPEAKER_MODE=enforce` and `SPEAKER_THRESHOLD=<number from calibrate>` in `.env`.

## Security notes

- `.env`, `data/`, `models/`, `certs/` are git-ignored. Never commit them.
- The master key lives in Windows Credential Manager. Back it up with `python scripts\security_tool.py export-key`. If the key is lost, encrypted data cannot be recovered.
- Set `API_TOKEN` before exposing the server to your LAN (`--host 0.0.0.0`).
- Voice biometrics is a convenience layer, not strong security. A recording or synthetic voice of the owner may be accepted (no anti-spoofing).
- Chat history and dashboard tasks in Redis are stored in plain text (with a TTL). Delete them from the privacy dashboard.

## Build phases

| Phase | Topic | Highlights |
|-------|-------|-----------|
| 1 | Environment + Ollama | venv, config, streaming LLM test |
| 2 | FastAPI + WebSocket | Token streaming chat, per-connection memory |
| 3 | Voice input | faster-whisper STT + Silero VAD |
| 4 | Voice output | Piper TTS, speed / volume, full voice loop |
| 5 | Wake word | openWakeWord, sleep / wake state machine |
| 6 | NLU | Intent classification + entity extraction |
| 7 | Memory + RAG | Redis, FAISS, document Q&A |
| 8 | Agents + skills | LangGraph agent, 9 skills, scheduler |
| 9 | Orchestration + dashboard | Multi-step parallel tasks, Plotly monitor |
| 10 | Docker + MLflow | Compose stack, tracking, NLU eval |
| 11 | Multi-platform clients | Web, PWA, Electron shell |
| 12 | Security + privacy | Encryption, audit log, permissions, privacy dashboard |
| 13 | Voice biometrics | WeSpeaker speaker verification |

Detailed write-ups (errors faced and fixes) are in [`docs/`](docs/).

## Known limitations

- `llama3.2:3b` is weak at Tamil / Tanglish and can hallucinate on live data. Skills answer weather, time, and math from real sources instead.
- "Hey Jarvis" is a placeholder wake word. A custom "Hey Nova" model is not trained yet.
- Phone access over HTTPS (mkcert) and the PWA install flow were not fully tested.
- Music control, smart home, news, calendar, translation, and native mobile apps are not built yet.

## Roadmap

Translation, news briefing, calendar, music control, smart-home integration, custom wake word, plugin system, native mobile clients.

## License

MIT, see [LICENSE](LICENSE).
