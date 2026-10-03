# Project Structure

## Directory Organization

### Core Application
```
app.py                 # Main FastAPI application entry point
api/                   # FastAPI route handlers and API endpoints
├── routes.py          # Main API routes and web interface routes
ui/                    # Gradio interface components
├── gradio_interface.py # Web UI for document upload and processing
```

### Business Logic (Services Layer)
```
services/              # Core business logic and processing services
├── translation_service.py              # Base translation service
├── enhanced_translation_service.py     # Drop-in replacement with parallel processing
├── parallel_translation_service.py     # High-performance parallel translation engine
├── advanced_pdf_processor.py           # PDF processing with image-text overlay
├── enhanced_document_processor.py      # Multi-format document handler
├── document_processor.py               # Base document processing
├── language_detector.py                # Language detection utilities
├── neologism_detector.py               # Philosophy-focused neologism detection
├── morphological_analyzer.py           # Text analysis and morphology
├── philosophical_context_analyzer.py   # Philosophy-specific processing
├── user_choice_manager.py              # User preference management
└── confidence_scorer.py                # Translation confidence scoring
```

### Data Models
```
models/                # Pydantic models and data structures
├── user_choice_models.py  # User preference and choice models
└── neologism_models.py    # Neologism detection and analysis models
```

### Core Infrastructure
```
core/                  # Core application infrastructure
├── state_manager.py   # Application state and job management
└── translation_handler.py # Translation workflow coordination
```

### Configuration
```
config/                # Configuration files and settings
├── settings.py        # Main application settings
├── main.py           # Configuration management
├── languages.json    # Supported language definitions
├── klages_terminology.json      # Philosophy terminology mappings
├── philosophical_indicators.json # Philosophy-specific indicators
└── debug_test_words.json       # Debug and test data
```

### Data Layer
```
database/              # Database and persistence layer
├── choice_database.py # User choice persistence
└── user_choices.db   # SQLite database file
```

### Utilities
```
utils/                 # Shared utility functions
├── file_handler.py    # File I/O operations
├── language_utils.py  # Language processing utilities
└── validators.py      # Input validation functions
```

### Testing
```
tests/                 # Test suite
├── test_*.py         # Unit and integration tests
└── services/         # Service-specific tests
```

### Static Assets & Templates
```
static/               # Static web assets
├── philosophy_interface.css  # Custom CSS
└── philosophy_interface.js   # Frontend JavaScript

templates/            # Jinja2 templates
└── philosophy_interface.html # Web interface template
```

### Working Directories
```
uploads/              # Temporary file uploads
downloads/            # Generated translated documents
input/                # Input document staging
output/               # Output document staging
temp/                 # Temporary processing files
logs/                 # Application logs
```

## Architecture Patterns

### Service Layer Pattern
- Services in `services/` contain all business logic
- Each service has a single responsibility
- Services are injected into route handlers
- Async/await throughout for performance

### Repository Pattern
- Database operations isolated in `database/` layer
- Models define data structures in `models/`
- Clear separation between data access and business logic

### Configuration Management
- Environment-based configuration via `.env`
- Centralized settings in `config/settings.py`
- JSON files for static configuration data

### Error Handling
- Comprehensive exception handling in services
- Graceful degradation (fallback to original text)
- Detailed logging throughout application

## File Naming Conventions
- **Snake_case** for Python files and directories
- **Descriptive names** indicating purpose (e.g., `enhanced_translation_service.py`)
- **Test files** prefixed with `test_`
- **Configuration files** use descriptive names with `.json` extensions
- **Service files** end with `_service.py` or `_processor.py`

## Import Organization
- Standard library imports first
- Third-party imports second
- Local application imports last
- Relative imports within same package preferred
- Absolute imports for cross-package dependencies

