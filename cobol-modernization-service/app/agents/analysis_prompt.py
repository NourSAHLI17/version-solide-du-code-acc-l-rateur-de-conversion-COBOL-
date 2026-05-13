"""System prompt text for LLM-backed COBOL semantic analysis (parser JSON → analysis JSON)."""

# v2.1 - prompt markdown uses doubled braces for JSON examples (LangChain str.format safe)

from pathlib import Path

_PROMPT_FILE = Path(__file__).resolve().parent.parent / "prompts" / "analysis_agent_system_prompt.md"

ANALYSIS_AGENT_SYSTEM_PROMPT = _PROMPT_FILE.read_text(encoding="utf-8")
