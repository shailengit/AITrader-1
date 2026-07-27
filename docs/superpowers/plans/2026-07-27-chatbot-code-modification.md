# Chatbot Code Modification — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the performance chatbot to modify strategy code conversationally, with apply/verify/save flow.

**Architecture:** The chat LLM emits a `[CODE_CHANGE: <instruction>]` marker when it detects code-change intent. The frontend shows an "Apply change" button, which calls the existing `refine-direct` endpoint with a 10-run batch validation. After verification, a "Save to library" button appears.

**Tech Stack:** FastAPI (Python), React/TypeScript, OpenAI-compatible LLM API

## Global Constraints

- All LLM calls use `max_tokens=16384` (32768 for code generation)
- Never throw 502 — return graceful 200 with error field
- Use shared engine from `app.db.database`, never `create_engine()`
- Frontend uses shadcn/ui patterns with `.slab-*` CSS classes
- ChatPanel must work in all steps (Idea, Plan, Code, Backtest, Deploy)

---

### Task 1: Backend — Enhanced Chat Service with Code-Change Detection

**Files:**
- Modify: `backend/app/services/strategy_lab_chat.py`

**Interfaces:**
- Consumes: `_chat()` from `strategy_lab_llm.py`
- Produces: `chat_with_llm()` returns `(response_text, history, code_change_instruction)`

- [ ] **Step 1: Add `_extract_code_change()` helper and enhanced system prompt**

Add the marker parser function and update the system prompt in `chat_with_llm()`:

```python
import re
from typing import Tuple, Optional

def _extract_code_change(text: str) -> Tuple[str, Optional[str]]:
    """Parse [CODE_CHANGE: ...] marker from the end of the response.
    Returns (cleaned_text, instruction_or_None)."""
    m = re.search(r'\n?\[CODE_CHANGE:\s*(.+?)\]\s*$', text, re.DOTALL)
    if m:
        instruction = m.group(1).strip()
        cleaned = text[:m.start()].strip()
        return cleaned, instruction
    return text, None
```

- [ ] **Step 2: Update `chat_with_llm()` system prompt**

In `chat_with_llm()`, add the code-change marker instruction and clarifying-question instruction to the system prompt (non-critique path only):

```python
# In chat_with_llm(), after the existing system prompt for non-critique mode:
system_prompt += (
    "\n\n---\n"
    "CODE CHANGE INSTRUCTIONS:\n"
    "If the user asks you to modify the strategy code (add/remove/change filters, "
    "adjust parameters, change exit logic, etc.), include a code-change marker at "
    "the END of your response in this exact format:\n\n"
    "[CODE_CHANGE: <one-line instruction describing the change>]\n\n"
    "The marker must be on its own line at the very end. "
    "If the user is just asking a question or requesting analysis, do NOT include the marker.\n\n"
    "If the user asks to modify the code but the request is ambiguous or "
    "could be interpreted multiple ways, ask ONE clarifying question before "
    "proceeding. For example:\n"
    "  User: \"make it more aggressive\"\n"
    "  Bot: \"Do you mean widen the trailing stop, increase max_holdings, "
    "or reduce min_hold_days?\"\n\n"
    "Only include the [CODE_CHANGE: ...] marker when the instruction is "
    "clear and specific enough to act on."
)
```

- [ ] **Step 3: Update `chat_with_llm()` return value**

After the LLM call, parse the marker and return it:

```python
# After getting content from _chat():
cleaned_text, code_change_instruction = _extract_code_change(content)

# Store assistant response (with cleaned text, no marker)
add_chat_message(db, session_id, "assistant", cleaned_text, model_id=model, critique_of=critique_of)

# Return updated history
updated_history = get_chat_history(db, session_id, limit=20)
return cleaned_text, updated_history, code_change_instruction
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/strategy_lab_chat.py
git commit -m "feat(chat): add code-change marker detection to chat service"
```

### Task 2: Backend — Router Changes

**Files:**
- Modify: `backend/app/routers/strategy_lab.py`

**Interfaces:**
- Consumes: `chat_with_llm()` from Task 1 (now returns 3-tuple)
- Produces: Updated `ChatResponse` and `RefineDirectRequest` models

- [ ] **Step 1: Update `ChatResponse` model**

```python
class ChatResponse(BaseModel):
    response: str
    history: List[ChatMessageResponse]
    code_change_instruction: Optional[str] = None  # NEW
```

- [ ] **Step 2: Update `post_chat` endpoint**

```python
@router.post("/sessions/{session_id}/chat", response_model=ChatResponse)
def post_chat(...):
    ...
    try:
        response_text, history, code_change_instruction = chat_with_llm(
            db, session_id, body.message,
            model=body.model, critique_of=critique_uuid,
        )
    except (ValueError, RuntimeError) as e:
        ...
    return ChatResponse(
        response=response_text,
        history=[ChatMessageResponse(**h) for h in history],
        code_change_instruction=code_change_instruction,
    )
```

- [ ] **Step 3: Add `validation_runs` to `RefineDirectRequest`**

```python
class RefineDirectRequest(BaseModel):
    instruction: str = Field(..., min_length=1)
    model: Optional[str] = None
    validation_runs: int = Field(10, ge=1, le=50)  # NEW
```

- [ ] **Step 4: Update `post_refine_direct` to use `validation_runs`**

Replace the single `_run_one()` call with a mini-batch loop:

```python
# In post_refine_direct, replace the single _run_one validation:
for cycle in range(max_debug_cycles + 1):
    # Run a mini-batch of N backtests
    failed_count = 0
    last_error = None
    for i in range(body.validation_runs):
        # Generate a random start date within the session's range
        import random
        from datetime import datetime, timedelta
        start = datetime.strptime("2022-01-01", "%Y-%m-%d")
        end = datetime.strptime("2024-01-01", "%Y-%m-%d")
        random_start = start + timedelta(days=random.randint(0, (end - start).days))
        try:
            result = _run_one(
                code_text=code,
                session_id=str(session_id),
                as_of=random_start.strftime("%Y-%m-%d"),
                end_date="2024-01-01",
                run_index=i,
            )
        except Exception as validate_err:
            result = {"status": "failed", "error_message": f"{type(validate_err).__name__}: {validate_err}"}
        
        if result["status"] != "completed":
            failed_count += 1
            last_error = result.get("error_message", "unknown error")
    
    if failed_count == 0:
        # All passed
        svc_update_session(db, session_id, code_text=code)
        return RefineDirectResponse(
            code=code,
            summary=f"Applied: {body.instruction[:120]}",
            validation_status="passed",
            validation_log=validation_log + [f"All {body.validation_runs} runs passed"],
        )
    
    validation_log.append(f"Debug cycle {cycle}: {failed_count}/{body.validation_runs} runs failed — {last_error}")
    
    if cycle >= max_debug_cycles:
        break
    
    # Debug: call LLM to fix
    try:
        fixed, debug_err = debug_code(code, last_error, model=body.model)
        if debug_err or fixed is None:
            validation_log.append(f"Debug cycle {cycle}: debugger failed — {debug_err}")
            continue
        code = fixed
        validation_log.append(f"Debug cycle {cycle}: debugger produced fix ({len(fixed)} chars)")
    except Exception as debug_exc:
        validation_log.append(f"Debug cycle {cycle}: debugger crashed — {debug_exc}")
        continue
```

- [ ] **Step 5: Commit**

```bash
git add backend/app/routers/strategy_lab.py
git commit -m "feat(router): add code_change_instruction and validation_runs to endpoints"
```

### Task 3: Frontend — API Client Types

**Files:**
- Modify: `frontend/src/lib/strategyLab.ts`

- [ ] **Step 1: Update `ChatResponse` type**

```typescript
export interface ChatResponse {
  response: string;
  history: ChatMessage[];
  code_change_instruction?: string;  // NEW
}
```

- [ ] **Step 2: Update `ChatMessage` type**

```typescript
export interface ChatMessage {
  id: string;
  role: string;
  content: string;
  model_id: string;
  critique_of?: string;
  code_change_instruction?: string;  // NEW
  created_at: string;
}
```

- [ ] **Step 3: Update `refineDirect` function signature**

```typescript
refineDirect: (id: string, body: { instruction: string; model?: string; validation_runs?: number }) =>
  postJson<RefineDirectResponse>(`${base}/sessions/${id}/refine-direct`, body),
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/lib/strategyLab.ts
git commit -m "feat(api): add code_change_instruction and validation_runs types"
```

### Task 4: Frontend — Enhanced ChatPanel

**Files:**
- Modify: `frontend/src/components/strategy-lab/ChatPanel.tsx`

- [ ] **Step 1: Add apply change mutation and save mutation**

```typescript
import { Wand2, Save, CheckCircle, Loader } from "lucide-react";

// Inside ChatPanel component, add these state variables and mutations:
const [pendingSave, setPendingSave] = useState(false);
const [saveDialogOpen, setSaveDialogOpen] = useState(false);
const [saveName, setSaveName] = useState("");
const [saveDescription, setSaveDescription] = useState("");
const [applyingInstruction, setApplyingInstruction] = useState<string | null>(null);
const [applyTimer, setApplyTimer] = useState(0);

const applyChange = useMutation({
  mutationFn: (instruction: string) =>
    strategyLabApi.refineDirect(sessionId, {
      instruction,
      model: selectedModel,
      validation_runs: 10,
    }),
  onSuccess: (r) => {
    setApplyingInstruction(null);
    setApplyTimer(0);
    const statusMsg: ChatMessage = {
      id: crypto.randomUUID(),
      role: "assistant",
      content: r.validation_status === "passed"
        ? `✅ Change applied and verified with 10 backtest runs.`
        : `⚠️ Change applied but some validation runs failed. Check the code in Step 3.`,
      model_id: "system",
      critique_of: undefined,
      code_change_instruction: undefined,
      created_at: new Date().toISOString(),
    };
    setMessages(prev => [...prev, statusMsg]);
    setPendingSave(true);
  },
  onError: (e) => {
    setApplyingInstruction(null);
    setApplyTimer(0);
    const errMsg = extractErrorMessage(e);
    const statusMsg: ChatMessage = {
      id: crypto.randomUUID(),
      role: "assistant",
      content: `❌ Failed to apply change: ${errMsg}`,
      model_id: "system",
      critique_of: undefined,
      code_change_instruction: undefined,
      created_at: new Date().toISOString(),
    };
    setMessages(prev => [...prev, statusMsg]);
  },
});

// Live timer for apply in progress
useEffect(() => {
  if (!applyingInstruction) return;
  const startedAt = Date.now();
  const id = setInterval(() => setApplyTimer(Math.floor((Date.now() - startedAt) / 1000)), 250);
  return () => clearInterval(id);
}, [applyingInstruction]);
```

- [ ] **Step 2: Add natural language approval detection in `handleSend`**

```typescript
const handleSend = () => {
  if (!input.trim() || send.isPending) return;
  const msg = input.trim();
  
  // Check for natural language approval of a pending code change
  const approvalKeywords = ["yes", "apply", "make the change", "do it", "go ahead", "sure"];
  const lastBotWithChange = [...messages].reverse().find(
    (m) => m.role === "assistant" && m.code_change_instruction
  );
  if (lastBotWithChange && approvalKeywords.some(k => msg.toLowerCase().includes(k))) {
    // Auto-trigger apply
    applyChange.mutate(lastBotWithChange.code_change_instruction!);
    // Still send the message to chat
    send.mutate({ message: msg, model: selectedModel });
    setInput("");
    return;
  }
  
  send.mutate({ message: msg, model: selectedModel });
  setInput("");
};
```

- [ ] **Step 3: Render "Apply change" button on bot messages with code_change_instruction**

Inside the message rendering loop, after the message bubble and metadata:

```tsx
{/* Apply change button */}
{msg.code_change_instruction && (
  <div style={{ marginTop: 8, display: "flex", gap: 8 }}>
    {applyingInstruction === msg.code_change_instruction ? (
      <span className="slab-status slab-status--live">
        <span className="slab-status__dot" />
        Applying change
        <span className="slab-mono slab-mono--xs slab-mono--dim" style={{ marginLeft: 8 }}>
          {applyTimer}s
        </span>
      </span>
    ) : (
      <button
        type="button"
        onClick={() => {
          setApplyingInstruction(msg.code_change_instruction!);
          applyChange.mutate(msg.code_change_instruction!);
        }}
        disabled={applyChange.isPending}
        className="slab-btn slab-btn--sm slab-btn--primary"
      >
        <Wand2 size={10} /> Apply change
      </button>
    )}
  </div>
)}
```

- [ ] **Step 4: Render "Save to library" button after successful apply**

After the message list, when `pendingSave` is true:

```tsx
{/* Save to library prompt */}
{pendingSave && !saveDialogOpen && (
  <div style={{ display: "flex", gap: 8, padding: "8px 20px", borderTop: "1px solid var(--slab-rule)" }}>
    <button
      type="button"
      onClick={() => setSaveDialogOpen(true)}
      className="slab-btn slab-btn--sm slab-btn--terminal"
    >
      <Save size={10} /> Save to library
    </button>
    <button
      type="button"
      onClick={() => setPendingSave(false)}
      className="slab-btn slab-btn--sm slab-btn--ghost"
    >
      Dismiss
    </button>
  </div>
)}

{saveDialogOpen && (
  <div style={{ padding: "12px 20px", borderTop: "1px solid var(--slab-rule)", display: "flex", flexDirection: "column", gap: 8 }}>
    <input
      type="text"
      value={saveName}
      onChange={(e) => setSaveName(e.target.value)}
      placeholder="Strategy name"
      className="slab-input"
      style={{ fontSize: 13 }}
    />
    <input
      type="text"
      value={saveDescription}
      onChange={(e) => setSaveDescription(e.target.value)}
      placeholder="What changed?"
      className="slab-input"
      style={{ fontSize: 13 }}
    />
    <div style={{ display: "flex", gap: 8 }}>
      <button
        type="button"
        onClick={() => {
          saveToLibrary.mutate();
          setSaveDialogOpen(false);
          setPendingSave(false);
        }}
        disabled={!saveName.trim()}
        className="slab-btn slab-btn--sm slab-btn--primary"
      >
        Save
      </button>
      <button
        type="button"
        onClick={() => setSaveDialogOpen(false)}
        className="slab-btn slab-btn--sm slab-btn--ghost"
      >
        Cancel
      </button>
    </div>
  </div>
)}
```

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/strategy-lab/ChatPanel.tsx
git commit -m "feat(chat): add apply change and save to library buttons to ChatPanel"
```

### Task 5: Frontend — Add ChatPanel to All Steps

**Files:**
- Modify: `frontend/src/pages/StrategyLab/StepIdea.tsx`
- Modify: `frontend/src/pages/StrategyLab/StepPlan.tsx`
- Modify: `frontend/src/pages/StrategyLab/StepCode.tsx`
- Modify: `frontend/src/pages/StrategyLab/StepDeploy.tsx`

- [ ] **Step 1: Add ChatPanel to StepIdea**

In `StepIdea.tsx`, import and add ChatPanel below the prompt form:

```tsx
import { ChatPanel } from "../../components/strategy-lab/ChatPanel";

// Inside the component, after the form and before the closing div:
{sessionId && (
  <ChatPanel
    sessionId={sessionId}
    defaultModelId={modelId}
  />
)}
```

Note: StepIdea needs to expose `sessionId` and `modelId` from its state. If it doesn't have a session yet, ChatPanel is not rendered.

- [ ] **Step 2: Add ChatPanel to StepPlan**

In `StepPlan.tsx`, import and add ChatPanel below the plan display:

```tsx
import { ChatPanel } from "../../components/strategy-lab/ChatPanel";

// Inside the component, after the plan display:
<ChatPanel
  sessionId={session.id}
  defaultModelId={session.model_id}
/>
```

- [ ] **Step 3: Add ChatPanel to StepCode**

In `StepCode.tsx`, import and add ChatPanel below the action row and refine panel:

```tsx
import { ChatPanel } from "../../components/strategy-lab/ChatPanel";

// Inside the component, after the save dialog section:
<ChatPanel
  sessionId={session.id}
  defaultModelId={session.model_id}
/>
```

- [ ] **Step 4: Add ChatPanel to StepDeploy**

In `StepDeploy.tsx`, import and add ChatPanel below the deploy section:

```tsx
import { ChatPanel } from "../../components/strategy-lab/ChatPanel";

// Inside the component, after the deploy section:
<ChatPanel
  sessionId={session.id}
  defaultModelId={session.model_id}
/>
```

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/StrategyLab/StepIdea.tsx frontend/src/pages/StrategyLab/StepPlan.tsx frontend/src/pages/StrategyLab/StepCode.tsx frontend/src/pages/StrategyLab/StepDeploy.tsx
git commit -m "feat(steps): add ChatPanel to Idea, Plan, Code, and Deploy steps"
```
