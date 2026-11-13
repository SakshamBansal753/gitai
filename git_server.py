# git_server.py
from fastmcp import FastMCP
from git import Repo, GitCommandError
from github import Github, Auth
from repo_registry import resolve_repo_path, register_repo
import os
import config
from github_auth import get_token, get_authed_clone_url

mcp = FastMCP("git_server")

_PROTECTED_BRANCHES = {"main", "master"}


def _get_authed_client() -> Github:
    """Build a fresh, per-call GitHub client bound to the current session's
    token. Never cache or reuse this across calls or users."""
    token = get_token()
    if token is None:
        raise PermissionError("Not logged in. Run 'login' first before using this tool.")
    return Github(auth=Auth.Token(token))


@mcp.tool()
def create_file(
    repo_name: str,
    file_name: str,
    content: str = "",
    branch: str = "",
    commit_message: str = "",
    push: bool = False,
) -> dict:
    """Create or write a file with content inside a repository on the user's computer,
    and optionally stage, commit, and push it to GitHub."""
    try:
        repo_path = resolve_repo_path(repo_name)
        if repo_path is None:
            return {
                "status": "error",
                "message": f"Repo '{repo_name}' is not registered or found locally.",
            }

        repo = Repo(repo_path)

        if branch:
            if repo.active_branch.name != branch:
                if branch in repo.heads:
                    repo.heads[branch].checkout()
                else:
                    repo.create_head(branch)
                    repo.heads[branch].checkout()

        file_full_path = os.path.join(repo_path, file_name)
        os.makedirs(os.path.dirname(file_full_path), exist_ok=True)

        with open(file_full_path, "w", encoding="utf-8") as f:
            f.write(content or "")

        rel_path = os.path.relpath(file_full_path, repo_path)
        result = {
            "status": "success",
            "file": rel_path,
            "full_path": file_full_path,
            "repo": repo_name,
        }

        if commit_message:
            repo.index.add([rel_path])
            commit = repo.index.commit(commit_message)
            result["commit_hash"] = commit.hexsha
            result["committed"] = True
            result["branch"] = repo.active_branch.name

            if push and repo.remotes:
                active_br = repo.active_branch.name
                repo.remotes.origin.push(refspec=f"{active_br}:{active_br}")
                result["pushed_to_github"] = True

        return result
    except Exception as e:
        return {"status": "error", "message": str(e)}


@mcp.tool()
def add_files_to_branch(
    repo_name: str,
    branch: str,
    files: list[str],
    commit_message: str,
    content: str = "",
    push: bool = False,
) -> dict:
    """Add files or a folder from a local repo to a branch and commit.
    Automatically creates any file that does not exist yet with optional content.
    Optionally pushes to GitHub if push=True."""
    try:
        repo_path = resolve_repo_path(repo_name)
        if repo_path is None:
            return {
                "status": "error",
                "message": f"Repo '{repo_name}' is not registered or found locally.",
            }

        repo = Repo(repo_path)

        if repo.active_branch.name != branch:
            if branch in repo.heads:
                repo.heads[branch].checkout()
            else:
                repo.create_head(branch)
                repo.heads[branch].checkout()

        resolved_files = []
        for f in files:
            full_path = os.path.join(repo_path, f)

            # Auto-create file if it does not exist on disk
            if not os.path.exists(full_path):
                os.makedirs(os.path.dirname(full_path), exist_ok=True)
                with open(full_path, "w", encoding="utf-8") as file_obj:
                    file_obj.write(content or "")

            if os.path.isdir(full_path):
                for root, _, filenames in os.walk(full_path):
                    if ".git" in root:
                        continue
                    for fname in filenames:
                        rel_path = os.path.relpath(os.path.join(root, fname), repo_path)
                        resolved_files.append(rel_path)
            else:
                rel_path = os.path.relpath(full_path, repo_path)
                resolved_files.append(rel_path)

        repo.index.add(resolved_files)
        commit = repo.index.commit(commit_message)

        res = {
            "status": "success",
            "branch": branch,
            "commit_hash": commit.hexsha,
            "files_committed": resolved_files,
        }

        if push and repo.remotes:
            repo.remotes.origin.push(refspec=f"{branch}:{branch}")
            res["pushed_to_github"] = True

        return res
    except Exception as e:
        return {"status": "error", "message": str(e)}


@mcp.tool()
def get_repo_status(repo_name: str = "", repo_path: str = "") -> dict:
    """Get the current git status (modified/staged/untracked files) of a local repo.
    Accepts repo_name, repo_path, or defaults to current directory."""
    try:
        target = repo_path or repo_name
        resolved = resolve_repo_path(target) if target else os.getcwd()
        if not resolved or not os.path.exists(resolved):
            return {"status": "error", "message": f"Repository '{target}' not found locally."}

        repo = Repo(resolved)
        return {
            "status": "success",
            "repo_path": resolved,
            "branch": repo.active_branch.name,
            "modified": [item.a_path for item in repo.index.diff(None)],
            "staged": [item.a_path for item in repo.index.diff("HEAD")],
            "untracked": repo.untracked_files,
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


@mcp.tool()
def clone_repository(repo_name: str, owner: str = "", local_path: str = "") -> dict:
    """Clone a GitHub repository by name into the GitAI workspace and register it locally.
    If owner is not given, defaults to the authenticated user's own repo.
    If owner is given, clones that user's repo instead (e.g. someone else's public project).
    Requires the user to be logged in via Clerk."""
    try:
        gh = _get_authed_client()

        if owner:
            full_name = f"{owner}/{repo_name}"
        else:
            user = gh.get_user()
            full_name = f"{user.login}/{repo_name}"

        gh_repo = gh.get_repo(full_name)
        clone_url = get_authed_clone_url(gh_repo.clone_url)

        if not local_path:
            target_path = os.path.join(config.GITAI_WORKSPACE_DIR, repo_name)
        else:
            norm_path = os.path.abspath(local_path)
            if os.path.basename(norm_path).lower() != repo_name.lower():
                target_path = os.path.join(norm_path, repo_name)
            else:
                target_path = norm_path

        os.makedirs(os.path.dirname(os.path.abspath(target_path)), exist_ok=True)

        if os.path.exists(target_path) and os.listdir(target_path):
            return {
                "status": "error",
                "message": f"'{repo_name}' already exists locally at {target_path}",
            }

        Repo.clone_from(clone_url, target_path)
        register_repo(repo_name, target_path)

        return {
            "status": "success",
            "repo_name": full_name,
            "local_path": target_path,
            "registered_as": repo_name,
        }
    except PermissionError as e:
        return {"status": "error", "message": str(e)}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@mcp.tool()
def get_branches(repo_name: str, owner: str = "") -> dict:
    """List all branches of a GitHub repository directly from GitHub — no local clone or registration required.
    Defaults to your own repo unless an owner is specified. Requires login unless owner is given for a public repo."""
    try:
        if owner:
            gh = _get_authed_client() if get_token() else Github()  # public repo: allow anonymous read
            full_name = f"{owner}/{repo_name}"
        else:
            gh = _get_authed_client()
            user = gh.get_user()
            full_name = f"{user.login}/{repo_name}"

        gh_repo = gh.get_repo(full_name)
        branches = [b.name for b in gh_repo.get_branches()]

        return {
            "status": "success",
            "repo_name": full_name,
            "default_branch": gh_repo.default_branch,
            "branches": branches,
        }
    except PermissionError as e:
        return {"status": "error", "message": str(e)}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@mcp.tool()
def merge_branch(repo_name: str, source_branch: str, target_branch: str, owner: str = "") -> dict:
    """Merge source_branch into target_branch in a repo, then push the result to GitHub.
    If the repo isn't registered locally yet, it's automatically cloned first.
    Requires the user to be logged in via Clerk."""
    try:
        gh = _get_authed_client()
        repo_path = resolve_repo_path(repo_name)

        if repo_path is None:
            if owner:
                full_name = f"{owner}/{repo_name}"
            else:
                user = gh.get_user()
                full_name = f"{user.login}/{repo_name}"

            gh_repo = gh.get_repo(full_name)
            clone_url = get_authed_clone_url(gh_repo.clone_url)

            repo_path = os.path.join(config.GITAI_WORKSPACE_DIR, repo_name)
            os.makedirs(config.GITAI_WORKSPACE_DIR, exist_ok=True)

            if not os.path.exists(repo_path):
                Repo.clone_from(clone_url, repo_path)

            register_repo(repo_name, repo_path)

        repo = Repo(repo_path)

        if repo.remotes:
            repo.remotes.origin.fetch()

        if source_branch not in repo.heads:
            if source_branch in [r.name.split("/")[-1] for r in repo.remote().refs]:
                repo.git.checkout("-b", source_branch, f"origin/{source_branch}")
            else:
                return {"status": "error", "message": f"source branch '{source_branch}' does not exist"}

        if target_branch not in repo.heads:
            if target_branch in [r.name.split("/")[-1] for r in repo.remote().refs]:
                repo.git.checkout("-b", target_branch, f"origin/{target_branch}")
            else:
                return {"status": "error", "message": f"target branch '{target_branch}' does not exist"}

        repo.heads[target_branch].checkout()
        merge_output = repo.git.merge(source_branch)

        push_info = repo.remotes.origin.push(refspec=f"{target_branch}:{target_branch}")
        push_summary = [str(info.summary) for info in push_info]

        return {
            "status": "success",
            "merged": f"{source_branch} into {target_branch}",
            "pushed_to_github": True,
            "push_summary": push_summary,
            "current_branch": repo.active_branch.name,
            "details": merge_output,
        }
    except PermissionError as e:
        return {"status": "error", "message": str(e)}
    except GitCommandError as e:
        return {"status": "error", "message": f"merge conflict or push failure: {str(e)}"}
    except Exception as e:
        return {"status": "error", "message": str(e)}
if __name__ == "__main__":
    mcp.run()