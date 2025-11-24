// Simple, direct invoice actions without complex modals

async function createBillInNetSuite(invoiceId) {
    // Find the button that was clicked
    const button = document.querySelector(`button[onclick="createBillInNetSuite('${invoiceId}')"]`);
    const originalText = button.innerHTML;
    
    // Show loading state
    button.disabled = true;
    button.innerHTML = '⏳ Creating bill...';
    
    try {
        // First, get invoice details
        const invoiceResponse = await fetch(`/api/invoices/${invoiceId}`);
        
        if (!invoiceResponse.ok) {
            throw new Error('Failed to fetch invoice details');
        }
        
        const invoice = await invoiceResponse.json();
        
        // Check if vendor exists
        if (!invoice.vendor_id) {
            button.innerHTML = '❌ No vendor matched';
            button.disabled = false;
            alert('Cannot create bill: This invoice has no vendor matched. Please match a vendor first.');
            return;
        }
        
        // Check vendor in NetSuite
        const vendorCheckResponse = await fetch('/api/netsuite/vendor/check', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ vendor_id: invoice.vendor_id })
        });
        
        if (!vendorCheckResponse.ok) {
            const errorText = await vendorCheckResponse.text();
            throw new Error(errorText || 'Failed to check vendor in NetSuite');
        }
        
        const vendorCheck = await vendorCheckResponse.json();
        
        if (!vendorCheck.success || !vendorCheck.exists_in_netsuite) {
            button.innerHTML = '❌ Vendor not in NS';
            button.disabled = false;
            
            if (confirm(`Vendor "${invoice.vendor_name}" is not in NetSuite yet. Would you like to create it?`)) {
                await createVendorInNetSuite(invoice.vendor_id, button, invoiceId);
            }
            return;
        }
        
        // Create the bill
        const createResponse = await fetch(`/api/netsuite/invoice/${invoiceId}/create`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });
        
        const responseText = await createResponse.text();
        let result;
        
        try {
            result = JSON.parse(responseText);
        } catch (e) {
            console.error('Failed to parse response:', responseText);
            throw new Error('Server returned invalid response');
        }
        
        if (createResponse.ok && result.success) {
            button.innerHTML = '✅ Bill Created';
            button.className = 'btn btn-success btn-sm';
            button.disabled = true;
            
            // Show success message
            const message = `Bill successfully created in NetSuite!\nNetSuite Bill ID: ${result.netsuite_bill_id}`;
            alert(message);
            
            // Reload to update the UI
            setTimeout(() => location.reload(), 1500);
        } else {
            throw new Error(result.error || 'Failed to create bill');
        }
        
    } catch (error) {
        console.error('Error creating bill:', error);
        button.innerHTML = '❌ Failed';
        button.disabled = false;
        
        // Show user-friendly error
        let errorMessage = 'Failed to create bill in NetSuite.\n\n';
        if (error.message.includes('<!doctype') || error.message.includes('html')) {
            errorMessage += 'The server encountered an error. Please try again.';
        } else {
            errorMessage += error.message;
        }
        alert(errorMessage);
        
        // Reset button after 3 seconds
        setTimeout(() => {
            button.innerHTML = originalText;
        }, 3000);
    }
}

async function createVendorInNetSuite(vendorId, button, invoiceId) {
    button.innerHTML = '⏳ Creating vendor...';
    
    try {
        const response = await fetch('/api/netsuite/vendor/create', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ vendor_id: vendorId })
        });
        
        const result = await response.json();
        
        if (result.success) {
            alert(`Vendor created successfully in NetSuite!\nNetSuite ID: ${result.netsuite_id}`);
            // Now create the bill
            await createBillInNetSuite(invoiceId);
        } else {
            throw new Error(result.error || 'Failed to create vendor');
        }
    } catch (error) {
        console.error('Error creating vendor:', error);
        button.innerHTML = '❌ Failed';
        alert('Failed to create vendor: ' + error.message);
    }
}

// Simple function to show invoice details
function viewInvoiceDetails(invoiceId) {
    window.open(`/api/invoices/${invoiceId}`, '_blank');
}

// Export functions for use
window.createBillInNetSuite = createBillInNetSuite;
window.viewInvoiceDetails = viewInvoiceDetails;