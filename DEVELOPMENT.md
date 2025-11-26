# Development Guide

This project uses **uv** for dependency management and task execution. All development commands are defined in `pyproject.toml`.

## Setup

### Quick Start (Fresh Checkout)

For a recently checked out copy of this repository, run the following commands to initialize your development environment:

```bash
# 1. Ensure you have Python 3.13+ installed
python3 --version

# 2. Install uv (if not already installed)
curl -LsSf https://astral.sh/uv/install.sh | sh

# 3. Create and activate a virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# 4. Install all dependencies (including dev tools)
uv sync --all-extras
```

Alternatively, if you have `uv` already installed, you can skip steps 2-3 and let `uv` manage the virtual environment:

```bash
uv sync --all-extras
```

This will automatically create a virtual environment and install all dependencies including development tools (pytest, mypy, type stubs).

### Initial Setup
```bash
uv sync --all-extras
```

This installs all dependencies including development tools (pytest, mypy, type stubs).

### Update Dependencies
```bash
uv sync --upgrade --all-extras
```

Updates all dependencies to their latest versions.

## Running Tasks

All tasks are defined as scripts in `pyproject.toml` and executed via `uv run`.

### Type Checking
```bash
uv run typecheck
```

Runs mypy to check for type errors in the `apantli/` directory.

## Running the Application

### Development Mode
```bash
uv run apantli
```

Starts the apantli server with default settings.

### With Custom Configuration
```bash
uv run apantli --db /path/to/db.sqlite --config /path/to/config.jsonc --env /path/to/.env --host 0.0.0.0 --port 4000
```

## Dependency Management

### View Installed Packages
```bash
uv pip list
```

### Add a New Dependency
```bash
uv add package-name
```

For development-only dependencies:
```bash
uv add --dev package-name
```

### Remove a Dependency
```bash
uv remove package-name
```

### Lock File
The `uv.lock` file is automatically generated and should be committed to version control. It ensures reproducible builds across environments.

## Docker

The project includes a Dockerfile that uses uv for dependency installation:

```bash
docker build -t apantli .
docker run -p 4000:4000 apantli
```

## Troubleshooting

### Dev Tools Not Found
If you get errors like "mypy not found" when running tests, ensure dev dependencies are installed:
```bash
uv sync --all-extras
```

### Stale Dependencies
If you encounter issues with dependencies, try:
```bash
rm uv.lock
uv sync --all-extras
```

This will regenerate the lock file with fresh dependency resolution.
