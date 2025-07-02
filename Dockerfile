# Use an official Python runtime as a parent image
FROM python:3.11-slim as python-base

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    # Poetry environment variables
    POETRY_VERSION=1.8.3 \
    POETRY_HOME="/opt/poetry" \
    POETRY_VIRTUALENVS_CREATE=false \
    # Path
    PATH="$POETRY_HOME/bin:$PATH"

# Install system dependencies required for Poetry and potentially some Python packages
RUN apt-get update && apt-get install --no-install-recommends -y \
    curl \
    # Add other system dependencies if needed by your Python packages (e.g., build-essential, libpq-dev for psycopg2)
    && rm -rf /var/lib/apt/lists/*

# Install Poetry
RUN curl -sSL https://install.python-poetry.org | python3 -


# --- Builder stage ---
# Used to install dependencies with Poetry
FROM python-base as builder

WORKDIR /app

# Copy only files necessary for installing dependencies
COPY poetry.lock pyproject.toml ./

# Install project dependencies
# --no-interaction: Do not ask any interactive question
# --no-ansi: Disable ANSI output
# --no-dev: Do not install development dependencies (for production image)
# If you need dev dependencies for tests in a stage, create another stage or modify this.
RUN poetry install --no-interaction --no-ansi --no-dev

# --- Runtime stage ---
# Final image with application code and installed dependencies
FROM python-base as runtime

WORKDIR /app

# Copy installed dependencies from the builder stage's virtual environment
# Since POETRY_VIRTUALENVS_CREATE=false, Poetry installs to the system Python site-packages.
# We need to ensure these site-packages are correctly copied or that the Python path is set up.
# If using default Poetry behavior (virtualenvs in project or cache), copying venv is an option.
# With POETRY_VIRTUALENVS_CREATE=false, packages are installed into the global site-packages of the python-base image.
# So, the dependencies installed in the 'builder' stage will be available in 'runtime' if it uses the same python-base
# and same Python version, provided the site-packages location is consistent or discoverable.

# However, a cleaner multi-stage build copies the installed packages.
# Poetry with POETRY_VIRTUALENVS_CREATE=false installs into the system Python's site-packages.
# So, if 'builder' and 'runtime' share the same base Python, the packages are already there.
# Let's make it more explicit by copying from the builder's environment.
# This requires knowing where Poetry installed them.
# With POETRY_VIRTUALENVS_CREATE=false, it's the standard site-packages.
# The path can be found using `python -m site --user-site` or `sysconfig.get_paths()["purelib"]`.

# A simpler approach for POETRY_VIRTUALENVS_CREATE=false:
# The builder stage installs dependencies into its python environment.
# The runtime stage starts from python-base again, copies the installed deps from builder.
# This assumes the site-packages path is standard.
# Example: COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
# This can be fragile if site-packages path changes.

# Alternative with POETRY_VIRTUALENVS_CREATE=false:
# The builder stage IS the runtime stage for dependencies. We just copy app code into it.
# Let's simplify: use a single stage approach for dependencies if POETRY_VIRTUALENVS_CREATE=false,
# or ensure correct copying of site-packages if using multi-stage for this setting.

# Let's refine the multi-stage approach with POETRY_VIRTUALENVS_CREATE=false:
# The builder installs into system python. The runtime image can be the same as builder after copying app code,
# or a fresh python-base and copy the *application code* and the *installed packages*.

# Copy the installed packages from the builder stage.
# Location of site-packages can vary. `python -m site` can show it.
# For python:3.11-slim, it's likely /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
# Copy poetry's own files in case any scripts rely on them, though not usually needed for runtime
COPY --from=builder $POETRY_HOME $POETRY_HOME

# Copy the application code from the current directory into the container
COPY ./app /app/app

# Expose the port the app runs on
EXPOSE 8000

# Command to run the application
# Use uvicorn to run the FastAPI application `app.main:app`
# host 0.0.0.0 to make it accessible from outside the container
# reload for development, but should be off for production image.
# This Dockerfile is more for production, so no --reload.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

# Notes for improvement/production:
# - Use a non-root user.
# - Reduce image size further if possible (e.g., by cleaning up caches more aggressively).
# - For multi-stage, ensure paths for site-packages are robust.
# - The `POETRY_VIRTUALENVS_CREATE=false` simplifies things by not needing to activate a venv in CMD.
# - If dev dependencies were needed for some build step (e.g. compiling static assets),
#   they would be installed in the builder stage before the --no-dev install, or in a separate stage.
# - Ensure .dockerignore is used to prevent copying unnecessary files (like .venv, .git, __pycache__) into the image.
#   This is crucial.
#
# Let's reconsider the COPY --from=builder for site-packages.
# If POETRY_VIRTUALENVS_CREATE=false, poetry installs into the global python environment.
# If 'runtime' stage uses the same 'python-base', the packages are already "there".
# The only thing builder does is run `poetry install`.
# So, a more common pattern for this setting is:
#
# FROM python:3.11-slim as base
# ... (install poetry, set env vars) ...
#
# FROM base as dependencies
# WORKDIR /app
# COPY poetry.lock pyproject.toml ./
# RUN poetry install --no-dev --no-root (or without --no-root if app is a library to be installed)
#
# FROM base as final_image
# WORKDIR /app
# COPY --from=dependencies /app /app  <-- This copies installed venv if create=true, or just project files
# COPY --from=dependencies /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages # If needed
# COPY ./app /app/app
# CMD ...
#
# Given POETRY_VIRTUALENVS_CREATE=false, the builder's Python environment *is* modified with the packages.
# So, if the runtime starts FROM python-base (not FROM builder), it won't have them.
# COPY --from=builder /usr/local/lib/python3.11/site-packages is one way.
#
# A perhaps cleaner way with POETRY_VIRTUALENVS_CREATE=false:
# Stage 1: Install poetry
# Stage 2 (FROM stage1): Install dependencies. This stage now has Python + Poetry + deps.
# Stage 3 (FROM stage1 or even stage2): Copy app code. This stage is the final image.
#
# Let's try this structure:
# FROM python:3.11-slim AS base
# ENV PYTHONUNBUFFERED=1 \
#     POETRY_VERSION=1.8.3 \
#     POETRY_HOME="/opt/poetry" \
#     POETRY_VIRTUALENVS_CREATE=false \
#     PATH="$POETRY_HOME/bin:$PATH"
# RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*
# RUN curl -sSL https://install.python-poetry.org | python3 -

# FROM base AS app_builder
# WORKDIR /app
# COPY poetry.lock pyproject.toml ./
# RUN poetry install --no-dev --no-interaction --no-ansi
# COPY ./app /app/app # Copy app code here as well, in case poetry build/package needs it

# FROM base AS runtime # Start from 'base' which has Python and Poetry
# WORKDIR /app
# COPY --from=app_builder /app /app # This copies the state of /app from app_builder, including its site-packages if installed there
                                # If poetry installed to global site-packages in app_builder, then this needs to copy that.
                                # This is where `POETRY_VIRTUALENVS_CREATE=false` makes it tricky for multi-stage if not careful.

# Let's use the simpler official Poetry recommendation for Docker:
# https://python-poetry.org/docs/docker/
# They use multi-stage but create a venv and activate it.
# If we stick to POETRY_VIRTUALENVS_CREATE=false, it means global install.

# Simpler Dockerfile structure for POETRY_VIRTUALENVS_CREATE=false (less "pure" multi-stage for deps layer):
# Stage 1: Base with Python & Poetry
# Stage 2: Install deps & copy app code (this becomes the final image)

# Reverting to a slightly simpler structure that should work with global site-packages:
# Build poetry layer
FROM python:3.11-slim as poetry-base
ENV PYTHONUNBUFFERED=1 \
    POETRY_VERSION=1.8.3 \
    POETRY_HOME="/opt/poetry" \
    POETRY_VIRTUALENVS_CREATE=false \
    PATH="$POETRY_HOME/bin:$PATH"
RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*
RUN curl -sSL https://install.python-poetry.org | python3 -

# Build dependencies layer
FROM poetry-base as builder
WORKDIR /app
COPY poetry.lock pyproject.toml ./
RUN poetry install --no-dev --no-interaction --no-ansi
# At this point, dependencies are in the global site-packages of this stage's Python.

# Final application image
FROM poetry-base as runtime # Start from poetry-base which has Python and Poetry tool
WORKDIR /app
# Copy installed packages from builder stage to this stage's global site-packages
# This ensures that only necessary prod dependencies are in the final image,
# and they are layered correctly.
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages

COPY ./app /app/app # Copy application code

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

# This structure is more robust for copying dependencies.
# Need a .dockerignore file.
# Example .dockerignore:
# __pycache__/
# *.pyc
# *.pyo
# *.pyd
# .Python
# .env
# .venv/
# venv/
# ENV/
# .git/
# .pytest_cache/
# .mypy_cache/
# build/
# dist/
# *.egg-info/
# .dockerignore
# Dockerfile
# alembic.ini # If not needed in image, or handled by volume
# interview_bpmn.db # Database file, should be a volume
# poetry.lock # Already copied, not needed again if app code doesn't need it at runtime
# pyproject.toml # Same as above
# README.md
# tests/
# alembic/ # If migrations run outside container or via entrypoint script that copies them
#           For now, assume app code includes alembic if needed at runtime for some reason.
#           Usually, migrations are run as a separate step or in an entrypoint.
#           The app itself doesn't need the alembic scripts folder at runtime typically.
#           Let's exclude alembic/ and alembic.ini from app code copy if they are not directly used by app.main.
#           My current app.main does not use alembic code directly.
#           The `interview_bpmn.db` should definitely be in .dockerignore and managed by a volume.
#           `pyproject.toml` and `poetry.lock` are build-time, not runtime, unless app reads them.
#           The `app` directory is the main source.
#           The `tests` directory should be excluded.
#           The root `.env` file should be excluded.
#           The `alembic` directory and `alembic.ini` are for running migrations,
#           not strictly for running the app, unless the app itself triggers migrations (bad practice).
#           For now, I'll assume `COPY ./app /app/app` is fine and .dockerignore will handle exclusions.
#           The `CMD` runs `app.main:app`, so only what's in `app/app` needs to be correct.
#           My `app` folder is at root, and `pyproject.toml` says `packages = [{include = "app"}]`.
#           So, `COPY ./app /app/app` is correct if `app` is the package name.
#           My source code is in `/app`, which is the package.
#           So, `COPY ./app /app/app` should be `COPY ./app /app/` if `app` is the package.
#           Or, if the code inside `./app` is structured as `main.py`, `models.py` etc.,
#           then `COPY ./app /app/` is suitable, and `uvicorn app.main:app` works if CWD is `/app`.
#           My current structure: `app/main.py`, `app/models.py`.
#           So `COPY ./app /app/` is what I want for the application code.
#           The `WORKDIR /app` means `uvicorn main:app` would be used if main.py is in /app.
#           But my `main.py` is in `app/app/main.py` from previous steps.
#           This is confusing. Let's clarify the source structure.
#
# My pyproject.toml: `packages = [{include = "app"}]`
# My source code (main.py, models.py etc) is in the root `app/` directory.
# Example: `app/main.py`, `app/models.py`.
# The `app/app` subdirectory was an earlier mistake I tried to correct.
# Let's check current file structure.
# `ls app/` shows `__init__.py, crud, db.py, main.py, models, routers, schemas, services, static, templates`.
# So, `main.py` is directly in `app/`.
# Thus, `COPY ./app /app/` is correct for copying the application source.
# And `uvicorn app.main:app` means uvicorn looks for an `app` package/directory in PYTHONPATH,
# then `main.py` inside it, then `app` instance inside `main.py`.
# If `WORKDIR /app` is set, and `app` is copied into `/app`, then PYTHONPATH implicitly includes `/app`.
# So `uvicorn main:app` from `/app` directory should work if `main.py` is in `/app`.
# My `main.py` is in `app/`. So `COPY ./app /app/` and `CMD ["uvicorn", "main:app", ...]` from `/app`.
#
# Final check on Dockerfile structure:
# FROM python:3.11-slim AS poetry-base
# ... (install poetry)
# FROM poetry-base AS builder
# WORKDIR /app_build # Use a different workdir to avoid confusion
# COPY poetry.lock pyproject.toml ./
# RUN poetry install --no-dev --no-interaction --no-ansi
# FROM python:3.11-slim AS runtime # Start from a clean python image for smaller size
# WORKDIR /app
# COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
# COPY ./app /app/ # Copy source code into /app
# EXPOSE 8000
# CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"] # Run from /app, main.py is app.main

# This looks more standard. The `PYTHONPATH` in the runtime will include the global site-packages.
# The `main:app` will be resolved from `/app/main.py`.
# This is better.
# The `poetry-base` alias for the final image `FROM poetry-base as runtime` was a mistake.
# It should be `FROM python:3.11-slim as runtime` to ensure it's clean, then copy deps.
# Or, if `poetry-base` IS the intended runtime base (already has python), then it's fine.
# Yes, `poetry-base` just adds poetry tool to `python:3.11-slim`. So it's a good base for runtime too.
# The key is the COPY --from=builder for site-packages.

# One final refinement for clarity and potentially smaller final image:
# The runtime image could start from a more minimal python image if poetry tool itself is not needed at runtime.
# But `poetry-base` is already slim. So this is fine.
# The `COPY --from=builder /usr/local/lib/python3.11/site-packages ...` makes the runtime image
# independent of whether `poetry-base` was used for `builder` or not, as long as paths match.
# This is a robust way.
