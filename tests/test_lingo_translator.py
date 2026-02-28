"""Tests for Lingo.dev translator integration."""

import asyncio
import json
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import requests

from services.translation_service import LingoTranslator, TranslationService


class TestLingoTranslator:
    """Test Lingo.dev translator functionality."""

    @pytest.fixture
    def mock_lingo_translator(self):
        """Create a mock Lingo translator for testing."""
        with patch.dict(os.environ, {"LINGO_API_KEY": "test_api_key"}):
            translator = LingoTranslator()
            return translator

    @pytest.mark.asyncio
    async def test_translate_text_success(self, mock_lingo_translator):
        """Test successful text translation."""
        with patch.object(mock_lingo_translator.session, "post") as mock_post:
            # Mock successful response
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"translation": "Hallo Welt"}
            mock_post.return_value = mock_response

            with patch("asyncio.to_thread", new_callable=AsyncMock) as mock_to_thread:
                mock_to_thread.return_value = mock_response

                result = await mock_lingo_translator.translate_text(
                    "Hello World", "en", "de"
                )

                assert result == "Hallo Welt"
                mock_to_thread.assert_called_once()

    @pytest.mark.asyncio
    async def test_translate_text_error_handling(self, mock_lingo_translator):
        """Test error handling in text translation."""
        with patch("asyncio.to_thread", new_callable=AsyncMock) as mock_to_thread:
            # Mock error response
            mock_response = MagicMock()
            mock_response.status_code = 400
            mock_response.text = "Bad Request"
            mock_to_thread.return_value = mock_response

            result = await mock_lingo_translator.translate_text(
                "Hello World", "en", "de"
            )

            # Should return original text on error
            assert result == "Hello World"

    @pytest.mark.asyncio
    async def test_translate_batch(self, mock_lingo_translator):
        """Test batch translation."""
        texts = ["Hello", "World", "Test"]

        with patch.object(mock_lingo_translator, "translate_text") as mock_translate:
            mock_translate.side_effect = ["Hallo", "Welt", "Test"]

            results = await mock_lingo_translator.translate_batch(texts, "en", "de")

            assert results == ["Hallo", "Welt", "Test"]
            assert mock_translate.call_count == 3

    def test_lingo_translator_initialization_error(self):
        """Test Lingo translator initialization with missing API key."""
        with pytest.raises(ValueError, match="LINGO_API_KEY is required"):
            LingoTranslator("")

    # Edge Case Tests
    @pytest.mark.asyncio
    async def test_empty_string_translation(self, mock_lingo_translator):
        """Test translation of empty strings."""
        result = await mock_lingo_translator.translate_text("", "en", "de")
        assert result == ""

        result = await mock_lingo_translator.translate_text("   ", "en", "de")
        assert result == "   "

    @pytest.mark.asyncio
    async def test_very_long_text_translation(self, mock_lingo_translator):
        """Test translation of very long text."""
        long_text = "This is a very long text. " * 1000  # ~27,000 characters

        with patch("asyncio.to_thread", new_callable=AsyncMock) as mock_to_thread:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"translation": "German translation"}
            mock_to_thread.return_value = mock_response

            result = await mock_lingo_translator.translate_text(long_text, "en", "de")

            assert result == "German translation"
            mock_to_thread.assert_called_once()

    @pytest.mark.asyncio
    async def test_malformed_json_response(self, mock_lingo_translator):
        """Test handling of malformed JSON responses."""
        with patch("asyncio.to_thread", new_callable=AsyncMock) as mock_to_thread:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.side_effect = json.JSONDecodeError("Invalid JSON", "", 0)
            mock_to_thread.return_value = mock_response

            result = await mock_lingo_translator.translate_text("Hello", "en", "de")

            # Should return original text on JSON decode error
            assert result == "Hello"

    @pytest.mark.asyncio
    async def test_missing_translation_field(self, mock_lingo_translator):
        """Test response with missing translation field."""
        with patch("asyncio.to_thread", new_callable=AsyncMock) as mock_to_thread:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"error": "Translation failed"}
            mock_to_thread.return_value = mock_response

            result = await mock_lingo_translator.translate_text("Hello", "en", "de")

            # Should return original text when translation field is missing
            assert result == "Hello"

    @pytest.mark.asyncio
    async def test_alternative_response_format(self, mock_lingo_translator):
        """Test response with 'text' field instead of 'translation'."""
        with patch("asyncio.to_thread", new_callable=AsyncMock) as mock_to_thread:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"text": "Hallo"}
            mock_to_thread.return_value = mock_response

            result = await mock_lingo_translator.translate_text("Hello", "en", "de")

            assert result == "Hallo"

    @pytest.mark.asyncio
    async def test_network_timeout(self, mock_lingo_translator):
        """Test handling of network timeouts."""
        with patch("asyncio.to_thread", new_callable=AsyncMock) as mock_to_thread:
            mock_to_thread.side_effect = requests.exceptions.Timeout(
                "Request timed out"
            )

            result = await mock_lingo_translator.translate_text("Hello", "en", "de")

            # Should return original text on timeout
            assert result == "Hello"

    @pytest.mark.asyncio
    async def test_connection_error(self, mock_lingo_translator):
        """Test handling of connection errors."""
        with patch("asyncio.to_thread", new_callable=AsyncMock) as mock_to_thread:
            mock_to_thread.side_effect = requests.exceptions.ConnectionError(
                "Connection failed"
            )

            result = await mock_lingo_translator.translate_text("Hello", "en", "de")

            # Should return original text on connection error
            assert result == "Hello"

    @pytest.mark.asyncio
    async def test_api_rate_limiting(self, mock_lingo_translator):
        """Test handling of API rate limiting (429 status)."""
        with patch("asyncio.to_thread", new_callable=AsyncMock) as mock_to_thread:
            mock_response = MagicMock()
            mock_response.status_code = 429
            mock_response.text = "Rate limit exceeded"
            mock_to_thread.return_value = mock_response

            result = await mock_lingo_translator.translate_text("Hello", "en", "de")

            # Should return original text on rate limiting
            assert result == "Hello"

    @pytest.mark.asyncio
    async def test_server_error(self, mock_lingo_translator):
        """Test handling of server errors (500 status)."""
        with patch("asyncio.to_thread", new_callable=AsyncMock) as mock_to_thread:
            mock_response = MagicMock()
            mock_response.status_code = 500
            mock_response.text = "Internal server error"
            mock_to_thread.return_value = mock_response

            result = await mock_lingo_translator.translate_text("Hello", "en", "de")

            # Should return original text on server error
            assert result == "Hello"

    @pytest.mark.asyncio
    async def test_concurrent_translations(self, mock_lingo_translator):
        """Test concurrent translation requests."""
        with patch("asyncio.to_thread", new_callable=AsyncMock) as mock_to_thread:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"translation": "Hallo"}
            mock_to_thread.return_value = mock_response

            # Run multiple translations concurrently
            tasks = [
                mock_lingo_translator.translate_text("Hello", "en", "de")
                for _ in range(5)
            ]

            results = await asyncio.gather(*tasks)

            # All should succeed
            assert all(result == "Hallo" for result in results)
            assert mock_to_thread.call_count == 5

    @pytest.mark.asyncio
    async def test_batch_with_empty_strings(self, mock_lingo_translator):
        """Test batch translation with empty strings."""
        texts = ["Hello", "", "World", "   ", "Test"]

        with patch.object(mock_lingo_translator, "translate_text") as mock_translate:
            # Only non-empty strings should be translated
            mock_translate.side_effect = ["Hallo", "Welt", "Test"]

            results = await mock_lingo_translator.translate_batch(texts, "en", "de")

            # Empty strings should be returned as-is
            assert results == ["Hallo", "", "Welt", "   ", "Test"]
            # translate_text should only be called for non-empty strings
            assert mock_translate.call_count == 3

    @pytest.mark.asyncio
    async def test_special_characters_translation(self, mock_lingo_translator):
        """Test translation with special characters and Unicode."""
        special_text = "Hello! @#$%^&*()_+ 你好 🌍 café naïve résumé"

        with patch("asyncio.to_thread", new_callable=AsyncMock) as mock_to_thread:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"translation": "German special chars"}
            mock_to_thread.return_value = mock_response

            result = await mock_lingo_translator.translate_text(
                special_text, "en", "de"
            )

            assert result == "German special chars"


class TestTranslationServiceWithLingo:
    """Test TranslationService with Lingo provider."""

    @pytest.fixture
    def mock_translation_service(self):
        """Create a mock translation service for testing."""
        with patch.dict(os.environ, {"LINGO_API_KEY": "test_api_key"}):
            service = TranslationService()
            return service

    def test_service_initialization(self, mock_translation_service):
        """Test service initializes with Lingo provider."""
        assert "lingo" in mock_translation_service.providers
        assert len(mock_translation_service.providers) == 1

    def test_get_available_providers(self, mock_translation_service):
        """Test getting available providers."""
        providers = mock_translation_service.get_available_providers()
        assert providers == ["lingo"]

    @pytest.mark.asyncio
    async def test_select_best_provider(self, mock_translation_service):
        """Test provider selection through public interface."""
        with patch.object(
            mock_translation_service.providers["lingo"], "translate_text"
        ) as mock_translate:
            mock_translate.return_value = "Test Result"

            # Using "auto" provider should select the best available provider
            result = await mock_translation_service.translate_text(
                "Test", "en", "de", "auto"
            )

            # Verify that lingo provider was selected and called
            assert result == "Test Result"
            mock_translate.assert_called_once_with("Test", "en", "de")

    @pytest.mark.asyncio
    async def test_translate_text_with_auto_provider(self, mock_translation_service):
        """Test text translation with auto provider selection."""
        with patch.object(
            mock_translation_service.providers["lingo"], "translate_text"
        ) as mock_translate:
            mock_translate.return_value = "Hallo Welt"

            result = await mock_translation_service.translate_text(
                "Hello World", "en", "de", "auto"
            )

            assert result == "Hallo Welt"
            mock_translate.assert_called_once_with("Hello World", "en", "de")

    @pytest.mark.asyncio
    async def test_translate_batch_with_lingo_provider(self, mock_translation_service):
        """Test batch translation with Lingo provider."""
        texts = ["Hello", "World"]

        with patch.object(
            mock_translation_service.providers["lingo"], "translate_batch"
        ) as mock_translate_batch:
            mock_translate_batch.return_value = ["Hallo", "Welt"]

            results = await mock_translation_service.translate_batch(
                texts, "en", "de", "lingo"
            )

            assert results == ["Hallo", "Welt"]
            mock_translate_batch.assert_called_once_with(texts, "en", "de")

    @pytest.mark.asyncio
    async def test_invalid_provider_error(self, mock_translation_service):
        """Test error handling for invalid provider."""
        with pytest.raises(ValueError, match="Provider invalid not available"):
            await mock_translation_service.translate_text(
                "Hello", "en", "de", "invalid"
            )

    # Additional TranslationService Edge Cases
    @pytest.mark.asyncio
    async def test_empty_text_service_level(self, mock_translation_service):
        """Test empty text handling at service level."""
        result = await mock_translation_service.translate_text("", "en", "de", "lingo")
        assert result == ""

        result = await mock_translation_service.translate_text(
            "   ", "en", "de", "lingo"
        )
        assert result == "   "

    @pytest.mark.asyncio
    async def test_batch_translation_failure_fallback(self, mock_translation_service):
        """Test batch translation fallback on provider failure."""
        texts = ["Hello", "World", "Test"]

        with patch.object(
            mock_translation_service.providers["lingo"], "translate_batch"
        ) as mock_translate_batch:
            mock_translate_batch.side_effect = Exception("Provider failed")

            results = await mock_translation_service.translate_batch(
                texts, "en", "de", "lingo"
            )

            # Should fallback to original texts
            assert results == texts

    @pytest.mark.asyncio
    async def test_single_translation_failure_fallback(self, mock_translation_service):
        """Test single translation fallback on provider failure."""
        with patch.object(
            mock_translation_service.providers["lingo"], "translate_text"
        ) as mock_translate:
            mock_translate.side_effect = Exception("Provider failed")

            result = await mock_translation_service.translate_text(
                "Hello", "en", "de", "lingo"
            )

            # Should fallback to original text
            assert result == "Hello"

    @pytest.mark.asyncio
    async def test_terminology_preprocessing(self):
        """Test terminology mapping preprocessing."""
        terminology_map = {"hello": "greeting", "world": "earth"}

        with patch.dict(os.environ, {"LINGO_API_KEY": "test_api_key"}):
            service = TranslationService(terminology_map=terminology_map)

            with patch.object(
                service.providers["lingo"], "translate_text"
            ) as mock_translate:
                mock_translate.return_value = "translated result"

                await service.translate_text("hello world", "en", "de", "lingo")

                # Should call with preprocessed text containing non-translate spans
                called_args = mock_translate.call_args[0]
                preprocessed_text = called_args[0]

                assert '<span translate="no">hello</span>' in preprocessed_text
                assert '<span translate="no">world</span>' in preprocessed_text

    @pytest.mark.asyncio
    async def test_batch_with_mixed_content(self, mock_translation_service):
        """Test batch translation with mixed content types."""
        texts = [
            "Hello World",
            "",
            "   ",
            "Special chars: @#$%",
            "Very long " * 100 + "text",
        ]

        with patch.object(
            mock_translation_service.providers["lingo"], "translate_batch"
        ) as mock_translate_batch:
            mock_translate_batch.return_value = [
                "Hallo Welt",
                "",
                "   ",
                "Spezialzeichen: @#$%",
                "Sehr langer Text",
            ]

            results = await mock_translation_service.translate_batch(
                texts, "en", "de", "lingo"
            )

            assert len(results) == 5
            assert results[0] == "Hallo Welt"
            assert results[1] == ""
            assert results[2] == "   "

    def test_service_initialization_without_api_key(self):
        """Test service initialization failure without API key."""
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ValueError, match="LINGO_API_KEY not found"):
                TranslationService()

    @pytest.mark.asyncio
    async def test_no_providers_available_error(self):
        """Test error when no providers are available."""
        with patch.dict(os.environ, {"LINGO_API_KEY": "test_api_key"}):
            service = TranslationService()
            # Clear providers to simulate no available providers
            service.providers.clear()

            with pytest.raises(ValueError, match="No translation providers available"):
                await service.translate_text("Hello", "en", "de", "auto")

    @pytest.mark.asyncio
    async def test_invalid_language_codes(self, lingo_translator):
        """Test handling of invalid language codes."""
        with patch("asyncio.to_thread", new_callable=AsyncMock) as mock_to_thread:
            # Mock API response for invalid language codes
            mock_response = MagicMock()
            mock_response.status_code = 400
            mock_response.text = "Invalid language code"
            mock_to_thread.return_value = mock_response

            result = await lingo_translator.translate_text(
                "Hello", "invalid_lang", "also_invalid"
            )

            # Should return original text on invalid language codes
            assert result == "Hello"

    @pytest.mark.asyncio
    async def test_extremely_long_batch_translation(self, mock_translation_service):
        """Test batch translation with many items."""
        texts = [f"Text number {i}" for i in range(100)]

        with patch.object(
            mock_translation_service.providers["lingo"], "translate_batch"
        ) as mock_translate_batch:
            mock_translate_batch.return_value = [f"German text {i}" for i in range(100)]

            results = await mock_translation_service.translate_batch(
                texts, "en", "de", "lingo"
            )

            assert len(results) == 100
            assert all(result.startswith("German text") for result in results)

    @pytest.mark.asyncio
    async def test_rate_limiting_with_retry_simulation(self, lingo_translator):
        """Test realistic rate limiting scenario."""
        with patch("asyncio.to_thread", new_callable=AsyncMock) as mock_to_thread:
            # First call returns rate limit, subsequent calls succeed
            rate_limit_response = MagicMock()
            rate_limit_response.status_code = 429
            rate_limit_response.text = "Rate limit exceeded"

            success_response = MagicMock()
            success_response.status_code = 200
            success_response.json.return_value = {"translation": "Success"}

            mock_to_thread.side_effect = [rate_limit_response, success_response]

            # First call should fail due to rate limiting
            result1 = await lingo_translator.translate_text("Hello", "en", "de")
            assert result1 == "Hello"  # Fallback to original

            # Second call should succeed
            result2 = await lingo_translator.translate_text("Hello", "en", "de")
            assert result2 == "Success"
