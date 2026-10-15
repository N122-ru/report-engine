"""Synchronize browser reports with remote MCP clients through session tokens.

Session state stays in RAM without server disk writes. The browser persists
text and metadata in localStorage and image originals in IndexedDB.
"""

import time
import secrets
import asyncio
import os
import re
import mimetypes
import hashlib
import json
import difflib
from collections import deque
from collections import Counter
from urllib.parse import unquote
from markdown_it import MarkdownIt
from typing import Dict, List, Optional, Set, Any

from .markdown_parser import _image_size
from .image_input import MAX_IMAGE_SIZE, MAX_IMAGES_COUNT
from .report_safety import OperationCache, ReportVerification, with_snapshot
from .security import validate_markdown_size
from .image_refs import canonical_image_name

MAX_INACTIVE_HOURS = 48


def build_content_patches(before: str, after: str) -> List[Dict[str, Any]]:
    """Build one compact replacement using Python Unicode code-point offsets."""
    before_chars = list(before)
    after_chars = list(after)
    prefix = 0
    while prefix < len(before_chars) and prefix < len(after_chars) and before_chars[prefix] == after_chars[prefix]:
        prefix += 1
    before_end = len(before_chars)
    after_end = len(after_chars)
    while before_end > prefix and after_end > prefix and before_chars[before_end - 1] == after_chars[after_end - 1]:
        before_end -= 1
        after_end -= 1
    return [{
        "start": prefix,
        "delete_count": before_end - prefix,
        "insert": "".join(after_chars[prefix:after_end]),
    }]


class SessionData:
    """Store one user session's report state in memory."""
    def __init__(self, token: str, meta: Optional[dict] = None, content: str = ""):
        self.token = token
        self.meta: dict = meta or {}
        self.content: str = content
        self.images: Dict[str, bytes] = {}
        self.image_hashes: Dict[str, str] = {}
        self.deleted_images: Set[str] = set()
        self.created_at: float = time.time()
        self.last_active: float = time.time()
        self.listeners: Set[asyncio.Queue] = set()
        self.edit_history: deque[dict] = deque(maxlen=20)
        self.verification = ReportVerification()
        self.operation_cache = OperationCache()
        self._revision_cache: dict[str, str] = {}
        # MCP reads may run concurrently, but mutations for one session must
        # observe revisions in order and never overwrite one another.
        self.mcp_write_lock = asyncio.Lock()

    def touch(self) -> None:
        self.last_active = time.time()

    @property
    def revision(self) -> str:
        cached = self._revision_cache.get("revision")
        if cached is None:
            cached = hashlib.sha256(self.content.encode("utf-8")).hexdigest()
            self._revision_cache["revision"] = cached
        return cached

    @property
    def meta_revision(self) -> str:
        cached = self._revision_cache.get("meta_revision")
        if cached is None:
            data = json.dumps(self.meta, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            cached = hashlib.sha256(data.encode("utf-8")).hexdigest()
            self._revision_cache["meta_revision"] = cached
        return cached

    @property
    def image_revision(self) -> str:
        cached = self._revision_cache.get("image_revision")
        if cached is None:
            data = json.dumps({
                "images": sorted(
                    (name, self.image_hashes.get(name) or hashlib.sha256(raw).hexdigest())
                    for name, raw in self.images.items()
                ),
                "deleted": sorted(self.deleted_images),
            }, ensure_ascii=False, separators=(",", ":"))
            cached = hashlib.sha256(data.encode("utf-8")).hexdigest()
            self._revision_cache["image_revision"] = cached
        return cached

    def _invalidate_revision(self, field: str) -> None:
        """Drop one cached revision after its corresponding state changes."""
        self._revision_cache.pop(field, None)

    @property
    def snapshot_id(self) -> str:
        """Return the combined revision for an atomic report snapshot."""
        return with_snapshot({
            "revision": self.revision,
            "meta_revision": self.meta_revision,
            "image_revision": self.image_revision,
        })["snapshot_id"]

    def add_listener(self, queue: asyncio.Queue) -> None:
        self.listeners.add(queue)

    def remove_listener(self, queue: asyncio.Queue) -> None:
        self.listeners.discard(queue)

    async def broadcast(self, event: dict) -> None:
        """Broadcast an event to all connected browser and client listeners."""
        self.touch()
        dead = []
        for q in list(self.listeners):
            try:
                await q.put(event)
            except (asyncio.QueueFull, RuntimeError):
                dead.append(q)
        for q in dead:
            self.listeners.discard(q)

    @staticmethod
    def sanitize_filename(filename: str) -> str:
        """Normalize a filename safely to prevent path traversal."""
        base = os.path.basename(filename.replace("\\", "/")).strip()
        cleaned = re.sub(r"[^\w.\-]", "_", base, flags=re.UNICODE)
        if not cleaned or cleaned.startswith("."):
            cleaned = f"image_{int(time.time())}.png"
        return cleaned

    def add_image(self, filename: str, data: bytes) -> str:
        """Add an image to session memory without writing to disk."""
        if not data:
            raise ValueError("Изображение пустое")
        if len(data) > MAX_IMAGE_SIZE:
            raise ValueError(f"Размер файла превышает лимит {MAX_IMAGE_SIZE // (1024*1024)} МБ")
        safe_name = self.sanitize_filename(filename)
        if safe_name in self.images:
            raise ValueError(f"Изображение «{safe_name}» уже прикреплено")
        if len(self.images) >= MAX_IMAGES_COUNT:
            raise ValueError(f"Превышено максимальное число изображений ({MAX_IMAGES_COUNT})")

        self.images[safe_name] = data
        self.image_hashes[safe_name] = hashlib.sha256(data).hexdigest()
        self.deleted_images.discard(safe_name)
        self._invalidate_revision("image_revision")
        self.verification.changed()
        self.touch()
        return safe_name

    def get_image(self, filename: str) -> Optional[bytes]:
        """Return image bytes by filename directly from memory."""
        safe_name = self.sanitize_filename(filename)
        return self.images.get(safe_name)

    def delete_image(self, filename: str) -> bool:
        """Delete an image from memory."""
        safe_name = self.sanitize_filename(filename)
        removed = self.images.pop(safe_name, None) is not None
        if removed:
            self.image_hashes.pop(safe_name, None)
            self.deleted_images.add(safe_name)
            self._invalidate_revision("image_revision")
            self.operation_cache.clear()
            self.verification.changed()
            self.touch()
        return removed

    def list_images(self, content: Optional[str] = None) -> List[Dict[str, Any]]:
        """List attached images with metadata and their report-reference status."""
        result = []
        used_images = {
            unquote(child.attrGet("src") or "")
            for token in MarkdownIt("commonmark").parse(self.content if content is None else content)
            for child in (token.children or [])
            if child.type == "image"
        }
        normalized_names = Counter(canonical_image_name(name) for name in self.images)
        used_names = {canonical_image_name(src) for src in used_images}
        for name, data in self.images.items():
            mime, _ = mimetypes.guess_type(name)
            mime = mime or "image/png"
            dimensions = _image_size(data)
            result.append({
                "filename": name,
                "size_bytes": len(data),
                "size_kb": round(len(data) / 1024, 1),
                "sha256": self.image_hashes.get(name) or hashlib.sha256(data).hexdigest(),
                "width_px": dimensions[0] if dimensions else None,
                "height_px": dimensions[1] if dimensions else None,
                "mime_type": mime,
                "is_in_report": name in used_images or (
                    normalized_names[canonical_image_name(name)] == 1
                    and canonical_image_name(name) in used_names
                ),
                "url": f"/api/session/{self.token}/images/{name}"
            })
        return result


class SessionManager:
    """Manage the lifecycle of in-memory sessions without disk writes."""
    def __init__(self):
        self._sessions: Dict[str, SessionData] = {}

    def _is_valid_token(self, token: str) -> bool:
        return bool(re.match(r"^(?:tok_|rep_tok_)[a-zA-Z0-9_\-]+$", token))

    def _cleanup_old_sessions(self) -> None:
        """Prune sessions inactive for 48 hours to bound RAM usage."""
        now = time.time()
        max_age = MAX_INACTIVE_HOURS * 3600
        dead_tokens = [
            t for t, s in self._sessions.items()
            if (now - s.last_active) > max_age and len(s.listeners) == 0
        ]
        for t in dead_tokens:
            self._sessions.pop(t, None)

    def _save_to_disk(self, session: SessionData) -> None:
        """Keep persistence a no-op because sessions are stored only in RAM."""
        pass

    def create_token(self) -> str:
        return f"tok_{secrets.token_hex(16)}"

    def get_or_create(self, token: Optional[str] = None) -> SessionData:
        self._cleanup_old_sessions()
        if token and token in self._sessions:
            session = self._sessions[token]
            session.touch()
            return session

        new_token = token if (token and self._is_valid_token(token)) else self.create_token()
        session = SessionData(token=new_token)
        self._sessions[new_token] = session
        return session

    def get(self, token: str) -> Optional[SessionData]:
        session = self._sessions.get(token)
        if session:
            session.touch()
            return session
        return None

    async def update_content(
        self,
        token: str,
        content: str,
        source: str = "web",
        section_name: Optional[str] = None,
        client_id: Optional[str] = None,
    ) -> SessionData:
        validate_markdown_size(content)
        session = self.get_or_create(token)
        if content == session.content:
            return session
        before = session.content
        before_revision = session.revision
        after_revision = hashlib.sha256(content.encode("utf-8")).hexdigest()
        session.edit_history.append({
            "source": source,
            "timestamp": time.time(),
            "before_content": before,
            "before_revision": before_revision,
            "after_revision": after_revision,
            "diff": "".join(difflib.unified_diff(
                before.splitlines(keepends=True), content.splitlines(keepends=True),
                fromfile="до", tofile="после"
            )),
        })
        session.content = content
        session._revision_cache["revision"] = after_revision
        session.verification.changed()
        session.touch()
        patches = build_content_patches(before, content)
        event = {
            "type": "content_updated",
            "source": source,
            "section": section_name,
            "client_id": client_id,
            "revision": after_revision,
            "timestamp": time.time()
        }
        patch_json = json.dumps(patches, ensure_ascii=False, separators=(",", ":"))
        if len(patch_json.encode("utf-8")) < len(content.encode("utf-8")):
            event["content_patches"] = patches
            event["content_base_revision"] = before_revision
        else:
            event["content"] = content
        await session.broadcast(event)
        return session

    async def update_meta(
        self,
        token: str,
        meta: dict,
        source: str = "web",
        client_id: Optional[str] = None,
    ) -> SessionData:
        session = self.get_or_create(token)
        if meta == session.meta:
            return session
        before_meta = session.meta
        before_meta_revision = session.meta_revision
        session.meta = meta
        session._invalidate_revision("meta_revision")
        session.verification.changed()
        session.touch()
        changed = {key: value for key, value in meta.items() if before_meta.get(key) != value}
        removed = [key for key in before_meta if key not in meta]
        event = {
            "type": "meta_updated",
            "source": source,
            "meta_revision": session.meta_revision,
            "client_id": client_id,
            "timestamp": time.time()
        }
        meta_patch = {
            "base_revision": before_meta_revision,
            "changed": changed,
            "removed": removed,
        }
        patch_json = json.dumps(meta_patch, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        meta_json = json.dumps(meta, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        if len(patch_json.encode("utf-8")) < len(meta_json.encode("utf-8")):
            event["meta_patch"] = meta_patch
        else:
            event["meta"] = meta
        await session.broadcast(event)
        return session


# Shared session manager instance.
session_manager = SessionManager()
