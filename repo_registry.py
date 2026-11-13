# repo_registry.py
import json
import os
import config

USER_GITAI_DIR = os.path.expanduser("~/.gitai")
REGISTRY_PATH = os.path.join(USER_GITAI_DIR, "repo_registry.json")
LEGACY_REGISTRY_PATH = os.path.join(config.BASE_DIR, ".gitai_repo_registry.json")


def load_registry() -> dict:
    # 1. Try user home directory registry
    if os.path.exists(REGISTRY_PATH):
        try:
            with open(REGISTRY_PATH, "r", encoding="utf-8") as f:
                content = f.read().strip()
                if content:
                    return json.loads(content)
        except Exception:
            pass

    # 2. Fallback to legacy local file
    if os.path.exists(LEGACY_REGISTRY_PATH):
        try:
            with open(LEGACY_REGISTRY_PATH, "r", encoding="utf-8") as f:
                content = f.read().strip()
                if content:
                    return json.loads(content)
        except Exception:
            pass

    return {}


def save_registry(registry: dict):
    os.makedirs(USER_GITAI_DIR, exist_ok=True)
    try:
        with open(REGISTRY_PATH, "w", encoding="utf-8") as f:
            json.dump(registry, f, indent=2)
    except Exception:
        pass


def register_repo(name: str, path: str):
    registry = load_registry()
    abs_path = os.path.abspath(path)
    registry[name.lower()] = abs_path
    save_registry(registry)


def resolve_repo_path(name: str) -> str | None:
    """
    Intelligently resolves a repo path from:
    1. Saved registry
    2. Current directory (if user runs from inside a git repo or asks for current)
    3. GITAI_WORKSPACE_DIR
    4. Direct filesystem path
    """
    if not name:
        cwd = os.getcwd()
        if os.path.exists(os.path.join(cwd, ".git")):
            return cwd
        return None

    clean_name = name.strip().lower()

    # 1. Current directory keywords
    if clean_name in (".", "current", "here", "this"):
        return os.getcwd()

    # 2. Saved registry
    registry = load_registry()
    if clean_name in registry:
        path = registry[clean_name]
        if os.path.exists(path):
            return path

    # 3. Direct path on disk
    if os.path.exists(name) and os.path.isdir(name):
        abs_p = os.path.abspath(name)
        register_repo(clean_name, abs_p)
        return abs_p

    # 4. In GITAI_WORKSPACE_DIR
    workspace_dir = getattr(config, "GITAI_WORKSPACE_DIR", os.path.expanduser("~/GitAI_Workspace"))
    workspace_path = os.path.join(workspace_dir, name)
    if os.path.exists(workspace_path):
        abs_p = os.path.abspath(workspace_path)
        register_repo(clean_name, abs_p)
        return abs_p

    # 5. Check if current directory name matches
    cwd = os.getcwd()
    if os.path.basename(cwd).lower() == clean_name and os.path.exists(os.path.join(cwd, ".git")):
        register_repo(clean_name, cwd)
        return cwd

    # 6. Case-insensitive scan in workspace directory
    if os.path.exists(workspace_dir):
        try:
            for item in os.listdir(workspace_dir):
                if item.lower() == clean_name:
                    found_path = os.path.abspath(os.path.join(workspace_dir, item))
                    register_repo(clean_name, found_path)
                    return found_path
        except Exception:
            pass

    return None
