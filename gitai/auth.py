# gitai/auth.py
"""
Handles GitAI's login flow via Clerk using the officially supported approach:
1. Serves a local page that mounts Clerk's own <SignIn /> component
   (loaded from Clerk's CDN, using your app's Publishable Key + Frontend API domain)
2. User signs in with GitHub directly in that page
3. A small script in the page detects sign-in completion and notifies our
   local server with the session ID
4. We use that session ID + Clerk's backend SDK to fetch the user's GitHub
   OAuth access token
5. We fetch the user's GitHub profile details and save/update the user record
   in PostgreSQL (Neon database)
6. We verify the session against the database before completing login
7. Session state is kept securely in-memory and in PostgreSQL — NO auth JSON files on disk.
"""

import webbrowser
import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs

from clerk_backend_api import Clerk

try:
    from . import config
    from .signin_page import build_signin_html
    from .database import (
        save_or_update_user,
        get_active_github_token,
        verify_user_in_db,
        deactivate_user,
        fetch_github_details,
    )
except (ImportError, ValueError):
    import config
    from signin_page import build_signin_html
    from database import (
        save_or_update_user,
        get_active_github_token,
        verify_user_in_db,
        deactivate_user,
        fetch_github_details,
    )

# In-memory session store (no credentials written to disk)
_current_session: dict = {}
_captured = {"session_id": None}


def _frontend_api_domain() -> str:
    """Derives the Frontend API domain from the Publishable Key."""
    import base64
    encoded = config.CLERK_PUBLISHABLE_KEY.split("_")[2]
    padded = encoded + "=" * (-len(encoded) % 4)
    decoded = base64.b64decode(padded).decode("utf-8")
    return decoded.rstrip("$")


class _AuthHTTPHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)

        if parsed.path == "/":
            html = build_signin_html(
                publishable_key=config.CLERK_PUBLISHABLE_KEY,
                frontend_api=_frontend_api_domain(),
            )
            self.send_response(200)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            self.wfile.write(html.encode("utf-8"))

        elif parsed.path == "/capture":
            query = parse_qs(parsed.query)
            session_id = query.get("session_id", [None])[0]
            _captured["session_id"] = session_id

            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"status": "ok"}')

        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass


def _run_server_until_captured():
    server = HTTPServer(("localhost", config.AUTH_CALLBACK_PORT), _AuthHTTPHandler)
    server.timeout = 5
    import time
    deadline = time.time() + 180
    while _captured["session_id"] is None and time.time() < deadline:
        server.handle_request()


def login(force_relogin: bool = False) -> dict:
    """
    Runs the full login flow:
    - Opens local sign-in page via Clerk
    - Obtains Clerk session & GitHub OAuth token
    - Retrieves GitHub account profile details
    - Saves user session & GitHub profile into PostgreSQL database
    - Verifies the database record
    - Keeps session strictly in-memory and inherited process environment (ZERO disk files)
    """
    _captured["session_id"] = None

    server_thread = threading.Thread(target=_run_server_until_captured)
    server_thread.start()

    query_param = "?relogin=true" if force_relogin else ""
    local_url = f"http://localhost:{config.AUTH_CALLBACK_PORT}/{query_param}"
    print(f"Opening browser for sign-in: {local_url}")
    webbrowser.open(local_url)

    server_thread.join(timeout=185)

    session_id = _captured["session_id"]
    if not session_id:
        return {"status": "error", "message": "Login timed out or was cancelled."}

    try:
        clerk = Clerk(bearer_auth=config.CLERK_SECRET_KEY)
        session = clerk.sessions.get(session_id=session_id)
        user_id = session.user_id

        tokens = clerk.users.get_o_auth_access_token(user_id=user_id, provider="oauth_github")
        if not tokens:
            return {"status": "error", "message": "No GitHub account connected to this Clerk user."}

        github_token = tokens[0].token
    except Exception as e:
        return {"status": "error", "message": f"Failed to retrieve GitHub credentials from Clerk: {e}"}

    # Fetch GitHub account details
    github_details = None
    try:
        github_details = fetch_github_details(github_token)
    except Exception as e:
        print(f"Notice: Failed to fetch GitHub account profile details: {e}")

    # Save to database (with automatic retry)
    user_data = None
    db_warning = None
    try:
        user_data = save_or_update_user(
            github_token=github_token,
            clerk_user_id=user_id,
            clerk_session_id=session_id,
            github_details=github_details,
        )
    except Exception as e:
        db_warning = f"Database save warning ({e})"
        print(f"Notice: Could not reach database to record session: {e}")

    # Verify session in database if user_data was saved
    verified_user = None
    if user_data:
        try:
            ok, verified_user, verify_msg = verify_user_in_db(clerk_user_id=user_id)
            if not ok:
                db_warning = verify_msg
        except Exception as e:
            db_warning = f"Database verify notice: {e}"

    # Determine username
    username = (
        (verified_user.get("github_username") if verified_user else None)
        or (user_data.get("github_username") if user_data else None)
        or (github_details.get("github_username") if github_details else None)
        or "user"
    )

    # Store active session in memory and environment for subprocesses (NO files written)
    _current_session["user_id"] = user_id
    _current_session["clerk_session_id"] = session_id
    _current_session["github_username"] = username
    _current_session["github_token"] = github_token

    os.environ["GITAI_CURRENT_USER_ID"] = user_id
    os.environ["GITAI_GITHUB_TOKEN"] = github_token

    resolved_user = verified_user or user_data or {
        "clerk_user_id": user_id,
        "github_username": username,
        "github_name": github_details.get("github_name") if github_details else username,
        "github_email": github_details.get("github_email") if github_details else None,
        "github_public_repos": github_details.get("github_public_repos", 0) if github_details else 0,
        "github_token": github_token,
    }

    return {
        "status": "success",
        "user_id": user_id,
        "user": resolved_user,
        "db_warning": db_warning,
        "message": f"Successfully signed in as @{username}",
    }


def get_current_session() -> dict:
    """Returns the in-memory active session dict."""
    return _current_session.copy()


def get_cached_github_token() -> str | None:
    """
    Retrieves GitHub token for the current session without reading any files from disk.
    Priority: In-memory session -> Environment -> PostgreSQL query.
    """
    if _current_session.get("github_token"):
        return _current_session["github_token"]

    env_token = os.environ.get("GITAI_GITHUB_TOKEN")
    if env_token:
        return env_token

    user_id = _current_session.get("user_id") or os.environ.get("GITAI_CURRENT_USER_ID")
    if user_id:
        try:
            db_token = get_active_github_token(clerk_user_id=user_id)
            if db_token:
                return db_token
        except Exception:
            pass

    return None


def logout():
    """Logs out by marking current session user as inactive in database and clearing in-memory state."""
    user_id = _current_session.get("user_id") or os.environ.get("GITAI_CURRENT_USER_ID")
    _current_session.clear()
    os.environ.pop("GITAI_CURRENT_USER_ID", None)
    os.environ.pop("GITAI_GITHUB_TOKEN", None)

    if user_id:
        try:
            deactivate_user(clerk_user_id=user_id)
        except Exception:
            pass
