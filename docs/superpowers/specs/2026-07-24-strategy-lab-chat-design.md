# Strategy Lab — AI Analysis Fix + Performance Chatbot

**Date:** 2026-07-24
**Status:** Draft

## Problem

1. **AI Analysis (Summarize) is truncated.** The "AI Analysis" button after a batch run produces only the first paragraph heading ("Overall Performance and Consistency") with no actual analysis or recommendations. Root cause: `max_tokens=1024` is too small for a 3-paragraph analysis, especially with reasoning models that burn tokens on chain-of-thought before producing content.

2. **No interactive performance Q&A.** Users cannot ask pointed questions about backtest results — e.g., "why did run 3 underperform?", "what do the worst runs have in common?", "should I widen the trailing stop?".

## Design Decisions

### Session-Level Scope
The chatbot has access to the entire session: strategy plan, generated code, all batch results across all batches, and all batch summaries. This allows cross-batch comparisons and questions that reference the strategy logic.

### Inline Panel Below Table
The chat interface lives as an inline panel below the ExperimentTable and PostBatchActions sections in StepBacktest. It does not overlay or replace content.

### Stateful Conversation
Chat messages are persisted in a new `strategy_chat_messages` DB table. The full conversation history (last 20 messages) is sent with each new message so the LLM can reference earlier answers.

### High Context Window
All LLM calls within the app should use generous `max_tokens` values to avoid truncation. This is a standing rule for all LLM interactions.

**Standard:** 16K `max_tokens` for all LLM calls except code generation (32K).

## Architecture

```
┌─────────────────────────────────────────────────┐
│  StepBacktest.tsx                                │
│  ┌─────────────────────────────────────────┐    │
│  │  ExperimentTable (runs grid)             │    │
│  ├─────────────────────────────────────────┤    │
│  │  PostBatchActions (summarize/refine)    │    │
│  ├─────────────────────────────────────────┤    │
│  │  ChatPanel (NEW)                         │    │
│  │  ┌──────────────────────────────────┐   │    │
│  │  │  MessageList                     │   │    │
│  │  │  • System context notice        │   │    │
│  │  │  • User msg [model: kimi-k2.6]  │   │    │
│  │  │  • Bot response [kimi-k2.6]     │   │    │
│  │  │    ┌──────────────────────┐     │   │    │
│  │  │    │ Critique with        │     │   │    │
│  │  │    │ [model dropdown] →  │     │   │    │
│  │  │    └──────────────────────┘     │   │    │
│  │  │  • Critique response [deepseek] │   │    │
│  │  └──────────────────────────────────┘   │    │
│  │  ┌──────────────────────────────────┐   │    │
│  │  │  [ModelPicker ▼]  Input bar  ▶  │   │    │
│  │  └──────────────────────────────────┘   │    │
│  └─────────────────────────────────────────┘    │
└─────────────────────────────────────────────────┘
```

## Backend Changes

### 1. Fix Summarize — `strategy_lab_llm.py`

Change `summarize_batch()`:
- `max_tokens`: 1024 → 4096
- `temperature`: 0.3 → 0.2

### 2. New DB Table — `strategy_chat_messages`

```sql
CREATE TABLE strategy_chat_messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID NOT NULL REFERENCES strategy_sessions(id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
    content TEXT NOT NULL,
    model_id TEXT NOT NULL DEFAULT '',
    critique_of UUID REFERENCES strategy_chat_messages(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_chat_session ON strategy_chat_messages(session_id, created_at);
```

### 3. New ORM Model — `StrategyChatMessage`

In `backend/app/models/strategy_lab.py`:
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
```

### 4. New Chat Service — `strategy_lab_chat.py`

```python
def get_chat_history(db, session_id, limit=20) -> List[dict]
def add_chat_message(db, session_id, role, content) -> StrategyChatMessage
def build_chat_context(session, experiments, summaries) -> str
def chat_with_llm(session_id, user_message, model=None) -> Tuple[str, List[dict]]
```

The `build_chat_context` function assembles:
- Strategy plan
- Strategy code
- All experiments across all batches (as a compact table)
- All batch summaries

The `chat_with_llm` function:
1. Loads session + experiments + summaries
2. Builds system context
3. Loads last 20 messages from DB
4. Calls LLM with system + history + new message
5. Stores user message + assistant response
6. Returns response + updated history

### 5. New Endpoints — `strategy_lab.py`

```python
class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1)
    model: str = Field(..., min_length=1)  # required — which LLM to use
    critique_of: Optional[str] = None     # message_id being critiqued

class ChatResponse(BaseModel):
    response: str
    history: List[ChatMessage]

class ChatMessage(BaseModel):
    id: str
    role: str
    content: str
    model_id: str
    critique_of: Optional[str] = None  # message_id this critiques
    created_at: str

@router.post("/sessions/{session_id}/chat", response_model=ChatResponse)
def post_chat(session_id, body, db):
    """Send a message to the performance chatbot. Returns response + full history.
    If critique_of is set, the LLM is prompted to critique the referenced response."""

@router.get("/sessions/{session_id}/chat", response_model=List[ChatMessage])
def get_chat_history(session_id, db):
    """Retrieve full chat history for a session."""
```

### 6. High Context Window Rule

Update `_chat()` default `max_tokens` from 2048 → 16384. Update all callers:
- `generate_plan`: 2048 → 16384
- `generate_code`: 32768 (unchanged)
- `generate_refine_diff`: 2048 → 16384
- `summarize_batch`: 1024 → 16384
- `refine_strategy`: 2048 → 16384
- `chat_with_llm`: new → 16384

## Frontend Changes

### 1. New Component — `ChatPanel.tsx`

Location: `frontend/src/components/strategy-lab/ChatPanel.tsx`

Props:
```typescript
interface ChatPanelProps {
  sessionId: string;
  defaultModelId: string;
}
```

States:
- **Empty**: Shows a prompt suggesting questions ("Ask about performance...")
- **Loading**: Typing indicator with animated dots, shows which model is responding
- **Messages**: Scrollable list with user (right) and bot (left) bubbles. Each message shows which model generated it. Bot responses have a "Critique" button.
- **Critique mode**: After clicking "Critique", a model dropdown appears inline below the response. User picks a model and clicks "Critique" to send.
- **Error**: Error message with retry button

**Model picker per message:** The input area has a ModelPicker dropdown (reusing the existing component from StepIdea) showing all available Ollama models. The selected model is used for the next message. Defaults to the session's model_id.

**Critique flow:**
1. User gets a response from Model A
2. Clicks "Critique" on that response
3. A model dropdown appears inline (defaults to a different model than A)
4. User selects Model B, clicks "Critique"
5. Backend sends: original question + Model A's response → Model B with prompt: "Critique the following analysis of backtest results. Point out any issues, gaps, or alternative interpretations."
6. Critique response appears as a new message tagged "Critique by Model B"

Styling: Matches the Strategy Lab aesthetic (Spectral headings, IBM Plex Sans body, JetBrains Mono for numbers, dark theme with gold accents).

### 2. Update API Client — `strategyLab.ts`

Add types and functions:
```typescript
interface ChatMessage {
  id: string;
  role: string;
  content: string;
  model_id: string;
  critique_of?: string;
  created_at: string;
}

interface ChatResponse {
  response: string;
  history: ChatMessage[];
}

chat: (id: string, body: { message: string; model: string; critique_of?: string }) =>
  postJson<ChatResponse>(`${base}/sessions/${id}/chat`, body),

getChatHistory: (id: string) =>
  getJson<ChatMessage[]>(`${base}/sessions/${id}/chat`),
```

### 3. Update StepBacktest — `StepBacktest.tsx`

Add `ChatPanel` below the `PostBatchActions` section. Only visible after a batch has completed.

## Data Flow

### Normal question
```
User types question, picks model from dropdown
  → POST /sessions/{id}/chat { message, model }
    → chat_with_llm()
      → Load session (plan, code)
      → Load all experiments (all batches)
      → Load all batch summaries
      → Build system context string
      → Load last 20 chat messages from DB
      → Call LLM(model) with system + history + new message
      → Store user message + assistant response in DB
      → Return { response, history }
  → ChatPanel renders new messages
```

### Critique flow
```
User clicks "Critique" on a bot response
  → Inline model dropdown appears below the response
  → User picks Model B, clicks "Critique"
  → POST /sessions/{id}/chat {
      message: "Critique the following analysis... [original question] [Model A's response]",
      model: "model-b",
      critique_of: "<message-id>"
    }
    → Same flow as normal, but system prompt includes:
      "You are critiquing another model's analysis. Be constructive.
      Point out strengths, weaknesses, gaps, and alternative interpretations."
    → Response stored with critique_of pointing to original message
  → Critique appears as new message tagged "Critique by Model B"
```

## Error Handling

- **LLM timeout/failure**: Show error message in chat with retry button
- **Empty response**: Show "The model returned an empty response" with retry
- **DB failure**: Log error, return 502 with details
- **Session not found**: Return 404

## Verification

1. Run a 10-run batch
2. Click "AI Analysis" — verify all 3 paragraphs are present
3. Type a question in the chat with model A: "why did run 3 underperform?"
4. Verify the response references actual run data
5. Click "Critique" on the response, pick model B
6. Verify critique response appears with different perspective
7. Type a follow-up with model A: "what about the best run?"
8. Verify the response references the earlier conversation
9. Refresh the page — verify chat history is preserved
10. Verify model picker shows all available Ollama models
