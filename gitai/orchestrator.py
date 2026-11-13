# gitai/orchestrator.py
import json
import re
from pathlib import Path
from langchain_core.prompts import ChatPromptTemplate
from langchain_groq import ChatGroq
from fastmcp import Client as MCPClient
from fastmcp.exceptions import ToolError

try:
    from . import config
    from .tool_catalog import format_all_tools_context, TOOL_CATALOG
except (ImportError, ValueError):
    import config
    from tool_catalog import format_all_tools_context, TOOL_CATALOG

router_system_prompt = """You are the tool router for GitAI, a natural language Git/GitHub assistant.
You may ONLY select a tool from the ones listed in the context below. Never invent a tool name or server name.

Retrieved tools for this query:
{context}

ROUTING GUIDELINES:
- Always match the user's intent to the most appropriate tool from the list above.
- If the user asks to create, make, initialize, or set up a repository, select "create_repo".
- If the user specifies a location, directory, or path (e.g. "at ./gitflow", "in ./folder", "to path X"), extract it into "local_path".
- Extract the clean repository name into "repo_name" (e.g. "create repo payment at ./gitflow" -> repo_name: "payment", local_path: "./gitflow").
- If the user says "private", set "private": true. Otherwise default "private": false.
- If the user asks to create, write, or add a file, prefer "create_file" (or "add_files_to_branch" if multiple files or staging).
- If the user asks about branches, list branches, or check branch status, select "get_branches".
- If the user asks to clone, download, or get a repo locally, select "clone_repository".
- If the user asks for status, changes, or working directory state, select "get_repo_status".
- If the user asks to merge, select "merge_branch".
- If the user asks to list, show, or display their repositories, select "list_my_repos".
- Only return tool as null if the query is completely unrelated to Git or GitHub (e.g. weather, jokes, general knowledge).

STRICT OUTPUT RULES:
- Output EXACTLY ONE JSON object. Never output multiple objects, never separate with semicolons.
- Use the key "arguments" — never "params" or any other key name.
- Pick only ONE tool, choosing the single most direct match.
- If none of the retrieved tools apply, return {{"tool": null, "server": null, "arguments": {{}}}}.
- Output ONLY the JSON object. No markdown, no explanation, no extra text.

Examples:
{{"tool": "create_repo", "server": "github_server", "arguments": {{"repo_name": "payment", "private": false, "description": "", "local_path": "./gitflow"}}}}
{{"tool": "clone_repository", "server": "git_server", "arguments": {{"repo_name": "payment", "local_path": "./gitflow"}}}}
{{"tool": "create_file", "server": "git_server", "arguments": {{"repo_name": "payment", "file_name": "README.md", "content": "# Payment Service", "branch": "main", "commit_message": "Add README", "push": true}}}}
{{"tool": "add_files_to_branch", "server": "git_server", "arguments": {{"repo_name": "payment", "branch": "main", "files": ["README.md"], "commit_message": "Add README"}}}}
{{"tool": "get_repo_status", "server": "git_server", "arguments": {{"repo_name": "payment"}}}}
{{"tool": "list_my_repos", "server": "github_server", "arguments": {{}}}}
"""

router_prompt = ChatPromptTemplate.from_messages([
    ("system", router_system_prompt),
    ("human", "{input}"),
])

condense_prompt = ChatPromptTemplate.from_messages([
    ("system", "You rewrite a user's follow-up message into a standalone question using the chat history.\n"
               "Output ONLY the rewritten question text itself — nothing else. No commentary, no explanation, "
               "no phrases like 'no changes needed'. If the input is already standalone, output it exactly as-is, "
               "word for word.\n\n"
               "History:\n{history}"),
    ("human", "{input}"),
])

format_prompt = ChatPromptTemplate.from_messages([
    ("system", "You turn raw JSON tool output from GitAI (a Git/GitHub assistant) into a short, "
               "clear, human-readable response for the user.\n\n"
               "Rules:\n"
               "- Never show raw JSON, keys, or field names like 'full_name' — write natural sentences "
               "or a short markdown list/table instead.\n"
               "- Never include internal identifiers: numeric ids, node_ids, owner ids, emails, or any "
               "field that looks like an internal database key. Only mention things a user would care "
               "about: repo names, URLs, branch names, file names, counts, messages.\n"
               "- Be concise — a few sentences or a short list, not a report.\n"
               "- If the data is a list of repositories, show it as a compact markdown table with only "
               "Name, Stars (if present), and URL columns.\n"
               "- If nothing meaningful is in the data (empty list, etc.), say so plainly in one sentence.\n"
               "- Do not invent facts that aren't in the JSON.\n\n"
               "User asked: {query}\n\n"
               "Raw tool output:\n{result}"),
    ("human", "Respond with the formatted answer only — no preamble like 'Here is the result:'."),
])


class Orchestrator:
    def __init__(self):
        key = config.get_groq_api_key()
        if not key:
            raise ValueError("No Groq API key configured. Provide GROQ_API_KEY in environment or ~/.gitai/config.json")

        self.api_key = key
        self.current_model = config.GROQ_MODEL or "llama-3.1-8b-instant"
        self.llm = ChatGroq(model=self.current_model, api_key=self.api_key)

        # Optional Chroma vector store initialization
        self.retriever = None
        try:
            from langchain_ollama import OllamaEmbeddings
            from langchain_chroma import Chroma
            import os

            if os.path.exists(config.CHROMA_DIR):
                embeddings = OllamaEmbeddings(model=config.EMBED_MODEL, base_url=config.OLLAMA_HOST)
                vectorstore = Chroma(
                    collection_name=config.CHROMA_COLLECTION,
                    embedding_function=embeddings,
                    persist_directory=config.CHROMA_DIR,
                )
                self.retriever = vectorstore.as_retriever(
                    search_kwargs={"k": config.RETRIEVAL_K}
                )
        except Exception:
            self.retriever = None

        self.mcp_clients = {
            name: MCPClient(Path(cfg["path"])) for name, cfg in config.MCP_SERVERS.items()
        }
        self.history: list[dict] = []

    def _invoke_llm(self, prompt, inputs: dict) -> str:
        """Invokes a LangChain chain with automatic model fallback on model errors."""
        candidate_models = [
            self.current_model,
            "openai/gpt-oss-120b",
            "openai/gpt-oss-20b",
            "qwen/qwen3.8-27b",
            "llama-3.1-8b-instant",
            "llama-3.3-70b-versatile",
        ]
        seen = set()
        models_to_try = [m for m in candidate_models if not (m in seen or seen.add(m))]

        last_error = None
        for model_name in models_to_try:
            try:
                if model_name != self.current_model or self.llm is None:
                    self.current_model = model_name
                    self.llm = ChatGroq(model=model_name, api_key=self.api_key)
                chain = prompt | self.llm
                resp = chain.invoke(inputs)
                return resp.content.strip()
            except Exception as e:
                err_str = str(e)
                if any(k in err_str.lower() for k in ["does not exist", "model_not_found", "404", "decommissioned", "not supported", "400"]):
                    last_error = e
                    continue
                raise e
        raise last_error

    def _condense(self, query: str) -> str:
        if not self.history:
            return query

        try:
            hist_text = "\n".join(f"{m['role']}: {m['content']}" for m in self.history[-6:])
            result = self._invoke_llm(condense_prompt, {"history": hist_text, "input": query})
            if not result or len(result) > len(query) * 3:
                return query
            return result
        except Exception:
            return query

    def _retrieve_context(self, query: str) -> tuple[str, set[str]]:
        """Retrieve tool context. Uses vectorstore if available and active, otherwise built-in catalog."""
        if self.retriever:
            try:
                docs = self.retriever.invoke(query)
                valid_tools = {d.metadata["tool_name"] for d in docs}
                context = "\n\n".join(
                    f"- tool: {d.metadata['tool_name']}\n"
                    f"  server: {d.metadata['server']}\n"
                    f"  params: {d.metadata['parameters']}\n"
                    f"  info: {d.page_content}"
                    for d in docs
                )
                if valid_tools:
                    return context, valid_tools
            except Exception:
                pass

        # Built-in zero-dependency tool catalog fallback
        return format_all_tools_context()

    def _route(self, standalone_query: str, context: str, valid_tools: set[str]) -> dict:
        try:
            raw = self._invoke_llm(router_prompt, {"context": context, "input": standalone_query})
        except Exception as e:
            err_str = str(e)
            if "rate_limit" in err_str.lower() or "429" in err_str:
                return {
                    "tool": None,
                    "server": None,
                    "arguments": {},
                    "error": "AI rate limit reached. Please wait a moment and try again.",
                }
            return {
                "tool": None,
                "server": None,
                "arguments": {},
                "error": f"LLM routing error: {err_str}",
            }

        print(f"[DEBUG] standalone_query: {standalone_query!r}")
        print(f"[DEBUG] valid_tools: {valid_tools}")
        print(f"[DEBUG] raw LLM response: {raw!r}")

        match = re.search(r"\{.*?\}(?=\s*;|\s*$)", raw, re.DOTALL)
        candidate = match.group(0) if match else raw

        try:
            decision = json.loads(candidate)
        except json.JSONDecodeError:
            return {"tool": None, "server": None, "arguments": {}, "raw": raw}

        if "params" in decision and "arguments" not in decision:
            decision["arguments"] = decision.pop("params")
        decision.setdefault("arguments", {})

        if decision.get("tool") and decision["tool"] not in valid_tools:
            return {
                "tool": None,
                "server": None,
                "arguments": {},
                "raw": f"Tool '{decision['tool']}' not in available set {valid_tools}",
            }

        return decision

    async def _dispatch(self, decision: dict):
        if not decision.get("tool"):
            return {"error": "no_tool_matched", "raw": decision.get("raw", "")}
        client = self.mcp_clients.get(decision["server"])
        if client is None:
            return {"error": f"unknown_server: {decision['server']}"}

        args = {k: v for k, v in decision.get("arguments", {}).items() if v is not None}

        try:
            async with client:
                raw_result = await client.call_tool(decision["tool"], args)
        except ToolError as e:
            return {"error": "tool_not_implemented", "tool": decision["tool"], "message": str(e)}

        if hasattr(raw_result, "data") and raw_result.data is not None:
            return raw_result.data
        if hasattr(raw_result, "structured_content") and raw_result.structured_content is not None:
            return raw_result.structured_content
        return {"raw": str(raw_result)}

    def _format_response(self, user_query: str, result: dict) -> str:
        try:
            return self._invoke_llm(format_prompt, {"query": user_query, "result": json.dumps(result, default=str)})
        except Exception:
            return json.dumps(result, indent=2, default=str)

    async def handle_query(self, user_query: str) -> dict:
        standalone_query = self._condense(user_query)
        context, valid_tools = self._retrieve_context(standalone_query)
        decision = self._route(standalone_query, context, valid_tools)

        if decision.get("error"):
            return {
                "decision": decision,
                "result": {"status": "error", "message": decision["error"]},
                "response": decision["error"],
            }

        if not decision.get("tool"):
            response = "⚠️ No matching tool found for that request."
            return {
                "decision": decision,
                "result": {},
                "response": response,
            }

        result = await self._dispatch(decision)
        response = self._format_response(user_query, result)

        self.history.append({"role": "user", "content": user_query})
        self.history.append({"role": "assistant", "content": response})

        return {
            "decision": decision,
            "result": result,
            "response": response,
        }
