/**
 * M1 Automation System - Main JavaScript
 */

// Global App Namespace
const App = {
    state: {
        eventSource: null,
        selectedM1File: null,
        aiValidationStatus: {
            isRunning: false,
            progress: 0,
            currentRecord: 0,
            totalRecords: 0,
            currentOperation: '',
            errors: [],
            warnings: [],
            results: null
        }
    },

    // Toast Notification System
    ui: {
        showToast: function (message, type = 'info') {
            // Create container if it doesn't exist
            let container = document.getElementById('toastContainer');
            if (!container) {
                container = document.createElement('div');
                container.id = 'toastContainer';
                container.className = 'toast-container';
                document.body.appendChild(container);
            }

            // Create toast element
            const toast = document.createElement('div');
            toast.className = `toast ${type}`;

            // Icon based on type
            let icon = 'info-circle';
            if (type === 'success') icon = 'check-circle';
            if (type === 'error') icon = 'exclamation-circle';
            if (type === 'warning') icon = 'exclamation-triangle';

            // Title based on type
            const title = type.charAt(0).toUpperCase() + type.slice(1);

            toast.innerHTML = `
                <div class="toast-icon"><i class="fas fa-${icon}"></i></div>
                <div class="toast-content">
                    <div class="toast-title">${title}</div>
                    <div class="toast-message">${message}</div>
                </div>
                <button class="toast-close" onclick="this.parentElement.remove()">&times;</button>
            `;

            // Add to container
            container.appendChild(toast);

            // Auto remove after 5 seconds
            setTimeout(() => {
                toast.style.animation = 'fadeOut 0.5s ease forwards';
                setTimeout(() => {
                    if (toast.parentElement) {
                        toast.remove();
                    }
                }, 500);
            }, 5000);
        },

        addLogEntry: function (log) {
            const logBox = document.getElementById('logBox');
            if (!logBox) return;

            const entry = document.createElement('div');
            entry.className = `log-entry ${log.level}`;

            const timestamp = new Date(log.timestamp).toLocaleTimeString();
            entry.innerHTML = `
                <span class="log-timestamp">[${timestamp}]</span>
                <span>${log.message}</span>
            `;

            logBox.appendChild(entry);
            logBox.scrollTop = logBox.scrollHeight;
        },

        addValidationFeedEntry: function (message, type = 'info') {
            const feed = document.getElementById('validationFeed');
            if (!feed) return;

            const entry = document.createElement('div');
            entry.className = `feed-entry ${type}`;

            const timestamp = new Date().toLocaleTimeString();
            entry.innerHTML = `
                <span class="feed-timestamp">[${timestamp}]</span>
                <span>${message}</span>
            `;

            feed.appendChild(entry);
            feed.scrollTop = feed.scrollHeight;
        },

        updateStatus: function (data) {
            const progressBar = document.getElementById('progressBar');
            const systemStatus = document.querySelector('.system-status');

            if (data.status === 'error') {
                systemStatus.style.background = 'rgba(239, 68, 68, 0.1)';
                systemStatus.style.borderColor = 'rgba(239, 68, 68, 0.2)';
                systemStatus.style.color = '#ef4444';
                systemStatus.innerHTML = '<i class="fas fa-exclamation-circle"></i> Error Occurred';
            } else if (data.status === 'idle') {
                systemStatus.style.background = 'rgba(16, 185, 129, 0.1)';
                systemStatus.style.borderColor = 'rgba(16, 185, 129, 0.2)';
                systemStatus.style.color = '#10b981';
                systemStatus.innerHTML = '<i class="fas fa-check-circle"></i> System Ready';
            } else if (data.status === 'completed') {
                systemStatus.style.background = 'rgba(16, 185, 129, 0.1)';
                systemStatus.style.borderColor = 'rgba(16, 185, 129, 0.2)';
                systemStatus.style.color = '#10b981';
                systemStatus.innerHTML = '<i class="fas fa-check-double"></i> All Tasks Completed';
            } else {
                systemStatus.style.background = 'rgba(59, 130, 246, 0.1)';
                systemStatus.style.borderColor = 'rgba(59, 130, 246, 0.2)';
                systemStatus.style.color = '#3b82f6';

                const statusMap = {
                    'checking_email': '<i class="fas fa-envelope"></i> Checking Email',
                    'downloading': '<i class="fas fa-download"></i> Downloading Data',
                    'fme_processing': '<i class="fas fa-cogs"></i> Processing with FME',
                    'pozi_processing': '<i class="fas fa-chart-line"></i> Running Pozi Connect',
                    'ai_validation': '<i class="fas fa-robot"></i> AI Validation Running'
                };
                systemStatus.innerHTML = statusMap[data.status] || `<i class="fas fa-sync fa-spin"></i> ${data.status.replace(/_/g, ' ')}`;
            }

            const progress = data.progress || 0;
            progressBar.style.width = progress + '%';
            progressBar.textContent = progress + '%';

            if (data.current_step) {
                document.getElementById('currentStep').textContent = data.current_step;
            }

            // Update buttons state
            const downloadBtns = [document.getElementById('downloadBtn'), document.getElementById('downloadBtn2')];
            const fmeBtns = [document.getElementById('fmeBtn'), document.getElementById('fmeBtn2')];
            const poziBtns = [document.getElementById('poziBtn'), document.getElementById('poziBtn2')];
            const aiBtns = [document.getElementById('aiValidateBtn'), document.getElementById('aiValidationBtn')];
            const aiReportBtns = [document.getElementById('aiReportBtn'), document.getElementById('viewReportBtn')];

            downloadBtns.forEach(btn => { if (btn) btn.disabled = !data.download_available });
            fmeBtns.forEach(btn => { if (btn) btn.disabled = !data.fme_ready });
            poziBtns.forEach(btn => { if (btn) btn.disabled = !data.pozi_ready });
            aiBtns.forEach(btn => { if (btn) btn.disabled = !data.ai_validation_ready });
            aiReportBtns.forEach(btn => { if (btn) btn.disabled = !data.ai_validation_completed });

            if (data.download_info && data.download_info.available) {
                const emailDate = new Date(data.download_info.email_date);
                const emailStatus = document.getElementById('emailStatus');
                if (emailStatus) {
                    emailStatus.innerHTML = `<div class="info-badge success">✓ Data available from ${emailDate.toLocaleString()}</div>`;
                }
            }
        }
    },

    api: {
        checkEmail: async function () {
            try {
                const response = await fetch('/api/email/check', { method: 'POST' });
                const data = await response.json();

                if (data.success && data.new_data) {
                    App.ui.showToast('New data available! ' + data.message, 'success');
                } else if (data.success) {
                    App.ui.showToast(data.message, 'info');
                }
            } catch (error) {
                App.ui.showToast('Error checking email: ' + error.message, 'error');
            }
        },

        downloadData: async function () {
            if (!confirm('Start downloading and extracting data?')) return;

            try {
                const response = await fetch('/api/download', { method: 'POST' });
                const data = await response.json();

                if (data.success) {
                    App.ui.showToast('Download started! Check the log for progress.', 'success');
                }
            } catch (error) {
                App.ui.showToast('Error starting download: ' + error.message, 'error');
            }
        },

        runFME: async function () {
            if (!confirm('Start FME processing? This may take 10-15 minutes.')) return;

            try {
                const response = await fetch('/api/fme/run', { method: 'POST' });
                const data = await response.json();

                if (data.success) {
                    App.ui.showToast('FME processing started! Check the log for progress.', 'success');
                }
            } catch (error) {
                App.ui.showToast('Error starting FME: ' + error.message, 'error');
            }
        },

        runPozi: async function () {
            if (!confirm('Start Pozi Connect tasks? This may take up to 60 minutes.')) return;

            try {
                const response = await fetch('/api/pozi/run', { method: 'POST' });
                const data = await response.json();

                if (data.success) {
                    App.ui.showToast('Pozi Connect tasks started! Check the log for progress.', 'success');
                }
            } catch (error) {
                App.ui.showToast('Error starting Pozi: ' + error.message, 'error');
            }
        },

        runCompleteWorkflow: async function () {
            if (!confirm('Run the complete workflow?\n\nThis will:\n1. Check for new emails\n2. Download and extract data\n3. Run FME processing\n4. Run Pozi Connect tasks\n5. AI Validation\n\nTotal time: 60-90 minutes')) return;

            try {
                const response = await fetch('/api/run-all', { method: 'POST' });
                const data = await response.json();

                if (data.success) {
                    App.ui.showToast('Complete workflow started! Monitor progress in the log.', 'success');
                }
            } catch (error) {
                App.ui.showToast('Error starting workflow: ' + error.message, 'error');
            }
        }
    },

    init: function () {
        // Connect Log Stream
        this.connectLogStream();

        // Start Status Polling
        this.updateStatus();
        setInterval(() => this.updateStatus(), 2000);

        // Load Logo
        this.loadLogo();
    },

    connectLogStream: function () {
        this.state.eventSource = new EventSource('/api/logs/stream');

        this.state.eventSource.onmessage = function (event) {
            try {
                const log = JSON.parse(event.data);
                App.ui.addLogEntry(log);
            } catch (e) {
                console.error('Error parsing log:', e);
            }
        };

        this.state.eventSource.onerror = function () {
            console.log('Log stream connection lost, reconnecting...');
            setTimeout(() => App.connectLogStream(), 5000);
        };
    },

    updateStatus: function () {
        fetch('/api/status')
            .then(response => response.json())
            .then(data => {
                App.ui.updateStatus(data);
            })
            .catch(err => console.error('Status check failed', err));
    },

    loadLogo: function () {
        const logoContainer = document.querySelector('.logo-container');
        const placeholder = document.querySelector('.logo-placeholder');

        if (!logoContainer) return;

        const img = new Image();
        img.onload = function () {
            if (placeholder) placeholder.style.display = 'none';
            const logoImg = document.createElement('img');
            logoImg.src = '/static/logo.png';
            logoImg.alt = 'Logo';
            logoImg.style.maxWidth = '100%';
            logoImg.style.maxHeight = '100%';
            logoImg.style.objectFit = 'contain';
            logoContainer.insertBefore(logoImg, placeholder);
        };
        img.onerror = function () {
            console.log('Logo not found, using placeholder emoji');
        };
        img.src = '/static/logo.png';
    }
};

// Global functions for HTML onclick handlers (backward compatibility)
// These map to the App namespace functions
window.checkEmail = App.api.checkEmail;
window.downloadData = App.api.downloadData;
window.runFME = App.api.runFME;
window.runPozi = App.api.runPozi;
window.runCompleteWorkflow = App.api.runCompleteWorkflow;

// Settings Modal Functions
window.openSettings = function () {
    const overlay = document.getElementById('settingsOverlay');
    const modal = document.getElementById('settingsModal');

    if (!overlay || !modal) return;

    overlay.style.display = 'flex';
    // Force reflow
    void overlay.offsetWidth;

    overlay.classList.add('active');
    modal.classList.add('active');

    loadCurrentSettings();
};

window.closeSettings = function () {
    const overlay = document.getElementById('settingsOverlay');
    const modal = document.getElementById('settingsModal');

    if (!overlay || !modal) return;

    overlay.classList.remove('active');
    modal.classList.remove('active');

    setTimeout(() => {
        overlay.style.display = 'none';
    }, 300);
};

async function loadCurrentSettings() {
    try {
        const response = await fetch('/api/settings');
        const settings = await response.json();

        document.getElementById('fmePath').value = settings.fme?.executable_path || '';
        document.getElementById('emailUsername').value = settings.email?.username || '';
        document.getElementById('logDir').value = settings.paths?.log_directory || '';
        document.getElementById('downloadDir').value = settings.paths?.download_directory || '';
        document.getElementById('extractDir').value = settings.paths?.extract_directory || '';
    } catch (error) {
        console.error('Error loading settings:', error);
        App.ui.showToast('Error loading settings', 'error');
    }
}

window.saveSettings = async function () {
    const settings = {
        fme: { executable_path: document.getElementById('fmePath').value },
        email: {
            username: document.getElementById('emailUsername').value,
            password: document.getElementById('emailPassword').value
        },
        paths: {
            log_directory: document.getElementById('logDir').value,
            download_directory: document.getElementById('downloadDir').value,
            extract_directory: document.getElementById('extractDir').value
        }
    };

    try {
        const response = await fetch('/api/settings', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(settings)
        });

        if (response.ok) {
            App.ui.showToast('Settings saved successfully', 'success');
            closeSettings();
        } else {
            App.ui.showToast('Error saving settings', 'error');
        }
    } catch (error) {
        console.error('Error saving settings:', error);
        App.ui.showToast('Error saving settings: ' + error.message, 'error');
    }
};

window.testFMEConnection = async function () {
    const path = document.getElementById('fmePath').value;
    try {
        const response = await fetch('/api/test/fme', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ path })
        });

        if (response.ok) {
            App.ui.showToast('FME connection successful!', 'success');
        } else {
            App.ui.showToast('FME connection failed', 'error');
        }
    } catch (error) {
        App.ui.showToast('Error testing FME connection', 'error');
    }
};

window.testEmailConnection = async function () {
    const username = document.getElementById('emailUsername').value;
    const password = document.getElementById('emailPassword').value;

    try {
        const response = await fetch('/api/test/email', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username, password })
        });

        if (response.ok) {
            App.ui.showToast('Email connection successful!', 'success');
        } else {
            App.ui.showToast('Email connection failed', 'error');
        }
    } catch (error) {
        App.ui.showToast('Error testing email connection', 'error');
    }
};

window.resetPaths = async function () {
    try {
        const response = await fetch('/api/settings/default-paths');
        const defaults = await response.json();

        document.getElementById('logDir').value = defaults.log_directory || '';
        document.getElementById('downloadDir').value = defaults.download_directory || '';
        document.getElementById('extractDir').value = defaults.extract_directory || '';
        App.ui.showToast('Paths reset to defaults', 'info');
    } catch (error) {
        console.error('Error resetting paths:', error);
        App.ui.showToast('Error resetting to default paths', 'error');
    }
};

// AI Validation Functions
window.runAIValidation = async function () {
    if (App.state.aiValidationStatus.isRunning) {
        App.ui.showToast('AI validation is already running!', 'warning');
        return;
    }

    const autoValidate = confirm('Validate the latest M1 file automatically?\n\nClick OK for auto-validation or Cancel to choose a file.');

    if (autoValidate) {
        await validateLatestFile();
    } else {
        showM1FileSelectionModal();
    }
};

async function validateLatestFile() {
    try {
        const response = await fetch('/api/m1-files/list');
        if (!response.ok) throw new Error(`Failed to fetch M1 files: ${response.status}`);

        const data = await response.json();

        if (data.latest_file) {
            App.state.selectedM1File = data.latest_file;
            const fileName = data.latest_file.split(/[/\\]/).pop();
            App.ui.addValidationFeedEntry(`🚀 Starting AI validation for: ${fileName}`, 'info');
            App.state.aiValidationStatus.isRunning = true;
            showAISections();
            await startValidationWithSelectedFile();
        } else if (data.files && data.files.length > 0) {
            App.state.selectedM1File = data.files[0].path;
            const fileName = App.state.selectedM1File.split(/[/\\]/).pop();
            App.ui.addValidationFeedEntry(`🚀 Starting AI validation for: ${fileName}`, 'info');
            App.state.aiValidationStatus.isRunning = true;
            showAISections();
            await startValidationWithSelectedFile();
        } else {
            App.ui.showToast('No M1 files found. Please check the POZI output directory.', 'warning');
        }
    } catch (error) {
        console.error('Error loading latest file:', error);
        App.ui.showToast('Error loading latest M1 file: ' + error.message, 'error');
        App.state.aiValidationStatus.isRunning = false;
    }
}

window.showM1FileSelectionModal = async function () {
    let modal = document.getElementById('m1FileSelectionModal');
    if (!modal) {
        modal = document.createElement('div');
        modal.id = 'm1FileSelectionModal';
        modal.className = 'modal-overlay';
        modal.innerHTML = `
            <div class="settings-modal" style="max-width: 600px;">
                <h2>
                    Select M1 File to Validate
                    <button class="close-modal" onclick="closeM1FileSelectionModal()">&times;</button>
                </h2>
                <div style="padding: 20px;">
                    <div style="margin-bottom: 12px;">
                        <label style="display:block; margin-bottom:5px; font-weight:bold;">📂 List M1 files from a folder (e.g. a previous run):</label>
                        <div style="display:flex; gap:8px;">
                            <input type="text" id="m1DirectoryPath" placeholder="Paste a folder path containing M1 CSV files"
                                   style="flex:1; padding:8px; border:1px solid #ddd; border-radius:4px;">
                            <button class="button" onclick="listM1FilesFromDirectory()">List</button>
                        </div>
                    </div>
                    <div id="m1FilesList" style="max-height: 400px; overflow-y: auto;">
                        <div class="loading">Loading available M1 files...</div>
                    </div>
                    <div style="margin-top: 15px; padding-top: 15px; border-top: 1px solid #ddd;">
                        <label style="display: block; margin-bottom: 5px; font-weight: bold;">Or enter file path manually:</label>
                        <input type="text" id="manualFilePath" placeholder="Enter full path to M1 CSV file" 
                               style="width: 100%; padding: 8px; margin-bottom: 10px; border: 1px solid #ddd; border-radius: 4px;">
                    </div>
                    <div class="settings-actions">
                        <button class="button secondary" onclick="closeM1FileSelectionModal()">Cancel</button>
                        <button class="button" onclick="startValidationWithSelectedFile()">Start Validation</button>
                    </div>
                </div>
            </div>
        `;
        document.body.appendChild(modal);

        modal.addEventListener('click', function (e) {
            if (e.target === modal) closeM1FileSelectionModal();
        });
    }

    modal.style.display = 'flex';
    // Activate BOTH the overlay and the inner box. The .settings-modal box
    // starts at opacity:0 and only becomes visible with its own .active class
    // — without this the page just dims with an invisible modal.
    setTimeout(() => {
        modal.classList.add('active');
        const box = modal.querySelector('.settings-modal');
        if (box) box.classList.add('active');
    }, 10);
    App.state.selectedM1File = null;
    const dirInput = document.getElementById('m1DirectoryPath');
    if (dirInput) dirInput.value = '';
    await loadM1FilesList();
};

// Fetch + render the M1 file list. With no `directory`, lists the default
// discovery locations (POZI output etc.) and auto-selects the latest. With a
// `directory`, lists M1 CSVs found under that folder (a previous run) and
// makes no auto-selection.
window.loadM1FilesList = async function (directory) {
    const filesList = document.getElementById('m1FilesList');
    if (filesList) filesList.innerHTML = '<div class="loading">Loading available M1 files...</div>';
    try {
        const url = directory
            ? `/api/m1-files/list?directory=${encodeURIComponent(directory)}`
            : '/api/m1-files/list';
        const response = await fetch(url);
        const data = await response.json();

        if (data.error) {
            filesList.innerHTML = `<div style="padding: 20px; text-align: center; color: #dc3545;">${data.error}</div>`;
            return;
        }

        // Only auto-select the latest on the default (non-directory) listing.
        if (!directory && data.latest_file) {
            App.state.selectedM1File = data.latest_file;
            const manualInput = document.getElementById('manualFilePath');
            if (manualInput) manualInput.value = data.latest_file;
        }

        if (data.files && data.files.length > 0) {
            filesList.innerHTML = data.files.map((file, index) => {
                const modifiedDate = new Date(file.modified * 1000).toLocaleString();
                const isLatest = file.is_latest || (index === 0 && data.latest_file === file.path);
                const latestBadge = isLatest ? '<span style="background: #10b981; color: white; padding: 2px 8px; border-radius: 12px; font-size: 0.75em; margin-left: 8px; font-weight: bold;">LATEST</span>' : '';
                const itemStyle = isLatest ? 'padding: 10px; border: 2px solid #10b981; margin-bottom: 8px; cursor: pointer; border-radius: 4px; background: #f0fdf4;' : 'padding: 10px; border: 1px solid #ddd; margin-bottom: 8px; cursor: pointer; border-radius: 4px;';

                return `
                    <div class="file-item ${isLatest ? 'latest-file' : ''}" onclick="selectM1File('${file.path.replace(/'/g, "\\'")}', this)"
                         style="${itemStyle}">
                        <div style="font-weight: bold; display: flex; align-items: center;">
                            ${file.filename}${latestBadge}
                        </div>
                        <div style="font-size: 0.85em; color: #666; margin-top: 4px;">
                            ${file.display_path}
                        </div>
                        <div style="font-size: 0.8em; color: #999; margin-top: 4px;">
                            Modified: ${modifiedDate}
                        </div>
                    </div>
                `;
            }).join('');
        } else {
            filesList.innerHTML = '<div style="padding: 20px; text-align: center; color: #999;">No M1 files found here. Enter a file path manually.</div>';
        }
    } catch (error) {
        filesList.innerHTML =
            `<div style="padding: 20px; text-align: center; color: #dc3545;">Error loading files: ${error.message}</div>`;
    }
};

// Re-list using the folder path the user typed (previous-run directory).
window.listM1FilesFromDirectory = async function () {
    const dirInput = document.getElementById('m1DirectoryPath');
    const dir = dirInput ? dirInput.value.trim() : '';
    if (!dir) { App.ui.showToast('Enter a folder path first', 'warning'); return; }
    App.state.selectedM1File = null;
    await loadM1FilesList(dir);
};

// Standalone entry point: validate an existing/previous M1 file WITHOUT
// running the full Email->Download->FME->Pozi workflow. Opens the same
// selection modal directly (the workflow-gated button stays as-is).
window.validateExistingM1 = function () {
    if (App.state.aiValidationStatus && App.state.aiValidationStatus.isRunning) {
        App.ui.showToast('AI validation is already running!', 'warning');
        return;
    }
    showM1FileSelectionModal();
};

window.selectM1File = function (filePath, element) {
    document.querySelectorAll('.file-item').forEach(item => {
        item.style.background = '';
        item.style.borderColor = '#ddd';
    });

    element.style.background = '#e3f2fd';
    element.style.borderColor = '#2196F3';
    App.state.selectedM1File = filePath;
    document.getElementById('manualFilePath').value = filePath;
};

window.closeM1FileSelectionModal = function () {
    const modal = document.getElementById('m1FileSelectionModal');
    if (modal) {
        const box = modal.querySelector('.settings-modal');
        if (box) box.classList.remove('active');
        modal.classList.remove('active');
        setTimeout(() => modal.style.display = 'none', 300);
    }
    App.state.selectedM1File = null;
};

window.startValidationWithSelectedFile = async function () {
    const manualInput = document.getElementById('manualFilePath');
    let filePath = App.state.selectedM1File || (manualInput ? manualInput.value.trim() : null);

    if (!filePath) {
        App.ui.showToast('Please select a file or enter a file path', 'warning');
        return;
    }

    closeM1FileSelectionModal();

    const fileName = filePath.split(/[/\\]/).pop();
    App.ui.addValidationFeedEntry('🚀 Starting AI validation for: ' + fileName, 'info');
    App.state.aiValidationStatus.isRunning = true;
    showAISections();

    try {
        const response = await fetch('/api/validate-m1', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                file_path: filePath,
                validator_type: 'openai'
            })
        });

        const data = await response.json();

        if (response.status === 202 || data.status === 'started' || data.message) {
            App.state.aiValidationStatus.isRunning = true;
            showAISections();
            startValidationMonitoring();
            App.ui.addValidationFeedEntry('✅ Validation request accepted! Monitoring progress...', 'success');
            App.ui.showToast('Validation started', 'success');
        } else if (data.error) {
            App.state.aiValidationStatus.isRunning = false;
            App.ui.showToast('Error starting AI validation: ' + data.error, 'error');
            App.ui.addValidationFeedEntry('❌ Validation failed: ' + data.error, 'error');
        } else {
            App.state.aiValidationStatus.isRunning = true;
            showAISections();
            startValidationMonitoring();
            App.ui.addValidationFeedEntry('⚠️ Validation request sent - status unknown, monitoring...', 'warning');
        }
    } catch (error) {
        App.state.aiValidationStatus.isRunning = false;
        App.ui.showToast('Error starting AI validation: ' + error.message, 'error');
        App.ui.addValidationFeedEntry('❌ Network error: ' + error.message, 'error');
    }
};

function showAISections() {
    document.getElementById('aiInsightsSection').style.display = 'block';
    document.getElementById('liveValidationSection').style.display = 'block';
}

function startValidationMonitoring() {
    const interval = setInterval(async () => {
        try {
            const response = await fetch('/api/validation-status');
            const status = await response.json();

            App.state.aiValidationStatus = status;
            updateAIStatus(status);

            if (!status.is_running) {
                clearInterval(interval);
                if (status.results) {
                    updateAIMetrics(status.results);
                    App.ui.addValidationFeedEntry('AI validation completed successfully!', 'success');
                    App.ui.showToast('AI Validation Completed', 'success');
                }
            }
        } catch (error) {
            console.error('Error monitoring validation:', error);
        }
    }, 2000);
}

function updateAIStatus(status) {
    const statusElement = document.getElementById('aiValidationStatus');
    const progressBar = document.getElementById('progressBar');
    const currentStep = document.getElementById('currentStep');

    if (status.is_running) {
        statusElement.innerHTML = `
            <div class="ai-validation-status processing">
                <i class="fas fa-robot"></i>
                <span>${status.current_operation} (${status.current_record}/${status.total_records})</span>
            </div>
        `;

        const progress = status.total_records > 0 ? (status.current_record / status.total_records) * 100 : 0;
        progressBar.style.width = progress + '%';
        progressBar.textContent = Math.round(progress) + '%';
        currentStep.textContent = `AI Validation: ${status.current_operation}`;

        App.ui.addValidationFeedEntry(`Processing record ${status.current_record}/${status.total_records}: ${status.current_operation}`, 'info');
    } else if (status.results) {
        statusElement.innerHTML = `
            <div class="ai-validation-status success">
                <i class="fas fa-check-circle"></i>
                <span>Validation completed successfully!</span>
            </div>
        `;
        currentStep.textContent = 'AI Validation completed';
    }
}

function updateAIMetrics(results) {
    if (results.summary) {
        document.getElementById('validationRate').textContent = results.summary.validation_rate || '--';
        document.getElementById('fieldMappingRate').textContent = results.summary.field_mapping_rate || '--';
        document.getElementById('autoFixesApplied').textContent = results.summary.auto_fixes_applied || '--';
        document.getElementById('commonErrors').textContent = results.summary.common_errors || '--';
    }
}

window.viewAIReport = async function () {
    try {
        const response = await fetch('/api/validation-results');
        const results = await response.json();

        if (results) {
            const reportWindow = window.open('', '_blank', 'width=800,height=600');
            reportWindow.document.write(`
                <html>
                    <head><title>AI Validation Report</title></head>
                    <body>
                        <h1>AI M1 Validation Report</h1>
                        <pre>${JSON.stringify(results, null, 2)}</pre>
                    </body>
                </html>
            `);
        } else {
            App.ui.showToast('No validation results available', 'info');
        }
    } catch (error) {
        App.ui.showToast('Error loading AI report: ' + error.message, 'error');
    }
};

window.viewDetailedReport = function () {
    viewAIReport();
};

window.exportAIReport = async function () {
    try {
        const response = await fetch('/api/export-report', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                report_data: App.state.aiValidationStatus.results,
                format: 'json'
            })
        });

        if (response.ok) {
            const blob = await response.blob();
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = 'ai_validation_report.json';
            a.click();
            window.URL.revokeObjectURL(url);
            App.ui.showToast('Report exported successfully', 'success');
        } else {
            App.ui.showToast('Error exporting report', 'error');
        }
    } catch (error) {
        App.ui.showToast('Error exporting report: ' + error.message, 'error');
    }
};

window.pauseValidation = function () {
    App.ui.addValidationFeedEntry('Validation paused by user', 'warning');
    App.ui.showToast('Validation paused', 'warning');
};

window.resumeValidation = function () {
    App.ui.addValidationFeedEntry('Validation resumed', 'info');
    App.ui.showToast('Validation resumed', 'info');
};

window.clearValidationFeed = function () {
    document.getElementById('validationFeed').innerHTML = `
        <div class="feed-entry">
            <span class="feed-timestamp">[System]</span>
            <span>Validation feed cleared</span>
        </div>
    `;
};

// Preview Functions
window.switchTab = function (tabName) {
    document.querySelectorAll('.preview-section').forEach(section => section.classList.remove('active'));
    document.querySelectorAll('.tab-btn').forEach(btn => btn.classList.remove('active'));

    if (tabName === 'pozi') {
        document.getElementById('poziPreview').classList.add('active');
        document.getElementById('poziTab').classList.add('active');
    } else if (tabName === 'validation') {
        document.getElementById('validationPreview').classList.add('active');
        document.getElementById('validationTab').classList.add('active');
    }
};

window.toggleFullscreen = function () {
    const container = document.querySelector('.preview-container');
    container.classList.toggle('fullscreen');
};

window.toggleSideBySide = function () {
    const container = document.querySelector('.container');
    container.classList.toggle('side-by-side');
};

window.refreshPreview = function () {
    // Implementation for refresh
    App.ui.showToast('Refreshing preview...', 'info');
};

// Initialize App
window.addEventListener('load', function () {
    App.init();
});
