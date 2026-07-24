# Strategy Lab — AI Analysis Fix + Performance Chatbot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the truncated AI Analysis (summarize) output and add a stateful, multi-LLM performance chatbot to the Strategy Lab backtest results page.

**Architecture:** Backend: bump `max_tokens` for summarize, add `strategy_chat_messages` DB table, new chat service + endpoints. Frontend: new `ChatPanel` component with per-message model picker and critique button, integrated into `StepBacktest`.

**Tech Stack:** FastAPI, PostgreSQL, SQLAlchemy, React, TypeScript, shadcn/ui, Monaco Editor

## Global Constraints

- All LLM `max_tokens` defaults bumped to 16384 (code generation stays at 32768)
- Chat messages persisted in `strategy_chat_messages` table
- Model picker reuses existing `ModelPicker` component from StepIdea
- Critique flow: per-response "Critique" button → inline model dropdown → send to another LLM
- Styling matches Strategy Lab aesthetic (Spectral, IBM Plex Sans, JetBrains Mono, dark theme)

---

### Task 1: Fix Summarize + Bump All Context Windows

**Files:**
- Modify: `backend/app/services/strategy_lab_llm.py`

**Interfaces:**
- Consumes: existing `summarize_batch()`, `generate_plan()`, `generate_refine_diff()`, `refine_strategy()`, `_chat()` functions
- Produces: updated functions with higher `max_tokens`

- [ ] **Step 1: Update `_chat()` default max_tokens**

Change the default `max_tokens` from 2048 to 16384 in the `_chat` function signature.

```python
def _chat(messages: List[Dict[str, str]], model: Optional[str] = None,
          max_tokens: int = 16384, temperature: float = 0.0,
          timeout: int = 180) -> Tuple[Optional[str], Optional[str], Optional[str]]:
```

- [ ] **Step 2: Update `summarize_batch()`**

```python
def summarize_batch(kpis_table: str, n_runs: int, model: Optional[str] = None) -> Tuple[Optional[str], Optional[str]]:
    messages = make_summarize_prompt(kpis_table, n_runs)
    content, _finish, err = _chat(messages, model=model, max_tokens=16384, temperature=0.2)
    return content, err
```

- [ ] **Step 3: Update `generate_plan()`**

```python
content, _finish, err = _chat(messages, model=model, max_tokens=16384, temperature=0.2)
```

- [ ] **Step 4: Update `generate_refine_diff()`**

```python
content, finish_reason, err = _chat(messages, model=model, max_tokens=16384, temperature=0.0)
```

- [ ] **Step 5: Update `refine_strategy()`**

```python
content, finish_reason, err = _chat(messages, model=model, max_tokens=16384, temperature=0.2)
```

- [ ] **Step 6: Verify changes**

```bash
grep -n "max_tokens" backend/app/services/strategy_lab_llm.py
```
Expected: all `max_tokens` values are 16384 or 32768 (for `generate_code`)

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/strategy_lab_llm.py
git commit -m "fix(strategy-lab): bump max_tokens to 16K for all LLM calls, fix summarize truncation"
```

---

### Task 2: New DB Table + ORM Model

**Files:**
- Modify: `backend/app/models/strategy_lab.py`
- Create: `backend/app/alembic/versions/xxxx_add_strategy_chat_messages.py` (or use raw SQL DDL)

**Interfaces:**
- Produces: `StrategyChatMessage` ORM model, `strategy_chat_messages` table

- [ ] **Step 1: Add ORM model to `backend/app/models/strategy_lab.py`**

Add after the existing `StrategyDeployment` class:

```python
class StrategyChatMessage(Base):
    __tablename__ = "strategy_chat_messages"
    id = Column(UUID, primary_key=True, default=uuid.uuid4)
    session_id = Column(UUID, ForeignKey("strategy_sessions.id", ondelete="CASCADE"), nullable=False)
    role = Column(Text, nullable=False)  # "user" | "assistant" | "system"
    content = Column(Text, nullable=False)
    model_id = Column(Text, nullable=False, default="")
    critique_of = Column(UUID, ForeignKey("strategy_chat_messages.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)

    session = relationship("StrategySession", back_populates="chat_messages")
```

Also add the relationship to `StrategySession`:
```python
# In StrategySession class, add:
chat_messages = relationship("StrategyChatMessage", back_populates="session", cascade="all, delete-orphan")
```

- [ ] **Step 2: Create the table via raw SQL**

```bash
DB_PASSWORD=sarina00 psql -h 127.0.0.1 -p 5431 -U postgres -d sp1500_1d -c "
CREATE TABLE IF NOT EXISTS strategy_chat_messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID NOT NULL REFERENCES strategy_sessions(id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
    content TEXT NOT NULL,
    model_id TEXT NOT NULL DEFAULT '',
    critique_of UUID REFERENCES strategy_chat_messages(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_chat_session ON strategy_chat_messages(session_id, created_at);
"
```

- [ ] **Step 3: Verify table exists**

```bash
DB_PASSWORD=sarina00 psql -h 127.0.0.1 -p 5431 -U postgres -d sp1500_1d -c "\d strategy_chat_messages"
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/models/strategy_lab.py
git commit -m "feat(strategy-lab): add StrategyChatMessage ORM model and DB table"
```

---

### Task 3: Chat Service

**Files:**
- Create: `backend/app/services/strategy_lab_chat.py`

**Interfaces:**
- Produces: `get_chat_history()`, `add_chat_message()`, `build_chat_context()`, `chat_with_llm()`

- [ ] **Step 1: Create `backend/app/services/strategy_lab_chat.py`**

```python
"""Chat service for the Strategy Lab performance chatbot.

Provides session-scoped, stateful chat with multi-LLM support and
cross-model critique functionality.
"""
import json
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.strategy_lab import StrategyChatMessage, StrategySession, StrategyExperiment, StrategyBatchSummary
from app.services.strategy_lab_llm import _chat

logger = logging.getLogger(__name__)


def get_chat_history(db: Session, session_id: UUID, limit: int = 20) -> List[Dict[str, Any]]:
    """Return the last N chat messages for a session, oldest first."""
    rows = (
        db.query(StrategyChatMessage)
        .filter(StrategyChatMessage.session_id == session_id)
        .order_by(StrategyChatMessage.created_at.asc())
        .limit(limit)
        .all()
    )
    return [
        {
            "id": str(r.id),
            "role": r.role,
            "content": r.content,
            "model_id": r.model_id,
            "critique_of": str(r.critique_of) if r.critique_of else None,
            "created_at": r.created_at.isoformat() if r.created_at else "",
        }
        for r in rows
    ]


def add_chat_message(db: Session, session_id: UUID, role: str, content: str,
                     model_id: str = "", critique_of: Optional[UUID] = None) -> StrategyChatMessage:
    """Persist a chat message and return the ORM object."""
    msg = StrategyChatMessage(
        session_id=session_id,
        role=role,
        content=content,
        model_id=model_id,
        critique_of=critique_of,
    )
    db.add(msg)
    db.commit()
    db.refresh(msg)
    return msg


def build_chat_context(session: StrategySession) -> str:
    """Build a system context string from the session's plan, code, experiments, and summaries."""
    parts = []

    if session.plan_text:
        parts.append(f"## Strategy Plan\n\n{session.plan_text}")

    if session.code_text:
        # Truncate code to 2000 chars to keep context manageable
        code = session.code_text[:2000]
        parts.append(f"## Strategy Code (truncated)\n\n```python\n{code}\n```")

    # Load experiments
    exps = (
        db.query(StrategyExperiment)
        .filter(StrategyExperiment.session_id == session.id)
        .order_by(StrategyExperiment.created_at.desc())
        .limit(100)
        .all()
    )
    if exps:
        rows = []
        for e in exps:
            k = e.kpis or {}
            rows.append({
                "run": e.run_index,
                "batch": str(e.batch_id)[:8],
                "start": e.start_date.isoformat() if e.start_date else "",
                "ret": k.get("total_return_pct"),
                "wr": k.get("win_rate"),
                "dd": k.get("max_drawdown_pct"),
                "trades": k.get("total_trades"),
                "status": e.status,
            })
        parts.append(f"## Backtest Results ({len(rows)} runs)\n\n{json.dumps(rows, indent=2)}")

    # Load summaries
    summaries = (
        db.query(StrategyBatchSummary)
        .filter(StrategyBatchSummary.session_id == session.id)
        .order_by(StrategyBatchSummary.created_at.desc())
        .limit(5)
        .all()
    )
    if summaries:
        summary_texts = [f"### Summary {i+1}\n{s.summary_text}" for i, s in enumerate(summaries)]
        parts.append("## Batch Summaries\n\n" + "\n\n".join(summary_texts))

    context = "\n\n".join(parts)
    return context


def chat_with_llm(db: Session, session_id: UUID, user_message: str,
                  model: str, critique_of: Optional[UUID] = None) -> Tuple[str, List[Dict[str, Any]]]:
    """Process a chat message and return (response_text, updated_history)."""
    # Store user message
    add_chat_message(db, session_id, "user", user_message, model_id=model)

    # Load session
    session = db.query(StrategySession).filter(StrategySession.id == session_id).first()
    if not session:
        raise ValueError("Session not found")

    # Build context
    context = build_chat_context(session)

    # Build system prompt
    if critique_of:
        # Find the message being critiqued
        critiqued = db.query(StrategyChatMessage).filter(StrategyChatMessage.id == critique_of).first()
        critiqued_text = critiqued.content if critiqued else "(not found)"
        system_prompt = (
            "You are a quantitative analyst critiquing another model's analysis of backtest results. "
            "Be constructive. Point out strengths, weaknesses, gaps, and alternative interpretations. "
            "Reference specific numbers and runs. Be concise but thorough.\n\n"
            f"## Session Context\n\n{context}\n\n"
            f"## Analysis to Critique\n\n{critiqued_text}"
        )
    else:
        system_prompt = (
            "You are a quantitative analyst assistant. You have access to the strategy plan, code, "
            "and backtest results. Answer questions about performance, compare runs, suggest improvements. "
            "Be specific — reference actual numbers and runs. Be concise.\n\n"
            f"## Session Context\n\n{context}"
        )

    # Load conversation history (last 20 messages)
    history = get_chat_history(db, session_id, limit=20)

    # Build messages for LLM
    messages = [{"role": "system", "content": system_prompt}]
    for h in history:
        if h["role"] in ("user", "assistant"):
            messages.append({"role": h["role"], "content": h["content"]})

    # Call LLM
    content, finish_reason, err = _chat(messages, model=model, max_tokens=16384, temperature=0.3, timeout=180)
    if err or content is None:
        raise RuntimeError(err or "LLM returned empty response")

    # Store assistant response
    add_chat_message(db, session_id, "assistant", content, model_id=model, critique_of=critique_of)

    # Return updated history
    updated_history = get_chat_history(db, session_id, limit=20)
    return content, updated_history
```

Note: The `build_chat_context` function needs access to `db`. Let me refactor it to accept `db` as a parameter:

```python
def build_chat_context(db: Session, session: StrategySession) -> str:
    """Build a system context string from the session's plan, code, experiments, and summaries."""
    ...
```

And update `chat_with_llm` to pass `db`:
```python
context = build_chat_context(db, session)
```

- [ ] **Step 2: Verify imports work**

```bash
cd backend && DB_PASSWORD=sarina00 ./venv/bin/python -c "from app.services.strategy_lab_chat import get_chat_history, add_chat_message, build_chat_context, chat_with_llm; print('OK')"
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/services/strategy_lab_chat.py
git commit -m "feat(strategy-lab): add chat service with multi-LLM and critique support"
```

---

### Task 4: Chat Endpoints

**Files:**
- Modify: `backend/app/routers/strategy_lab.py`

**Interfaces:**
- Consumes: `chat_with_llm()`, `get_chat_history()` from `strategy_lab_chat.py`
- Produces: `POST /sessions/{id}/chat`, `GET /sessions/{id}/chat`

- [ ] **Step 1: Add Pydantic models and endpoints to `strategy_lab.py`**

Add after the existing `RefineStrategyResponse` class:

```python
class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1)
    model: str = Field(..., min_length=1)
    critique_of: Optional[str] = None

class ChatMessageResponse(BaseModel):
    id: str
    role: str
    content: str
    model_id: str
    critique_of: Optional[str] = None
    created_at: str

class ChatResponse(BaseModel):
    response: str
    history: List[ChatMessageResponse]
```

Add the endpoints after the `refine_strategy_after_batch` endpoint:

```python
@router.post("/sessions/{session_id}/chat", response_model=ChatResponse)
def post_chat(
    session_id: uuid.UUID,
    body: ChatRequest,
    db: Session = Depends(get_db),
):
    """Send a message to the performance chatbot. Returns response + full history."""
    from app.services.strategy_lab_chat import chat_with_llm
    sess = svc_get_session(db, session_id)
    if sess is None:
        raise HTTPException(status_code=404, detail="session not found")
    try:
        critique_uuid = uuid.UUID(body.critique_of) if body.critique_of else None
        response_text, history = chat_with_llm(
            db, session_id, body.message,
            model=body.model, critique_of=critique_uuid,
        )
    except (ValueError, RuntimeError) as e:
        raise HTTPException(status_code=502, detail={"error": "chat_failed", "details": str(e)})
    return ChatResponse(
        response=response_text,
        history=[ChatMessageResponse(**h) for h in history],
    )


@router.get("/sessions/{session_id}/chat", response_model=List[ChatMessageResponse])
def get_chat(
    session_id: uuid.UUID,
    db: Session = Depends(get_db),
):
    """Retrieve full chat history for a session."""
    from app.services.strategy_lab_chat import get_chat_history
    sess = svc_get_session(db, session_id)
    if sess is None:
        raise HTTPException(status_code=404, detail="session not found")
    history = get_chat_history(db, session_id, limit=100)
    return [ChatMessageResponse(**h) for h in history]
```

- [ ] **Step 2: Verify endpoints load**

```bash
cd backend && DB_PASSWORD=sarina00 ./venv/bin/python -c "
from app.routers.strategy_lab import post_chat, get_chat
print('Endpoints loaded OK')
"
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/routers/strategy_lab.py
git commit -m "feat(strategy-lab): add chat endpoints with multi-LLM and critique support"
```

---

### Task 5: Update API Client

**Files:**
- Modify: `frontend/src/lib/strategyLab.ts`

- [ ] **Step 1: Add chat types and functions**

Add after the existing `RefineStrategyResponse` interface:

```typescript
export interface ChatMessage {
  id: string;
  role: string;
  content: string;
  model_id: string;
  critique_of?: string;
  created_at: string;
}

export interface ChatResponse {
  response: string;
  history: ChatMessage[];
}
```

Add to the `strategyLabApi` object:

```typescript
chat: (id: string, body: { message: string; model: string; critique_of?: string }) =>
  postJson<ChatResponse>(`${base}/sessions/${id}/chat`, body),

getChatHistory: (id: string) =>
  getJson<ChatMessage[]>(`${base}/sessions/${id}/chat`),
```

- [ ] **Step 2: Verify TypeScript compiles**

```bash
cd frontend && npx tsc --noEmit --pretty 2>&1 | head -20
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/lib/strategyLab.ts
git commit -m "feat(strategy-lab): add chat API types and client functions"
```

---

### Task 6: ChatPanel Component

**Files:**
- Create: `frontend/src/components/strategy-lab/ChatPanel.tsx`

- [ ] **Step 1: Create `ChatPanel.tsx`**

```tsx
import { useState, useEffect, useRef } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { motion, AnimatePresence } from "framer-motion";
import { Send, Bot, User, RefreshCw, AlertCircle, MessageSquare } from "lucide-react";
import { strategyLabApi, type ChatMessage } from "../../lib/strategyLab";
import { ModelPicker } from "../../pages/StrategyLab/StepIdea"; // reuse existing

interface ChatPanelProps {
  sessionId: string;
  defaultModelId: string;
}

export function ChatPanel({ sessionId, defaultModelId }: ChatPanelProps) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [selectedModel, setSelectedModel] = useState(defaultModelId);
  const [critiquingId, setCritiquingId] = useState<string | null>(null);
  const [critiqueModel, setCritiqueModel] = useState("");
  const listRef = useRef<HTMLDivElement>(null);

  // Load existing chat history
  const { data: history } = useQuery({
    queryKey: ["chat-history", sessionId],
    queryFn: () => strategyLabApi.getChatHistory(sessionId),
  });
  useEffect(() => {
    if (history) setMessages(history);
  }, [history]);

  // Auto-scroll to bottom
  useEffect(() => {
    if (listRef.current) {
      listRef.current.scrollTop = listRef.current.scrollHeight;
    }
  }, [messages]);

  const send = useMutation({
    mutationFn: (body: { message: string; model: string; critique_of?: string }) =>
      strategyLabApi.chat(sessionId, body),
    onSuccess: (r) => setMessages(r.history),
  });

  const handleSend = () => {
    if (!input.trim() || send.isPending) return;
    send.mutate({ message: input.trim(), model: selectedModel });
    setInput("");
  };

  const handleCritique = () => {
    if (!critiquingId || !critiqueModel) return;
    // Find the original user message that prompted the critiqued response
    const critiquedIdx = messages.findIndex((m) => m.id === critiquingId);
    const userMsg = critiquedIdx > 0 ? messages[critiquedIdx - 1] : null;
    const critiquePrompt = userMsg
      ? `Critique the following analysis. The original question was: "${userMsg.content}"\n\nAnalysis to critique:\n${messages.find((m) => m.id === critiquingId)?.content ?? ""}`
      : `Critique the following analysis:\n${messages.find((m) => m.id === critiquingId)?.content ?? ""}`;
    send.mutate({ message: critiquePrompt, model: critiqueModel, critique_of: critiquingId });
    setCritiquingId(null);
    setCritiqueModel("");
  };

  return (
    <div className="slab-panel" style={{ maxWidth: 1280, marginTop: 24 }}>
      <div className="slab-panel__head">
        <span className="slab-eyebrow slab-eyebrow--gold">
          <MessageSquare size={11} style={{ verticalAlign: "middle", marginRight: 6 }} />
          Performance Chat
        </span>
        <span className="slab-mono slab-mono--xs slab-mono--dim">
          ask about any run, compare, or get recommendations
        </span>
      </div>

      <div
        ref={listRef}
        style={{
          maxHeight: 400,
          overflowY: "auto",
          padding: "16px 20px",
          display: "flex",
          flexDirection: "column",
          gap: 12,
        }}
      >
        {messages.length === 0 && !send.isPending && (
          <div style={{ textAlign: "center", padding: "32px 16px", color: "var(--slab-paper-faint)" }}>
            <MessageSquare size={24} style={{ marginBottom: 8, opacity: 0.4 }} />
            <p className="slab-prose" style={{ fontSize: 14 }}>
              Ask about performance — e.g. "why did run 3 underperform?" or "what do the worst runs have in common?"
            </p>
          </div>
        )}

        <AnimatePresence initial={false}>
          {messages.map((msg) => (
            <motion.div
              key={msg.id}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              style={{
                display: "flex",
                flexDirection: "column",
                alignItems: msg.role === "user" ? "flex-end" : "flex-start",
              }}
            >
              <div
                style={{
                  maxWidth: "80%",
                  padding: "10px 14px",
                  borderRadius: 8,
                  background: msg.role === "user"
                    ? "var(--slab-gold)"
                    : "var(--slab-ink-3)",
                  color: msg.role === "user" ? "var(--slab-ink-1)" : "var(--slab-paper)",
                  fontSize: 13,
                  lineHeight: 1.5,
                  whiteSpace: "pre-wrap",
                  wordBreak: "break-word",
                }}
              >
                {msg.content}
              </div>
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 6,
                  marginTop: 4,
                  fontSize: 11,
                  color: "var(--slab-paper-faint)",
                }}
              >
                {msg.role === "assistant" && (
                  <>
                    <Bot size={10} />
                    <span className="slab-mono slab-mono--xs">{msg.model_id || "unknown"}</span>
                    {msg.critique_of && (
                      <span style={{ color: "var(--slab-cyan)" }}>· critique</span>
                    )}
                    <button
                      type="button"
                      onClick={() => {
                        setCritiquingId(msg.id);
                        setCritiqueModel("");
                      }}
                      className="slab-btn slab-btn--xs slab-btn--ghost"
                      style={{ fontSize: 10, padding: "2px 6px" }}
                    >
                      Critique
                    </button>
                  </>
                )}
                {msg.role === "user" && (
                  <>
                    <User size={10} />
                    <span className="slab-mono slab-mono--xs">{msg.model_id || "you"}</span>
                  </>
                )}
              </div>

              {/* Inline critique model picker */}
              {critiquingId === msg.id && msg.role === "assistant" && (
                <motion.div
                  initial={{ opacity: 0, height: 0 }}
                  animate={{ opacity: 1, height: "auto" }}
                  style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 6 }}
                >
                  <span className="slab-mono slab-mono--xs" style={{ color: "var(--slab-paper-faint)" }}>
                    Critique with:
                  </span>
                  <ModelPicker
                    models={[]} // Will be populated from props or a query
                    selected={critiqueModel}
                    onChange={setCritiqueModel}
                    compact
                  />
                  <button
                    type="button"
                    onClick={handleCritique}
                    disabled={!critiqueModel || send.isPending}
                    className="slab-btn slab-btn--xs"
                  >
                    {send.isPending ? "..." : "Go"}
                  </button>
                  <button
                    type="button"
                    onClick={() => setCritiquingId(null)}
                    className="slab-btn slab-btn--xs slab-btn--ghost"
                  >
                    Cancel
                  </button>
                </motion.div>
              )}
            </motion.div>
          ))}
        </AnimatePresence>

        {send.isPending && (
          <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "8px 0" }}>
            <span className="slab-status slab-status--live">
              <span className="slab-status__dot" />
              {critiquingId ? "Critiquing" : "Thinking"}
            </span>
            <span className="slab-mono slab-mono--xs slab-mono--dim">{selectedModel}</span>
          </div>
        )}

        {send.isError && (
          <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "8px 0" }}>
            <span className="slab-mono slab-mono--sm slab-mono--rose" style={{ display: "flex", alignItems: "center", gap: 6 }}>
              <AlertCircle size={12} />
              {String((send.error as Error)?.message ?? "Chat failed")}
            </span>
            <button type="button" onClick={() => send.mutate({ message: input, model: selectedModel })} className="slab-btn slab-btn--xs">
              <RefreshCw size={10} /> Retry
            </button>
          </div>
        )}
      </div>

      {/* Input bar */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 8,
          padding: "12px 16px",
          borderTop: "1px solid var(--slab-rule)",
        }}
      >
        <ModelPicker
          models={[]}
          selected={selectedModel}
          onChange={setSelectedModel}
          compact
        />
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); handleSend(); } }}
          placeholder="Ask about performance..."
          className="slab-input"
          style={{ flex: 1, fontSize: 13 }}
          disabled={send.isPending}
        />
        <button
          type="button"
          onClick={handleSend}
          disabled={!input.trim() || send.isPending}
          className="slab-btn slab-btn--primary"
          style={{ padding: "8px 12px" }}
        >
          <Send size={12} />
        </button>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Verify TypeScript compiles**

```bash
cd frontend && npx tsc --noEmit --pretty 2>&1 | head -20
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/strategy-lab/ChatPanel.tsx
git commit -m "feat(strategy-lab): add ChatPanel component with model picker and critique"
```

---

### Task 7: Integrate ChatPanel into StepBacktest

**Files:**
- Modify: `frontend/src/pages/StrategyLab/StepBacktest.tsx`

- [ ] **Step 1: Import and add ChatPanel**

Add import at top:
```tsx
import { ChatPanel } from "../../components/strategy-lab/ChatPanel";
```

Add after the `PostBatchActions` closing div (around line 178):
```tsx
{isDone && stats && stats.n_completed > 0 && (
  <ChatPanel
    sessionId={session.id}
    defaultModelId={session.model_id}
  />
)}
```

- [ ] **Step 2: Verify TypeScript compiles**

```bash
cd frontend && npx tsc --noEmit --pretty 2>&1 | head -20
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/StrategyLab/StepBacktest.tsx
git commit -m "feat(strategy-lab): integrate ChatPanel into StepBacktest"
```

---

### Task 8: End-to-End Verification

- [ ] **Step 1: Start backend**

```bash
cd backend && DB_PASSWORD=sarina00 ./venv/bin/python -m app.main &
sleep 3
```

- [ ] **Step 2: Test summarize fix**

```bash
# Run a batch first
BATCH_ID=$(curl -s -X POST http://localhost:8000/strategy-lab/sessions/$SESSION_ID/experiments \
  -H "Content-Type: application/json" \
  -d '{"n_runs": 3, "end_date": "2024-01-01", "start_date_min": "2022-01-01", "start_date_max": "2024-01-01"}' | jq -r '.batch_id')
sleep 30
# Summarize
curl -s -X POST "http://localhost:8000/strategy-lab/sessions/$SESSION_ID/batches/$BATCH_ID/summarize" \
  -H "Content-Type: application/json" -d '{}' | jq '.summary_text | length'
```
Expected: summary_text length > 500 chars (all 3 paragraphs)

- [ ] **Step 3: Test chat endpoint**

```bash
curl -s -X POST "http://localhost:8000/strategy-lab/sessions/$SESSION_ID/chat" \
  -H "Content-Type: application/json" \
  -d '{"message": "why did run 1 underperform?", "model": "kimi-k2.6:cloud"}' | jq '.response | length'
```
Expected: response length > 100 chars

- [ ] **Step 4: Test critique**

```bash
# Get the first assistant message ID
MSG_ID=$(curl -s "http://localhost:8000/strategy-lab/sessions/$SESSION_ID/chat" | jq -r '.[] | select(.role=="assistant") | .id' | head -1)
curl -s -X POST "http://localhost:8000/strategy-lab/sessions/$SESSION_ID/chat" \
  -H "Content-Type: application/json" \
  -d "{\"message\": \"Critique the following analysis\", \"model\": \"deepseek-v4-flash:cloud\", \"critique_of\": \"$MSG_ID\"}" | jq '.response | length'
```
Expected: response length > 100 chars

- [ ] **Step 5: Start frontend and verify ChatPanel renders**

```bash
cd frontend && npm run dev &
# Open browser to Strategy Lab page, run a batch, verify ChatPanel appears
```

- [ ] **Step 6: Commit any final fixes**

```bash
git add -A
git commit -m "fix(strategy-lab): final adjustments after E2E verification"
```
