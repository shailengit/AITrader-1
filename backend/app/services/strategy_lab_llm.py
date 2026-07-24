"""LLM service wrapper for the AI Strategy Builder.

Wraps the existing llm_engine with strategy_lab_prompts to produce:
  - plan text (Phase 2)
  - strategy code (Phase 2)
  - refined code as a unified diff (Phase 2)
  - batch summaries (Phase 3)
  - refinement diffs based on batch results (Phase 3)

All functions accept an explicit `model` parameter so the caller can
override the default model from the dropdown. The OpenAI client is
created per-request so we can vary the model without monkey-patching
module state.
"""
import logging
import os
import re
import textwrap
from typing import List, Dict, Any, Optional, Tuple

from openai import OpenAI  # type: ignore[import-untyped]

from app.services.strategy_lab_prompts import (
    make_plan_prompt,
    make_code_prompt,
    make_refine_prompt,
    make_summarize_prompt,
    make_refine_strategy_prompt,
)

logger = logging.getLogger(__name__)


def _get_client_and_model(model: Optional[str] = None) -> Tuple[Optional[OpenAI], str]:
    """Build a per-request OpenAI client and resolve the model name.

    If `model` is None, falls back to the OLLAMA_MODEL env var.
    """
    api_base = os.environ.get("LOCAL_LLM_API_BASE", "http://localhost:11434/v1")
    api_key = os.environ.get("LOCAL_LLM_API_KEY", "not-needed")
    # Timeout: long enough to absorb cloud-model latency (typical 15–30s
    # for plan, 30–60s for code) plus a retry, but short enough that the
    # user doesn't wait indefinitely on a hung model.
    try:
        client = OpenAI(base_url=api_base, api_key=api_key, timeout=90, max_retries=0)
    except Exception as e:
        logger.error("Failed to create OpenAI client: %s", e)
        return None, ""
    model_name = model or os.environ.get("OLLAMA_MODEL", "kimi-k2.6:cloud")
    return client, model_name


def _chat(messages: List[Dict[str, str]], model: Optional[str] = None,
          max_tokens: int = 16384, temperature: float = 0.0,
          timeout: int = 180) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """Call the LLM with messages, return (content, finish_reason, error).

    finish_reason is one of: "stop" (clean), "length" (truncated — max_tokens
    hit), "content_filter", "tool_calls", or None if unknown. Useful for
    distinguishing a real "no code block" failure from a token-budget cut.
    """
    client, model_name = _get_client_and_model(model)
    if client is None:
        return None, None, "LLM client not initialized"
    try:
        response = client.chat.completions.create(
            model=model_name,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
            timeout=timeout,
        )
        choice = response.choices[0]
        content = choice.message.content
        finish_reason = getattr(choice, "finish_reason", None)

        # Some reasoning models (deepseek-v4-flash, kimi-k2.6 observed) put
        # their response in a "reasoning" field and leave content empty.
        # Fall back to reasoning when content is None or empty.
        if not content:
            reasoning = getattr(choice.message, "reasoning", None)
            if reasoning and reasoning.strip():
                logger.info(
                    "LLM returned empty content but has reasoning field — "
                    "using reasoning as content (model=%s, finish_reason=%s)",
                    model_name, finish_reason,
                )
                content = reasoning

        if content is None:
            logger.warning(
                "LLM returned None content: model=%s, finish_reason=%s, usage=%s",
                model_name, finish_reason, getattr(response, "usage", None),
            )
            return None, finish_reason, f"LLM returned no content (finish_reason={finish_reason})"
        content = content.strip()
        if not content:
            # Some cloud models finish with a 200 status but emit zero
            # content — usually a token-budget or moderation cutoff.
            # Surface this as an error rather than silently persisting
            # an empty plan.
            usage = getattr(response, "usage", None)
            logger.warning(
                "LLM returned empty content: model=%s, finish_reason=%s, "
                "prompt_tokens=%s, completion_tokens=%s, total_tokens=%s",
                model_name, finish_reason,
                getattr(usage, "prompt_tokens", None) if usage else None,
                getattr(usage, "completion_tokens", None) if usage else None,
                getattr(usage, "total_tokens", None) if usage else None,
            )
            return None, finish_reason, f"LLM returned empty content (finish_reason={finish_reason})"
        return content, finish_reason, None
    except Exception as e:
        return None, None, f"LLM call failed: {type(e).__name__}: {e}"


def _extract_code_block(text: str) -> Optional[str]:
    """Extract the first ```python ... ``` block from text. Returns None if no block."""
    m = re.search(r"```python\s*\n(.*?)```", text, re.DOTALL)
    if m:
        return textwrap.dedent(m.group(1).rstrip()) + "\n"
    # Fallback: any fenced block
    m = re.search(r"```\s*\n(.*?)```", text, re.DOTALL)
    if m:
        return textwrap.dedent(m.group(1).rstrip()) + "\n"
    return None


def _extract_diff_block(text: str) -> Optional[str]:
    """Extract the first ```diff ... ``` block from text."""
    m = re.search(r"```diff\s*\n(.*?)```", text, re.DOTALL)
    if m:
        return m.group(1)
    return None


# ── Public API ────────────────────────────────────────────────────────────

def generate_plan(user_prompt: str, model: Optional[str] = None) -> Tuple[Optional[str], Optional[str]]:
    """Generate a structured plan for a strategy idea. Returns (plan_text, error)."""
    messages = make_plan_prompt(user_prompt)
    content, _finish, err = _chat(messages, model=model, max_tokens=16384, temperature=0.2)
    if err:
        return None, err
    if content is None:
        return None, "LLM returned no content"

    # Check if the response is the model's chain-of-thought (reasoning) rather
    # than a structured plan. Reasoning output is full of meta-cognition like
    # "We need to...", "I'll propose...", "But the user didn't specify...".
    # If it looks like reasoning, make a second call to structure it.
    reasoning_markers = [
        "we need to", "i'll propose", "let's keep it simple",
        "but the user didn't", "alternatively,", "to be safe,",
        "however", "or we can say", "the instruction says",
    ]
    content_lower = content.lower()
    reasoning_score = sum(1 for m in reasoning_markers if m in content_lower)

    if reasoning_score >= 3:
        logger.info(
            "Plan response appears to be chain-of-thought (score=%d) — "
            "restructuring into structured plan", reasoning_score
        )
        # Second call: ask the model to format the reasoning as a structured plan
        structure_prompt = (
            "Below is a reasoning/analysis about a trading strategy. "
            "Extract the key decisions and format them as a STRUCTURED PLAN "
            "with these exact sections:\n\n"
            "## Signal\n"
            "## Entry scoring\n"
            "## Holding re-score\n"
            "## Exits\n"
            "## Parameters\n"
            "## Edge cases\n\n"
            "Be concrete and specific. Use exact percentages. "
            "Do NOT include meta-commentary, reasoning, or alternatives. "
            "Just the plan.\n\n"
            f"Reasoning to structure:\n\n{content}"
        )
        structured, _finish2, err2 = _chat(
            [{"role": "user", "content": structure_prompt}],
            model=model, max_tokens=16384, temperature=0.0,
        )
        if err2:
            logger.warning("Structuring call failed: %s — falling back to raw content", err2)
        elif structured and structured.strip():
            content = structured

    return content, err


def generate_code(plan: str, model: Optional[str] = None) -> Tuple[Optional[str], Optional[str]]:
    """Generate strategy code (4 filter functions + CONFIG) from a plan. Returns (code, error)."""
    messages = make_code_prompt(plan)
    # 8192 was empirically needed: the system prompt embeds the full
    # ENGINE_CONTRACT (~500 tokens) and the user prompt is the plan
    # (~500-1000 tokens). The model response — 4 functions + CONFIG +
    # importlib boilerplate — runs 2-4K tokens. With max_tokens=4096
    # the response gets cut off mid-code-block (finish_reason=length)
    # and the regex can't find a closing ``` fence, surfacing as a
    # confusing "no code block" error after a 30-40s wait.
    content, finish_reason, err = _chat(messages, model=model, max_tokens=32768, temperature=0.0, timeout=300)
    if err:
        return None, err
    code = _extract_code_block(content or "")

    # If the first call produced reasoning instead of code (common with
    # kimi-k2.6 and deepseek models that put chain-of-thought in the content
    # field), try extracting from the full response. These models tend to
    # output reasoning first, then a code block near the end.
    if code is None or len(code) < 1000:
        # Try to find the LAST code block in the response (models often put
        # the complete code at the end after reasoning through it)
        all_blocks = re.findall(r"```python\s*\n(.*?)```", content or "", re.DOTALL)
        if not all_blocks:
            all_blocks = re.findall(r"```\s*\n(.*?)```", content or "", re.DOTALL)
        if all_blocks:
            # Take the longest block (likely the complete code)
            all_blocks.sort(key=len, reverse=True)
            best = textwrap.dedent(all_blocks[0].rstrip()) + "\n"
            if len(best) > len(code or ""):
                code = best

    if code is None or len(code) < 1000:
            # Log the first 200 chars so the user (or backend logs) can see
            # what the LLM returned. Two common failure modes:
            #   1. finish_reason="length" — the model ran out of tokens before
            #      closing the ```python fence. Bumping max_tokens helps.
            #   2. The model returned prose without any fence.
            preview = (content or "")[:200].replace("\n", " ")
            if finish_reason == "length":
                detail = "response was truncated (finish_reason=length) — likely ran out of tokens before closing the ```python fence"
            else:
                detail = "response contained no ```python code block"
            return None, f"LLM {detail} (first 200 chars: {preview!r})"
    # Validate Python syntax
    import ast
    try:
        ast.parse(code)
    except SyntaxError as e:
        return None, f"Generated code has invalid syntax: {e}"
    return code, None


def generate_refine_diff(current_code: str, instruction: str, model: Optional[str] = None) -> Tuple[Optional[str], Optional[str]]:
    """Generate a unified diff that refines current_code per the instruction. Returns (diff, error)."""
    messages = make_refine_prompt(current_code, instruction)
    content, finish_reason, err = _chat(messages, model=model, max_tokens=16384, temperature=0.0)
    if err:
        return None, err
    diff = _extract_diff_block(content or "")
    if diff is None:
        if finish_reason == "length":
            detail = "response was truncated (finish_reason=length) before closing the ```diff fence"
        else:
            detail = "response contained no ```diff block"
        return None, f"LLM {detail} (content length={len(content or '')})"
    return diff, None


def summarize_batch(kpis_table: str, n_runs: int, model: Optional[str] = None) -> Tuple[Optional[str], Optional[str]]:
    """Generate a 3-paragraph analysis of N backtest runs. Returns (summary, error)."""
    messages = make_summarize_prompt(kpis_table, n_runs)
    content, _finish, err = _chat(messages, model=model, max_tokens=16384, temperature=0.2)
    return content, err


def refine_strategy(current_code: str, summary: str, worst_runs_table: str,
                    model: Optional[str] = None) -> Tuple[Optional[str], Optional[str]]:
    """Generate a diff that tweaks current_code to address worst-performing runs. Returns (diff, error)."""
    messages = make_refine_strategy_prompt(current_code, summary, worst_runs_table)
    content, finish_reason, err = _chat(messages, model=model, max_tokens=16384, temperature=0.2)
    if err:
        return None, err
    diff = _extract_diff_block(content or "")
    if diff is None:
        if finish_reason == "length":
            detail = "response was truncated (finish_reason=length) before closing the ```diff fence"
        else:
            detail = "response contained no ```diff block"
        return None, f"LLM {detail} (content length={len(content or '')})"
    return diff, None


def debug_code(code: str, error: str, model: Optional[str] = None) -> Tuple[Optional[str], Optional[str]]:
    """Given a failing strategy and its error, ask the LLM to produce a fixed version.

    Returns (fixed_code, error). The debugger outputs the COMPLETE fixed file
    (not a diff) to avoid fragile diff-application issues.
    """
    from app.services.strategy_lab_prompts import make_debug_prompt
    messages = make_debug_prompt(code, error)
    content, finish_reason, err = _chat(messages, model=model, max_tokens=16384, temperature=0.0)
    if err:
        return None, err
    fixed = _extract_code_block(content or "")
    if fixed is None:
        if finish_reason == "length":
            detail = "response was truncated (finish_reason=length) before closing the ```python fence"
        else:
            detail = "response contained no ```python code block"
        return None, f"LLM {detail} (content length={len(content or '')})"
    # Validate syntax
    import ast
    try:
        ast.parse(fixed)
    except SyntaxError as e:
        return None, f"Debugger produced invalid syntax: {e}"
    return fixed, None
