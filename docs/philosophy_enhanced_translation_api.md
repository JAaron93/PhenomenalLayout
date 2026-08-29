# Philosophy-Enhanced Translation API Documentation

> [!NOTE]
> For full-length books and treatises, PhenomenalLayout has migrated to **Google Cloud Document Translation Advanced (v3)** with **Dual-Tier Glossary Synchronization**, **Modal Volume Persistent Vocabulary Storage** (`UserVocabularyStore`), and **Scholarly Resilience** (`FrakturClassifier`, `BatchJobRecoveryManager`, `FallbackPageTranslator`, `DualPaneViewerController`). See [ADR 0001](adr/0001-migrate-to-google-cloud-document-translation.md) and the [.kiro/specs/gcp-migration/](../.kiro/specs/gcp-migration/) specification suite for the modern cloud-native architecture.

## Overview

The Philosophy-Enhanced Translation API provides comprehensive neologism detection and user choice management capabilities integrated with the existing translation infrastructure. This system is specifically designed for translating philosophical texts while preserving the integrity of philosophical neologisms according to user preferences.

## Table of Contents

1. [Core Services](#core-services)
2. [Philosophy-Enhanced Translation Service](#philosophy-enhanced-translation-service)
3. [Philosophy-Enhanced Document Processor](#philosophy-enhanced-document-processor)
4. [Progress Tracking](#progress-tracking)
5. [User Choice Management](#user-choice-management)
6. [Performance Optimization](#performance-optimization)
7. [Error Handling](#error-handling)
8. [Examples](#examples)

## Core Services

### Method Types: Synchronous vs Asynchronous

**Important Note:** The API contains both synchronous and asynchronous methods. Follow these guidelines:

- **Translation Service Methods** (`PhilosophyEnhancedTranslationService`): **Synchronous** - do not use `await`
- **Document Processor Methods** (`PhilosophyEnhancedDocumentProcessor`): **Asynchronous** - use `await`
- **User Choice Manager Methods** (`UserChoiceManager`): **Synchronous** - do not use `await`

**Verification:** All code examples in this documentation have been validated for async/await consistency:
- ✅ Translation service examples (lines 68-78, 103-113, 138-145) use synchronous calls
- ✅ Document processor examples (lines 191-203, 218-224) use async/await
- ✅ FastAPI integration (lines 521-535) uses synchronous endpoint for synchronous service calls

### PhilosophyEnhancedTranslationService

The main service that integrates neologism detection with translation capabilities.

#### Initialization

```python
from services.philosophy_enhanced_translation_service import PhilosophyEnhancedTranslationService

# Default initialization
service = PhilosophyEnhancedTranslationService()

# Custom initialization
service = PhilosophyEnhancedTranslationService(
    translation_service=custom_translation_service,
    neologism_detector=custom_neologism_detector,
    user_choice_manager=custom_user_choice_manager,
    terminology_path="path/to/terminology.json"
)
```

#### Methods

##### `translate_text_with_neologism_handling()`

Translates text while detecting and handling neologisms according to user preferences.

**Parameters:**
- `text` (str): The text to translate
- `source_lang` (str): Source language code (e.g., "en", "de", "fr")
- `target_lang` (str): Target language code
- `provider` (str): Translation provider ("auto", "lingo", etc.)
- `session_id` (str): User session ID for choice management
- `progress_callback` (Optional[Callable]): Progress callback function

**Returns:**
- `NeologismPreservationResult`: Comprehensive result with original text, translated text, neologism analysis, and preservation information

**Example:**
```python
result = service.translate_text_with_neologism_handling(
    text="Dasein is a fundamental concept in Heideggerian philosophy",
    source_lang="en",
    target_lang="de",
    provider="auto",
    session_id="user_session_123"
)

print(f"Original: {result.original_text}")
print(f"Translated: {result.translated_text}")
print(f"Neologisms detected: {result.neologism_analysis.total_neologisms}")
```

##### `translate_batch_with_neologism_handling()`

Translates multiple texts in batch while handling neologisms.

**Parameters:**
- `texts` (List[str]): List of texts to translate
- `source_lang` (str): Source language code
- `target_lang` (str): Target language code
- `provider` (str): Translation provider
- `session_id` (str): User session ID
- `progress_callback` (Optional[Callable]): Progress callback function

**Returns:**
- `List[NeologismPreservationResult]`: List of translation results

**Example:**
```python
texts = [
    "Dasein encompasses the whole of human existence",
    "Angst reveals the fundamental groundlessness of existence"
]

results = service.translate_batch_with_neologism_handling(
    texts=texts,
    source_lang="en",
    target_lang="de",
    provider="auto",
    session_id="batch_session_456"
)

for i, result in enumerate(results):
    print(f"Text {i+1}: {result.translated_text}")
```

##### `translate_document_with_neologism_handling()`

Translates an entire document with neologism handling.

**Parameters:**
- `document` (Dict[str, Any]): Document content structure
- `source_lang` (str): Source language code
- `target_lang` (str): Target language code
- `provider` (str): Translation provider
- `session_id` (str): User session ID
- `progress_callback` (Optional[Callable]): Progress callback function

**Returns:**
- `Dict[str, Any]`: Document translation result with metadata

**Example:**
```python
document = {
    "type": "pdf_advanced",
    "pages": [...],  # Document pages
    "text_by_page": {...}  # Text content by page
}

result = service.translate_document_with_neologism_handling(
    document=document,
    source_lang="en",
    target_lang="de",
    provider="auto",
    session_id="doc_session_789"
)
```

### PhilosophyEnhancedDocumentProcessor

Enhanced document processor with integrated neologism detection and user choice management.

#### Initialization

```python
from services.philosophy_enhanced_document_processor import PhilosophyEnhancedDocumentProcessor

# Default initialization
processor = PhilosophyEnhancedDocumentProcessor()

# Custom initialization
processor = PhilosophyEnhancedDocumentProcessor(
    base_processor=custom_base_processor,
    philosophy_translation_service=custom_philosophy_service,
    neologism_detector=custom_detector,
    user_choice_manager=custom_choice_manager,
    dpi=300,
    preserve_images=True,
    max_concurrent_pages=8
)
```

#### Methods

##### `process_document_with_philosophy_awareness()`

Processes a document with comprehensive philosophy-aware translation.

**Parameters:**
- `file_path` (str): Path to the document file
- `source_lang` (str): Source language code
- `target_lang` (str): Target language code
- `provider` (str): Translation provider
- `user_id` (Optional[str]): User ID for session management
- `session_id` (Optional[str]): Existing session ID or None to create new
- `progress_callback` (Optional[Callable]): Progress callback function

**Returns:**
- `PhilosophyDocumentResult`: Comprehensive processing result

**Example:**
```python
result = await processor.process_document_with_philosophy_awareness(
    file_path="philosophical_text.pdf",
    source_lang="en",
    target_lang="de",
    provider="auto",
    user_id="philosopher_123",
    progress_callback=lambda p: print(f"Progress: {p.overall_progress:.1f}%")
)

print(f"Document processed: {result.session_id}")
print(f"Neologisms detected: {result.document_neologism_analysis.total_neologisms}")
print(f"Processing time: {result.processing_time:.2f}s")
```

##### `create_translated_document_with_philosophy_awareness()`

Creates a translated document with philosophy-aware enhancements.

**Parameters:**
- `processing_result` (PhilosophyDocumentResult): Result from document processing
- `output_filename` (str): Output filename for the translated document

**Returns:**
- `str`: Path to the created translated document

**Example:**
```python
output_path = await processor.create_translated_document_with_philosophy_awareness(
    processing_result=result,
    output_filename="translated_philosophical_text.pdf"
)

print(f"Translated document saved to: {output_path}")
```

## Progress Tracking

### PhilosophyTranslationProgress

Tracks progress during philosophy-enhanced translation operations.

#### Properties

- `text_processing_progress` (int): Text processing progress (0-100)
- `neologism_detection_progress` (int): Neologism detection progress (0-100)
- `user_choice_application_progress` (int): User choice application progress (0-100)
- `translation_progress` (int): Translation progress (0-100)
- `overall_progress` (float): Overall progress percentage
- `current_stage` (str): Current processing stage
- `elapsed_time` (float): Elapsed time in seconds

#### Example Usage

```python
def progress_callback(progress: PhilosophyTranslationProgress):
    print(f"Overall Progress: {progress.overall_progress:.1f}%")
    print(f"Current Stage: {progress.current_stage}")
    print(f"Elapsed Time: {progress.elapsed_time:.2f}s")
```

### PhilosophyProcessingProgress

Tracks progress during document processing with philosophy awareness.

#### Properties

- `extraction_progress` (int): Document extraction progress (0-100)
- `neologism_detection_progress` (int): Neologism detection progress (0-100)
- `user_choice_progress` (int): User choice progress (0-100)
- `translation_progress` (int): Translation progress (0-100)
- `reconstruction_progress` (int): Document reconstruction progress (0-100)
- `overall_progress` (float): Overall progress percentage
- `total_pages` (int): Total number of pages
- `processed_pages` (int): Number of processed pages
- `total_neologisms` (int): Total neologisms detected
- `processed_neologisms` (int): Number of processed neologisms

## User Choice Management

### Setting User Choices

```python
from services.user_choice_manager import UserChoiceManager
from models.user_choice_models import ChoiceType

# Create session
manager = UserChoiceManager()
session = manager.create_session(
    session_name="Philosophy Translation Session",
    document_name="Heidegger Analysis",
    user_id="user123",
    source_language="en",
    target_language="de"
)

# Set choices for neologisms
from models.neologism_models import DetectedNeologism

neologism = DetectedNeologism(
    term="Dasein",
    positions=[(0, 6)],
    context="Dasein is fundamental...",
    confidence=0.9,
    philosophical_domain="existentialism"
)

# Preserve the neologism
manager.set_choice(
    neologism=neologism,
    choice_type=ChoiceType.PRESERVE,
    session_id=session.session_id
)

# Use custom translation
manager.set_choice(
    neologism=neologism,
    choice_type=ChoiceType.CUSTOM,
    session_id=session.session_id,
    custom_translation="Being-there"
)
```

### Retrieving User Choices

```python
# Get choice for specific neologism
choice = manager.get_choice_for_neologism(
    neologism=neologism,
    session_id=session.session_id
)

# Get all choices in session
choices = manager.get_session_choices(session.session_id)
```

## Performance Optimization

### Large Document Processing

For documents with 2,000+ pages, use the optimized processing approach:

```python
from examples.performance_optimization_examples import LargeDocumentProcessor

processor = LargeDocumentProcessor(
    max_concurrent_pages=10,
    chunk_size=50,
    memory_limit_mb=2048,
    enable_memory_management=True
)

# Process with streaming approach
async for result in processor.process_large_document_streaming(
    file_path="large_document.pdf",
    source_lang="en",
    target_lang="de",
    provider="auto",
    user_id="user123"
):
    if result['type'] == 'progress':
        print(f"Progress: {result['progress_percent']:.1f}%")
    elif result['type'] == 'complete':
        print(f"Completed: {result['total_pages']} pages, {result['total_neologisms']} neologisms")
```

### Parallel Processing

For multiple documents:

```python
from examples.performance_optimization_examples import ParallelProcessingOptimizer

parallel_processor = ParallelProcessingOptimizer(max_workers=4)

results = await parallel_processor.process_multiple_documents_parallel(
    document_paths=["doc1.pdf", "doc2.pdf", "doc3.pdf"],
    source_lang="en",
    target_lang="de",
    provider="auto"
)
```

## Error Handling

### Common Error Scenarios

1. **Translation Service Errors**
   - Network connectivity issues
   - API quota limits
   - Invalid language codes

2. **Document Processing Errors**
   - File not found
   - Corrupted documents
   - Unsupported formats

3. **Neologism Detection Errors**
   - Terminology file not found
   - Invalid configuration

### Error Handling Patterns

```python
from services.philosophy_enhanced_translation_service import PhilosophyEnhancedTranslationService
import logging

service = PhilosophyEnhancedTranslationService()

try:
    result = service.translate_text_with_neologism_handling(
        text="Philosophical text",
        source_lang="en",
        target_lang="de",
        provider="auto",
        session_id="session123"
    )
except Exception as e:
    logging.error(f"Translation failed: {e}")
    # Implement fallback logic
    # - Use basic translation without neologism handling
    # - Try alternative provider
    # - Return partial results
```

### Graceful Degradation

The system provides graceful degradation when components fail:

```python
# If neologism detection fails, translation continues without it
# If user choice management fails, defaults are used
# If specific provider fails, auto-fallback to available providers
```

## Statistics and Monitoring

### Translation Service Statistics

```python
stats = service.get_statistics()
print(f"Total translations: {stats['philosophy_enhanced_stats']['total_translations']}")
print(f"Neologisms detected: {stats['philosophy_enhanced_stats']['total_neologisms_detected']}")
print(f"Average detection time: {stats['philosophy_enhanced_stats']['average_detection_time']:.3f}s")
```

### Document Processor Statistics

```python
stats = processor.get_statistics()
print(f"Documents processed: {stats['philosophy_enhanced_processor_stats']['documents_processed']}")
print(f"Average processing time: {stats['philosophy_enhanced_processor_stats']['average_processing_time']:.2f}s")
```

## Convenience Functions

### Quick Document Processing

```python
from services.philosophy_enhanced_document_processor import process_document_with_philosophy_awareness

# One-line document processing
result, output_path = await process_document_with_philosophy_awareness(
    file_path="document.pdf",
    source_lang="en",
    target_lang="de",
    provider="auto",
    user_id="user123",
    terminology_path="terminology.json",
    output_filename="translated_document.pdf"
)
```

### Factory Functions

```python
from services.philosophy_enhanced_document_processor import create_philosophy_enhanced_document_processor

# Create processor with defaults
processor = create_philosophy_enhanced_document_processor(
    dpi=300,
    preserve_images=True,
    terminology_path="terminology.json",
    db_path="user_choices.db"
)
```

## Data Models

### NeologismPreservationResult

```python
@dataclass
class NeologismPreservationResult:
    original_text: str
    translated_text: str
    neologism_analysis: NeologismAnalysis
    neologisms_preserved: List[str]
    preservation_markers: Dict[str, str]
    user_choices_applied: Dict[str, str]
    processing_metadata: Dict[str, Any]
```

### PhilosophyDocumentResult

```python
@dataclass
class PhilosophyDocumentResult:
    translated_content: Dict[str, Any]
    original_content: Dict[str, Any]
    document_neologism_analysis: NeologismAnalysis
    page_neologism_analyses: List[NeologismAnalysis]
    session_id: Optional[str]
    total_choices_applied: int
    processing_metadata: Dict[str, Any]
    processing_time: float
    neologism_detection_time: float
    translation_time: float
```

## Integration Examples

### With Web Framework (FastAPI)

```python
from fastapi import FastAPI, UploadFile, File
from services.philosophy_enhanced_translation_service import PhilosophyEnhancedTranslationService

app = FastAPI()
service = PhilosophyEnhancedTranslationService()

@app.post("/translate-philosophy-text")
def translate_philosophy_text(
    text: str,
    source_lang: str,
    target_lang: str,
    provider: str = "auto",
    session_id: str = None
):
    result = service.translate_text_with_neologism_handling(
        text=text,
        source_lang=source_lang,
        target_lang=target_lang,
        provider=provider,
        session_id=session_id
    )

    return {
        "translated_text": result.translated_text,
        "neologisms_detected": result.neologism_analysis.total_neologisms,
        "neologisms_preserved": result.neologisms_preserved
    }
```

### With CLI Interface

```python
import click
from services.philosophy_enhanced_document_processor import process_document_with_philosophy_awareness

@click.command()
@click.option('--file', '-f', required=True, help='Document file path')
@click.option('--source', '-s', required=True, help='Source language')
@click.option('--target', '-t', required=True, help='Target language')
@click.option('--provider', '-p', default='auto', help='Translation provider')
@click.option('--output', '-o', help='Output filename')
async def translate_document(file, source, target, provider, output):
    """Translate document with philosophy awareness."""
    result, output_path = await process_document_with_philosophy_awareness(
        file_path=file,
        source_lang=source,
        target_lang=target,
        provider=provider,
        output_filename=output
    )

    click.echo(f"Translation completed: {output_path}")
    click.echo(f"Neologisms detected: {result.document_neologism_analysis.total_neologisms}")
```

## Best Practices

1. **Session Management**
   - Always use session IDs for user choice consistency
   - Clean up expired sessions regularly
   - Consider user privacy when storing choices

2. **Performance Optimization**
   - Use batch processing for multiple texts
   - Implement streaming for large documents
   - Monitor memory usage during processing

3. **Error Handling**
   - Implement retry logic for transient failures
   - Provide meaningful error messages
   - Use graceful degradation patterns

4. **Quality Assurance**
   - Validate neologism detection results
   - Review user choice applications
   - Monitor translation quality metrics

## Troubleshooting

### Common Issues

1. **High Memory Usage**
   - Reduce chunk size for large documents
   - Enable memory management
   - Use streaming processing

2. **Slow Processing**
   - Increase concurrent page processing
   - Use batch operations
   - Optimize neologism detection

3. **Translation Quality**
   - Review terminology files
   - Adjust user choice settings
   - Validate provider configurations

### Debug Mode

```python
import logging

# Enable debug logging
logging.basicConfig(level=logging.DEBUG)

# Use debug mode in services
service = PhilosophyEnhancedTranslationService(debug=True)
```

This comprehensive API documentation provides developers with all the information needed to effectively use the philosophy-enhanced translation system for their applications.
