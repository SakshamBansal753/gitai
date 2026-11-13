# gitai/tool_catalog.py
"""
Complete source of truth for all tools supported by GitAI.
Provides instant, zero-dependency in-memory tool catalog and context formatting.
"""
import json

TOOL_CATALOG = [
    {
        "tool_name": "create_repo",
        "server": "github_server",
        "description": "Create a new GitHub repository for the authenticated user and optionally initialize it locally.",
        "parameters": {
            "repo_name": "str",
            "private": "bool",
            "description": "str (optional)",
            "local_path": "str (optional)",
        },
        "example_phrases": [
            "create a new repo called {X}",
            "make a private repository named {X}",
            "start a brand new github project",
            "create repo {X} at {path}",
            "create a repository in {path}",
        ],
    },
    {
        "tool_name": "clone_repository",
        "server": "git_server",
        "description": "Clone an existing GitHub repository to a local directory.",
        "parameters": {
            "repo_name": "str",
            "owner": "str (optional)",
            "local_path": "str (optional)",
        },
        "example_phrases": [
            "clone repo {X}",
            "clone repository {X} into {path}",
            "download my repo {X}",
        ],
    },
    {
        "tool_name": "create_file",
        "server": "git_server",
        "description": "Create or write a file with content inside a repository on the user's computer, and optionally stage, commit, and push it to GitHub.",
        "parameters": {
            "repo_name": "str",
            "file_name": "str",
            "content": "str (optional)",
            "branch": "str (optional)",
            "commit_message": "str (optional)",
            "push": "bool (optional)",
        },
        "example_phrases": [
            "create a file named {file} with content {content}",
            "add a README.md file to repo {repo}",
            "write index.js in my repository",
            "create file {file} and commit it",
        ],
    },
    {
        "tool_name": "add_files_to_branch",
        "server": "git_server",
        "description": "Stage, commit, and optionally create specified files to a branch in a local git repo.",
        "parameters": {
            "repo_name": "str",
            "branch": "str",
            "files": "list[str]",
            "commit_message": "str",
            "content": "str (optional)",
            "push": "bool (optional)",
        },
        "example_phrases": [
            "add {file} to {branch} and commit it",
            "put these files onto the dev branch with a commit",
            "commit and push my files to {branch}",
        ],
    },
    {
        "tool_name": "get_repo_status",
        "server": "git_server",
        "description": "Get the current git status including modified, staged, deleted, and untracked files.",
        "parameters": {"repo_name": "str (optional)", "repo_path": "str (optional)"},
        "example_phrases": [
            "is my working directory clean",
            "what files have I changed but not committed yet",
            "git status",
            "show me what is different from the last commit",
        ],
    },
    {
        "tool_name": "get_branches",
        "server": "git_server",
        "description": "List all local and remote branches for a repository.",
        "parameters": {"repo_name": "str", "owner": "str (optional)"},
        "example_phrases": [
            "list branches for repo {X}",
            "show all branches",
            "what branches exist in this repo",
        ],
    },
    {
        "tool_name": "merge_branch",
        "server": "git_server",
        "description": "Merge source branch into target branch in a local git repository.",
        "parameters": {
            "repo_name": "str",
            "source_branch": "str",
            "target_branch": "str",
            "owner": "str (optional)",
        },
        "example_phrases": [
            "merge {source} into {target}",
            "merge branch feature to main in repo {X}",
        ],
    },
    {
        "tool_name": "list_my_repos",
        "server": "github_server",
        "description": "List repositories owned by the authenticated GitHub user.",
        "parameters": {"query": "str (optional)"},
        "example_phrases": [
            "show my repos",
            "what repositories do I have",
            "list everything under my github account",
        ],
    },
    {
        "tool_name": "search_repo",
        "server": "github_server",
        "description": "Search public GitHub repositories by keyword and optional language filter.",
        "parameters": {"query": "str", "language": "str (optional)"},
        "example_phrases": [
            "find public projects about {X}",
            "search github for {X} written in python",
            "look for open source repos related to {X}",
        ],
    },
    {
        "tool_name": "search_user_repo",
        "server": "github_server",
        "description": "Search repositories belonging to a specific GitHub user.",
        "parameters": {"username": "str", "query": "str (optional)"},
        "example_phrases": [
            "find {username}'s projects about {X}",
            "what has user {username} built on github",
            "search {username}'s github account for {X}",
        ],
    },
    {
        "tool_name": "create_issue",
        "server": "github_server",
        "description": "Create an issue in a GitHub repository.",
        "parameters": {
            "repo_name": "str",
            "title": "str",
            "body": "str (optional)",
            "owner": "str (optional)",
        },
        "example_phrases": [
            "create an issue in {repo} titled {title}",
            "file a bug report for repo {repo}",
        ],
    },
    {
        "tool_name": "delete_repo",
        "server": "github_server",
        "description": "Delete a repository on GitHub (requires confirm=True).",
        "parameters": {
            "repo_name": "str",
            "confirm": "bool",
            "owner": "str (optional)",
        },
        "example_phrases": [
            "delete repo {X}",
            "remove repository {X} from my github",
        ],
    },
]


def format_all_tools_context() -> tuple[str, set[str]]:
    """Format all available tools into a clear context block for the router prompt."""
    valid_tools = {t["tool_name"] for t in TOOL_CATALOG}
    parts = []
    for t in TOOL_CATALOG:
        parts.append(
            f"- tool: {t['tool_name']}\n"
            f"  server: {t['server']}\n"
            f"  params: {json.dumps(t['parameters'])}\n"
            f"  info: Tool: {t['tool_name']}\n"
            f"Description: {t['description']}\n"
            f"Examples: {'; '.join(t['example_phrases'])}"
        )
    return "\n\n".join(parts), valid_tools
