"""
Custom exceptions for TradeCraft API.
Provides structured error responses for different failure modes.
"""

from typing import Optional, Dict, Any


class TradeCraftError(Exception):
    """Base exception for all TradeCraft errors."""
    
    def __init__(self, message: str, code: str = "INTERNAL_ERROR", details: Optional[Dict[str, Any]] = None):
        self.message = message
        self.code = code
        self.details = details or {}
        super().__init__(self.message)


class DatabaseError(TradeCraftError):
    """Raised when database operations fail."""
    
    def __init__(self, message: str = "Database operation failed", details: Optional[Dict[str, Any]] = None):
        super().__init__(message, code="DATABASE_ERROR", details=details)


class SecurityError(TradeCraftError):
    """Raised when security validation fails."""
    
    def __init__(self, message: str = "Security validation failed", details: Optional[Dict[str, Any]] = None):
        super().__init__(message, code="SECURITY_ERROR", details=details)


class ValidationError(TradeCraftError):
    """Raised when input validation fails."""
    
    def __init__(self, message: str = "Validation failed", details: Optional[Dict[str, Any]] = None):
        super().__init__(message, code="VALIDATION_ERROR", details=details)


class LLMError(TradeCraftError):
    """Raised when LLM operations fail."""
    
    def __init__(self, message: str = "LLM operation failed", details: Optional[Dict[str, Any]] = None):
        super().__init__(message, code="LLM_ERROR", details=details)


class StrategyExecutionError(TradeCraftError):
    """Raised when strategy execution fails."""
    
    def __init__(self, message: str = "Strategy execution failed", details: Optional[Dict[str, Any]] = None):
        super().__init__(message, code="STRATEGY_EXECUTION_ERROR", details=details)


class OptimizationError(TradeCraftError):
    """Raised when optimization fails."""
    
    def __init__(self, message: str = "Optimization failed", details: Optional[Dict[str, Any]] = None):
        super().__init__(message, code="OPTIMIZATION_ERROR", details=details)


class DataNotFoundError(TradeCraftError):
    """Raised when requested data is not found."""
    
    def __init__(self, message: str = "Data not found", details: Optional[Dict[str, Any]] = None):
        super().__init__(message, code="DATA_NOT_FOUND", details=details)
