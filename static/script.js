const uploadArea = document.getElementById('uploadArea');
const fileInput = document.getElementById('fileInput');
const uploadForm = document.getElementById('uploadForm');
const submitBtn = document.getElementById('submitBtn');
const loading = document.getElementById('loading');
const results = document.getElementById('results');
const resultContent = document.getElementById('resultContent');

const gmailConnectBtn = document.getElementById('gmailConnectBtn');
const gmailImportBtn = document.getElementById('gmailImportBtn');
const gmailDisconnectBtn = document.getElementById('gmailDisconnectBtn');
const gmailStatus = document.getElementById('gmailStatus');
const gmailConnectSection = document.getElementById('gmailConnectSection');
const gmailImportSection = document.getElementById('gmailImportSection');
const gmailImportResults = document.getElementById('gmailImportResults');
const gmailMaxResults = document.getElementById('gmailMaxResults');

let selectedFile = null;

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

function addTerminalLine(message, type = 'info') {
    const line = document.createElement('div');
    line.className = `terminal-line ${type}`;
    line.textContent = message;
    terminalOutput.appendChild(line);
    terminalOutput.scrollTop = terminalOutput.scrollHeight;
}

function clearTerminal() {
    terminalOutput.innerHTML = '';
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
        
        eventSource.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                
                if (data.type === 'complete') {
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
                    
                } else if (data.type === 'error') {
                    addTerminalLine(data.message, 'error');
                    eventSource.close();
                    gmailImportBtn.disabled = false;
                    gmailImportBtn.textContent = '🔍 Start Import';
                    
                } else {
                    addTerminalLine(data.message, data.type);
                }
                
            } catch (e) {
                console.error('Error parsing SSE data:', e);
            }
        };
        
        eventSource.onerror = (error) => {
            console.error('SSE Error:', error);
            addTerminalLine('❌ Connection error occurred', 'error');
            eventSource.close();
            gmailImportBtn.disabled = false;
            gmailImportBtn.textContent = '🔍 Start Smart Scan';
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
        const lineItems = invoice.line_items || [];
        
        html += `
            <div style="background: white; border: 2px solid #667eea; border-radius: 8px; padding: 20px; margin-bottom: 20px; box-shadow: 0 2px 8px rgba(0,0,0,0.1);">
                <div style="display: flex; justify-content: space-between; align-items: start; margin-bottom: 15px; border-bottom: 2px solid #f0f0f0; padding-bottom: 15px;">
                    <div>
                        <h4 style="margin: 0 0 5px 0; color: #667eea; font-size: 18px;">Invoice #${idx + 1}: ${invoice.vendor || 'Unknown Vendor'}</h4>
                        <p style="margin: 0; color: #666; font-size: 13px;">From: ${invoice.sender || 'Unknown'}</p>
                        <p style="margin: 5px 0 0 0; color: #666; font-size: 13px;">Date: ${invoice.date || 'N/A'}</p>
                    </div>
                    <div style="text-align: right;">
                        <div style="font-size: 24px; font-weight: bold; color: #2e7d32;">${invoice.currency || ''} ${invoice.total || 'N/A'}</div>
                        <div style="font-size: 12px; color: #666;">Invoice #${invoice.invoice_number || 'N/A'}</div>
                    </div>
                </div>
                
                <div style="display: grid; grid-template-columns: repeat(2, 1fr); gap: 15px; margin-bottom: 15px;">
                    <div>
                        <strong style="color: #555;">📧 Email Subject:</strong>
                        <p style="margin: 5px 0; color: #333;">${invoice.subject || 'N/A'}</p>
                    </div>
                    <div>
                        <strong style="color: #555;">🏢 Vendor:</strong>
                        <p style="margin: 5px 0; color: #333;">${invoice.vendor || 'N/A'}</p>
                    </div>
                </div>
                
                ${lineItems.length > 0 ? `
                    <div style="margin-top: 15px;">
                        <strong style="color: #555;">📝 Line Items:</strong>
                        <table style="width: 100%; margin-top: 10px; border-collapse: collapse;">
                            <thead>
                                <tr style="background: #f5f5f5;">
                                    <th style="padding: 8px; text-align: left; border: 1px solid #ddd;">Description</th>
                                    <th style="padding: 8px; text-align: right; border: 1px solid #ddd;">Quantity</th>
                                    <th style="padding: 8px; text-align: right; border: 1px solid #ddd;">Unit Price</th>
                                    <th style="padding: 8px; text-align: right; border: 1px solid #ddd;">Total</th>
                                </tr>
                            </thead>
                            <tbody>
                                ${lineItems.map(item => `
                                    <tr>
                                        <td style="padding: 8px; border: 1px solid #ddd;">${item.description || 'N/A'}</td>
                                        <td style="padding: 8px; text-align: right; border: 1px solid #ddd;">${item.quantity || '-'}</td>
                                        <td style="padding: 8px; text-align: right; border: 1px solid #ddd;">${item.unit_price || '-'}</td>
                                        <td style="padding: 8px; text-align: right; border: 1px solid #ddd;">${item.total || '-'}</td>
                                    </tr>
                                `).join('')}
                            </tbody>
                        </table>
                    </div>
                ` : ''}
                
                <button onclick="toggleFullData(${idx})" style="margin-top: 15px; padding: 8px 16px; background: #667eea; color: white; border: none; border-radius: 4px; cursor: pointer; font-size: 14px;">
                    View Full Extracted Data
                </button>
                
                <div id="fullData${idx}" style="display: none; margin-top: 15px; background: #f9f9f9; padding: 15px; border-radius: 4px; max-height: 400px; overflow-y: auto;">
                    <pre style="margin: 0; font-size: 12px; white-space: pre-wrap;">${JSON.stringify(fullData, null, 2)}</pre>
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

checkGmailStatus();

const urlParams = new URLSearchParams(window.location.search);
if (urlParams.get('gmail_connected') === 'true') {
    window.history.replaceState({}, document.title, window.location.pathname);
    checkGmailStatus();
}

uploadArea.addEventListener('click', () => fileInput.click());

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
        handleFileSelect(files[0]);
    }
});

fileInput.addEventListener('change', (e) => {
    if (e.target.files.length > 0) {
        handleFileSelect(e.target.files[0]);
    }
});

function handleFileSelect(file) {
    selectedFile = file;
    uploadArea.querySelector('p').textContent = `Selected: ${file.name}`;
    submitBtn.disabled = false;
}

uploadForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    
    if (!selectedFile) return;
    
    const formData = new FormData();
    formData.append('file', selectedFile);
    
    loading.classList.remove('hidden');
    results.classList.add('hidden');
    submitBtn.disabled = true;
    
    try {
        const response = await fetch('/upload', {
            method: 'POST',
            body: formData
        });
        
        const contentType = response.headers.get('content-type');
        if (!contentType || !contentType.includes('application/json')) {
            const text = await response.text();
            throw new Error(`Server returned non-JSON response: ${text.substring(0, 200)}`);
        }
        
        const data = await response.json();
        
        loading.classList.add('hidden');
        displayResults(data);
        
    } catch (error) {
        loading.classList.add('hidden');
        results.classList.remove('hidden');
        resultContent.innerHTML = `
            <div class="error-message">
                <strong>Error:</strong> ${error.message}
            </div>
        `;
        console.error('Upload error:', error);
    }
});

function displayResults(data) {
    results.classList.remove('hidden');
    
    if (data.status === 'error') {
        resultContent.innerHTML = `
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
    
    let html = `<span class="success-badge">✓ Processing Complete</span>`;
    
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
