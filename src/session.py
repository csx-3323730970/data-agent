"""Session data model — lightweight struct, no business logic."""

import time
import json
import os
from dataclasses import dataclass, field


@dataclass
class Session:
    session_id: str
    name: str = "未命名会话"
    messages: list[dict] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    last_active_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "name": self.name,
            "messages": self.messages,
            "metadata": self.metadata,
            "created_at": self.created_at,
            "last_active_at": self.last_active_at,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Session":
        return cls(**d)


class SessionStore:
    """In-memory session store with optional JSON persistence."""

    def __init__(self, persist_dir: str | None = None):
        self._sessions: dict[str, Session] = {}
        self._persist_dir = persist_dir
        if persist_dir and os.path.isdir(persist_dir):
            self._load_all()

    def create(self, session_id: str, name: str = "未命名会话") -> Session:
        s = Session(session_id=session_id, name=name)
        self._sessions[session_id] = s
        return s

    def get(self, session_id: str) -> Session | None:
        s = self._sessions.get(session_id)
        if s:
            s.last_active_at = time.time()
        return s

    def list_sessions(self) -> list[Session]:
        return sorted(
            self._sessions.values(),
            key=lambda s: s.last_active_at,
            reverse=True,
        )

    def save(self, session: Session):
        self._sessions[session.session_id] = session
        if self._persist_dir:
            path = os.path.join(self._persist_dir, f"{session.session_id}.json")
            with open(path, "w", encoding="utf-8") as f:
                json.dump(session.to_dict(), f, ensure_ascii=False, indent=2)

    def _load_all(self):
        if not self._persist_dir:
            return
        for fname in os.listdir(self._persist_dir):
            if fname.endswith(".json"):
                path = os.path.join(self._persist_dir, fname)
                with open(path, "r", encoding="utf-8") as f:
                    d = json.load(f)
                s = Session.from_dict(d)
                self._sessions[s.session_id] = s
