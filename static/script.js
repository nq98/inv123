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
    
    let html = `<span class="success-badge">✓ Processing Complete</span>`;
    
    if (validated.vendor_name || validated.vendor_id) {
        html += `
            <div class="result-section">
                <h3>Vendor Information</h3>
                <div class="result-grid">
                    ${validated.vendor_name ? `<div class="result-item"><strong>Vendor Name</strong><span>${validated.vendor_name}</span></div>` : ''}
                    ${validated.vendor_id ? `<div class="result-item"><strong>Vendor ID</strong><span>${validated.vendor_id}</span></div>` : ''}
                </div>
            </div>
        `;
    }
    
    if (validated.invoice_number || validated.invoice_date || validated.due_date) {
        html += `
            <div class="result-section">
                <h3>Invoice Details</h3>
                <div class="result-grid">
                    ${validated.invoice_number ? `<div class="result-item"><strong>Invoice Number</strong><span>${validated.invoice_number}</span></div>` : ''}
                    ${validated.invoice_date ? `<div class="result-item"><strong>Invoice Date</strong><span>${validated.invoice_date}</span></div>` : ''}
                    ${validated.due_date ? `<div class="result-item"><strong>Due Date</strong><span>${validated.due_date}</span></div>` : ''}
                    ${validated.currency ? `<div class="result-item"><strong>Currency</strong><span>${validated.currency}</span></div>` : ''}
                </div>
            </div>
        `;
    }
    
    if (validated.total_amount || validated.tax_amount || validated.subtotal) {
        html += `
            <div class="result-section">
                <h3>Amounts</h3>
                <div class="result-grid">
                    ${validated.subtotal ? `<div class="result-item"><strong>Subtotal</strong><span>${validated.subtotal}</span></div>` : ''}
                    ${validated.tax_amount ? `<div class="result-item"><strong>Tax</strong><span>${validated.tax_amount}</span></div>` : ''}
                    ${validated.total_amount ? `<div class="result-item"><strong>Total Amount</strong><span>${validated.total_amount}</span></div>` : ''}
                </div>
            </div>
        `;
    }
    
    if (validated.line_items && validated.line_items.length > 0) {
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
        
        validated.line_items.forEach(item => {
            html += `
                <tr>
                    <td>${item.description || '-'}</td>
                    <td>${item.quantity || '-'}</td>
                    <td>${item.unit_price || '-'}</td>
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
    
    if (validated.math_verification) {
        const mathStatus = validated.math_verification.all_valid ? 'success' : 'warning';
        html += `
            <div class="result-section">
                <h3>Math Verification</h3>
                <span class="${mathStatus}-badge">${validated.math_verification.all_valid ? '✓ All Calculations Valid' : '⚠ Some Calculations Need Review'}</span>
            </div>
        `;
    }
    
    resultContent.innerHTML = html;
}
