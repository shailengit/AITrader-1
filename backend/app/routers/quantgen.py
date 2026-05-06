"""
QuantGen Strategy Builder router for TradeCraft API.
Provides AI-powered strategy generation, execution, and optimization.
Ported from QuantGen FastAPI backend with database integration.
"""

import os
import logging
from typing import Dict, Any, List, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services.llm_engine import (
    generate_strategy_code,
    chat_about_code,
    is_llm_available,
    get_model_name
)
from app.services.executor import execute_strategy
from app.services.optimization_runner import run_optimization
from app.services.validators import (
    validate_api_request,
    BaseValidationError,
    SecurityValidationError,
    sanitize_filename,
    validate_file_path,
    StrategyValidator
)
from app.services.vbt_helpers import get_indicator_list
from app.services.code_verifier import CodeVerifier
from app.services.lessons_learned import LessonsLearnedStore
from app.db.database import engine
from sqlalchemy import text

logger = logging.getLogger(__name__)

router = APIRouter()


def _extract_error_details_from_result(result: dict, code: str) -> dict:
    """Extract structured error details from an executor result."""
    import re

    error_str = result.get("error", "Unknown error")
    traceback_str = result.get("traceback", "")
    stdout = result.get("output", "")

    # Extract line number from traceback
    line_match = re.search(r'File "<string>".*line (\d+)', traceback_str)
    if not line_match:
        line_match = re.search(r"line (\d+)", traceback_str)
    line_num = int(line_match.group(1)) if line_match else None
    line_content = None
    if line_num:
        lines = code.split("\n")
        if 0 <= line_num - 1 < len(lines):
            line_content = lines[line_num - 1]

    # Classify error type
    category = "execution"
    error_lower = error_str.lower()
    if "syntax" in error_lower or "invalid syntax" in error_lower:
        category = "syntax"
    elif "validation" in error_lower:
        category = "validation"
    elif "security" in error_lower or "forbidden" in error_lower:
        category = "security"
    elif "timeout" in error_lower:
        category = "timeout"

    # Try to classify with lessons store
    try:
        lessons_store = LessonsLearnedStore()
        error_type = lessons_store.classify_error(error_str) or "UNKNOWN"
        lesson = lessons_store.find_match(error_str)
        suggestion = (
            lesson["fix_description"]
            if lesson
            else _get_default_suggestion(error_type, error_str, line_content)
        )
        related_lesson = lesson["id"] if lesson else None
    except Exception:  # pylint: disable=broad-exception-caught
        error_type = "UNKNOWN"
        suggestion = _get_default_suggestion("UNKNOWN", error_str, line_content)
        related_lesson = None

    return {
        "type": error_type,
        "category": category,
        "message": error_str,
        "line": line_num,
        "line_content": line_content,
        "traceback": traceback_str,
        "stdout": stdout,
        "suggestion": suggestion,
        "related_lesson": related_lesson,
    }


def _get_default_suggestion(error_type: str, error_message: str, _line_content: Optional[str]) -> str:
    """Generate a default suggestion based on error type."""
    suggestions = {
        "VBT_COMPARISON_OPERATOR": (
            "Replace comparison operators (>, <, &, |) with VBT methods: "
            "ma_above(), ma_below(), rsi_below(), vbt.And(), vbt.Or()"
        ),
        "MISSING_PF_OBJECT": (
            "Ensure code ends with: pf = vbt.Portfolio.from_signals(...)"
        ),
        "SYNTAX_ERROR": (
            "Check for missing parentheses, quotes, or indentation issues."
        ),
        "DATA_LOADING": (
            "Use DataService.get_ohlcv_data(ticker, start, end) to load data."
        ),
        "PORTFOLIO_EMPTY": (
            "Portfolio has no trades. Check that entries/exits have True values."
        ),
        "MISSING_PARAMETERS": (
            "Add a '# Parameters' section at the top with tunable numeric variables."
        ),
        "IMPORT_ERROR": (
            "Only standard libraries + pandas/numpy/vectorbt are allowed."
        ),
    }
    return suggestions.get(
        error_type,
        f"Review the error and fix the code. Error: {error_message[:100]}",
    )


class GenerateRequest(BaseModel):
    """Request model for strategy generation."""
    prompt: str
    tickers: List[str]
    start_date: str
    end_date: str


class RunRequest(BaseModel):
    """Request model for strategy execution."""
    code: str
    use_database: bool = True
    tickers: Optional[List[str]] = None


class OptimizeRequest(BaseModel):
    """Request model for strategy optimization."""
    code: str
    strategy_params: Dict[str, Any]
    config: Dict[str, Any]
    tickers: Optional[List[str]] = None


class TrueWFORequest(BaseModel):
    """Request model for True Walk-Forward Optimization."""
    code: str
    strategy_params: Dict[str, Any]
    config: Dict[str, Any]
    tickers: Optional[List[str]] = None


class ChatRequest(BaseModel):
    """Request model for code chat."""
    code: str
    messages: List[Dict[str, str]]


class StrategyModel(BaseModel):
    """Model for saving/loading strategies."""
    name: str
    code: str


@router.get("/health")
async def quantgen_health():
    """Health check for QuantGen module."""
    return {
        "status": "healthy",
        "module": "quantgen",
        "llm_model": get_model_name() if is_llm_available() else None,
        "features": {
            "strategy_generation": is_llm_available(),
            "backtesting": True,
            "optimization": True,
            "database_integration": True
        }
    }


@router.post("/generate")
async def generate_strategy(request: GenerateRequest):
    """
    Generate trading strategy code using AI.
    Uses database (PostgreSQL) for historical data instead of yfinance.
    """
    try:
        logger.info("Generating strategy for tickers: %s", request.tickers)

        if not is_llm_available():
            return {
                "success": False,
                "error": {
                    "type": "ConfigurationError",
                    "message": "Local LLM not available. Ensure the model server is running on port 11434 with kimi-k2.5:cloud model."
                },
                "data": None
            }

        # Validate input
        try:
            validated = validate_api_request('generate', {
                'prompt': request.prompt,
                'tickers': request.tickers,
                'start_date': request.start_date,
                'end_date': request.end_date
            })
        except BaseValidationError as e:
            return {
                "success": False,
                "error": {
                    "type": "ValidationError",
                    "message": e.message,
                    "field": e.field
                },
                "data": None
            }

        # Generate code
        code, error_msg = generate_strategy_code(
            validated.prompt,
            validated.tickers,
            validated.start_date,
            validated.end_date
        )

        if code is None:
            logger.error("Strategy generation failed: %s", error_msg)
            return {
                "success": False,
                "error": {
                    "type": "GenerationError",
                    "message": f"LLM Generation failed: {error_msg}",
                    "details": "Check backend logs and API Key configuration"
                },
                "data": {
                    "code": f"# Generation failed.\n# Error: {error_msg}",
                    "output": ""
                }
            }

        # Verify and auto-fix the generated code using CodeVerifier
        verifier = CodeVerifier()
        verification = verifier.verify_and_fix(
            code,
            tickers=request.tickers,
            max_attempts=3,
            record_lessons=True
        )

        if verification.success:
            msg = "Strategy generated and validated successfully"
            if verification.fix_attempts > 0:
                msg = f"Strategy generated and auto-fixed after {verification.fix_attempts} attempt(s)"
            return {
                "success": True,
                "data": {
                    "code": verification.code,
                    "output": verification.output,
                    "fix_attempts": verification.fix_attempts,
                    "lessons_applied": verification.lessons_applied,
                    "execution_time": verification.execution_time,
                },
                "message": msg
            }

        # Failed after all attempts - return structured error details
        error_details = None
        if verification.error_details:
            error_details = {
                "type": verification.error_details.type,
                "category": verification.error_details.category,
                "message": verification.error_details.message,
                "line": verification.error_details.line,
                "line_content": verification.error_details.line_content,
                "traceback": verification.error_details.traceback,
                "stdout": verification.error_details.stdout,
                "suggestion": verification.error_details.suggestion,
                "related_lesson": verification.error_details.related_lesson,
            }

        logger.error(
            "Strategy generation failed after %d attempts. Error: %s",
            verification.fix_attempts,
            verification.error_details.message if verification.error_details else "Unknown"
        )
        return {
            "success": False,
            "error": {
                "type": "GenerationError",
                "message": f"Failed after {verification.fix_attempts} attempts",
                "details": error_details,
            },
            "data": {
                "code": verification.code,
                "output": verification.output,
                "fix_attempts": verification.fix_attempts,
            }
        }

    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.error("Strategy generation failed: %s", e)
        return {
            "success": False,
            "error": str(e)
        }


@router.post("/run")
async def run_strategy_endpoint(request: RunRequest):
    """
    Execute a trading strategy.
    If use_database is True, fetches data from PostgreSQL instead of yfinance.
    """
    try:
        logger.info("Running strategy (length: %d chars)", len(request.code))

        # Validate input
        try:
            validated = validate_api_request('run', {'code': request.code})
        except BaseValidationError as e:
            return {
                "success": False,
                "error": {
                    "type": "ValidationError",
                    "message": e.message,
                    "field": e.field
                },
                "data": None
            }

        # Execute strategy with enhanced error extraction
        result = execute_strategy(validated.code, request.tickers)

        if result["success"]:
            logger.info("Strategy executed successfully")
            return {
                "success": True,
                "data": {
                    "output": result.get("output", ""),
                    "stats": result.get("stats", {}),
                    "equity": result.get("equity", []),
                    "ohlcv": result.get("ohlcv", []),
                    "drawdown": result.get("drawdown", {}),
                    "benchmark_drawdown": result.get("benchmark_drawdown", {}),
                    "trades": result.get("trades", []),
                    "indicators": result.get("indicators", [])
                },
                "message": "Strategy executed successfully"
            }
        else:
            error_str = result.get("error", "Unknown error")
            logger.error("Strategy execution failed: %s", error_str)

            # Extract structured error details
            error_details = _extract_error_details_from_result(result, validated.code)

            return {
                "success": False,
                "error": {
                    "type": "ExecutionError",
                    "message": "Strategy execution failed",
                    "details": error_details
                },
                "data": {
                    "output": result.get("output", "")
                }
            }

    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.error("Strategy execution failed: %s", e)
        return {
            "success": False,
            "error": str(e)
        }


@router.post("/optimize")
async def optimize_strategy_endpoint(request: OptimizeRequest):
    """
    Run parameter optimization on a strategy.
    Uses walk-forward optimization by default.
    """
    try:
        logger.info("Starting optimization with params: %s", request.strategy_params)

        # Validate input
        try:
            validated = validate_api_request('optimize', {
                'code': request.code,
                'strategy_params': request.strategy_params,
                'config': request.config
            })
        except BaseValidationError as e:
            return {
                "success": False,
                "error": {
                    "type": "ValidationError",
                    "message": e.message,
                    "field": e.field
                },
                "data": None
            }

        # Run optimization
        result = run_optimization(
            validated.code,
            validated.strategy_params,
            validated.config,
            request.tickers
        )

        # Check if there was an error
        if result.get("output", "").startswith("Optimization Error") or result.get("output", "").startswith("\nOptimization Error"):
            logger.error("Optimization failed: %s", result.get("output", ""))
            return {
                "success": False,
                "error": {
                    "type": "OptimizationError",
                    "message": "Optimization failed",
                    "details": result.get("output", "")
                },
                "data": result
            }

        logger.info("Optimization completed successfully")
        return {
            "success": True,
            "data": result,
            "message": "Optimization completed successfully"
        }

    except Exception as e:  # pylint: disable=broad-exception-caught
        import traceback
        logger.error("Optimization failed: %s", e)
        logger.error(traceback.format_exc())
        return {
            "success": False,
            "error": str(e),
            "details": traceback.format_exc()
        }


@router.post("/true-wfo")
async def run_true_wfo(request: TrueWFORequest):
    """
    DEPRECATED: Use /optimize endpoint with mode='true_wfo' instead.

    This endpoint is maintained for backward compatibility but routes
    to the same code as /optimize with mode='true_wfo'.

    For each rolling window:
    1. Optimize parameters on training data
    2. Get signal from training window's last day for the NEXT day
    3. Trade only on that next day (first day of test window)
    4. Maintain portfolio state across windows
    """
    logger.warning("DEPRECATED: /true-wfo endpoint is deprecated. Use /optimize with mode='true_wfo' instead.")

    # Convert TrueWFORequest to OptimizeRequest format and call optimize endpoint
    opt_request = OptimizeRequest(
        code=request.code,
        strategy_params=request.strategy_params,
        config={**request.config, "mode": "true_wfo"},
        tickers=request.tickers
    )

    # Route to optimize endpoint
    return await optimize_strategy_endpoint(opt_request)


@router.post("/chat")
async def chat_about_code_endpoint(request: ChatRequest):
    """
    Chat about strategy code with AI.
    Maintains conversation context for iterative refinement.
    """
    try:
        logger.info("Chat request (code length: %d chars, messages: %d)", len(request.code), len(request.messages))

        if not is_llm_available():
            return {
                "success": False,
                "error": {
                    "type": "ConfigurationError",
                    "message": "Local LLM not available. Ensure the model server is running on port 11434 with kimi-k2.5:cloud model."
                },
                "data": None
            }

        # Call the chat function
        response, error_msg = chat_about_code(
            code=request.code,
            messages=request.messages
        )

        if error_msg:
            logger.error("Chat error: %s", error_msg)
            return {
                "success": False,
                "error": {
                    "type": "ChatError",
                    "message": error_msg
                },
                "data": {
                    "response": None
                }
            }

        logger.info("Chat response generated successfully")
        return {
            "success": True,
            "data": {
                "response": response
            }
        }

    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.error("Chat failed: %s", e)
        return {
            "success": False,
            "error": str(e)
        }


@router.get("/strategies")
async def list_strategies():
    """List all saved strategies."""
    try:
        import glob

        strategies_dir = "../strategies"
        if not os.path.exists(strategies_dir):
            os.makedirs(strategies_dir)

        files = glob.glob(os.path.join(strategies_dir, "*.py"))
        strategy_names = [os.path.basename(f) for f in files]

        return {
            "success": True,
            "data": {
                "strategies": strategy_names,
                "count": len(strategy_names)
            },
            "message": f"Found {len(strategy_names)} strategies"
        }

    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.error("Error listing strategies: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/strategies")
async def save_strategy(strategy: StrategyModel):
    """Save a strategy to file."""
    try:
        # Validate the strategy code before saving
        validation = StrategyValidator.validate_strategy_code(strategy.code)
        if not validation["valid"]:
            return {
                "success": False,
                "error": {
                    "type": "ValidationError",
                    "message": "Strategy code validation failed",
                    "details": validation["errors"]
                }
            }

        # Sanitize filename
        safe_name = sanitize_filename(strategy.name)

        strategies_dir = "../strategies"
        if not os.path.exists(strategies_dir):
            os.makedirs(strategies_dir)

        # Additional path validation
        path = os.path.join(strategies_dir, safe_name)
        if not validate_file_path(path, strategies_dir):
            raise SecurityValidationError("Invalid file path")

        # Save with backup if exists
        import shutil
        backup_path = None
        if os.path.exists(path):
            backup_path = f"{path}.backup"
            shutil.copy2(path, backup_path)
            logger.info("Created backup: %s", backup_path)

        with open(path, "w", encoding="utf-8") as f:
            f.write(strategy.code)

        logger.info("Strategy saved: %s", safe_name)

        return {
            "success": True,
            "data": {
                "path": path,
                "filename": safe_name,
                "backup_created": backup_path is not None
            },
            "message": f"Strategy '{safe_name}' saved successfully"
        }

    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.error("Error saving strategy: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/strategies/{name}")
async def get_strategy(name: str):
    """Get a saved strategy by name."""
    try:
        safe_name = sanitize_filename(name)
        strategies_dir = "../strategies"
        path = os.path.join(strategies_dir, safe_name)

        # Path validation
        if not validate_file_path(path, strategies_dir):
            raise SecurityValidationError("Invalid file path")

        if not os.path.exists(path):
            raise HTTPException(status_code=404, detail="Strategy not found")

        with open(path, "r", encoding="utf-8") as f:
            content = f.read()

        logger.info("Strategy loaded: %s", safe_name)

        return {
            "success": True,
            "data": {
                "name": name,
                "code": content,
                "filename": safe_name,
                "size": len(content)
            },
            "message": f"Strategy '{name}' loaded successfully"
        }

    except HTTPException:
        raise
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.error("Error loading strategy: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.delete("/strategies/{name}")
async def delete_strategy(name: str):
    """Delete a saved strategy."""
    try:
        safe_name = sanitize_filename(name)
        strategies_dir = "../strategies"
        path = os.path.join(strategies_dir, safe_name)

        # Path validation
        if not validate_file_path(path, strategies_dir):
            raise SecurityValidationError("Invalid file path")

        if not os.path.exists(path):
            raise HTTPException(status_code=404, detail="Strategy not found")

        # Create backup before deletion
        import shutil
        backup_path = f"{path}.deleted"
        shutil.copy2(path, backup_path)
        os.remove(path)

        logger.info("Strategy deleted: %s (backup: %s)", safe_name, backup_path)

        return {
            "success": True,
            "data": {
                "filename": safe_name,
                "backup_path": backup_path
            },
            "message": f"Strategy '{name}' deleted successfully"
        }

    except HTTPException:
        raise
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.error("Error deleting strategy: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/indicators")
async def list_indicators():
    """List available technical indicators."""
    try:
        indicators = get_indicator_list()
        return {
            "success": True,
            "data": {
                "indicators": indicators,
                "count": len(indicators)
            },
            "message": f"Found {len(indicators)} indicators"
        }
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.error("Error listing indicators: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/latest-date")
async def get_latest_date():
    """Return the latest available trading date in the database."""
    try:
        # Query aapl table as a reliable S&P 1500 constituent
        query = text('SELECT MAX("Date") as latest_date FROM aapl')
        with engine.connect() as conn:
            result = conn.execute(query).fetchone()

        if result and result[0]:
            latest = str(result[0])
            # Ensure YYYY-MM-DD format
            if len(latest) > 10:
                latest = latest[:10]
            return {
                "success": True,
                "data": {"latest_date": latest},
                "message": f"Latest available date: {latest}"
            }
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.warning("Could not fetch latest date from DB: %s", e)

    # Fallback to today if DB is unavailable
    from datetime import datetime
    today = datetime.now().strftime("%Y-%m-%d")
    return {
        "success": True,
        "data": {"latest_date": today},
        "message": f"Database unavailable, fallback to today: {today}"
    }
