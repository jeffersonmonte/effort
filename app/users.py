import os
from typing import AsyncGenerator, Optional
from uuid import UUID

from fastapi import Depends, Request
from fastapi_users import BaseUserManager, FastAPIUsers, UUIDIDMixin
from fastapi_users.authentication import (
    AuthenticationBackend,
    BearerTransport,
    CookieTransport, # If browser-based login is also desired
    JWTStrategy,
    MagicLinkStrategy,
)
from fastapi_users.db import SQLModelUserDatabase # Use specific SQLModelUserDatabase
from sqlmodel.ext.asyncio.session import AsyncSession  # For async database operations
# If using sync SQLModel engine, we'd use sync session and run_in_threadpool

from app.db import engine # Using the synchronous engine for now
from app.models import User
from app.schemas import UserRead, UserCreate
from sqlmodel import Session as SyncSession # Synchronous session

# For sending emails (magic links)
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart


# --- Environment Variables ---
# It's better to load these via a proper config management system (e.g., Pydantic's BaseSettings)
# For now, direct os.getenv for simplicity in this file.
# Ensure .env is loaded by the application (e.g. uvicorn --env-file .env or python-dotenv in main)
SECRET = os.getenv("AUTH_SECRET", "a_default_secret_key_if_not_set_123") # Fallback for safety
JWT_LIFETIME_SECONDS = int(os.getenv("JWT_LIFETIME_SECONDS", 3600))
APP_BASE_URL = os.getenv("APP_BASE_URL", "http://localhost:8000")

SMTP_HOST = os.getenv("SMTP_HOST", "localhost")
SMTP_PORT = int(os.getenv("SMTP_PORT", 1025))
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
SMTP_FROM_EMAIL = os.getenv("SMTP_FROM_EMAIL", "noreply@example.com")
SMTP_FROM_NAME = os.getenv("SMTP_FROM_NAME", "Your App")


# --- Database Dependency ---
# FastAPI Users expects an async session if using its async components.
# Our current engine in app/db.py is synchronous.
# For a production setup with async FastAPI, an async DB driver (like asyncpg for Postgres)
# and AsyncEngine/AsyncSession from SQLModel would be preferred.
# To bridge this for now with a sync engine:
# We can use `fastapi.concurrency.run_in_threadpool` for DB operations,
# or set up fastapi-users with a synchronous adapter if available/customized.
# The SQLModelUserDatabase is designed for async usage with AsyncSession.

# Let's adapt to use a synchronous session for now, as our engine is sync.
# This means the UserDatabase needs to be synchronous too.
# FastAPI-Users v11+ has better support for sync DB sessions.
# SQLModelUserDatabase can work with a sync session if passed correctly.

# def get_sync_session() -> SyncSession: # Changed from Generator to just Session
#     with SyncSession(engine) as session:
#         yield session # This makes it a generator, which is standard for FastAPI deps

async def get_user_db() -> AsyncGenerator[SQLModelUserDatabase, None]: # FastAPI Users expects async
    # This is tricky with a sync engine. For SQLModelUserDatabase to work as expected by fastapi-users (async),
    # it needs an AsyncSession. If we must use a sync engine, we might need a custom UserDatabase
    # or ensure all calls are wrapped with run_in_threadpool.
    # For simplicity, let's assume we will switch to AsyncEngine later if performance dictates.
    # For now, we'll try to make SQLModelUserDatabase work with what we have,
    # understanding it might not be ideal.
    # The issue is SQLModelUserDatabase methods are async.

    # The official SQLModelUserDatabase needs an AsyncSession.
    # Let's assume we will create an AsyncEngine for fastapi-users if needed,
    # or find a way to make it work with sync.
    # For now, this will likely cause issues if UserDatabase methods are called.
    # I will need to create an AsyncEngine for this to work properly.
    # Let's placeholder this and fix when setting up AsyncEngine.
    # For now, to make the code runnable, I'll use a sync session and acknowledge this needs fixing.

    # Correct approach for SYNC SQLModel engine with FastAPI-Users:
    # FastAPI-Users typically expects async DB operations.
    # If you must use a sync engine, you'd often run DB calls in a threadpool.
    # Or, use a UserDatabase adapter that works synchronously.
    # The provided SQLModelUserDatabase is async.
    #
    # For now, I'll create a synchronous session provider and a synchronous UserDatabase.
    # This means I can't use `SQLModelUserDatabase` directly if it's strictly async.
    # Let me check `fastapi-users-db-sqlmodel` documentation for sync usage.
    # It seems `SQLModelUserDatabase` is inherently async.
    #
    # Plan:
    # 1. Keep current sync engine in `app/db.py` for general app use.
    # 2. For `fastapi-users`, it strongly prefers async. I should set up an AsyncEngine
    #    for it if I want to use `SQLModelUserDatabase`.
    #    Alternatively, one could write a custom sync UserDatabase.
    #
    # Given the project spec implies a lightweight setup, let's stick to one engine.
    # If the engine is sync, then UserDatabase methods must be wrapped.
    # This is complex.
    #
    # Simpler path for now: Assume we will use an AsyncEngine for the whole app soon.
    # For this step, I will define `get_async_session` assuming an `AsyncEngine` exists or will be created.
    # I will create `app/async_db.py` for this.

    # This will be defined in app/async_db.py or app/db.py if we make engine async
    # For now, this is a forward declaration.
    from app.db import get_async_session # This function needs to be created

    async with get_async_session() as session:
        yield SQLModelUserDatabase(session, User)


class UserManager(UUIDIDMixin, BaseUserManager[User, UUID]):
    reset_password_token_secret = SECRET
    verification_token_secret = SECRET

    async def on_after_register(self, user: User, request: Optional[Request] = None):
        print(f"User {user.id} has registered.")
        # Potentially send a welcome email here, or a verification email if not using magiclink for register

    async def on_after_forgot_password(
        self, user: User, token: str, request: Optional[Request] = None
    ):
        print(f"User {user.id} has forgot their password. Reset token: {token}")
        # Send email with password reset link: f"{APP_BASE_URL}/reset-password?token={token}"

    async def on_after_request_verify(
        self, user: User, token: str, request: Optional[Request] = None
    ):
        print(f"Verification requested for user {user.id}. Verification token: {token}")
        # Send email with verification link: f"{APP_BASE_URL}/verify?token={token}"

    async def on_after_magic_link_login(self, user: User, request: Optional[Request] = None) -> None:
        print(f"User {user.id} has logged in via magic link.")
        # This is called after successful magic link login and token exchange for JWT

# JWT Strategy
def get_jwt_strategy() -> JWTStrategy:
    return JWTStrategy(secret=SECRET, lifetime_seconds=JWT_LIFETIME_SECONDS)

# Magic Link Strategy
async def send_magic_link(email_to: str, token: str, subject: str, content: str):
    message = MIMEMultipart()
    message["From"] = f"{SMTP_FROM_NAME} <{SMTP_FROM_EMAIL}>"
    message["To"] = email_to
    message["Subject"] = subject
    message.attach(MIMEText(content, "html")) # Assuming HTML content

    try:
        # Use aiosmtplib for async email sending if in async context
        # For sync context (like a direct call from some parts of fastapi-users if not fully async)
        # smtplib would be used. MagicLinkStrategy expects an async callable.
        # This part needs to be async.
        # If SMTP_HOST is 'localhost' and port 1025, it's likely MailHog.
        # No SSL/TLS needed for MailHog.

        # For now, a synchronous example, but this should be async for MagicLinkStrategy
        # This will block if used in an async function.
        # TODO: Convert to use aiosmtplib if this function is called from an async path.
        # For now, let's print to console / MailHog.
        print(f"Sending email to {email_to} with token {token}")
        print(f"Subject: {subject}")
        print(f"Content: {content}")

        # Example with smtplib (synchronous) - not for direct use in async fastapi-users
        # with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
        #     if SMTP_USER and SMTP_PASSWORD:
        #         server.login(SMTP_USER, SMTP_PASSWORD)
        #     server.sendmail(SMTP_FROM_EMAIL, email_to, message.as_string())
        # print(f"Magic link email supposedly sent to {email_to} via {SMTP_HOST}:{SMTP_PORT}")

    except Exception as e:
        print(f"Error sending magic link email: {e}")
        # In production, log this error properly.

class CustomMagicLinkStrategy(MagicLinkStrategy):
    async def send_magic_link(
        self, user: User, token: str, request: Optional[Request] = None
    ):
        # This method is called by fastapi-users when a magic link needs to be sent.
        # The 'token' here is the one to be embedded in the magic link.
        link = f"{APP_BASE_URL}/auth/verify-magic-token?token={token}" # Path for user to click
        subject = "Your Magic Login Link"
        content = f"<p>Hello {user.email},</p>" \
                  f"<p>Click <a href='{link}'>this link</a> to log in.</p>" \
                  f"<p>If you did not request this, please ignore this email.</p>" \
                  f"<p>Link: {link}</p>" # Also show plain link

        await send_magic_link(user.email, token, subject, content) # Call our email sending utility

def get_magic_link_strategy() -> CustomMagicLinkStrategy:
    return CustomMagicLinkStrategy(secret=SECRET, lifetime_seconds=JWT_LIFETIME_SECONDS) # Use same secret and lifetime for magic token


# Authentication Backend
# Combines transport (how token is sent/received) and strategy (how token is generated/verified)
bearer_transport = BearerTransport(tokenUrl="auth/jwt/login") # Standard token URL for Swagger UI
# cookie_transport = CookieTransport(cookie_name="interview_cookie", cookie_max_age=JWT_LIFETIME_SECONDS)


# Auth backend for JWT (e.g. after magic link verification)
jwt_auth_backend = AuthenticationBackend(
    name="jwt",
    transport=bearer_transport,
    get_strategy=get_jwt_strategy,
)

# Auth backend specifically for handling the magic link sending and token verification (not for session)
# This backend isn't directly used for "logged-in state" protection, but for the magic link flow.
# The MagicLinkStrategy itself is used by the /request-magic-link and /verify-magic-link routes.
# The JWT backend is what provides the actual session JWT after magic link is verified.

# FastAPIUsers instance
# This requires an async session provider (get_user_db)
# If using sync engine, this setup needs careful handling of async/sync boundaries.
# I will proceed assuming an AsyncEngine and get_async_session will be set up in db.py.
async def get_user_manager(user_db: SQLModelUserDatabase = Depends(get_user_db)):
    yield UserManager(user_db)

fastapi_users = FastAPIUsers[User, UUID](
    get_user_manager,
    [jwt_auth_backend], # Only JWT backend for active sessions
)

# Current active user dependency
current_active_user = fastapi_users.current_user(active=True)
current_superuser = fastapi_users.current_user(active=True, superuser=True)

# Routers for fastapi-users
# We need a router for /magic-login and /verify-magic-token
# fastapi-users provides get_auth_router (for jwt login/logout)
# and get_register_router, get_reset_password_router, get_verify_router.
# For magic links, we typically define custom endpoints that use the MagicLinkStrategy.

# The plan:
# POST /auth/request-link -> uses magic_link_strategy.request_magic_link(user)
# POST /auth/verify -> this is usually for exchanging a magic token for a JWT.
# This endpoint will use magic_link_strategy.verify_magic_token(token) then issue a JWT.
# I will create these routes in `app/routers/auth.py`.

# fastapi-users does not directly provide a "magic link router".
# We build it using the strategy.
# The `jwt_auth_backend` is for the JWT part after the magic link has been verified.
# The actual magic link request and verification will be custom endpoints.
# The JWT strategy's `lifetime_seconds` applies to the JWT issued *after* magic link verification.
# The magic link token itself has its own lifetime, also configured by `lifetime_seconds` in MagicLinkStrategy.
# Using the same `SECRET` for both JWT and MagicLink tokens is common but can be different.
# Using the same `lifetime_seconds` for both is also a choice. Magic links are often shorter-lived.
# For now, let's keep it simple.
# The `bearer_transport`'s `tokenUrl` should point to an endpoint that can issue a JWT,
# which is what our custom /auth/verify endpoint will do after validating a magic token.
# Alternatively, `fastapi-users` provides a default JWT login endpoint if forms/passwords were used.
# Since we are magic-link only for login, our /auth/verify will be the effective "login" that produces a JWT.
# The BearerTransport tokenUrl "auth/jwt/login" might be confusing if we don't have such an endpoint.
# Let's set it to our magic link verification endpoint that returns a JWT.
# Or, more simply, the default "auth/jwt/login" is fine for Swagger to know where to *send* a JWT,
# not necessarily where to obtain it if using a non-standard flow like magic links.
# For now, keep as is.
# The user will get the JWT from /auth/verify and then use it as a Bearer token.
# The `jwt_auth_backend` will then validate this Bearer token on protected routes.
