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
    try:
        client = OpenAI(base_url=api_base, api_key=api_key, timeout=180, max_retries=1)
    except Exception as e:
        logger.error("Failed to create OpenAI client: %s", e)
        return None, ""
    model_name = model or os.environ.get("OLLAMA_MODEL", "kimi-k2.6:cloud")
    return client, model_name


def _chat(messages: List[Dict[str, str]], model: Optional[str] = None,
          max_tokens: int = 2048, temperature: float = 0.0) -> Tuple[Optional[str], Optional[str]]:
    """Call the LLM with messages, return (content, error)."""
    client, model_name = _get_client_and_model(model)
    if client is None:
        return None, "LLM client not initialized"
    try:
        response = client.chat.completions.create(
            model=model_name,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
            timeout=180,
        )
        content = response.choices[0].message.content
        if content is None:
            return None, "LLM returned empty response"
        return content, None
    except Exception as e:
        return None, f"LLM call failed: {type(e).__name__}: {e}"


def _extract_code_block(text: str) -> Optional[str]:
    """Extract the first ```python ... ``` block from text. Returns None if no block."""
    m = re.search(r"```python\s*\n(.*?)```", text, re.DOTALL)
    if m:
        return m.group(1).rstrip() + "\n"
    # Fallback: any fenced block
    m = re.search(r"```\s*\n(.*?)```", text, re.DOTALL)
    if m:
        return m.group(1).rstrip() + "\n"
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
    return _chat(messages, model=model, max_tokens=1024, temperature=0.2)


def generate_code(plan: str, model: Optional[str] = None) -> Tuple[Optional[str], Optional[str]]:
    """Generate strategy code (4 filter functions + CONFIG) from a plan. Returns (code, error)."""
    messages = make_code_prompt(plan)
    content, err = _chat(messages, model=model, max_tokens=4096, temperature=0.0)
    if err:
        return None, err
    code = _extract_code_block(content or "")
    if code is None:
        return None, "LLM response contained no code block"
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
    content, err = _chat(messages, model=model, max_tokens=2048, temperature=0.0)
    if err:
        return None, err
    diff = _extract_diff_block(content or "")
    if diff is None:
        return None, "LLM response contained no diff block"
    return diff, None


def summarize_batch(kpis_table: str, n_runs: int, model: Optional[str] = None) -> Tuple[Optional[str], Optional[str]]:
    """Generate a 3-paragraph analysis of N backtest runs. Returns (summary, error)."""
    messages = make_summarize_prompt(kpis_table, n_runs)
    return _chat(messages, model=model, max_tokens=1024, temperature=0.3)


def refine_strategy(current_code: str, summary: str, worst_runs_table: str,
                    model: Optional[str] = None) -> Tuple[Optional[str], Optional[str]]:
    """Generate a diff that tweaks current_code to address worst-performing runs. Returns (diff, error)."""
    messages = make_refine_strategy_prompt(current_code, summary, worst_runs_table)
    content, err = _chat(messages, model=model, max_tokens=2048, temperature=0.2)
    if err:
        return None, err
    diff = _extract_diff_block(content or "")
    if diff is None:
        return None, "LLM response contained no diff block"
    return diff, None
