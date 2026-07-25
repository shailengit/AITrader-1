# Strategy Lab — Code Generation Learnings

> Ever-evolving reference for generating working strategy code.
> Update this file whenever a new issue is discovered and fixed.

---

## Golden Rules

### 1. Use the Shared Database Engine — NEVER create your own

**Problem:** The LLM creates `_get_db_engine()` with `create_engine()` per ticker, exhausting PostgreSQL connections ("too many clients already").

**Fix:** Import the shared engine from `app.db.database`:
```python
from app.db.database import engine
```
Do NOT use `create_engine()` anywhere in the generated code. The shared engine manages the connection pool. Creating per-ticker engines exhausts the 100-connection PostgreSQL limit, especially with 4 concurrent workers × ~1500 tickers.

**Prompt rule:** `from app.db.database import engine` — the shared engine manages the connection pool. Creating per-ticker engines exhausts PostgreSQL connections.

### 2. Import `get_safe_table_name` from `app.utils.security`

**Problem:** The LLM guesses `from app.db.database import get_safe_table_name` which doesn't exist.

**Fix:** 
```python
from app.utils.security import get_safe_table_name
```

**Prompt rule:** Explicit import instruction: `from app.utils.security import get_safe_table_name`

### 3. Guard Against NULL `market_cap`

**Problem:** `stock_metadata.market_cap` can be NULL. Calling `float(None)` crashes with `TypeError: float() argument must be a string or a real number, not 'NoneType'`.

**Fix:** Always check before using:
```python
sector, market_cap = _fetch_metadata(ticker)
if market_cap is None or market_cap <= 0:
    continue
```

**Prompt rule:** `market_cap` can be NULL — guard with `if market_cap is None: continue`.

### 4. Use `textwrap.dedent()` When Extracting Code Blocks

**Problem:** Some models (kimi-k2.6, deepseek-v4-flash) indent code blocks inside markdown fences, producing `SyntaxError: unexpected indent`.

**Fix:** Apply `textwrap.dedent()` to extracted code blocks.

### 5. Handle Chain-of-Thought in Content Field

**Problem:** Some models put reasoning/chain-of-thought in the content field instead of a separate reasoning field. This produces 30K+ chars of prose with tiny partial code blocks.

**Fix:** When the extracted code is < 1000 chars, find ALL code blocks in the response and take the longest one. If still too short, make a second call with the original system prompt asking for code only.

### 6. Use Generous `max_tokens` for Code Generation

**Problem:** The model needs ~30K tokens for reasoning + ~4K tokens for code. With `max_tokens=8192`, the code gets truncated mid-fence.

**Fix:** Use `max_tokens=32768` and `timeout=300` for the first code generation call.

---

### 7. JSON-Safe KPIs — No Infinity or NaN

**Problem:** `profit_factor` can be `float("inf")` when there are 0 losing trades. PostgreSQL JSONB rejects `Infinity` with `invalid input syntax for type json`.

**Fix:** Sanitize all float values with `_json_safe()` before building the summary dict:
```python
def _json_safe(val: float) -> float:
    if np.isinf(val) or np.isnan(val):
        return 0.0
    return float(val)
```

**Prompt rule:** All KPI values must be JSON-safe — replace Infinity/NaN with 0.0.

### 8. Use 16K max_tokens for All LLM Calls

**Problem:** The default `max_tokens=2048` was too small for reasoning models that burn tokens on chain-of-thought before producing content. The summarize endpoint with `max_tokens=1024` produced only the first paragraph heading.

**Fix:** Set `_chat()` default to `max_tokens=16384`. All callers use 16384 except code generation (32768).

**Prompt rule:** Always use generous `max_tokens` — 16384 for analysis/chat, 32768 for code generation.

### 9. Call `.mean()` on `.ewm()` Before Accessing `.values`

**Problem:** The LLM writes `close.ewm(span=20, adjust=False).values` which raises `AttributeError: 'ExponentialMovingWindow' object has no attribute 'values'`. The `.ewm()` method returns an `ExponentialMovingWindow` object, not a Series.

**Fix:** Always chain `.mean()` before `.values`:
```python
ema20 = close.ewm(span=20, adjust=False).mean().values  # CORRECT
ema20 = close.ewm(span=20, adjust=False).values          # WRONG
```

**Prompt rule:** Always call `.mean()` on `.ewm()` before accessing `.values`.

### 10. Avoid Triple-Quoted f-strings for SQL

**Problem:** The LLM uses `f"""..."""` or `f'''...'''` for SQL queries containing double-quoted column names like `"Date"`. While valid Python, this confuses syntax highlighters (Monaco, VS Code) which show everything after the string as a comment (brown).

**Fix:** Use concatenated single-line f-strings instead:
```python
query = text(
    f'SELECT "Date", "Close" '
    f'FROM "{table}" WHERE "Date" >= :start'
)
```

**Prompt rule:** Use single-line f-strings for SQL. Never triple-quoted f-strings.

---

## Known Anti-Patterns to Reject

| Anti-pattern | Why | Fix |
|---|---|---|
| `create_engine()` | Exhausts PG connections | Use shared `from app.db.database import engine` |
| `from app.db.database import get_safe_table_name` | Doesn't exist there | Use `from app.utils.security import get_safe_table_name` |
| `float(market_cap)` without None check | NULL in DB crashes | Guard with `if market_cap is None: continue` |
| `os.environ.setdefault(...)` for DB config | Not needed with shared engine | Remove — shared engine handles this |
| `_get_db_engine()` helper function | Creates per-call engines | Remove entirely |
| Plain dict `CONFIG = {...}` | Engine expects `StrategyConfig` | Use `_engine.StrategyConfig(...)` |
| VBT/vectorbt APIs | Not compatible with StrategyEngine | Use pandas/numpy only |
| `pd.Timestamp(x)` with numpy arrays | Type mismatch | Use `np.datetime64()` for searchsorted keys |

---

## Never Throw 502 on LLM Failure

**Rule:** Every endpoint must NEVER return a 502. If an LLM call fails, return a 200 with an `error` field in the response body. The frontend shows a clear error message with a Retry button.

**Why:** A 502 is a cryptic server error that confuses users. A graceful failure with a clear message and retry button is much better UX.

**Implementation:** Every endpoint in `strategy_lab.py` that calls an LLM catches failures and returns a 200 response with an `error` field instead of raising `HTTPException(502)`. All response models (PlanResponse, GenerateCodeResponse, RefineCodeResponse, SummarizeResponse, RefineStrategyResponse, ChatResponse) include an optional `error: Optional[str]` field.

**Affected endpoints:** `/plan`, `/generate-code`, `/refine-code`, `/batches/{id}/summarize`, `/batches/{id}/refine`, `/chat`.

## LLM Call Reliability — Three Layers of Defense

LLM calls fail for three reasons. Each has a fix:

| Failure | Root Cause | Fix |
|---------|------------|-----|
| Timeout | Client timeout (90s) < per-request timeout (180s) | Client timeout → 300s |
| Transient failure | `max_retries=0` | `max_retries=2` |
| Model unavailable | Single model, no fallback | Auto-fallback to `OLLAMA_MODEL_FALLBACK` (minimax-m3:cloud) |

**Implementation:** `_get_client_and_model()` in `strategy_lab_llm.py` creates the client with `timeout=300, max_retries=2`. The `_chat()` function tries the primary model first; if it returns a 404/model-not-found error, it retries with the fallback model.

## Coding Agent Architecture

The code generation is now a 3-stage process, not a single LLM call:

### Stage 1: Generate
- LLM receives: plan + reference template (`strategies/_template.py`) + accumulated learnings + rules
- LLM fills in the 4 function bodies in the template
- All boilerplate (imports, engine wiring, CONFIG) is pre-verified in the template

### Stage 2: Validate
1. Syntax check (`ast.parse`)
2. Import check (try importing the module)
3. Backtest check (`_run_one` with a single date window)

### Stage 3: Debug (if validation fails)
- Separate LLM call with error message + failing code
- Produces a surgical unified diff (not a full rewrite)
- Diff is applied and code is re-validated
- Up to 3 debug cycles before falling back to save-anyway

### Key Files
- `strategies/_template.py` — known-working reference template
- `backend/app/services/strategy_lab_prompts.py:make_debug_prompt()` — debug prompt
- `backend/app/services/strategy_lab_llm.py:debug_code()` — debug LLM call
- `backend/app/routers/strategy_lab.py:post_generate_code()` — 3-stage loop

## Validation Checklist (run after every code generation)

- [ ] `from app.db.database import engine` present (not `create_engine`)
- [ ] `from app.utils.security import get_safe_table_name` present
- [ ] All 4 functions defined: `precompute`, `entry_score`, `holding_score`, `exit_check`
- [ ] Uses `StrategyConfig` (not a plain dict)
- [ ] `market_cap` guarded against None
- [ ] No `create_engine()` calls
- [ ] No `os.environ.setdefault()` for DB config
- [ ] Python syntax valid (`ast.parse` passes)
- [ ] Single backtest run completes (not crashes)
- [ ] 10-run batch completes with 0 failures
