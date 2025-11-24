// Simple, direct invoice actions without ANY popups or alerts

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
            // NO ALERT - just show in button
            console.error('Cannot create bill: No vendor matched for this invoice');
            
            setTimeout(() => {
                button.innerHTML = originalText;
                button.disabled = false;
            }, 3000);
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
            
            // NO CONFIRM - just try to create vendor automatically
            console.log(`Creating vendor "${invoice.vendor_name}" in NetSuite...`);
            await createVendorInNetSuite(invoice.vendor_id, button, invoiceId);
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
            
            // NO ALERT - just console log and button feedback
            console.log(`Bill successfully created in NetSuite! NetSuite Bill ID: ${result.netsuite_bill_id}`);
            
            // Reload to update the UI
            setTimeout(() => location.reload(), 1500);
        } else {
            throw new Error(result.error || 'Failed to create bill');
        }
        
    } catch (error) {
        console.error('Error creating bill:', error);
        button.innerHTML = '❌ Failed';
        button.disabled = false;
        
        // NO ALERT - just show error in console and button
        console.error('Failed to create bill in NetSuite:', error.message);
        
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
        
        const responseText = await response.text();
        let result;
        
        try {
            result = JSON.parse(responseText);
        } catch (e) {
            // If response is HTML or invalid JSON, just log it
            console.error('Invalid JSON response:', responseText);
            throw new Error('Server error - check logs');
        }
        
        if (response.ok && result.success) {
            console.log(`Vendor created successfully in NetSuite! NetSuite ID: ${result.netsuite_id}`);
            // Now create the bill
            await createBillInNetSuite(invoiceId);
        } else {
            throw new Error(result.error || 'Failed to create vendor');
        }
    } catch (error) {
        console.error('Error creating vendor:', error);
        button.innerHTML = '❌ Failed';
        
        // NO ALERT - just console error
        console.error('Failed to create vendor:', error.message);
        
        setTimeout(() => {
            button.innerHTML = '📋 Create Bill';
            button.disabled = false;
        }, 3000);
    }
}

// Simple function to show invoice details
function viewInvoiceDetails(invoiceId) {
    window.open(`/api/invoices/${invoiceId}`, '_blank');
}

// Export functions for use
window.createBillInNetSuite = createBillInNetSuite;
window.viewInvoiceDetails = viewInvoiceDetails;