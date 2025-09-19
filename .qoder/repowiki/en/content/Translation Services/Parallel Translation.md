# Parallel Translation

<cite>
**Referenced Files in This Document**  
- [services/parallel_translation_service.py](file://services/parallel_translation_service.py)
- [examples/parallel_translation_demo.py](file://examples/parallel_translation_demo.py)
- [tests/test_parallel_translation.py](file://tests/test_parallel_translation.py)
- [services/enhanced_translation_service.py](file://services/enhanced_translation_service.py)
</cite>

## Table of Contents
1. [Introduction](#introduction)
2. [Core Components](#core-components)
3. [Architecture Overview](#architecture-overview)
4. [Detailed Component Analysis](#detailed-component-analysis)
5. [Concurrency and Rate Limiting](#concurrency-and-rate-limiting)
6. [Error Handling and Retry Mechanisms](#error-handling-and-retry-mechanisms)
7. [Batch Processing and Progress Tracking](#batch-processing-and-progress-tracking)
8. [Document Translation Workflow](#document-translation-workflow)
9. [Performance Optimization and Configuration](#performance-optimization-and-configuration)
10. [Integration and Usage Patterns](#integration-and-usage-patterns)
11. [Conclusion](#conclusion)

## Introduction
The Parallel Translation service provides high-performance batch processing capabilities for document translation with bounded concurrency and rate limiting. This system enables efficient processing of large volumes of text by leveraging asynchronous programming patterns while maintaining strict control over API usage and resource consumption. The service is designed to handle complex document structures, preserve input order, and provide robust error handling for production environments.

**Section sources**
- [services/parallel_translation_service.py](file://services/parallel_translation_service.py#L1-L50)

## Core Components
The Parallel Translation service consists of several key components that work together to enable high-performance batch processing. The core classes include ParallelLingoTranslator for managing translation operations, RateLimiter for controlling request throughput, and various dataclasses for structuring translation tasks and results. The system uses asyncio for concurrency control and aiohttp for efficient HTTP communication with translation APIs.

**Section sources**
- [services/parallel_translation_service.py](file://services/parallel_translation_service.py#L150-L200)

## Architecture Overview

```mermaid
graph TD
A[Client Application] --> B[ParallelTranslationService]
B --> C[ParallelLingoTranslator]
C --> D[RateLimiter]
C --> E[Semaphore]
C --> F[HTTP Session]
D --> G[Token Bucket Algorithm]
E --> H[Bounded Concurrency]
F --> I[Lingo API]
C --> J[TranslationTask]
C --> K[TranslationResult]
C --> L[BatchProgress]
```

**Diagram sources**
- [services/parallel_translation_service.py](file://services/parallel_translation_service.py#L150-L300)

## Detailed Component Analysis

### ParallelLingoTranslator Analysis
The ParallelLingoTranslator class serves as the primary interface for parallel translation operations. It manages HTTP sessions, enforces rate limiting, and coordinates concurrent requests through a combination of asyncio primitives. The translator uses an async context manager pattern to ensure proper resource cleanup and provides multiple methods for different translation scenarios.

#### For Object-Oriented Components:
```mermaid
classDiagram
class ParallelLingoTranslator {
+str api_key
+str base_url
+ParallelTranslationConfig config
+RateLimiter rate_limiter
+Semaphore semaphore
+-ClientSession _session
+__aenter__() ClientSession
+__aexit__() None
+close() None
+_ensure_session() ClientSession
+_translate_single_with_retry(task) TranslationResult
+translate_batch_parallel(tasks, callback) list[TranslationResult]
+translate_texts_parallel(texts, langs, callback) list[str]
+translate_document_parallel(content, langs, callback) dict
}
class ParallelTranslationService {
+str api_key
+ParallelTranslationConfig config
+-ParallelLingoTranslator _translator
+__aenter__() ParallelTranslationService
+__aexit__() None
+translate_large_document(content, langs, callback) dict
+translate_batch_texts(texts, langs, callback) list[str]
}
ParallelTranslationService --> ParallelLingoTranslator : "uses"
```

**Diagram sources**
- [services/parallel_translation_service.py](file://services/parallel_translation_service.py#L300-L500)

### Translation Data Structures
The service uses dataclasses to structure translation tasks and results, providing type safety and clear interfaces. The TranslationTask class encapsulates individual translation units with metadata, while TranslationResult captures the outcome of each translation attempt.

#### For Object-Oriented Components:
```mermaid
classDiagram
class TranslationTask {
+str text
+str source_lang
+str target_lang
+str task_id
+dict[str, Any] metadata
}
class TranslationResult {
+str task_id
+str original_text
+str translated_text
+bool success
+Optional[str] error
+int retry_count
+float processing_time
+dict[str, Any] metadata
}
class BatchProgress {
+int total_tasks
+int completed_tasks
+int failed_tasks
+float start_time
+progress_percentage() float
+elapsed_time() float
+estimated_remaining_time() float
}
class ParallelTranslationConfig {
+int max_concurrent_requests
+float max_requests_per_second
+int batch_size
+int max_retries
+float retry_delay
+float backoff_multiplier
+float request_timeout
+float total_timeout
+float rate_limit_window
+int burst_allowance
+from_config() ParallelTranslationConfig
}
```

**Diagram sources**
- [services/parallel_translation_service.py](file://services/parallel_translation_service.py#L100-L150)

## Concurrency and Rate Limiting

### Token-Bucket RateLimiter Implementation
The RateLimiter class implements a token-bucket algorithm to control request throughput and prevent API rate limit violations. This approach allows for smooth request distribution while accommodating short bursts of activity within defined limits.

```mermaid
flowchart TD
Start([Request Received]) --> CheckTokens["Check Available Tokens"]
CheckTokens --> TokensAvailable{"Tokens >= 1?"}
TokensAvailable --> |Yes| ConsumeToken["Consume One Token"]
TokensAvailable --> |No| CalculateWait["Calculate Wait Time"]
CalculateWait --> Wait["Wait Required Duration"]
Wait --> RefillTokens["Refill Tokens Based on Time"]
RefillTokens --> ConsumeToken
ConsumeToken --> AllowRequest["Allow Request"]
AllowRequest --> End([Request Processed])
subgraph "Token Refill Logic"
direction LR
TimeElapsed["Time Elapsed"] --> TokenAccumulation["Tokens += Elapsed * Rate"]
TokenAccumulation --> MaxTokens["Min(Tokens, Max + Burst)"]
end
```

**Diagram sources**
- [services/parallel_translation_service.py](file://services/parallel_translation_service.py#L250-L300)

### Bounded Concurrency with Semaphore
The service uses asyncio.Semaphore to limit the number of concurrent requests, preventing resource exhaustion and ensuring stable performance. This mechanism works in conjunction with the RateLimiter to provide multi-layered control over request throughput.

```mermaid
sequenceDiagram
participant Client
participant Translator
participant Semaphore
participant API
Client->>Translator : Request Translation
Translator->>Semaphore : acquire()
alt Semaphore Available
Semaphore-->>Translator : Permit Acquired
Translator->>API : Send Request
API-->>Translator : Receive Response
Translator->>Semaphore : release()
Translator-->>Client : Return Result
else Semaphore Full
Semaphore->>Translator : Wait for Permit
Translator->>Semaphore : acquire() [Blocks]
Semaphore-->>Translator : Permit Available
Translator->>API : Send Request
API-->>Translator : Receive Response
Translator->>Semaphore : release()
Translator-->>Client : Return Result
end
```

**Diagram sources**
- [services/parallel_translation_service.py](file://services/parallel_translation_service.py#L300-L350)

## Error Handling and Retry Mechanisms

### Exponential Backoff Retry Strategy
The service implements a robust retry mechanism with exponential backoff to handle transient errors and rate limiting responses. This approach increases the delay between retries to avoid overwhelming the API during periods of high load.

```mermaid
flowchart TD
Start([Translation Attempt]) --> APIRequest["Send API Request"]
APIRequest --> ResponseReceived["Response Received"]
ResponseReceived --> IsSuccess{"Status 200?"}
IsSuccess --> |Yes| SuccessPath["Return Success Result"]
IsSuccess --> |No| IsRetryable{"Retryable Error?"}
IsRetryable --> |No| FailurePath["Return Failure Result"]
IsRetryable --> |Yes| RetryCount{"Max Retries<br>Exceeded?"}
RetryCount --> |Yes| FailurePath
RetryCount --> |No| CalculateDelay["Calculate Delay:<br>base * multiplier^attempt"]
CalculateDelay --> Wait["Wait Delay Period"]
Wait --> APIRequest
SuccessPath --> End([Complete])
FailurePath --> End
```

**Diagram sources**
- [services/parallel_translation_service.py](file://services/parallel_translation_service.py#L500-L600)

### Retry-After Header Parsing
The service includes specialized logic for parsing Retry-After headers from API responses, allowing it to respect server-specified rate limit windows. This ensures compliance with API provider requirements and minimizes unnecessary retry attempts.

```mermaid
sequenceDiagram
participant Client
participant Translator
participant API
Client->>Translator : Request Translation
Translator->>API : POST /translate
API-->>Translator : 429 Too Many Requests
API-->>Translator : Retry-After : 5
Translator->>Translator : _parse_retry_after()
Translator->>Translator : Parse Header Value
alt Numeric Value
Translator->>Translator : Use as Seconds
else HTTP Date
Translator->>Translator : Convert to Seconds
end
Translator->>Translator : Cap at MAX_RETRY_AFTER
Translator->>Translator : Sleep Calculated Duration
Translator->>API : Retry Request
API-->>Translator : 200 OK
Translator-->>Client : Return Result
```

**Diagram sources**
- [services/parallel_translation_service.py](file://services/parallel_translation_service.py#L400-L450)

## Batch Processing and Progress Tracking

### translate_batch_parallel Method
The translate_batch_parallel method enables concurrent execution of multiple translation tasks while preserving the original input order. It uses asyncio.gather to coordinate parallel execution and includes comprehensive progress tracking capabilities.

```mermaid
sequenceDiagram
participant Client
participant Translator
participant Task
participant Progress
Client->>Translator : translate_batch_parallel(tasks)
Translator->>Progress : Initialize BatchProgress
Translator->>Translator : Create progress_lock
loop For Each Task
Translator->>Task : translate_with_progress()
Task->>Translator : _translate_single_with_retry()
Translator->>Progress : Update completed/failed count
Progress->>Client : progress_callback() if provided
end
Translator->>Translator : asyncio.gather(all tasks)
Translator->>Translator : Handle exceptions
Translator-->>Client : Return results in original order
```

**Diagram sources**
- [services/parallel_translation_service.py](file://services/parallel_translation_service.py#L600-L650)

### Progress Tracking System
The BatchProgress class provides real-time monitoring of translation batch operations, including completion percentage, elapsed time, and estimated remaining time. This enables responsive user interfaces and operational monitoring.

```mermaid
classDiagram
class BatchProgress {
+int total_tasks
+int completed_tasks
+int failed_tasks
+float start_time
+progress_percentage() float
+elapsed_time() float
+estimated_remaining_time() float
}
class ParallelLingoTranslator {
+translate_batch_parallel(tasks, callback) list[TranslationResult]
}
class ProgressTracker {
+update_progress(current, total) None
}
ParallelLingoTranslator --> BatchProgress : "creates"
ParallelLingoTranslator --> ProgressTracker : "callback"
ProgressTracker --> BatchProgress : "receives updates"
```

**Diagram sources**
- [services/parallel_translation_service.py](file://services/parallel_translation_service.py#L200-L250)

## Document Translation Workflow

### translate_document_parallel Implementation
The translate_document_parallel method extracts text blocks from structured document content, translates them in parallel, and reassembles the results while preserving the original document structure.

```mermaid
flowchart TD
Start([Document Input]) --> ExtractBlocks["Extract Text Blocks<br>_extract_text_blocks()"]
ExtractBlocks --> CreateTasks["Create TranslationTasks<br>with block IDs"]
CreateTasks --> TranslateBatch["translate_batch_parallel()"]
TranslateBatch --> ApplyResults["Apply Translations<br>_apply_translations_to_content()"]
ApplyResults --> ReconstructDoc["Reconstruct Document<br>with Translated Text"]
ReconstructDoc --> End([Translated Document])
subgraph "Text Block Extraction"
direction LR
Pages["content['pages']"] --> PageBlocks["Extract page blocks"]
Layouts["content['layouts']"] --> LayoutBlocks["Extract layout text"]
end
subgraph "Result Application"
direction LR
Results["TranslationResult[]"] --> Mapping["Create ID → Text Map"]
Mapping --> Pages["Update page blocks"]
Mapping --> Layouts["Update layout text"]
end
```

**Diagram sources**
- [services/parallel_translation_service.py](file://services/parallel_translation_service.py#L700-L750)

## Performance Optimization and Configuration

### ParallelTranslationConfig Options
The service provides extensive configuration options for tuning performance characteristics, including concurrency limits, rate limiting parameters, retry behavior, and timeout settings. These can be set via environment variables or direct instantiation.

```mermaid
erDiagram
PARALLEL_TRANSLATION_CONFIG {
int max_concurrent_requests
float max_requests_per_second
int batch_size
int max_retries
float retry_delay
float backoff_multiplier
float request_timeout
float total_timeout
float rate_limit_window
int burst_allowance
}
CONFIG_SOURCE {
string ENVIRONMENT_VARIABLES
string CODE_INSTANTIATION
}
CONFIG_SOURCE ||--o{ PARALLEL_TRANSLATION_CONFIG : "sets"
ENVIRONMENT_VARIABLES {
string MAX_CONCURRENT_REQUESTS
string MAX_REQUESTS_PER_SECOND
string TRANSLATION_BATCH_SIZE
string TRANSLATION_MAX_RETRIES
string TRANSLATION_RETRY_DELAY
string TRANSLATION_BACKOFF_MULTIPLIER
string TRANSLATION_REQUEST_TIMEOUT
string TRANSLATION_TOTAL_TIMEOUT
string TRANSLATION_RATE_LIMIT_WINDOW
string TRANSLATION_BURST_ALLOWANCE
}
PARALLEL_TRANSLATION_CONFIG }o--|| ENVIRONMENT_VARIABLES : "maps to"
```

**Diagram sources**
- [services/parallel_translation_service.py](file://services/parallel_translation_service.py#L50-L100)

## Integration and Usage Patterns

### EnhancedTranslationService Integration
The EnhancedTranslationService class integrates parallel translation capabilities into the existing translation workflow, automatically selecting between parallel and sequential processing based on document size.

```mermaid
flowchart TD
Start([translate_document_enhanced]) --> AnalyzeSize["Analyze Text Block Count"]
AnalyzeSize --> ShouldUseParallel{"Text Count >= Threshold?"}
ShouldUseParallel --> |Yes| UseParallel["Use _translate_document_parallel()"]
ShouldUseParallel --> |No| UseSequential["Use super().translate_document()"]
UseParallel --> UpdateStats["Update performance_stats"]
UseSequential --> UpdateStats
UpdateStats --> ReturnResult["Return Translated Document"]
subgraph "Performance Tracking"
direction LR
Stats["performance_stats"] --> Metrics["total_requests, parallel_requests,<br>sequential_requests, processing_time"]
end
```

**Diagram sources**
- [services/enhanced_translation_service.py](file://services/enhanced_translation_service.py#L50-L150)

## Conclusion
The Parallel Translation service provides a comprehensive solution for high-performance batch translation with robust error handling, rate limiting, and progress tracking. By combining asyncio.Semaphore for bounded concurrency and a token-bucket RateLimiter for request smoothing, the system achieves optimal throughput while respecting API limitations. The service's modular design, with clear separation of concerns between translation tasks, results, and progress tracking, makes it both powerful and accessible to developers of varying experience levels. Through its integration with the EnhancedTranslationService, it seamlessly enhances existing translation workflows with parallel processing capabilities when beneficial, providing automatic performance optimization based on document size.
