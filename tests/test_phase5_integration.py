"""Tests for Phase 5 integration endpoints.

These tests verify that the "future-facing code" items from Phase 5
of unused_code_report.md are properly integrated into the API.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


def _make_app() -> TestClient:
    """Create a test FastAPI app with the routes."""
    from api.routes import api_router, app_router
    
    app = FastAPI()
    app.include_router(app_router)
    app.include_router(api_router, prefix="/api/v1")
    return TestClient(app)


class TestDolphinConfigurationEndpoints:
    """Tests for Dolphin OCR configuration endpoints."""

    def test_get_dolphin_configuration_default(self):
        """Test GET /config/dolphin returns default configuration."""
        client = _make_app()
        response = client.get("/api/v1/config/dolphin")
        
        assert response.status_code == 200
        data = response.json()
        
        # Should return default modal endpoint
        assert data["endpoint_type"] == "modal"
        assert "modal_endpoint" in data
        assert "local_endpoint" in data
        assert "active_endpoint" in data
        assert data["available_endpoint_types"] == ["modal", "local"]

    def test_update_dolphin_configuration_valid(self):
        """Test POST /config/dolphin updates configuration."""
        client = _make_app()
        response = client.post(
            "/api/v1/config/dolphin",
            json={"DOLPHIN_ENDPOINT_TYPE": "local"}
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["success"] is True
        assert "Updated configuration" in data["message"]

    def test_update_dolphin_configuration_invalid(self):
        """Test POST /config/dolphin with invalid keys."""
        client = _make_app()
        response = client.post(
            "/api/v1/config/dolphin",
            json={"INVALID_KEY": "value"}
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["success"] is False
        assert "No valid configuration keys" in data["message"]


class TestPhilosophyTerminologyEndpoints:
    """Tests for philosophy terminology management endpoints."""

    def test_get_terminology_map(self):
        """Test GET /philosophy/terminology returns terminology map."""
        client = _make_app()
        response = client.get("/api/v1/philosophy/terminology")
        
        assert response.status_code == 200
        data = response.json()
        
        assert "terminology_map" in data
        assert "term_count" in data
        assert isinstance(data["terminology_map"], dict)
        assert isinstance(data["term_count"], int)

    def test_update_terminology_map(self):
        """Test POST /philosophy/terminology updates terminology."""
        client = _make_app()
        test_terms = {
            "Dasein": "being-there",
            "Vorhandenheit": "presence-at-hand"
        }
        
        response = client.post(
            "/api/v1/philosophy/terminology",
            json={"terminology": test_terms}
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["success"] is True
        assert "Updated terminology map" in data["message"]

    def test_update_terminology_map_invalid(self):
        """Test POST /philosophy/terminology with invalid data."""
        client = _make_app()
        
        # Send invalid data (not a dict)
        response = client.post(
            "/api/v1/philosophy/terminology",
            json={"terminology": "not-a-dict"}
        )
        
        assert response.status_code == 400


class TestPhilosophyConfigEndpoints:
    """Tests for philosophy-enhanced translation config endpoints."""

    def test_get_philosophy_config(self):
        """Test GET /philosophy/config returns configuration."""
        client = _make_app()
        response = client.get("/api/v1/philosophy/config")
        
        assert response.status_code == 200
        data = response.json()
        
        assert "preserve_neologisms_by_default" in data
        assert "neologism_confidence_threshold" in data
        assert "chunk_size" in data
        assert "available_providers" in data

    def test_update_philosophy_config(self):
        """Test POST /philosophy/config updates configuration."""
        client = _make_app()
        
        response = client.post(
            "/api/v1/philosophy/config",
            json={
                "preserve_neologisms_by_default": False,
                "neologism_confidence_threshold": 0.7
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["success"] is True


class TestNeologismMergeEndpoint:
    """Tests for neologism analysis merge endpoint."""

    def test_merge_analyses_empty(self):
        """Test POST /philosophy/merge-analyses with empty list."""
        client = _make_app()
        
        response = client.post(
            "/api/v1/philosophy/merge-analyses",
            json={"analyses": []}
        )
        
        assert response.status_code == 400

    def test_merge_analyses_invalid_type(self):
        """Test POST /philosophy/merge-analyses with invalid type."""
        client = _make_app()
        
        response = client.post(
            "/api/v1/philosophy/merge-analyses",
            json={"analyses": "not-a-list"}
        )
        
        assert response.status_code == 400


class TestPDFQualityValidationEndpoint:
    """Tests for PDF quality validation endpoint."""

    def test_validate_quality_missing_original(self):
        """Test POST /pdf/validate-quality missing original_pdf."""
        client = _make_app()
        
        response = client.post(
            "/api/v1/pdf/validate-quality",
            json={"reconstructed_pdf": "/path/to/reconstructed.pdf"}
        )
        
        assert response.status_code == 400
        assert "original_pdf" in response.json()["detail"]

    def test_validate_quality_missing_reconstructed(self):
        """Test POST /pdf/validate-quality missing reconstructed_pdf."""
        client = _make_app()
        
        response = client.post(
            "/api/v1/pdf/validate-quality",
            json={"original_pdf": "/path/to/original.pdf"}
        )
        
        assert response.status_code == 400
        assert "reconstructed_pdf" in response.json()["detail"]


class TestConfidenceScorerEndpoints:
    """Tests for confidence scorer endpoints."""

    def test_get_confidence_scorer_info(self):
        """Test GET /confidence/scorer-info returns info."""
        client = _make_app()
        response = client.get("/api/v1/confidence/scorer-info")
        
        assert response.status_code == 200
        data = response.json()
        
        assert "confidence_threshold" in data
        assert "philosophical_indicators_count" in data
        assert "pattern_types" in data

    def test_update_confidence_scorer_config(self):
        """Test POST /confidence/scorer-config updates config."""
        client = _make_app()
        
        response = client.post(
            "/api/v1/confidence/scorer-config",
            json={"confidence_threshold": 0.6}
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["success"] is True

    def test_calculate_confidence_missing_term(self):
        """Test POST /confidence/calculate missing term."""
        client = _make_app()
        
        response = client.post(
            "/api/v1/confidence/calculate",
            json={"term": ""}
        )
        
        assert response.status_code == 400

    def test_calculate_confidence_valid_term(self):
        """Test POST /confidence/calculate with valid term."""
        client = _make_app()
        
        response = client.post(
            "/api/v1/confidence/calculate",
            json={"term": "philosophy"}
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["term"] == "philosophy"
        assert "final_confidence" in data
        assert "confidence_factors" in data
        assert "confidence_breakdown" in data
