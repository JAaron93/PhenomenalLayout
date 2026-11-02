/**
 * Philosophy Interface JavaScript
 * Interactive neologism detection and user choice management
 */

class PhilosophyInterface {
    constructor() {
        this.neologisms = [];
        this.userChoices = {};
        this.currentSession = null;
        this.progressTracking = {
            totalNeologisms: 0,
            processedNeologisms: 0,
            choicesMade: 0
        };
        this.websocket = null;
        this.initializeInterface();
    }

    initializeInterface() {
        // Initialize event listeners
        this.setupEventListeners();

        // Initialize WebSocket connection for real-time updates
        this.initializeWebSocket();

        // Setup drag and drop
        this.setupDragDrop();

        // Initialize terminology management
        this.initializeTerminologyManager();

        console.log('Philosophy Interface initialized');
    }

    setupEventListeners() {
        // Neologism selection events
        document.addEventListener('change', (e) => {
            if (e.target.classList.contains('neologism-choice')) {
                this.handleNeologismChoice(e.target);
            }
        });

        // Batch operation buttons
        document.getElementById('batch-preserve')?.addEventListener('click', () => {
            this.batchOperation('preserve');
        });

        document.getElementById('batch-translate')?.addEventListener('click', () => {
            this.batchOperation('translate');
        });

        document.getElementById('batch-custom')?.addEventListener('click', () => {
            this.batchOperation('custom');
        });

        // Export/Import buttons
        document.getElementById('export-choices')?.addEventListener('click', () => {
            this.exportUserChoices();
        });

        document.getElementById('import-choices')?.addEventListener('click', () => {
            this.importUserChoices();
        });

        // Settings panel
        document.getElementById('philosophy-settings')?.addEventListener('change', (e) => {
            this.updateSettings(e.target);
        });

        // Search functionality
        document.getElementById('neologism-search')?.addEventListener('input', (e) => {
            this.searchNeologisms(e.target.value);
        });

        // Confidence filter
        document.getElementById('confidence-filter')?.addEventListener('change', (e) => {
            this.filterByConfidence(e.target.value);
        });
    }

    initializeWebSocket() {
        // Initialize WebSocket for real-time progress updates
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${protocol}//${window.location.host}/ws/philosophy`;

        try {
            this.websocket = new WebSocket(wsUrl);

            this.websocket.onmessage = (event) => {
                const data = JSON.parse(event.data);
                this.handleWebSocketMessage(data);
            };

            this.websocket.onopen = () => {
                console.log('WebSocket connected');
                this.updateConnectionStatus(true);
            };

            this.websocket.onclose = () => {
                console.log('WebSocket disconnected');
                this.updateConnectionStatus(false);
                // Attempt to reconnect after 5 seconds
                setTimeout(() => this.initializeWebSocket(), 5000);
            };
        } catch (error) {
            console.warn('WebSocket not available, falling back to polling');
            this.setupPolling();
        }
    }

    setupPolling() {
        // Fallback to polling if WebSocket is not available
        setInterval(() => {
            this.pollProgress();
        }, 2000);
    }

    async pollProgress() {
        try {
            const response = await fetch('/api/philosophy/progress');
            const data = await response.json();
            this.updateProgress(data);
        } catch (error) {
            console.error('Error polling progress:', error);
        }
    }

    handleWebSocketMessage(data) {
        switch (data.type) {
            case 'neologism_detected':
                this.addNeologism(data.neologism);
                break;
            case 'progress_update':
                this.updateProgress(data.progress);
                break;
            case 'choice_conflict':
                this.handleChoiceConflict(data.conflict);
                break;
            case 'session_complete':
                this.handleSessionComplete(data.session);
                break;
            default:
                console.log('Unknown message type:', data.type);
        }
    }

    setupDragDrop() {
        // Enable drag and drop for terminology files
        const dropZone = document.getElementById('terminology-drop-zone');
        if (!dropZone) return;

        dropZone.addEventListener('dragover', (e) => {
            e.preventDefault();
            dropZone.classList.add('drag-over');
        });

        dropZone.addEventListener('dragleave', () => {
            dropZone.classList.remove('drag-over');
        });

        dropZone.addEventListener('drop', (e) => {
            e.preventDefault();
            dropZone.classList.remove('drag-over');

            const files = e.dataTransfer.files;
            if (files.length > 0) {
                this.handleTerminologyUpload(files[0]);
            }
        });
    }

    initializeTerminologyManager() {
        // Load existing terminology
        this.loadTerminology();

        // Setup terminology search
        const searchInput = document.getElementById('terminology-search');
        if (searchInput) {
            searchInput.addEventListener('input', (e) => {
                this.searchTerminology(e.target.value);
            });
        }
    }

    // Neologism Management
    addNeologism(neologism) {
        this.neologisms.push(neologism);
        this.progressTracking.totalNeologisms = this.neologisms.length;

        // Add to UI
        this.renderNeologism(neologism);

        // Update progress
        this.updateProgressDisplay();

        // Check for existing choices
        this.checkExistingChoice(neologism);
    }

    renderNeologism(neologism) {
        const container = document.getElementById('neologism-container');
        if (!container) return;

        const neologismElement = this.createNeologismElement(neologism);
        container.appendChild(neologismElement);

        // Add animation
        setTimeout(() => {
            neologismElement.classList.add('visible');
        }, 100);
    }

    createNeologismElement(neologism) {
        const div = document.createElement('div');
        div.className = 'neologism-item';
        div.setAttribute('data-term', neologism.term);
        div.setAttribute('data-confidence', neologism.confidence);

        const confidenceClass = this.getConfidenceClass(neologism.confidence);

        div.innerHTML = `
            <div class="neologism-header">
                <div class="neologism-term">
                    <span class="term-text">${neologism.term}</span>
                    <span class="confidence-badge ${confidenceClass}">
                        ${(neologism.confidence * 100).toFixed(1)}%
                    </span>
                </div>
                <div class="neologism-type">
                    <span class="type-badge">${neologism.neologism_type}</span>
                </div>
            </div>

            <div class="neologism-context">
                <div class="context-sentence">
                    <strong>Context:</strong> ${neologism.sentence_context}
                </div>
                <div class="context-details">
                    <span class="semantic-field">Field: ${neologism.philosophical_context.semantic_field}</span>
                    <span class="page-number">Page: ${neologism.page_number || 'N/A'}</span>
                </div>
            </div>

            <div class="neologism-analysis">
                <details class="analysis-details">
                    <summary>Analysis Details</summary>
                    <div class="analysis-content">
                        <div class="morphological-analysis">
                            <h4>Morphological Analysis</h4>
                            <p><strong>Compound:</strong> ${neologism.morphological_analysis.is_compound ? 'Yes' : 'No'}</p>
                            <p><strong>Parts:</strong> ${neologism.morphological_analysis.compound_parts.join(', ')}</p>
                            <p><strong>Complexity:</strong> ${(neologism.morphological_analysis.structural_complexity * 100).toFixed(1)}%</p>
                        </div>
                        <div class="philosophical-context">
                            <h4>Philosophical Context</h4>
                            <p><strong>Density:</strong> ${(neologism.philosophical_context.philosophical_density * 100).toFixed(1)}%</p>
                            <p><strong>Keywords:</strong> ${neologism.philosophical_context.philosophical_keywords.join(', ')}</p>
                        </div>
                    </div>
                </details>
            </div>

            <div class="neologism-choices">
                <div class="choice-options">
                    <label class="choice-option">
                        <input type="radio" name="choice-${neologism.term}" value="preserve" class="neologism-choice">
                        <span class="choice-label">Preserve Original</span>
                    </label>
                    <label class="choice-option">
                        <input type="radio" name="choice-${neologism.term}" value="translate" class="neologism-choice">
                        <span class="choice-label">Allow Translation</span>
                    </label>
                    <label class="choice-option">
                        <input type="radio" name="choice-${neologism.term}" value="custom" class="neologism-choice">
                        <span class="choice-label">Custom Translation</span>
                    </label>
                </div>

                <div class="custom-translation" style="display: none;">
                    <input type="text" class="custom-translation-input" placeholder="Enter custom translation...">
                    <button class="apply-custom-btn">Apply</button>
                </div>

                <div class="choice-notes">
                    <textarea class="choice-notes-input" placeholder="Notes (optional)..." rows="2"></textarea>
                </div>
            </div>
        `;

        return div;
    }

    getConfidenceClass(confidence) {
        if (confidence >= 0.8) return 'confidence-high';
        if (confidence >= 0.6) return 'confidence-medium';
        if (confidence >= 0.4) return 'confidence-low';
        return 'confidence-uncertain';
    }

    handleNeologismChoice(target) {
        const neologismItem = target.closest('.neologism-item');
        const term = neologismItem.getAttribute('data-term');
        const choice = target.value;

        // Show/hide custom translation input
        const customDiv = neologismItem.querySelector('.custom-translation');
        if (choice === 'custom') {
            customDiv.style.display = 'block';
            customDiv.querySelector('.custom-translation-input').focus();
        } else {
            customDiv.style.display = 'none';
        }

        // Store choice
        this.userChoices[term] = {
            choice: choice,
            timestamp: new Date().toISOString(),
            notes: ''
        };

        // Update progress
        this.progressTracking.choicesMade = Object.keys(this.userChoices).length;
        this.updateProgressDisplay();

        // Mark as processed
        neologismItem.classList.add('choice-made');

        // Send choice to backend
        this.sendChoiceToBackend(term, choice);
    }

    async sendChoiceToBackend(term, choice, customTranslation = '', notes = '') {
        try {
            const response = await fetch('/api/philosophy/choice', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    term: term,
                    choice: choice,
                    custom_translation: customTranslation,
                    notes: notes,
                    session_id: this.currentSession
                })
            });

            if (!response.ok) {
                throw new Error('Failed to save choice');
            }

            const result = await response.json();
            console.log('Choice saved:', result);

        } catch (error) {
            console.error('Error saving choice:', error);
            this.showNotification('Error saving choice', 'error');
        }
    }

    // Batch Operations
    batchOperation(operation) {
        const selectedNeologisms = this.getSelectedNeologisms();

        if (selectedNeologisms.length === 0) {
            this.showNotification('No neologisms selected', 'warning');
            return;
        }

        const confirmation = confirm(
            `Apply "${operation}" to ${selectedNeologisms.length} selected neologisms?`
        );

        if (!confirmation) return;

        selectedNeologisms.forEach(term => {
            this.applyChoiceToNeologism(term, operation);
        });

        this.showNotification(
            `Applied "${operation}" to ${selectedNeologisms.length} neologisms`,
            'success'
        );
    }

    getSelectedNeologisms() {
        const checkboxes = document.querySelectorAll('.neologism-select:checked');
        return Array.from(checkboxes).map(cb => cb.value);
    }

    applyChoiceToNeologism(term, choice) {
        const neologismItem = document.querySelector(`[data-term="${term}"]`);
        if (!neologismItem) return;

        const choiceInput = neologismItem.querySelector(`input[value="${choice}"]`);
        if (choiceInput) {
            choiceInput.checked = true;
            this.handleNeologismChoice(choiceInput);
        }
    }

    // Search and Filter
    searchNeologisms(searchTerm) {
        const neologisms = document.querySelectorAll('.neologism-item');
        const term = searchTerm.toLowerCase();

        neologisms.forEach(item => {
            const neologismTerm = item.getAttribute('data-term').toLowerCase();
            const context = item.querySelector('.context-sentence').textContent.toLowerCase();

            if (neologismTerm.includes(term) || context.includes(term)) {
                item.style.display = 'block';
            } else {
                item.style.display = 'none';
            }
        });
    }

    filterByConfidence(minConfidence) {
        const neologisms = document.querySelectorAll('.neologism-item');
        const threshold = parseFloat(minConfidence);

        neologisms.forEach(item => {
            const confidence = parseFloat(item.getAttribute('data-confidence'));

            if (confidence >= threshold) {
                item.style.display = 'block';
            } else {
                item.style.display = 'none';
            }
        });
    }

    // Progress Tracking
    updateProgress(progressData) {
        this.progressTracking = { ...this.progressTracking, ...progressData };
        this.updateProgressDisplay();
    }

    updateProgressDisplay() {
        const { totalNeologisms, processedNeologisms, choicesMade } = this.progressTracking;

        // Update progress bars
        this.updateProgressBar('detection-progress', processedNeologisms, totalNeologisms);
        this.updateProgressBar('choice-progress', choicesMade, totalNeologisms);

        // Update statistics
        const totalEl = document.getElementById('total-neologisms');
        const choicesEl = document.getElementById('choices-made');
        const remainingEl = document.getElementById('remaining-choices');
        if (totalEl) totalEl.textContent = totalNeologisms;
        if (choicesEl) choicesEl.textContent = choicesMade;
        if (remainingEl) remainingEl.textContent = totalNeologisms - choicesMade;

        // Update overall progress
        const overallProgress = totalNeologisms > 0 ? (choicesMade / totalNeologisms) * 100 : 0;
        this.updateProgressBar('overall-progress', overallProgress, 100);
    }

    updateProgressBar(id, current, total) {
        const progressBar = document.getElementById(id);
        if (!progressBar) return;

        const percentage = total > 0 ? (current / total) * 100 : 0;
        progressBar.style.width = `${percentage}%`;
        progressBar.setAttribute('aria-valuenow', current);
        progressBar.setAttribute('aria-valuemax', total);

        // Update text
        const progressText = progressBar.querySelector('.progress-text');
        if (progressText) {
            progressText.textContent = `${current}/${total} (${percentage.toFixed(1)}%)`;
        }
    }

    // Export/Import
    async exportUserChoices() {
        try {
            const response = await fetch('/api/philosophy/export-choices', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    session_id: this.currentSession
                })
            });

            if (!response.ok) {
                throw new Error('Export failed');
            }

            const blob = await response.blob();
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `philosophy-choices-${new Date().toISOString().split('T')[0]}.json`;
            a.click();
            window.URL.revokeObjectURL(url);

            this.showNotification('Choices exported successfully', 'success');

        } catch (error) {
            console.error('Export error:', error);
            this.showNotification('Export failed', 'error');
        }
    }

    importUserChoices() {
        const input = document.createElement('input');
        input.type = 'file';
        input.accept = '.json';

        input.onchange = (e) => {
            const file = e.target.files[0];
            if (file) {
                this.handleChoicesImport(file);
            }
        };

        input.click();
    }

    async handleChoicesImport(file) {
        try {
            const text = await file.text();
            const data = JSON.parse(text);

            const response = await fetch('/api/philosophy/import-choices', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    choices: data,
                    session_id: this.currentSession
                })
            });

            if (!response.ok) {
                throw new Error('Import failed');
            }

            const result = await response.json();
            this.showNotification(`Imported ${result.count} choices`, 'success');

            // Refresh the interface
            this.refreshNeologismList();

        } catch (error) {
            console.error('Import error:', error);
            this.showNotification('Import failed', 'error');
        }
    }

    // Terminology Management
    async loadTerminology() {
        try {
            const response = await fetch('/api/philosophy/terminology');
            const terminology = await response.json();
            this.renderTerminology(terminology);
        } catch (error) {
            console.error('Error loading terminology:', error);
        }
    }

    renderTerminology(terminology) {
        const container = document.getElementById('terminology-list');
        if (!container) return;

        container.innerHTML = '';

        Object.entries(terminology).forEach(([term, translation]) => {
            const item = document.createElement('div');
            item.className = 'terminology-item';
            item.innerHTML = `
                <div class="term-pair">
                    <span class="source-term">${term}</span>
                    <span class="arrow">→</span>
                    <span class="target-term">${translation}</span>
                </div>
                <div class="term-actions">
                    <button class="edit-term-btn" data-term="${term}">Edit</button>
                    <button class="delete-term-btn" data-term="${term}">Delete</button>
                </div>
            `;
            container.appendChild(item);
        });
    }

    searchTerminology(searchTerm) {
        const items = document.querySelectorAll('.terminology-item');
        const term = searchTerm.toLowerCase();

        items.forEach(item => {
            const termText = item.textContent.toLowerCase();
            if (termText.includes(term)) {
                item.style.display = 'block';
            } else {
                item.style.display = 'none';
            }
        });
    }

    // Utility Methods
    showNotification(message, type = 'info') {
        const notification = document.createElement('div');
        notification.className = `notification notification-${type}`;
        notification.textContent = message;

        document.body.appendChild(notification);

        setTimeout(() => {
            notification.classList.add('visible');
        }, 100);

        setTimeout(() => {
            notification.classList.remove('visible');
            setTimeout(() => {
                document.body.removeChild(notification);
            }, 300);
        }, 3000);
    }

    updateConnectionStatus(connected) {
        const statusElement = document.getElementById('connection-status');
        if (statusElement) {
            statusElement.className = connected ? 'status-connected' : 'status-disconnected';
            statusElement.textContent = connected ? 'Connected' : 'Disconnected';
        }
    }

    async refreshNeologismList() {
        try {
            const response = await fetch('/api/philosophy/neologisms');
            const neologisms = await response.json();

            // Clear existing list
            const container = document.getElementById('neologism-container');
            if (container) {
                container.innerHTML = '';
            }

            // Render new list
            neologisms.forEach(neologism => {
                this.renderNeologism(neologism);
            });

        } catch (error) {
            console.error('Error refreshing neologisms:', error);
        }
    }
}

// Initialize the interface when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    window.philosophyInterface = new PhilosophyInterface();
});

// Export for use in other modules
export default PhilosophyInterface;
