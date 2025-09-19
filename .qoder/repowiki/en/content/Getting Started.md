# Getting Started with PhenomenalLayout

<cite>
**Referenced Files in This Document**
- [README.md](file://README.md)
- [requirements.txt](file://requirements.txt)
- [requirements-dev.txt](file://requirements-dev.txt)
- [app.py](file://app.py)
- [ui/gradio_interface.py](file://ui/gradio_interface.py)
- [config/settings.py](file://config/settings.py)
- [examples/basic_usage.py](file://examples/basic_usage.py)
- [examples/philosophy_interface_usage_example.py](file://examples/philosophy_interface_usage_example.py)
- [CONTRIBUTING.md](file://CONTRIBUTING.md)
</cite>

## Table of Contents
1. [Introduction](#introduction)
2. [Prerequisites](#prerequisites)
3. [Installation Guide](#installation-guide)
4. [Development Environment Setup](#development-environment-setup)
5. [Configuration](#configuration)
6. [Running the Application](#running-the-application)
7. [Basic Usage Examples](#basic-usage-examples)
8. [Philosophy Interface](#philosophy-interface)
9. [Troubleshooting](#troubleshooting)
10. [Best Practices](#best-practices)

## Introduction

PhenomenalLayout is an advanced layout preservation engine for document translation that orchestrates Lingo.dev's translation services with ByteDance's Dolphin OCR to achieve pixel-perfect formatting integrity during document translation. This comprehensive guide will walk you through setting up your development environment, configuring the system, and using both the basic translation interface and the advanced philosophy-enhanced features.

### Key Features

- **Layout Preservation**: Sophisticated algorithms that maintain original document formatting during translation
- **Multiple Language Support**: Supports over 20 languages with intelligent translation
- **Philosophy Mode**: Specialized interface for handling philosophical texts with neologism detection
- **Web Interface**: Modern Gradio-based user interface with real-time progress tracking
- **Parallel Processing**: High-performance translation with configurable concurrency

## Prerequisites

### System Requirements

Before installing PhenomenalLayout, ensure your system meets the following requirements:

**Python Version**: Python 3.11 or 3.12 recommended (match CI environment)
- Python 3.8–3.12 supported
- Python 3.13 support pending due to Pillow 10 wheels

**Operating System**: Compatible with macOS, Linux, and Windows

**Additional Dependencies**:
- Poppler runtime (required by pdf2image)
  - Ubuntu/Debian: `sudo apt-get update && sudo apt-get install -y poppler-utils`
  - macOS: `brew install poppler`

### Hardware Recommendations

- **Minimum RAM**: 4GB
- **Recommended RAM**: 8GB+
- **Storage**: 2GB free space for installation and temporary files
- **Network**: Stable internet connection for API calls to Lingo.dev

## Installation Guide

### Step 1: Clone the Repository

```bash
git clone https://github.com/your-repository-url.git
cd PhenomenalLayout
```

### Step 2: Create Virtual Environment

```bash
# Create virtual environment
python3 -m venv .venv

# Activate virtual environment
# On macOS/Linux:
source .venv/bin/activate

# On Windows:
.venv\Scripts\activate
```

### Step 3: Install Core Dependencies

```bash
# Upgrade pip
python -m pip install -U pip

# Install runtime dependencies
python -m pip install -r requirements.txt
```

### Step 4: Install Development Dependencies (Optional)

```bash
# Install development and testing dependencies
python -m pip install -r requirements-dev.txt
```

### Step 5: Verify Installation

```bash
# Test that all dependencies are installed correctly
python -c "import gradio, fastapi, pdf2image; print('Installation successful')"
```

**Section sources**
- [README.md](file://README.md#L1-L100)
- [requirements.txt](file://requirements.txt#L1-L50)

## Development Environment Setup

### Recommended Development Tools

For optimal development experience, install these additional tools:

```bash
# Install pre-commit hooks for automated formatting
pre-commit install

# Install linting and type checking tools
pip install ruff mypy
```

### Development Workflow

```bash
# Run tests
export GRADIO_SCHEMA_PATCH=true GRADIO_SHARE=true CI=true
pytest -q

# Run linting
ruff check .

# Run type checking
mypy .

# Format code
black .
```

### Directory Structure Verification

The application creates several required directories automatically:

- `uploads/` - Temporary storage for uploaded PDFs
- `downloads/` - Storage for translated documents
- `.layout_backups/` - Backup files for layout preservation
- `static/` - Static assets for the web interface
- `templates/` - HTML templates
- `logs/` - Application logs

**Section sources**
- [CONTRIBUTING.md](file://CONTRIBUTING.md#L1-L50)
- [app.py](file://app.py#L20-L40)

## Configuration

### Environment Variables

PhenomenalLayout uses environment variables for configuration. Create a `.env` file in the project root:

```bash
# Required: Lingo.dev API key
LINGO_API_KEY="your_lingo_api_key_here"

# Optional: Server configuration
HOST="127.0.0.1"
PORT="8000"

# Optional: Translation settings
MAX_CONCURRENT_REQUESTS=10
MAX_REQUESTS_PER_SECOND=5.0
TRANSLATION_BATCH_SIZE=50

# Optional: PDF processing settings
PDF_DPI=300
PRESERVE_IMAGES=true
MEMORY_THRESHOLD=500

# Optional: Debug mode
DEBUG=false
```

### Configuration Options

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `LINGO_API_KEY` | Your Lingo.dev API key | None | Yes |
| `HOST` | Server host address | `127.0.0.1` | No |
| `PORT` | Server port | `8000` | No |
| `PDF_DPI` | PDF rendering resolution | `300` | No |
| `PRESERVE_IMAGES` | Preserve embedded images | `true` | No |
| `MAX_CONCURRENT_REQUESTS` | Maximum concurrent requests | `10` | No |
| `MAX_REQUESTS_PER_SECOND` | Rate limit for requests | `5.0` | No |

### Settings Module

The configuration is managed through the `config/settings.py` module, which provides:

- Environment variable parsing with validation
- Default value assignment
- Directory creation and verification
- Configuration validation

**Section sources**
- [config/settings.py](file://config/settings.py#L1-L100)
- [README.md](file://README.md#L400-L500)

## Running the Application

### Starting the Web Interface

```bash
# From the project root
python app.py
```

The application will start and display:

```
INFO:     Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)
INFO:     Starting PhenomenalLayout - Advanced Layout Preservation Engine
```

### Accessing the Interface

Open your web browser and navigate to:
- **Main Interface**: `http://localhost:8000/ui`
- **Philosophy Interface**: `http://localhost:8000/philosophy`

### Command Line Options

You can customize the server settings:

```bash
# Change host and port
export HOST="0.0.0.0"
export PORT="8080"
python app.py

# Run with debug mode
export DEBUG=true
python app.py
```

### API Endpoints

The application exposes several API endpoints:

- `GET /` - Root endpoint
- `POST /api/v1/upload` - File upload
- `POST /api/v1/translate` - Translation initiation
- `GET /api/v1/status` - Translation status
- `GET /api/v1/download` - File download

**Section sources**
- [app.py](file://app.py#L80-L120)
- [ui/gradio_interface.py](file://ui/gradio_interface.py#L1-L50)

## Basic Usage Examples

### Example 1: Simple PDF Translation

Here's a basic example of how to use the translation service programmatically:

```python
import asyncio
from services.enhanced_translation_service import EnhancedTranslationService

async def translate_document():
    # Initialize the translation service
    service = EnhancedTranslationService()

    # Define the text to translate
    text = "This is a sample text that needs translation."

    # Perform translation
    result = await service.translate_text(
        text=text,
        source_lang="en",
        target_lang="de"
    )

    print(f"Translated text: {result}")

# Run the translation
asyncio.run(translate_document())
```

### Example 2: Batch Translation

```python
import asyncio
from services.parallel_translation_service import ParallelTranslationService

async def batch_translate():
    # Initialize with custom configuration
    service = ParallelTranslationService(
        api_key="your_lingo_api_key",
        config={
            "max_concurrent_requests": 5,
            "max_requests_per_second": 2.0,
            "batch_size": 25
        }
    )

    # Define a large batch of texts
    texts = ["Text " + str(i) for i in range(100)]

    # Translate the batch
    translated = await service.translate_batch_texts(
        texts=texts,
        source_lang="en",
        target_lang="de"
    )

    print(f"Translated {len(translated)} texts successfully!")

asyncio.run(batch_translate())
```

### Example 3: Using the Dolphin OCR Service

```python
import asyncio
import httpx
import json
from pathlib import Path

async def dolphin_ocr_example():
    # Service configuration
    service_url = "https://your-dolphin-service-url"
    api_key = "your_api_key"  # Optional

    # Create HTTP client
    client = httpx.AsyncClient(timeout=30.0)

    try:
        # Health check
        response = await client.get(f"{service_url}/health")
        if response.status_code == 200:
            print("✅ Service is healthy")

        # Upload and process PDF
        test_pdf = Path("sample.pdf")
        if test_pdf.exists():
            with open(test_pdf, "rb") as f:
                files = {"pdf_file": (test_pdf.name, f, "application/pdf")}

                response = await client.post(
                    f"{service_url}/",
                    files=files,
                    headers={"X-API-Key": api_key} if api_key else {}
                )

            if response.status_code == 200:
                result = response.json()
                print(f"✅ Successfully processed {len(result.get('pages', []))} pages")

    finally:
        await client.aclose()

asyncio.run(dolphin_ocr_example())
```

**Section sources**
- [examples/basic_usage.py](file://examples/basic_usage.py#L1-L114)
- [examples/philosophy_interface_usage_example.py](file://examples/philosophy_interface_usage_example.py#L1-L50)

## Philosophy Interface

### What is Philosophy Mode?

The Philosophy Interface is a specialized feature designed for translating philosophical texts with advanced neologism detection and user choice management. It's particularly useful for academic and scholarly documents containing technical philosophical terminology.

### Enabling Philosophy Mode

1. **Via Web Interface**:
   - Navigate to the main translation interface at `http://localhost:8000/ui`
   - Upload your PDF document
   - Check the "Enable Philosophy Mode (Neologism Detection)" checkbox
   - Start the translation process

2. **Via Philosophy Interface**:
   - Navigate to `http://localhost:8000/philosophy`
   - This interface appears automatically when Philosophy Mode is enabled

### Philosophy Interface Features

#### Neologism Detection
- **Real-time Detection**: Automatically identifies philosophical neologisms during translation
- **Confidence Scoring**: Provides confidence levels for detected terms
- **Semantic Analysis**: Analyzes contextual meaning and usage

#### User Choice Management
- **Preserve**: Keep original term in target language
- **Translate**: Translate the term normally
- **Custom Translation**: Provide custom translation for the term

#### Terminology Management
- **Philosophical Database**: Maintains specialized terminology for different philosophers
- **Import/Export**: Export and import terminology databases
- **Batch Operations**: Handle multiple neologisms efficiently

### Philosophy Interface Workflow

1. **Upload Document**: Upload your philosophical text
2. **Enable Philosophy Mode**: Check the philosophy checkbox
3. **Start Translation**: Begin the translation process
4. **Review Neologisms**: Access the philosophy interface to review detected terms
5. **Make Choices**: Decide how to handle each neologism
6. **Export Results**: Save your translation choices and terminology

### Philosophy API Usage

```python
from services.philosophy_enhanced_translation_service import PhilosophyEnhancedTranslationService
from services.neologism_detector import NeologismDetector
from services.user_choice_manager import UserChoiceManager

# Initialize components
neologism_detector = NeologismDetector(
    terminology_path="config/klages_terminology.json",
    philosophical_threshold=0.5
)

user_choice_manager = UserChoiceManager(
    db_path="philosophy.db",
    auto_resolve_conflicts=True
)

philosophy_service = PhilosophyEnhancedTranslationService(
    neologism_detector=neologism_detector,
    user_choice_manager=user_choice_manager,
    preserve_neologisms_by_default=True,
    neologism_confidence_threshold=0.6
)

# Translate with philosophy enhancements
result = await philosophy_service.translate_text_with_neologism_handling(
    text="Your philosophical text here",
    source_lang="de",
    target_lang="en",
    session_id="your_session_id"
)
```

**Section sources**
- [examples/philosophy_interface_usage_example.py](file://examples/philosophy_interface_usage_example.py#L1-L100)
- [ui/gradio_interface.py](file://ui/gradio_interface.py#L200-L250)

## Troubleshooting

### Common Setup Issues

#### Issue 1: Missing Poppler Dependencies

**Problem**: `ModuleNotFoundError: No module named 'pdf2image'` or PDF processing fails

**Solution**:
```bash
# macOS
brew install poppler

# Ubuntu/Debian
sudo apt-get update && sudo apt-get install -y poppler-utils

# Verify installation
pdftoppm --version
pdfinfo --version
```

#### Issue 2: Port Already in Use

**Problem**: `OSError: [Errno 48] Address already in use`

**Solution**:
```bash
# Check what's using the port
lsof -i :8000  # macOS/Linux
netstat -ano | findstr :8000  # Windows

# Kill the process or change port
export PORT=8080
python app.py
```

#### Issue 3: Lingo API Key Not Found

**Problem**: Translation fails with API key errors

**Solution**:
```bash
# Set the environment variable
export LINGO_API_KEY="your_actual_api_key_here"

# Verify it's set correctly
echo $LINGO_API_KEY
```

#### Issue 4: Memory Issues with Large Documents

**Problem**: Out of memory errors during processing

**Solution**:
```bash
# Reduce memory usage
export MEMORY_THRESHOLD=250  # Lower from default 500MB
export PDF_DPI=150           # Lower resolution
```

### Debug Mode

Enable debug mode for detailed logging:

```bash
export DEBUG=true
export LOG_LEVEL=DEBUG
python app.py
```

### Performance Optimization

For large document processing:

```bash
# Increase concurrency (be careful with API limits)
export MAX_CONCURRENT_REQUESTS=15
export MAX_REQUESTS_PER_SECOND=8.0

# Larger batch sizes
export TRANSLATION_BATCH_SIZE=100
```

### Log Analysis

Check application logs for troubleshooting:

```bash
# View recent logs
tail -f logs/app.log

# Look for specific error patterns
grep -i error logs/app.log
grep -i exception logs/app.log
```

**Section sources**
- [config/settings.py](file://config/settings.py#L400-L500)
- [README.md](file://README.md#L700-L800)

## Best Practices

### Development Workflow

1. **Always use virtual environments**:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```

2. **Follow code quality standards**:
   ```bash
   # Run pre-commit hooks
   pre-commit run --all-files

   # Run comprehensive tests
   pytest -q

   # Check type hints
   mypy .
   ```

3. **Use appropriate configuration for different environments**:
   - Development: Lower concurrency, verbose logging
   - Production: Higher concurrency, optimized settings

### Translation Quality

1. **Test with multiple languages**:
   - German → English (longer translations)
   - English → Chinese (different character density)
   - Technical → Technical (specialized vocabulary)

2. **Monitor quality metrics**:
   - OCR confidence scores
   - Layout preservation scores
   - Translation accuracy

3. **Use philosophy mode for academic texts**:
   - Enable neologism detection
   - Review philosophical terminology
   - Save custom translations

### Performance Considerations

1. **Optimize for your use case**:
   ```bash
   # For quick prototyping
   export MAX_CONCURRENT_REQUESTS=2
   export MAX_REQUESTS_PER_SECOND=1.0

   # For production use
   export MAX_CONCURRENT_REQUESTS=10
   export MAX_REQUESTS_PER_SECOND=5.0
   ```

2. **Monitor resource usage**:
   - Memory consumption for large documents
   - Network usage for API calls
   - Disk space for temporary files

3. **Implement proper error handling**:
   ```python
   try:
       result = await service.translate_text(text, source, target)
   except Exception as e:
       logger.error(f"Translation failed: {e}")
       # Implement fallback strategy
   ```

### Security Best Practices

1. **Protect API keys**:
   - Never commit API keys to version control
   - Use environment variables
   - Rotate keys regularly

2. **Validate inputs**:
   - Check file types before processing
   - Validate language codes
   - Sanitize user inputs

3. **Secure configuration**:
   ```bash
   # Use strong secret keys in production
   export SECRET_KEY=$(openssl rand -hex 32)

   # Disable debug mode in production
   export DEBUG=false
   ```

### Testing Strategy

1. **Unit testing**: Test individual components
2. **Integration testing**: Test complete workflows
3. **Performance testing**: Test with large documents
4. **UI testing**: Test web interface functionality

```bash
# Run focused tests
pytest -q -m "not slow"

# Run with coverage
pytest --cov=services --cov-report=html

# Test philosophy features
pytest tests/test_philosophy_enhanced_integration.py
```

**Section sources**
- [CONTRIBUTING.md](file://CONTRIBUTING.md#L50-L150)
- [README.md](file://README.md#L600-L700)
