# gitai/database.py
"""
Database integration for GitAI.
Stores and verifies user authentication sessions and GitHub account details
in PostgreSQL (Neon).
"""

import os
import re
import time
from datetime import datetime, timezone
from typing import Optional, Dict, Any, Tuple, Callable

from sqlalchemy import (
    create_engine,
    Column,
    Integer,
    BigInteger,
    String,
    Text,
    Boolean,
    DateTime,
)
from sqlalchemy.orm import declarative_base, sessionmaker
from github import Github, Auth

try:
    from . import config
except (ImportError, ValueError):
    import config

Base = declarative_base()


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    clerk_user_id = Column(String(255), unique=True, index=True, nullable=True)
    clerk_session_id = Column(String(255), nullable=True)

    # GitHub account details
    github_id = Column(BigInteger, nullable=True, index=True)
    github_username = Column(String(255), nullable=False, index=True)
    github_name = Column(String(255), nullable=True)
    github_email = Column(String(255), nullable=True)
    github_avatar_url = Column(Text, nullable=True)
    github_profile_url = Column(Text, nullable=True)
    github_bio = Column(Text, nullable=True)
    github_public_repos = Column(Integer, default=0)

    # Authentication details
    github_token = Column(Text, nullable=False)
    is_active = Column(Boolean, default=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    last_login_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "clerk_user_id": self.clerk_user_id,
            "clerk_session_id": self.clerk_session_id,
            "github_id": self.github_id,
            "github_username": self.github_username,
            "github_name": self.github_name,
            "github_email": self.github_email,
            "github_avatar_url": self.github_avatar_url,
            "github_profile_url": self.github_profile_url,
            "github_bio": self.github_bio,
            "github_public_repos": self.github_public_repos,
            "github_token": self.github_token,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "last_login_at": self.last_login_at.isoformat() if self.last_login_at else None,
        }


_engine = None
_session_factory = None


def get_engine():
    global _engine
    if _engine is None:
        db_url = config.DATABASE_URL
        if not db_url:
            raise ValueError("DATABASE_URL is not set in environment or config.py")

        # Explicitly specify driver: prefer psycopg2 if installed, otherwise psycopg
        if "postgresql+" not in db_url:
            try:
                import psycopg2
                driver = "postgresql+psycopg2://"
            except ImportError:
                driver = "postgresql+psycopg://"
            if db_url.startswith("postgres://"):
                db_url = db_url.replace("postgres://", driver, 1)
            elif db_url.startswith("postgresql://"):
                db_url = db_url.replace("postgresql://", driver, 1)

        # Clean channel_binding parameter if present as it can trigger DNS/libpq handshake issues
        if "channel_binding=" in db_url:
            db_url = re.sub(r"[?&]channel_binding=[^&]+", "", db_url)
            if "?" not in db_url and "&" in db_url:
                db_url = db_url.replace("&", "?", 1)

        connect_args = {
            "connect_timeout": 15,
        }

        # Resolve hostaddr automatically to prevent DNS failure on Windows / restrictive ISPs
        try:
            import urllib.parse
            import socket
            parsed = urllib.parse.urlparse(db_url)
            host = parsed.hostname
            if host and "hostaddr=" not in db_url:
                ip = None
                try:
                    infos = socket.getaddrinfo(host, 5432, socket.AF_INET, socket.SOCK_STREAM)
                    if infos and infos[0][4]:
                        ip = infos[0][4][0]
                except Exception:
                    pass

                # If local DNS could not resolve, use known Neon cluster fallback IP
                if not ip and "neon.tech" in host:
                    ip = "52.14.39.200"

                if ip:
                    connect_args["hostaddr"] = ip
        except Exception:
            pass

        _engine = create_engine(
            db_url,
            pool_pre_ping=True,
            pool_recycle=300,
            pool_size=10,
            max_overflow=20,
            connect_args=connect_args,
        )
    return _engine


def get_session_factory():
    global _session_factory
    if _session_factory is None:
        engine = get_engine()
        _session_factory = sessionmaker(
            bind=engine,
            autoflush=False,
            autocommit=False,
            expire_on_commit=False,
        )
    return _session_factory


def retry_db_operation(op: Callable, max_retries: int = 3, delay: float = 1.0) -> Any:
    """Retries a database operation on transient network/DNS errors."""
    last_exc = None
    for attempt in range(1, max_retries + 1):
        try:
            return op()
        except Exception as e:
            last_exc = e
            err_msg = str(e).lower()
            if any(
                k in err_msg
                for k in ["could not translate", "dns", "connection", "timeout", "terminated", "temporary"]
            ):
                if attempt < max_retries:
                    time.sleep(delay * attempt)
                    continue
            raise e
    raise last_exc


def init_db():
    """Ensure database tables exist with retry support."""
    def _op():
        engine = get_engine()
        Base.metadata.create_all(bind=engine)
    try:
        retry_db_operation(_op, max_retries=3, delay=1.0)
    except Exception:
        pass


def fetch_github_details(token: str) -> Dict[str, Any]:
    """Fetches full GitHub profile details using the provided token."""
    gh = Github(auth=Auth.Token(token))
    gh_user = gh.get_user()

    primary_email = gh_user.email
    if not primary_email:
        try:
            for email_obj in gh_user.get_emails():
                if email_obj.primary:
                    primary_email = email_obj.email
                    break
        except Exception:
            pass

    return {
        "github_id": gh_user.id,
        "github_username": gh_user.login,
        "github_name": gh_user.name or gh_user.login,
        "github_email": primary_email,
        "github_avatar_url": gh_user.avatar_url,
        "github_profile_url": gh_user.html_url,
        "github_bio": gh_user.bio,
        "github_public_repos": gh_user.public_repos or 0,
    }


def save_or_update_user(
    github_token: str,
    clerk_user_id: Optional[str] = None,
    clerk_session_id: Optional[str] = None,
    github_details: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Saves or updates user and GitHub account details in the database with retry logic.
    """
    if not github_details:
        try:
            github_details = fetch_github_details(github_token)
        except Exception as e:
            print(f"Notice: Could not fetch GitHub profile details: {e}")
            github_details = {
                "github_username": "github_user",
                "github_name": None,
                "github_email": None,
                "github_public_repos": 0,
            }

    def _save():
        init_db()
        Session = get_session_factory()
        session = Session()
        try:
            user = None
            if clerk_user_id:
                user = session.query(User).filter(User.clerk_user_id == clerk_user_id).first()

            if not user and github_details.get("github_username"):
                user = session.query(User).filter(User.github_username == github_details["github_username"]).first()

            now = datetime.now(timezone.utc)
            if user:
                if clerk_user_id:
                    user.clerk_user_id = clerk_user_id
                if clerk_session_id:
                    user.clerk_session_id = clerk_session_id
                user.github_token = github_token
                user.github_id = github_details.get("github_id") or user.github_id
                user.github_username = github_details.get("github_username") or user.github_username
                user.github_name = github_details.get("github_name") or user.github_name
                user.github_email = github_details.get("github_email") or user.github_email
                user.github_avatar_url = github_details.get("github_avatar_url") or user.github_avatar_url
                user.github_profile_url = github_details.get("github_profile_url") or user.github_profile_url
                user.github_bio = github_details.get("github_bio") or user.github_bio
                user.github_public_repos = github_details.get("github_public_repos", user.github_public_repos)
                user.is_active = True
                user.last_login_at = now
                user.updated_at = now
            else:
                user = User(
                    clerk_user_id=clerk_user_id,
                    clerk_session_id=clerk_session_id,
                    github_token=github_token,
                    github_id=github_details.get("github_id"),
                    github_username=github_details.get("github_username", "unknown"),
                    github_name=github_details.get("github_name"),
                    github_email=github_details.get("github_email"),
                    github_avatar_url=github_details.get("github_avatar_url"),
                    github_profile_url=github_details.get("github_profile_url"),
                    github_bio=github_details.get("github_bio"),
                    github_public_repos=github_details.get("github_public_repos", 0),
                    is_active=True,
                    created_at=now,
                    updated_at=now,
                    last_login_at=now,
                )
                session.add(user)

            session.commit()
            session.refresh(user)
            return user.to_dict()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    return retry_db_operation(_save, max_retries=3, delay=1.0)


def get_active_user(clerk_user_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Retrieves the active user record as a dict from database."""
    def _get():
        init_db()
        Session = get_session_factory()
        session = Session()
        try:
            query = session.query(User).filter(User.is_active == True)
            if clerk_user_id:
                query = query.filter(User.clerk_user_id == clerk_user_id)
            user = query.order_by(User.last_login_at.desc()).first()
            if user:
                return user.to_dict()
            return None
        finally:
            session.close()

    try:
        return retry_db_operation(_get, max_retries=2, delay=0.5)
    except Exception:
        return None


def get_active_github_token(clerk_user_id: Optional[str] = None) -> Optional[str]:
    """Retrieves the valid github token from database for active user."""
    def _token():
        init_db()
        Session = get_session_factory()
        session = Session()
        try:
            query = session.query(User.github_token).filter(User.is_active == True)
            if clerk_user_id:
                query = query.filter(User.clerk_user_id == clerk_user_id)
            row = query.order_by(User.last_login_at.desc()).first()
            if row and row[0]:
                return row[0]
        finally:
            session.close()
        return None

    try:
        return retry_db_operation(_token, max_retries=2, delay=0.5)
    except Exception:
        return None


def verify_user_in_db(clerk_user_id: str) -> Tuple[bool, Optional[Dict[str, Any]], str]:
    """
    Specifically verifies that the signed-in user exists in the database,
    is marked active, and their GitHub token is valid.
    """
    def _verify():
        init_db()
        Session = get_session_factory()
        session = Session()
        try:
            user = session.query(User).filter(User.clerk_user_id == clerk_user_id, User.is_active == True).first()
            if not user:
                return False, None, f"User {clerk_user_id} was not found or inactive in database."

            token = user.github_token
            if not token:
                return False, user.to_dict(), "No GitHub token found in database for this user."

            try:
                gh = Github(auth=Auth.Token(token))
                gh_user = gh.get_user()
                actual_username = gh_user.login
                user.github_username = actual_username
            except Exception as e:
                return False, user.to_dict(), f"GitHub verification failed for @{user.github_username}: {e}"

            now = datetime.now(timezone.utc)
            user.last_login_at = now
            session.commit()
            return True, user.to_dict(), f"Verified @{actual_username} in database."
        except Exception as e:
            session.rollback()
            raise e
        finally:
            session.close()

    try:
        return retry_db_operation(_verify, max_retries=3, delay=1.0)
    except Exception as e:
        return False, None, f"Database verification error: {e}"


def deactivate_user(clerk_user_id: Optional[str] = None, github_username: Optional[str] = None):
    """Marks user as inactive (logout)."""
    try:
        init_db()
        Session = get_session_factory()
        session = Session()
        try:
            query = session.query(User)
            if clerk_user_id:
                query = query.filter(User.clerk_user_id == clerk_user_id)
            elif github_username:
                query = query.filter(User.github_username == github_username)
            user = query.first()
            if user:
                user.is_active = False
                session.commit()
        except Exception:
            session.rollback()
        finally:
            session.close()
    except Exception:
        pass
