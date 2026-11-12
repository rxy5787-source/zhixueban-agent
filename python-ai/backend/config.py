import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = Path(os.getenv("AI_DATA_DIR", str(ROOT / "runtime"))).resolve()
AUTH_URL = os.getenv("AI_AUTH_URL", "http://127.0.0.1:8087").rstrip("/")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434/api/chat")
TEXT_MODEL = os.getenv("AI_TEXT_MODEL", "qwen3:1.7b")
VISION_MODEL = os.getenv("AI_VISION_MODEL", "qwen3-vl:2b-instruct")
MODEL_TIMEOUT = int(os.getenv("AI_MODEL_TIMEOUT", "180"))
MAX_FILE_BYTES = 20 * 1024 * 1024
MAX_FILES = 5
MAX_PARTS = 3
