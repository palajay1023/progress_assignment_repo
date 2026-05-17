from dotenv import load_dotenv
import os

load_dotenv()

# Generic LLM config — works with any OpenAI-compatible provider
# Fallbacks keep existing .env files (OPENROUTER_API_KEY / CLAUDE_MODEL) working
LLM_API_KEY = os.getenv("LLM_API_KEY") or os.getenv("OPENROUTER_API_KEY", "")
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.openai.com/v1")
LLM_MODEL = os.getenv("LLM_MODEL") or os.getenv("CLAUDE_MODEL", "gpt-4o")

TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "")
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./market_intelligence.db")
