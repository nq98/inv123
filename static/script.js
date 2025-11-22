const uploadArea = document.getElementById('uploadArea');
const fileInput = document.getElementById('fileInput');
const uploadForm = document.getElementById('uploadForm');
const submitBtn = document.getElementById('submitBtn');
const loading = document.getElementById('loading');
const results = document.getElementById('results');
const resultContent = document.getElementById('resultContent');

let selectedFile = null;

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
    
    const displayData = Object.keys(validated).length > 0 ? validated : {
        vendor_name: rawEntities.supplier_name,
        invoice_number: rawEntities.invoice_id,
        invoice_date: rawEntities.invoice_date,
        total_amount: rawEntities.total_amount,
        currency: rawEntities.currency,
        line_items: rawEntities.line_item || []
    };
    
    if (displayData.vendor_name || displayData.vendor_id || displayData.vendor?.name) {
        const vendorName = displayData.vendor?.name || displayData.vendor_name;
        const vendorId = displayData.vendor?.matched_db_id || displayData.vendor_id;
        html += `
            <div class="result-section">
                <h3>Vendor Information</h3>
                <div class="result-grid">
                    ${vendorName ? `<div class="result-item"><strong>Vendor Name</strong><span>${vendorName}</span></div>` : ''}
                    ${vendorId ? `<div class="result-item"><strong>Vendor ID</strong><span>${vendorId}</span></div>` : ''}
                </div>
            </div>
        `;
    }
    
    if (displayData.invoice_number || displayData.invoice_date || displayData.due_date) {
        html += `
            <div class="result-section">
                <h3>Invoice Details</h3>
                <div class="result-grid">
                    ${displayData.invoice_number ? `<div class="result-item"><strong>Invoice Number</strong><span>${displayData.invoice_number}</span></div>` : ''}
                    ${displayData.invoice_date ? `<div class="result-item"><strong>Invoice Date</strong><span>${displayData.invoice_date}</span></div>` : ''}
                    ${displayData.due_date ? `<div class="result-item"><strong>Due Date</strong><span>${displayData.due_date}</span></div>` : ''}
                    ${displayData.currency ? `<div class="result-item"><strong>Currency</strong><span>${displayData.currency}</span></div>` : ''}
                </div>
            </div>
        `;
    }
    
    if (displayData.total_amount || displayData.tax_amount || displayData.subtotal) {
        html += `
            <div class="result-section">
                <h3>Amounts</h3>
                <div class="result-grid">
                    ${displayData.subtotal ? `<div class="result-item"><strong>Subtotal</strong><span>${displayData.subtotal}</span></div>` : ''}
                    ${displayData.tax_amount ? `<div class="result-item"><strong>Tax</strong><span>${displayData.tax_amount}</span></div>` : ''}
                    ${displayData.total_amount ? `<div class="result-item"><strong>Total Amount</strong><span>${displayData.total_amount}</span></div>` : ''}
                </div>
            </div>
        `;
    }
    
    if (displayData.line_items && displayData.line_items.length > 0) {
        html += `
            <div class="result-section">
                <h3>Line Items</h3>
                <table class="line-items">
                    <thead>
                        <tr>
                            <th>Description</th>
                            <th>Quantity</th>
                            <th>Unit Price</th>
                            <th>Amount</th>
                        </tr>
                    </thead>
                    <tbody>
        `;
        
        displayData.line_items.forEach(item => {
            html += `
                <tr>
                    <td>${item.description || '-'}</td>
                    <td>${item.quantity || '-'}</td>
                    <td>${item.unit_price || item.unit_cost || '-'}</td>
                    <td>${item.amount || '-'}</td>
                </tr>
            `;
        });
        
        html += `
                    </tbody>
                </table>
            </div>
        `;
    }
    
    if (displayData.math_verification) {
        const mathStatus = displayData.math_verification.all_valid ? 'success' : 'warning';
        html += `
            <div class="result-section">
                <h3>Math Verification</h3>
                <span class="${mathStatus}-badge">${displayData.math_verification.all_valid ? '✓ All Calculations Valid' : '⚠ Some Calculations Need Review'}</span>
            </div>
        `;
    }
    
    if (!html.includes('result-section')) {
        html += `
            <div class="result-section">
                <p>No structured data could be extracted. Check the console for raw data.</p>
                <details style="margin-top: 15px;">
                    <summary style="cursor: pointer; font-weight: 600;">View Raw Response</summary>
                    <pre style="background: #f5f5f5; padding: 15px; border-radius: 6px; overflow-x: auto; margin-top: 10px;">${JSON.stringify(data, null, 2)}</pre>
                </details>
            </div>
        `;
    }
    
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
