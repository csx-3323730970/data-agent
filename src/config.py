from dotenv import load_dotenv
load_dotenv()

import os

LLM_API_KEY = os.environ["DEEPSEEK_API_KEY"]
LLM_BASE_URL = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
LLM_MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek-v4-flash")

PG_HOST = os.environ.get("PG_HOST", "localhost")
PG_PORT = int(os.environ.get("PG_PORT", "5432"))
PG_USER = os.environ.get("PG_USER", "postgres")
PG_PASSWORD = os.environ["PG_PASSWORD"]
PG_DATABASE = os.environ.get("PG_DATABASE", "data_agent")
PG_DSN = f"postgresql://{PG_USER}:{PG_PASSWORD}@{PG_HOST}:{PG_PORT}/{PG_DATABASE}"

MAX_TURNS = int(os.environ.get("MAX_TURNS", "20"))
CONTEXT_MAX_TOKENS = int(os.environ.get("CONTEXT_MAX_TOKENS", "8000"))
SQL_TIMEOUT_SECONDS = int(os.environ.get("SQL_TIMEOUT_SECONDS", "30"))
ASYNC_DELAY_SECONDS = int(os.environ.get("ASYNC_DELAY_SECONDS", "2"))
RECENT_FULL_ROUNDS = int(os.environ.get("RECENT_FULL_ROUNDS", "3"))
