"""
GitAI - Natural language Git & GitHub assistant.

Use via CLI:
    gitai
    or: gitai "create repo payment at ./gitflow"

Use via Python SDK:
    import gitai
    client = gitai.Client()
    result = client.run("create repo payment at ./gitflow")
    print(result["response"])
"""

import asyncio

try:
    from .orchestrator import Orchestrator
    from . import config
except (ImportError, ValueError):
    from orchestrator import Orchestrator
    import config

__version__ = "0.1.2"


class Client:
    """Programmatic Python SDK client for GitAI."""

    def __init__(self, groq_api_key: str = None):
        if groq_api_key:
            config.set_groq_api_key(groq_api_key)

        key = config.get_groq_api_key()
        if not key:
            raise ValueError(
                "No Groq API key found. Pass groq_api_key='gsk_...' or set GROQ_API_KEY in your environment, or configure via CLI: gitai --set-groq-key <KEY>"
            )

        self.orchestrator = Orchestrator()

    def run(self, query: str) -> dict:
        """Run a natural language prompt synchronously."""
        return asyncio.run(self.orchestrator.handle_query(query))

    async def arun(self, query: str) -> dict:
        """Run a natural language prompt asynchronously."""
        return await self.orchestrator.handle_query(query)


__all__ = ["Client", "Orchestrator", "__version__"]
