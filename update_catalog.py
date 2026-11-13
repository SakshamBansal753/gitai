# update_catalog.py
"""
Standalone script to add OR update a single tool entry in the existing
Chroma vectorstore — without touching any other tool already indexed.

Use this whenever you implement one new tool (your stated workflow),
instead of running a full build_dataset.py rebuild every time.

Usage:
    1. Edit the TOOL_ENTRY dict below to describe the tool you just added.
    2. Run:  python update_catalog.py
    3. It deletes any existing entry with the same tool_name (so re-running
       this after editing a tool's description/params cleanly replaces it,
       instead of leaving a stale duplicate embedding behind), then inserts
       the current version.

This has no dependency on orchestrator.py, cli.py, or the MCP servers —
it only needs to agree with config.py on CHROMA_DIR / CHROMA_COLLECTION.
"""

import json
from langchain_core.documents import Document
from langchain_chroma import Chroma
from langchain_ollama import OllamaEmbeddings

import config


# ---------------------------------------------------------------------
# EDIT THIS: describe the one tool you want to add or update.
# ---------------------------------------------------------------------
TOOL_ENTRY = {
    "tool_name": "delete_repo",
    "server": "github_server",
    "description": "Permanently delete a GitHub repository. Irreversible — requires explicit confirmation before it actually deletes anything.",
    "parameters": {
        "repo_name": "str",
        "confirm": "bool (must be true to actually delete)",
        "owner": "str (optional — defaults to your own account)",
    },
    "example_phrases": [
        "delete the repo gitrepo",
        "remove {repo} from github",
        "permanently delete {repo}",
    ],
}

def build_document(tool: dict) -> Document:
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
    return Document(page_content=content, metadata=metadata)


def update_catalog(tool: dict):
    embeddings = OllamaEmbeddings(model=config.EMBED_MODEL, base_url=config.OLLAMA_HOST)
    vectorstore = Chroma(
        collection_name=config.CHROMA_COLLECTION,
        embedding_function=embeddings,
        persist_directory=config.CHROMA_DIR,
    )

    # find and delete any existing entries for this tool_name first,
    # so re-running this script replaces rather than duplicates.
    existing = vectorstore.get(where={"tool_name": tool["tool_name"]})
    existing_ids = existing.get("ids", [])
    if existing_ids:
        vectorstore.delete(ids=existing_ids)
        print(f"🗑️  Removed {len(existing_ids)} existing entr{'y' if len(existing_ids)==1 else 'ies'} for '{tool['tool_name']}'")

    doc = build_document(tool)
    vectorstore.add_documents([doc])

    print(f"✅ Added/updated '{tool['tool_name']}' in collection '{config.CHROMA_COLLECTION}'")
    print(f"   server: {tool['server']}")
    print(f"   persisted to: {config.CHROMA_DIR}")


if __name__ == "__main__":
    update_catalog(TOOL_ENTRY)