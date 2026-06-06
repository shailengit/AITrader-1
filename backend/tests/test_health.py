"""Tests for health check endpoints."""


def test_health_check(client, mock_db):
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["version"] == "1.0.0"
    assert "timestamp" in data
    assert data["services"]["api"] == "running"
    assert data["services"]["database"]["connected"] is True


def test_db_status(client, mock_db):
    response = client.get("/api/db-status")
    assert response.status_code == 200
    data = response.json()
    assert data["connected"] is True
    assert data["status"] == "connected"


def test_root_endpoint(client):
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "TradeCraft API"
    assert "endpoints" in data
