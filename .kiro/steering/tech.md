# Technology Stack

## Core Framework
- **Python 3.8+** - Primary language with async/await support
- **FastAPI** - Modern web framework for API endpoints
- **Gradio** - Web UI framework for document upload interface
- **Uvicorn** - ASGI server for production deployment

## Key Libraries
- **PyMuPDF (fitz)** - Advanced PDF processing and rendering
- **python-docx** - DOCX document manipulation
- **aiohttp** - Async HTTP client for parallel translation requests
- **pydantic** - Data validation and settings management
- **spacy** - NLP processing for morphological analysis
- **psutil** - System resource monitoring

## Development Tools
- **pytest + pytest-asyncio** - Testing framework with async support
- **black** - Code formatting (88 char line length)
- **ruff** - Fast Python linter replacing flake8/isort
- **pre-commit** - Git hooks for code quality (non-blocking mode)
- **mypy** - Static type checking

## Build System
- **setuptools** - Package building via pyproject.toml
- **pip** - Dependency management via requirements.txt

## Common Commands

### Development Setup
```bash
# Install dependencies
pip install -r requirements.txt
pip install -r requirements-dev.txt

# Install pre-commit hooks
pre-commit install
```

### Running the Application
```bash
# Start development server
python app.py

# With custom host/port
HOST=0.0.0.0 PORT=8080 python app.py
```

### Testing
```bash
# Run all tests
pytest

# Run specific test file
pytest tests/test_translation_service.py

# Run with coverage
pytest --cov=services --cov=models

# Skip load tests
pytest -m "not load"
```

### Code Quality
```bash
# Format code
black .

# Lint code
ruff check .

# Fix auto-fixable issues
ruff check . --fix

# Run pre-commit on all files
pre-commit run --all-files
```

### Environment Variables
```bash
# Required
export LINGO_API_KEY="your_api_key"

# Optional performance tuning
export MAX_CONCURRENT_REQUESTS=10
export MAX_REQUESTS_PER_SECOND=5.0
export TRANSLATION_BATCH_SIZE=50
```

## Deployment
- **Modal** - Cloud deployment platform (see scripts/deploy_modal.py)
- **Docker** - Containerization support
- **Environment-based configuration** - 12-factor app principles
