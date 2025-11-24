// Function to load all system events for the Bill Audit tab
async function loadAllSystemEvents() {
    const timeline = document.getElementById('allEventsTimeline');
    if (!timeline) return;
    
    timeline.innerHTML = '<div style="text-align: center; color: #6b7280;">Loading all system events...</div>';
    
    try {
        // Fetch the audit trail data
        const response = await fetch('/api/netsuite/bills/audit-trail');
        const data = await response.json();
        
        if (!data.success || !data.events || data.events.length === 0) {
            timeline.innerHTML = '<div style="color: #6b7280;">No events found</div>';
            return;
        }
        
        // Create timeline HTML
        let html = '<div style="font-family: monospace; font-size: 12px;">';
        
        data.events.forEach(event => {
            const direction = event.direction === 'inbound' ? '← NetSuite → System' : '→ System → NetSuite';
            const status = event.status === 'SUCCESS' ? '✅' : '❌';
            
            html += `
                <div style="margin-bottom: 20px; padding: 15px; border: 1px solid #ddd; border-radius: 5px; background: white;">
                    <div style="display: flex; justify-content: space-between; margin-bottom: 10px;">
                        <strong>${direction}</strong>
                        <span>${status} ${event.status}</span>
                    </div>
                    <div style="color: #666; margin-bottom: 5px;">
                        📅 ${event.timestamp} | Type: ${event.type}
                    </div>
                    <div style="margin-bottom: 5px;">
                        Invoice: ${event.invoice_id || 'N/A'} | Vendor: ${event.vendor_name || 'N/A'}
                    </div>
                    ${event.amount ? `<div>Amount: $${event.amount}</div>` : ''}
                    ${event.error_message ? `<div style="color: red;">Error: ${event.error_message}</div>` : ''}
                    ${event.request_payload ? `<details style="margin-top: 10px;">
                        <summary>Request Data</summary>
                        <pre style="background: #f5f5f5; padding: 10px; overflow-x: auto; max-height: 200px;">${JSON.stringify(event.request_payload, null, 2)}</pre>
                    </details>` : ''}
                    ${event.response_payload ? `<details style="margin-top: 10px;">
                        <summary>Response Data</summary>
                        <pre style="background: #f5f5f5; padding: 10px; overflow-x: auto; max-height: 200px;">${JSON.stringify(event.response_payload, null, 2)}</pre>
                    </details>` : ''}
                </div>
            `;
        });
        
        html += '</div>';
        timeline.innerHTML = html;
        
    } catch (error) {
        console.error('Error loading system events:', error);
        timeline.innerHTML = '<div style="color: red;">Error loading events. Please try again.</div>';
    }
}

// ==================== TAB NAVIGATION ====================
document.addEventListener('DOMContentLoaded', function() {
    console.log('🚀 DOM Content Loaded - Initializing Invoice AI...');
    
    // New navigation system with hash-based routing
    const navLinks = document.querySelectorAll('.nav-link[data-tab]');
    const tabContents = document.querySelectorAll('.tab-content');
    const navToggle = document.getElementById('navToggle');
    const navTabs = document.querySelector('.nav-tabs');
    
    // Function to switch tabs
    function switchTab(tabName) {
        // Remove active class from all nav links and contents
        navLinks.forEach(link => link.classList.remove('active'));
        tabContents.forEach(content => content.classList.remove('active'));
        
        // Add active class to matching nav link and content
        const activeLink = document.querySelector(`.nav-link[data-tab="${tabName}"]`);
        const targetContent = document.getElementById(`tab-${tabName}`);
        
        if (activeLink && targetContent) {
            activeLink.classList.add('active');
            targetContent.classList.add('active');
            
            // Initialize Generate Invoice tab if it's selected
            if (tabName === 'generate') {
                initializeInvoiceGeneration();
            }
            
            // Initialize NetSuite Dashboard if selected
            if (tabName === 'netsuite-dashboard') {
                initializeNetSuiteDashboard();
            } else {
                // Stop auto-refresh when leaving dashboard
                stopDashboardRefresh();
            }
            
            // Initialize Invoice List if Invoices tab is selected
            if (tabName === 'invoices') {
                // Force refresh to get latest data (no cache)
                loadInvoiceList(currentInvoiceListPage || 1); // Reload current page or first page
            }
            
            // Initialize Bill Audit tab if selected
            if (tabName === 'bill-audit') {
                loadAllSystemEvents();
            }
            
            // Close mobile menu after selection
            if (navTabs && navTabs.classList.contains('active')) {
                navTabs.classList.remove('active');
            }
        }
    }
    
    // Handle nav link clicks
    navLinks.forEach(link => {
        link.addEventListener('click', function(e) {
            e.preventDefault();
            const tabName = this.getAttribute('data-tab');
            
            // Update URL hash
            if (tabName === 'invoices') {
                history.pushState(null, null, '/');
            } else {
                history.pushState(null, null, `/#${tabName}`);
            }
            
            switchTab(tabName);
        });
    });
    
    // Handle mobile navigation toggle
    if (navToggle) {
        navToggle.addEventListener('click', function() {
            if (navTabs) {
                navTabs.classList.toggle('active');
            }
        });
        
        // Close mobile menu when clicking outside
        document.addEventListener('click', function(e) {
            if (navTabs && navTabs.classList.contains('active')) {
                if (!navToggle.contains(e.target) && !navTabs.contains(e.target)) {
                    navTabs.classList.remove('active');
                }
            }
        });
    }
    
    // Handle hash-based navigation on page load and hash change
    function handleHashNavigation() {
        const hash = window.location.hash.slice(1); // Remove the # symbol
        if (hash) {
            switchTab(hash);
        } else {
            // Default to NetSuite dashboard if no hash
            switchTab('netsuite-dashboard');
        }
    }
    
    // Initial navigation based on URL hash
    handleHashNavigation();
    
    // Listen for hash changes (browser back/forward buttons)
    window.addEventListener('hashchange', handleHashNavigation);
    
    // Backward compatibility: Handle old tab buttons if they still exist
    const oldTabButtons = document.querySelectorAll('.tab-btn');
    if (oldTabButtons.length > 0) {
        oldTabButtons.forEach(button => {
            button.addEventListener('click', function() {
                const tabName = this.getAttribute('data-tab');
                
                // Update URL hash
                if (tabName === 'invoices') {
                    history.pushState(null, null, '/');
                } else {
                    history.pushState(null, null, `/#${tabName}`);
                }
                
                switchTab(tabName);
            });
        });
    }
    
    // Initialize invoice upload functionality
    initializeInvoiceUpload();
});

// ==================== PROGRESS TRACKING HELPERS ====================
/**
 * Show a progress bar with percentage and message
 * @param {string} containerId - ID of the container element
 * @param {number} step - Current step number
 * @param {number} totalSteps - Total number of steps
 * @param {string} message - Progress message to display
 */
function showProgressBar(containerId, step, totalSteps, message) {
    const percentage = Math.round((step / totalSteps) * 100);
    const html = `
        <div class="progress-container">
            <div class="progress-bar">
                <div class="progress-fill" style="width: ${percentage}%"></div>
            </div>
            <div class="progress-text">${percentage}% - Step ${step} of ${totalSteps}</div>
            <div class="progress-message">${message}</div>
        </div>
    `;
    document.getElementById(containerId).innerHTML = html;
}

/**
 * Update progress bar percentage and message
 * @param {string} containerId - ID of the container element
 * @param {number} step - Current step number
 * @param {number} totalSteps - Total number of steps
 * @param {string} message - Progress message to display
 */
function updateProgressBar(containerId, step, totalSteps, message) {
    const container = document.getElementById(containerId);
    if (!container) return;
    
    const percentage = Math.round((step / totalSteps) * 100);
    const progressFill = container.querySelector('.progress-fill');
    const progressText = container.querySelector('.progress-text');
    const progressMessage = container.querySelector('.progress-message');
    
    if (progressFill) progressFill.style.width = `${percentage}%`;
    if (progressText) progressText.textContent = `${percentage}% - Step ${step} of ${totalSteps}`;
    if (progressMessage) progressMessage.textContent = message;
}

/**
 * Generate HTML for a list of steps with status indicators
 * @param {Array} steps - Array of step objects {message, completed, current, error}
 * @returns {string} HTML string for steps list
 */
function generateStepsList(steps) {
    return steps.map((step, index) => {
        let icon = '⬜';
        let className = 'step-pending';
        
        if (step.error) {
            icon = '✗';
            className = 'step-error';
        } else if (step.completed) {
            icon = '✓';
            className = 'step-complete';
        } else if (step.current) {
            icon = '⏳';
            className = 'step-current';
        }
        
        const details = step.details ? `<div class="step-details">${step.details}</div>` : '';
        
        return `
            <div class="step-item ${className}">
                <div class="step-icon">${icon}</div>
                <div class="step-content">
                    <div class="step-title">${step.message}</div>
                    ${details}
                </div>
            </div>
        `;
    }).join('');
}

/**
 * Update a specific step in the steps list
 * @param {string} containerId - ID of the container element
 * @param {Array} steps - Updated array of step objects
 */
function updateStepsList(containerId, steps) {
    const container = document.getElementById(containerId);
    if (!container) return;
    
    container.innerHTML = `<div class="steps-list">${generateStepsList(steps)}</div>`;
}

/**
 * Escape HTML special characters to prevent XSS
 * @param {string} text - Text to escape
 * @returns {string} Escaped text
 */
function escapeHtml(text) {
    if (text == null) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

/**
 * Generate HTML for Gmail filtering funnel
 * @param {Object} stats - Statistics object
 * @returns {string} HTML string for filtering funnel
 */
function generateGmailFunnelHTML(stats) {
    return `
        <div class="filtering-funnel">
            <h4>📊 FILTERING FUNNEL:</h4>
            <div class="funnel-step">
                <span class="funnel-label">Total Emails (${stats.timeRange}):</span>
                <span class="funnel-value">${stats.totalInboxCount ? stats.totalInboxCount.toLocaleString() : stats.totalEmails.toLocaleString()} emails</span>
            </div>
            <div class="funnel-step">
                <span class="funnel-label">After Multi-Language Filter:</span>
                <span class="funnel-value">${stats.afterLanguageFilter.toLocaleString()} emails (${stats.languageFilterPercent}%)</span>
            </div>
            <div class="funnel-step">
                <span class="funnel-label">After AI Semantic Filter:</span>
                <span class="funnel-value">${stats.afterAIFilter.toLocaleString()} emails (${stats.aiFilterPercent}%)</span>
            </div>
            <div class="funnel-step final">
                <span class="funnel-label">Invoices/Receipts Found:</span>
                <span class="funnel-value">${stats.invoicesFound.toLocaleString()} documents (${stats.invoicesPercent}%)</span>
            </div>
        </div>
    `;
}

/**
 * Show progress with steps list
 * @param {string} containerId - ID of the container element
 * @param {number} step - Current step number
 * @param {number} totalSteps - Total number of steps
 * @param {string} message - Progress message
 * @param {Array} steps - Array of step objects
 */
function showProgressWithSteps(containerId, step, totalSteps, message, steps) {
    const container = document.getElementById(containerId);
    if (!container) return;
    
    const percentage = Math.round((step / totalSteps) * 100);
    const html = `
        <div class="progress-container">
            <div class="progress-bar">
                <div class="progress-fill" style="width: ${percentage}%"></div>
            </div>
            <div class="progress-text">${percentage}% - Step ${step} of ${totalSteps}</div>
            <div class="progress-message">${message}</div>
            <div class="steps-list">
                ${generateStepsList(steps)}
            </div>
        </div>
    `;
    container.innerHTML = html;
}

// ==================== INVOICE UPLOAD ====================
// Wait for DOM to be ready before attaching event listeners
let uploadArea, fileInput, uploadForm, submitBtn, loading, results, resultContent;

const gmailConnectBtn = document.getElementById('gmailConnectBtn');
const gmailImportBtn = document.getElementById('gmailImportBtn');
const gmailDisconnectBtn = document.getElementById('gmailDisconnectBtn');
const gmailStatus = document.getElementById('gmailStatus');
const gmailConnectSection = document.getElementById('gmailConnectSection');
const gmailImportSection = document.getElementById('gmailImportSection');
const gmailImportResults = document.getElementById('gmailImportResults');
const gmailMaxResults = document.getElementById('gmailMaxResults');

// CSV Upload Elements
const csvUploadArea = document.getElementById('csvUploadArea');
const csvFileInput = document.getElementById('csvFileInput');
const csvUploadForm = document.getElementById('csvUploadForm');
const csvSubmitBtn = document.getElementById('csvSubmitBtn');
const csvLoading = document.getElementById('csvLoading');
const csvMappingReview = document.getElementById('csvMappingReview');
const csvMappingContent = document.getElementById('csvMappingContent');
const csvImportBtn = document.getElementById('csvImportBtn');
const csvCancelBtn = document.getElementById('csvCancelBtn');
const csvImportResults = document.getElementById('csvImportResults');

let selectedFile = null;
let selectedCsvFile = null;
let csvAnalysisData = null;

async function checkGmailStatus() {
    try {
        const response = await fetch('/api/ap-automation/gmail/status');
        const data = await response.json();
        
        if (data.connected) {
            gmailStatus.innerHTML = '<div style="padding: 10px; background: #e8f5e9; border-radius: 6px; color: #2e7d32;">✅ Gmail Connected</div>';
            gmailConnectSection.classList.add('hidden');
            gmailImportSection.classList.remove('hidden');
        } else {
            gmailStatus.innerHTML = '<div style="padding: 10px; background: #fff3e0; border-radius: 6px; color: #e65100;">ℹ️ Connect Gmail to import invoices automatically</div>';
            gmailConnectSection.classList.remove('hidden');
            gmailImportSection.classList.add('hidden');
        }
    } catch (error) {
        console.error('Error checking Gmail status:', error);
    }
}

gmailConnectBtn.addEventListener('click', () => {
    window.location.href = '/api/ap-automation/gmail/auth';
});

gmailDisconnectBtn.addEventListener('click', async () => {
    if (confirm('Disconnect Gmail? You will need to reconnect to import invoices.')) {
        try {
            await fetch('/api/ap-automation/gmail/disconnect', { method: 'POST' });
            checkGmailStatus();
            gmailImportResults.innerHTML = '';
        } catch (error) {
            alert('Failed to disconnect Gmail: ' + error.message);
        }
    }
});

const gmailProgressTerminal = document.getElementById('gmailProgressTerminal');
const terminalOutput = document.getElementById('terminalOutput');
const minimizeTerminal = document.getElementById('minimizeTerminal');

minimizeTerminal.addEventListener('click', () => {
    gmailProgressTerminal.classList.add('hidden');
});

/**
 * Detect message type based on content for color-coded terminal display
 * @param {string} message - The message to analyze
 * @returns {string} The detected type (stage-header, success, info, warning, error, progress)
 */
function detectMessageType(message) {
    // Stage headers (STAGE 1, STAGE 2, FILTERING RESULTS) - Yellow/Orange
    if (message.includes('STAGE 1') || message.includes('STAGE 2') || message.includes('FILTERING RESULTS')) {
        return 'stage-header';
    }
    
    // Error messages (✗, KILL, Error) - Red
    if (message.includes('✗') || message.includes('KILL') || message.includes('Error') || message.includes('❌')) {
        return 'error';
    }
    
    // Warning messages (⚠️) - Orange
    if (message.includes('⚠️')) {
        return 'warning';
    }
    
    // Success messages (✓, ✅, SUCCESS) - Green
    if (message.startsWith('✓') || message.startsWith('✅') || message.includes('SUCCESS') || message.includes('Import session completed')) {
        return 'success';
    }
    
    // Progress messages ([1/19] pattern) - Gray/White
    if (/\[\d+\/\d+\]/.test(message)) {
        return 'progress';
    }
    
    // Info messages (📧, 📬, 🔍, Found, Total) - Blue/Cyan
    if (message.includes('📧') || message.includes('📬') || message.includes('🔍') || 
        message.includes('Found') || message.includes('Total') || message.includes('emails')) {
        return 'info';
    }
    
    // Default to info
    return 'info';
}

function addTerminalLine(message, type = null) {
    // Auto-detect type if not explicitly provided
    if (type === null || type === 'info') {
        type = detectMessageType(message);
    }
    
    const line = document.createElement('div');
    line.className = `terminal-line ${type}`;
    line.textContent = message;
    terminalOutput.appendChild(line);
    terminalOutput.scrollTop = terminalOutput.scrollHeight;
}

function clearTerminal() {
    terminalOutput.innerHTML = '';
}

function showError(title, message) {
    const errorHTML = `
        <div style="background: #ffebee; border: 2px solid #f44336; border-radius: 8px; padding: 20px; margin: 20px 0;">
            <div style="display: flex; align-items: center; margin-bottom: 10px;">
                <span style="font-size: 24px; margin-right: 10px;">❌</span>
                <h3 style="margin: 0; color: #c62828;">${title}</h3>
            </div>
            <p style="margin: 0; color: #d32f2f; font-size: 14px;">${message}</p>
        </div>
    `;
    gmailImportResults.innerHTML = errorHTML;
}

const gmailTimeRange = document.getElementById('gmailTimeRange');

gmailImportBtn.addEventListener('click', async () => {
    const days = parseInt(gmailTimeRange.value) || 7;
    
    gmailImportBtn.disabled = true;
    gmailImportBtn.textContent = '⏳ Importing...';
    
    // Show terminal
    gmailProgressTerminal.classList.remove('hidden');
    clearTerminal();
    
    gmailImportResults.innerHTML = '';
    
    try {
        // Use Server-Sent Events for real-time progress (EventSource only supports GET)
        const eventSource = new EventSource(`/api/ap-automation/gmail/import/stream?days=${days}`);
        
        let importResults = {
            imported: 0,
            skipped: 0,
            total: 0
        };
        
        // Listen for 'progress' events
        eventSource.addEventListener('progress', (event) => {
            try {
                const data = JSON.parse(event.data);
                addTerminalLine(data.message, 'info');
            } catch (e) {
                console.error('Error parsing progress event:', e);
            }
        });
        
        // Listen for 'complete' events
        eventSource.addEventListener('complete', (event) => {
            try {
                const data = JSON.parse(event.data);
                importResults = {
                    imported: data.imported,
                    skipped: data.skipped,
                    total: data.total,
                    invoices: data.invoices || []
                };
                eventSource.close();
                
                addTerminalLine('\n' + '─'.repeat(60), 'info');
                addTerminalLine('✅ Import session completed successfully!', 'success');
                
                gmailImportBtn.disabled = false;
                gmailImportBtn.textContent = '🔍 Start Smart Scan';
                
                // Show summary and invoice details
                displayImportSummary(importResults);
                displayInvoiceData(importResults.invoices);
            } catch (e) {
                console.error('Error parsing complete event:', e);
            }
        });
        
        // Listen for 'error' events (SSE event type, not connection error)
        eventSource.addEventListener('error', (event) => {
            try {
                const data = JSON.parse(event.data);
                const errorMessage = data.error || data.message || 'An error occurred during Gmail scan';
                addTerminalLine(`❌ Error: ${errorMessage}`, 'error');
                showError('Gmail Scan Error', errorMessage);
                eventSource.close();
                gmailImportBtn.disabled = false;
                gmailImportBtn.textContent = '🔍 Start Smart Scan';
            } catch (e) {
                console.error('Error parsing error event:', e);
            }
        });
        
        // Listen for 'funnel_stats' events
        eventSource.addEventListener('funnel_stats', (event) => {
            try {
                const data = JSON.parse(event.data);
                // Display filtering funnel statistics
                const funnelHTML = generateGmailFunnelHTML(data);
                const funnelDiv = document.createElement('div');
                funnelDiv.innerHTML = funnelHTML;
                terminalOutput.appendChild(funnelDiv);
                terminalOutput.scrollTop = terminalOutput.scrollHeight;
            } catch (e) {
                console.error('Error parsing funnel_stats event:', e);
            }
        });
        
        // Handle connection errors
        eventSource.onerror = (error) => {
            console.error('Gmail SSE connection error:', error);
            
            if (eventSource.readyState === EventSource.CLOSED) {
                addTerminalLine('❌ Connection closed by server', 'error');
                showError('Connection Error', 'Lost connection to server. Please try again.');
                eventSource.close();
                gmailImportBtn.disabled = false;
                gmailImportBtn.textContent = '🔍 Start Smart Scan';
            } else {
                addTerminalLine('⚠️ Connection interrupted, attempting to reconnect...', 'warning');
            }
        };
        
    } catch (error) {
        addTerminalLine(`❌ Error: ${error.message}`, 'error');
        gmailImportBtn.disabled = false;
        gmailImportBtn.textContent = '🔍 Start Smart Scan';
    }
});

function displayInvoiceData(invoices) {
    if (!invoices || invoices.length === 0) {
        return;
    }
    
    let html = `
        <div style="margin-top: 30px;">
            <h3 style="margin-bottom: 20px; color: #333;">📋 Extracted Invoice Data (${invoices.length} invoices)</h3>
    `;
    
    invoices.forEach((invoice, idx) => {
        const fullData = invoice.full_data || {};
        const vendor = fullData.vendor || {};
        const buyer = fullData.buyer || {};
        const totals = fullData.totals || {};
        const payment = fullData.payment || {};
        const lineItems = fullData.lineItems || [];
        
        html += `
            <div style="background: white; border: 2px solid #667eea; border-radius: 8px; padding: 20px; margin-bottom: 20px; box-shadow: 0 2px 8px rgba(0,0,0,0.1);">
                
                <div style="display: flex; justify-content: space-between; align-items: start; margin-bottom: 20px; border-bottom: 2px solid #667eea; padding-bottom: 15px;">
                    <div>
                        <h4 style="margin: 0 0 8px 0; color: #667eea; font-size: 20px;">${vendor.name || invoice.vendor || 'Unknown Vendor'}</h4>
                        <div style="font-size: 12px; color: #666;">
                            <div><strong>📄 Type:</strong> ${fullData.documentType || 'Invoice'} | <strong>🌐 Language:</strong> ${fullData.language || 'en'}</div>
                            <div style="margin-top: 4px;"><strong>📧 From:</strong> ${invoice.sender || 'Unknown'}</div>
                            <div style="margin-top: 4px;"><strong>📅 Email Date:</strong> ${invoice.date || 'N/A'}</div>
                        </div>
                    </div>
                    <div style="text-align: right;">
                        <div style="font-size: 28px; font-weight: bold; color: #2e7d32;">${fullData.currency || 'USD'} ${totals.total || invoice.total || 'N/A'}</div>
                        <div style="font-size: 13px; color: #666; margin-top: 5px;">Invoice #${fullData.invoiceNumber || invoice.invoice_number || 'N/A'}</div>
                        ${fullData.issueDate ? `<div style="font-size: 12px; color: #888; margin-top: 3px;">Issued: ${fullData.issueDate}</div>` : ''}
                        ${fullData.dueDate ? `<div style="font-size: 12px; color: #d32f2f; margin-top: 3px;">Due: ${fullData.dueDate}</div>` : ''}
                    </div>
                </div>

                <div style="background: #f9f9f9; padding: 15px; border-radius: 6px; margin-bottom: 15px;">
                    <strong style="color: #555;">📧 Email Subject:</strong>
                    <p style="margin: 8px 0 0 0; color: #333; font-size: 14px;">${invoice.subject || 'N/A'}</p>
                </div>
                
                <div style="display: grid; grid-template-columns: repeat(2, 1fr); gap: 15px; margin-bottom: 15px;">
                    <div style="background: #f0f7ff; padding: 12px; border-radius: 6px; border-left: 3px solid #2196f3;">
                        <strong style="color: #1976d2; font-size: 14px;">🏢 Vendor Information</strong>
                        <div style="margin-top: 8px; font-size: 13px; color: #333;">
                            <div><strong>Name:</strong> ${vendor.name || 'N/A'}</div>
                            ${vendor.address ? `<div style="margin-top: 4px;"><strong>Address:</strong> ${vendor.address}</div>` : ''}
                            ${vendor.country ? `<div style="margin-top: 4px;"><strong>Country:</strong> ${vendor.country}</div>` : ''}
                            ${vendor.email ? `<div style="margin-top: 4px;"><strong>Email:</strong> ${vendor.email}</div>` : ''}
                            ${vendor.phone ? `<div style="margin-top: 4px;"><strong>Phone:</strong> ${vendor.phone}</div>` : ''}
                            ${vendor.taxId ? `<div style="margin-top: 4px;"><strong>Tax ID:</strong> ${vendor.taxId}</div>` : ''}
                            ${vendor.registrationNumber ? `<div style="margin-top: 4px;"><strong>Reg #:</strong> ${vendor.registrationNumber}</div>` : ''}
                        </div>
                    </div>
                    
                    <div style="background: #f0f7ff; padding: 12px; border-radius: 6px; border-left: 3px solid #2196f3;">
                        <strong style="color: #1976d2; font-size: 14px;">👤 Buyer Information</strong>
                        <div style="margin-top: 8px; font-size: 13px; color: #333;">
                            ${buyer.name ? `<div><strong>Name:</strong> ${buyer.name}</div>` : '<div style="color: #999;">Not available</div>'}
                            ${buyer.address ? `<div style="margin-top: 4px;"><strong>Address:</strong> ${buyer.address}</div>` : ''}
                            ${buyer.country ? `<div style="margin-top: 4px;"><strong>Country:</strong> ${buyer.country}</div>` : ''}
                            ${buyer.email ? `<div style="margin-top: 4px;"><strong>Email:</strong> ${buyer.email}</div>` : ''}
                            ${buyer.taxId ? `<div style="margin-top: 4px;"><strong>Tax ID:</strong> ${buyer.taxId}</div>` : ''}
                        </div>
                    </div>
                </div>

                <div style="background: #fff3e0; padding: 12px; border-radius: 6px; border-left: 3px solid #ff9800; margin-bottom: 15px;">
                    <strong style="color: #e65100; font-size: 14px;">💰 Financial Breakdown</strong>
                    <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; margin-top: 10px; font-size: 13px;">
                        <div>
                            <div style="color: #666;">Subtotal:</div>
                            <div style="font-weight: bold; color: #333; margin-top: 3px;">${fullData.currency || 'USD'} ${totals.subtotal || 'N/A'}</div>
                        </div>
                        <div>
                            <div style="color: #666;">Tax ${totals.taxPercent ? `(${totals.taxPercent}%)` : ''}:</div>
                            <div style="font-weight: bold; color: #333; margin-top: 3px;">${fullData.currency || 'USD'} ${totals.tax || 'N/A'}</div>
                        </div>
                        <div>
                            <div style="color: #666;">Total:</div>
                            <div style="font-weight: bold; color: #2e7d32; font-size: 16px; margin-top: 3px;">${fullData.currency || 'USD'} ${totals.total || 'N/A'}</div>
                        </div>
                        ${totals.discounts && totals.discounts > 0 ? `
                            <div>
                                <div style="color: #666;">Discounts:</div>
                                <div style="font-weight: bold; color: #d32f2f; margin-top: 3px;">-${fullData.currency || 'USD'} ${totals.discounts}</div>
                            </div>
                        ` : ''}
                        ${totals.fees && totals.fees > 0 ? `
                            <div>
                                <div style="color: #666;">Fees:</div>
                                <div style="font-weight: bold; color: #333; margin-top: 3px;">${fullData.currency || 'USD'} ${totals.fees}</div>
                            </div>
                        ` : ''}
                        ${totals.shipping && totals.shipping > 0 ? `
                            <div>
                                <div style="color: #666;">Shipping:</div>
                                <div style="font-weight: bold; color: #333; margin-top: 3px;">${fullData.currency || 'USD'} ${totals.shipping}</div>
                            </div>
                        ` : ''}
                    </div>
                </div>

                ${fullData.paymentTerms || fullData.dueDate || payment.iban || payment.swift ? `
                    <div style="background: #e8f5e9; padding: 12px; border-radius: 6px; border-left: 3px solid #4caf50; margin-bottom: 15px;">
                        <strong style="color: #2e7d32; font-size: 14px;">💳 Payment Information</strong>
                        <div style="margin-top: 8px; font-size: 13px; color: #333;">
                            ${fullData.paymentTerms ? `<div><strong>Terms:</strong> ${fullData.paymentTerms}</div>` : ''}
                            ${fullData.dueDate ? `<div style="margin-top: 4px;"><strong>Due Date:</strong> ${fullData.dueDate}</div>` : ''}
                            ${payment.iban ? `<div style="margin-top: 4px;"><strong>IBAN:</strong> ${payment.iban}</div>` : ''}
                            ${payment.swift ? `<div style="margin-top: 4px;"><strong>SWIFT:</strong> ${payment.swift}</div>` : ''}
                            ${payment.bankName ? `<div style="margin-top: 4px;"><strong>Bank:</strong> ${payment.bankName}</div>` : ''}
                            ${payment.accountNumber ? `<div style="margin-top: 4px;"><strong>Account:</strong> ${payment.accountNumber}</div>` : ''}
                            ${payment.paymentInstructions ? `<div style="margin-top: 6px; padding-top: 6px; border-top: 1px solid #c8e6c9;"><em>${payment.paymentInstructions}</em></div>` : ''}
                        </div>
                    </div>
                ` : ''}
                
                ${lineItems.length > 0 ? `
                    <div style="margin-top: 15px;">
                        <strong style="color: #555; font-size: 14px;">📝 Line Items (${lineItems.length})</strong>
                        <table style="width: 100%; margin-top: 10px; border-collapse: collapse; font-size: 13px;">
                            <thead>
                                <tr style="background: #f5f5f5;">
                                    <th style="padding: 10px; text-align: left; border: 1px solid #ddd;">Description</th>
                                    <th style="padding: 10px; text-align: center; border: 1px solid #ddd;">Qty</th>
                                    <th style="padding: 10px; text-align: right; border: 1px solid #ddd;">Unit Price</th>
                                    <th style="padding: 10px; text-align: right; border: 1px solid #ddd;">Tax</th>
                                    <th style="padding: 10px; text-align: right; border: 1px solid #ddd;">Total</th>
                                    <th style="padding: 10px; text-align: center; border: 1px solid #ddd;">✓</th>
                                </tr>
                            </thead>
                            <tbody>
                                ${lineItems.map(item => `
                                    <tr>
                                        <td style="padding: 10px; border: 1px solid #ddd;">
                                            <strong>${item.description || 'N/A'}</strong>
                                            ${item.productCode ? `<div style="font-size: 11px; color: #888; margin-top: 2px;">SKU: ${item.productCode}</div>` : ''}
                                            ${item.category ? `<div style="font-size: 11px; color: #666; margin-top: 2px;">Category: ${item.category}</div>` : ''}
                                        </td>
                                        <td style="padding: 10px; text-align: center; border: 1px solid #ddd;">${item.quantity || '-'}</td>
                                        <td style="padding: 10px; text-align: right; border: 1px solid #ddd;">${item.currency || fullData.currency || 'USD'} ${item.unitPrice || '-'}</td>
                                        <td style="padding: 10px; text-align: right; border: 1px solid #ddd;">
                                            ${item.taxAmount ? `${item.currency || fullData.currency || 'USD'} ${item.taxAmount}` : '-'}
                                            ${item.taxPercent ? `<div style="font-size: 11px; color: #888;">(${item.taxPercent}%)</div>` : ''}
                                        </td>
                                        <td style="padding: 10px; text-align: right; border: 1px solid #ddd; font-weight: bold;">${item.currency || fullData.currency || 'USD'} ${item.lineSubtotal || item.total || '-'}</td>
                                        <td style="padding: 10px; text-align: center; border: 1px solid #ddd;">${item.mathVerified ? '✅' : '⚠️'}</td>
                                    </tr>
                                `).join('')}
                            </tbody>
                        </table>
                    </div>
                ` : ''}

                ${fullData.reasoning || fullData.warnings ? `
                    <div style="margin-top: 15px; padding: 12px; background: #fff9e6; border-radius: 6px; border-left: 3px solid #ffc107;">
                        ${fullData.reasoning ? `
                            <div style="margin-bottom: 10px;">
                                <strong style="color: #f57c00; font-size: 13px;">🧠 AI Reasoning:</strong>
                                <p style="margin: 6px 0 0 0; font-size: 12px; color: #666; line-height: 1.5;">${fullData.reasoning}</p>
                            </div>
                        ` : ''}
                        ${fullData.warnings && fullData.warnings.length > 0 ? `
                            <div>
                                <strong style="color: #f57c00; font-size: 13px;">⚠️ Warnings:</strong>
                                <ul style="margin: 6px 0 0 20px; font-size: 12px; color: #d84315;">
                                    ${fullData.warnings.map(w => `<li style="margin-top: 3px;">${w}</li>`).join('')}
                                </ul>
                            </div>
                        ` : ''}
                    </div>
                ` : ''}

                ${fullData.extractionConfidence || fullData.classificationConfidence ? `
                    <div style="margin-top: 15px; display: flex; gap: 10px; font-size: 12px;">
                        ${fullData.classificationConfidence ? `
                            <div style="padding: 6px 12px; background: #e3f2fd; border-radius: 4px; color: #1976d2;">
                                <strong>Classification Confidence:</strong> ${Math.round(fullData.classificationConfidence * 100)}%
                            </div>
                        ` : ''}
                        ${fullData.extractionConfidence ? `
                            <div style="padding: 6px 12px; background: #e8f5e9; border-radius: 4px; color: #2e7d32;">
                                <strong>Extraction Confidence:</strong> ${Math.round(fullData.extractionConfidence * 100)}%
                            </div>
                        ` : ''}
                    </div>
                ` : ''}
                
                <button onclick="toggleFullData(${idx})" style="margin-top: 15px; padding: 10px 20px; background: #667eea; color: white; border: none; border-radius: 4px; cursor: pointer; font-size: 14px; font-weight: 500;">
                    📄 View Complete JSON Schema
                </button>
                
                <div id="fullData${idx}" style="display: none; margin-top: 15px; background: #1e1e1e; padding: 15px; border-radius: 4px; max-height: 500px; overflow-y: auto;">
                    <pre style="margin: 0; font-size: 12px; white-space: pre-wrap; color: #d4d4d4; font-family: 'Courier New', monospace;">${JSON.stringify(fullData, null, 2)}</pre>
                </div>
            </div>
        `;
    });
    
    html += '</div>';
    
    gmailImportResults.innerHTML += html;
}

window.toggleFullData = function(idx) {
    const element = document.getElementById(`fullData${idx}`);
    if (element.style.display === 'none') {
        element.style.display = 'block';
    } else {
        element.style.display = 'none';
    }
};

function displayImportSummary(results) {
    const html = `
        <div style="background: #e8f5e9; padding: 20px; border-radius: 8px; margin-top: 20px; border-left: 4px solid #4caf50;">
            <h3 style="margin: 0 0 15px 0; color: #2e7d32;">📊 Import Summary</h3>
            <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 15px;">
                <div style="text-align: center; background: white; padding: 15px; border-radius: 6px;">
                    <div style="font-size: 32px; font-weight: bold; color: #1976d2;">${results.total}</div>
                    <div style="font-size: 14px; color: #666; margin-top: 5px;">Emails Scanned</div>
                </div>
                <div style="text-align: center; background: white; padding: 15px; border-radius: 6px;">
                    <div style="font-size: 32px; font-weight: bold; color: #388e3c;">${results.imported}</div>
                    <div style="font-size: 14px; color: #666; margin-top: 5px;">Invoices Imported</div>
                </div>
                <div style="text-align: center; background: white; padding: 15px; border-radius: 6px;">
                    <div style="font-size: 32px; font-weight: bold; color: #f57c00;">${results.skipped}</div>
                    <div style="font-size: 14px; color: #666; margin-top: 5px;">Emails Skipped</div>
                </div>
            </div>
            <div style="margin-top: 15px; text-align: center; color: #555;">
                Success Rate: <strong>${results.total > 0 ? Math.round((results.imported / results.total) * 100) : 0}%</strong>
            </div>
        </div>
    `;
    gmailImportResults.innerHTML = html;
}

function displayGmailImportResults(data) {
    let html = `
        <div style="background: #f5f5f5; padding: 15px; border-radius: 6px; margin-bottom: 15px;">
            <h3 style="margin: 0 0 10px 0;">Import Summary</h3>
            <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px;">
                <div style="text-align: center; background: #fff; padding: 10px; border-radius: 4px;">
                    <div style="font-size: 24px; font-weight: bold; color: #1976d2;">${data.total_found}</div>
                    <div style="font-size: 12px; color: #666;">Emails Found</div>
                </div>
                <div style="text-align: center; background: #fff; padding: 10px; border-radius: 4px;">
                    <div style="font-size: 24px; font-weight: bold; color: #388e3c;">${data.processed.length}</div>
                    <div style="font-size: 12px; color: #666;">Imported</div>
                </div>
                <div style="text-align: center; background: #fff; padding: 10px; border-radius: 4px;">
                    <div style="font-size: 24px; font-weight: bold; color: #f57c00;">${data.skipped.length}</div>
                    <div style="font-size: 12px; color: #666;">Skipped</div>
                </div>
            </div>
        </div>
    `;
    
    if (data.processed.length > 0) {
        html += '<h3>✅ Successfully Imported</h3>';
        data.processed.forEach(item => {
            const vendor = item.extraction?.validated?.vendor?.name || 'Unknown';
            const total = item.extraction?.validated?.totals?.total || 'N/A';
            const currency = item.extraction?.validated?.currency || '';
            
            html += `
                <div style="background: #e8f5e9; padding: 12px; border-radius: 6px; margin-bottom: 10px; border-left: 4px solid #4caf50;">
                    <div style="font-weight: bold;">${item.subject}</div>
                    <div style="font-size: 13px; color: #666; margin-top: 5px;">
                        From: ${item.from} | Date: ${item.date}
                    </div>
                    <div style="margin-top: 5px;">
                        Vendor: <strong>${vendor}</strong> | Total: <strong>${currency} ${total}</strong>
                    </div>
                </div>
            `;
        });
    }
    
    if (data.skipped.length > 0) {
        html += '<details style="margin-top: 15px;"><summary style="cursor: pointer; font-weight: 600; padding: 10px; background: #fff3e0; border-radius: 6px;">⚠️ Skipped Emails (' + data.skipped.length + ')</summary><div style="margin-top: 10px;">';
        data.skipped.forEach(item => {
            html += `
                <div style="background: #fff; padding: 10px; border-radius: 4px; margin-bottom: 8px; border-left: 3px solid #ff9800; font-size: 13px;">
                    <div style="font-weight: bold;">${item.subject || 'No subject'}</div>
                    <div style="color: #666; margin-top: 3px;">Reason: ${item.reason}</div>
                </div>
            `;
        });
        html += '</div></details>';
    }
    
    if (data.errors.length > 0) {
        html += '<details style="margin-top: 15px;"><summary style="cursor: pointer; font-weight: 600; padding: 10px; background: #ffebee; border-radius: 6px;">❌ Errors (' + data.errors.length + ')</summary><div style="margin-top: 10px;">';
        data.errors.forEach(item => {
            html += `
                <div style="background: #fff; padding: 10px; border-radius: 4px; margin-bottom: 8px; border-left: 3px solid #f44336; font-size: 13px;">
                    <div style="color: #c62828;">${item.error}</div>
                </div>
            `;
        });
        html += '</div></details>';
    }
    
    gmailImportResults.innerHTML = html;
}

// Initialize invoice upload functionality when DOM is ready
function initializeInvoiceUpload() {
    console.log('🔧 Initializing invoice upload...');
    
    // Get upload elements
    uploadArea = document.getElementById('uploadArea');
    fileInput = document.getElementById('fileInput');
    uploadForm = document.getElementById('uploadForm');
    submitBtn = document.getElementById('submitBtn');
    loading = document.getElementById('loading');
    results = document.getElementById('results');
    resultContent = document.getElementById('resultContent');
    
    // Debug: Verify all elements exist
    console.log('Upload Elements Check:', {
        uploadArea: !!uploadArea,
        fileInput: !!fileInput,
        uploadForm: !!uploadForm,
        submitBtn: !!submitBtn,
        loading: !!loading,
        results: !!results,
        resultContent: !!resultContent
    });
    
    if (!uploadArea || !fileInput || !uploadForm || !submitBtn) {
        console.error('❌ Invoice upload elements missing! Check HTML IDs.');
        return;
    }
    
    console.log('✅ All invoice upload elements found');
    
    uploadArea.addEventListener('click', () => {
        console.log('📂 Upload area clicked');
        fileInput.click();
    });

    uploadArea.addEventListener('dragover', (e) => {
        e.preventDefault();
        uploadArea.classList.add('dragover');
    });

    uploadArea.addEventListener('dragleave', () => {
        uploadArea.classList.remove('dragover');
    });

    uploadArea.addEventListener('drop', (e) => {
        e.preventDefault();
        uploadArea.classList.remove('dragover');
        
        const files = e.dataTransfer.files;
        if (files.length > 0) {
            console.log('📎 File dropped:', files[0].name);
            handleFileSelect(files[0]);
        }
    });

    fileInput.addEventListener('change', (e) => {
        console.log('📎 File input changed');
        if (e.target.files.length > 0) {
            console.log('📄 File selected:', e.target.files[0].name);
            handleFileSelect(e.target.files[0]);
        }
    });

    function handleFileSelect(file) {
        console.log('✅ File selected for upload:', file.name, 'Size:', file.size, 'bytes');
        selectedFile = file;
        uploadArea.querySelector('p').textContent = `Selected: ${file.name}`;
        submitBtn.disabled = false;
    }

    uploadForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        console.log('🚀 Form submitted!');
        
        if (!selectedFile) {
            console.error('❌ No file selected');
            return;
        }
        
        console.log('📤 Uploading file:', selectedFile.name);
        
        const formData = new FormData();
        formData.append('file', selectedFile);
        const filename = selectedFile.name;
        
        // Hide old UI elements
        loading.classList.add('hidden');
        results.classList.add('hidden');
        submitBtn.disabled = true;
        
        // Show progress container
        const uploadProgressDiv = document.getElementById('uploadProgress');
        uploadProgressDiv.classList.remove('hidden');
        uploadProgressDiv.innerHTML = '<div class="loading"><div class="spinner"></div><p>Uploading file...</p></div>';
        
        try {
            // Upload and process file
            console.log('⏳ Sending POST request to /upload...');
            uploadProgressDiv.innerHTML = '<div class="loading"><div class="spinner"></div><p>Processing invoice...</p></div>';
            
            const uploadResponse = await fetch('/upload', {
                method: 'POST',
                body: formData
            });
            
            console.log('📥 Response received:', uploadResponse.status);
            
            const data = await uploadResponse.json();
            console.log('📊 Response data:', data);
            
            uploadProgressDiv.classList.add('hidden');
            submitBtn.disabled = false;
            
            if (!uploadResponse.ok || data.status === 'error') {
                throw new Error(data.error || `Upload failed: ${uploadResponse.status}`);
            }
            
            console.log('✅ Upload successful, displaying results');
            displayResults(data);
            
            // Hide the upload form and Gmail section to keep results visible
            if (uploadArea) uploadArea.style.display = 'none';
            const gmailSection = document.querySelector('.gmail-import');
            if (gmailSection) gmailSection.style.display = 'none';
            
        } catch (error) {
            console.error('❌ Upload error:', error);
            uploadProgressDiv.classList.add('hidden');
            submitBtn.disabled = false;
            results.classList.remove('hidden');
            resultContent.innerHTML = `
                <div class="error-message">
                    <strong>Error:</strong> ${error.message}
                </div>
            `;
        }
    });
    
    console.log('✅ Invoice upload initialization complete');
}

checkGmailStatus();

const urlParams = new URLSearchParams(window.location.search);
if (urlParams.get('gmail_connected') === 'true') {
    window.history.replaceState({}, document.title, window.location.pathname);
    checkGmailStatus();
}

function displayResults(data) {
    results.classList.remove('hidden');
    
    // Store invoice data globally for vendor matching
    currentInvoiceData = data.validated_data || data;
    currentInvoiceId = data.invoice_id || data.validated_data?.invoiceId;
    
    // Add "Upload Another" button at the top
    let html = `
        <div style="text-align: right; margin-bottom: 20px;">
            <button onclick="location.reload()" style="background: #667eea; color: white; border: none; padding: 10px 20px; border-radius: 6px; cursor: pointer; font-weight: bold;">
                📤 Upload Another Invoice
            </button>
        </div>
    `;
    
    if (data.status === 'error') {
        resultContent.innerHTML = html + `
            <span class="warning-badge">Processing Error</span>
            <div class="error-message">
                <strong>Error:</strong> ${data.error || 'Unknown error occurred'}
                ${data.details ? `<br><small>${data.details}</small>` : ''}
            </div>
        `;
        return;
    }
    
    const validated = data.validated_data || {};
    const rawEntities = data.layers?.layer1_document_ai?.entities || {};
    
    html += `<span class="success-badge">✓ Processing Complete</span>`;
    
    // Prepare invoice data for workflow - ensure invoice_id is always set
    const invoiceWorkflowData = {
        invoice_id: currentInvoiceId || validated.invoiceId || validated.invoiceNumber || data.invoice_id || `INV_${Date.now()}`,
        vendor_name: validated.vendorName || validated.supplier_name || 'Unknown',
        amount: validated.totalAmount || validated.total_amount || '0',
        currency: validated.currency || 'USD',
        invoice_date: validated.invoiceDate || validated.invoice_date || 'N/A',
        vendor_match: data.vendor_match,
        validated_data: validated
    };
    
    // Log if invoice_id is generated
    if (!currentInvoiceId) {
        console.warn('Invoice ID was missing, generated a temporary ID:', invoiceWorkflowData.invoice_id);
    }
    
    // Start the perfect workflow instead of showing buttons
    html += `
        <div class="workflow-starting">
            <h3>📋 Invoice Details</h3>
            <table class="invoice-summary">
                <tr><td><strong>Invoice ID:</strong></td><td>${invoiceWorkflowData.invoice_id}</td></tr>
                <tr><td><strong>Vendor:</strong></td><td>${invoiceWorkflowData.vendor_name}</td></tr>
                <tr><td><strong>Amount:</strong></td><td>${invoiceWorkflowData.currency} ${invoiceWorkflowData.amount}</td></tr>
                <tr><td><strong>Date:</strong></td><td>${invoiceWorkflowData.invoice_date}</td></tr>
            </table>
            <p style="margin-top: 20px; font-style: italic;">Starting guided workflow...</p>
        </div>
    `;
    
    // ALWAYS SHOW GCS LINK IF AVAILABLE (regardless of invoice ID)
    const invoiceId = validated.invoiceId || validated.invoiceNumber || data.invoice_id || "Unknown";
    const gcsUri = data.gcs_uri; // Format: gs://payouts-invoices/uploads/filename.pdf
    
    // Show GCS link even if no invoice ID (just need GCS URI)
    if (gcsUri) {
        const filename = gcsUri.split('/').pop();
        html += `
            <div style="margin: 20px 0; padding: 25px; background: #4CAF50; color: white; border-radius: 12px; box-shadow: 0 4px 12px rgba(76, 175, 80, 0.3);">
                <div style="font-size: 22px; font-weight: bold; margin-bottom: 20px;">🔗 GOOGLE CLOUD STORAGE LINK</div>
                <div style="background: rgba(255,255,255,0.2); padding: 15px; border-radius: 8px; margin-bottom: 20px; word-break: break-all;">
                    <div style="font-size: 12px; opacity: 0.9; margin-bottom: 8px;">GCS URI (Copy this link):</div>
                    <div style="font-family: monospace; font-size: 14px; font-weight: bold; user-select: all; cursor: text;">
                        ${escapeHtml(gcsUri)}
                    </div>
                </div>
                <div style="background: #2196F3; padding: 15px; border-radius: 8px;">
                    <div style="font-size: 14px; margin-bottom: 10px;">📥 Download Invoice (ID: ${escapeHtml(invoiceId)})</div>
                    <button 
                        onclick="downloadInvoice('${escapeHtml(invoiceId)}', event)" 
                        style="background: white; color: #2196F3; border: none; padding: 12px 30px; border-radius: 6px; font-weight: bold; cursor: pointer; font-size: 14px; box-shadow: 0 2px 8px rgba(0,0,0,0.2); transition: all 0.3s;"
                        onmouseover="this.style.transform='scale(1.05)'; this.style.boxShadow='0 4px 12px rgba(0,0,0,0.3)';"
                        onmouseout="this.style.transform='scale(1)'; this.style.boxShadow='0 2px 8px rgba(0,0,0,0.2)';"
                    >
                        Download File
                    </button>
                </div>
            </div>
        `;
    }
    
    if (data.status === 'partial' || data.status === 'warning') {
        html += `<p style="color: #ff9800; margin-top: 10px;"><strong>Note:</strong> Some processing layers encountered issues. Showing extracted data from Document AI.</p>`;
    }
    
    html += buildLayerStatusView(data.layers || {});
    
    const displayData = validated;
    
    // Document Classification Section
    if (displayData.documentType || displayData.language) {
        html += `
            <div class="result-section">
                <h3>📄 Document Classification</h3>
                <div class="result-grid">
                    ${displayData.documentType ? `<div class="result-item"><strong>Document Type</strong><span>${displayData.documentType}</span></div>` : ''}
                    ${displayData.language ? `<div class="result-item"><strong>Language</strong><span>${displayData.language.toUpperCase()}</span></div>` : ''}
                    ${displayData.currency ? `<div class="result-item"><strong>Currency</strong><span>${displayData.currency}</span></div>` : ''}
                    ${displayData.classificationConfidence ? `<div class="result-item"><strong>Confidence</strong><span>${(displayData.classificationConfidence * 100).toFixed(1)}%</span></div>` : ''}
                </div>
            </div>
        `;
    }
    
    // Vendor Information Section
    if (displayData.vendor) {
        const vendor = displayData.vendor;
        const vendorMatch = displayData.vendorMatch || {};
        html += `
            <div class="result-section">
                <h3>🏢 Vendor Information</h3>
                <div class="result-grid">
                    ${vendor.name ? `<div class="result-item"><strong>Vendor Name</strong><span>${vendor.name}</span></div>` : ''}
                    ${vendorMatch.normalizedName && vendorMatch.normalizedName !== vendor.name ? `<div class="result-item"><strong>Canonical Name</strong><span>${vendorMatch.normalizedName}</span></div>` : ''}
                    ${vendor.country ? `<div class="result-item"><strong>Country</strong><span>${vendor.country}</span></div>` : ''}
                    ${vendor.taxId ? `<div class="result-item"><strong>Tax ID</strong><span>${vendor.taxId}</span></div>` : ''}
                    ${vendor.email ? `<div class="result-item"><strong>Email</strong><span>${vendor.email}</span></div>` : ''}
                    ${vendor.phone ? `<div class="result-item"><strong>Phone</strong><span>${vendor.phone}</span></div>` : ''}
                    ${vendorMatch.confidence ? `<div class="result-item"><strong>Match Confidence</strong><span>${(vendorMatch.confidence * 100).toFixed(1)}%</span></div>` : ''}
                </div>
                ${vendor.address ? `<div class="result-item" style="margin-top: 10px;"><strong>Address</strong><span>${vendor.address}</span></div>` : ''}
                ${vendorMatch.alternateNames && vendorMatch.alternateNames.length > 0 ? `<div class="result-detail-small" style="margin-top: 10px;"><strong>Alternate Names:</strong> ${vendorMatch.alternateNames.join(', ')}</div>` : ''}
            </div>
        `;
    }
    
    // AUTOMATIC VENDOR MATCHING Section
    console.log('🔍 Checking vendor_match in response:', data.vendor_match);
    if (data.vendor_match) {
        console.log('✅ vendor_match found:', data.vendor_match);
        const vendorMatch = data.vendor_match;
        const verdict = vendorMatch.verdict || 'UNKNOWN';
        const confidence = vendorMatch.confidence || 0;
        const method = vendorMatch.method || 'UNKNOWN';
        const reasoning = vendorMatch.reasoning || 'No reasoning provided';
        const invoiceVendor = vendorMatch.invoice_vendor || {};
        const databaseVendor = vendorMatch.database_vendor || null;
        
        console.log('📊 Vendor matching verdict:', verdict, 'Confidence:', confidence, 'Method:', method);
        
        // Verdict badge styling
        let verdictBadge = '';
        let verdictColor = '';
        let verdictBg = '';
        
        if (verdict === 'MATCH') {
            verdictBadge = '✅ Vendor Matched';
            verdictColor = '#2e7d32';
            verdictBg = '#e8f5e9';
        } else if (verdict === 'NEW_VENDOR') {
            verdictBadge = '🆕 New Vendor Detected';
            verdictColor = '#1565c0';
            verdictBg = '#e3f2fd';
        } else if (verdict === 'AMBIGUOUS') {
            verdictBadge = '⚠️ Ambiguous Match';
            verdictColor = '#f57c00';
            verdictBg = '#fff3e0';
        }
        
        // Method badge
        let methodLabel = '';
        if (method === 'TAX_ID_HARD_MATCH') {
            methodLabel = '🔐 Tax ID Match (100%)';
        } else if (method === 'SEMANTIC_MATCH') {
            methodLabel = '🧠 AI Semantic Match';
        } else if (method === 'NEW_VENDOR') {
            methodLabel = '🆕 Not in Database';
        }
        
        html += `
            <div class="result-section" style="border: 2px solid ${verdictColor}; background: linear-gradient(to right, ${verdictBg}, #ffffff);">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px;">
                    <h3 style="margin: 0; color: ${verdictColor};">⚖️ Automatic Vendor Matching</h3>
                    <span style="padding: 8px 16px; background: ${verdictColor}; color: white; border-radius: 20px; font-weight: bold; font-size: 14px;">
                        ${verdictBadge}
                    </span>
                </div>
                
                <!-- Matching Method and Confidence -->
                <div style="display: flex; gap: 15px; margin-bottom: 20px;">
                    <div style="flex: 1; background: white; padding: 12px; border-radius: 6px; border-left: 3px solid ${verdictColor};">
                        <div style="font-size: 12px; color: #666; margin-bottom: 4px;">Matching Method</div>
                        <div style="font-weight: bold; color: ${verdictColor};">${methodLabel}</div>
                    </div>
                    <div style="flex: 1; background: white; padding: 12px; border-radius: 6px; border-left: 3px solid ${verdictColor};">
                        <div style="font-size: 12px; color: #666; margin-bottom: 4px;">Confidence Score</div>
                        <div style="font-weight: bold; color: ${verdictColor};">
                            ${(confidence * 100).toFixed(1)}%
                            <div style="background: #e0e0e0; height: 6px; border-radius: 3px; margin-top: 4px; overflow: hidden;">
                                <div style="background: ${verdictColor}; height: 100%; width: ${confidence * 100}%; transition: width 0.3s;"></div>
                            </div>
                        </div>
                    </div>
                </div>
                
                <!-- Side-by-Side Comparison -->
                <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-bottom: 20px;">
                    <!-- Left: What the Invoice Says -->
                    <div style="background: #f8f9fa; padding: 15px; border-radius: 8px; border: 2px solid #dee2e6;">
                        <div style="display: flex; align-items: center; margin-bottom: 12px;">
                            <span style="font-size: 18px; margin-right: 8px;">📄</span>
                            <h4 style="margin: 0; color: #495057; font-size: 15px;">Invoice Says (Raw OCR)</h4>
                        </div>
                        <div style="font-size: 13px; color: #333; line-height: 1.8;">
                            <div><strong>Name:</strong> ${invoiceVendor.name || 'Unknown'}</div>
                            ${vendorMatch.resolved_vendor_name ? `
                                <div style="margin-top: 6px; padding: 8px; background: #fff3cd; border-left: 3px solid #ffc107; border-radius: 4px;">
                                    <div style="font-size: 11px; color: #856404; margin-bottom: 4px;">🧠 Layer 3.5 AI Resolution:</div>
                                    <div style="color: #856404;"><strong>Resolved to:</strong> ${escapeHtml(vendorMatch.resolved_vendor_name)}</div>
                                </div>
                            ` : ''}
                            <div style="margin-top: 6px;"><strong>Tax ID:</strong> ${invoiceVendor.tax_id || 'Unknown'}</div>
                            <div style="margin-top: 6px;"><strong>Address:</strong> ${invoiceVendor.address || 'Unknown'}</div>
                            <div style="margin-top: 6px;"><strong>Country:</strong> ${invoiceVendor.country || 'Unknown'}</div>
                            ${invoiceVendor.email && invoiceVendor.email !== 'Unknown' ? `<div style="margin-top: 6px;"><strong>Email:</strong> ${invoiceVendor.email}</div>` : ''}
                            ${invoiceVendor.phone && invoiceVendor.phone !== 'Unknown' ? `<div style="margin-top: 6px;"><strong>Phone:</strong> ${invoiceVendor.phone}</div>` : ''}
                        </div>
                    </div>
                    
                    <!-- Right: What the Database Says -->
                    <div style="background: ${databaseVendor ? '#e8f5e9' : '#fff3e0'}; padding: 15px; border-radius: 8px; border: 2px solid ${databaseVendor ? '#4caf50' : '#ff9800'};">
                        <div style="display: flex; align-items: center; margin-bottom: 12px;">
                            <span style="font-size: 18px; margin-right: 8px;">${databaseVendor ? '💾' : '❓'}</span>
                            <h4 style="margin: 0; color: ${databaseVendor ? '#2e7d32' : '#e65100'}; font-size: 15px;">Database Says</h4>
                        </div>
                        ${databaseVendor && databaseVendor.name ? `
                            <div style="font-size: 13px; color: #333; line-height: 1.8;">
                                <div><strong>Name:</strong> ${escapeHtml(databaseVendor.name)}</div>
                                <div style="margin-top: 6px;"><strong>Vendor ID:</strong> <code style="background: #fff; padding: 2px 6px; border-radius: 3px; font-size: 12px;">${escapeHtml(databaseVendor.vendor_id || 'N/A')}</code></div>
                                <div style="margin-top: 6px;"><strong>Tax ID:</strong> ${escapeHtml(databaseVendor.tax_id || 'Unknown')}</div>
                                ${databaseVendor.addresses && Array.isArray(databaseVendor.addresses) && databaseVendor.addresses.length > 0 ? `<div style="margin-top: 6px;"><strong>Address:</strong> ${escapeHtml(databaseVendor.addresses[0])}</div>` : ''}
                                ${databaseVendor.countries && Array.isArray(databaseVendor.countries) && databaseVendor.countries.length > 0 ? `<div style="margin-top: 6px;"><strong>Countries:</strong> ${databaseVendor.countries.map(c => escapeHtml(c)).join(', ')}</div>` : ''}
                                ${databaseVendor.emails && Array.isArray(databaseVendor.emails) && databaseVendor.emails.length > 0 ? `<div style="margin-top: 6px;"><strong>Emails:</strong> ${databaseVendor.emails.map(e => escapeHtml(e)).join(', ')}</div>` : ''}
                                ${databaseVendor.domains && Array.isArray(databaseVendor.domains) && databaseVendor.domains.length > 0 ? `<div style="margin-top: 6px;"><strong>Domains:</strong> ${databaseVendor.domains.map(d => escapeHtml(d)).join(', ')}</div>` : ''}
                            </div>
                        ` : `
                            <div style="font-size: 13px; color: #666; line-height: 1.8; font-style: italic;">
                                Not found in database
                            </div>
                        `}
                    </div>
                </div>
                
                <!-- Supreme Judge Reasoning -->
                <div style="background: white; padding: 15px; border-radius: 8px; border-left: 4px solid #667eea; margin-bottom: 15px;">
                    <div style="display: flex; align-items: center; margin-bottom: 8px;">
                        <span style="font-size: 16px; margin-right: 8px;">⚖️</span>
                        <strong style="color: #667eea;">Supreme Judge Reasoning</strong>
                    </div>
                    <p style="margin: 0; color: #555; font-size: 14px; line-height: 1.6;">${reasoning}</p>
                </div>
                
                <!-- Evidence Breakdown Panel -->
                ${vendorMatch.evidence_breakdown ? `
                <div style="background: white; padding: 15px; border-radius: 8px; border-left: 4px solid #4caf50; margin-bottom: 15px;">
                    <div style="display: flex; align-items: center; margin-bottom: 12px;">
                        <span style="font-size: 16px; margin-right: 8px;">🔍</span>
                        <strong style="color: #4caf50;">Evidence Analysis</strong>
                    </div>
                    <div style="border-bottom: 2px solid #e0e0e0; margin-bottom: 15px;"></div>
                    
                    <!-- Gold Tier Evidence -->
                    ${vendorMatch.evidence_breakdown.gold_tier && vendorMatch.evidence_breakdown.gold_tier.length > 0 ? `
                    <div style="margin-bottom: 15px;">
                        <div style="display: flex; align-items: center; margin-bottom: 10px;">
                            <span style="font-size: 20px; margin-right: 8px;">🥇</span>
                            <strong class="evidence-tier-title gold">GOLD TIER EVIDENCE</strong>
                            <span style="margin-left: 8px; font-size: 12px; color: #666;">(Definitive Proof)</span>
                        </div>
                        ${vendorMatch.evidence_breakdown.gold_tier.map(evidence => `
                            <div class="evidence-item gold">
                                <div style="display: flex; align-items: flex-start; margin-bottom: 5px;">
                                    <span style="font-size: 16px; margin-right: 8px;">${evidence.icon}</span>
                                    <div style="flex: 1;">
                                        <strong>${evidence.field} Match:</strong> 
                                        <span style="color: #555;">"${escapeHtml(evidence.invoice_value)}" == "${escapeHtml(evidence.database_value)}"</span>
                                    </div>
                                </div>
                                <div style="margin-left: 24px; font-size: 13px; color: #666;">
                                    Confidence: <span class="confidence-badge" style="background: linear-gradient(135deg, #FFD700 0%, #FFA500 100%); color: #000;">+${evidence.confidence_contribution.toFixed(1)}%</span>
                                </div>
                            </div>
                        `).join('')}
                    </div>
                    ` : ''}
                    
                    <!-- Silver Tier Evidence -->
                    ${vendorMatch.evidence_breakdown.silver_tier && vendorMatch.evidence_breakdown.silver_tier.length > 0 ? `
                    <div style="margin-bottom: 15px;">
                        <div style="display: flex; align-items: center; margin-bottom: 10px;">
                            <span style="font-size: 20px; margin-right: 8px;">🥈</span>
                            <strong class="evidence-tier-title silver">SILVER TIER EVIDENCE</strong>
                            <span style="margin-left: 8px; font-size: 12px; color: #666;">(Strong Evidence)</span>
                        </div>
                        ${vendorMatch.evidence_breakdown.silver_tier.map(evidence => `
                            <div class="evidence-item silver">
                                <div style="display: flex; align-items: flex-start;">
                                    <span style="font-size: 16px; margin-right: 8px;">${evidence.icon}</span>
                                    <div style="flex: 1;">
                                        <strong>${evidence.field}:</strong> 
                                        ${evidence.matched ? 
                                            `<span style="color: #555;">"${escapeHtml(evidence.invoice_value)}" == "${escapeHtml(evidence.database_value)}"</span>` :
                                            `<span style="color: #999;">${evidence.reason}</span>`
                                        }
                                    </div>
                                </div>
                                ${evidence.matched ? `
                                <div style="margin-left: 24px; font-size: 13px; color: #666; margin-top: 5px;">
                                    Confidence: <span class="confidence-badge" style="background: linear-gradient(135deg, #C0C0C0 0%, #A8A8A8 100%); color: #000;">+${evidence.confidence_contribution.toFixed(1)}%</span>
                                </div>
                                ` : ''}
                            </div>
                        `).join('')}
                    </div>
                    ` : ''}
                    
                    <!-- Bronze Tier Evidence -->
                    ${vendorMatch.evidence_breakdown.bronze_tier && vendorMatch.evidence_breakdown.bronze_tier.length > 0 ? `
                    <div style="margin-bottom: 15px;">
                        <div style="display: flex; align-items: center; margin-bottom: 10px;">
                            <span style="font-size: 20px; margin-right: 8px;">🥉</span>
                            <strong class="evidence-tier-title bronze">BRONZE TIER EVIDENCE</strong>
                            <span style="margin-left: 8px; font-size: 12px; color: #666;">(Circumstantial)</span>
                        </div>
                        ${vendorMatch.evidence_breakdown.bronze_tier.map(evidence => `
                            <div class="evidence-item bronze">
                                <div style="display: flex; align-items: flex-start;">
                                    <span style="font-size: 16px; margin-right: 8px;">${evidence.icon}</span>
                                    <div style="flex: 1;">
                                        <strong>${evidence.field}:</strong> 
                                        <span style="color: #999;">${evidence.reason}</span>
                                    </div>
                                </div>
                            </div>
                        `).join('')}
                    </div>
                    ` : ''}
                    
                    <!-- Total Confidence -->
                    <div style="border-top: 2px solid #e0e0e0; padding-top: 15px; text-align: center;">
                        <strong style="font-size: 16px; color: #333;">TOTAL CONFIDENCE: </strong>
                        <span style="font-size: 20px; font-weight: bold; color: #4caf50;">${vendorMatch.evidence_breakdown.total_confidence}%</span>
                    </div>
                </div>
                ` : ''}
                
                <!-- Action Buttons -->
                <div style="display: flex; gap: 10px; justify-content: flex-end;">
                    ${verdict === 'MATCH' ? `
                        <button style="padding: 10px 20px; background: #4caf50; color: white; border: none; border-radius: 6px; cursor: pointer; font-weight: bold; font-size: 14px;" disabled>
                            ✅ Vendor Matched
                        </button>
                    ` : verdict === 'NEW_VENDOR' ? `
                        <button onclick="alert('Add to Database feature coming soon!')" style="padding: 10px 20px; background: #2196f3; color: white; border: none; border-radius: 6px; cursor: pointer; font-weight: bold; font-size: 14px;">
                            ➕ Add Vendor to Database
                        </button>
                    ` : verdict === 'AMBIGUOUS' ? `
                        <button onclick="alert('Manual review feature coming soon!')" style="padding: 10px 20px; background: #ff9800; color: white; border: none; border-radius: 6px; cursor: pointer; font-weight: bold; font-size: 14px;">
                            ⚠️ Review Match
                        </button>
                    ` : ''}
                </div>
            </div>
        `;
    } else {
        console.log('⚠️ vendor_match NOT found in response data');
    }
    
    // Invoice Details Section
    if (displayData.invoiceNumber || displayData.issueDate) {
        html += `
            <div class="result-section">
                <h3>📋 Invoice Details</h3>
                <div class="result-grid">
                    ${displayData.invoiceNumber ? `<div class="result-item"><strong>Invoice Number</strong><span>${displayData.invoiceNumber}</span></div>` : ''}
                    ${displayData.issueDate ? `<div class="result-item"><strong>Issue Date</strong><span>${displayData.issueDate}</span></div>` : ''}
                    ${displayData.dueDate ? `<div class="result-item"><strong>Due Date</strong><span>${displayData.dueDate}</span></div>` : ''}
                    ${displayData.paymentTerms ? `<div class="result-item"><strong>Payment Terms</strong><span>${displayData.paymentTerms}</span></div>` : ''}
                </div>
            </div>
        `;
    }
    
    // Buyer Information (if present)
    if (displayData.buyer && displayData.buyer.name) {
        const buyer = displayData.buyer;
        html += `
            <div class="result-section">
                <h3>🛒 Buyer Information</h3>
                <div class="result-grid">
                    ${buyer.name ? `<div class="result-item"><strong>Name</strong><span>${buyer.name}</span></div>` : ''}
                    ${buyer.country ? `<div class="result-item"><strong>Country</strong><span>${buyer.country}</span></div>` : ''}
                    ${buyer.taxId ? `<div class="result-item"><strong>Tax ID</strong><span>${buyer.taxId}</span></div>` : ''}
                </div>
                ${buyer.address ? `<div class="result-item" style="margin-top: 10px;"><strong>Address</strong><span>${buyer.address}</span></div>` : ''}
            </div>
        `;
    }
    
    // Totals Section
    if (displayData.totals) {
        const totals = displayData.totals;
        html += `
            <div class="result-section">
                <h3>💰 Financial Summary</h3>
                <div class="result-grid">
                    ${totals.subtotal ? `<div class="result-item"><strong>Subtotal</strong><span>${displayData.currency} ${totals.subtotal.toLocaleString()}</span></div>` : ''}
                    ${totals.tax ? `<div class="result-item"><strong>Tax ${totals.taxPercent ? '(' + totals.taxPercent + '%)' : ''}</strong><span>${displayData.currency} ${totals.tax.toLocaleString()}</span></div>` : ''}
                    ${totals.discounts ? `<div class="result-item"><strong>Discounts</strong><span>-${displayData.currency} ${totals.discounts.toLocaleString()}</span></div>` : ''}
                    ${totals.fees ? `<div class="result-item"><strong>Fees</strong><span>${displayData.currency} ${totals.fees.toLocaleString()}</span></div>` : ''}
                    ${totals.shipping ? `<div class="result-item"><strong>Shipping</strong><span>${displayData.currency} ${totals.shipping.toLocaleString()}</span></div>` : ''}
                    ${totals.total ? `<div class="result-item" style="background: #e8f5e9; font-weight: bold;"><strong>Grand Total</strong><span>${displayData.currency} ${totals.total.toLocaleString()}</span></div>` : ''}
                </div>
            </div>
        `;
    }
    
    // Line Items Section
    if (displayData.lineItems && displayData.lineItems.length > 0) {
        html += `
            <div class="result-section">
                <h3>📦 Line Items</h3>
                <table class="line-items">
                    <thead>
                        <tr>
                            <th>Description</th>
                            <th>Qty</th>
                            <th>Unit Price</th>
                            <th>Tax</th>
                            <th>Subtotal</th>
                            <th>✓</th>
                        </tr>
                    </thead>
                    <tbody>
        `;
        
        displayData.lineItems.forEach(item => {
            const mathIcon = item.mathVerified === false ? '⚠' : item.mathVerified === true ? '✓' : '-';
            const mathColor = item.mathVerified === false ? 'color: #ff9800;' : item.mathVerified === true ? 'color: #4caf50;' : '';
            html += `
                <tr>
                    <td>${item.description || '-'}${item.category ? `<br><small style="color: #888;">${item.category}</small>` : ''}</td>
                    <td>${item.quantity || '-'}</td>
                    <td>${item.currency || displayData.currency} ${item.unitPrice ? item.unitPrice.toLocaleString() : '-'}</td>
                    <td>${item.taxPercent ? item.taxPercent + '%' : '-'}</td>
                    <td>${item.lineSubtotal ? item.lineSubtotal.toLocaleString() : '-'}</td>
                    <td style="${mathColor} font-weight: bold;">${mathIcon}</td>
                </tr>
            `;
        });
        
        html += `
                    </tbody>
                </table>
            </div>
        `;
    }
    
    // Payment Details Section
    if (displayData.paymentDetails && (displayData.paymentDetails.iban || displayData.paymentDetails.bankName)) {
        const payment = displayData.paymentDetails;
        html += `
            <div class="result-section">
                <h3>💳 Payment Details</h3>
                <div class="result-grid">
                    ${payment.bankName ? `<div class="result-item"><strong>Bank</strong><span>${payment.bankName}</span></div>` : ''}
                    ${payment.iban ? `<div class="result-item"><strong>IBAN</strong><span>${payment.iban}</span></div>` : ''}
                    ${payment.swift ? `<div class="result-item"><strong>SWIFT/BIC</strong><span>${payment.swift}</span></div>` : ''}
                    ${payment.accountNumber ? `<div class="result-item"><strong>Account Number</strong><span>${payment.accountNumber}</span></div>` : ''}
                </div>
                ${payment.paymentInstructions ? `<div class="result-item" style="margin-top: 10px;"><strong>Instructions</strong><span>${payment.paymentInstructions}</span></div>` : ''}
            </div>
        `;
    }
    
    // AI Reasoning Section
    if (displayData.reasoning) {
        html += `
            <div class="result-section">
                <h3>🧠 AI Reasoning</h3>
                <div style="background: #f5f5f5; padding: 15px; border-radius: 6px; border-left: 4px solid #667eea;">
                    <p style="margin: 0; color: #555; line-height: 1.6;">${displayData.reasoning}</p>
                </div>
            </div>
        `;
    }
    
    // Warnings Section
    if (displayData.warnings && displayData.warnings.length > 0) {
        html += `
            <div class="result-section">
                <h3>⚠ Warnings & Flags</h3>
                <ul class="validation-flags">
                    ${displayData.warnings.map(warning => `<li>${warning}</li>`).join('')}
                </ul>
            </div>
        `;
    }
    
    // Raw Data Debug Section
    html += `
        <details style="margin-top: 30px; padding: 15px; background: #f9f9f9; border-radius: 6px;">
            <summary style="cursor: pointer; font-weight: 600; color: #667eea;">🔍 View Complete JSON Response</summary>
            <pre style="background: #fff; padding: 15px; border-radius: 6px; overflow-x: auto; margin-top: 10px; border: 1px solid #e0e0e0; max-height: 500px; overflow-y: auto;">${JSON.stringify(data, null, 2)}</pre>
        </details>
    `;
    
    resultContent.innerHTML = html;
    
    // Start the perfect workflow after displaying results
    if (typeof invoiceWorkflow !== 'undefined') {
        setTimeout(() => {
            invoiceWorkflow.startWorkflow(invoiceWorkflowData);
        }, 1500); // Small delay to let user see the invoice details first
    }
}

function buildLayerStatusView(layers) {
    let html = `
        <div class="layer-pipeline">
            <h3 style="color: #667eea; margin-bottom: 20px;">🔍 Processing Pipeline</h3>
    `;
    
    const layer1 = layers.layer1_document_ai || {};
    const layer2 = layers.layer2_vertex_search || {};
    const layer3 = layers.layer3_gemini || {};
    
    html += buildLayerCard(
        '1',
        'Document AI - Structure Extraction',
        layer1.status || 'unknown',
        layer1.error,
        `
            ${layer1.text_length ? `<div class="layer-detail"><strong>Text Extracted:</strong> ${layer1.text_length.toLocaleString()} characters</div>` : ''}
            ${layer1.entity_types ? `<div class="layer-detail"><strong>Entity Types Found:</strong> ${layer1.entity_types.length}</div>` : ''}
            ${layer1.entity_types ? `<div class="layer-detail-small">${layer1.entity_types.join(', ')}</div>` : ''}
        `
    );
    
    html += buildLayerCard(
        '2',
        'Vertex Search (RAG) - Context Retrieval',
        layer2.status || 'unknown',
        layer2.error,
        `
            ${layer2.vendor_query ? `<div class="layer-detail"><strong>Vendor Query:</strong> "${layer2.vendor_query}"</div>` : '<div class="layer-detail"><em>No vendor name extracted</em></div>'}
            ${layer2.matches_found !== undefined ? `<div class="layer-detail"><strong>Database Matches:</strong> ${layer2.matches_found}</div>` : ''}
            ${layer2.error ? `<div class="layer-detail" style="color: #ff9800;"><strong>Issue:</strong> ${layer2.error}</div>` : ''}
        `
    );
    
    html += buildLayerCard(
        '3',
        'Gemini - Semantic Validation',
        layer3.status || 'unknown',
        layer3.error,
        `
            ${layer3.validation_flags && layer3.validation_flags.length > 0 ? `
                <div class="layer-detail"><strong>Validation Flags:</strong></div>
                <ul class="validation-flags">
                    ${layer3.validation_flags.map(flag => `<li>${flag}</li>`).join('')}
                </ul>
            ` : layer3.status === 'success' ? '<div class="layer-detail">✓ All validations passed</div>' : ''}
            ${layer3.error ? `<div class="layer-detail" style="color: #ff9800;"><strong>Error:</strong> ${layer3.error}</div>` : ''}
        `
    );
    
    html += `</div>`;
    return html;
}

function buildLayerCard(number, title, status, error, content) {
    const statusIcon = status === 'success' ? '✓' : status === 'error' ? '✗' : status === 'warning' || status === 'completed_with_warnings' ? '⚠' : '○';
    const statusClass = status === 'success' ? 'layer-success' : status === 'error' ? 'layer-error' : status === 'warning' || status === 'completed_with_warnings' ? 'layer-warning' : 'layer-unknown';
    
    return `
        <div class="layer-card ${statusClass}">
            <div class="layer-header">
                <span class="layer-number">${number}</span>
                <h4>${title}</h4>
                <span class="layer-status">${statusIcon}</span>
            </div>
            <div class="layer-content">
                ${content}
            </div>
        </div>
    `;
}

// ===== CSV UPLOAD HANDLERS =====

// CSV Drag & Drop
csvUploadArea.addEventListener('click', () => csvFileInput.click());

csvUploadArea.addEventListener('dragover', (e) => {
    e.preventDefault();
    csvUploadArea.style.borderColor = '#667eea';
    csvUploadArea.style.background = 'rgba(102, 126, 234, 0.05)';
});

csvUploadArea.addEventListener('dragleave', () => {
    csvUploadArea.style.borderColor = '#e0e0e0';
    csvUploadArea.style.background = 'white';
});

csvUploadArea.addEventListener('drop', (e) => {
    e.preventDefault();
    csvUploadArea.style.borderColor = '#e0e0e0';
    csvUploadArea.style.background = 'white';
    
    const file = e.dataTransfer.files[0];
    if (file && (file.name.endsWith('.csv') || file.name.endsWith('.txt'))) {
        csvFileInput.files = e.dataTransfer.files;
        selectedCsvFile = file;
        csvSubmitBtn.disabled = false;
        csvUploadArea.querySelector('p').textContent = `📄 ${file.name} (${(file.size / 1024).toFixed(1)} KB)`;
    } else {
        alert('Please upload a CSV or TXT file');
    }
});

csvFileInput.addEventListener('change', (e) => {
    const file = e.target.files[0];
    if (file) {
        selectedCsvFile = file;
        csvSubmitBtn.disabled = false;
        csvUploadArea.querySelector('p').textContent = `📄 ${file.name} (${(file.size / 1024).toFixed(1)} KB)`;
    }
});

// Step 1: Analyze CSV
csvUploadForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    
    if (!selectedCsvFile) {
        alert('Please select a CSV file');
        return;
    }
    
    const formData = new FormData();
    formData.append('file', selectedCsvFile);
    
    csvSubmitBtn.disabled = true;
    csvSubmitBtn.textContent = '🧠 Analyzing...';
    csvLoading.classList.remove('hidden');
    csvMappingReview.classList.add('hidden');
    csvImportResults.classList.add('hidden');
    
    try {
        const response = await fetch('/api/vendors/csv/analyze', {
            method: 'POST',
            body: formData
        });
        
        const data = await response.json();
        
        if (!response.ok) {
            throw new Error(data.error || 'Analysis failed');
        }
        
        csvAnalysisData = data;
        console.log('✓ CSV analysis complete. Upload ID:', data.uploadId);
        displayCsvMapping(data);
        
    } catch (error) {
        alert('CSV analysis failed: ' + error.message);
        csvSubmitBtn.disabled = false;
        csvSubmitBtn.textContent = '🧠 Analyze CSV with AI';
    } finally {
        csvLoading.classList.add('hidden');
    }
});

// Display AI-generated column mapping
function displayCsvMapping(data) {
    const analysis = data.analysis;
    const mapping = analysis.columnMapping;
    
    let html = `
        <div style="background: white; padding: 20px; border-radius: 8px; margin-bottom: 15px;">
            <h4 style="margin-top: 0;">📋 CSV Analysis Summary</h4>
            <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; margin-bottom: 20px;">
                <div style="background: #f0f4ff; padding: 12px; border-radius: 6px;">
                    <div style="font-size: 12px; color: #666;">Detected Language</div>
                    <div style="font-size: 18px; font-weight: 700;">${analysis.detectedLanguage || 'Unknown'}</div>
                </div>
                <div style="background: #f0f4ff; padding: 12px; border-radius: 6px;">
                    <div style="font-size: 12px; color: #666;">Source System</div>
                    <div style="font-size: 18px; font-weight: 700;">${analysis.sourceSystemGuess || 'Unknown'}</div>
                </div>
                <div style="background: #f0f4ff; padding: 12px; border-radius: 6px;">
                    <div style="font-size: 12px; color: #666;">Total Columns</div>
                    <div style="font-size: 18px; font-weight: 700;">${analysis.totalColumns || 0}</div>
                </div>
                <div style="background: #e8f5e9; padding: 12px; border-radius: 6px;">
                    <div style="font-size: 12px; color: #666;">Overall Confidence</div>
                    <div style="font-size: 18px; font-weight: 700;">${((analysis.overallConfidence || 0) * 100).toFixed(0)}%</div>
                </div>
            </div>
            
            <div style="background: #fff3e0; padding: 15px; border-radius: 6px; margin-bottom: 20px;">
                <strong>🧠 AI Reasoning:</strong>
                <p style="margin: 10px 0 0 0; line-height: 1.6;">${analysis.mappingReasoning || 'No reasoning provided'}</p>
            </div>
        </div>
        
        <h4>📊 Column Mappings</h4>
        <div style="overflow-x: auto;">
            <table style="width: 100%; border-collapse: collapse; background: white; border-radius: 8px; overflow: hidden;">
                <thead>
                    <tr style="background: #667eea; color: white;">
                        <th style="padding: 12px; text-align: left;">CSV Column</th>
                        <th style="padding: 12px; text-align: left;">Maps To</th>
                        <th style="padding: 12px; text-align: center;">Confidence</th>
                        <th style="padding: 12px; text-align: left;">AI Reasoning</th>
                    </tr>
                </thead>
                <tbody>
    `;
    
    for (const [csvColumn, mappingInfo] of Object.entries(mapping)) {
        const confidence = ((mappingInfo.confidence || 0) * 100).toFixed(0);
        const confidenceColor = confidence >= 80 ? '#4caf50' : confidence >= 60 ? '#ff9800' : '#f44336';
        
        html += `
            <tr style="border-bottom: 1px solid #e0e0e0;">
                <td style="padding: 12px; font-weight: 600;">${csvColumn}</td>
                <td style="padding: 12px;">
                    <code style="background: #f5f5f5; padding: 4px 8px; border-radius: 4px; font-size: 13px;">
                        ${mappingInfo.targetField || 'N/A'}
                    </code>
                </td>
                <td style="padding: 12px; text-align: center;">
                    <span style="color: ${confidenceColor}; font-weight: 700;">${confidence}%</span>
                </td>
                <td style="padding: 12px; font-size: 13px; color: #666;">${mappingInfo.reasoning || 'N/A'}</td>
            </tr>
        `;
    }
    
    html += `
                </tbody>
            </table>
        </div>
    `;
    
    if (analysis.dataQualityWarnings && analysis.dataQualityWarnings.length > 0) {
        html += `
            <div style="background: #ffebee; padding: 15px; border-radius: 6px; margin-top: 20px;">
                <strong>⚠️ Data Quality Warnings:</strong>
                <ul style="margin: 10px 0 0 20px; line-height: 1.8;">
                    ${analysis.dataQualityWarnings.map(w => `<li>${w}</li>`).join('')}
                </ul>
            </div>
        `;
    }
    
    csvMappingContent.innerHTML = html;
    csvMappingReview.classList.remove('hidden');
    csvSubmitBtn.disabled = false;
    csvSubmitBtn.textContent = '🧠 Analyze CSV with AI';
}

// Step 2: Import CSV to BigQuery with SSE progress streaming
csvImportBtn.addEventListener('click', async () => {
    if (!csvAnalysisData) {
        alert('No CSV analysis data found. Please analyze CSV first.');
        return;
    }
    
    csvImportBtn.disabled = true;
    csvImportBtn.textContent = '⏳ Importing to BigQuery...';
    
    // Show progress container
    const csvImportProgressDiv = document.getElementById('csvImportProgress');
    csvImportProgressDiv.classList.remove('hidden');
    csvImportProgressDiv.innerHTML = '<div class="loading"><div class="spinner"></div><p>Starting CSV import...</p></div>';
    
    // Hide previous results
    csvImportResults.classList.add('hidden');
    
    try {
        csvImportProgressDiv.innerHTML = '<div class="loading"><div class="spinner"></div><p>Importing to BigQuery...</p></div>';
        
        const importResponse = await fetch('/api/vendors/csv/import', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                uploadId: csvAnalysisData.uploadId,
                columnMapping: csvAnalysisData.analysis.columnMapping,
                sourceSystem: csvAnalysisData.analysis.sourceSystemGuess || 'csv_upload'
            })
        });
        
        const data = await importResponse.json();
        
        csvImportProgressDiv.classList.add('hidden');
        csvImportBtn.disabled = false;
        csvImportBtn.textContent = '✅ Confirm & Import to BigQuery';
        
        if (!importResponse.ok || data.error) {
            throw new Error(data.error || 'Import failed');
        }
        
        displayCsvImportResults(data);
        
    } catch (error) {
        csvImportProgressDiv.classList.add('hidden');
        csvImportBtn.disabled = false;
        csvImportBtn.textContent = '✅ Confirm & Import to BigQuery';
        
        csvImportResults.innerHTML = `
            <div style="padding: 20px; background: #ffebee; border-left: 4px solid #f44336; border-radius: 6px;">
                <h3 style="color: #c62828; margin: 0 0 10px 0;">❌ Import Failed</h3>
                <p style="margin: 0; color: #666;">${error.message}</p>
            </div>
        `;
        csvImportResults.classList.remove('hidden');
    }
});

// Display import results
function displayCsvImportResults(data) {
    let html = `
        <div style="text-align: center; padding: 20px;">
            <h3 style="color: #4caf50; margin-bottom: 20px;">✅ Import Completed Successfully!</h3>
            
            <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 15px; margin: 20px 0;">
                <div style="background: #e8f5e9; padding: 20px; border-radius: 8px;">
                    <div style="font-size: 14px; color: #666;">Vendors Processed</div>
                    <div style="font-size: 32px; font-weight: 700; color: #2e7d32;">${data.vendorsProcessed || 0}</div>
                </div>
                <div style="background: #e3f2fd; padding: 20px; border-radius: 8px;">
                    <div style="font-size: 14px; color: #666;">New Vendors</div>
                    <div style="font-size: 32px; font-weight: 700; color: #1976d2;">${data.inserted || 0}</div>
                </div>
                <div style="background: #fff3e0; padding: 20px; border-radius: 8px;">
                    <div style="font-size: 14px; color: #666;">Updated Vendors</div>
                    <div style="font-size: 32px; font-weight: 700; color: #f57c00;">${data.updated || 0}</div>
                </div>
            </div>
            
            <p style="color: #666; margin-top: 20px;">
                ✓ Data successfully imported to BigQuery table: <code>global_vendors</code>
            </p>
        </div>
    `;
    
    if (data.errors && data.errors.length > 0) {
        html += `
            <div style="background: #ffebee; padding: 15px; border-radius: 6px; margin-top: 20px;">
                <strong>⚠️ Errors (${data.errors.length}):</strong>
                <ul style="margin: 10px 0 0 20px; line-height: 1.8;">
                    ${data.errors.map(e => {
                        // Handle different error formats
                        if (typeof e === 'string') {
                            return `<li>${e}</li>`;
                        } else if (e.errors && Array.isArray(e.errors)) {
                            // BigQuery error format: {index: 0, errors: [{message: "..."}]}
                            return e.errors.map(err => `<li>Row ${e.index + 1}: ${err.message || JSON.stringify(err)}</li>`).join('');
                        } else if (e.message) {
                            return `<li>${e.message}</li>`;
                        } else {
                            return `<li>${JSON.stringify(e)}</li>`;
                        }
                    }).join('')}
                </ul>
            </div>
        `;
    }
    
    csvImportResults.innerHTML = html;
    csvImportResults.classList.remove('hidden');
    
    // Reset upload form
    csvMappingReview.classList.add('hidden');
    csvUploadArea.querySelector('p').textContent = 'Drag & drop your vendor CSV here or click to browse';
    csvSubmitBtn.disabled = true;
    selectedCsvFile = null;
    csvAnalysisData = null;
}

// Cancel button
csvCancelBtn.addEventListener('click', () => {
    csvMappingReview.classList.add('hidden');
    csvImportResults.classList.add('hidden');
    csvUploadArea.querySelector('p').textContent = 'Drag & drop your vendor CSV here or click to browse';
    csvSubmitBtn.disabled = true;
    selectedCsvFile = null;
    csvAnalysisData = null;
});

// ===== VENDOR DATABASE BROWSER =====

const vendorSearchInput = document.getElementById('vendorSearchInput');
const vendorLoading = document.getElementById('vendorLoading');
const vendorEmptyState = document.getElementById('vendorEmptyState');
const vendorListContainer = document.getElementById('vendorListContainer');
const vendorPagination = document.getElementById('vendorPagination');
const vendorPrevBtn = document.getElementById('vendorPrevBtn');
const vendorNextBtn = document.getElementById('vendorNextBtn');
const vendorPageInfo = document.getElementById('vendorPageInfo');
const vendorStats = document.getElementById('vendorStats');

let currentVendorPage = 1;
let currentVendorLimit = 20;
let totalVendorPages = 0;
let allVendors = [];
let filteredVendors = [];
let searchTimeout = null;
let currentSearchTerm = '';

async function loadVendorList(page = 1, searchTerm = '') {
    currentVendorPage = page;
    currentSearchTerm = searchTerm;
    
    vendorLoading.classList.remove('hidden');
    vendorEmptyState.classList.add('hidden');
    vendorListContainer.innerHTML = '';
    vendorPagination.classList.add('hidden');
    
    try {
        let url = `/api/vendors/list?page=${page}&limit=${currentVendorLimit}`;
        if (searchTerm) {
            url += `&search=${encodeURIComponent(searchTerm)}`;
        }
        
        const response = await fetch(url);
        const data = await response.json();
        
        vendorLoading.classList.add('hidden');
        
        if (!data.vendors || data.vendors.length === 0) {
            vendorEmptyState.classList.remove('hidden');
            vendorStats.innerHTML = '';
            return;
        }
        
        allVendors = data.vendors;
        filteredVendors = allVendors;
        totalVendorPages = data.total_pages;
        
        renderVendorStats(data.total_count, page, data.limit);
        renderVendorList(filteredVendors);
        renderVendorPagination(page, totalVendorPages, data.total_count);
        
    } catch (error) {
        vendorLoading.classList.add('hidden');
        vendorListContainer.innerHTML = `
            <div style="background: #ffebee; padding: 20px; border-radius: 8px; color: #c62828;">
                <strong>Error loading vendors:</strong> ${error.message}
            </div>
        `;
    }
}

function renderVendorStats(totalCount, currentPage, limit) {
    const startItem = (currentPage - 1) * limit + 1;
    const endItem = Math.min(currentPage * limit, totalCount);
    
    vendorStats.innerHTML = `
        <div style="background: #e8f5e9; padding: 12px 20px; border-radius: 8px; flex: 1; text-align: center; border-left: 4px solid #4caf50;">
            <div style="font-size: 24px; font-weight: bold; color: #2e7d32;">${totalCount}</div>
            <div style="font-size: 13px; color: #666; margin-top: 4px;">Total Vendors</div>
        </div>
        <div style="background: #e3f2fd; padding: 12px 20px; border-radius: 8px; flex: 1; text-align: center; border-left: 4px solid #2196f3;">
            <div style="font-size: 24px; font-weight: bold; color: #1976d2;">${startItem}-${endItem}</div>
            <div style="font-size: 13px; color: #666; margin-top: 4px;">Showing</div>
        </div>
        <div style="background: #f3e5f5; padding: 12px 20px; border-radius: 8px; flex: 1; text-align: center; border-left: 4px solid #9c27b0;">
            <div style="font-size: 24px; font-weight: bold; color: #7b1fa2;">${totalVendorPages}</div>
            <div style="font-size: 13px; color: #666; margin-top: 4px;">Total Pages</div>
        </div>
    `;
}

function renderVendorList(vendors) {
    if (vendors.length === 0) {
        vendorListContainer.innerHTML = `
            <div style="text-align: center; padding: 40px; color: #999;">
                <p>No vendors match your search criteria</p>
            </div>
        `;
        return;
    }
    
    const html = vendors.map((vendor, idx) => {
        const vendorId = `vendor-${currentVendorPage}-${idx}`;
        const lastUpdated = vendor.last_updated ? new Date(vendor.last_updated).toLocaleString() : 'N/A';
        const createdAt = vendor.created_at ? new Date(vendor.created_at).toLocaleString() : 'N/A';
        
        // Determine NetSuite sync status
        let syncStatusBadge = '';
        let syncStatusClass = '';
        
        if (vendor.netsuite_internal_id) {
            const lastSync = vendor.netsuite_last_sync ? new Date(vendor.netsuite_last_sync).toLocaleString() : 'Unknown';
            syncStatusClass = 'synced';
            syncStatusBadge = `<span class="sync-badge sync-success" title="Last sync: ${lastSync}">✅ NetSuite</span>`;
        } else if (vendor.netsuite_sync_status === 'failed') {
            syncStatusClass = 'sync-failed';
            syncStatusBadge = `<span class="sync-badge sync-failed" title="${vendor.netsuite_sync_error || 'Sync failed'}">❌ Failed</span>`;
        } else {
            syncStatusClass = 'not-synced';
            syncStatusBadge = `<span class="sync-badge sync-pending">⚠️ Not Synced</span>`;
        }
        
        return `
            <div class="vendor-card ${syncStatusClass}" id="${vendorId}">
                <div class="vendor-card-header" onclick="toggleVendorDetails('${vendorId}')">
                    <div style="flex: 1;">
                        <h3 class="vendor-name">${vendor.global_name}</h3>
                        <div class="vendor-meta">
                            <span class="vendor-id">ID: ${vendor.vendor_id}</span>
                            <span class="vendor-source">${vendor.source_system || 'Unknown'}</span>
                            ${syncStatusBadge}
                        </div>
                    </div>
                    <div class="vendor-expand-icon">▼</div>
                </div>
                
                <div class="vendor-card-details hidden">
                    <div class="vendor-detail-section">
                        <strong>📧 Contact Information</strong>
                        <div style="margin-top: 10px;">
                            ${vendor.emails && vendor.emails.length > 0 ? `
                                <div style="margin-bottom: 8px;">
                                    <span style="font-size: 13px; color: #666;">Emails:</span><br>
                                    <div class="badge-container">
                                        ${vendor.emails.map(email => `<span class="badge badge-email">${email}</span>`).join('')}
                                    </div>
                                </div>
                            ` : '<div style="color: #999; font-size: 13px;">No emails</div>'}
                            
                            ${vendor.domains && vendor.domains.length > 0 ? `
                                <div style="margin-top: 8px;">
                                    <span style="font-size: 13px; color: #666;">Domains:</span><br>
                                    <div class="badge-container">
                                        ${vendor.domains.map(domain => `<span class="badge badge-domain">${domain}</span>`).join('')}
                                    </div>
                                </div>
                            ` : ''}
                        </div>
                    </div>
                    
                    ${vendor.countries && vendor.countries.length > 0 ? `
                        <div class="vendor-detail-section">
                            <strong>🌍 Countries</strong>
                            <div class="badge-container" style="margin-top: 10px;">
                                ${vendor.countries.map(country => `<span class="badge badge-country">${getCountryFlag(country)} ${country}</span>`).join('')}
                            </div>
                        </div>
                    ` : ''}
                    
                    ${vendor.custom_attributes && Object.keys(vendor.custom_attributes).length > 0 ? `
                        <div class="vendor-detail-section">
                            <strong>⚙️ Custom Attributes</strong>
                            <div class="custom-attributes-viewer">
                                ${renderCustomAttributes(vendor.custom_attributes)}
                            </div>
                        </div>
                    ` : ''}
                    
                    <div class="vendor-detail-section">
                        <strong>🕒 Timestamps</strong>
                        <div style="margin-top: 10px; font-size: 13px; color: #666;">
                            <div><strong>Last Updated:</strong> ${lastUpdated}</div>
                            <div style="margin-top: 4px;"><strong>Created:</strong> ${createdAt}</div>
                        </div>
                    </div>
                </div>
            </div>
        `;
    }).join('');
    
    vendorListContainer.innerHTML = html;
}

function renderCustomAttributes(attrs) {
    if (!attrs || Object.keys(attrs).length === 0) {
        return '<div style="color: #999; font-size: 13px;">No custom attributes</div>';
    }
    
    return `
        <div class="custom-attr-grid">
            ${Object.entries(attrs).map(([key, value]) => `
                <div class="custom-attr-item">
                    <strong>${key}:</strong>
                    <span>${typeof value === 'object' ? JSON.stringify(value) : value}</span>
                </div>
            `).join('')}
        </div>
    `;
}

function getCountryFlag(countryCode) {
    const flagMap = {
        'US': '🇺🇸', 'USA': '🇺🇸', 'United States': '🇺🇸',
        'GB': '🇬🇧', 'UK': '🇬🇧', 'United Kingdom': '🇬🇧',
        'DE': '🇩🇪', 'Germany': '🇩🇪', 'Deutschland': '🇩🇪',
        'FR': '🇫🇷', 'France': '🇫🇷',
        'ES': '🇪🇸', 'Spain': '🇪🇸', 'España': '🇪🇸',
        'IT': '🇮🇹', 'Italy': '🇮🇹',
        'CA': '🇨🇦', 'Canada': '🇨🇦',
        'AU': '🇦🇺', 'Australia': '🇦🇺',
        'JP': '🇯🇵', 'Japan': '🇯🇵',
        'CN': '🇨🇳', 'China': '🇨🇳',
        'IN': '🇮🇳', 'India': '🇮🇳',
        'BR': '🇧🇷', 'Brazil': '🇧🇷',
        'MX': '🇲🇽', 'Mexico': '🇲🇽',
        'NL': '🇳🇱', 'Netherlands': '🇳🇱',
        'SE': '🇸🇪', 'Sweden': '🇸🇪',
        'CH': '🇨🇭', 'Switzerland': '🇨🇭',
        'AT': '🇦🇹', 'Austria': '🇦🇹',
        'BE': '🇧🇪', 'Belgium': '🇧🇪',
        'PL': '🇵🇱', 'Poland': '🇵🇱',
        'IL': '🇮🇱', 'Israel': '🇮🇱'
    };
    
    return flagMap[countryCode] || '🌍';
}

function renderVendorPagination(currentPage, totalPages, totalCount) {
    vendorPagination.classList.remove('hidden');
    
    vendorPrevBtn.disabled = currentPage <= 1;
    vendorNextBtn.disabled = currentPage >= totalPages;
    
    const startItem = (currentPage - 1) * currentVendorLimit + 1;
    const endItem = Math.min(currentPage * currentVendorLimit, totalCount);
    
    vendorPageInfo.textContent = `Page ${currentPage} of ${totalPages} (${startItem}-${endItem} of ${totalCount})`;
}

window.toggleVendorDetails = function(vendorId) {
    const card = document.getElementById(vendorId);
    const details = card.querySelector('.vendor-card-details');
    const icon = card.querySelector('.vendor-expand-icon');
    
    if (details.classList.contains('hidden')) {
        details.classList.remove('hidden');
        icon.textContent = '▲';
        card.classList.add('expanded');
    } else {
        details.classList.add('hidden');
        icon.textContent = '▼';
        card.classList.remove('expanded');
    }
};

vendorPrevBtn.addEventListener('click', () => {
    if (currentVendorPage > 1) {
        loadVendorList(currentVendorPage - 1, currentSearchTerm);
    }
});

vendorNextBtn.addEventListener('click', () => {
    if (currentVendorPage < totalVendorPages) {
        loadVendorList(currentVendorPage + 1, currentSearchTerm);
    }
});

vendorSearchInput.addEventListener('input', (e) => {
    clearTimeout(searchTimeout);
    
    searchTimeout = setTimeout(() => {
        const searchTerm = e.target.value.trim();
        
        // Perform server-side search by calling API with search parameter
        // This searches across ALL vendors in BigQuery, not just current page
        loadVendorList(1, searchTerm);
    }, 300);
});

// Load vendors on page load
document.addEventListener('DOMContentLoaded', () => {
    loadVendorList(1);
});

// ==================== VENDOR MATCHING ENGINE ====================

const vendorMatchForm = document.getElementById('vendorMatchForm');
const matchLoading = document.getElementById('matchLoading');
const matchResults = document.getElementById('matchResults');

vendorMatchForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    
    const vendorName = document.getElementById('matchVendorName').value.trim();
    const taxId = document.getElementById('matchTaxId').value.trim();
    const emailDomain = document.getElementById('matchEmailDomain').value.trim();
    const country = document.getElementById('matchCountry').value.trim();
    const address = document.getElementById('matchAddress').value.trim();
    const phone = document.getElementById('matchPhone').value.trim();
    
    if (!vendorName) {
        alert('Please enter a vendor name');
        return;
    }
    
    // Hide old UI elements
    matchLoading.classList.add('hidden');
    matchResults.classList.add('hidden');
    
    // Show progress container
    const vendorMatchProgressDiv = document.getElementById('vendorMatchProgress');
    vendorMatchProgressDiv.classList.remove('hidden');
    vendorMatchProgressDiv.innerHTML = '<div class="loading"><div class="spinner"></div><p>Matching vendor...</p></div>';
    
    try {
        const matchResponse = await fetch('/api/vendor/match', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                vendor_name: vendorName,
                tax_id: taxId || null,
                email_domain: emailDomain || null,
                country: country || null,
                address: address || null,
                phone: phone || null
            })
        });
        
        const data = await matchResponse.json();
        
        vendorMatchProgressDiv.classList.add('hidden');
        
        if (!matchResponse.ok || !data.success) {
            throw new Error(data.error || 'Matching failed');
        }
        
        displayMatchResults(data.result);
        
    } catch (error) {
        vendorMatchProgressDiv.classList.add('hidden');
        matchResults.innerHTML = `
            <div style="padding: 20px; background: #ffebee; border-left: 4px solid #f44336; border-radius: 6px;">
                <h3 style="color: #c62828; margin: 0 0 10px 0;">❌ Matching Failed</h3>
                <p style="margin: 0; color: #666;">${error.message}</p>
            </div>
        `;
        matchResults.classList.remove('hidden');
    }
});

function displayMatchResults(result) {
    const { verdict, vendor_id, confidence, reasoning, risk_analysis, database_updates, parent_child_logic, method } = result;
    
    // Color coding based on verdict
    let verdictColor, verdictIcon, verdictBg;
    if (verdict === 'MATCH') {
        verdictColor = '#2e7d32';
        verdictIcon = '✅';
        verdictBg = '#e8f5e9';
    } else if (verdict === 'NEW_VENDOR') {
        verdictColor = '#f57c00';
        verdictIcon = '🆕';
        verdictBg = '#fff3e0';
    } else {
        verdictColor = '#d32f2f';
        verdictIcon = '⚠️';
        verdictBg = '#ffebee';
    }
    
    // Risk color coding with defensive null check
    let riskColor, riskBg;
    const safeRiskAnalysis = risk_analysis || 'UNKNOWN';
    if (safeRiskAnalysis === 'NONE' || safeRiskAnalysis === 'LOW') {
        riskColor = '#2e7d32';
        riskBg = '#e8f5e9';
    } else if (safeRiskAnalysis === 'MEDIUM') {
        riskColor = '#f57c00';
        riskBg = '#fff3e0';
    } else {
        riskColor = '#d32f2f';
        riskBg = '#ffebee';
    }
    
    // Method badge
    let methodBadge = '';
    if (method === 'TAX_ID_HARD_MATCH') {
        methodBadge = '<span style="background: #667eea; color: white; padding: 4px 12px; border-radius: 12px; font-size: 13px; font-weight: 600;">⚡ TAX ID HARD MATCH</span>';
    } else if (method === 'SEMANTIC_MATCH') {
        methodBadge = '<span style="background: #764ba2; color: white; padding: 4px 12px; border-radius: 12px; font-size: 13px; font-weight: 600;">🧠 SEMANTIC MATCH</span>';
    } else {
        methodBadge = '<span style="background: #f57c00; color: white; padding: 4px 12px; border-radius: 12px; font-size: 13px; font-weight: 600;">🆕 NEW VENDOR</span>';
    }
    
    // Database updates section
    let dbUpdatesHtml = '';
    if (database_updates && (database_updates.add_new_alias || database_updates.add_new_address || database_updates.add_new_domain)) {
        const updates = [];
        if (database_updates.add_new_alias) updates.push(`<li><strong>New Alias:</strong> ${database_updates.add_new_alias}</li>`);
        if (database_updates.add_new_address) updates.push(`<li><strong>New Address:</strong> ${database_updates.add_new_address}</li>`);
        if (database_updates.add_new_domain) updates.push(`<li><strong>New Domain:</strong> ${database_updates.add_new_domain}</li>`);
        
        dbUpdatesHtml = `
            <div style="margin-top: 20px; padding: 15px; background: #e3f2fd; border-left: 4px solid #1976d2; border-radius: 6px;">
                <h4 style="margin: 0 0 10px 0; color: #1565c0; display: flex; align-items: center; gap: 8px;">
                    🔧 Self-Healing Database Updates
                </h4>
                <ul style="margin: 0; padding-left: 20px; color: #333;">
                    ${updates.join('')}
                </ul>
            </div>
        `;
    }
    
    // Parent/child logic section
    let parentChildHtml = '';
    if (parent_child_logic && parent_child_logic.is_subsidiary) {
        parentChildHtml = `
            <div style="margin-top: 20px; padding: 15px; background: #f3e5f5; border-left: 4px solid #9c27b0; border-radius: 6px;">
                <h4 style="margin: 0 0 10px 0; color: #7b1fa2; display: flex; align-items: center; gap: 8px;">
                    🏢 Parent/Child Relationship Detected
                </h4>
                <p style="margin: 0; color: #333;">
                    <strong>Parent Company:</strong> ${parent_child_logic.parent_company_detected || 'Unknown'}
                </p>
            </div>
        `;
    }
    
    matchResults.innerHTML = `
        <div style="margin-bottom: 20px; padding: 20px; background: ${verdictBg}; border-left: 6px solid ${verdictColor}; border-radius: 8px;">
            <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 10px; margin-bottom: 15px;">
                <h3 style="margin: 0; color: ${verdictColor}; font-size: 24px;">
                    ${verdictIcon} ${verdict}
                </h3>
                ${methodBadge}
            </div>
            
            ${vendor_id ? `
                <div style="padding: 12px; background: rgba(255,255,255,0.7); border-radius: 6px; margin-bottom: 10px;">
                    <strong style="color: #333;">Matched Vendor ID:</strong>
                    <code style="background: #fff; padding: 4px 8px; border-radius: 4px; font-family: monospace; margin-left: 8px;">${vendor_id}</code>
                </div>
            ` : ''}
            
            <div style="display: flex; gap: 20px; align-items: center; margin-top: 15px; flex-wrap: wrap;">
                <div>
                    <div style="font-size: 13px; color: #666; font-weight: 600; margin-bottom: 5px;">CONFIDENCE SCORE</div>
                    <div style="font-size: 28px; font-weight: 700; color: ${verdictColor};">
                        ${(confidence * 100).toFixed(0)}%
                    </div>
                </div>
                
                <div style="flex: 1; min-width: 200px;">
                    <div style="font-size: 13px; color: #666; font-weight: 600; margin-bottom: 5px;">CONFIDENCE BAR</div>
                    <div style="background: #ddd; height: 20px; border-radius: 10px; overflow: hidden;">
                        <div style="background: ${verdictColor}; height: 100%; width: ${confidence * 100}%; transition: width 0.3s;"></div>
                    </div>
                </div>
                
                ${safeRiskAnalysis && safeRiskAnalysis !== 'UNKNOWN' ? `
                    <div>
                        <div style="font-size: 13px; color: #666; font-weight: 600; margin-bottom: 5px;">RISK LEVEL</div>
                        <div style="background: ${riskBg}; color: ${riskColor}; padding: 6px 16px; border-radius: 6px; font-weight: 700; display: inline-block;">
                            ${safeRiskAnalysis}
                        </div>
                    </div>
                ` : ''}
            </div>
        </div>
        
        <div style="padding: 20px; background: white; border: 2px solid #e0e0e0; border-radius: 8px; margin-bottom: 20px;">
            <h4 style="margin: 0 0 15px 0; color: #333; display: flex; align-items: center; gap: 8px;">
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor">
                    <path d="M12 2L2 7l10 5 10-5-10-5z"></path>
                    <path d="M2 17l10 5 10-5"></path>
                    <path d="M2 12l10 5 10-5"></path>
                </svg>
                Supreme Judge Reasoning
            </h4>
            <p style="margin: 0; color: #666; line-height: 1.6; font-size: 15px;">
                ${reasoning}
            </p>
        </div>
        
        ${dbUpdatesHtml}
        ${parentChildHtml}
    `;
    
    matchResults.classList.remove('hidden');
}

// ==================== API DOCS TAB ====================
// API Key Generation
const generateApiKeyBtn = document.getElementById('generateApiKeyBtn');
const copyApiKeyBtn = document.getElementById('copyApiKeyBtn');
const apiKeyResult = document.getElementById('apiKeyResult');

if (generateApiKeyBtn) {
    generateApiKeyBtn.addEventListener('click', async function() {
        const clientId = document.getElementById('apiClientId').value.trim();
        const description = document.getElementById('apiKeyDescription').value.trim();
        
        if (!clientId) {
            showAlert('Please enter a Client ID', 'error');
            return;
        }
        
        generateApiKeyBtn.disabled = true;
        generateApiKeyBtn.textContent = '⏳ Generating...';
        
        try {
            const response = await fetch('/api/agent/generate-key', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    client_id: clientId,
                    description: description || 'Generated from UI'
                })
            });
            
            const data = await response.json();
            
            if (data.success) {
                // Show the API key
                document.getElementById('generatedApiKey').textContent = data.api_key;
                document.getElementById('apiKeyClientId').textContent = data.client_id;
                document.getElementById('apiKeyCreated').textContent = new Date().toLocaleString();
                apiKeyResult.classList.remove('hidden');
                
                showAlert('API key generated successfully! Save it now - it won\'t be shown again.', 'success');
            } else {
                showAlert(data.error || 'Failed to generate API key', 'error');
            }
        } catch (error) {
            console.error('Error generating API key:', error);
            showAlert('Error generating API key: ' + error.message, 'error');
        } finally {
            generateApiKeyBtn.disabled = false;
            generateApiKeyBtn.textContent = '⚡ Generate API Key';
        }
    });
}

if (copyApiKeyBtn) {
    copyApiKeyBtn.addEventListener('click', function() {
        const apiKey = document.getElementById('generatedApiKey').textContent;
        
        navigator.clipboard.writeText(apiKey).then(() => {
            const originalText = copyApiKeyBtn.textContent;
            copyApiKeyBtn.textContent = '✅ Copied!';
            
            setTimeout(() => {
                copyApiKeyBtn.textContent = originalText;
            }, 2000);
        }).catch(err => {
            console.error('Failed to copy API key:', err);
            showAlert('Failed to copy to clipboard', 'error');
        });
    });
}

// ==================== INVOICE MATCH HISTORY ====================
let currentInvoicePage = 1;
let currentInvoiceStatus = '';

// ==================== INVOICE LIST FUNCTIONS (FOR INVOICES TAB) ====================

let currentInvoiceListPage = 1;
let currentInvoiceSearchTerm = '';
let currentInvoiceStatusFilter = '';
let currentInvoiceSyncFilter = '';
let totalInvoicePages = 0;

/**
 * Load invoice list with pagination and filters (for Invoices tab)
 */
async function loadInvoiceList(page = 1) {
    const invoiceLoading = document.getElementById('invoiceLoading');
    const invoiceList = document.getElementById('invoiceList');
    const invoiceEmptyState = document.getElementById('invoiceEmptyState');
    const invoicePagination = document.getElementById('invoicePagination');
    const invoiceStats = document.getElementById('invoiceStats');
    
    currentInvoiceListPage = page;
    
    // Show loading state
    if (invoiceLoading) invoiceLoading.classList.remove('hidden');
    if (invoiceEmptyState) invoiceEmptyState.classList.add('hidden');
    if (invoiceList) invoiceList.innerHTML = '';
    if (invoicePagination) invoicePagination.classList.add('hidden');
    
    try {
        // Build API URL with filters
        let url = `/api/invoices/matches?page=${page}&limit=20`;
        
        if (currentInvoiceStatusFilter) {
            url += `&status=${encodeURIComponent(currentInvoiceStatusFilter)}`;
        }
        
        const response = await fetch(url);
        const data = await response.json();
        
        // Hide loading
        if (invoiceLoading) invoiceLoading.classList.add('hidden');
        
        if (!data.invoices || data.invoices.length === 0) {
            if (invoiceEmptyState) invoiceEmptyState.classList.remove('hidden');
            if (invoiceStats) invoiceStats.innerHTML = '';
            return;
        }
        
        totalInvoicePages = Math.ceil(data.total_count / 20);
        
        // Render stats
        renderInvoiceStats(data.total_count, page, 20);
        
        // Render invoice list
        renderInvoiceListView(data.invoices);
        
        // Render pagination
        renderInvoiceListPagination(page, totalInvoicePages, data.total_count);
        
    } catch (error) {
        if (invoiceLoading) invoiceLoading.classList.add('hidden');
        if (invoiceList) {
            invoiceList.innerHTML = `
                <div style="background: #ffebee; padding: 20px; border-radius: 8px; color: #c62828;">
                    <strong>Error loading invoices:</strong> ${error.message}
                </div>
            `;
        }
    }
}

/**
 * Render invoice statistics
 */
function renderInvoiceStats(totalCount, currentPage, limit) {
    const invoiceStats = document.getElementById('invoiceStats');
    if (!invoiceStats) return;
    
    const startItem = (currentPage - 1) * limit + 1;
    const endItem = Math.min(currentPage * limit, totalCount);
    
    invoiceStats.innerHTML = `
        <div style="background: #e8f5e9; padding: 12px 20px; border-radius: 8px; flex: 1; text-align: center; border-left: 4px solid #4caf50;">
            <div style="font-size: 24px; font-weight: bold; color: #2e7d32;">${totalCount}</div>
            <div style="font-size: 13px; color: #666; margin-top: 4px;">Total Invoices</div>
        </div>
        <div style="background: #e3f2fd; padding: 12px 20px; border-radius: 8px; flex: 1; text-align: center; border-left: 4px solid #2196f3;">
            <div style="font-size: 24px; font-weight: bold; color: #1976d2;">${startItem}-${endItem}</div>
            <div style="font-size: 13px; color: #666; margin-top: 4px;">Showing</div>
        </div>
        <div style="background: #f3e5f5; padding: 12px 20px; border-radius: 8px; flex: 1; text-align: center; border-left: 4px solid #9c27b0;">
            <div style="font-size: 24px; font-weight: bold; color: #7b1fa2;">${totalInvoicePages}</div>
            <div style="font-size: 13px; color: #666; margin-top: 4px;">Total Pages</div>
        </div>
    `;
}

/**
 * Render invoice list view (for Invoices tab)
 */
function renderInvoiceListView(invoices) {
    const invoiceList = document.getElementById('invoiceList');
    if (!invoiceList) return;
    
    let html = '<div class="invoice-list-grid" style="display: grid; gap: 15px;">';
    
    invoices.forEach(invoice => {
        const statusBadge = getInvoiceStatusBadge(invoice.status);
        const syncBadge = invoice.netsuite_bill_id ? 
            '<span class="badge badge-success">✅ In NetSuite</span>' : 
            '<span class="badge badge-warning">⏳ Not Synced</span>';
        const paymentBadge = getPaymentStatusBadge(invoice.payment_status);
        const invoiceDate = invoice.invoice_date ? new Date(invoice.invoice_date).toLocaleDateString() : 'N/A';
        const amount = invoice.amount ? invoice.amount.toLocaleString() : '0';
        const currency = invoice.currency || 'USD';
        
        html += `
            <div class="invoice-card" style="background: white; padding: 20px; border-radius: 12px; border: 1px solid #e5e7eb; transition: all 0.3s; cursor: pointer;" 
                 onmouseover="this.style.boxShadow='0 4px 6px rgba(0,0,0,0.1)'" 
                 onmouseout="this.style.boxShadow='none'">
                <div style="display: flex; justify-content: space-between; align-items: start; margin-bottom: 15px;">
                    <div>
                        <h3 style="margin: 0 0 5px 0; font-size: 18px; color: #111827;">
                            📄 ${invoice.invoice_id || 'Unknown ID'}
                        </h3>
                        <div style="display: flex; gap: 8px; margin-top: 8px;">
                            ${statusBadge}
                            ${syncBadge}
                            ${paymentBadge}
                        </div>
                    </div>
                    <div style="text-align: right;">
                        <div style="font-size: 24px; font-weight: bold; color: #111827;">
                            ${amount} ${currency}
                        </div>
                        <div style="font-size: 13px; color: #6b7280; margin-top: 4px;">
                            ${invoiceDate}
                        </div>
                    </div>
                </div>
                
                <div style="border-top: 1px solid #e5e7eb; padding-top: 15px; margin-top: 15px;">
                    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 12px;">
                        <div>
                            <span style="font-size: 13px; color: #6b7280;">Vendor:</span>
                            <div style="font-weight: 500; color: #111827;">${invoice.vendor_name || 'Unknown'}</div>
                        </div>
                        <div>
                            <span style="font-size: 13px; color: #6b7280;">Match Confidence:</span>
                            <div style="font-weight: 500; color: #111827;">${invoice.match_confidence || 'N/A'}</div>
                        </div>
                    </div>
                </div>
                
                <div style="margin-top: 15px; display: flex; gap: 8px;">
                    ${invoice.gcs_uri ? `
                        <button onclick="downloadInvoice('${invoice.invoice_id}', event)" class="btn btn-secondary btn-sm">
                            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
                                <polyline points="7 10 12 15 17 10"></polyline>
                                <line x1="12" y1="15" x2="12" y2="3"></line>
                            </svg>
                            Download
                        </button>
                    ` : ''}
                    ${(!invoice.netsuite_bill_id || invoice.netsuite_bill_id === null || invoice.netsuite_bill_id === 'null' || invoice.invoice_id === '506') ? `
                        <button onclick="createBillInNetSuite('${invoice.invoice_id}')" class="btn btn-primary btn-sm">
                            📋 Create Bill
                        </button>
                    ` : `
                        <button class="btn btn-success btn-sm" disabled>
                            ✅ Bill Created
                        </button>
                    `}
                </div>
            </div>
        `;
    });
    
    html += '</div>';
    invoiceList.innerHTML = html;
}

/**
 * Get invoice status badge HTML
 */
function getInvoiceStatusBadge(status) {
    const badges = {
        'matched': '<span class="badge badge-success">✅ Matched</span>',
        'unmatched': '<span class="badge badge-info">➕ New Vendor</span>',
        'ambiguous': '<span class="badge badge-warning">❓ Ambiguous</span>'
    };
    return badges[status] || '<span class="badge badge-secondary">Unknown</span>';
}

/**
 * Render invoice list pagination
 */
function renderInvoiceListPagination(currentPage, totalPages, totalCount) {
    const pagination = document.getElementById('invoicePagination');
    if (!pagination || totalPages <= 1) {
        if (pagination) pagination.classList.add('hidden');
        return;
    }
    
    pagination.classList.remove('hidden');
    
    let html = '<div style="display: flex; justify-content: center; align-items: center; gap: 10px;">';
    
    // Previous button
    html += `
        <button onclick="loadInvoiceList(${currentPage - 1})" 
                ${currentPage === 1 ? 'disabled' : ''} 
                class="btn btn-secondary btn-sm">
            Previous
        </button>
    `;
    
    // Page numbers
    const maxButtons = 7;
    const halfButtons = Math.floor(maxButtons / 2);
    let startPage = Math.max(1, currentPage - halfButtons);
    let endPage = Math.min(totalPages, startPage + maxButtons - 1);
    
    if (endPage - startPage < maxButtons - 1) {
        startPage = Math.max(1, endPage - maxButtons + 1);
    }
    
    if (startPage > 1) {
        html += `<button onclick="loadInvoiceList(1)" class="btn btn-secondary btn-sm">1</button>`;
        if (startPage > 2) html += '<span>...</span>';
    }
    
    for (let i = startPage; i <= endPage; i++) {
        html += `
            <button onclick="loadInvoiceList(${i})" 
                    class="btn ${i === currentPage ? 'btn-primary' : 'btn-secondary'} btn-sm">
                ${i}
            </button>
        `;
    }
    
    if (endPage < totalPages) {
        if (endPage < totalPages - 1) html += '<span>...</span>';
        html += `<button onclick="loadInvoiceList(${totalPages})" class="btn btn-secondary btn-sm">${totalPages}</button>`;
    }
    
    // Next button
    html += `
        <button onclick="loadInvoiceList(${currentPage + 1})" 
                ${currentPage === totalPages ? 'disabled' : ''} 
                class="btn btn-secondary btn-sm">
            Next
        </button>
    `;
    
    html += '</div>';
    pagination.innerHTML = html;
}

/**
 * Search invoices with filters
 */
function searchInvoices() {
    const searchInput = document.getElementById('invoiceSearchInput');
    const statusFilter = document.getElementById('invoiceStatusFilter');
    const syncFilter = document.getElementById('invoiceSyncFilter');
    
    currentInvoiceSearchTerm = searchInput ? searchInput.value : '';
    currentInvoiceStatusFilter = statusFilter ? statusFilter.value : '';
    currentInvoiceSyncFilter = syncFilter ? syncFilter.value : '';
    
    loadInvoiceList(1); // Reset to page 1 when searching
}

// ==================== INVOICE MATCHING FUNCTIONS (FOR MATCHING TAB) ====================

/**
 * Load invoice matches from API
 */
async function loadInvoiceMatches(page = 1, status = '') {
    const container = document.getElementById('invoiceMatchList');
    
    if (!container) return;
    
    container.innerHTML = '<div class="loading"><div class="spinner"></div><p>Loading invoices...</p></div>';
    
    try {
        let url = `/api/invoices/matches?page=${page}&limit=20`;
        if (status) {
            url += `&status=${status}`;
        }
        
        const response = await fetch(url);
        const data = await response.json();
        
        currentInvoicePage = page;
        currentInvoiceStatus = status;
        
        renderInvoiceMatches(data);
        renderInvoicePagination(data);
        
    } catch (error) {
        console.error('Error loading invoices:', error);
        container.innerHTML = `
            <div class="alert alert-error">
                <strong>❌ Error loading invoices</strong>
                <p>${error.message}</p>
            </div>
        `;
    }
}

/**
 * Render invoice matches
 */
function renderInvoiceMatches(data) {
    const container = document.getElementById('invoiceMatchList');
    
    if (!data.invoices || data.invoices.length === 0) {
        container.innerHTML = `
            <div class="empty-state">
                <svg class="empty-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor">
                    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
                    <polyline points="14 2 14 8 20 8"></polyline>
                </svg>
                <h3 class="empty-title">No invoices found</h3>
                <p class="empty-desc">Upload an invoice to see vendor matches here</p>
            </div>
        `;
        return;
    }
    
    let html = '<div class="invoice-cards">';
    
    data.invoices.forEach(invoice => {
        const statusBadge = getStatusBadge(invoice.status);
        const paymentBadge = getPaymentStatusBadge(invoice.payment_status);
        const confidence = invoice.match_confidence || 'N/A';
        const reasoning = invoice.match_reasoning || 'No reasoning available';
        const invoiceDate = invoice.invoice_date ? new Date(invoice.invoice_date).toLocaleDateString() : 'N/A';
        const createdAt = invoice.created_at ? new Date(invoice.created_at).toLocaleString() : 'N/A';
        const paymentDate = invoice.payment_date ? new Date(invoice.payment_date).toLocaleDateString() : null;
        
        html += `
            <div class="invoice-card">
                <div class="invoice-card-header">
                    <div class="invoice-card-title">
                        <strong>${invoice.invoice_id}</strong>
                        ${statusBadge}
                        ${paymentBadge}
                    </div>
                    <div class="invoice-card-amount">
                        ${invoice.amount.toLocaleString()} ${invoice.currency}
                    </div>
                </div>
                
                <div class="invoice-card-body">
                    <div class="invoice-info-grid">
                        <div class="invoice-info-item">
                            <span class="invoice-info-label">Vendor:</span>
                            <span class="invoice-info-value">${invoice.vendor_name}</span>
                        </div>
                        <div class="invoice-info-item">
                            <span class="invoice-info-label">Invoice Date:</span>
                            <span class="invoice-info-value">${invoiceDate}</span>
                        </div>
                        <div class="invoice-info-item">
                            <span class="invoice-info-label">Uploaded:</span>
                            <span class="invoice-info-value">${createdAt}</span>
                        </div>
                        <div class="invoice-info-item">
                            <span class="invoice-info-label">Confidence:</span>
                            <span class="invoice-info-value">${confidence}</span>
                        </div>
                        ${paymentDate ? `
                        <div class="invoice-info-item">
                            <span class="invoice-info-label">Payment Date:</span>
                            <span class="invoice-info-value">${paymentDate}</span>
                        </div>
                        ` : ''}
                        ${invoice.payment_amount ? `
                        <div class="invoice-info-item">
                            <span class="invoice-info-label">Amount Paid:</span>
                            <span class="invoice-info-value">${invoice.payment_amount.toLocaleString()} ${invoice.currency}</span>
                        </div>
                        ` : ''}
                    </div>
                    
                    <details class="invoice-details">
                        <summary class="invoice-details-toggle">View Match Reasoning</summary>
                        <div class="invoice-details-content">
                            <p>${reasoning}</p>
                        </div>
                    </details>
                </div>
            </div>
        `;
    });
    
    html += '</div>';
    
    container.innerHTML = html;
}

/**
 * Get status badge HTML
 */
function getStatusBadge(status) {
    const badges = {
        'matched': '<span class="status-badge status-matched">✓ MATCHED</span>',
        'unmatched': '<span class="status-badge status-unmatched">+ NEW VENDOR</span>',
        'ambiguous': '<span class="status-badge status-ambiguous">? AMBIGUOUS</span>'
    };
    
    return badges[status] || '<span class="status-badge status-unknown">UNKNOWN</span>';
}

/**
 * Get payment status badge HTML
 */
function getPaymentStatusBadge(paymentStatus) {
    const badges = {
        'paid': '<span class="payment-badge payment-paid">💰 PAID</span>',
        'partial': '<span class="payment-badge payment-partial">⚠️ PARTIAL</span>',
        'pending': '<span class="payment-badge payment-pending">⏳ PENDING</span>',
        'overdue': '<span class="payment-badge payment-overdue">🔴 OVERDUE</span>'
    };
    
    return badges[paymentStatus] || '';
}

/**
 * Render invoice pagination controls
 */
function renderInvoicePagination(data) {
    const container = document.getElementById('invoicePagination');
    
    if (!container) return;
    
    const totalPages = Math.ceil(data.total_count / data.limit);
    
    if (totalPages <= 1) {
        container.classList.add('hidden');
        return;
    }
    
    container.classList.remove('hidden');
    
    const prevDisabled = data.page <= 1;
    const nextDisabled = data.page >= totalPages;
    
    container.innerHTML = `
        <button 
            id="invoicePrevBtn" 
            class="btn btn-secondary" 
            ${prevDisabled ? 'disabled' : ''}
        >
            ← Previous
        </button>
        <div class="page-info">
            Page ${data.page} of ${totalPages} (${data.total_count} total)
        </div>
        <button 
            id="invoiceNextBtn" 
            class="btn btn-secondary" 
            ${nextDisabled ? 'disabled' : ''}
        >
            Next →
        </button>
    `;
    
    // Add event listeners
    const prevBtn = document.getElementById('invoicePrevBtn');
    const nextBtn = document.getElementById('invoiceNextBtn');
    
    if (prevBtn) {
        prevBtn.addEventListener('click', () => {
            loadInvoiceMatches(currentInvoicePage - 1, currentInvoiceStatus);
        });
    }
    
    if (nextBtn) {
        nextBtn.addEventListener('click', () => {
            loadInvoiceMatches(currentInvoicePage + 1, currentInvoiceStatus);
        });
    }
}

// Initialize invoice match history when Matching tab is opened
document.addEventListener('DOMContentLoaded', function() {
    const matchingTabButton = document.querySelector('[data-tab="matching"]');
    
    if (matchingTabButton) {
        matchingTabButton.addEventListener('click', function() {
            // Load invoices when tab is opened
            setTimeout(() => {
                loadInvoiceMatches(1, '');
            }, 100);
        });
    }
    
    // Refresh button
    const refreshBtn = document.getElementById('refreshInvoicesBtn');
    if (refreshBtn) {
        refreshBtn.addEventListener('click', function() {
            loadInvoiceMatches(currentInvoicePage, currentInvoiceStatus);
        });
    }
    
    // Status filter
    const statusFilter = document.getElementById('invoiceStatusFilter');
    if (statusFilter) {
        statusFilter.addEventListener('change', function() {
            loadInvoiceMatches(1, this.value);
        });
    }
});

/**
 * Download invoice file from Google Cloud Storage
 */
async function downloadInvoice(invoiceId, event) {
    let button = null;
    let originalHTML = '';
    
    try {
        console.log(`📥 Downloading invoice: ${invoiceId}`);
        
        // Get button and save original HTML
        button = event.target.closest('button');
        originalHTML = button.innerHTML;
        
        // Show loading indicator
        button.disabled = true;
        button.innerHTML = `
            <svg class="spinner" style="width: 18px; height: 18px; animation: spin 1s linear infinite;" viewBox="0 0 24 24">
                <circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" fill="none" opacity="0.25"></circle>
                <path fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" opacity="0.75"></path>
            </svg>
            Generating URL...
        `;
        
        // Call the download API endpoint
        const response = await fetch(`/api/invoices/${encodeURIComponent(invoiceId)}/download`);
        const data = await response.json();
        
        if (!response.ok || !data.success) {
            throw new Error(data.error || 'Failed to generate download URL');
        }
        
        // Open the signed URL in a new tab
        window.open(data.download_url, '_blank');
        
        // Show success message
        button.innerHTML = `
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M20 6L9 17l-5-5"></path>
            </svg>
            Downloaded!
        `;
        
        // Reset button after 2 seconds
        setTimeout(() => {
            button.disabled = false;
            button.innerHTML = originalHTML;
        }, 2000);
        
        console.log(`✅ Download initiated for invoice: ${invoiceId}`);
        
    } catch (error) {
        console.error('❌ Download error:', error);
        
        // Show error message
        alert(`Failed to download invoice: ${error.message}`);
        
        // Reset button if available
        if (button) {
            button.disabled = false;
            button.innerHTML = originalHTML || `
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
                    <polyline points="7 10 12 15 17 10"></polyline>
                    <line x1="12" y1="15" x2="12" y2="3"></line>
                </svg>
                Download Invoice
            `;
        }
    }
}

// ==================== INVOICE GENERATION ====================
let selectedVendorData = null;
let lineItemCounter = 0;
let generatedInvoiceData = null;

// Helper function to escape HTML
function escapeHtml(text) {
    if (!text) return '';
    const map = {
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#039;'
    };
    return text.toString().replace(/[&<>"']/g, m => map[m]);
}

function initializeInvoiceGeneration() {
    console.log('Initializing Invoice Generation feature...');
    
    // Initialize mode switching
    initializeModeToggle();
    
    // Initialize vendor search autocomplete
    initializeVendorAutocomplete();
    
    // Initialize magic fill
    initializeMagicFill();
    
    // Initialize line items management
    initializeLineItems();
    
    // Initialize form submission
    initializeInvoiceFormSubmission();
    
    // Initialize test data buttons - NEW!
    initializeTestDataButtons();
    
    // Set default dates
    setDefaultDates();
}

// Test Data Functionality - NEW!
function initializeTestDataButtons() {
    // Simple mode test data button
    const simpleTestBtn = document.getElementById('fillTestDataSimple');
    if (simpleTestBtn) {
        simpleTestBtn.addEventListener('click', fillSimpleTestData);
    }
    
    // Advanced mode test data button
    const advancedTestBtn = document.getElementById('fillTestDataAdvanced');
    if (advancedTestBtn) {
        advancedTestBtn.addEventListener('click', fillAdvancedTestData);
    }
}

async function fillSimpleTestData() {
    console.log('🎲 Filling simple mode with test data...');
    
    // Set test vendor data
    const vendorSearch = document.getElementById('vendorSearch');
    const vendorId = document.getElementById('selectedVendorId');
    const description = document.getElementById('invoiceDescription');
    const amount = document.getElementById('invoiceAmount');
    const currency = document.getElementById('invoiceCurrency');
    const taxType = document.getElementById('taxType');
    const buyerName = document.getElementById('buyerName');
    
    if (vendorSearch) vendorSearch.value = 'Acme Corporation';
    if (vendorId) vendorId.value = 'test-vendor-001';
    if (description) description.value = 'Web Development Services';
    if (amount) amount.value = '1500.00';
    if (currency) currency.value = 'USD';
    if (taxType) taxType.value = 'vat';
    if (buyerName) buyerName.value = 'MyCompany Inc.';
    
    // Trigger change events
    [vendorSearch, description, amount, currency, taxType, buyerName].forEach(field => {
        if (field) field.dispatchEvent(new Event('change'));
    });
    
    // Show success message
    showToast('✅ Test data filled successfully!', 'success');
}

async function fillAdvancedTestData() {
    console.log('🎲 Filling advanced mode with test data...');
    
    // Fill basic invoice info
    const invoiceNumber = document.getElementById('invoiceNumber');
    const poNumber = document.getElementById('poNumber');
    const issueDate = document.getElementById('issueDate');
    const dueDate = document.getElementById('dueDate');
    
    const today = new Date();
    const dueDateValue = new Date(today);
    dueDateValue.setDate(dueDateValue.getDate() + 30);
    
    if (invoiceNumber) invoiceNumber.value = 'INV-2024-TEST-001';
    if (poNumber) poNumber.value = 'PO-12345';
    if (issueDate) issueDate.value = today.toISOString().split('T')[0];
    if (dueDate) dueDate.value = dueDateValue.toISOString().split('T')[0];
    
    // Fill vendor
    const vendorSearchAdv = document.getElementById('vendorSearchAdv');
    const vendorIdAdv = document.getElementById('selectedVendorIdAdv');
    if (vendorSearchAdv) vendorSearchAdv.value = 'Tech Solutions Ltd.';
    if (vendorIdAdv) vendorIdAdv.value = 'test-vendor-002';
    
    // Fill buyer info
    const buyerNameAdv = document.getElementById('buyerNameAdv');
    const buyerTaxId = document.getElementById('buyerTaxId');
    const buyerAddress = document.getElementById('buyerAddress');
    const buyerCountry = document.getElementById('buyerCountry');
    
    if (buyerNameAdv) buyerNameAdv.value = 'Global Enterprises Corp.';
    if (buyerTaxId) buyerTaxId.value = 'TAX-123456789';
    if (buyerAddress) buyerAddress.value = '123 Business Ave, Suite 500';
    if (buyerCountry) buyerCountry.value = 'United States';
    
    // Clear existing line items and add test items
    const lineItemsBody = document.getElementById('lineItemsBody');
    if (lineItemsBody) {
        lineItemsBody.innerHTML = '';
        lineItemCounter = 0;
        
        // Add 3 sample line items
        const sampleItems = [
            { desc: 'Frontend Development', qty: 40, price: 75, discount: 0, tax: 10, category: 'Consulting' },
            { desc: 'Backend API Development', qty: 60, price: 85, discount: 5, tax: 10, category: 'Services' },
            { desc: 'Database Optimization', qty: 20, price: 100, discount: 0, tax: 10, category: 'Consulting' }
        ];
        
        sampleItems.forEach(item => {
            addLineItem();
            const itemId = lineItemCounter;
            
            setTimeout(() => {
                const descInput = document.querySelector(`input[name="description_${itemId}"]`);
                const qtyInput = document.querySelector(`input[name="qty_${itemId}"]`);
                const priceInput = document.querySelector(`input[name="price_${itemId}"]`);
                const discountInput = document.querySelector(`input[name="discount_${itemId}"]`);
                const taxInput = document.querySelector(`input[name="tax_${itemId}"]`);
                const categorySelect = document.querySelector(`select[name="category_${itemId}"]`);
                
                if (descInput) descInput.value = item.desc;
                if (qtyInput) qtyInput.value = item.qty;
                if (priceInput) priceInput.value = item.price;
                if (discountInput) discountInput.value = item.discount;
                if (taxInput) taxInput.value = item.tax;
                if (categorySelect) categorySelect.value = item.category;
                
                calculateLineItemTotal(itemId);
            }, 100);
        });
    }
    
    // Set currency and notes
    const currencyAdv = document.getElementById('invoiceCurrencyAdv');
    const exchangeRate = document.getElementById('exchangeRate');
    const paymentTerms = document.getElementById('paymentTerms');
    const notes = document.getElementById('invoiceNotes');
    
    if (currencyAdv) currencyAdv.value = 'USD';
    if (exchangeRate) exchangeRate.value = '1.00';
    if (paymentTerms) paymentTerms.value = 'Net 30';
    if (notes) notes.value = 'Thank you for your business!';
    
    // Calculate totals
    setTimeout(calculateTotals, 500);
    
    // Show success
    showToast('✅ Advanced test data filled!', 'success');
}

function showToast(message, type = 'info') {
    const existing = document.querySelector('.toast');
    if (existing) existing.remove();
    
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.style.cssText = `
        position: fixed; top: 80px; right: 20px; padding: 16px 20px;
        border-radius: 8px; background: white; box-shadow: 0 4px 12px rgba(0,0,0,0.15);
        z-index: 10000; animation: slideIn 0.3s ease; max-width: 400px;
        ${type === 'success' ? 'background: #22c55e; color: white;' : ''}
        ${type === 'error' ? 'background: #ef4444; color: white;' : ''}
    `;
    toast.textContent = message;
    document.body.appendChild(toast);
    
    setTimeout(() => toast.remove(), 3000);
}

// Mode Toggle - UPDATED!
function initializeModeToggle() {
    const modeCards = document.querySelectorAll('.mode-card');
    const simpleMode = document.getElementById('simple-mode');
    const advancedMode = document.getElementById('advanced-mode');
    
    if (!modeCards.length || !simpleMode || !advancedMode) return;
    
    modeCards.forEach(card => {
        card.addEventListener('click', function() {
            const mode = this.getAttribute('data-mode');
            
            // Update card states
            modeCards.forEach(c => c.classList.remove('active'));
            this.classList.add('active');
            
            // Show/hide forms
            if (mode === 'simple') {
                simpleMode.classList.remove('hidden');
                advancedMode.classList.add('hidden');
            } else {
                simpleMode.classList.add('hidden');
                advancedMode.classList.remove('hidden');
                
                // Add initial line item if none exist
                const lineItemsBody = document.getElementById('lineItemsBody');
                if (lineItemsBody && lineItemsBody.children.length === 0) {
                    addLineItem();
                }
            }
        });
    });
}

// Vendor Autocomplete
function initializeVendorAutocomplete() {
    const vendorSearchInputs = [
        { input: document.getElementById('vendorSearch'), suggestions: document.getElementById('vendorSuggestions'), idField: document.getElementById('selectedVendorId') },
        { input: document.getElementById('vendorSearchAdv'), suggestions: document.getElementById('vendorSuggestionsAdv'), idField: document.getElementById('selectedVendorIdAdv') }
    ];
    
    vendorSearchInputs.forEach(({ input, suggestions, idField }) => {
        if (!input || !suggestions || !idField) return;
        
        let searchTimeout = null;
        
        input.addEventListener('input', function() {
            const query = this.value.trim();
            
            if (query.length < 2) {
                suggestions.classList.add('hidden');
                return;
            }
            
            clearTimeout(searchTimeout);
            searchTimeout = setTimeout(() => {
                searchVendors(query, suggestions, input, idField);
            }, 300);
        });
        
        // Hide suggestions on click outside
        document.addEventListener('click', function(e) {
            if (!input.contains(e.target) && !suggestions.contains(e.target)) {
                suggestions.classList.add('hidden');
            }
        });
    });
}

async function searchVendors(query, suggestionsDiv, inputField, idField) {
    try {
        const response = await fetch(`/api/invoice/search-vendors?q=${encodeURIComponent(query)}`);
        const data = await response.json();
        
        if (!response.ok) {
            throw new Error(data.error || 'Failed to search vendors');
        }
        
        displayVendorSuggestions(data.vendors, suggestionsDiv, inputField, idField);
    } catch (error) {
        console.error('Error searching vendors:', error);
        suggestionsDiv.innerHTML = `<div class="suggestion-error">Error searching vendors</div>`;
        suggestionsDiv.classList.remove('hidden');
    }
}

function displayVendorSuggestions(vendors, suggestionsDiv, inputField, idField) {
    if (!vendors || vendors.length === 0) {
        suggestionsDiv.innerHTML = '<div class="suggestion-no-results">No vendors found</div>';
        suggestionsDiv.classList.remove('hidden');
        return;
    }
    
    let html = '';
    vendors.forEach(vendor => {
        html += `
            <div class="suggestion-item" data-vendor='${JSON.stringify(vendor)}'>
                <div class="suggestion-name">${escapeHtml(vendor.name)}</div>
                <div class="suggestion-details">
                    ${vendor.country ? `<span class="suggestion-country">${escapeHtml(vendor.country)}</span>` : ''}
                    ${vendor.email ? `<span class="suggestion-email">${escapeHtml(vendor.email)}</span>` : ''}
                </div>
            </div>
        `;
    });
    
    suggestionsDiv.innerHTML = html;
    suggestionsDiv.classList.remove('hidden');
    
    // Add click handlers
    suggestionsDiv.querySelectorAll('.suggestion-item').forEach(item => {
        item.addEventListener('click', function() {
            const vendor = JSON.parse(this.getAttribute('data-vendor'));
            selectVendor(vendor, inputField, idField, suggestionsDiv);
        });
    });
}

function selectVendor(vendor, inputField, idField, suggestionsDiv) {
    selectedVendorData = vendor;
    inputField.value = vendor.name;
    idField.value = vendor.vendor_id;
    suggestionsDiv.classList.add('hidden');
    
    // Auto-detect tax type based on country
    const taxTypeSelect = document.getElementById('taxType');
    if (taxTypeSelect && vendor.country) {
        autoDetectTaxType(vendor.country, taxTypeSelect);
    }
}

function autoDetectTaxType(country, taxTypeSelect) {
    const taxMappings = {
        'United Kingdom': 'vat',
        'UK': 'vat',
        'United States': 'sales',
        'USA': 'sales',
        'US': 'sales',
        'Canada': 'gst',
        'Australia': 'gst',
        'India': 'gst',
        'Hong Kong': 'none'
    };
    
    const detectedTax = taxMappings[country];
    if (detectedTax) {
        taxTypeSelect.value = detectedTax;
    }
}

// Magic Fill
function initializeMagicFill() {
    const magicFillBtn = document.getElementById('magicFillBtn');
    const descriptionField = document.getElementById('invoiceDescription');
    
    if (!magicFillBtn || !descriptionField) return;
    
    magicFillBtn.addEventListener('click', async function() {
        const description = descriptionField.value.trim();
        
        if (!description) {
            alert('Please enter a description first');
            return;
        }
        
        magicFillBtn.disabled = true;
        magicFillBtn.textContent = '⏳ Analyzing...';
        
        try {
            const response = await fetch('/api/invoice/magic-fill', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    description: description,
                    vendor: selectedVendorData
                })
            });
            
            const data = await response.json();
            
            if (!response.ok) {
                throw new Error(data.error || 'Magic fill failed');
            }
            
            // Apply magic fill results
            applyMagicFillResults(data.data);
            
        } catch (error) {
            console.error('Magic fill error:', error);
            alert(`Magic fill failed: \${error.message}`);
        } finally {
            magicFillBtn.disabled = false;
            magicFillBtn.textContent = '🪄 Magic Fill';
        }
    });
}

function applyMagicFillResults(data) {
    // Apply to simple mode
    if (data.line_items && data.line_items.length > 0) {
        const firstItem = data.line_items[0];
        const amountField = document.getElementById('invoiceAmount');
        
        if (amountField && firstItem.unit_price) {
            const total = (firstItem.quantity || 1) * firstItem.unit_price;
            amountField.value = total.toFixed(2);
        }
    }
    
    // Apply currency
    if (data.currency) {
        const currencySelect = document.getElementById('invoiceCurrency');
        if (currencySelect) {
            currencySelect.value = data.currency;
        }
    }
    
    // Apply suggested tax
    if (data.suggested_tax_rate !== undefined) {
        const taxTypeSelect = document.getElementById('taxType');
        if (taxTypeSelect && data.tax_type) {
            taxTypeSelect.value = data.tax_type.toLowerCase();
        }
    }
    
    // Show success message
    showMessage('✨ Magic fill applied successfully!', 'success');
}

// Line Items Management
function initializeLineItems() {
    const addLineItemBtn = document.getElementById('addLineItemBtn');
    
    if (!addLineItemBtn) return;
    
    addLineItemBtn.addEventListener('click', addLineItem);
    
    // Add initial line item
    addLineItem();
}

function addLineItem() {
    const lineItemsBody = document.getElementById('lineItemsBody');
    if (!lineItemsBody) return;
    
    const itemId = ++lineItemCounter;
    
    const row = document.createElement('tr');
    row.id = `line-item-\${itemId}`;
    row.innerHTML = `
        <td>
            <input type="text" class="line-item-input" 
                   name="description_\${itemId}" 
                   placeholder="Item description" required>
        </td>
        <td>
            <input type="number" class="line-item-input line-item-qty" 
                   name="qty_\${itemId}" 
                   value="1" min="0" step="0.01" required>
        </td>
        <td>
            <input type="number" class="line-item-input line-item-price" 
                   name="price_\${itemId}" 
                   value="0" min="0" step="0.01" required>
        </td>
        <td>
            <input type="number" class="line-item-input line-item-discount" 
                   name="discount_\${itemId}" 
                   value="0" min="0" max="100" step="0.1">
        </td>
        <td>
            <input type="number" class="line-item-input line-item-tax" 
                   name="tax_\${itemId}" 
                   value="0" min="0" max="100" step="0.1">
        </td>
        <td>
            <select class="line-item-input" name="category_\${itemId}">
                <option value="General">General</option>
                <option value="Consulting">Consulting</option>
                <option value="Services">Services</option>
                <option value="Products">Products</option>
                <option value="Software">Software</option>
                <option value="Marketing">Marketing</option>
            </select>
        </td>
        <td class="line-item-total">$0.00</td>
        <td>
            <button type="button" class="btn-remove-line" onclick="removeLineItem(\${itemId})">❌</button>
        </td>
    `;
    
    lineItemsBody.appendChild(row);
    
    // Add change listeners for calculations
    row.querySelectorAll('.line-item-qty, .line-item-price, .line-item-discount, .line-item-tax').forEach(input => {
        input.addEventListener('change', () => calculateLineItemTotal(itemId));
        input.addEventListener('input', () => calculateLineItemTotal(itemId));
    });
}

function removeLineItem(itemId) {
    const row = document.getElementById(`line-item-\${itemId}`);
    if (row) {
        row.remove();
        calculateTotals();
    }
}

function calculateLineItemTotal(itemId) {
    const row = document.getElementById(`line-item-\${itemId}`);
    if (!row) return;
    
    const qty = parseFloat(row.querySelector(`[name="qty_\${itemId}"]`).value) || 0;
    const price = parseFloat(row.querySelector(`[name="price_\${itemId}"]`).value) || 0;
    const discount = parseFloat(row.querySelector(`[name="discount_\${itemId}"]`).value) || 0;
    const tax = parseFloat(row.querySelector(`[name="tax_\${itemId}"]`).value) || 0;
    
    const subtotal = qty * price;
    const discountAmount = subtotal * (discount / 100);
    const afterDiscount = subtotal - discountAmount;
    const taxAmount = afterDiscount * (tax / 100);
    const total = afterDiscount + taxAmount;
    
    const totalCell = row.querySelector('.line-item-total');
    const currency = document.getElementById('invoiceCurrencyAdv')?.value || 'USD';
    const symbol = getCurrencySymbol(currency);
    
    totalCell.textContent = `\${symbol}\${total.toFixed(2)}`;
    
    calculateTotals();
}

function calculateTotals() {
    let subtotal = 0;
    let totalDiscount = 0;
    let totalTax = 0;
    
    const lineItemsBody = document.getElementById('lineItemsBody');
    if (!lineItemsBody) return;
    
    lineItemsBody.querySelectorAll('tr').forEach(row => {
        const itemId = row.id.replace('line-item-', '');
        
        const qty = parseFloat(row.querySelector(`[name="qty_\${itemId}"]`)?.value) || 0;
        const price = parseFloat(row.querySelector(`[name="price_\${itemId}"]`)?.value) || 0;
        const discount = parseFloat(row.querySelector(`[name="discount_\${itemId}"]`)?.value) || 0;
        const tax = parseFloat(row.querySelector(`[name="tax_\${itemId}"]`)?.value) || 0;
        
        const itemSubtotal = qty * price;
        const discountAmount = itemSubtotal * (discount / 100);
        const afterDiscount = itemSubtotal - discountAmount;
        const taxAmount = afterDiscount * (tax / 100);
        
        subtotal += itemSubtotal;
        totalDiscount += discountAmount;
        totalTax += taxAmount;
    });
    
    const grandTotal = subtotal - totalDiscount + totalTax;
    
    const currency = document.getElementById('invoiceCurrencyAdv')?.value || 'USD';
    const symbol = getCurrencySymbol(currency);
    
    // Update display
    const subtotalDisplay = document.getElementById('subtotalDisplay');
    const discountDisplay = document.getElementById('discountDisplay');
    const taxDisplay = document.getElementById('taxDisplay');
    const grandTotalDisplay = document.getElementById('grandTotalDisplay');
    
    if (subtotalDisplay) subtotalDisplay.textContent = `\${symbol}\${subtotal.toFixed(2)}`;
    if (discountDisplay) discountDisplay.textContent = `-\${symbol}\${totalDiscount.toFixed(2)}`;
    if (taxDisplay) taxDisplay.textContent = `\${symbol}\${totalTax.toFixed(2)}`;
    if (grandTotalDisplay) grandTotalDisplay.textContent = `\${symbol}\${grandTotal.toFixed(2)}`;
}

// Form Submission
function initializeInvoiceFormSubmission() {
    // Simple form
    const simpleForm = document.getElementById('simpleInvoiceForm');
    if (simpleForm) {
        simpleForm.addEventListener('submit', handleSimpleInvoiceSubmit);
    }
    
    // Advanced form
    const advancedForm = document.getElementById('advancedInvoiceForm');
    if (advancedForm) {
        advancedForm.addEventListener('submit', handleAdvancedInvoiceSubmit);
    }
    
    // Validation buttons
    const validateSimpleBtn = document.getElementById('validateInvoiceBtn');
    if (validateSimpleBtn) {
        validateSimpleBtn.addEventListener('click', () => validateInvoice('simple'));
    }
    
    const validateAdvBtn = document.getElementById('validateAdvancedBtn');
    if (validateAdvBtn) {
        validateAdvBtn.addEventListener('click', () => validateInvoice('advanced'));
    }
}

async function handleSimpleInvoiceSubmit(e) {
    e.preventDefault();
    
    const invoiceData = {
        vendor: selectedVendorData,
        description: document.getElementById('invoiceDescription').value,
        amount: parseFloat(document.getElementById('invoiceAmount').value),
        currency: document.getElementById('invoiceCurrency').value,
        tax_type: document.getElementById('taxType').value,
        buyer: {
            name: document.getElementById('buyerName').value,
            address: '',
            city: '',
            country: '',
            tax_id: ''
        },
        mode: 'simple'
    };
    
    await generateInvoice(invoiceData);
}

async function handleAdvancedInvoiceSubmit(e) {
    e.preventDefault();
    
    // Collect line items
    const lineItems = [];
    const lineItemsBody = document.getElementById('lineItemsBody');
    
    lineItemsBody.querySelectorAll('tr').forEach(row => {
        const itemId = row.id.replace('line-item-', '');
        
        lineItems.push({
            description: row.querySelector(`[name="description_\${itemId}"]`).value,
            quantity: parseFloat(row.querySelector(`[name="qty_\${itemId}"]`).value) || 1,
            unit_price: parseFloat(row.querySelector(`[name="price_\${itemId}"]`).value) || 0,
            discount_percent: parseFloat(row.querySelector(`[name="discount_\${itemId}"]`).value) || 0,
            tax_rate: parseFloat(row.querySelector(`[name="tax_\${itemId}"]`).value) || 0,
            tracking_category: row.querySelector(`[name="category_\${itemId}"]`).value
        });
    });
    
    const invoiceData = {
        vendor: selectedVendorData,
        invoice_number: document.getElementById('invoiceNumber').value,
        po_number: document.getElementById('poNumber').value,
        issue_date: document.getElementById('issueDate').value,
        due_date: document.getElementById('dueDate').value,
        line_items: lineItems,
        currency: document.getElementById('invoiceCurrencyAdv').value,
        exchange_rate: parseFloat(document.getElementById('exchangeRate').value) || 1,
        payment_terms: document.getElementById('paymentTerms').value,
        notes: document.getElementById('invoiceNotes').value,
        buyer: {
            name: document.getElementById('buyerNameAdv').value,
            address: document.getElementById('buyerAddress').value,
            city: '',
            country: document.getElementById('buyerCountry').value,
            tax_id: document.getElementById('buyerTaxId').value
        },
        mode: 'advanced'
    };
    
    await generateInvoice(invoiceData);
}

async function generateInvoice(invoiceData) {
    const generateBtn = invoiceData.mode === 'simple' 
        ? document.getElementById('generateSimpleInvoiceBtn')
        : document.getElementById('generateAdvancedInvoiceBtn');
    
    const originalText = generateBtn.textContent;
    generateBtn.disabled = true;
    generateBtn.textContent = '⏳ Generating...';
    
    try {
        const response = await fetch('/api/invoice/generate', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(invoiceData)
        });
        
        const data = await response.json();
        
        if (!response.ok) {
            throw new Error(data.error || 'Failed to generate invoice');
        }
        
        generatedInvoiceData = data;
        displayGenerationResults(data);
        
    } catch (error) {
        console.error('Invoice generation error:', error);
        alert(`Failed to generate invoice: \${error.message}`);
    } finally {
        generateBtn.disabled = false;
        generateBtn.textContent = originalText;
    }
}

async function validateInvoice(mode) {
    // Collect invoice data based on mode
    let invoiceData;
    
    if (mode === 'simple') {
        invoiceData = {
            vendor: selectedVendorData,
            tax_type: document.getElementById('taxType').value,
            currency: document.getElementById('invoiceCurrency').value
        };
    } else {
        // Collect advanced mode data
        const lineItems = [];
        const lineItemsBody = document.getElementById('lineItemsBody');
        
        lineItemsBody.querySelectorAll('tr').forEach(row => {
            const itemId = row.id.replace('line-item-', '');
            lineItems.push({
                description: row.querySelector(`[name="description_\${itemId}"]`).value,
                quantity: parseFloat(row.querySelector(`[name="qty_\${itemId}"]`).value) || 1,
                unit_price: parseFloat(row.querySelector(`[name="price_\${itemId}"]`).value) || 0,
                tax_rate: parseFloat(row.querySelector(`[name="tax_\${itemId}"]`).value) || 0
            });
        });
        
        invoiceData = {
            vendor: selectedVendorData,
            line_items: lineItems,
            currency: document.getElementById('invoiceCurrencyAdv').value
        };
    }
    
    const resultsDiv = mode === 'simple' 
        ? document.getElementById('validationResults')
        : document.getElementById('validationResultsAdv');
    
    resultsDiv.innerHTML = '<div class="loading">Validating...</div>';
    resultsDiv.classList.remove('hidden');
    
    try {
        const response = await fetch('/api/invoice/validate', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(invoiceData)
        });
        
        const data = await response.json();
        
        if (!response.ok) {
            throw new Error(data.error || 'Validation failed');
        }
        
        displayValidationResults(data.validation, resultsDiv);
        
    } catch (error) {
        console.error('Validation error:', error);
        resultsDiv.innerHTML = `<div class="validation-error">Validation failed: \${error.message}</div>`;
    }
}

function displayValidationResults(validation, resultsDiv) {
    let html = '';
    
    if (validation.is_valid) {
        html = '<div class="validation-success">✅ Invoice is valid</div>';
    } else {
        html = '<div class="validation-error">❌ Validation issues found</div>';
    }
    
    if (validation.errors && validation.errors.length > 0) {
        html += '<div class="validation-section"><h4>Errors:</h4><ul>';
        validation.errors.forEach(error => {
            html += `<li class="validation-error-item">\${error.field}: \${error.message}</li>`;
        });
        html += '</ul></div>';
    }
    
    if (validation.warnings && validation.warnings.length > 0) {
        html += '<div class="validation-section"><h4>Warnings:</h4><ul>';
        validation.warnings.forEach(warning => {
            html += `<li class="validation-warning-item">\${warning.field}: \${warning.message}</li>`;
        });
        html += '</ul></div>';
    }
    
    if (validation.suggestions && validation.suggestions.length > 0) {
        html += '<div class="validation-section"><h4>Suggestions:</h4><ul>';
        validation.suggestions.forEach(suggestion => {
            html += `<li class="validation-suggestion-item">
                \${suggestion.field}: Change from "\${suggestion.current_value}" to "\${suggestion.suggested_value}" 
                (\${suggestion.reason})
            </li>`;
        });
        html += '</ul></div>';
    }
    
    resultsDiv.innerHTML = html;
    resultsDiv.classList.remove('hidden');
}

function displayGenerationResults(data) {
    const resultsSection = document.getElementById('generationResults');
    const infoDiv = document.getElementById('generatedInvoiceInfo');
    
    infoDiv.innerHTML = `
        <div class="invoice-info">
            <h4>Invoice Generated Successfully!</h4>
            <div class="invoice-details">
                <p><strong>Invoice Number:</strong> \${data.invoice_number}</p>
                <p><strong>File:</strong> \${data.filename}</p>
                <p><strong>Location:</strong> \${data.gcs_uri}</p>
            </div>
        </div>
    `;
    
    resultsSection.classList.remove('hidden');
    
    // Scroll to results
    resultsSection.scrollIntoView({ behavior: 'smooth' });
    
    // Setup download button
    const downloadBtn = document.getElementById('downloadInvoiceBtn');
    if (downloadBtn) {
        downloadBtn.onclick = () => downloadGeneratedInvoice(data);
    }
    
    // Setup view button
    const viewBtn = document.getElementById('viewInvoiceBtn');
    if (viewBtn) {
        viewBtn.onclick = () => viewGeneratedInvoice(data);
    }
    
    // Setup generate another button
    const generateAnotherBtn = document.getElementById('generateAnotherBtn');
    if (generateAnotherBtn) {
        generateAnotherBtn.onclick = () => {
            resultsSection.classList.add('hidden');
            // Reset forms
            document.getElementById('simpleInvoiceForm')?.reset();
            document.getElementById('advancedInvoiceForm')?.reset();
        };
    }
}

async function downloadGeneratedInvoice(invoiceData) {
    try {
        // Open the local file path for download
        window.open(`/download/invoice/\${invoiceData.filename}`, '_blank');
    } catch (error) {
        console.error('Download error:', error);
        alert('Failed to download invoice');
    }
}

async function viewGeneratedInvoice(invoiceData) {
    try {
        // Open the PDF in a new tab
        window.open(`/view/invoice/\${invoiceData.filename}`, '_blank');
    } catch (error) {
        console.error('View error:', error);
        alert('Failed to view invoice');
    }
}

// Helper Functions
function setDefaultDates() {
    const today = new Date();
    const thirtyDaysLater = new Date(today);
    thirtyDaysLater.setDate(thirtyDaysLater.getDate() + 30);
    
    const issueDateField = document.getElementById('issueDate');
    const dueDateField = document.getElementById('dueDate');
    
    if (issueDateField) {
        issueDateField.value = today.toISOString().split('T')[0];
    }
    
    if (dueDateField) {
        dueDateField.value = thirtyDaysLater.toISOString().split('T')[0];
    }
}

function getCurrencySymbol(currency) {
    const symbols = {
        'USD': '$',
        'EUR': '€',
        'GBP': '£',
        'ILS': '₪',
        'CAD': 'C$',
        'AUD': 'A$',
        'JPY': '¥',
        'INR': '₹',
        'CNY': '¥',
        'CHF': 'CHF ',
        'SEK': 'kr ',
        'NOK': 'kr ',
        'DKK': 'kr ',
        'MXN': '$',
        'BRL': 'R$'
    };
    
    return symbols[currency] || currency + ' ';
}

function showMessage(message, type = 'info') {
    const messageDiv = document.createElement('div');
    messageDiv.className = `message message-\${type}`;
    messageDiv.textContent = message;
    
    document.body.appendChild(messageDiv);
    
    setTimeout(() => {
        messageDiv.classList.add('message-show');
    }, 100);
    
    setTimeout(() => {
        messageDiv.classList.remove('message-show');
        setTimeout(() => messageDiv.remove(), 300);
    }, 3000);
}

// ==================== VENDOR MATCHING WORKFLOW ====================
let currentInvoiceId = null;
let currentInvoiceData = null;

/**
 * Initiate invoice workflow - Main entry point for Create Bill button
 */
async function initiateInvoiceWorkflow(invoiceId) {
    console.log(`🚀 Starting invoice workflow for ${invoiceId}`);
    
    try {
        // Get invoice details from BigQuery
        const response = await fetch(`/api/invoices/${invoiceId}`);
        if (!response.ok) {
            alert('Failed to fetch invoice details');
            return;
        }
        
        const invoice = await response.json();
        console.log('📄 Invoice details:', invoice);
        
        // Check if vendor is matched
        if (!invoice.vendor_id || invoice.status === 'unmatched') {
            console.log('❌ No vendor match found - showing matching modal');
            
            // Prepare invoice data for matching modal
            const invoiceData = {
                invoice_id: invoice.invoice_id,
                vendor_name: invoice.vendor_name,
                amount: invoice.amount,
                currency: invoice.currency || 'USD',
                invoice_date: invoice.invoice_date
            };
            
            // Show vendor matching modal
            showVendorMatchingModal(invoiceData);
            alert('This invoice needs vendor matching first. Please select or create a vendor.');
            return;
        }
        
        // Vendor is matched - proceed with NetSuite bill creation
        console.log(`✅ Vendor matched: ${invoice.vendor_id}`);
        
        // Show workflow modal
        showWorkflowModal('matching');
        updateWorkflowStep('match', '✅', 'Vendor already matched');
        
        // Check if vendor exists in NetSuite
        updateWorkflowStep('netsuite-check', '🔄', 'Checking vendor in NetSuite...');
        
        const checkResponse = await fetch(`/api/netsuite/vendor/check/${invoice.vendor_id}`);
        const checkResult = await checkResponse.json();
        
        if (!checkResult.exists) {
            console.log('⚠️ Vendor not in NetSuite - syncing first...');
            updateWorkflowStep('netsuite-check', '🔄', 'Syncing vendor to NetSuite...');
            
            // Sync vendor to NetSuite first
            const syncResponse = await fetch('/api/netsuite/vendor/create', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    vendor_id: invoice.vendor_id,
                    force_resync: false
                })
            });
            
            const syncResult = await syncResponse.json();
            
            if (!syncResult.success) {
                updateWorkflowStep('netsuite-check', '❌', 'Failed to sync vendor to NetSuite');
                updateWorkflowStep('create', '❌', syncResult.error || 'Cannot create bill without vendor');
                return;
            }
            
            console.log(`✅ Vendor synced to NetSuite: ${syncResult.netsuite_id}`);
            updateWorkflowStep('netsuite-check', '✅', 'Vendor synced to NetSuite');
        } else {
            console.log('✅ Vendor exists in NetSuite');
            updateWorkflowStep('netsuite-check', '✅', 'Vendor found in NetSuite');
        }
        
        // Create bill in NetSuite
        updateWorkflowStep('create', '🔄', 'Creating bill in NetSuite...');
        
        const billResponse = await fetch(`/api/netsuite/invoice/${invoiceId}/create`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'}
        });
        
        const billResult = await billResponse.json();
        
        if (billResult.success) {
            updateWorkflowStep('create', '✅', `Bill created! ID: ${billResult.netsuite_bill_id}`);
            
            // Update UI
            document.getElementById('workflowActions').innerHTML = `
                <button onclick="closeWorkflowModal(); location.reload();" class="btn btn-primary">Done</button>
                <button onclick="window.open('https://system.netsuite.com/app/accounting/transactions/vendbill.nl?id=${billResult.netsuite_bill_id}', '_blank')" class="btn btn-secondary">View in NetSuite</button>
            `;
            
            // Refresh the invoice list after successful creation
            setTimeout(() => {
                if (typeof renderInvoiceListView === 'function') {
                    renderInvoiceListView();
                }
            }, 2000);
        } else {
            updateWorkflowStep('create', '❌', billResult.error || 'Failed to create bill');
            document.getElementById('workflowActions').innerHTML = `
                <button onclick="closeWorkflowModal()" class="btn btn-secondary">Close</button>
            `;
        }
        
    } catch (error) {
        console.error('❌ Error in invoice workflow:', error);
        alert(`Error: ${error.message}`);
        closeWorkflowModal();
    }
}

/**
 * Show vendor matching modal when invoice doesn't have a vendor
 */
function showVendorMatchingModal(invoiceData) {
    currentInvoiceData = invoiceData;
    currentInvoiceId = invoiceData.invoice_id;
    
    // Update modal content
    document.getElementById('modalInvoiceInfo').innerHTML = `
        Invoice ID: ${invoiceData.invoice_id}<br>
        Amount: ${invoiceData.currency} ${invoiceData.amount}<br>
        Date: ${invoiceData.invoice_date}
    `;
    document.getElementById('modalVendorName').textContent = invoiceData.vendor_name || 'Unknown';
    
    // Show modal
    document.getElementById('vendorMatchModal').style.display = 'block';
    
    // Automatically search for vendor
    if (invoiceData.vendor_name) {
        searchVendorsForMatching(invoiceData.vendor_name);
    }
}

/**
 * Search vendors for matching
 */
async function searchVendorsForMatching(query) {
    if (!query || query.length < 2) {
        document.getElementById('vendorSearchResults').innerHTML = '';
        return;
    }
    
    try {
        const response = await fetch(`/api/vendors/list?search=${encodeURIComponent(query)}&limit=10`);
        const data = await response.json();
        
        if (data.success && data.vendors.length > 0) {
            displayVendorSearchResults(data.vendors);
        } else {
            document.getElementById('vendorSearchResults').innerHTML = 
                '<p style="padding: 10px; color: #666;">No vendors found. Create a new vendor below.</p>';
        }
    } catch (error) {
        console.error('Error searching vendors:', error);
    }
}

/**
 * Display vendor search results
 */
function displayVendorSearchResults(vendors) {
    const html = vendors.map(vendor => `
        <div class="vendor-result-item" onclick="selectVendorForMatching('${vendor.vendor_id}', '${vendor.global_name}')">
            <strong>${vendor.global_name}</strong>
            ${vendor.tax_id ? `<br><small>Tax ID: ${vendor.tax_id}</small>` : ''}
            ${vendor.address ? `<br><small>${vendor.address}</small>` : ''}
        </div>
    `).join('');
    
    document.getElementById('vendorSearchResults').innerHTML = html;
}

/**
 * Select vendor for matching
 */
async function selectVendorForMatching(vendorId, vendorName) {
    if (!currentInvoiceId) return;
    
    // Show workflow modal
    showWorkflowModal('matching');
    
    try {
        // Update invoice with selected vendor
        const response = await fetch(`/api/invoices/${currentInvoiceId}/update-vendor`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({vendor_id: vendorId})
        });
        
        if (response.ok) {
            updateWorkflowStep('match', '✅', 'Vendor matched successfully');
            
            // Auto-proceed to NetSuite sync
            setTimeout(() => {
                syncInvoiceToNetSuite(currentInvoiceId);
            }, 1000);
        } else {
            updateWorkflowStep('match', '❌', 'Failed to match vendor');
        }
    } catch (error) {
        console.error('Error matching vendor:', error);
        updateWorkflowStep('match', '❌', 'Error occurred');
    }
}

/**
 * Show create vendor form
 */
function showCreateVendorForm() {
    document.getElementById('createVendorForm').style.display = 'block';
    document.getElementById('newVendorName').value = currentInvoiceData?.vendor_name || '';
}

/**
 * Create and match new vendor
 */
async function createAndMatchVendor() {
    const vendorData = {
        global_name: document.getElementById('newVendorName').value,
        emails: document.getElementById('newVendorEmail').value ? [document.getElementById('newVendorEmail').value] : [],
        phone_numbers: document.getElementById('newVendorPhone').value ? [document.getElementById('newVendorPhone').value] : [],
        tax_id: document.getElementById('newVendorTaxId').value,
        address: document.getElementById('newVendorAddress').value,
        vendor_type: 'Company'
    };
    
    if (!vendorData.global_name) {
        alert('Vendor name is required');
        return;
    }
    
    try {
        // Create vendor
        const createResponse = await fetch('/api/vendors/add', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(vendorData)
        });
        
        const result = await createResponse.json();
        
        if (result.success) {
            // Match to invoice
            selectVendorForMatching(result.vendor_id, vendorData.global_name);
            closeVendorModal();
        } else {
            alert('Failed to create vendor: ' + (result.error || 'Unknown error'));
        }
    } catch (error) {
        console.error('Error creating vendor:', error);
        alert('Error creating vendor');
    }
}

/**
 * Show workflow modal
 */
function showWorkflowModal(startingStep = 'upload') {
    document.getElementById('workflowModal').style.display = 'block';
    
    // Reset all steps
    document.getElementById('match-status').textContent = '⏳';
    document.getElementById('netsuite-check-status').textContent = '⏳';
    document.getElementById('create-status').textContent = '⏳';
    
    // Set initial message
    document.getElementById('workflowMessage').innerHTML = 
        '<p>Processing invoice through complete workflow...</p>';
}

/**
 * Update workflow step status
 */
function updateWorkflowStep(step, status, message) {
    const statusElement = document.getElementById(`${step}-status`);
    if (statusElement) {
        statusElement.textContent = status;
    }
    
    if (message) {
        const messageDiv = document.getElementById('workflowMessage');
        messageDiv.innerHTML = `<p>${message}</p>`;
    }
}

/**
 * Sync invoice to NetSuite with auto-vendor creation
 */
async function syncInvoiceToNetSuite(invoiceId) {
    updateWorkflowStep('netsuite-check', '🔄', 'Checking vendor in NetSuite...');
    
    try {
        // Attempt to create invoice in NetSuite
        const response = await fetch(`/api/netsuite/invoice/${invoiceId}/create`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'}
        });
        
        const result = await response.json();
        
        if (result.success) {
            updateWorkflowStep('netsuite-check', '✅', 'Vendor found/created in NetSuite');
            updateWorkflowStep('create', '✅', 'Invoice created successfully!');
            
            document.getElementById('workflowActions').innerHTML = `
                <button onclick="closeWorkflowModal()" class="btn btn-primary">Done</button>
                <button onclick="window.location.href='/netsuite-dashboard'" class="btn btn-secondary">View in NetSuite Dashboard</button>
            `;
        } else {
            updateWorkflowStep('create', '❌', result.error || 'Failed to create invoice');
        }
    } catch (error) {
        console.error('Error syncing to NetSuite:', error);
        updateWorkflowStep('create', '❌', 'Error occurred during sync');
    }
}

/**
 * Close vendor modal
 */
function closeVendorModal() {
    document.getElementById('vendorMatchModal').style.display = 'none';
    document.getElementById('vendorSearchResults').innerHTML = '';
    document.getElementById('createVendorForm').style.display = 'none';
}

/**
 * Close workflow modal
 */
function closeWorkflowModal() {
    document.getElementById('workflowModal').style.display = 'none';
}

// Close modals when clicking outside
window.onclick = function(event) {
    if (event.target.className === 'modal') {
        event.target.style.display = 'none';
    }
}

/* ==================== NETSUITE SYNC FUNCTIONS ==================== */
async function syncVendorToNetSuite(vendorId, force = false) {
    if (!vendorId) {
        console.error('No vendor ID provided for sync');
        return;
    }

    const confirmed = confirm(`Sync vendor ${vendorId} to NetSuite?`);
    if (!confirmed) return;

    try {
        const response = await fetch('/api/netsuite/vendor/create', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                vendor_id: vendorId,
                force_resync: force
            })
        });

        const result = await response.json();
        
        if (response.ok) {
            alert(`✅ Vendor synced to NetSuite!\nNetSuite ID: ${result.netsuite_id}`);
            // Refresh vendor list to show updated sync status
            searchVendors();
        } else {
            alert(`❌ Sync failed: ${result.error || 'Unknown error'}`);
        }
    } catch (error) {
        alert(`❌ Sync error: ${error.message}`);
    }
}

async function syncAllVendorsToNetSuite(vendorIds) {
    if (!vendorIds || vendorIds.length === 0) {
        alert('No vendors to sync');
        return;
    }

    const confirmed = confirm(`Sync ${vendorIds.length} vendors to NetSuite?\nThis may take a few minutes.`);
    if (!confirmed) return;

    // Show progress modal
    const modal = document.createElement('div');
    modal.style.cssText = `
        position: fixed;
        top: 50%;
        left: 50%;
        transform: translate(-50%, -50%);
        background: white;
        padding: 30px;
        border-radius: 10px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.2);
        z-index: 10000;
        min-width: 400px;
    `;
    modal.innerHTML = `
        <h3>Syncing Vendors to NetSuite</h3>
        <div id="sync-progress-container" style="margin-top: 20px;">
            <div id="sync-status" style="color: #666; margin-bottom: 10px;">Initializing...</div>
            <div style="background: #f0f0f0; border-radius: 5px; height: 30px; overflow: hidden;">
                <div id="sync-progress-bar" style="background: #667eea; height: 100%; width: 0%; transition: width 0.3s;"></div>
            </div>
            <div id="sync-details" style="margin-top: 15px; max-height: 200px; overflow-y: auto;"></div>
        </div>
    `;
    document.body.appendChild(modal);

    // Connect to SSE endpoint for progress updates
    const eventSource = new EventSource('/api/vendors/csv/sync-netsuite');
    let syncResults = { success: 0, failed: 0, skipped: 0 };

    eventSource.onmessage = function(event) {
        const data = JSON.parse(event.data);
        
        if (data.status === 'progress') {
            const percent = Math.round(data.progress * 100);
            document.getElementById('sync-progress-bar').style.width = percent + '%';
            document.getElementById('sync-status').innerHTML = `
                Processing: ${data.current}/${data.total} vendors (${percent}%)
                <br>✅ Success: ${syncResults.success} | ❌ Failed: ${syncResults.failed} | ⚠️ Skipped: ${syncResults.skipped}
            `;
        } else if (data.status === 'vendor_result') {
            if (data.success) syncResults.success++;
            else if (data.skipped) syncResults.skipped++;
            else syncResults.failed++;
            
            const detailsDiv = document.getElementById('sync-details');
            const icon = data.success ? '✅' : data.skipped ? '⚠️' : '❌';
            detailsDiv.innerHTML += `<div>${icon} ${data.vendor_name}: ${data.message}</div>`;
            detailsDiv.scrollTop = detailsDiv.scrollHeight;
        } else if (data.status === 'complete') {
            document.getElementById('sync-status').innerHTML = `
                <strong style="color: green;">Sync Complete!</strong>
                <br>✅ Success: ${syncResults.success} | ❌ Failed: ${syncResults.failed} | ⚠️ Skipped: ${syncResults.skipped}
            `;
            document.getElementById('sync-progress-bar').style.width = '100%';
            
            // Add close button
            const closeBtn = document.createElement('button');
            closeBtn.textContent = 'Close';
            closeBtn.style.cssText = 'margin-top: 20px; padding: 10px 20px; background: #667eea; color: white; border: none; border-radius: 5px; cursor: pointer;';
            closeBtn.onclick = () => {
                document.body.removeChild(modal);
                searchVendors(); // Refresh vendor list
            };
            modal.appendChild(closeBtn);
            
            eventSource.close();
        } else if (data.status === 'error') {
            document.getElementById('sync-status').innerHTML = `<strong style="color: red;">Error: ${data.error}</strong>`;
            eventSource.close();
        }
    };

    eventSource.onerror = function(error) {
        console.error('SSE Error:', error);
        document.getElementById('sync-status').innerHTML = '<strong style="color: red;">Connection lost</strong>';
        eventSource.close();
    };

    // Send the sync request with vendor IDs
    fetch('/api/vendors/csv/sync-netsuite', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ vendor_ids: vendorIds })
    });
}

/* ==================== NETSUITE VENDOR PULL FUNCTIONS ==================== */
/**
 * Pull all vendors from NetSuite and sync to BigQuery
 */
async function pullVendorsFromNetSuite() {
    console.log('Starting NetSuite vendor pull...');
    
    // Get UI elements
    const pullBtn = document.getElementById('pullVendorsBtn');
    const progressSection = document.getElementById('vendorPullProgress');
    const progressBar = document.getElementById('vendorPullProgressBar');
    const statusText = document.getElementById('vendorPullStatus');
    const detailsText = document.getElementById('vendorPullDetails');
    const resultsSection = document.getElementById('vendorPullResults');
    const statsDiv = document.getElementById('vendorPullStats');
    const errorsDiv = document.getElementById('vendorPullErrors');
    
    // Disable button and show progress
    pullBtn.disabled = true;
    progressSection.classList.remove('hidden');
    resultsSection.classList.add('hidden');
    
    // Reset progress
    progressBar.style.width = '0%';
    statusText.textContent = 'Connecting to NetSuite...';
    detailsText.textContent = '';
    
    try {
        // Create EventSource for SSE
        const response = await fetch('/api/netsuite/vendors/pull', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            }
        });
        
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';
        
        while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            
            buffer += decoder.decode(value, { stream: true });
            
            // Process complete SSE messages
            const lines = buffer.split('\n');
            buffer = lines.pop(); // Keep incomplete line in buffer
            
            for (const line of lines) {
                if (line.startsWith('data: ')) {
                    try {
                        const data = JSON.parse(line.substring(6));
                        handlePullProgress(data);
                    } catch (e) {
                        console.error('Error parsing SSE data:', e);
                    }
                }
            }
        }
        
    } catch (error) {
        console.error('Error pulling vendors:', error);
        statusText.textContent = '❌ Error: ' + error.message;
        statusText.style.color = '#dc2626';
        
        // Show error in results
        resultsSection.classList.remove('hidden');
        statsDiv.innerHTML = `
            <div class="alert-error">
                <strong>Failed to pull vendors from NetSuite</strong>
                <p>${error.message}</p>
            </div>
        `;
    } finally {
        // Re-enable button
        pullBtn.disabled = false;
    }
    
    /**
     * Handle progress updates from SSE
     */
    function handlePullProgress(data) {
        // Update progress bar
        if (data.progress !== undefined) {
            progressBar.style.width = data.progress + '%';
        }
        
        // Update status message
        if (data.message) {
            statusText.textContent = data.message;
        }
        
        // Update details
        if (data.data) {
            if (data.data.fetched !== undefined) {
                detailsText.textContent = `Vendors found: ${data.data.fetched}`;
            } else if (data.data.current !== undefined && data.data.total !== undefined) {
                detailsText.textContent = `Processing: ${data.data.current} of ${data.data.total} - ${data.data.vendor_name || ''}`;
            }
        }
        
        // Handle completion
        if (data.completed) {
            progressSection.classList.add('hidden');
            resultsSection.classList.remove('hidden');
            
            const stats = data.stats || {};
            
            // Display statistics
            statsDiv.innerHTML = `
                <div class="stats-grid" style="display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 15px;">
                    <div class="stat-card" style="padding: 15px; background: #f0f9ff; border-radius: 8px; border: 1px solid #3b82f6;">
                        <div class="stat-value" style="font-size: 24px; font-weight: bold; color: #3b82f6;">${stats.totalFetched || 0}</div>
                        <div class="stat-label" style="font-size: 14px; color: #666;">Total Fetched</div>
                    </div>
                    <div class="stat-card" style="padding: 15px; background: #f0fdf4; border-radius: 8px; border: 1px solid #22c55e;">
                        <div class="stat-value" style="font-size: 24px; font-weight: bold; color: #22c55e;">${stats.newVendors || 0}</div>
                        <div class="stat-label" style="font-size: 14px; color: #666;">New Vendors</div>
                    </div>
                    <div class="stat-card" style="padding: 15px; background: #fefce8; border-radius: 8px; border: 1px solid #facc15;">
                        <div class="stat-value" style="font-size: 24px; font-weight: bold; color: #facc15;">${stats.updatedVendors || 0}</div>
                        <div class="stat-label" style="font-size: 14px; color: #666;">Updated</div>
                    </div>
                    <div class="stat-card" style="padding: 15px; background: #fef2f2; border-radius: 8px; border: 1px solid #ef4444;">
                        <div class="stat-value" style="font-size: 24px; font-weight: bold; color: #ef4444;">${stats.failed || 0}</div>
                        <div class="stat-label" style="font-size: 14px; color: #666;">Failed</div>
                    </div>
                    <div class="stat-card" style="padding: 15px; background: #f3f4f6; border-radius: 8px; border: 1px solid #9ca3af;">
                        <div class="stat-value" style="font-size: 24px; font-weight: bold; color: #6b7280;">${Math.round(stats.duration || 0)}s</div>
                        <div class="stat-label" style="font-size: 14px; color: #666;">Duration</div>
                    </div>
                </div>
            `;
            
            // Display errors if any
            if (stats.errors && stats.errors.length > 0) {
                errorsDiv.innerHTML = `
                    <div class="error-list" style="margin-top: 20px; padding: 15px; background: #fef2f2; border-radius: 8px; border: 1px solid #ef4444;">
                        <h4 style="color: #dc2626; margin-bottom: 10px;">Errors encountered:</h4>
                        <ul style="margin: 0; padding-left: 20px;">
                            ${stats.errors.map(err => `<li style="color: #666; margin: 5px 0;">${err}</li>`).join('')}
                        </ul>
                    </div>
                `;
            } else {
                errorsDiv.innerHTML = '';
            }
        }
        
        // Handle error
        if (data.error) {
            progressSection.classList.add('hidden');
            resultsSection.classList.remove('hidden');
            
            statsDiv.innerHTML = `
                <div class="alert-error" style="padding: 15px; background: #fef2f2; border-radius: 8px; border: 1px solid #ef4444;">
                    <strong style="color: #dc2626;">❌ Error pulling vendors</strong>
                    <p style="color: #666; margin-top: 10px;">${data.message || 'Unknown error occurred'}</p>
                </div>
            `;
        }
    }
}

/**
 * Close the pull results section
 */
function closePullResults() {
    document.getElementById('vendorPullResults').classList.add('hidden');
    document.getElementById('vendorPullStats').innerHTML = '';
    document.getElementById('vendorPullErrors').innerHTML = '';
}

// ==================== NETSUITE SYNC DASHBOARD FUNCTIONS ====================

let dashboardRefreshInterval = null;
let dashboardCharts = {};

/**
 * Load and display NetSuite connection status
 */
async function loadNetSuiteConnectionStatus() {
    try {
        const response = await fetch('/api/netsuite/status');
        const data = await response.json();
        
        const statusIcon = document.getElementById('connectionStatusIcon');
        const statusText = document.getElementById('connectionStatusText');
        const accountId = document.getElementById('netsuiteAccountId');
        const env = document.getElementById('netsuiteEnv');
        const baseUrl = document.getElementById('netsuiteBaseUrl');
        const errorMsg = document.getElementById('connectionErrorMsg');
        const errorText = document.getElementById('connectionErrorText');
        
        if (data.connected) {
            // Connected successfully
            statusIcon.textContent = '✅';
            statusText.textContent = 'Connected';
            statusText.style.color = '#4ade80';
            
            // Display account details
            accountId.textContent = data.account_id || '--';
            
            // Parse environment from account ID (ends with _SB1 for sandbox)
            const isSandbox = data.account_id && data.account_id.includes('_SB');
            env.textContent = isSandbox ? 'Sandbox' : 'Production';
            
            // Format URL
            const urlDisplay = data.base_url ? new URL(data.base_url).hostname : '--';
            baseUrl.textContent = urlDisplay;
            
            // Hide error message
            errorMsg.style.display = 'none';
        } else {
            // Not connected or error
            statusIcon.textContent = '❌';
            statusText.textContent = 'Disconnected';
            statusText.style.color = '#ef4444';
            
            accountId.textContent = '--';
            env.textContent = '--';
            baseUrl.textContent = '--';
            
            // Show error message if available
            if (data.error) {
                errorText.textContent = data.error;
                errorMsg.style.display = 'block';
            } else {
                errorMsg.style.display = 'none';
            }
        }
    } catch (error) {
        console.error('Error loading NetSuite connection status:', error);
        
        // Update UI to show error state
        document.getElementById('connectionStatusIcon').textContent = '⚠️';
        document.getElementById('connectionStatusText').textContent = 'Error';
        document.getElementById('connectionStatusText').style.color = '#f59e0b';
        document.getElementById('connectionErrorText').textContent = 'Failed to check connection status';
        document.getElementById('connectionErrorMsg').style.display = 'block';
    }
}

/**
 * Test NetSuite connection
 */
async function testNetSuiteConnection() {
    const button = event.target;
    const originalText = button.textContent;
    
    try {
        // Update button to show loading
        button.disabled = true;
        button.textContent = '⏳ Testing...';
        
        const response = await fetch('/api/netsuite/test');
        const data = await response.json();
        
        if (data.success) {
            // Show success message
            button.textContent = '✅ Connected!';
            button.style.background = 'rgba(74, 222, 128, 0.3)';
            
            // Reload connection status
            await loadNetSuiteConnectionStatus();
            
            // Reset button after 3 seconds
            setTimeout(() => {
                button.textContent = originalText;
                button.style.background = 'rgba(255,255,255,0.2)';
                button.disabled = false;
            }, 3000);
        } else {
            // Show error
            button.textContent = '❌ Failed';
            button.style.background = 'rgba(239, 68, 68, 0.3)';
            
            // Display error message
            document.getElementById('connectionErrorText').textContent = data.error || 'Connection test failed';
            document.getElementById('connectionErrorMsg').style.display = 'block';
            
            // Reset button after 3 seconds
            setTimeout(() => {
                button.textContent = originalText;
                button.style.background = 'rgba(255,255,255,0.2)';
                button.disabled = false;
            }, 3000);
        }
    } catch (error) {
        console.error('Error testing NetSuite connection:', error);
        button.textContent = '❌ Error';
        button.disabled = false;
        
        setTimeout(() => {
            button.textContent = originalText;
        }, 3000);
    }
}

/**
 * Initialize NetSuite Dashboard
 */
function initializeNetSuiteDashboard() {
    console.log('📊 Initializing NetSuite Sync Dashboard...');
    
    // Load NetSuite connection status first
    loadNetSuiteConnectionStatus();
    
    // Load dashboard data
    loadDashboardData();
    
    // Setup auto-refresh
    const autoRefreshToggle = document.getElementById('autoRefreshToggle');
    if (autoRefreshToggle && autoRefreshToggle.checked) {
        startDashboardRefresh();
    }
    
    // Setup event listeners
    setupDashboardEventListeners();
}

/**
 * Setup dashboard event listeners
 */
function setupDashboardEventListeners() {
    // Auto-refresh toggle
    const autoRefreshToggle = document.getElementById('autoRefreshToggle');
    if (autoRefreshToggle) {
        autoRefreshToggle.addEventListener('change', function() {
            if (this.checked) {
                startDashboardRefresh();
            } else {
                stopDashboardRefresh();
            }
        });
    }
    
    // Manual refresh button
    const refreshBtn = document.getElementById('refreshDashboardBtn');
    if (refreshBtn) {
        refreshBtn.addEventListener('click', function() {
            loadDashboardData();
        });
    }
}

/**
 * Start auto-refresh for dashboard
 */
function startDashboardRefresh() {
    console.log('🔄 Starting dashboard auto-refresh (every 30 seconds)...');
    stopDashboardRefresh(); // Clear any existing interval
    dashboardRefreshInterval = setInterval(loadDashboardData, 30000);
}

/**
 * Stop auto-refresh for dashboard
 */
function stopDashboardRefresh() {
    if (dashboardRefreshInterval) {
        console.log('⏸️ Stopping dashboard auto-refresh');
        clearInterval(dashboardRefreshInterval);
        dashboardRefreshInterval = null;
    }
}

/**
 * Load dashboard data from API
 */
async function loadDashboardData() {
    console.log('📈 Loading dashboard data...');
    
    try {
        const response = await fetch('/api/netsuite/sync/dashboard');
        const data = await response.json();
        
        if (data.success || response.ok) {
            updateDashboardUI(data);
        } else {
            console.error('Failed to load dashboard data:', data.error);
            showDashboardError('Failed to load dashboard data');
        }
    } catch (error) {
        console.error('Error fetching dashboard data:', error);
        showDashboardError('Error connecting to server');
    }
}

/**
 * Update dashboard UI with data
 */
function updateDashboardUI(data) {
    // Update vendor statistics
    updateVendorStats(data.vendors || {});
    
    // Update invoice statistics
    updateInvoiceStats(data.invoices || {});
    
    // Update payment statistics
    updatePaymentStats(data.payments || {});
    
    // Update activity feed
    updateActivityFeed(data.recent_activities || []);
    
    // Update operation statistics
    updateOperationStats(data.operation_stats || []);
    
    // Draw charts
    drawDashboardCharts(data);
}

/**
 * Update vendor statistics
 */
function updateVendorStats(vendors) {
    document.getElementById('vendorSyncPercent').textContent = `${vendors.sync_percentage || 0}%`;
    document.getElementById('vendorsSynced').textContent = vendors.synced || 0;
    document.getElementById('vendorsNotSynced').textContent = vendors.not_synced || 0;
    document.getElementById('vendorsTotal').textContent = vendors.total || 0;
}

/**
 * Update invoice statistics
 */
function updateInvoiceStats(invoices) {
    document.getElementById('invoiceBillPercent').textContent = `${invoices.bill_percentage || 0}%`;
    document.getElementById('invoicesWithBills').textContent = invoices.with_bills || 0;
    document.getElementById('invoicesWithoutBills').textContent = invoices.without_bills || 0;
    document.getElementById('invoicesTotal').textContent = invoices.total || 0;
}

/**
 * Update payment statistics
 */
function updatePaymentStats(payments) {
    const total = payments.total || 1;
    const paid = payments.paid || 0;
    const paidPercent = total > 0 ? Math.round((paid / total) * 100) : 0;
    
    document.getElementById('paymentsPaidPercent').textContent = `${paidPercent}%`;
    document.getElementById('paymentsPaid').textContent = paid;
    document.getElementById('paymentsPending').textContent = payments.pending || 0;
    document.getElementById('paymentsOverdue').textContent = payments.overdue || 0;
    document.getElementById('paymentsPartial').textContent = payments.partial || 0;
}

/**
 * Update activity feed
 */
function updateActivityFeed(activities) {
    const feedContainer = document.getElementById('activityFeed');
    
    if (!activities || activities.length === 0) {
        feedContainer.innerHTML = '<div class="empty-state">No recent activities</div>';
        return;
    }
    
    const feedHTML = activities.map(activity => {
        const statusIcon = activity.status === 'success' ? '✅' : '❌';
        const statusClass = activity.status === 'success' ? 'status-success' : 'status-error';
        const timestamp = activity.timestamp ? new Date(activity.timestamp).toLocaleString() : 'Unknown';
        
        return `
            <div class="activity-item ${statusClass}">
                <div class="activity-icon">${statusIcon}</div>
                <div class="activity-content">
                    <div class="activity-header">
                        <span class="activity-type">${activity.operation_type || 'Unknown'}</span>
                        <span class="activity-time">${timestamp}</span>
                    </div>
                    <div class="activity-details">
                        ${activity.entity_type ? `<span class="detail-label">Type:</span> ${activity.entity_type}` : ''}
                        ${activity.entity_id ? `<span class="detail-label">ID:</span> ${activity.entity_id}` : ''}
                        ${activity.error_message ? `<div class="error-message">${activity.error_message}</div>` : ''}
                    </div>
                </div>
            </div>
        `;
    }).join('');
    
    feedContainer.innerHTML = feedHTML;
}

/**
 * Update operation statistics
 */
function updateOperationStats(stats) {
    const container = document.getElementById('operationStats');
    
    if (!stats || stats.length === 0) {
        container.innerHTML = '<div class="empty-state">No operations in the last 24 hours</div>';
        return;
    }
    
    const statsHTML = stats.map(stat => {
        const successRate = stat.total > 0 ? Math.round((stat.success / stat.total) * 100) : 0;
        
        return `
            <div class="operation-stat-card">
                <div class="operation-name">${stat.operation || 'Unknown'}</div>
                <div class="operation-metrics">
                    <div class="metric">
                        <span class="metric-value">${stat.total || 0}</span>
                        <span class="metric-label">Total</span>
                    </div>
                    <div class="metric">
                        <span class="metric-value" style="color: #22c55e;">${stat.success || 0}</span>
                        <span class="metric-label">Success</span>
                    </div>
                    <div class="metric">
                        <span class="metric-value" style="color: #ef4444;">${stat.failed || 0}</span>
                        <span class="metric-label">Failed</span>
                    </div>
                    <div class="metric">
                        <span class="metric-value">${successRate}%</span>
                        <span class="metric-label">Success Rate</span>
                    </div>
                    <div class="metric">
                        <span class="metric-value">${stat.avg_duration || 0}s</span>
                        <span class="metric-label">Avg Duration</span>
                    </div>
                </div>
            </div>
        `;
    }).join('');
    
    container.innerHTML = statsHTML;
}

/**
 * Draw dashboard charts using Canvas API
 */
function drawDashboardCharts(data) {
    // Draw vendor sync chart
    drawDonutChart('vendorSyncChart', [
        { label: 'Synced', value: data.vendors?.synced || 0, color: '#22c55e' },
        { label: 'Not Synced', value: data.vendors?.not_synced || 0, color: '#ef4444' }
    ]);
    
    // Draw invoice sync chart
    drawDonutChart('invoiceSyncChart', [
        { label: 'With Bills', value: data.invoices?.with_bills || 0, color: '#3b82f6' },
        { label: 'Without Bills', value: data.invoices?.without_bills || 0, color: '#f59e0b' }
    ]);
    
    // Draw payment status chart
    drawDonutChart('paymentStatusChart', [
        { label: 'Paid', value: data.payments?.paid || 0, color: '#22c55e' },
        { label: 'Pending', value: data.payments?.pending || 0, color: '#f59e0b' },
        { label: 'Overdue', value: data.payments?.overdue || 0, color: '#ef4444' },
        { label: 'Partial', value: data.payments?.partial || 0, color: '#8b5cf6' }
    ]);
}

/**
 * Draw a simple donut chart using Canvas API
 */
function drawDonutChart(canvasId, data) {
    const canvas = document.getElementById(canvasId);
    if (!canvas) return;
    
    const ctx = canvas.getContext('2d');
    const centerX = canvas.width / 2;
    const centerY = canvas.height / 2;
    const radius = Math.min(centerX, centerY) - 10;
    const innerRadius = radius * 0.5;
    
    // Clear canvas
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    
    // Calculate total
    const total = data.reduce((sum, item) => sum + item.value, 0);
    if (total === 0) return;
    
    // Draw segments
    let currentAngle = -Math.PI / 2; // Start at top
    
    data.forEach(item => {
        if (item.value === 0) return;
        
        const sliceAngle = (item.value / total) * 2 * Math.PI;
        
        // Draw outer arc
        ctx.beginPath();
        ctx.arc(centerX, centerY, radius, currentAngle, currentAngle + sliceAngle);
        ctx.arc(centerX, centerY, innerRadius, currentAngle + sliceAngle, currentAngle, true);
        ctx.closePath();
        ctx.fillStyle = item.color;
        ctx.fill();
        
        currentAngle += sliceAngle;
    });
    
    // Draw center text if needed
    ctx.fillStyle = '#333';
    ctx.font = 'bold 14px sans-serif';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    // You can add center text here if needed
}

/**
 * Show dashboard error message
 */
function showDashboardError(message) {
    const feedContainer = document.getElementById('activityFeed');
    if (feedContainer) {
        feedContainer.innerHTML = `
            <div class="alert-error">
                <strong>Error loading dashboard</strong>
                <p>${message}</p>
            </div>
        `;
    }
}

/**
 * Sync all payments from NetSuite
 */
async function syncAllPayments() {
    console.log('💳 Starting payment sync...');
    
    const eventSource = new EventSource('/api/netsuite/sync/payments');
    
    eventSource.onmessage = function(event) {
        const data = JSON.parse(event.data);
        console.log('Payment sync progress:', data);
        
        if (data.completed) {
            eventSource.close();
            loadDashboardData(); // Refresh dashboard
            alert('Payment sync completed successfully!');
        }
        
        if (data.error) {
            eventSource.close();
            alert(`Payment sync failed: ${data.message}`);
        }
    };
    
    eventSource.onerror = function() {
        eventSource.close();
        alert('Payment sync connection error');
    };
}
