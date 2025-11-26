# Development Guide

This project uses **uv** for dependency management and task execution. All development commands are defined in `pyproject.toml`.

## Setup

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
