// Simple, direct invoice actions without ANY popups or alerts

async function createBillInNetSuite(invoiceId, skipVendorCheck = false) {
    // Find the button that was clicked
    const button = document.querySelector(`button[onclick="createBillInNetSuite('${invoiceId}')"]`);
    const originalText = button.innerHTML;
    const originalBg = button.style.backgroundColor;
    
    // Add CSS animations if not exists
    if (!document.getElementById('bill-btn-animations')) {
        const style = document.createElement('style');
        style.id = 'bill-btn-animations';
        style.textContent = `
            @keyframes pulse {
                0%, 100% { opacity: 1; transform: scale(1); }
                50% { opacity: 0.8; transform: scale(0.98); }
            }
            .status-badge {
                position: absolute;
                top: -25px;
                left: 50%;
                transform: translateX(-50%);
                background: #333;
                color: white;
                padding: 4px 8px;
                border-radius: 4px;
                font-size: 11px;
                white-space: nowrap;
                z-index: 1000;
                box-shadow: 0 2px 4px rgba(0,0,0,0.2);
            }
        `;
        document.head.appendChild(style);
    }
    
    // Create status badge
    const statusBadge = document.createElement('div');
    statusBadge.className = 'status-badge';
    statusBadge.textContent = 'Checking invoice...';
    button.style.position = 'relative';
    button.parentElement.style.position = 'relative';
    button.parentElement.appendChild(statusBadge);
    
    // Show loading state with animation
    button.disabled = true;
    button.innerHTML = '⏳ PROCESSING...';
    button.style.backgroundColor = '#fbbf24';
    button.style.color = '#000';
    button.style.fontWeight = 'bold';
    button.style.animation = 'pulse 1s infinite';
    
    try {
        // First, get invoice details
        statusBadge.textContent = 'Loading invoice...';
        const invoiceResponse = await fetch(`/api/invoices/${invoiceId}`);
        
        if (!invoiceResponse.ok) {
            throw new Error('Failed to fetch invoice details');
        }
        
        const invoice = await invoiceResponse.json();
        
        // Check if vendor exists
        if (!invoice.vendor_id) {
            button.innerHTML = '❌ NO VENDOR MATCHED';
            button.style.backgroundColor = '#ef4444';
            button.style.color = 'white';
            button.style.animation = 'none';
            button.disabled = false;
            statusBadge.textContent = 'Cannot create bill without vendor';
            statusBadge.style.backgroundColor = '#ef4444';
            // NO ALERT - just show in button
            console.error('Cannot create bill: No vendor matched for this invoice');
            
            setTimeout(() => {
                button.innerHTML = originalText;
                button.style.backgroundColor = originalBg;
                button.style.color = '';
                button.style.fontWeight = '';
                button.disabled = false;
                statusBadge.remove();
            }, 5000);
            return;
        }
        
        // Skip vendor check if we just created the vendor
        if (!skipVendorCheck) {
            // Check vendor in NetSuite
            statusBadge.textContent = 'Checking vendor in NetSuite...';
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
                button.innerHTML = '⚠️ CREATING VENDOR...';
                button.style.backgroundColor = '#f59e0b';
                button.style.color = 'white';
                statusBadge.textContent = 'Vendor not in NetSuite, creating...';
                statusBadge.style.backgroundColor = '#f59e0b';
                
                // Create vendor first
                console.log(`Creating vendor "${invoice.vendor_name}" in NetSuite...`);
                
                const createVendorResponse = await fetch('/api/netsuite/vendor/create', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ vendor_id: invoice.vendor_id })
                });
                
                const vendorResult = await createVendorResponse.json();
                
                if (!createVendorResponse.ok || !vendorResult.success) {
                    throw new Error(vendorResult.error || 'Failed to create vendor');
                }
                
                // Vendor created - show brief success
                button.innerHTML = '✅ VENDOR CREATED!';
                button.style.backgroundColor = '#10b981';
                statusBadge.textContent = `Vendor ID: ${vendorResult.netsuite_id}`;
                statusBadge.style.backgroundColor = '#10b981';
                console.log(`Vendor created: ${vendorResult.netsuite_id}`);
                
                // Brief pause to show vendor success
                await new Promise(resolve => setTimeout(resolve, 1000));
            }
        }
        
        // Now create the bill
        statusBadge.textContent = 'Creating bill in NetSuite...';
        statusBadge.style.backgroundColor = '#3b82f6';
        button.innerHTML = '📄 CREATING BILL...';
        button.style.backgroundColor = '#3b82f6';
        
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
            // SUCCESS - Show very clear success state
            button.innerHTML = '✅ BILL CREATED SUCCESSFULLY!';
            button.style.backgroundColor = '#10b981';
            button.style.color = 'white';
            button.style.fontWeight = 'bold';
            button.style.animation = 'none';
            button.className = 'btn btn-success btn-sm';
            button.disabled = true;
            
            statusBadge.textContent = `Bill #${result.netsuite_bill_id || 'Created'} in NetSuite`;
            statusBadge.style.backgroundColor = '#10b981';
            
            // NO ALERT - just console log and button feedback
            console.log(`Bill successfully created in NetSuite! NetSuite Bill ID: ${result.netsuite_bill_id}`);
            
            // Keep success visible longer, then reload
            setTimeout(() => {
                statusBadge.remove();
                location.reload();
            }, 3000);
        } else {
            throw new Error(result.error || 'Failed to create bill');
        }
        
    } catch (error) {
        console.error('Error creating bill:', error);
        button.innerHTML = '❌ FAILED TO CREATE BILL';
        button.style.backgroundColor = '#ef4444';
        button.style.color = 'white';
        button.style.fontWeight = 'bold';
        button.style.animation = 'none';
        button.disabled = false;
        
        statusBadge.textContent = error.message.substring(0, 50);
        statusBadge.style.backgroundColor = '#ef4444';
        
        // NO ALERT - just show error in console and button
        console.error('Failed to create bill in NetSuite:', error.message);
        
        // Reset button after 5 seconds
        setTimeout(() => {
            button.innerHTML = originalText;
            button.style.backgroundColor = originalBg;
            button.style.color = '';
            button.style.fontWeight = '';
            statusBadge.remove();
        }, 5000);
    }
}

// Simple function to show invoice details
function viewInvoiceDetails(invoiceId) {
    window.open(`/api/invoices/${invoiceId}`, '_blank');
}

// Export functions for use
window.createBillInNetSuite = createBillInNetSuite;
window.viewInvoiceDetails = viewInvoiceDetails;