"""Track whether server-local file sources are allowed in this process.

Reading `file_path` sources is a trust decision, not a user setting: only
distributions that run on the user's own machine enable it. Standalone headless
always reads paths; the portable loopback web enables them when its launcher
starts the application. Docker and networked deployments serve remote agents,
so they accept image data as base64 and profiles as objects, and their tool
schemas omit `file_path` entirely.
"""

_LOCAL_FILES_ENABLED = False


def enable_local_files() -> None:
    """Allow server-local file sources for this process."""
    global _LOCAL_FILES_ENABLED
    _LOCAL_FILES_ENABLED = True


def local_files_enabled() -> bool:
    """Report whether this process may read server-local file sources."""
    return _LOCAL_FILES_ENABLED
