"""CRUD helpers for strategy_sessions.

Pure database helpers — no business logic, no validation. The router
layer is responsible for input validation and error handling.
"""
import uuid
from typing import List, Optional, Sequence

from sqlalchemy import or_, text
from sqlalchemy.orm import Session

from app.models.strategy_lab import StrategySession


def create_session(
    db: Session,
    *,
    name: str,
    prompt: str,
    model_id: str,
    tags: Optional[Sequence[str]] = None,
) -> StrategySession:
    """Create a new strategy session."""
    sess = StrategySession(
        name=name,
        prompt=prompt,
        model_id=model_id,
        tags=list(tags or []),
    )
    db.add(sess)
    db.commit()
    db.refresh(sess)
    return sess


def get_session(db: Session, session_id: uuid.UUID) -> Optional[StrategySession]:
    """Fetch one session by id, or None."""
    return db.get(StrategySession, session_id)


def list_sessions(
    db: Session,
    *,
    search: Optional[str] = None,
    tags: Optional[Sequence[str]] = None,
    limit: int = 50,
    offset: int = 0,
) -> List[StrategySession]:
    """List sessions, optionally filtered by free-text search and/or tags.

    Free-text search uses ILIKE on name, prompt, plan_text, code_text.
    Tag filter uses array overlap (session must have at least one matching tag).
    """
    q = db.query(StrategySession)
    if search:
        like = f"%{search}%"
        q = q.filter(or_(
            StrategySession.name.ilike(like),
            StrategySession.prompt.ilike(like),
            StrategySession.plan_text.ilike(like),
            StrategySession.code_text.ilike(like),
        ))
    if tags:
        # PostgreSQL array overlap: tags && ARRAY[...]
        tag_array = "{" + ",".join(t.replace('"', '\\"') for t in tags) + "}"
        q = q.filter(text("tags && CAST(:tag_array AS text[])").bindparams(tag_array=tag_array))
    q = q.order_by(StrategySession.updated_at.desc())
    return q.limit(limit).offset(offset).all()


def update_session(
    db: Session,
    session_id: uuid.UUID,
    *,
    plan_text: Optional[str] = None,
    code_text: Optional[str] = None,
    tags: Optional[Sequence[str]] = None,
    name: Optional[str] = None,
) -> Optional[StrategySession]:
    """Update mutable fields on a session. Returns the updated session, or None if not found.

    Pass a value (including None) to set that field. To leave a field unchanged,
    don't pass it.
    """
    sess = db.get(StrategySession, session_id)
    if sess is None:
        return None
    if plan_text is not None:
        sess.plan_text = plan_text
    if code_text is not None:
        sess.code_text = code_text
    if tags is not None:
        sess.tags = list(tags)
    if name is not None:
        sess.name = name
    # Bump updated_at
    sess.updated_at = text("now()")
    db.commit()
    db.refresh(sess)
    return sess


def delete_session(db: Session, session_id: uuid.UUID) -> bool:
    """Delete a session. Returns True if it existed, False otherwise."""
    sess = db.get(StrategySession, session_id)
    if sess is None:
        return False
    db.delete(sess)
    db.commit()
    return True
