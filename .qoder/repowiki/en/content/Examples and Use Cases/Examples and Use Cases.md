# Examples and Use Cases

<cite>
**Referenced Files in This Document**  
- [basic_usage.py](file://examples/basic_usage.py)
- [parallel_translation_demo.py](file://examples/parallel_translation_demo.py)
- [philosophy_enhanced_usage_examples.py](file://examples/philosophy_enhanced_usage_examples.py)
- [cache_metrics_demo.py](file://examples/cache_metrics_demo.py)
- [user_choice_integration_example.py](file://examples/user_choice_integration_example.py)
- [database_enhancements_example.py](file://examples/database_enhancements_example.py)
- [lazy_loading_performance_example.py](file://examples/lazy_loading_performance_example.py)
- [performance_optimization_examples.py](file://examples/performance_optimization_examples.py)
- [web_eval_demo.py](file://examples/web_eval_demo.py)
</cite>

## Table of Contents
1. [Basic Usage Example](#basic-usage-example)
2. [Parallel Translation Demonstration](#parallel-translation-demonstration)
3. [Philosophy-Enhanced Usage Examples](#philosophy-enhanced-usage-examples)
4. [Cache Metrics and Performance Monitoring](#cache-metrics-and-performance-monitoring)
5. [User Choice Integration](#user-choice-integration)
6. [Database Enhancements for Choice Persistence](#database-enhancements-for-choice-persistence)
7. [Performance Optimization with Lazy Loading](#performance-optimization-with-lazy-loading)
8. [Translation Quality Evaluation](#translation-quality-evaluation)
9. [Best Practices and Implementation Patterns](#best-practices-and-implementation-patterns)

## Basic Usage Example

The `basic_usage.py` example demonstrates fundamental interaction with the Dolphin OCR Modal service through HTTP requests. It provides a practical walkthrough of service initialization, health checking, and document processing workflows. The script implements environment variable validation for service URL configuration, ensuring robust error handling when required variables are missing or improperly set.

Key implementation patterns include asynchronous HTTP client usage with httpx for non-blocking operations, structured error handling for various HTTP status codes (401 for authentication failures, 429 for rate limiting), and proper resource cleanup with client closure. The example shows how to upload a PDF document to the OCR service and save the resulting JSON output with timestamped filenames.

The workflow follows a clear sequence: health check → service information retrieval → document processing → result persistence. This pattern serves as a foundation for more complex integrations, demonstrating proper separation of concerns and progressive enhancement of functionality.

**Section sources**
- [basic_usage.py](file://examples/basic_usage.py#L1-L113)

## Parallel Translation Demonstration

The `parallel_translation_demo.py` example showcases the system's capability for high-performance processing of large documents through parallel translation. It demonstrates two primary use cases: basic parallel translation of text batches and large document processing with performance metrics tracking.

The implementation uses the `EnhancedTranslationService` with configurable `ParallelTranslationConfig` parameters including `max_concurrent_requests`, `max_requests_per_second`, and `batch_size`. These settings allow fine-tuning of resource utilization based on system capabilities and API rate limits. The example includes a `ProgressTracker` utility that provides real-time feedback on processing progress, items per second, and elapsed time.

For performance demonstration, the script creates synthetic text batches by modifying base philosophical texts with variant identifiers. This approach allows testing of translation consistency across similar content. The example estimates performance improvements by comparing actual processing time against theoretical sequential processing time, providing concrete metrics on the benefits of parallelization.

**Section sources**
- [parallel_translation_demo.py](file://examples/parallel_translation_demo.py#L1-L199)

## Philosophy-Enhanced Usage Examples

The `philosophy_enhanced_usage_examples.py` file provides comprehensive demonstrations of philosophy-focused translation capabilities. It showcases the integration of neologism detection with translation services, user choice management, and progress tracking for complex philosophical texts.

The example suite includes four primary demonstrations: basic text translation with neologism detection, batch translation of multiple philosophical concepts, user choice management for specific terms, and progress tracking during translation operations. The implementation uses the `PhilosophyEnhancedTranslationService` to handle specialized philosophical terminology like "Dasein", "Sein-zum-Tode", and "Zuhandenheit" with appropriate preservation strategies.

User choice management is demonstrated through the `UserChoiceManager` system, allowing users to specify how specific neologisms should be handled (preserve, translate, or custom translation). The example shows session-based choice persistence, where translation decisions for terms like "Dasein" can be preserved as "being-there" while "Angst" is translated as "Anxiety" according to user preferences.

Progress tracking is implemented through callback functions that monitor various stages of the translation pipeline, including text processing, neologism detection, user choice application, and final translation. This provides transparency into the processing workflow and enables monitoring of long-running operations.

**Section sources**
- [philosophy_enhanced_usage_examples.py](file://examples/philosophy_enhanced_usage_examples.py#L1-L199)

## Cache Metrics and Performance Monitoring

The `cache_metrics_demo.py` example demonstrates the system's metrics collection and connection tracking capabilities. It showcases a comprehensive monitoring framework for cache performance and resource utilization, which is critical for optimizing large-scale document processing.

The implementation features a decorator-based instrumentation system (`instrument_cache`) that tracks cache hits and misses without modifying the core logic of cached functions. This approach uses closure-based caching to maintain state while allowing the decorator to monitor access patterns. The example demonstrates both synchronous and asynchronous connection tracking using context managers (`track_connection` and `track_async_connection`).

Key metrics collected include cache hit rate, active connection count, and detailed cache statistics. The demo shows how these metrics can be accessed programmatically and displayed in real-time during operations. The example includes both synchronous and asynchronous demonstrations, reflecting the system's support for different concurrency models.

The metrics system is designed to be thread-safe using locking mechanisms, ensuring accurate measurements in multi-threaded environments. It also includes periodic counter reset functionality to prevent unbounded growth of metrics data, making it suitable for long-running services.

**Section sources**
- [cache_metrics_demo.py](file://examples/cache_metrics_demo.py#L1-L194)

## User Choice Integration

The `user_choice_integration_example.py` provides a detailed walkthrough of the User Choice Management System integration with neologism detection. This example demonstrates how to create persistent user preferences for translation choices and apply them consistently across documents.

The implementation shows the complete workflow: environment setup, session creation, neologism analysis, choice making, and session completion. It uses a temporary database for demonstration purposes, with automatic cleanup on program exit. The example creates a `UserChoiceManager` instance connected to a SQLite database for persistent storage of translation preferences.

Key features demonstrated include different choice scopes (global, contextual, document-specific), confidence level tracking, and user notes for documentation. The example shows how choices for terms like "Dasein" can be set to translate as "being-there" with global scope, while other terms like "Seinsvergessenheit" are translated as "forgetfulness-of-being" with contextual scope.

The system supports conflict resolution strategies and maintains consistency scores for translation sessions. The example demonstrates how previously made choices can be reused in new documents, enabling consistent terminology across related philosophical works. This is particularly valuable for academic translation projects where terminological consistency is crucial.

**Section sources**
- [user_choice_integration_example.py](file://examples/user_choice_integration_example.py#L1-L199)

## Database Enhancements for Choice Persistence

The `database_enhancements_example.py` demonstrates three critical database enhancements that improve the reliability and performance of the choice persistence system. These enhancements address configuration flexibility, international character support, and bulk data operations.

The first enhancement demonstrates configurable learning rate parameters (alpha) for the choice database, allowing adjustment of how quickly success rates are updated based on new evidence. This enables fine-tuning of the adaptive learning system based on translation quality feedback.

The second enhancement focuses on JSON encoding configuration for international characters. It shows how the database can be configured to either preserve Unicode characters directly or escape them as ASCII sequences. This flexibility is important for compatibility with different downstream systems and storage constraints.

The third enhancement demonstrates high-performance batch import optimization. The example generates a large dataset of 2,000 test choices to showcase the efficiency of bulk operations. This capability is essential for initializing the system with existing terminology databases or migrating preferences from other systems.

**Section sources**
- [database_enhancements_example.py](file://examples/database_enhancements_example.py#L1-L199)

## Performance Optimization with Lazy Loading

The `lazy_loading_performance_example.py` demonstrates the performance benefits of lazy loading in the NeologismDetector system. This optimization is crucial for applications that need to instantiate the translation system quickly without incurring the full initialization cost upfront.

The example measures and compares memory usage and instantiation time between eager and lazy loading approaches. It shows that lazy loading reduces initial memory consumption from approximately 150 MB to a minimal footprint, with resources loaded only when needed. The script includes sophisticated memory measurement using psutil to provide accurate performance metrics.

Key lazy loading triggers demonstrated include the spaCy NLP model, terminology database, and philosophical indicators. Each component is loaded only when first accessed, allowing the system to remain lightweight until actual processing begins. The example shows the timing of each lazy loading operation, providing insights into the cost distribution of system initialization.

The implementation includes configurable memory estimates through environment variables and command-line arguments, allowing adaptation to different deployment environments. This flexibility ensures that performance expectations can be calibrated based on specific hardware and software configurations.

**Section sources**
- [lazy_loading_performance_example.py](file://examples/lazy_loading_performance_example.py#L1-L199)

## Translation Quality Evaluation

The `web_eval_demo.py` example (referenced in the project structure) demonstrates translation quality evaluation capabilities, though the specific implementation details are not available in the provided context. Based on the naming convention and directory structure, this example likely provides a web-based interface for evaluating and comparing translation outputs.

Such evaluation systems typically include side-by-side comparison of source and translated text, quality scoring mechanisms, and annotation tools for identifying issues. They may incorporate automated metrics like BLEU scores alongside human evaluation components. The static assets in the `static/demos/web-eval` directory suggest a web interface with CSS styling and HTML structure for presenting evaluation results.

Quality evaluation is a critical component of the translation workflow, enabling continuous improvement of the system through feedback loops. By analyzing translation errors and user preferences, the system can adapt its behavior and improve future outputs.

**Section sources**
- [web_eval_demo.py](file://examples/web_eval_demo.py)

## Best Practices and Implementation Patterns

Based on the examples, several best practices emerge for implementing and extending the system:

1. **Environment Configuration**: Always validate required environment variables before proceeding with operations, providing clear error messages when configuration is missing.

2. **Resource Management**: Use context managers and proper cleanup mechanisms (like atexit registration) to ensure resources are properly released.

3. **Performance Monitoring**: Implement comprehensive metrics collection for cache performance, connection tracking, and processing speed to identify bottlenecks.

4. **Error Handling**: Provide detailed error messages and graceful degradation when components are unavailable (e.g., spaCy models).

5. **Configuration Flexibility**: Support multiple configuration methods (environment variables, command-line arguments, defaults) to accommodate different deployment scenarios.

6. **Testing and Validation**: Include comprehensive test coverage and validation scripts to ensure system reliability.

7. **Documentation**: Maintain clear documentation of configuration options, expected behavior, and integration patterns.

8. **Scalability**: Design systems to handle large documents through chunking, batching, and parallel processing.

These patterns ensure that implementations are robust, maintainable, and performant in real-world scenarios.

**Section sources**
- [basic_usage.py](file://examples/basic_usage.py#L1-L113)
- [parallel_translation_demo.py](file://examples/parallel_translation_demo.py#L1-L199)
- [philosophy_enhanced_usage_examples.py](file://examples/philosophy_enhanced_usage_examples.py#L1-L199)
- [performance_optimization_examples.py](file://examples/performance_optimization_examples.py#L1-L199)
