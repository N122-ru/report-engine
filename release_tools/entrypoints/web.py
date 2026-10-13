"""PyInstaller entry point for the loopback-only standalone web server."""

from backend.app.standalone_web import main


if __name__ == "__main__":
    main()
