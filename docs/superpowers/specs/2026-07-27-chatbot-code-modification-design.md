# Chatbot Code Modification — Design Spec

> **Status:** Approved design
> **Date:** 2026-07-27
> **Supersedes:** 2026-07-24-strategy-lab-chat-design.md (extends with code modification capability)

## Overview

The performance chatbot in the AI Strategy Builder currently provides text-only analysis of backtest results. This spec extends it to also **modify strategy code** conversationally: the chatbot can suggest code changes, the user approves via a button or natural language, the change is applied and validated with a full 10-run batch, and the user is prompted to save to the library.

## Architecture

**Approach:** Enhanced chat + existing refine-direct bridge (Approach 1 from brainstorming).

The chat LLM is prompted to detect code-change intent and emit a structured marker (`[CODE_CHANGE: <instruction>]`). The frontend parses this marker and shows an "Apply change" button. Clicking it calls the existing `POST /sessions/{id}/refine-direct` endpoint, which modifies the code, validates with a full batch, and returns the result.

## Data Flow

```
User: "add a SPY > 20d MA filter"
  → POST /chat
  → LLM detects code intent, emits [CODE_CHANGE: add SPY > 20d MA filter to entry_score]
  → Response: { response: "...analysis...", code_change_instruction: "add SPY > 20d MA filter to entry_score" }
  → Frontend shows analysis + [Apply change] button
  → User clicks [Apply change] (or types "yes, apply it")
  → POST /refine-direct { instruction: "add SPY > 20d MA filter to entry_score", validation_runs: 10 }
  → Backend: modify → validate (10-run batch) → debug loop (up to 3 cycles)
  → Response: { code: "...", validation_status: "passed", validation_log: [...] }
  → Frontend: updates session code, shows [Save to library] button
  → User clicks [Save to library] → save dialog → saved
```

## Backend Changes

### 1. Chat Service (`backend/app/services/strategy_lab_chat.py`)

**Enhanced system prompt** — The `chat_with_llm()` system prompt gets two additions:

a) **Code-change marker instruction:**
```
If the user asks you to modify the strategy code (add/remove/change filters,
adjust parameters, change exit logic, etc.), include a code-change marker at
the END of your response in this exact format:

[CODE_CHANGE: <one-line instruction describing the change>]

The marker must be on its own line at the very end.
If the user is just asking a question or requesting analysis, do NOT include the marker.
```

b) **Clarifying question instruction:**
```
If the user asks to modify the code but the request is ambiguous or
could be interpreted multiple ways, ask ONE clarifying question before
proceeding. For example:
  User: "make it more aggressive"
  Bot: "Do you mean widen the trailing stop, increase max_holdings,
or reduce min_hold_days?"

Only include the [CODE_CHANGE: ...] marker when the instruction is
clear and specific enough to act on.
```

**Marker parser** — New helper function:
```python
def _extract_code_change(text: str) -> Tuple[str, Optional[str]]:
    """Parse [CODE_CHANGE: ...] marker from the end of the response.
    Returns (cleaned_text, instruction_or_None)."""
    import re
    m = re.search(r'\n?\[CODE_CHANGE:\s*(.+?)\]\s*$', text, re.DOTALL)
    if m:
        instruction = m.group(1).strip()
        cleaned = text[:m.start()].strip()
        return cleaned, instruction
    return text, None
```

**Return value change** — `chat_with_llm()` now returns `(response_text, history, code_change_instruction)` instead of `(response_text, history)`.

### 2. Router (`backend/app/routers/strategy_lab.py`)

**ChatResponse model** — New optional field:
```python
class ChatResponse(BaseModel):
    response: str
    history: List[ChatMessageResponse]
    code_change_instruction: Optional[str] = None  # NEW
```

**post_chat endpoint** — Passes through the parsed `code_change_instruction` from the chat service.

**RefineDirectRequest model** — New optional field:
```python
class RefineDirectRequest(BaseModel):
    instruction: str = Field(..., min_length=1)
    model: Optional[str] = None
    validation_runs: int = Field(10, ge=1, le=50)  # NEW
```

**post_refine_direct endpoint** — When `validation_runs > 1`, runs a mini-batch of N backtests instead of a single backtest during validation. All N must pass for the change to be accepted. The debug loop still runs up to 3 cycles.

### 3. Frontend API Client (`frontend/src/lib/strategyLab.ts`)

**ChatResponse type** — New field:
```typescript
export interface ChatResponse {
  response: string;
  history: ChatMessage[];
  code_change_instruction?: string;  // NEW
}
```

**ChatMessage type** — New optional field for display:
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

**refineDirect function** — New parameter:
```typescript
refineDirect: (id: string, body: { instruction: string; model?: string; validation_runs?: number }) =>
  postJson<RefineDirectResponse>(`${base}/sessions/${id}/refine-direct`, body),
```

## Frontend Changes

### 1. ChatPanel (`frontend/src/components/strategy-lab/ChatPanel.tsx`)

**Code-change button** — When a bot message has `code_change_instruction`, render an "Apply change" button below the message:
- Button text: "Apply change" with a Wand2 icon
- Positioned below the message bubble, left-aligned with the bot messages
- Disabled while an apply is in progress

**Apply mutation** — Calls `refineDirect` with the instruction and `validation_runs=10`:
- On success: inserts a system message in the chat confirming the result
- Shows a "Save to library" button below the confirmation
- On error: shows the error message with a retry button

**Natural language approval** — The chat input handler checks if the user's message is approving a prior code suggestion:
- Keywords: "yes", "apply", "make the change", "do it", "go ahead", "sure"
- If matched and there's a prior bot message with `code_change_instruction`, auto-trigger the apply
- The user's message is still sent to the chat as a normal message

**Save to library** — After successful apply, show a "Save to library" button:
- Clicking it opens an inline dialog (name + change description)
- Calls the existing `saveToLibrary` API
- On success: inserts a confirmation message in the chat

**Progress indicator** — While the apply is running (10-run batch can take 30-60s):
- Show a live timer like StepCode's code generation: "Applying change... 12s"
- Since refine-direct is a synchronous POST (not streaming), the validation log is shown in full when the call completes, not incrementally

### 2. ChatPanel in All Steps

The ChatPanel is added to:

- **StepIdea** — Below the prompt form. Useful for discussing strategy ideas before generating a plan.
- **StepPlan** — Below the plan display. Useful for discussing the plan before generating code.
- **StepCode** — Below the editor and action row. Serves as a conversational alternative to the "Refine with AI" button.
- **StepBacktest** — Already present, unchanged.
- **StepDeploy** — Below the deploy section.

Each step passes `sessionId` and `defaultModelId` to ChatPanel. No step-specific configuration needed.

## Validation & Error Handling

### Validation Flow
1. LLM modifies the code (syntax check via `ast.parse`)
2. Run a 10-run mini-batch with random date windows
3. If all 10 pass → code is accepted
4. If any fail → debug loop (up to 3 cycles), each cycle re-runs the full 10-run batch
5. If all cycles exhausted → code is saved anyway with a warning

### Error Handling
- **LLM fails to produce code:** Return the error in the chat as a bot message with a retry button
- **Validation fails:** Show the validation log in the chat, offer to save the code anyway
- **Network error:** Show a retry button
- **Ambiguous request:** The LLM asks a clarifying question instead of emitting a code-change marker

## Files Modified

| File | Change |
|------|--------|
| `backend/app/services/strategy_lab_chat.py` | Enhanced system prompt, marker parser, return code_change_instruction |
| `backend/app/routers/strategy_lab.py` | ChatResponse.code_change_instruction, RefineDirectRequest.validation_runs |
| `frontend/src/lib/strategyLab.ts` | Updated types, refineDirect signature |
| `frontend/src/components/strategy-lab/ChatPanel.tsx` | Apply button, save button, NL approval, progress indicator |
| `frontend/src/pages/StrategyLab/StepIdea.tsx` | Add ChatPanel |
| `frontend/src/pages/StrategyLab/StepPlan.tsx` | Add ChatPanel |
| `frontend/src/pages/StrategyLab/StepCode.tsx` | Add ChatPanel |
| `frontend/src/pages/StrategyLab/StepDeploy.tsx` | Add ChatPanel |

## Files Unchanged

| File | Reason |
|------|--------|
| `backend/app/services/strategy_lab_llm.py` | refine_code_direct and debug_code are reused as-is |
| `backend/app/services/strategy_lab_prompts.py` | No prompt changes needed |
| `backend/app/services/strategy_lab_orchestrator.py` | _run_one is reused as-is |
| `backend/app/services/strategy_lab_library.py` | save_strategy is reused as-is |
| `frontend/src/pages/StrategyLab/StepBacktest.tsx` | ChatPanel already present |
| `frontend/src/pages/StrategyLab/index.tsx` | No structural changes needed |
