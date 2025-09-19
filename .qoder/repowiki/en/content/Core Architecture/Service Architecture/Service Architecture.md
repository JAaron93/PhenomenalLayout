# Service Architecture

<cite>
**Referenced Files in This Document**  
- [services/enhanced_document_processor.py](file://services/enhanced_document_processor.py)
- [services/dolphin_ocr_service.py](file://services/dolphin_ocr_service.py)
- [services/layout_aware_translation_service.py](file://services/layout_aware_translation_service.py)
- [services/pdf_document_reconstructor.py](file://services/pdf_document_reconstructor.py)
- [services/philosophy_enhanced_document_processor.py](file://services/philosophy_enhanced_document_processor.py)
- [services/main_document_processor.py](file://services/main_document_processor.py)
- [config/settings.py](file://config/settings.py)
- [api/routes.py](file://api/routes.py)
</cite>

## Table of Contents
1. [Introduction](#introduction)
2. [Service Layer Overview](#service-layer-overview)
3. [Core Service Components](#core-service-components)
4. [Enhanced Document Processor](#enhanced-document-processor)
5. [Dolphin OCR Service](#dolphin-ocr-service)
6. [Layout-Aware Translation Service](#layout-aware-translation-service)
7. [PDF Document Reconstructor](#pdf-document-reconstructor)
8. [Philosophy-Enhanced Document Processor](#philosophy-enhanced-document-processor)
9. [Service Dependencies and Injection](#service-dependencies-and-injection)
10. [Service Interaction Patterns](#service-interaction-patterns)
11. [Error Handling and Retry Mechanisms](#error-handling-and-retry-mechanisms)
12. [Performance Considerations](#performance-considerations)

## Introduction
The PhenomenalLayout service layer implements a modular architecture where each service encapsulates a specific business capability following the Service Pattern. This documentation details the core services responsible for document processing, from OCR extraction to layout-preserving translation and PDF reconstruction. The architecture emphasizes dependency injection, with services being instantiated and passed to orchestrators that coordinate complex workflows. The system supports both synchronous and asynchronous processing patterns, with comprehensive error handling and retry mechanisms for external service calls.

## Service Layer Overview
The service layer of PhenomenalLayout consists of specialized services that handle distinct aspects of document processing. The architecture follows a clear separation of concerns, with each service responsible for a specific domain: OCR processing, layout-aware translation, PDF reconstruction, and philosophy-enhanced document processing. Services are designed to be stateless and reusable, with dependencies injected through constructor parameters. The main orchestrator, `DocumentProcessor`, coordinates the workflow by chaining service calls in a pipeline that converts PDFs to images, extracts text with layout information, translates content while preserving formatting, and reconstructs the final document.

```mermaid
graph TD
A[DocumentProcessor] --> B[PDFToImageConverter]
A --> C[DolphinOCRService]
A --> D[LayoutAwareTranslationService]
A --> E[PDFDocumentReconstructor]
F[PhilosophyEnhancedDocumentProcessor] --> G[EnhancedDocumentProcessor]
F --> H[PhilosophyEnhancedTranslationService]
F --> I[NeologismDetector]
F --> J[UserChoiceManager]
G --> K[PDFToImageConverter]
G --> C
G --> E
```

**Diagram sources**
- [services/main_document_processor.py](file://services/main_document_processor.py#L1-L323)
- [services/philosophy_enhanced_document_processor.py](file://services/philosophy_enhanced_document_processor.py#L1-L730)

## Core Service Components
The service layer comprises several key components that work together to process documents. The `EnhancedDocumentProcessor` serves as the central orchestrator, coordinating OCR, translation, and reconstruction services. The `DolphinOCRService` interfaces with the Dolphin OCR engine for layout analysis and text extraction. The `LayoutAwareTranslationService` ensures translated text fits within original layout constraints by adjusting font size and text wrapping. The `PDFDocumentReconstructor` uses ReportLab to generate output PDFs with precise text-image overlay. Finally, the `PhilosophyEnhancedDocumentProcessor` extends core functionality with philosophical context awareness and neologism detection.

**Section sources**
- [services/enhanced_document_processor.py](file://services/enhanced_document_processor.py#L1-L398)
- [services/dolphin_ocr_service.py](file://services/dolphin_ocr_service.py#L1-L375)
- [services/layout_aware_translation_service.py](file://services/layout_aware_translation_service.py#L1-L311)
- [services/pdf_document_reconstructor.py](file://services/pdf_document_reconstructor.py#L1-L487)

## Enhanced Document Processor
The `EnhancedDocumentProcessor` is the central orchestrator of document processing, coordinating OCR, translation, and layout preservation. It initializes with dependencies on `PDFToImageConverter`, `DolphinOCRService`, and `PDFDocumentReconstructor`, which are injected through dependency injection. The processor extracts content from PDFs by converting them to images and calling Dolphin OCR to obtain layout information. It then creates translated documents by using the reconstructor to preserve original formatting. The service validates Dolphin layout structure and handles errors gracefully, continuing processing even when OCR fails. It supports PDF-only processing with advanced layout preservation, using DPI settings to control image quality.

```mermaid
classDiagram
class EnhancedDocumentProcessor {
+dpi : int
+preserve_images : bool
+pdf_converter : PDFToImageConverter
+ocr : DolphinOCRService
+reconstructor : PDFDocumentReconstructor
+__init__(dpi : int, preserve_images : bool)
+extract_content(file_path : str) dict[str, Any]
+create_translated_document(original_content : dict, translated_texts : dict, output_filename : str) str
+convert_format(input_path : str, target_format : str) str
+generate_preview(file_path : str, max_chars : int) str | None
}
class DocumentMetadata {
+filename : str
+file_type : str
+total_pages : int
+total_text_elements : int
+file_size_mb : float
+processing_time : float
+dpi : int
}
EnhancedDocumentProcessor --> PDFToImageConverter : "uses"
EnhancedDocumentProcessor --> DolphinOCRService : "uses"
EnhancedDocumentProcessor --> PDFDocumentReconstructor : "uses"
EnhancedDocumentProcessor --> DocumentMetadata : "creates"
```

**Diagram sources**
- [services/enhanced_document_processor.py](file://services/enhanced_document_processor.py#L1-L398)

**Section sources**
- [services/enhanced_document_processor.py](file://services/enhanced_document_processor.py#L1-L398)

## Dolphin OCR Service
The `DolphinOCRService` provides a thin HTTP client interface to the Dolphin OCR Modal service for layout analysis and text extraction. It handles authentication via HF token and endpoint configuration through environment variables. The service implements comprehensive error handling and retry mechanisms, mapping HTTP status codes to standardized error types. It supports both synchronous and asynchronous processing, with retry logic for rate limiting (429) and service unavailability (5xx) errors. The service includes performance metrics tracking and validates image size and count before making requests. Configuration can be supplied directly or sourced from environment variables, with validation performed at call time to allow local development without a configured endpoint.

```mermaid
classDiagram
class DolphinOCRService {
+hf_token : str | None
+modal_endpoint : str | None
+timeout_seconds : int
+max_image_bytes : int
+max_images : int
+max_attempts : int
+backoff_base_seconds : float
+total_requests : int
+successful_requests : int
+failed_requests : int
+last_duration_ms : float
+process_document_images(images : list[bytes]) dict[str, Any]
+process_document_images_async(images : list[bytes]) dict[str, Any]
+_require_endpoint() str
+_build_auth_headers() dict[str, str]
+_handle_response_status(resp : httpx.Response, endpoint : str, attempts : int, start : float) str
+_validate_images(images : list[bytes]) void
}
class OcrProcessingError {
+message : str
+context : dict[str, Any]
}
class ServiceUnavailableError {
+message : str
+context : dict[str, Any]
}
class ApiRateLimitError {
+message : str
+context : dict[str, Any]
}
class ConfigurationError {
+message : str
+context : dict[str, Any]
}
class AuthenticationError {
+message : str
+context : dict[str, Any]
}
DolphinOCRService --> OcrProcessingError : "raises"
DolphinOCRService --> ServiceUnavailableError : "raises"
DolphinOCRService --> ApiRateLimitError : "raises"
DolphinOCRService --> ConfigurationError : "raises"
DolphinOCRService --> AuthenticationError : "raises"
```

**Diagram sources**
- [services/dolphin_ocr_service.py](file://services/dolphin_ocr_service.py#L1-L375)

**Section sources**
- [services/dolphin_ocr_service.py](file://services/dolphin_ocr_service.py#L1-L375)

## Layout-Aware Translation Service
The `LayoutAwareTranslationService` coordinates translation with layout preservation decisions, ensuring translated text fits within original layout constraints. It integrates a translation client via the `McpLingoClient` protocol and uses the `LayoutPreservationEngine` to analyze fit and apply adjustments. The service provides both single-item and batch translation APIs, preserving layout context per element. For each text block, it first translates the content, then performs length-aware optimization to reduce unnecessary growth, analyzes layout fit, and applies adjustments such as font scaling and text wrapping. The service returns detailed `TranslationResult` objects containing raw and adjusted text, layout strategy, and quality scores. It supports confidence-aware translation when available from the underlying client.

```mermaid
classDiagram
class LayoutAwareTranslationService {
+_lingo : McpLingoClient
+_engine : LayoutPreservationEngine
+__init__(lingo_client : McpLingoClient, layout_engine : LayoutPreservationEngine)
+translate_with_layout_constraints(text : str, source_lang : str, target_lang : str, layout_context : LayoutContext) TranslationResult
+translate_document_batch(text_blocks : list[TextBlock], source_lang : str, target_lang : str) list[TranslationResult]
}
class McpLingoClient {
<<protocol>>
+translate(text : str, source_lang : str, target_lang : str) str
+translate_batch(texts : list[str], source_lang : str, target_lang : str) list[str]
+translate_with_confidence(text : str, source_lang : str, target_lang : str) tuple[str, float]
+translate_batch_with_confidence(texts : list[str], source_lang : str, target_lang : str) list[tuple[str, float]]
}
class LayoutContext {
+bbox : BoundingBox
+font : FontInfo
+ocr_confidence : float | None
}
class TextBlock {
+text : str
+layout : LayoutContext
}
class TranslationResult {
+source_text : str
+raw_translation : str
+adjusted_text : str
+strategy : LayoutStrategy
+analysis : FitAnalysis
+adjusted_font : FontInfo
+adjusted_bbox : BoundingBox
+quality_score : float
+ocr_confidence : float | None
+translation_confidence : float | None
}
LayoutAwareTranslationService --> McpLingoClient : "depends on"
LayoutAwareTranslationService --> LayoutPreservationEngine : "uses"
LayoutAwareTranslationService --> TranslationResult : "creates"
TextBlock --> LayoutContext : "contains"
```

**Diagram sources**
- [services/layout_aware_translation_service.py](file://services/layout_aware_translation_service.py#L1-L311)

**Section sources**
- [services/layout_aware_translation_service.py](file://services/layout_aware_translation_service.py#L1-L311)

## PDF Document Reconstructor
The `PDFDocumentReconstructor` uses ReportLab to generate output PDFs with precise text-image overlay, preserving the original document's layout. It validates PDF format before reconstruction, checking for proper extension, file existence, %PDF- header, and encryption. The service reconstructs PDFs by creating a ReportLab canvas and rendering each translated element with its specified font, size, color, and position. It handles font selection and fallback, automatically substituting unavailable fonts with appropriate alternatives. The reconstructor implements text wrapping to fit content within bounding boxes and tracks overflow when text exceeds available space. It returns detailed `ReconstructionResult` objects containing output path, success status, processing time, warnings, and quality metrics. The service supports dynamic page sizing based on element positions when explicit dimensions are not provided.

```mermaid
classDiagram
class PDFDocumentReconstructor {
+supported_extension : str
+is_pdf_format(file_path : str | PathLike[str]) bool
+validate_pdf_format_or_raise(file_path : str | PathLike[str]) void
+reconstruct_pdf_document(translated_layout : TranslatedLayout, original_file_path : str, output_path : str) ReconstructionResult
+reconstruct_pdf(translated_layout : TranslatedLayout, _original_file_path : str, output_path : str) ReconstructionResult
+_select_font_name(font : FontInfo) str
+_fallback_font_name(font : FontInfo) str
+_wrap_text_to_width_reportlab(text : str, max_width : float, font_name : str, font_size : float, pdfmetrics_module) list[str]
}
class TranslatedElement {
+original_text : str
+translated_text : str
+adjusted_text : str | None
+bbox : BoundingBox
+font_info : FontInfo
+layout_strategy : str
+confidence : float | None
}
class TranslatedPage {
+page_number : int
+translated_elements : list[TranslatedElement]
+width : float | None
+height : float | None
+original_elements : list[TranslatedElement] | None
}
class TranslatedLayout {
+pages : list[TranslatedPage]
}
class ReconstructionResult {
+output_path : str
+format : str
+success : bool
+processing_time : float
+warnings : list[str]
+quality_metrics : dict[str, float] | None
}
class UnsupportedFormatError {
+message : str
+error_code : str | None
}
class DocumentReconstructionError {
+message : str
}
PDFDocumentReconstructor --> TranslatedLayout : "consumes"
PDFDocumentReconstructor --> ReconstructionResult : "creates"
PDFDocumentReconstructor --> UnsupportedFormatError : "raises"
PDFDocumentReconstructor --> DocumentReconstructionError : "raises"
TranslatedPage --> TranslatedElement : "contains"
TranslatedLayout --> TranslatedPage : "contains"
```

**Diagram sources**
- [services/pdf_document_reconstructor.py](file://services/pdf_document_reconstructor.py#L1-L487)

**Section sources**
- [services/pdf_document_reconstructor.py](file://services/pdf_document_reconstructor.py#L1-L487)

## Philosophy-Enhanced Document Processor
The `PhilosophyEnhancedDocumentProcessor` extends core document processing functionality with philosophical context awareness and neologism detection. It builds upon the `EnhancedDocumentProcessor` while adding integrated neologism detection, user choice management, and enhanced progress tracking. The processor coordinates multiple services including `NeologismDetector`, `UserChoiceManager`, and `PhilosophyEnhancedTranslationService` to provide comprehensive philosophy-aware processing. It implements asynchronous processing with detailed progress tracking through `PhilosophyProcessingProgress` and returns rich `PhilosophyDocumentResult` objects containing neologism analyses, user choices, and processing metadata. The service manages user sessions for choice persistence and provides statistics on neologism detection and choice application rates. It supports both batch and concurrent processing with configurable limits.

```mermaid
classDiagram
class PhilosophyEnhancedDocumentProcessor {
+base_processor : EnhancedDocumentProcessor
+philosophy_translation_service : PhilosophyEnhancedTranslationService
+neologism_detector : NeologismDetector
+user_choice_manager : UserChoiceManager
+enable_batch_processing : bool
+max_concurrent_pages : int
+stats : dict[str, Any]
+__init__(base_processor : EnhancedDocumentProcessor, philosophy_translation_service : PhilosophyEnhancedTranslationService, neologism_detector : NeologismDetector, user_choice_manager : UserChoiceManager, dpi : int, preserve_images : bool, terminology_path : str | None, enable_batch_processing : bool, max_concurrent_pages : int)
+extract_content(file_path : str) dict[str, Any]
+process_document_with_philosophy_awareness(file_path : str, source_lang : str, target_lang : str, provider : str, user_id : str | None, session_id : str | None, philosophy_mode : bool, progress_callback : Callable[[PhilosophyProcessingProgress], None] | None) PhilosophyDocumentResult
+create_translated_document_with_philosophy_awareness(processing_result : PhilosophyDocumentResult, output_filename : str) str
+get_statistics() dict[str, Any]
+cleanup_expired_sessions() int
}
class PhilosophyProcessingProgress {
+extraction_progress : int
+neologism_detection_progress : int
+user_choice_progress : int
+translation_progress : int
+reconstruction_progress : int
+total_pages : int
+processed_pages : int
+total_text_blocks : int
+processed_text_blocks : int
+total_neologisms : int
+processed_neologisms : int
+choices_applied : int
+start_time : float
+current_stage : str
+overall_progress : float
+elapsed_time : float
+to_dict() dict[str, Any]
}
class PhilosophyDocumentResult {
+translated_content : dict[str, Any]
+original_content : dict[str, Any]
+document_neologism_analysis : NeologismAnalysis
+page_neologism_analyses : list[NeologismAnalysis]
+session_id : str | None
+total_choices_applied : int
+processing_metadata : dict[str, Any]
+processing_time : float
+neologism_detection_time : float
+translation_time : float
+to_dict() dict[str, Any]
}
PhilosophyEnhancedDocumentProcessor --> EnhancedDocumentProcessor : "extends"
PhilosophyEnhancedDocumentProcessor --> PhilosophyEnhancedTranslationService : "uses"
PhilosophyEnhancedDocumentProcessor --> NeologismDetector : "uses"
PhilosophyEnhancedDocumentProcessor --> UserChoiceManager : "uses"
PhilosophyEnhancedDocumentProcessor --> PhilosophyProcessingProgress : "creates"
PhilosophyEnhancedDocumentProcessor --> PhilosophyDocumentResult : "creates"
```

**Diagram sources**
- [services/philosophy_enhanced_document_processor.py](file://services/philosophy_enhanced_document_processor.py#L1-L730)

**Section sources**
- [services/philosophy_enhanced_document_processor.py](file://services/philosophy_enhanced_document_processor.py#L1-L730)

## Service Dependencies and Injection
Services in PhenomenalLayout are instantiated and passed via dependency injection, promoting loose coupling and testability. The main orchestrator `DocumentProcessor` receives its dependencies through constructor parameters, including `PDFToImageConverter`, `DolphinOCRService`, `LayoutAwareTranslationService`, and `PDFDocumentReconstructor`. Similarly, the `PhilosophyEnhancedDocumentProcessor` injects its dependencies including the base processor, translation service, neologism detector, and user choice manager. This pattern allows for easy substitution of implementations, particularly for testing where mock services can be injected. The dependency injection approach also enables configuration of service parameters such as DPI, timeout settings, and retry limits at instantiation time, making the system highly configurable.

```mermaid
graph TD
A[DocumentProcessor] --> B[PDFToImageConverter]
A --> C[DolphinOCRService]
A --> D[LayoutAwareTranslationService]
A --> E[PDFDocumentReconstructor]
F[PhilosophyEnhancedDocumentProcessor] --> G[EnhancedDocumentProcessor]
F --> H[PhilosophyEnhancedTranslationService]
F --> I[NeologismDetector]
F --> J[UserChoiceManager]
K[EnhancedDocumentProcessor] --> L[PDFToImageConverter]
K --> C
K --> E
M[LayoutAwareTranslationService] --> N[McpLingoClient]
M --> O[LayoutPreservationEngine]
P[DolphinOCRService] --> Q[httpx.Client]
R[PDFDocumentReconstructor] --> S[ReportLab]
style A fill:#f9f,stroke:#333
style F fill:#f9f,stroke:#333
style K fill:#f9f,stroke:#333
style M fill:#f9f,stroke:#333
style P fill:#f9f,stroke:#333
style R fill:#f9f,stroke:#333
```

**Diagram sources**
- [services/main_document_processor.py](file://services/main_document_processor.py#L1-L323)
- [services/philosophy_enhanced_document_processor.py](file://services/philosophy_enhanced_document_processor.py#L1-L730)
- [services/enhanced_document_processor.py](file://services/enhanced_document_processor.py#L1-L398)

**Section sources**
- [services/main_document_processor.py](file://services/main_document_processor.py#L1-L323)
- [services/philosophy_enhanced_document_processor.py](file://services/philosophy_enhanced_document_processor.py#L1-L730)

## Service Interaction Patterns
The service interaction patterns in PhenomenalLayout follow a coordinated workflow where services are invoked in a specific sequence to process documents. The main document processing workflow begins with PDF conversion to images, followed by OCR processing to extract text and layout information, batch translation with layout preservation, and finally PDF reconstruction. The `DocumentProcessor` orchestrates this workflow, emitting progress events at each stage. The system supports both synchronous and asynchronous patterns, with the philosophy-enhanced processor using async/await for non-blocking operations. Batch processing is implemented to handle multiple text blocks efficiently, with configurable batch sizes to balance memory usage and API call frequency.

```mermaid
sequenceDiagram
participant Client
participant DocumentProcessor
participant Converter
participant OCR
participant Translator
participant Reconstructor
Client->>DocumentProcessor : process_document(request)
DocumentProcessor->>Converter : convert_pdf_to_images()
Converter-->>DocumentProcessor : images
DocumentProcessor->>OCR : process_document_images(images)
OCR-->>DocumentProcessor : ocr_result
DocumentProcessor->>Translator : translate_document_batch()
Translator-->>DocumentProcessor : translations
DocumentProcessor->>Reconstructor : reconstruct_pdf_document()
Reconstructor-->>DocumentProcessor : reconstruction_result
DocumentProcessor-->>Client : ProcessingResult
```

**Diagram sources**
- [services/main_document_processor.py](file://services/main_document_processor.py#L1-L323)

**Section sources**
- [services/main_document_processor.py](file://services/main_document_processor.py#L1-L323)

## Error Handling and Retry Mechanisms
The service layer implements comprehensive error handling and retry mechanisms to ensure robust document processing. The `DolphinOCRService` includes sophisticated retry logic for transient failures, with exponential backoff and jitter for rate limiting (429) and service unavailability (5xx) errors. It maps HTTP status codes to standardized error types such as `ApiRateLimitError`, `ServiceUnavailableError`, and `AuthenticationError`. The `PDFDocumentReconstructor` validates input format and handles encryption detection, raising `UnsupportedFormatError` with standardized error codes like DOLPHIN_014 for encrypted PDFs. Services use defensive programming with input validation and graceful degradation, continuing processing even when non-critical components fail. Error handling is consistent across services, with meaningful error messages and context information to aid debugging.

**Section sources**
- [services/dolphin_ocr_service.py](file://services/dolphin_ocr_service.py#L1-L375)
- [services/pdf_document_reconstructor.py](file://services/pdf_document_reconstructor.py#L1-L487)
- [api/routes.py](file://api/routes.py#L1-L520)

## Performance Considerations
The service architecture considers performance implications of synchronous vs. asynchronous service calls, with different patterns used for different scenarios. The main document processing workflow uses synchronous calls for simplicity and deterministic behavior, while the philosophy-enhanced processor leverages asynchronous processing for improved throughput with large documents. The system implements batching for translation operations to reduce API call overhead, with configurable batch sizes to balance memory usage and performance. PDF processing uses optimized image conversion with configurable DPI settings to balance quality and processing time. The architecture includes performance monitoring with detailed timing metrics for each processing stage, allowing for identification of bottlenecks. Configuration settings in `settings.py` allow tuning of performance-related parameters such as concurrency limits, memory thresholds, and cleanup intervals.

**Section sources**
- [config/settings.py](file://config/settings.py#L1-L549)
- [services/main_document_processor.py](file://services/main_document_processor.py#L1-L323)
- [services/philosophy_enhanced_document_processor.py](file://services/philosophy_enhanced_document_processor.py#L1-L730)
