"""PyInstaller entry point for the standalone headless MCP process."""

from backend.app.headless import main


if __name__ == "__main__":
    main()
