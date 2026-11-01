from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    assistant_name: str = "Nova"
    # NOTE: OLLAMA_HOST nu name use panna Windows system variable conflict aagum.
    # So namma OLLAMA_BASE_URL use pannurom.
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "llama3.2:3b"

    # Phase 3: Whisper (Speech-to-Text)
    whisper_model: str = "base"
    whisper_compute_type: str = "int8"
    whisper_language: str = ""  # kaali = auto detect

    # Phase 4: Piper (Text-to-Speech)
    tts_model_path: str = "models/piper/en_US-lessac-medium.onnx"
    tts_speed: float = 1.0   # 1.0 normal, 1.5 = 1.5x fast, 0.8 = konjam slow
    tts_volume: float = 1.0  # 0.0 (mute) to 1.0 (full)

    # Phase 5: Wake word + continuous listening
    wake_word_model: str = "hey_jarvis"       # pre-trained name, illa custom .onnx path
    wake_word_display: str = "Hey Jarvis"     # screen la kaattura peyar
    wake_threshold: float = 0.5               # adhigam = strict
    wake_ack_text: str = "Yes?"               # wake aanadhum Nova solradhu
    listen_timeout: float = 6.0               # wake apparam pesa aarambikka wait (sec)
    followup_timeout: float = 8.0             # reply apparam follow-up ku wait (sec)

    # Phase 6: NLU (Intent + Entity)
    embed_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    intent_threshold: float = 0.45            # idhukku kammi na general_chat

    # Phase 7: Memory + RAG
    redis_url: str = "redis://127.0.0.1:6379/0"
    redis_ttl_seconds: int = 86400            # short-term history 24 hours ku apparam azhiyum
    memory_dir: str = "data/memory"           # FAISS index + facts (private, gitignore la irukku)
    docs_dir: str = "data/docs"               # RAG ku documents inga podunga
    memory_top_k: int = 3                     # evlo facts prompt ku anuppanum
    fact_threshold: float = 0.30              # fact similarity minimum
    rag_top_k: int = 3                        # evlo document chunks prompt ku anuppanum
    rag_threshold: float = 0.40               # document similarity minimum
    chunk_size: int = 500                     # oru chunk la max characters
    chunk_overlap: int = 80                   # periya paragraph split na overlap

    # Phase 8: Skills + Agent
    default_location: str = "Madurai"         # weather ku ooru sollala na idhu
    home_currency: str = "INR"                # "dollar rate" nu ketta idhukku convert
    scheduler_file: str = "data/scheduler.json"  # timers / reminders save aagura file
    http_timeout: float = 8.0                 # weather / currency / search API timeout (sec)

    # Phase 9: Task orchestration + monitoring
    max_steps: int = 5                        # oru request la max evlo steps
    max_parallel_steps: int = 3               # evlo steps onnaa parallel run
    step_retries: int = 1                     # network fail aana evlo dhadavai retry
    step_retry_delay: float = 1.0             # retry munnaadi wait (sec)
    tasks_keep: int = 100                     # Redis la evlo recent tasks vechikkanum
    task_ttl_seconds: int = 604800            # task record 7 days ku apparam azhiyum

    # Phase 10: MLflow tracking
    mlflow_enabled: bool = True               # False na tracking off
    mlflow_tracking_uri: str = "http://127.0.0.1:5000"
    mlflow_experiment: str = "nova-assistant"     # ovvoru task oru run
    mlflow_nlu_experiment: str = "nova-nlu-eval"  # eval_nlu.py runs
    mlflow_speaker_experiment: str = "nova-speaker-eval"  # speaker_tool.py calibrate runs
    mlflow_log_text: bool = True              # False na user sonna text MLflow la save aagaadhu

    # Phase 11: Web / multi-platform clients
    api_token: str = ""                       # kaali = auth illa (localhost mattum). LAN ku kandippa token
    max_audio_seconds: int = 30               # oru voice message max length

    # Phase 12: Security & privacy
    encrypt_at_rest: bool = True              # facts / documents / reminders files encrypt
    security_dir: str = "data/security"       # key marker (key.id) inga. Key file fallback kooda
    offline_mode: bool = False                # True na internet skills (weather, currency, search) off
    disabled_skills: str = ""                 # comma separated, e.g. "web_search,weather"
    audit_file: str = "data/audit/audit.jsonl"
    audit_log_text: bool = False              # True na user sonna text audit la save aagum
    auth_max_failures: int = 5                # idhu varaikkum thappa token try pannalam
    auth_window_seconds: int = 60             # ...indha neram kulla
    auth_lockout_seconds: int = 300           # apparam evlo neram block

    # Phase 13: Voice biometrics (speaker verification)
    speaker_mode: str = "off"                 # "off" | "enforce" (enroll pannittu mattum enforce)
    speaker_model_path: str = "models/speaker/wespeaker_en_voxceleb_resnet34_LM.onnx"
    speaker_profile: str = "data/voice/voiceprint.json"   # encrypted (ENCRYPT_AT_REST=true na)
    speaker_threshold: float = 0.50           # cosine score idhukku mela na "nee thaan"
    speaker_min_seconds: float = 1.0          # idhukku kammi speech na verify panna mudiyaadhu
    speaker_trust_seconds: float = 20.0       # verify aana apparam chinna replies ("yes") ku allow window
    speaker_enroll_samples: int = 6           # enroll ku evlo sentences

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()