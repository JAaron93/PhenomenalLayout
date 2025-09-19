# PDF Validation

<cite>
**Referenced Files in This Document**  
- [pdf_quality_validator.py](file://services/pdf_quality_validator.py)
- [pdf_document_reconstructor.py](file://services/pdf_document_reconstructor.py)
- [pdf_to_image.py](file://dolphin_ocr/pdf_to_image.py)
- [main_document_processor.py](file://services/main_document_processor.py)
</cite>

## Table of Contents
1. [Introduction](#introduction)
2. [Core Components](#core-components)
3. [Validation Workflow](#validation-workflow)
4. [Configuration Options](#configuration-options)
5. [Error Handling](#error-handling)
6. [Integration with Document Processor](#integration-with-document-processor)
7. [Performance Considerations](#performance-considerations)

## Introduction
The PDF validation system ensures document integrity and quality throughout the processing pipeline. This documentation details the implementation of the `PDFQualityValidator` class, which performs comprehensive checks on PDF files to ensure they meet quality standards for subsequent OCR and translation processing. The validation process includes file integrity verification, resolution assessment, page corruption detection, and readability evaluation.

## Core Components

The PDF validation functionality is implemented through several key components that work together to ensure document quality. The primary validator class coordinates multiple extraction methods and fallback strategies to handle various PDF quality issues.

```mermaid
classDiagram
class PDFQualityValidator {
+DEFAULT_MAX_PAGES : int
+DEFAULT_OVERALL_TIMEOUT_S : float
+DEFAULT_OCR_TIMEOUT_S : float
+DEFAULT_PDFMINER_CHUNK : int
+DEFAULT_OCR_BATCH_PAGES : int
+DEFAULT_PDF_DPI : int
+DEFAULT_TESS_LANG : str
+DEFAULT_POPPLER_PATH : str
+extract_text_hybrid(pdf_path, max_pages, lang, overall_timeout_seconds, pdfminer_chunk_size, ocr_batch_pages, dpi, poppler_path) ExtractTextResult
+compute_text_accuracy(original_text, translated_text, min_ratio, max_ratio) dict
+compare_layout_hashes(original_pdf, reconstructed_pdf, page_normalize, pages_a, pages_b, max_length_ratio) dict
+validate_pdf_reconstruction_quality(original_pdf, reconstructed_pdf, min_text_length_score, min_layout_score, require_font_preservation, min_font_match_ratio, page_normalize_layout) dict
-_truncate(text, limit) str
-_aggregate_warnings(warnings) dict
-_elapsed_exceeded(start_ts, overall_timeout_s) bool
-_collect_fonts(pdf_path) set[str]
-_extract_text_direct_only(pdf_path) str
-_iter_page_index_chunks(indices, chunk_size) Iterator[list[int]]
-_iter_pages_for_indices(indices, batch) Iterator[range]
}
class ExtractTextResult {
+text_per_page : list[str]
+warnings : list[str]
+warning_counts : dict[str, int]
+used_ocr_pages : list[int]
+extractor_summary : str
}
PDFQualityValidator --> ExtractTextResult : "returns"
```

**Diagram sources**
- [pdf_quality_validator.py](file://services/pdf_quality_validator.py#L1-L668)

**Section sources**
- [pdf_quality_validator.py](file://services/pdf_quality_validator.py#L1-L668)

## Validation Workflow

The PDF validation workflow follows a systematic approach to ensure document quality through multiple stages of inspection and analysis. The process begins with header inspection and progresses through page stream analysis, image density verification, and font embedding checks.

```mermaid
flowchart TD
Start([PDF Validation Start]) --> HeaderCheck["Check PDF Header (%PDF-)"]
HeaderCheck --> ExtensionCheck["Validate File Extension (.pdf)"]
ExtensionCheck --> ExistenceCheck["Verify File Exists"]
ExistenceCheck --> EncryptionCheck["Check for Encryption"]
EncryptionCheck --> PageCount["Determine Page Count"]
PageCount --> DirectExtraction["Attempt Direct Text Extraction (pypdf)"]
DirectExtraction --> EmptyPages{"Empty Pages?"}
EmptyPages --> |Yes| PDFMiner["Use PDFMiner for Text Extraction"]
EmptyPages --> |No| OCRCheck{"Text Quality Adequate?"}
PDFMiner --> OCRCheck
OCRCheck --> |No| OCR["Perform OCR on Problematic Pages"]
OCRCheck --> |Yes| ResolutionCheck["Verify Image Resolution"]
OCR --> ResolutionCheck
ResolutionCheck --> FontCheck["Check Font Embedding"]
FontCheck --> IntegrityCheck["Assess Page Corruption"]
IntegrityCheck --> Summary["Generate Validation Summary"]
Summary --> End([Validation Complete])
```

**Diagram sources**
- [pdf_quality_validator.py](file://services/pdf_quality_validator.py#L1-L668)
- [pdf_to_image.py](file://dolphin_ocr/pdf_to_image.py#L1-L283)

**Section sources**
- [pdf_quality_validator.py](file://services/pdf_quality_validator.py#L1-L668)
- [pdf_to_image.py](file://dolphin_ocr/pdf_to_image.py#L1-L283)

## Configuration Options

The PDF validation system provides several configurable parameters that can be set through environment variables or method arguments. These options allow fine-tuning of the validation process to meet specific requirements.

```mermaid
erDiagram
CONFIGURATION_OPTIONS {
string name PK
string environment_variable
string default_value
string description
string type
string constraints
}
CONFIGURATION_OPTIONS ||--o{ VALIDATION_RULES : defines
CONFIGURATION_OPTIONS ||--o{ PERFORMANCE_METRICS : affects
VALIDATION_RULES {
string rule_name PK
string description
string severity
}
PERFORMANCE_METRICS {
string metric_name PK
string description
string unit
}
CONFIGURATION_OPTIONS {
"DEFAULT_MAX_PAGES" "PDF_QUALITY_MAX_PAGES" "200" "Maximum number of pages to process" "int" "≥1"
"DEFAULT_OVERALL_TIMEOUT_S" "PDF_QUALITY_OVERALL_TIMEOUT_SECONDS" "60" "Overall timeout for validation process" "float" "≥0"
"DEFAULT_OCR_TIMEOUT_S" "PDF_QUALITY_OCR_TIMEOUT_SECONDS" "5" "Timeout for individual OCR operations" "float" "≥0"
"DEFAULT_PDFMINER_CHUNK" "PDF_QUALITY_PDFMINER_CHUNK_SIZE" "16" "Chunk size for PDFMiner processing" "int" "≥1"
"DEFAULT_OCR_BATCH_PAGES" "PDF_QUALITY_OCR_BATCH_PAGES" "8" "Number of pages to process in OCR batches" "int" "≥1"
"DEFAULT_PDF_DPI" "PDF_DPI" "300" "Default DPI for image conversion" "int" "≥72"
"DEFAULT_TESS_LANG" "TESSERACT_LANG" "eng" "Default language for OCR processing" "str" "valid Tesseract language code"
"DEFAULT_POPPLER_PATH" "POPPLER_PATH" "None" "Path to Poppler utilities" "str" "valid filesystem path"
}
VALIDATION_RULES {
"File Integrity Check" "Verifies PDF header and basic structure" "critical"
"Encryption Detection" "Identifies encrypted PDFs that cannot be processed" "critical"
"Resolution Adequacy" "Ensures sufficient DPI for OCR quality" "high"
"Page Corruption" "Detects corrupted or unreadable pages" "high"
"Text Readability" "Assesses text extraction quality and completeness" "medium"
}
PERFORMANCE_METRICS {
"Processing Time" "Total time for validation process" "seconds"
"Memory Usage" "Peak memory consumption during validation" "bytes"
"OCR Page Count" "Number of pages requiring OCR processing" "count"
}
```

**Diagram sources**
- [pdf_quality_validator.py](file://services/pdf_quality_validator.py#L1-L668)

**Section sources**
- [pdf_quality_validator.py](file://services/pdf_quality_validator.py#L1-L668)

## Error Handling

The PDF validation system implements comprehensive error handling to manage various failure scenarios gracefully. Different error types are raised based on specific validation failures, allowing for targeted recovery strategies.

```mermaid
stateDiagram-v2
[*] --> Idle
Idle --> FileIntegrityCheck : "Start Validation"
FileIntegrityCheck --> FileIntegritySuccess : "Valid PDF header"
FileIntegrityCheck --> CorruptedPDFError : "Missing %PDF- header"
FileIntegrityCheck --> FileNotFoundError : "File does not exist"
FileIntegritySuccess --> EncryptionCheck
EncryptionCheck --> EncryptionCheckSuccess : "Not encrypted"
EncryptionCheck --> EncryptedPDFError : "Encrypted PDF detected"
EncryptionCheckSuccess --> PageExtraction
PageExtraction --> DirectExtraction
DirectExtraction --> DirectExtractionSuccess : "Text extracted successfully"
DirectExtraction --> EmptyPageWarning : "Empty page detected"
DirectExtraction --> ExtractionError : "Extraction failed"
EmptyPageWarning --> PDFMinerExtraction
PDFMinerExtraction --> PDFMinerSuccess : "Text extracted with PDFMiner"
PDFMinerExtraction --> PDFMinerFailure : "PDFMiner extraction failed"
PDFMinerFailure --> OCRProcessing
OCRProcessing --> OCRSuccess : "OCR completed successfully"
OCRProcessing --> LowResolutionError : "Insufficient resolution for OCR"
OCRProcessing --> OCRFailure : "OCR processing failed"
OCRSuccess --> ResolutionCheck
ResolutionCheck --> ResolutionAdequate : "Resolution meets requirements"
ResolutionCheck --> LowResolutionError : "Resolution below threshold"
ResolutionAdequate --> FontCheck
FontCheck --> FontCheckSuccess : "Fonts properly embedded"
FontCheck --> FontEmbeddingError : "Missing or corrupted fonts"
FontCheckSuccess --> ValidationComplete
ValidationComplete --> [*]
note right of CorruptedPDFError
Raised when PDF structure is
corrupted or invalid
end note
note right of EncryptedPDFError
Raised when PDF is encrypted
and cannot be processed
end note
note right of LowResolutionError
Raised when image resolution
is below minimum threshold
end note
note right of FontEmbeddingError
Raised when required fonts
are not properly embedded
end note
```

**Diagram sources**
- [pdf_quality_validator.py](file://services/pdf_quality_validator.py#L1-L668)
- [pdf_to_image.py](file://dolphin_ocr/pdf_to_image.py#L1-L283)

**Section sources**
- [pdf_quality_validator.py](file://services/pdf_quality_validator.py#L1-L668)
- [pdf_to_image.py](file://dolphin_ocr/pdf_to_image.py#L1-L283)

## Integration with Document Processor

The PDF validation system is tightly integrated with the main document processing pipeline, ensuring that only valid documents proceed to subsequent processing stages. The validation occurs early in the workflow to prevent unnecessary processing of invalid documents.

```mermaid
sequenceDiagram
participant User as "User Application"
participant Processor as "DocumentProcessor"
participant Validator as "PDFQualityValidator"
participant Reconstructor as "PDFDocumentReconstructor"
participant OCR as "DolphinOCRService"
participant Translator as "LayoutAwareTranslationService"
User->>Processor : process_document(request)
Processor->>Reconstructor : validate_pdf_format_or_raise()
Reconstructor->>Reconstructor : Check file extension
Reconstructor->>Reconstructor : Verify file exists
Reconstructor->>Reconstructor : Check %PDF- header
Reconstructor->>Reconstructor : Detect encryption
alt Valid PDF
Reconstructor-->>Processor : Success
Processor->>Validator : extract_text_hybrid()
Validator->>Validator : Attempt pypdf extraction
alt Direct extraction successful
Validator-->>Processor : Return text
else Empty or corrupted pages
Validator->>Validator : Use PDFMiner
alt PDFMiner successful
Validator-->>Processor : Return text
else OCR required
Validator->>Validator : Convert to images
Validator->>Validator : Perform OCR
Validator-->>Processor : Return OCR text
end
end
Processor->>OCR : process_document_images()
OCR-->>Processor : OCR results
Processor->>Translator : translate_document_batch()
Translator-->>Processor : Translated text
Processor->>Reconstructor : reconstruct_pdf_document()
Reconstructor-->>User : ProcessingResult
else Invalid PDF
Reconstructor--x Processor : UnsupportedFormatError
Processor--x User : ProcessingResult (failure)
end
```

**Diagram sources**
- [main_document_processor.py](file://services/main_document_processor.py#L1-L323)
- [pdf_document_reconstructor.py](file://services/pdf_document_reconstructor.py#L1-L487)
- [pdf_quality_validator.py](file://services/pdf_quality_validator.py#L1-L668)

**Section sources**
- [main_document_processor.py](file://services/main_document_processor.py#L1-L323)
- [pdf_document_reconstructor.py](file://services/pdf_document_reconstructor.py#L1-L487)
- [pdf_quality_validator.py](file://services/pdf_quality_validator.py#L1-L668)

## Performance Considerations

The PDF validation system incorporates several performance optimizations to handle large documents efficiently while minimizing resource consumption. Early failure detection strategies prevent unnecessary processing when validation requirements are not met.

```mermaid
flowchart TD
Start([Start Validation]) --> TimeoutCheck["Initialize Timeout Tracking"]
TimeoutCheck --> PageLimit["Apply Page Limit (DEFAULT_MAX_PAGES)"]
PageLimit --> HeaderValidation["Validate PDF Header"]
HeaderValidation --> EncryptionDetection["Detect Encryption Early"]
EncryptionDetection --> ResolutionCheck["Check Minimum Resolution"]
ResolutionCheck --> ExtractionStrategy["Select Extraction Method"]
ExtractionStrategy --> DirectExtraction{"Use pypdf first?"}
DirectExtraction --> |Yes| PypdfAttempt["Attempt pypdf extraction"]
DirectExtraction --> |No| PDFMinerAttempt["Attempt PDFMiner extraction"]
PypdfAttempt --> ExtractionSuccess{"Extraction successful?"}
PDFMinerAttempt --> ExtractionSuccess
ExtractionSuccess --> |Yes| ContinueProcessing["Continue with extracted text"]
ExtractionSuccess --> |No| OCROnlyMissing["Apply OCR only to missing pages"]
OCROnlyMissing --> BatchProcessing["Process in Batches (DEFAULT_OCR_BATCH_PAGES)"]
BatchProcessing --> MemoryEfficiency["Use Temporary Files to Reduce Memory"]
MemoryEfficiency --> ProgressTracking["Track Progress and Time"]
ProgressTracking --> TimeoutExceeded{"Timeout exceeded?"}
TimeoutExceeded --> |Yes| EarlyTermination["Terminate Early with Warning"]
TimeoutExceeded --> |No| ContinueValidation["Continue Validation"]
ContinueValidation --> ResolutionAdequacy{"Resolution adequate?"}
ResolutionAdequacy --> |No| LowResolutionPath["Flag LowResolutionError"]
ResolutionAdequacy --> |Yes| FontCheck["Check Font Embedding"]
FontCheck --> ValidationComplete["Complete Validation"]
ValidationComplete --> GenerateReport["Generate Validation Report"]
GenerateReport --> End([End Validation])
style EarlyTermination fill:#ffcccc,stroke:#f66
style LowResolutionPath fill:#ffcccc,stroke:#f66
click EarlyTermination "## Error Handling" "Navigate to Error Handling section"
click LowResolutionPath "## Error Handling" "Navigate to Error Handling section"
```

**Diagram sources**
- [pdf_quality_validator.py](file://services/pdf_quality_validator.py#L1-L668)
- [pdf_to_image.py](file://dolphin_ocr/pdf_to_image.py#L1-L283)

**Section sources**
- [pdf_quality_validator.py](file://services/pdf_quality_validator.py#L1-L668)
- [pdf_to_image.py](file://dolphin_ocr/pdf_to_image.py#L1-L283)
