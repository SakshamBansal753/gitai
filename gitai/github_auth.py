# gitai/github_auth.py
"""
Single shared source for GitHub authentication across the whole project.
Every file that needs a GitHub token or client imports from here.
Token priority: Clerk-issued token (if logged in) > GITHUB_TOKEN environment variable.
"""

import os
from dotenv import load_dotenv
from github import Github, Auth

try:
    from .auth import get_cached_github_token
except (ImportError, ValueError):
    from auth import get_cached_github_token

load_dotenv()


def get_token() -> str | None:
    clerk_token = get_cached_github_token()
    if clerk_token:
        return clerk_token
    return os.environ.get("GITHUB_TOKEN")


def get_client() -> Github:
    token = get_token()
    return Github(auth=Auth.Token(token)) if token else Github()


def get_authed_clone_url(clone_url: str) -> str:
    token = get_token()
    if token:
        return clone_url.replace("https://", f"https://{token}@")
    return clone_url
