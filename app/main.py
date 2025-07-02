from fastapi import FastAPI
from contextlib import asynccontextmanager
from app.db import create_db_and_tables
# Import engine from app.db if it's needed directly in main.py for other purposes later
# from app.db import async_engine # Renamed to async_engine

from dotenv import load_dotenv # For loading .env file

# Load .env file variables into environment
# This should be one of the first things done.
# Uvicorn's --env-file option is another way to do this.
load_dotenv()

from fastapi.templating import Jinja2Templates # Import Jinja2Templates
from fastapi.staticfiles import StaticFiles # To serve static files if needed later

from app.users import fastapi_users, jwt_auth_backend #, cookie_auth_backend (if using cookies)
from app.schemas import UserRead, UserCreate, UserUpdate
from app.routers.auth import router as magic_link_router # Custom magic link routes

# Lifespan context manager for startup and shutdown events
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Database tables are now managed by Alembic migrations.
    # The create_db_and_tables() call is removed.
    # Ensure migrations are run before starting the application.
    print("INFO:     Application startup. Database schema managed by Alembic.")
    # You could add other startup tasks here, like connecting to external services.
    yield
    # Shutdown: Any cleanup tasks can go here
    print("INFO:     Application shutdown.")

app = FastAPI(
    title="Interview-to-BPMN API",
    description="API for managing interviews and generating BPMN diagrams.",
    version="0.1.0",
    lifespan=lifespan # Register the lifespan context manager
)

# --- Static files and Templates ---
# Mount static files directory (for CSS, JS, images if not using CDN exclusively)
# The path "/static" means that files in "app/static" directory will be accessible via "/static" URL path
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# Configure Jinja2 templates
# The directory "app/templates" will store all Jinja2 .html files
templates = Jinja2Templates(directory="app/templates")


@app.get("/")
async def read_root():
    return {"message": "Welcome to the Interview-to-BPMN API!"}

# --- FastAPI Users Routers ---
# Registration router
app.include_router(
    fastapi_users.get_register_router(UserRead, UserCreate),
    prefix="/auth",
    tags=["auth"],
)

# JWT Login/Logout router (standard username/password, may not be used if purely magic link)
# It provides POST /auth/jwt/login and POST /auth/jwt/logout
# If users never set passwords, /login won't work, but /logout is useful for client-side token clearing.
app.include_router(
    fastapi_users.get_auth_router(jwt_auth_backend), # Requires the JWT auth backend
    prefix="/auth/jwt", # Standard prefix
    tags=["auth"],
)

# Users router (e.g., /users/me, /users/{id})
app.include_router(
    fastapi_users.get_users_router(UserRead, UserUpdate),
    prefix="/users",
    tags=["users"],
)

# Custom Magic Link Routes
app.include_router(
    magic_link_router,
    prefix="/auth", # Mounts /request-magic-link and /verify under /auth
    tags=["auth"],
)


# Placeholder for other application-specific routers (interviews, etc.)
from app.routers.interviews import router as interviews_router
from app.routers.wizard import router as wizard_router # Import wizard router

app.include_router(interviews_router, prefix="/interviews", tags=["Interviews"])
app.include_router(wizard_router, prefix="/wizard", tags=["Wizard Pages"])


# Regarding Alembic:
# The plan mentions adding Alembic. If Alembic is fully set up for migrations,
# the create_db_and_tables() call in the lifespan manager would typically be removed.
# Database schema creation and evolution would then be handled by running
# `alembic upgrade head` command manually or as part of a deployment script.
# For this initial setup with SQLite, create_db_and_tables() is a quick way to get started.
# I will proceed with setting up Alembic next as per the plan.
