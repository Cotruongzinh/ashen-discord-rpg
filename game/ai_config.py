import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


def _bool_env(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


@dataclass(frozen=True)
class AIConfig:
    enabled: bool
    model: str
    max_output_tokens: int
    timeout_seconds: float
    draft_auto_apply: bool


def get_ai_config() -> AIConfig:
    return AIConfig(
        enabled=_bool_env("ASHEN_AI_ENABLED", False) and bool(os.getenv("OPENAI_API_KEY")),
        model=os.getenv("OPENAI_MODEL", "gpt-5.5"),
        max_output_tokens=int(os.getenv("OPENAI_MAX_OUTPUT_TOKENS", "1200")),
        timeout_seconds=float(os.getenv("OPENAI_TIMEOUT_SECONDS", "25")),
        draft_auto_apply=_bool_env("ASHEN_AI_DRAFT_AUTO_APPLY", False),
    )
