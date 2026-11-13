# GitAI ⚡

**GitAI** is a natural language Git and GitHub assistant available both as an **interactive CLI** and an **installable Python SDK**.

Say goodbye to memorizing complex git syntax. Just say what you want in plain English, and GitAI handles the rest.

---

## 🚀 Quick Start (Zero-Config Backend)

GitAI is designed for immediate use:
- **Bring Your Own Key (BYOK)**: All you need is a free [Groq API Key](https://console.groq.com/keys).
- **Zero Database / Auth Setup**: PostgreSQL (Neon) and Clerk authentication are pre-configured and work out of the box.
- **Zero Token Files on Disk**: Your GitHub credentials stay in-memory and in PostgreSQL for maximum security.

### 1. Installation

Install GitAI via pip:

```bash
pip install .
```

*(or install from wheel: `pip install gitai-0.1.0-py3-none-any.whl`)*

### 2. Configure Your Groq API Key

Set your key via the CLI or environment:

```bash
# Option A: Save once in GitAI config (~/.gitai/config.json)
gitai --set-groq-key gsk_your_groq_api_key_here

# Option B: Set as environment variable
export GROQ_API_KEY="gsk_your_groq_api_key_here"
```

If not set, GitAI will prompt you automatically on your first launch!

---

## 💻 CLI Usage

### Interactive Mode
Launch the interactive terminal:
```bash
gitai
```

On your first turn, GitAI opens a secure browser window to authenticate with GitHub via Clerk. Once signed in, you can start typing commands:

```
you> create repo payment at ./gitflow
you> create file README.md with content # Payment Service and commit
you> show my repos
you> git status
you> merge dev into main
you> whoami
you> exit
```

### One-Shot Command Mode
Run quick commands directly from your terminal:
```bash
gitai "create repo payment at ./gitflow"
gitai "create file config.json with content {\"env\": \"prod\"}"
gitai "clone repo payment to ./my_projects"
```

### CLI Helper Commands
```bash
gitai --help          # Show all options and examples
gitai --version       # Show current version
gitai --whoami        # View verified database session profile
gitai --relogin       # Switch GitHub accounts
```

---

## 🐍 Python SDK (`import gitai`)

GitAI can be integrated directly into your Python applications, agents, or automation pipelines:

```python
import gitai

# Initialize client (uses GROQ_API_KEY from env or ~/.gitai/config.json)
client = gitai.Client()

# Or pass the key explicitly:
# client = gitai.Client(groq_api_key="gsk_...")

# Run natural language git commands synchronously
result = client.run("create repo payment at ./gitflow")
print(result["response"])

# Create files inside the repository
res2 = client.run("create file README.md with content # Payment API and push to main")
print(res2["response"])

# Check status
res3 = client.run("git status")
print(res3["response"])
```

### Asynchronous Support
```python
import asyncio
import gitai

async def main():
    client = gitai.Client()
    result = await client.arun("list my repos")
    print(result["response"])

asyncio.run(main())
```

---

## 🛠️ Supported Tools & Capabilities

| Capability | Example Prompt | Tool Called |
| :--- | :--- | :--- |
| **Create Repo** | `"create repo payment at ./gitflow"` | `create_repo` (`github_server`) |
| **Clone Repo** | `"clone repo payment to ./local"` | `clone_repository` (`git_server`) |
| **Create File** | `"create file index.js with content console.log('hello')"` | `create_file` (`git_server`) |
| **Stage & Commit** | `"add files to branch main with commit 'Update docs'"` | `add_files_to_branch` (`git_server`) |
| **Git Status** | `"is my working directory clean"` | `get_repo_status` (`git_server`) |
| **List Branches** | `"show all branches for repo payment"` | `get_branches` (`git_server`) |
| **Merge Branch** | `"merge dev into main"` | `merge_branch` (`git_server`) |
| **List Repos** | `"list my repos"` | `list_my_repos` (`github_server`) |
| **Search GitHub** | `"search github for fastmcp in python"` | `search_repo` (`github_server`) |
| **Create Issue** | `"create issue in payment titled 'Fix auth'"` | `create_issue` (`github_server`) |
| **Delete Repo** | `"delete repo test-repo with confirm true"` | `delete_repo` (`github_server`) |

---

## 🔒 Security & Multi-User Architecture

- **PostgreSQL Neon Database**: User sessions and GitHub metadata are linked via Clerk and stored securely with connection pooling and retry logic.
- **In-Memory Credential Passing**: GitHub OAuth tokens are passed in-memory and through environment variables to subprocess MCP servers — zero plaintext token files on disk.
- **Local Isolation**: Repositories are cloned and created directly inside the user's local filesystem with automatic folder hierarchy generation.
- **Groq LLM**: Natural language routing is powered by Groq's high-speed inference engine (`llama-3.3-70b-versatile`).

---

## 📄 License
MIT License.
