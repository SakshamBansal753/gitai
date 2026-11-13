# orchestrator.py
import json
from langchain_core.prompts import ChatPromptTemplate
from langchain_ollama import ChatOllama, OllamaEmbeddings
from langchain_chroma import Chroma
from fastmcp import Client as MCPClient
import re
import config
from fastmcp.exceptions import ToolError

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
- Only return tool as null if the query is completely unrelated to Git or GitHub (e.g. weather, jokes, general knowledge).

STRICT OUTPUT RULES:
- Output EXACTLY ONE JSON object. Never output multiple objects, never separate with semicolons.
- Use the key "arguments" — never "params" or any other key name.
- Pick only ONE tool, choosing the single most direct match.
- If none of the retrieved tools apply, return {{"tool": null, "server": null, "arguments": {{}}}}.
- Output ONLY the JSON object. No markdown, no explanation, no extra text.

Examples:
{{"tool": "create_repo", "server": "github_server", "arguments": {{"repo_name": "payment", "private": false, "description": "", "local_path": "./gitflow"}}}}
{{"tool": "create_repo", "server": "github_server", "arguments": {{"repo_name": "myrepo", "private": true, "description": "My private project"}}}}
{{"tool": "add_files_to_branch", "server": "git_server", "arguments": {{"repo_name": "payment", "branch": "main", "files": ["README.md"], "commit_message": "Add README"}}}}
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
from langchain_groq import ChatGroq
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
        self.llm = ChatGroq(model=config.GROQ_MODEL, api_key=config.GROQ_API_KEY)
        self.embeddings = OllamaEmbeddings(model=config.EMBED_MODEL, base_url=config.OLLAMA_HOST)
        self.vectorstore = Chroma(
            collection_name=config.CHROMA_COLLECTION,
            embedding_function=self.embeddings,
            persist_directory=config.CHROMA_DIR,
        )
        self.retriever = self.vectorstore.as_retriever(
            search_kwargs={"k": config.RETRIEVAL_K}
        )
        self.mcp_clients = {
            name: MCPClient(cfg["path"]) for name, cfg in config.MCP_SERVERS.items()
        }
        self.history: list[dict] = []

    # ---------- condense follow-up into standalone query ----------
    def _condense(self, query: str) -> str:
        if not self.history:
            return query

        try:
            hist_text = "\n".join(f"{m['role']}: {m['content']}" for m in self.history[-6:])
            chain = condense_prompt | self.llm
            resp = chain.invoke({"history": hist_text, "input": query})
            result = resp.content.strip()

            if not result or len(result) > len(query) * 3:
                return query

            return result
        except Exception:
            return query

    # ---------- retrieve tool context (always, every turn) ----------
    def _retrieve_context(self, query: str) -> tuple[str, set[str]]:
        docs = self.retriever.invoke(query)
        valid_tools = {d.metadata["tool_name"] for d in docs}
        context = "\n\n".join(
            f"- tool: {d.metadata['tool_name']}\n"
            f"  server: {d.metadata['server']}\n"
            f"  params: {d.metadata['parameters']}\n"
            f"  info: {d.page_content}"
            for d in docs
        )
        return context, valid_tools

    # ---------- build grounded prompt + call router LLM ----------
    def _route(self, standalone_query: str, context: str, valid_tools: set[str]) -> dict:
        try:
            chain = router_prompt | self.llm
            resp = chain.invoke({"context": context, "input": standalone_query})
            raw = resp.content.strip()
        except Exception as e:
            err_str = str(e)
            if "rate_limit" in err_str.lower() or "429" in err_str:
                return {"tool": None, "server": None, "arguments": {}, "error": "AI rate limit reached. Please wait a moment and try again."}
            return {"tool": None, "server": None, "arguments": {}, "error": f"LLM routing error: {err_str}"}
        print(f"[DEBUG] standalone_query: {standalone_query!r}")
        print(f"[DEBUG] valid_tools: {valid_tools}")
        print(f"[DEBUG] raw LLM response: {raw!r}")

        # extract just the first {...} block in case the model added extra text/objects
        match = re.search(r"\{.*?\}(?=\s*;|\s*$)", raw, re.DOTALL)
        candidate = match.group(0) if match else raw

        try:
            decision = json.loads(candidate)
        except json.JSONDecodeError:
            return {"tool": None, "server": None, "arguments": {}, "raw": raw}
            

        # normalize common key mistakes
        if "params" in decision and "arguments" not in decision:
            decision["arguments"] = decision.pop("params")
        decision.setdefault("arguments", {})

        if decision.get("tool") and decision["tool"] not in valid_tools:
            return {
                "tool": None,
                "server": None,
                "arguments": {},
                "raw": f"hallucinated tool '{decision['tool']}' not in retrieved set {valid_tools}",
                
            }

        return decision
    # ---------- dispatch to correct MCP server ----------
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
    # ---------- public entrypoint the CLI calls ----------
    def _format_response(self, user_query: str, result: dict) -> str:
        # Don't waste an LLM call on already-short, already-clear system messages
        if not isinstance(result, dict):
            return str(result)

        status = result.get("status")
        if status == "error":
            return f"⚠️ {result.get('message', 'Something went wrong.')}"
        if status == "confirmation_required":
            return f"❓ {result.get('message', 'Please confirm to proceed.')}"
        if "error" in result:
            return f"⚠️ {result.get('raw') or result.get('message') or 'No matching tool found for that request.'}"

        try:
            chain = format_prompt | self.llm
            resp = chain.invoke({
                "query": user_query,
                "result": json.dumps(result, default=str),
            })
            return resp.content.strip()
        except Exception:
            return json.dumps(result, indent=2, default=str)
    async def handle_query(self, user_query: str) -> dict:
        self.history.append({"role": "user", "content": user_query})

        standalone_q = self._condense(user_query)
        context, valid_tools = self._retrieve_context(standalone_q)
        decision = self._route(standalone_q, context, valid_tools)
        result = await self._dispatch(decision)
        response_text = self._format_response(standalone_q, result)

        self.history.append({"role": "assistant", "content": response_text})
        return {"decision": decision, "result": result, "response": response_text}