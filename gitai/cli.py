# gitai/cli.py
"""
Interactive and one-shot CLI for GitAI.

Usage:
    gitai
    gitai "create repo payment at ./gitflow"
    gitai --set-groq-key <KEY>
    gitai --relogin
    gitai --whoami
    gitai --help
"""

import asyncio
import os
import sys

from rich.console import Console
from rich.table import Table

try:
    from . import config
except (ImportError, ValueError):
    import config

console = Console()
VERSION = "0.1.1"


def _ensure_groq_key() -> str:
    """Prompts the user once for their Groq API key if not already configured."""
    key = config.get_groq_api_key()
    if not key:
        console.print("[bold yellow]⚡ Welcome to GitAI![/bold yellow]")
        console.print("GitAI uses [cyan]Groq[/cyan] for lightning-fast natural language routing.")
        console.print("Get your free API key at: [cyan]https://console.groq.com/keys[/cyan]\n")
        try:
            key = console.input("[bold]Enter your GROQ_API_KEY>[/bold] ").strip()
        except (KeyboardInterrupt, EOFError):
            console.print("\n[red]Setup cancelled.[/red]")
            raise SystemExit(1)
        if not key:
            console.print("[red]A Groq API key is required to use GitAI.[/red]")
            raise SystemExit(1)
        config.set_groq_api_key(key)
        console.print("[bold green]✓ Groq API key saved to ~/.gitai/config.json[/bold green]\n")
    return key


async def _ensure_logged_in(force_relogin: bool = False):
    """
    Ensure an authenticated GitHub session is active.
    Multi-user isolation: User credentials and sessions are verified in PostgreSQL.
    """
    try:
        from .auth import login
    except (ImportError, ValueError):
        from auth import login

    loop = asyncio.get_running_loop()

    console.print("[yellow]Sign-in required for this session.[/yellow] Opening browser to sign in with GitHub...")
    with console.status("[dim]Waiting for sign-in to complete...[/dim]"):
        result = await loop.run_in_executor(None, lambda: login(force_relogin=force_relogin))

    if result.get("status") != "success":
        console.print(f"[bold red]Login failed:[/bold red] {result.get('message', 'Unknown error')}")
        console.print("Restart GitAI to try again.")
        raise SystemExit(1)

    user_data = result.get("user", {})
    username = user_data.get("github_username", "user")
    name = user_data.get("github_name") or "GitHub User"
    db_warning = result.get("db_warning")

    if db_warning:
        console.print(
            f"[bold green]✓ Signed in:[/bold green] "
            f"[bold cyan]@{username}[/bold cyan] ({name})"
        )
        console.print(f"[dim yellow]Notice: Database status ({db_warning}). Active session running.[/dim yellow]")
    else:
        console.print(
            f"[bold green]✓ Signed in and verified in database:[/bold green] "
            f"[bold cyan]@{username}[/bold cyan] ({name})"
        )

    details = []
    if user_data.get("github_email"):
        details.append(f"Email: {user_data['github_email']}")
    details.append(f"Public repos: {user_data.get('github_public_repos', 0)}")
    console.print(f"[dim]{' | '.join(details)}[/dim]")
    console.print(f"[dim green]Session bound to @{username}.[/dim green]\n")
    return user_data


def _print_user_profile():
    """Display user details stored in database for the current signed-in user."""
    try:
        from .auth import get_current_session
        from .database import get_active_user
    except (ImportError, ValueError):
        from auth import get_current_session
        from database import get_active_user

    session = get_current_session()
    user_id = session.get("user_id") or os.environ.get("GITAI_CURRENT_USER_ID")

    user_data = get_active_user(clerk_user_id=user_id) if user_id else get_active_user()
    if not user_data:
        if session.get("github_username"):
            user_data = {
                "github_username": session.get("github_username"),
                "clerk_user_id": user_id,
                "github_name": session.get("github_username"),
                "github_profile_url": f"https://github.com/{session.get('github_username')}",
            }
        else:
            console.print("[yellow]No active user session found.[/yellow]")
            return

    table = Table(title="Current Verified Session")
    table.add_column("Field", style="cyan")
    table.add_column("Value", style="green")

    table.add_row("GitHub Username", f"@{user_data.get('github_username')}")
    table.add_row("Name", str(user_data.get("github_name") or "N/A"))
    table.add_row("Email", str(user_data.get("github_email") or "N/A"))
    table.add_row("Profile URL", str(user_data.get("github_profile_url") or "N/A"))
    table.add_row("Public Repos", str(user_data.get("github_public_repos", 0)))
    table.add_row("Clerk User ID", str(user_data.get("clerk_user_id") or "N/A"))
    table.add_row("Last Login", str(user_data.get("last_login_at") or "N/A"))

    console.print(table)


def _show_help():
    console.print(f"[bold cyan]GitAI v{VERSION}[/bold cyan] - Natural language Git & GitHub assistant\n")
    console.print("[bold]Usage:[/bold]")
    console.print("  [green]gitai[/green]                                Start interactive assistant shell")
    console.print("  [green]gitai \"<command>\"[/green]                    Run a one-shot natural language command")
    console.print("  [green]gitai --set-groq-key <KEY>[/green]           Save your Groq API key")
    console.print("  [green]gitai --whoami[/green]                         Show active user session info")
    console.print("  [green]gitai --relogin[/green]                        Force re-login with GitHub")
    console.print("  [green]gitai --version[/green]                        Print GitAI version")
    console.print("  [green]gitai --help[/green]                           Show this help message\n")
    console.print("[bold]Examples:[/bold]")
    console.print("  gitai \"create repo payment at ./gitflow\"")
    console.print("  gitai \"create file README.md with content Hello World\"")
    console.print("  gitai \"show my repos\"")
    console.print("  gitai \"git status\"\n")


async def _async_main(query_args: list[str], force_relogin: bool):
    await _ensure_logged_in(force_relogin=force_relogin)

    from rich.markdown import Markdown
    try:
        from .orchestrator import Orchestrator
        from .auth import logout
    except (ImportError, ValueError):
        from orchestrator import Orchestrator
        from auth import logout

    console.print("Setting up GitAI...")
    try:
        orch = Orchestrator()
    except Exception as e:
        console.print(f"[bold red]Failed to initialize:[/bold red] {e}")
        return

    # One-shot command mode
    if query_args:
        query = " ".join(query_args)
        console.print(f"[bold]you>[/bold] {query}")
        with console.status("[dim]working...[/dim]"):
            payload = await orch.handle_query(query)
        console.print(Markdown(payload["response"]))
        console.print()
        logout()
        return

    # Interactive REPL mode
    console.print("[green]Ready.[/green] Type 'whoami' for user profile, 'relogin' to switch accounts, or 'exit' to quit.\n")

    try:
        while True:
            try:
                user_input = console.input("[bold]you>[/bold] ")
            except (EOFError, KeyboardInterrupt):
                break
            if user_input.strip().lower() in {"exit", "quit"}:
                break
            if not user_input.strip():
                continue

            cmd = user_input.strip().lower()
            if cmd in {"whoami", "user", "profile"}:
                _print_user_profile()
                continue
            if cmd in {"relogin", "login"}:
                await _ensure_logged_in(force_relogin=True)
                continue
            if cmd in {"logout", "signout"}:
                logout()
                console.print("[yellow]Logged out. Run 'relogin' to sign in again.[/yellow]\n")
                continue

            with console.status("[dim]working...[/dim]"):
                payload = await orch.handle_query(user_input)

            console.print(Markdown(payload["response"]))
            console.print()
    finally:
        logout()
        console.print("[dim]Session closed. Goodbye.[/dim]")


def run_cli():
    """Console script entrypoint."""
    raw_args = sys.argv[1:]

    # 1. Instant flag handling without starting event loop
    if "--help" in raw_args or "-h" in raw_args:
        _show_help()
        return

    if "--version" in raw_args or "-v" in raw_args:
        console.print(f"GitAI version {VERSION}")
        return

    if "--set-groq-key" in raw_args:
        idx = raw_args.index("--set-groq-key")
        if idx + 1 < len(raw_args):
            k = raw_args[idx + 1]
            config.set_groq_api_key(k)
            console.print("[bold green]✓ Groq API key saved successfully to ~/.gitai/config.json[/bold green]")
            return
        else:
            console.print("[red]Error: Missing key argument after --set-groq-key[/red]")
            return

    console.print(f"[bold cyan]GitAI[/bold cyan] [dim]v{VERSION}[/dim] - Natural language Git & GitHub assistant")

    # 2. Ensure Groq key exists
    _ensure_groq_key()

    if "--whoami" in raw_args or "--profile" in raw_args:
        _print_user_profile()
        return

    force_relogin = "--relogin" in raw_args or "--login" in raw_args
    query_args = [a for a in raw_args if not a.startswith("--") and not a.startswith("-")]

    try:
        asyncio.run(_async_main(query_args=query_args, force_relogin=force_relogin))
    except KeyboardInterrupt:
        print("\nGoodbye.")


if __name__ == "__main__":
    run_cli()
