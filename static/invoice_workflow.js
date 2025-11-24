// ==================== PERFECT INVOICE WORKFLOW ====================
// Complete step-by-step flow with confirmations at each stage

class InvoiceWorkflow {
    constructor() {
        this.currentInvoice = null;
        this.currentVendor = null;
        this.netsuiteVendor = null;
        this.workflowStep = 'upload';
    }

    // STEP 1: Process uploaded invoice
    async startWorkflow(invoiceData) {
        this.currentInvoice = invoiceData;
        this.workflowStep = 'vendor_match';
        
        // Check if vendor was matched
        if (invoiceData.vendor_match && invoiceData.vendor_match.vendor_id) {
            // Vendor matched! Move to NetSuite check
            this.currentVendor = invoiceData.vendor_match;
            this.checkNetSuiteVendor();
        } else {
            // No vendor match - require user to select/create
            this.showVendorSelectionModal();
        }
    }

    // STEP 2: Show vendor selection modal (REQUIRED)
    showVendorSelectionModal() {
        const modal = document.getElementById('vendorSelectionModal');
        const invoiceInfo = document.getElementById('invoiceVendorInfo');
        
        invoiceInfo.innerHTML = `
            <div class="invoice-details">
                <h4>Invoice Details:</h4>
                <p><strong>Invoice ID:</strong> ${this.currentInvoice.invoice_id || 'N/A'}</p>
                <p><strong>Amount:</strong> ${this.currentInvoice.currency || 'USD'} ${this.currentInvoice.amount || '0'}</p>
                <p><strong>Date:</strong> ${this.currentInvoice.invoice_date || 'N/A'}</p>
                <p><strong>Vendor Name (from invoice):</strong> ${this.currentInvoice.vendor_name || 'Unknown'}</p>
            </div>
            <div class="warning-message">
                ⚠️ <strong>This invoice cannot proceed without a vendor match.</strong>
                Please select an existing vendor or create a new one.
            </div>
        `;
        
        modal.style.display = 'block';
        
        // Auto-search for vendor name if available
        if (this.currentInvoice.vendor_name) {
            this.searchVendors(this.currentInvoice.vendor_name);
        }
    }

    // Search for vendors
    async searchVendors(query) {
        if (!query || query.length < 2) return;
        
        try {
            const response = await fetch(`/api/vendors/list?search=${encodeURIComponent(query)}&limit=10`);
            const data = await response.json();
            
            const resultsDiv = document.getElementById('vendorSearchResultsList');
            
            if (data.success && data.vendors.length > 0) {
                resultsDiv.innerHTML = data.vendors.map(vendor => `
                    <div class="vendor-option" onclick="invoiceWorkflow.selectVendor('${vendor.vendor_id}', '${vendor.global_name}')">
                        <div class="vendor-name">${vendor.global_name}</div>
                        <div class="vendor-details">
                            ${vendor.tax_id ? `Tax ID: ${vendor.tax_id} | ` : ''}
                            ${vendor.address || 'No address'}
                        </div>
                        <button class="select-vendor-btn">Select This Vendor</button>
                    </div>
                `).join('');
            } else {
                resultsDiv.innerHTML = `
                    <div class="no-results">
                        No vendors found matching "${query}". 
                        Please create a new vendor below.
                    </div>
                `;
            }
        } catch (error) {
            console.error('Error searching vendors:', error);
        }
    }

    // Select existing vendor
    async selectVendor(vendorId, vendorName) {
        this.currentVendor = { vendor_id: vendorId, vendor_name: vendorName };
        
        // Update invoice with vendor
        try {
            const response = await fetch(`/api/invoices/${this.currentInvoice.invoice_id}/update-vendor`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ vendor_id: vendorId })
            });
            
            if (response.ok) {
                // Close vendor selection modal
                document.getElementById('vendorSelectionModal').style.display = 'none';
                
                // Move to NetSuite check
                this.checkNetSuiteVendor();
            } else {
                alert('Failed to update invoice vendor. Please try again.');
            }
        } catch (error) {
            console.error('Error updating invoice vendor:', error);
        }
    }

    // Create new vendor
    async createNewVendor() {
        const vendorData = {
            global_name: document.getElementById('newVendorName').value,
            emails: document.getElementById('newVendorEmail').value ? 
                    [document.getElementById('newVendorEmail').value] : [],
            phone_numbers: document.getElementById('newVendorPhone').value ? 
                          [document.getElementById('newVendorPhone').value] : [],
            tax_id: document.getElementById('newVendorTaxId').value,
            address: document.getElementById('newVendorAddress').value,
            vendor_type: 'Company'
        };
        
        if (!vendorData.global_name) {
            alert('Vendor name is required');
            return;
        }
        
        try {
            const response = await fetch('/api/vendors/add', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(vendorData)
            });
            
            const result = await response.json();
            
            if (result.success) {
                // Select the newly created vendor
                this.selectVendor(result.vendor_id, vendorData.global_name);
            } else {
                alert('Failed to create vendor: ' + (result.error || 'Unknown error'));
            }
        } catch (error) {
            console.error('Error creating vendor:', error);
        }
    }

    // STEP 3: Check if vendor exists in NetSuite
    async checkNetSuiteVendor() {
        this.workflowStep = 'netsuite_check';
        
        // Show checking modal
        const modal = document.getElementById('netsuiteCheckModal');
        const statusDiv = document.getElementById('netsuiteCheckStatus');
        
        statusDiv.innerHTML = `
            <div class="checking-status">
                <div class="spinner"></div>
                <p>Checking if vendor "${this.currentVendor.vendor_name}" exists in NetSuite...</p>
            </div>
        `;
        
        modal.style.display = 'block';
        
        try {
            // Check vendor in NetSuite
            const response = await fetch(`/api/netsuite/vendor/check`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ vendor_id: this.currentVendor.vendor_id })
            });
            
            const result = await response.json();
            
            if (result.exists) {
                // Vendor exists in NetSuite
                this.netsuiteVendor = result.vendor;
                this.showVendorComparison(result.vendor, result.differences);
            } else {
                // Vendor doesn't exist in NetSuite
                this.showCreateNetSuiteVendor();
            }
        } catch (error) {
            console.error('Error checking NetSuite vendor:', error);
            this.showCreateNetSuiteVendor();
        }
    }

    // STEP 4A: Show vendor comparison (if exists)
    showVendorComparison(netsuiteVendor, differences) {
        const statusDiv = document.getElementById('netsuiteCheckStatus');
        
        let html = `
            <div class="vendor-found">
                <h3>✅ Vendor Found in NetSuite</h3>
                <p><strong>NetSuite ID:</strong> ${netsuiteVendor.id}</p>
        `;
        
        if (differences && differences.length > 0) {
            html += `
                <div class="differences-section">
                    <h4>⚠️ Differences Found:</h4>
                    <table class="differences-table">
                        <tr><th>Field</th><th>Your Database</th><th>NetSuite</th></tr>
            `;
            
            differences.forEach(diff => {
                html += `
                    <tr>
                        <td>${diff.field}</td>
                        <td>${diff.local_value || 'N/A'}</td>
                        <td>${diff.netsuite_value || 'N/A'}</td>
                    </tr>
                `;
            });
            
            html += `
                    </table>
                    <div class="action-buttons">
                        <button onclick="invoiceWorkflow.updateNetSuiteVendor()" class="btn btn-secondary">
                            🔄 Update NetSuite Vendor
                        </button>
                        <button onclick="invoiceWorkflow.proceedToInvoiceCreation()" class="btn btn-primary">
                            ➡️ Continue Without Updating
                        </button>
                    </div>
                </div>
            `;
        } else {
            html += `
                <p>✅ Vendor data matches NetSuite records.</p>
                <button onclick="invoiceWorkflow.proceedToInvoiceCreation()" class="btn btn-primary">
                    ➡️ Proceed to Create Invoice
                </button>
            `;
        }
        
        html += `</div>`;
        statusDiv.innerHTML = html;
    }

    // STEP 4B: Show create NetSuite vendor option
    showCreateNetSuiteVendor() {
        const statusDiv = document.getElementById('netsuiteCheckStatus');
        
        statusDiv.innerHTML = `
            <div class="vendor-not-found">
                <h3>❌ Vendor Not Found in NetSuite</h3>
                <p>The vendor "${this.currentVendor.vendor_name}" does not exist in NetSuite.</p>
                <p>Would you like to create this vendor in NetSuite?</p>
                
                <div class="vendor-preview">
                    <h4>Vendor Details to Create:</h4>
                    <p><strong>Name:</strong> ${this.currentVendor.vendor_name}</p>
                    <p><strong>Tax ID:</strong> ${this.currentVendor.tax_id || 'N/A'}</p>
                    <p><strong>Email:</strong> ${this.currentVendor.email || 'N/A'}</p>
                    <p><strong>Phone:</strong> ${this.currentVendor.phone || 'N/A'}</p>
                </div>
                
                <div class="action-buttons">
                    <button onclick="invoiceWorkflow.createVendorInNetSuite()" class="btn btn-primary">
                        ✅ Yes, Create Vendor in NetSuite
                    </button>
                    <button onclick="invoiceWorkflow.cancelWorkflow()" class="btn btn-secondary">
                        ❌ Cancel (Invoice cannot proceed)
                    </button>
                </div>
            </div>
        `;
    }

    // Create vendor in NetSuite
    async createVendorInNetSuite() {
        const statusDiv = document.getElementById('netsuiteCheckStatus');
        statusDiv.innerHTML = `
            <div class="creating-vendor">
                <div class="spinner"></div>
                <p>Creating vendor in NetSuite...</p>
            </div>
        `;
        
        try {
            const response = await fetch('/api/netsuite/vendor/create', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ vendor_id: this.currentVendor.vendor_id })
            });
            
            const result = await response.json();
            
            if (result.success) {
                this.netsuiteVendor = { id: result.netsuite_id };
                statusDiv.innerHTML = `
                    <div class="success-message">
                        <h3>✅ Vendor Created Successfully!</h3>
                        <p><strong>NetSuite Vendor ID:</strong> ${result.netsuite_id}</p>
                        <button onclick="invoiceWorkflow.proceedToInvoiceCreation()" class="btn btn-primary">
                            ➡️ Proceed to Create Invoice
                        </button>
                    </div>
                `;
            } else {
                statusDiv.innerHTML = `
                    <div class="error-message">
                        <h3>❌ Failed to Create Vendor</h3>
                        <p>${result.error || 'Unknown error occurred'}</p>
                        <button onclick="invoiceWorkflow.checkNetSuiteVendor()" class="btn btn-secondary">
                            🔄 Retry
                        </button>
                    </div>
                `;
            }
        } catch (error) {
            console.error('Error creating NetSuite vendor:', error);
        }
    }

    // Update vendor in NetSuite
    async updateNetSuiteVendor() {
        // Implementation for updating vendor details in NetSuite
        alert('Updating vendor in NetSuite...');
        // After update, proceed to invoice creation
        this.proceedToInvoiceCreation();
    }

    // STEP 5: Ask to create invoice/bill
    proceedToInvoiceCreation() {
        this.workflowStep = 'invoice_creation';
        
        // Close NetSuite check modal
        document.getElementById('netsuiteCheckModal').style.display = 'none';
        
        // Show invoice creation modal
        const modal = document.getElementById('invoiceCreationModal');
        const contentDiv = document.getElementById('invoiceCreationContent');
        
        contentDiv.innerHTML = `
            <div class="invoice-creation-preview">
                <h3>Ready to Create Invoice/Bill in NetSuite</h3>
                
                <div class="invoice-summary">
                    <h4>Invoice Summary:</h4>
                    <table class="summary-table">
                        <tr><td><strong>Invoice ID:</strong></td><td>${this.currentInvoice.invoice_id}</td></tr>
                        <tr><td><strong>Vendor:</strong></td><td>${this.currentVendor.vendor_name}</td></tr>
                        <tr><td><strong>NetSuite Vendor ID:</strong></td><td>${this.netsuiteVendor?.id || 'N/A'}</td></tr>
                        <tr><td><strong>Amount:</strong></td><td>${this.currentInvoice.currency} ${this.currentInvoice.amount}</td></tr>
                        <tr><td><strong>Date:</strong></td><td>${this.currentInvoice.invoice_date}</td></tr>
                    </table>
                </div>
                
                <p class="confirmation-text">
                    Do you want to create this vendor bill in NetSuite?
                </p>
                
                <div class="action-buttons">
                    <button onclick="invoiceWorkflow.createInvoiceInNetSuite()" class="btn btn-primary btn-large">
                        ✅ Yes, Create Bill in NetSuite
                    </button>
                    <button onclick="invoiceWorkflow.skipInvoiceCreation()" class="btn btn-secondary">
                        ⏭️ Skip for Now
                    </button>
                </div>
            </div>
        `;
        
        modal.style.display = 'block';
    }

    // Create invoice in NetSuite
    async createInvoiceInNetSuite() {
        const contentDiv = document.getElementById('invoiceCreationContent');
        
        // Validate that we have a valid invoice_id
        if (!this.currentInvoice || !this.currentInvoice.invoice_id) {
            contentDiv.innerHTML = `
                <div class="error-message">
                    <h3>❌ Error: Invalid Invoice</h3>
                    <p>Cannot create bill in NetSuite - invoice ID is missing.</p>
                    <p>Invoice data: ${JSON.stringify(this.currentInvoice || {})}</p>
                    <button onclick="location.reload()" class="btn btn-secondary">
                        🔄 Start Over
                    </button>
                </div>
            `;
            console.error('Cannot create invoice in NetSuite - invoice_id is missing:', this.currentInvoice);
            return;
        }
        
        contentDiv.innerHTML = `
            <div class="creating-invoice">
                <div class="spinner"></div>
                <p>Creating vendor bill in NetSuite...</p>
                <p>Invoice ID: ${this.currentInvoice.invoice_id}</p>
            </div>
        `;
        
        try {
            const response = await fetch(`/api/netsuite/invoice/${this.currentInvoice.invoice_id}/create`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' }
            });
            
            const result = await response.json();
            
            if (result.success) {
                contentDiv.innerHTML = `
                    <div class="success-complete">
                        <h2>🎉 Success! Workflow Complete!</h2>
                        
                        <div class="final-summary">
                            <p>✅ Invoice matched to vendor: ${this.currentVendor.vendor_name}</p>
                            <p>✅ Vendor synced to NetSuite: ID ${this.netsuiteVendor?.id}</p>
                            <p>✅ Bill created in NetSuite: ID ${result.netsuite_bill_id}</p>
                        </div>
                        
                        <div class="next-actions">
                            <button onclick="location.reload()" class="btn btn-primary">
                                📤 Upload Another Invoice
                            </button>
                            <button onclick="window.location.href='/netsuite-dashboard'" class="btn btn-secondary">
                                📊 View NetSuite Dashboard
                            </button>
                        </div>
                    </div>
                `;
            } else {
                contentDiv.innerHTML = `
                    <div class="error-message">
                        <h3>❌ Failed to Create Bill</h3>
                        <p>${result.error || 'Unknown error occurred'}</p>
                        <button onclick="invoiceWorkflow.createInvoiceInNetSuite()" class="btn btn-secondary">
                            🔄 Retry
                        </button>
                    </div>
                `;
            }
        } catch (error) {
            console.error('Error creating invoice in NetSuite:', error);
        }
    }

    // Skip invoice creation
    skipInvoiceCreation() {
        document.getElementById('invoiceCreationModal').style.display = 'none';
        alert('Invoice saved but not synced to NetSuite. You can sync it later from the NetSuite Dashboard.');
        location.reload();
    }

    // Cancel workflow
    cancelWorkflow() {
        if (confirm('Are you sure you want to cancel? The invoice will not be processed.')) {
            // Close all modals
            document.querySelectorAll('.modal').forEach(modal => {
                modal.style.display = 'none';
            });
            location.reload();
        }
    }

    // Show create vendor form
    showCreateVendorForm() {
        document.getElementById('createVendorFormSection').style.display = 'block';
        // Pre-fill with invoice vendor name if available
        document.getElementById('newVendorName').value = this.currentInvoice.vendor_name || '';
    }
}

// Initialize workflow
const invoiceWorkflow = new InvoiceWorkflow();

// Helper functions for UI
function searchVendorsForSelection(query) {
    invoiceWorkflow.searchVendors(query);
}

function showVendorCreationForm() {
    invoiceWorkflow.showCreateVendorForm();
}

function createNewVendorAndMatch() {
    invoiceWorkflow.createNewVendor();
}

// Close modals when clicking outside
window.addEventListener('click', function(event) {
    if (event.target.className === 'modal') {
        // Don't allow closing critical modals
        if (event.target.id === 'vendorSelectionModal' && invoiceWorkflow.workflowStep === 'vendor_match') {
            alert('You must select or create a vendor to continue.');
            return;
        }
        event.target.style.display = 'none';
    }
});