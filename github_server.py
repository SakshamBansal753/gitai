# github_server.py
from fastmcp import FastMCP
from git import Repo as GitRepo
from github import Github, Auth
from repo_registry import register_repo
import os
import config
from github_auth import get_token, get_authed_clone_url

mcp = FastMCP("github_server")

_anon_gh = Github()  # unauthenticated fallback for public reads


def _get_client() -> Github:
    """Uses authenticated client if available, otherwise falls back to anon."""
    token = get_token()
    return Github(auth=Auth.Token(token)) if token else _anon_gh


def _get_authed_client() -> Github:
    """Build a fresh, per-call GitHub client bound to the current session's
    token. Never cache or reuse this across calls or users."""
    token = get_token()
    if token is None:
        raise PermissionError("Not logged in. Run 'login' first before using this tool.")
    return Github(auth=Auth.Token(token))


@mcp.tool()
def create_repo(repo_name: str, private: bool = False, description: str = "", local_path: str = "") -> dict:
    """Create a new GitHub repository, clone it locally into the user's environment,
    and register it so it can be referenced by name in future commands (e.g. add_files_to_branch).
    Requires the user to be logged in via Clerk."""
    try:
        gh = _get_authed_client()
        user = gh.get_user()
        # auto_init=True creates initial commit with README.md so repository files are visible immediately
        gh_repo = user.create_repo(name=repo_name, private=private, description=description, auto_init=True)

        if not local_path:
            target_path = os.path.join(config.GITAI_WORKSPACE_DIR, repo_name)
        else:
            norm_path = os.path.abspath(local_path)
            # If the user specified a parent folder (e.g. "./gitflow"), place the repo inside it
            if os.path.basename(norm_path).lower() != repo_name.lower():
                target_path = os.path.join(norm_path, repo_name)
            else:
                target_path = norm_path

        os.makedirs(os.path.dirname(os.path.abspath(target_path)), exist_ok=True)

        clone_url = get_authed_clone_url(gh_repo.clone_url)

        GitRepo.clone_from(clone_url, target_path)
        register_repo(repo_name, target_path)

        return {
            "status": "success",
            "repo_name": gh_repo.full_name,
            "url": gh_repo.html_url,
            "local_path": target_path,
            "registered_as": repo_name,
        }
    except PermissionError as e:
        return {"status": "error", "message": str(e)}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@mcp.tool()
def search_repo(query: str, language: str = "") -> dict:
    """Search public GitHub repositories by keyword and optional language filter.
    Works without login (read-only, public data)."""
    try:
        q = query if not language else f"{query} language:{language}"
        gh = _get_client()
        results = gh.search_repositories(query=q)
        repos = [{"full_name": r.full_name, "url": r.html_url, "stars": r.stargazers_count}
                 for r in results[:10]]
        return {"status": "success", "results": repos}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@mcp.tool()
def search_user_repo(username: str, query: str = "") -> dict:
    """Search repositories belonging to a specific GitHub user.
    Works without login (read-only, public data)."""
    try:
        q = f"user:{username} {query}".strip()
        gh = _get_client()
        results = gh.search_repositories(query=q)
        repos = [{"full_name": r.full_name, "url": r.html_url} for r in results[:10]]
        return {"status": "success", "results": repos}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@mcp.tool()
def create_issue(repo_name: str, title: str, body: str = "", owner: str = "") -> dict:
    """Create an issue on a GitHub repository. Defaults to your own repo unless
    an owner/username is specified for someone else's repo you have access to.
    Requires the user to be logged in via Clerk."""
    try:
        gh = _get_authed_client()
        if owner:
            full_name = f"{owner}/{repo_name}"
        else:
            user = gh.get_user()
            full_name = f"{user.login}/{repo_name}"

        repo = gh.get_repo(full_name)
        issue = repo.create_issue(title=title, body=body)

        return {
            "status": "success",
            "repo_name": full_name,
            "issue_number": issue.number,
            "title": issue.title,
            "url": issue.html_url,
        }
    except PermissionError as e:
        return {"status": "error", "message": str(e)}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@mcp.tool()
def list_my_repos(query: str = "") -> dict:
    """List repositories owned by the authenticated user, optionally filtered
    by a substring in the repo name. Use this for 'my repo named X' — pass X
    as query. Requires login."""
    try:
        gh = _get_authed_client()
        user = gh.get_user()
        repos = [
            {"full_name": r.full_name, "private": r.private}
            for r in user.get_repos()
            if not query or query.lower() in r.name.lower()
        ]
        return {"status": "success", "repos": repos}
    except PermissionError as e:
        return {"status": "error", "message": str(e)}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@mcp.tool()
def delete_repo(repo_name: str, confirm: bool = False, owner: str = "") -> dict:
    """Permanently delete a GitHub repository. THIS CANNOT BE UNDONE.
    Requires confirm=true to actually execute, and requires the user to be
    logged in via Clerk."""
    try:
        gh = _get_authed_client()

        if not confirm:
            return {
                "status": "confirmation_required",
                "message": f"This will permanently delete '{repo_name}'. This cannot be undone. "
                           f"Call again with confirm=true to proceed.",
            }

        if owner:
            full_name = f"{owner}/{repo_name}"
        else:
            user = gh.get_user()
            full_name = f"{user.login}/{repo_name}"

        repo = gh.get_repo(full_name)
        repo.delete()

        return {
            "status": "success",
            "deleted": full_name,
        }
    except PermissionError as e:
        return {"status": "error", "message": str(e)}
    except Exception as e:
        return {"status": "error", "message": str(e)}


if __name__ == "__main__":
    mcp.run()