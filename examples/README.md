# Neologism Detection Engine Examples

This directory contains examples demonstrating the use of the Neologism Detection Engine for philosophy-focused translation.

## Files

- `neologism_integration_example.py` - Complete integration example showing how to use the neologism detector with translation services
- `translation_results.json` - Sample output from the integration example (generated when running the example)

## Running the Examples

### Prerequisites

1. Install the project (choose one):
   - **Editable package installation (recommended):**
     ```bash
     pip install -e .
     ```

   - **Editable installation with development tools:**
     ```bash
     pip install -e ".[dev]"
     ```
     This installs pre-configured test tools and linters (Black, Ruff, pytest)
     alongside the main package, avoiding the need for separate requirements-dev.txt
     installation and reducing version skew between dependencies.

   - **Direct dependency installation:**
     ```bash
     pip install -r requirements.txt
     ```

2. Optionally, install spaCy German model for better linguistic analysis:
   ```bash
   python -m spacy download de_core_news_sm
   ```

3. Set up environment variables for translation services:
   ```bash
   export LINGO_API_KEY=your_lingo_api_key
   ```

### Running the Integration Example

```bash
cd examples
python neologism_integration_example.py
```

This will:
1. Initialize the Philosophy-Enhanced Translator
2. Analyze sample German philosophical text for neologisms
3. Translate the text while preserving detected neologisms
4. Generate translation suggestions for philosophical terms
5. Display comprehensive analysis results
6. Export results to JSON format

## Example Output

The integration example processes a sample text from Ludwig Klages' philosophy and demonstrates:

### Neologism Detection
- **Wirklichkeitsbewusstsein** (Reality-consciousness) - Compound neologism with high confidence
- **Bewusstseinsphilosophie** (Consciousness-philosophy) - Philosophical compound term
- **Lebensweltthematik** (Life-world thematics) - Complex philosophical concept
- **Zeitlichkeitsanalyse** (Temporality analysis) - Technical philosophical term

### Translation Enhancement
- Preservation of philosophical neologisms in translation
- Morphological breakdown of compound terms
- Contextual suggestions based on semantic field analysis
- Confidence scoring for translation decisions

### Analysis Results
- Philosophical density measurement
- Semantic field identification
- Morphological complexity analysis
- Performance metrics and caching statistics

## Key Features Demonstrated

1. **Morphological Analysis**: Detection and analysis of German compound words
2. **Context Awareness**: Identification of philosophical density and semantic fields
3. **Confidence Scoring**: Multi-factor confidence calculation for neologism detection
4. **Translation Integration**: Seamless integration with existing translation services
5. **Performance Optimization**: Caching and efficient processing for large documents

## Use Cases

This example demonstrates the system's capability to handle:
- Large philosophical texts (2,000+ pages)
- Complex German compound terminology
- Philosophy-specific translation requirements
- Academic and scholarly translation needs
- Preservation of author-specific terminology

## Configuration Options

The `PhilosophyEnhancedTranslator` class accepts several configuration options:

- `terminology_path`: Path to custom terminology JSON file
- `min_confidence`: Minimum confidence threshold for neologism detection (default: 0.6)
- `preserve_neologisms`: Whether to preserve detected neologisms in translation (default: True)
- `spacy_model`: spaCy model to use for linguistic analysis (default: "de_core_news_sm")
- `philosophical_threshold`: Minimum philosophical density for detection (default: 0.3)

## Performance Considerations

The system is optimized for:
- **Memory Efficiency**: Text chunking for large documents
- **Processing Speed**: LRU caching for morphological analysis
- **Scalability**: Batch processing capabilities
- **Error Handling**: Graceful fallback when spaCy models are unavailable

## Integration with Existing Systems

The neologism detector integrates seamlessly with:
- Lingo.dev translation service with parallel processing
- Document processing pipeline
- Language detection system
- Terminology management system

## Extending the System

To extend the system for other philosophical traditions or languages:

1. **Add New Terminology**: Update `config/klages_terminology.json` or create new terminology files
2. **Customize Indicators**: Modify philosophical indicators in the detector
3. **Add Language Support**: Extend morphological patterns for other languages
4. **Enhance Context Analysis**: Add domain-specific context analysis rules

## Testing

Run the comprehensive test suite:
```bash
pytest tests/test_neologism_detector.py -v
```

This includes tests for:
- Core detection algorithms
- Morphological analysis
- Confidence scoring
- Performance characteristics
- Error handling
- Integration scenarios
