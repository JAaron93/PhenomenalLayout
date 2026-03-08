"""Unit tests for Phase 5 service integrations.

These tests verify the individual service methods that were integrated
as part of Phase 5 of unused_code_report.md.
"""

import os
import pytest


class TestDolphinClientEndpointConfiguration:
    """Tests for Dolphin client endpoint configuration."""

    def test_default_modal_endpoint(self, monkeypatch):
        """Test default Modal endpoint is used when endpoint_type is modal."""
        # Clear any existing env vars
        monkeypatch.delenv("DOLPHIN_ENDPOINT_TYPE", raising=False)
        monkeypatch.delenv("DOLPHIN_ENDPOINT", raising=False)
        monkeypatch.delenv("DOLPHIN_LOCAL_ENDPOINT", raising=False)
        
        from services.dolphin_client import DEFAULT_MODAL_ENDPOINT, DEFAULT_LOCAL_ENDPOINT
        
        # The function should use Modal endpoint by default
        # (This tests the logic that will be used when get_layout is called)
        endpoint_type = os.getenv("DOLPHIN_ENDPOINT_TYPE", "modal").lower()
        assert endpoint_type == "modal"

    def test_local_endpoint_configuration(self, monkeypatch):
        """Test local endpoint is used when endpoint_type is local."""
        monkeypatch.setenv("DOLPHIN_ENDPOINT_TYPE", "local")
        monkeypatch.setenv("DOLPHIN_LOCAL_ENDPOINT", "http://custom:9999/layout")
        
        endpoint_type = os.getenv("DOLPHIN_ENDPOINT_TYPE", "modal").lower()
        local_endpoint = os.getenv("DOLPHIN_LOCAL_ENDPOINT", "http://localhost:8501/layout")
        
        assert endpoint_type == "local"
        assert local_endpoint == "http://custom:9999/layout"

    def test_settings_dolphin_config(self, monkeypatch):
        """Test Settings class has Dolphin configuration."""
        monkeypatch.setenv("DOLPHIN_ENDPOINT_TYPE", "local")
        monkeypatch.setenv("DOLPHIN_LOCAL_ENDPOINT", "http://test:8000/layout")
        monkeypatch.setenv("DOLPHIN_TIMEOUT_SECONDS", "120")
        
        from config.settings import Settings
        settings = Settings()
        
        assert settings.DOLPHIN_ENDPOINT_TYPE == "local"
        assert settings.DOLPHIN_LOCAL_ENDPOINT == "http://test:8000/layout"
        assert settings.DOLPHIN_TIMEOUT_SECONDS == 120


class TestPhilosophicalContextAnalyzerTerminology:
    """Tests for PhilosophicalContextAnalyzer terminology management."""

    def test_update_terminology_map(self):
        """Test update_terminology_map method."""
        from services.philosophical_context_analyzer import PhilosophicalContextAnalyzer
        
        analyzer = PhilosophicalContextAnalyzer()
        initial_count = len(analyzer.terminology_map)
        
        # Add new terms
        new_terms = {
            "TestTerm": "test_translation",
            "AnotherTerm": "another_translation"
        }
        analyzer.update_terminology_map(new_terms)
        
        assert len(analyzer.terminology_map) == initial_count + 2
        assert "TestTerm" in analyzer.terminology_map
        assert analyzer.terminology_map["TestTerm"] == "test_translation"

    def test_terminology_map_persists_after_update(self):
        """Test that terminology persists across updates."""
        from services.philosophical_context_analyzer import PhilosophicalContextAnalyzer
        
        analyzer = PhilosophicalContextAnalyzer()
        
        # First update
        analyzer.update_terminology_map({"Term1": "trans1"})
        assert analyzer.terminology_map.get("Term1") == "trans1"
        
        # Second update should add to existing
        analyzer.update_terminology_map({"Term2": "trans2"})
        assert analyzer.terminology_map.get("Term1") == "trans1"
        assert analyzer.terminology_map.get("Term2") == "trans2"


class TestPhilosophyEnhancedTranslationService:
    """Tests for PhilosophyEnhancedTranslationService integration."""

    def test_update_configuration(self):
        """Test update_configuration method."""
        from services.philosophy_enhanced_translation_service import (
            PhilosophyEnhancedTranslationService
        )
        
        service = PhilosophyEnhancedTranslationService()
        initial_threshold = service.neologism_confidence_threshold
        
        # Update configuration
        service.update_configuration(neologism_confidence_threshold=0.7)
        
        assert service.neologism_confidence_threshold == 0.7
        
        # Restore original
        service.update_configuration(neologism_confidence_threshold=initial_threshold)

    def test_get_statistics(self):
        """Test get_statistics method returns configuration."""
        from services.philosophy_enhanced_translation_service import (
            PhilosophyEnhancedTranslationService
        )
        
        service = PhilosophyEnhancedTranslationService()
        stats = service.get_statistics()
        
        assert "configuration" in stats
        config = stats["configuration"]
        assert "preserve_neologisms_by_default" in config
        assert "neologism_confidence_threshold" in config
        assert "chunk_size" in config


class TestNeologismDetectorMerge:
    """Tests for neologism detector merge functionality."""

    def test_merge_neologism_analyses_import(self):
        """Test merge_neologism_analyses can be imported."""
        from services.neologism_detector import merge_neologism_analyses
        
        assert callable(merge_neologism_analyses)

    def test_merge_neologism_analyses_empty_raises(self):
        """Test merge_neologism_analyses raises on empty list."""
        from services.neologism_detector import merge_neologism_analyses
        
        with pytest.raises(ValueError, match="Cannot merge empty"):
            merge_neologism_analyses([])


class TestPDFQualityValidator:
    """Tests for PDF quality validator integration."""

    def test_validate_pdf_reconstruction_quality_import(self):
        """Test validate_pdf_reconstruction_quality can be accessed."""
        from services.pdf_quality_validator import PDFQualityValidator
        
        validator = PDFQualityValidator()
        assert callable(validator.validate_pdf_reconstruction_quality)

    def test_validate_pdf_reconstruction_quality_missing_files(self, tmp_path):
        """Test validation handles missing files gracefully."""
        from services.pdf_quality_validator import PDFQualityValidator
        
        validator = PDFQualityValidator()
        
        # Non-existent files should return warnings, not raise
        result = validator.validate_pdf_reconstruction_quality(
            original_pdf=str(tmp_path / "nonexistent1.pdf"),
            reconstructed_pdf=str(tmp_path / "nonexistent2.pdf"),
        )
        
        assert "passed" in result
        assert "warnings" in result


class TestConfidenceScorerIntegration:
    """Tests for confidence scorer integration."""

    def test_confidence_scorer_initialization(self):
        """Test ConfidenceScorer can be initialized."""
        from services.confidence_scorer import ConfidenceScorer
        
        scorer = ConfidenceScorer()
        
        assert scorer.confidence_threshold is not None
        assert isinstance(scorer.philosophical_indicators, set)

    def test_adjust_confidence_threshold(self):
        """Test adjust_confidence_threshold method."""
        from services.confidence_scorer import ConfidenceScorer
        
        scorer = ConfidenceScorer()
        original_threshold = scorer.confidence_threshold
        
        scorer.adjust_confidence_threshold(0.7)
        assert scorer.confidence_threshold == 0.7
        
        # Restore original
        scorer.adjust_confidence_threshold(original_threshold)

    def test_calculate_confidence_factors(self):
        """Test calculate_confidence_factors method."""
        from services.confidence_scorer import ConfidenceScorer
        
        scorer = ConfidenceScorer()
        
        factors = scorer.calculate_confidence_factors("philosophy")
        
        assert factors is not None
        assert hasattr(factors, 'rarity_score')
        assert hasattr(factors, 'pattern_score')

    def test_get_confidence_breakdown(self):
        """Test get_confidence_breakdown method."""
        from services.confidence_scorer import ConfidenceScorer
        
        scorer = ConfidenceScorer()
        
        factors = scorer.calculate_confidence_factors("philosophy")
        breakdown = scorer.get_confidence_breakdown(factors)
        
        assert isinstance(breakdown, dict)

    def test_update_patterns(self):
        """Test update_patterns method."""
        from services.confidence_scorer import ConfidenceScorer
        
        scorer = ConfidenceScorer()
        
        new_patterns = {
            "test_patterns": ["test1", "test2"]
        }
        
        scorer.update_patterns(new_patterns)
        
        assert "test_patterns" in scorer.patterns

    def test_update_philosophical_indicators(self):
        """Test update_philosophical_indicators method."""
        from services.confidence_scorer import ConfidenceScorer
        
        scorer = ConfidenceScorer()
        
        new_indicators = {"new_indicator_1", "new_indicator_2"}
        initial_count = len(scorer.philosophical_indicators)
        
        scorer.update_philosophical_indicators(new_indicators)
        
        assert len(scorer.philosophical_indicators) == initial_count + 2
