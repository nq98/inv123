// ==================== TAB NAVIGATION ====================
document.addEventListener('DOMContentLoaded', function() {
    const tabButtons = document.querySelectorAll('.tab-btn');
    const tabContents = document.querySelectorAll('.tab-content');
    
    tabButtons.forEach(button => {
        button.addEventListener('click', function() {
            const tabName = this.getAttribute('data-tab');
            
            // Remove active class from all buttons and contents
            tabButtons.forEach(btn => btn.classList.remove('active'));
            tabContents.forEach(content => content.classList.remove('active'));
            
            // Add active class to clicked button and corresponding content
            this.classList.add('active');
            const targetContent = document.getElementById(`tab-${tabName}`);
            if (targetContent) {
                targetContent.classList.add('active');
            }
        });
    });
});

// ==================== INVOICE UPLOAD ====================
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
            
            if (eventSource.readyState === EventSource.CLOSED) {
                addTerminalLine('❌ Connection closed by server', 'error');
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
    
    // AUTOMATIC VENDOR MATCHING Section
    if (data.vendor_match) {
        const vendorMatch = data.vendor_match;
        const verdict = vendorMatch.verdict || 'UNKNOWN';
        const confidence = vendorMatch.confidence || 0;
        const method = vendorMatch.method || 'UNKNOWN';
        const reasoning = vendorMatch.reasoning || 'No reasoning provided';
        const invoiceVendor = vendorMatch.invoice_vendor || {};
        const databaseVendor = vendorMatch.database_vendor || null;
        
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
                            <h4 style="margin: 0; color: #495057; font-size: 15px;">Invoice Says</h4>
                        </div>
                        <div style="font-size: 13px; color: #333; line-height: 1.8;">
                            <div><strong>Name:</strong> ${invoiceVendor.name || 'Unknown'}</div>
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

// Step 2: Import CSV to BigQuery
csvImportBtn.addEventListener('click', async () => {
    if (!csvAnalysisData) {
        alert('No CSV analysis data found. Please analyze CSV first.');
        return;
    }
    
    csvImportBtn.disabled = true;
    csvImportBtn.textContent = '⏳ Importing to BigQuery...';
    
    try {
        const response = await fetch('/api/vendors/csv/import', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                columnMapping: csvAnalysisData.analysis.columnMapping,
                sourceSystem: csvAnalysisData.analysis.sourceSystemGuess || 'csv_upload'
            })
        });
        
        const data = await response.json();
        
        if (!response.ok) {
            throw new Error(data.error || 'Import failed');
        }
        
        displayCsvImportResults(data);
        
    } catch (error) {
        alert('CSV import failed: ' + error.message);
    } finally {
        csvImportBtn.disabled = false;
        csvImportBtn.textContent = '✅ Confirm & Import to BigQuery';
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

async function loadVendorList(page = 1) {
    currentVendorPage = page;
    
    vendorLoading.classList.remove('hidden');
    vendorEmptyState.classList.add('hidden');
    vendorListContainer.innerHTML = '';
    vendorPagination.classList.add('hidden');
    
    try {
        const response = await fetch(`/api/vendors/list?page=${page}&limit=${currentVendorLimit}`);
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
        
        return `
            <div class="vendor-card" id="${vendorId}">
                <div class="vendor-card-header" onclick="toggleVendorDetails('${vendorId}')">
                    <div style="flex: 1;">
                        <h3 class="vendor-name">${vendor.global_name}</h3>
                        <div class="vendor-meta">
                            <span class="vendor-id">ID: ${vendor.vendor_id}</span>
                            <span class="vendor-source">${vendor.source_system || 'Unknown'}</span>
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
        loadVendorList(currentVendorPage - 1);
    }
});

vendorNextBtn.addEventListener('click', () => {
    if (currentVendorPage < totalVendorPages) {
        loadVendorList(currentVendorPage + 1);
    }
});

vendorSearchInput.addEventListener('input', (e) => {
    clearTimeout(searchTimeout);
    
    searchTimeout = setTimeout(() => {
        const searchTerm = e.target.value.toLowerCase().trim();
        
        if (searchTerm === '') {
            filteredVendors = allVendors;
        } else {
            filteredVendors = allVendors.filter(vendor => 
                vendor.global_name.toLowerCase().includes(searchTerm) ||
                (vendor.normalized_name && vendor.normalized_name.toLowerCase().includes(searchTerm)) ||
                vendor.vendor_id.toLowerCase().includes(searchTerm)
            );
        }
        
        renderVendorList(filteredVendors);
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
    
    // Show loading
    matchLoading.classList.remove('hidden');
    matchResults.classList.add('hidden');
    
    try {
        const response = await fetch('/api/vendor/match', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                vendor_name: vendorName,
                tax_id: taxId || null,
                email_domain: emailDomain || null,
                country: country || null,
                address: address || null,
                phone: phone || null
            })
        });
        
        const data = await response.json();
        
        // Hide loading
        matchLoading.classList.add('hidden');
        
        if (data.success) {
            displayMatchResults(data.result);
        } else {
            matchResults.innerHTML = `
                <div style="padding: 20px; background: #ffebee; border-left: 4px solid #f44336; border-radius: 6px;">
                    <h3 style="color: #c62828; margin: 0 0 10px 0;">❌ Matching Failed</h3>
                    <p style="margin: 0; color: #666;">${data.error || 'Unknown error occurred'}</p>
                </div>
            `;
            matchResults.classList.remove('hidden');
        }
        
    } catch (error) {
        matchLoading.classList.add('hidden');
        matchResults.innerHTML = `
            <div style="padding: 20px; background: #ffebee; border-left: 4px solid #f44336; border-radius: 6px;">
                <h3 style="color: #c62828; margin: 0 0 10px 0;">❌ Network Error</h3>
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
