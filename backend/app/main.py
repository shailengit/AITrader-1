"""
TradeCraft - Unified Trading Application Backend
FastAPI application combining Sector Rotation, Stock Screener, and QuantGen.
"""

import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.db import database

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
    title="TradeCraft API",
    description="Unified Trading Application - Sector Rotation, AI Screener, and QuantGen",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS configuration
ALLOWED_ORIGINS = [
    "http://localhost:3000",  # React dev server
    "http://localhost:5173",  # Vite dev server
    "http://localhost:5174",  # Vite dev server (alternate)
    "http://127.0.0.1:3000",
    "http://127.0.0.1:5173",
    "http://127.0.0.1:5174",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
    max_age=86400,
)


# Security headers middleware
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


@app.on_event("startup")
async def startup_event():
    """Check database connection on startup."""
    connected = database.test_connection()
    database.set_db_connected(connected)
    if connected:
        logger.info("Database connected: %s:%s/%s", database.DB_HOST, database.DB_PORT, database.DB_NAME)
    else:
        logger.warning("Database connection failed - some features will use fallback data")


# Import routers
from app.routers import sectors, screener, quantgen, health

# Include routers
app.include_router(health.router, prefix="/api", tags=["Health"])
app.include_router(sectors.router, prefix="/api", tags=["Sector Rotation"])
app.include_router(screener.router, prefix="/api/screener", tags=["AI Screener"])
app.include_router(quantgen.router, prefix="/api", tags=["QuantGen"])


# Root endpoint
@app.get("/")
async def root():
    """Root endpoint with API information."""
    return {
        "name": "TradeCraft API",
        "version": "1.0.0",
        "description": "Unified Trading Application",
        "endpoints": {
            "health": "/api/health",
            "sectors": "/api/sectors",
            "stocks": "/api/stocks/{sector}",
            "screener": "/api/screener/scan",
            "generate": "/api/generate",
            "run": "/api/run",
            "optimize": "/api/optimize",
            "strategies": "/api/strategies",
        },
        "database": {
            "connected": database.db_connected,
            "host": database.DB_HOST,
            "port": database.DB_PORT,
            "name": database.DB_NAME
        }
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )