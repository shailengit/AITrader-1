import os
import sys

# Ensure backend is on path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import pytest
from fastapi.testclient import TestClient

# Set test environment variables before importing app
os.environ["DB_PASSWORD"] = "test_password"
os.environ["JWT_SECRET_KEY"] = "test-jwt-secret-key-for-testing-only"
os.environ["CORS_ORIGINS"] = "http://localhost:3000"

from app.main import app


@pytest.fixture
def client():
    """FastAPI test client."""
    return TestClient(app)


@pytest.fixture
def mock_db(monkeypatch):
    """Mock database connection for tests."""
    from app.db import database
    monkeypatch.setattr(database, "db_connected", True)
    return database
