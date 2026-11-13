"""
Standalone script to build the GitAI tool-catalog vector store.
Run this independently, whenever tools are added/changed:

    python build_vectorstore.py

It has no dependency on orchestrator.py, cli.py, or the MCP servers —
it only needs to agree with config.py on CHROMA_DIR / CHROMA_COLLECTION
so the orchestrator can later load what this script builds.

IMPORTANT: This catalog only lists tools that are ACTUALLY implemented
right now in git_server.py / github_server.py. Add a new entry here
ONLY after you've implemented the matching @mcp.tool() function —
otherwise the router can select a tool that doesn't exist and dispatch
will fail with "Unknown tool: ...".
"""

import json
from langchain_core.documents import Document
from langchain_chroma import Chroma
from langchain_ollama import OllamaEmbeddings

import config


# ---------------------------------------------------------------------
# Single source of truth for tool metadata. Keep this in sync with the
# actual @mcp.tool() signatures in git_server.py / github_server.py.
# Currently implemented tools only — extend one at a time.
# ---------------------------------------------------------------------
TOOL_CATALOG = [
    {
        "tool_name": "create_repo",
        "server": "github_server",
        "description": "Create a new GitHub repository for the authenticated user.",
        "parameters": {"repo_name": "str", "private": "bool", "description": "str (optional)", "local_path": "str (optional)"},
        "example_phrases": [
            "create a new repo called {X}",
            "make a private repository named {X}",
            "start a brand new github project",
            "set up a fresh repository for me",
            "create repo {X} at {path}",
            "create a repository in {path}",
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
        "tool_name": "list_my_repos",
        "server": "github_server",
        "description": "List repositories owned by the authenticated user.",
        "parameters": {},
        "example_phrases": [
            "show my repos",
            "what repositories do I have",
            "list everything under my github account",
        ],
    },
    {
        "tool_name": "create_file",
        "server": "git_server",
        "description": "Create or write a file with content in a local git repository in the user's environment, and optionally commit and push.",
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
            "create a new file called {file}",
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
            "add and commit {file}",
            "commit and push my files to {branch}",
        ],
    },
    {
        "tool_name": "get_repo_status",
        "server": "git_server",
        "description": "Get the current git status including modified, staged, deleted, and untracked files.",
        "parameters": {"repo_path": "str"},
        "example_phrases": [
            "is my working directory clean",
            "what files have I changed but not committed yet",
            "git status",
            "show me what's different from the last commit",
        ],
    },
]


def build_documents() -> list[Document]:
    """Convert the tool catalog into LangChain Documents with flat metadata."""
    docs = []
    for tool in TOOL_CATALOG:
        content = (
            f"Tool: {tool['tool_name']}\n"
            f"Description: {tool['description']}\n"
            f"Examples: {'; '.join(tool['example_phrases'])}"
        )
        metadata = {
            "tool_name": tool["tool_name"],
            "server": tool["server"],
            "parameters": json.dumps(tool["parameters"]),
        }
        docs.append(Document(page_content=content, metadata=metadata))
    return docs


def build_vectorstore():
    docs = build_documents()

    embeddings = OllamaEmbeddings(model=config.EMBED_MODEL, base_url=config.OLLAMA_HOST)

    vectorstore = Chroma.from_documents(
        documents=docs,
        embedding=embeddings,
        collection_name=config.CHROMA_COLLECTION,
        persist_directory=config.CHROMA_DIR,
    )

    print(f"✅ Built vector store with {len(docs)} tool documents")
    print(f"   collection: {config.CHROMA_COLLECTION}")
    print(f"   persisted to: {config.CHROMA_DIR}")
    return vectorstore


if __name__ == "__main__":
    build_vectorstore()