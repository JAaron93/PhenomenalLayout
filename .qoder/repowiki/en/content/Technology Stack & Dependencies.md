# Technology Stack & Dependencies

<cite>
**Referenced Files in This Document**  
- [pyproject.toml](file://pyproject.toml)
- [requirements.txt](file://requirements.txt)
- [requirements-dev.txt](file://requirements-dev.txt)
- [requirements-prod.txt](file://requirements-prod.txt)
- [app.py](file://app.py)
- [ui/gradio_interface.py](file://ui/gradio_interface.py)
- [dolphin_ocr/pdf_to_image.py](file://dolphin_ocr/pdf_to_image.py)
- [services/pdf_document_reconstructor.py](file://services/pdf_document_reconstructor.py)
- [scripts/deploy_modal.py](file://scripts/deploy_modal.py)
- [scripts/update-deps.sh](file://scripts/update-deps.sh)
- [config/settings.py](file://config/settings.py)
- [dolphin_ocr/logging_config.py](file://dolphin_ocr/logging_config.py)
</cite>

## Table of Contents
1. [Core Frameworks and Libraries](#core-frameworks-and-libraries)
2. [Dependency Categorization](#dependency-categorization)
3. [External Service Integration](#external-service-integration)
4. [Deployment and Infrastructure](#deployment-and-infrastructure)
5. [Development and Testing Tools](#development-and-testing-tools)
6. [Configuration and Environment Management](#configuration-and-environment-management)
7. [Dependency Versioning and Compatibility](#dependency-versioning-and-compatibility)
8. [Dependency Upgrade Strategy](#dependency-upgrade-strategy)

## Core Frameworks and Libraries

The PhenomenalLayout system is built on a robust technology stack that enables advanced document translation with precise layout preservation. The core dependencies provide essential functionality for API routing, user interface, document processing, data validation, and configuration management.

### FastAPI for API Routing
FastAPI serves as the primary web framework for building the API layer of PhenomenalLayout. It provides high-performance API routing with automatic OpenAPI documentation generation and Pydantic-based request/response validation. The framework is integrated with the application through the FastAPI instance in `app.py`, which includes routers from the `api.routes` module to handle various endpoints. FastAPI's asynchronous capabilities support the system's need for handling concurrent document processing requests efficiently.

**Section sources**
- [app.py](file://app.py#L1-L120)
- [api/routes.py](file://api/routes.py)

### Gradio for UI
Gradio provides the interactive user interface for PhenomenalLayout, enabling users to upload PDF documents, configure translation parameters, and download translated outputs. The UI is implemented in `ui/gradio_interface.py` and features components for file upload, language selection, progress monitoring, and result downloading. The interface integrates with the backend through synchronous wrapper functions that call the core translation services, providing real-time feedback on processing status and quality metrics.

**Section sources**
- [ui/gradio_interface.py](file://ui/gradio_interface.py#L1-L463)
- [app.py](file://app.py#L1-L120)

### pdf2image for PDF-to-Image Conversion
The pdf2image library enables the conversion of PDF documents to image formats suitable for OCR processing. This functionality is encapsulated in the `PDFToImageConverter` class within `dolphin_ocr/pdf_to_image.py`. The converter uses Poppler as a backend to render PDF pages at configurable DPI settings, with memory-efficient processing that writes temporary files rather than loading entire documents into memory. The library is essential for preparing documents for layout analysis by Dolphin OCR.

**Section sources**
- [dolphin_ocr/pdf_to_image.py](file://dolphin_ocr/pdf_to_image.py#L1-L283)
- [requirements.txt](file://requirements.txt#L1-L368)

### ReportLab for PDF Reconstruction
ReportLab is used for reconstructing translated content back into PDF format while preserving the original layout, fonts, and styling. The `PDFDocumentReconstructor` class in `services/pdf_document_reconstructor.py` leverages ReportLab's canvas and PDF generation capabilities to render translated text elements within their original bounding boxes. The system handles font selection, text wrapping, color preservation, and overflow detection to maintain document fidelity during the reconstruction process.

**Section sources**
- [services/pdf_document_reconstructor.py](file://services/pdf_document_reconstructor.py#L1-L486)
- [requirements.txt](file://requirements.txt#L1-L368)

### Pydantic for Data Validation
Pydantic provides data validation and settings management throughout the PhenomenalLayout system. It is used extensively for defining data models, validating API inputs, and managing configuration settings. The dependency is listed in `pyproject.toml` and `requirements.txt`, and its integration enables type-safe data handling across the application. Pydantic's validation capabilities ensure data integrity when processing document metadata, translation parameters, and API requests.

**Section sources**
- [pyproject.toml](file://pyproject.toml#L1-L143)
- [requirements.txt](file://requirements.txt#L1-L368)

### python-dotenv for Configuration
The python-dotenv library facilitates environment variable management by loading configuration from `.env` files into the application environment. This dependency supports the system's configuration management by allowing sensitive credentials and environment-specific settings to be stored externally from the codebase. It is particularly important for managing API keys and service endpoints used in external service integrations.

**Section sources**
- [requirements.txt](file://requirements.txt#L1-L368)

### Jinja2 for Template Rendering
Jinja2 is utilized for template rendering in the philosophy interface component of PhenomenalLayout. It enables dynamic HTML generation for the web-based user interface, allowing for the creation of responsive and interactive UI elements. The template engine is integrated with the FastAPI application to serve HTML content from the `templates` directory, supporting the philosophy-enhanced translation features of the system.

**Section sources**
- [requirements.txt](file://requirements.txt#L1-L368)
- [templates/philosophy_interface.html](file://templates/philosophy_interface.html)

## Dependency Categorization

The dependencies in PhenomenalLayout are organized into distinct categories based on their usage context and environment requirements, as defined in the various requirements files.

### Core Dependencies
Core dependencies are essential for the basic functionality of the application and are listed in `requirements.txt`. These include:
- FastAPI: Web framework for API routing
- Gradio: User interface components
- httpx: HTTP client for external service communication
- modal: Infrastructure for distributed processing
- pdf2image: PDF to image conversion
- pydantic: Data validation and settings management
- python-dotenv: Environment variable loading
- reportlab: PDF document reconstruction
- spacy: Natural language processing for text analysis

These dependencies form the foundation of the application and are required for both development and production environments.

**Section sources**
- [requirements.txt](file://requirements.txt#L1-L368)

### Development Dependencies
Development dependencies are specified in `requirements-dev.txt` and include tools for testing, linting, and type checking. These dependencies are not required for production deployment but are essential for maintaining code quality and ensuring reliable functionality during development. The development dependencies include:
- pytest: Testing framework with plugins for asyncio and coverage
- mypy: Static type checker for Python
- ruff: Code linter and formatter
- pytest-xdist: Test parallelization
- pytest-rerunfailures: Automatic test retry functionality

These tools support a robust development workflow with automated testing, code quality checks, and type safety verification.

**Section sources**
- [requirements-dev.txt](file://requirements-dev.txt#L1-L17)

### Production Dependencies
Production dependencies are defined in `requirements-prod.txt` and include all packages required for deployment in a production environment. This file contains the same core dependencies as `requirements.txt` but with cryptographic hashes for security and reproducibility. The production requirements file ensures that deployments use exactly the same package versions across different environments, preventing unexpected behavior due to dependency changes.

**Section sources**
- [requirements-prod.txt](file://requirements-prod.txt#L1-L2654)

## External Service Integration

PhenomenalLayout integrates with several external services to provide specialized functionality for document translation and layout analysis.

### Lingo.dev for Translation
The system integrates with Lingo.dev as the primary translation service, leveraging its API to convert text content between languages. This integration is facilitated through the `mcp_lingo_client.py` service, which handles authentication, request formatting, and response processing. The translation service supports the system's core functionality of converting document content while preserving contextual meaning and specialized terminology.

**Section sources**
- [services/mcp_lingo_client.py](file://services/mcp_lingo_client.py)

### Dolphin OCR for Layout Analysis
Dolphin OCR provides advanced layout analysis capabilities, detecting text regions, bounding boxes, and font characteristics within document images. The integration is implemented in the `dolphin_ocr` package, which includes services for PDF-to-image conversion, layout extraction, and confidence scoring. The OCR service enables the system to understand document structure and preserve formatting during translation.

**Section sources**
- [dolphin_ocr/layout.py](file://dolphin_ocr/layout.py)
- [services/dolphin_ocr_service.py](file://services/dolphin_ocr_service.py)

## Deployment and Infrastructure

The deployment infrastructure for PhenomenalLayout is designed for scalability and reliability, with specific tools and configurations for different deployment scenarios.

### Modal Deployment via deploy_modal.py
The system supports deployment on Modal, a cloud platform for running Python applications at scale. The `deploy_modal.py` script in the `scripts` directory contains the configuration and deployment logic for launching the application on Modal infrastructure. This deployment approach enables automatic scaling, distributed processing, and efficient resource utilization for handling large document translation workloads.

**Section sources**
- [scripts/deploy_modal.py](file://scripts/deploy_modal.py)

### Asynchronous Processing with asyncio
The application leverages Python's asyncio library for asynchronous processing of document translation tasks. This enables non-blocking I/O operations, allowing the system to handle multiple translation requests concurrently without performance degradation. The async capabilities are integrated throughout the service layer, particularly in document processing and external API communication.

**Section sources**
- [services/async_document_processor.py](file://services/async_document_processor.py)
- [services/main_document_processor.py](file://services/main_document_processor.py)

## Development and Testing Tools

The development environment for PhenomenalLayout includes comprehensive tools for testing, logging, and code quality assurance.

### Logging Configuration
The system implements structured logging through the `logging_config.py` module in the `dolphin_ocr` package. This configuration sets up file and console handlers with appropriate formatting and log levels, enabling detailed monitoring of application behavior and troubleshooting of issues. The logging system captures important events throughout the document processing pipeline.

**Section sources**
- [dolphin_ocr/logging_config.py](file://dolphin_ocr/logging_config.py)

### Testing with pytest
The test suite is built on pytest, providing a comprehensive framework for unit and integration testing. Test files are located in the `tests` directory and cover various components of the system, including API routes, document processing services, and utility functions. The testing configuration in `pytest.ini` and `pytest-service.ini` defines test discovery patterns and execution parameters.

**Section sources**
- [pytest.ini](file://pytest.ini)
- [pytest-service.ini](file://pytest-service.ini)
- [tests/](file://tests/)

## Configuration and Environment Management

The system employs a structured approach to configuration and environment management to support different deployment scenarios and user preferences.

### Configuration Files
Configuration is managed through JSON files in the `config` directory, including:
- `languages.json`: Supported language definitions
- `settings.py`: Application settings and constants
- Various JSON files for terminology and indicators

These configuration files enable customization of the system's behavior without modifying code, supporting localization and domain-specific terminology.

**Section sources**
- [config/settings.py](file://config/settings.py)
- [config/languages.json](file://config/languages.json)

### Environment Variables
Environment variables are used to configure runtime parameters such as host, port, and API endpoints. The `python-dotenv` library loads these variables from `.env` files, allowing for environment-specific configuration without code changes. This approach supports secure management of sensitive credentials and flexible deployment across different environments.

**Section sources**
- [requirements.txt](file://requirements.txt#L1-L368)
- [app.py](file://app.py#L1-L120)

## Dependency Versioning and Compatibility

The dependency management strategy for PhenomenalLayout emphasizes stability, security, and compatibility across different components.

### Version Constraints
The system specifies version constraints for all dependencies to ensure compatibility and prevent breaking changes. Core dependencies have minimum version requirements specified in `pyproject.toml`, while production deployments use pinned versions with cryptographic hashes in `requirements-prod.txt`. This approach balances the need for security updates with the stability required for production systems.

### Compatibility Considerations
The dependency versions are selected to ensure compatibility across the technology stack. For example, the versions of FastAPI, Pydantic, and Starlette are coordinated to work together seamlessly. Similarly, the PDF processing libraries (pdf2image, ReportLab, and pypdf) are versioned to avoid conflicts in document handling capabilities.

**Section sources**
- [pyproject.toml](file://pyproject.toml#L1-L143)
- [requirements.txt](file://requirements.txt#L1-L368)
- [requirements-prod.txt](file://requirements-prod.txt#L1-L2654)

## Dependency Upgrade Strategy

The system includes tools and processes for safely upgrading dependencies to incorporate security patches and new features.

### Safe Dependency Upgrades with update-deps.sh
The `update-deps.sh` script in the `scripts` directory provides a controlled mechanism for upgrading dependencies. This script likely uses pip-tools or a similar dependency management tool to resolve version conflicts and generate updated requirements files. The upgrade process follows a staged approach:
1. Update development dependencies first
2. Test changes in a development environment
3. Generate updated production requirements
4. Deploy to staging environment
5. Validate functionality before production deployment

This strategy minimizes the risk of introducing breaking changes while allowing the system to benefit from dependency updates.

**Section sources**
- [scripts/update-deps.sh](file://scripts/update-deps.sh)
