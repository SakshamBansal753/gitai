# gitai/config.py
import json
import os
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# 1. Load project .env if present (in current directory or package parent)
env_candidates = [
    os.path.join(os.getcwd(), ".env"),
    os.path.join(BASE_DIR, ".env"),
    os.path.join(os.path.dirname(BASE_DIR), ".env"),
]
for ep in env_candidates:
    if os.path.exists(ep):
        load_dotenv(ep)
        break
else:
    load_dotenv()

# 2. User home directory configuration (~/.gitai/config.json)
USER_CONFIG_DIR = os.path.expanduser("~/.gitai")
USER_CONFIG_PATH = os.path.join(USER_CONFIG_DIR, "config.json")


def get_groq_api_key() -> str | None:
    """Return Groq API key from environment variable or ~/.gitai/config.json."""
    env_key = os.getenv("GROQ_API_KEY")
    if env_key and env_key.strip():
        return env_key.strip()

    if os.path.exists(USER_CONFIG_PATH):
        try:
            with open(USER_CONFIG_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                key = data.get("groq_api_key")
                if key and str(key).strip():
                    return str(key).strip()
        except Exception:
            pass
    return None


def set_groq_api_key(key: str):
    """Save Groq API key to ~/.gitai/config.json and set in environment."""
    clean_key = key.strip()
    global GROQ_API_KEY
    GROQ_API_KEY = clean_key
    os.environ["GROQ_API_KEY"] = clean_key

    try:
        os.makedirs(USER_CONFIG_DIR, exist_ok=True)
        data = {}
        if os.path.exists(USER_CONFIG_PATH):
            try:
                with open(USER_CONFIG_PATH, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                data = {}
        data["groq_api_key"] = clean_key
        with open(USER_CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception:
        pass


GITAI_WORKSPACE_DIR = os.getenv("GITAI_WORKSPACE_DIR", os.path.expanduser("~/GitAI_Workspace"))
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
ROUTER_MODEL = os.getenv("ROUTER_MODEL", "llama3.2")
EMBED_MODEL = os.getenv("EMBED_MODEL", "nomic-embed-text")

GROQ_API_KEY = get_groq_api_key()
GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")

CHROMA_DIR = os.getenv("CHROMA_DIR", os.path.join(BASE_DIR, "chroma_db"))
CHROMA_COLLECTION = os.getenv("CHROMA_COLLECTION", "gitai_tools")
RETRIEVAL_K = int(os.getenv("RETRIEVAL_K", 3))

# Central Auth & Database Configuration (built-in defaults for zero-config user experience)
DEFAULT_DATABASE_URL = (
    "postgresql://neondb_owner:npg_SuXTK9Ghr0Jn@ep-damp-thunder-b4uwy2ol-pooler.c-6.us-east-2.aws.neon.tech/neondb?sslmode=require&hostaddr=52.14.39.200"
)
DEFAULT_CLERK_PUBLISHABLE_KEY = "pk_test_ZGVzaXJlZC1mbGFtaW5nby05MS5jbGVyay5hY2NvdW50cy5kZXYk"
DEFAULT_CLERK_SECRET_KEY = "sk_test_UeYMqOYo42Vdff9JuJyoAD6f6R4UYdSFT08tqrZHDO"
DEFAULT_CLERK_SIGNIN_URL = "https://desired-flamingo-91.accounts.dev/sign-in"

DATABASE_URL = os.getenv("DATABASE_URL") or DEFAULT_DATABASE_URL
CLERK_PUBLISHABLE_KEY = os.getenv("CLERK_PUBLISHABLE_KEY") or DEFAULT_CLERK_PUBLISHABLE_KEY
CLERK_SECRET_KEY = os.getenv("CLERK_SECRET_KEY") or DEFAULT_CLERK_SECRET_KEY
CLERK_SIGNIN_URL = os.getenv("CLERK_SIGNIN_URL") or DEFAULT_CLERK_SIGNIN_URL
AUTH_CALLBACK_PORT = int(os.getenv("AUTH_CALLBACK_PORT", 8787))

MCP_SERVERS = {
    "git_server": {"path": os.path.join(BASE_DIR, "git_server.py")},
    "github_server": {"path": os.path.join(BASE_DIR, "github_server.py")},
}
