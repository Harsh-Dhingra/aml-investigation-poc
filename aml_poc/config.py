import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
DATA = Path(os.environ.get("AML_DATA_DIR", ROOT / "data"))
RUNTIME = Path(os.environ.get("AML_RUNTIME_DIR", ROOT / "runtime"))


def agent_mode() -> str:
    mode = os.environ.get("AML_AGENT_MODE", "demo")
    if mode not in {"demo", "claude", "openai"}:
        raise ValueError("AML_AGENT_MODE must be demo, claude, or openai")
    return mode
