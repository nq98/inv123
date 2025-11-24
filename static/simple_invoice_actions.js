// Invoice actions with proper duplicate detection and confirmation

async function createBillInNetSuite(invoiceId, skipVendorCheck = false, forceUpdate = false) {
    // Find the button that was clicked
    const button = document.querySelector(`button[onclick*="createBillInNetSuite('${invoiceId}')"]`);
    if (!button) return;
    
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
            .confirmation-dialog {
                position: fixed;
                top: 50%;
                left: 50%;
                transform: translate(-50%, -50%);
                background: white;
                padding: 20px;
                border-radius: 8px;
                box-shadow: 0 4px 20px rgba(0,0,0,0.3);
                z-index: 10000;
                max-width: 400px;
                text-align: center;
            }
            .confirmation-overlay {
                position: fixed;
                top: 0;
                left: 0;
                right: 0;
                bottom: 0;
                background: rgba(0,0,0,0.5);
                z-index: 9999;
            }
            .confirmation-buttons {
                margin-top: 20px;
                display: flex;
                gap: 10px;
                justify-content: center;
            }
            .confirmation-buttons button {
                padding: 8px 20px;
                border-radius: 4px;
                border: none;
                cursor: pointer;
                font-weight: bold;
            }
            .btn-confirm-yes {
                background: #10b981;
                color: white;
            }
            .btn-confirm-no {
                background: #ef4444;
                color: white;
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
                // Check if vendor already exists (duplicate detection)
                const vendorResponse = await handleVendorCreation(invoice, button, statusBadge);
                if (!vendorResponse.success) {
                    throw new Error(vendorResponse.error || 'Failed to create/update vendor');
                }
                
                // Brief pause to show vendor success
                await new Promise(resolve => setTimeout(resolve, 1000));
            }
        }
        
        // Now create or update the bill based on forceUpdate flag
        if (forceUpdate) {
            // User confirmed they want to update the existing bill
            statusBadge.textContent = 'Updating bill in NetSuite...';
            statusBadge.style.backgroundColor = '#f59e0b';
            button.innerHTML = '📝 UPDATING BILL...';
            button.style.backgroundColor = '#f59e0b';
            
            const updateResponse = await fetch(`/api/netsuite/invoice/${invoiceId}/update-bill`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' }
            });
            
            const updateResult = await updateResponse.json();
            
            if (updateResponse.ok && updateResult.success) {
                button.innerHTML = '✅ BILL UPDATED!';
                button.style.backgroundColor = '#10b981';
                button.style.color = 'white';
                button.style.fontWeight = 'bold';
                button.style.animation = 'none';
                button.disabled = true;
                
                statusBadge.textContent = `Bill updated with amount $${updateResult.amount}`;
                statusBadge.style.backgroundColor = '#10b981';
                
                console.log(`Bill successfully updated in NetSuite with amount: $${updateResult.amount}`);
                
                setTimeout(() => {
                    statusBadge.remove();
                    location.reload();
                }, 3000);
            } else {
                throw new Error(updateResult.error || 'Failed to update bill');
            }
        } else {
            // Try to create the bill
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
            
            // Check if it's a duplicate bill
            if (createResponse.status === 409 && result.duplicate) {
                // Bill already exists - show confirmation dialog
                button.innerHTML = '⚠️ DUPLICATE DETECTED';
                button.style.backgroundColor = '#f59e0b';
                button.style.animation = 'none';
                statusBadge.textContent = result.message;
                statusBadge.style.backgroundColor = '#f59e0b';
                
                // Show confirmation dialog
                const userChoice = await showDuplicateConfirmation(
                    'Bill Already Exists',
                    result.message,
                    `Do you want to update the existing bill with amount $${result.invoice_amount}?`
                );
                
                if (userChoice) {
                    // User wants to update - recurse with forceUpdate=true
                    statusBadge.remove();
                    button.innerHTML = originalText;
                    button.style.backgroundColor = originalBg;
                    button.style.color = '';
                    button.style.fontWeight = '';
                    button.disabled = false;
                    
                    // Call again with forceUpdate flag
                    return createBillInNetSuite(invoiceId, true, true);
                } else {
                    // User cancelled
                    button.innerHTML = '❌ CANCELLED';
                    button.style.backgroundColor = '#6b7280';
                    statusBadge.textContent = 'Update cancelled by user';
                    statusBadge.style.backgroundColor = '#6b7280';
                    
                    setTimeout(() => {
                        button.innerHTML = originalText;
                        button.style.backgroundColor = originalBg;
                        button.style.color = '';
                        button.style.fontWeight = '';
                        button.disabled = false;
                        statusBadge.remove();
                    }, 3000);
                }
            } else if (createResponse.ok && result.success) {
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
                
                console.log(`Bill successfully created in NetSuite! NetSuite Bill ID: ${result.netsuite_bill_id}`);
                
                // Keep success visible longer, then reload
                setTimeout(() => {
                    statusBadge.remove();
                    location.reload();
                }, 3000);
            } else {
                throw new Error(result.error || 'Failed to create bill');
            }
        }
        
    } catch (error) {
        console.error('Error creating/updating bill:', error);
        button.innerHTML = '❌ FAILED';
        button.style.backgroundColor = '#ef4444';
        button.style.color = 'white';
        button.style.fontWeight = 'bold';
        button.style.animation = 'none';
        button.disabled = false;
        
        statusBadge.textContent = error.message.substring(0, 50);
        statusBadge.style.backgroundColor = '#ef4444';
        
        console.error('Failed to create/update bill in NetSuite:', error.message);
        
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

// Handle vendor creation with duplicate detection
async function handleVendorCreation(invoice, button, statusBadge) {
    button.innerHTML = '⚠️ CREATING VENDOR...';
    button.style.backgroundColor = '#f59e0b';
    button.style.color = 'white';
    statusBadge.textContent = 'Vendor not in NetSuite, creating...';
    statusBadge.style.backgroundColor = '#f59e0b';
    
    console.log(`Creating vendor "${invoice.vendor_name}" in NetSuite...`);
    
    const createVendorResponse = await fetch('/api/netsuite/vendor/create', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ vendor_id: invoice.vendor_id })
    });
    
    const vendorResult = await createVendorResponse.json();
    
    // Check if vendor is a duplicate
    if (createVendorResponse.status === 409 && vendorResult.duplicate) {
        // Vendor already exists - show confirmation
        const userChoice = await showDuplicateConfirmation(
            'Vendor Already Exists',
            vendorResult.message,
            'Do you want to update the existing vendor?'
        );
        
        if (userChoice) {
            // User wants to update vendor
            const updateResponse = await fetch('/api/netsuite/vendor/update', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ 
                    vendor_id: invoice.vendor_id,
                    force_update: true
                })
            });
            
            const updateResult = await updateResponse.json();
            
            if (updateResponse.ok && updateResult.success) {
                button.innerHTML = '✅ VENDOR UPDATED!';
                button.style.backgroundColor = '#10b981';
                statusBadge.textContent = `Vendor updated: ${updateResult.netsuite_id}`;
                statusBadge.style.backgroundColor = '#10b981';
                return { success: true, netsuite_id: updateResult.netsuite_id };
            } else {
                return { success: false, error: updateResult.error };
            }
        } else {
            // User cancelled vendor update
            return { success: false, error: 'Vendor update cancelled by user' };
        }
    } else if (createVendorResponse.ok && vendorResult.success) {
        // Vendor created successfully
        button.innerHTML = '✅ VENDOR CREATED!';
        button.style.backgroundColor = '#10b981';
        statusBadge.textContent = `Vendor ID: ${vendorResult.netsuite_id}`;
        statusBadge.style.backgroundColor = '#10b981';
        console.log(`Vendor created: ${vendorResult.netsuite_id}`);
        return { success: true, netsuite_id: vendorResult.netsuite_id };
    } else {
        return { success: false, error: vendorResult.error || 'Failed to create vendor' };
    }
}

// Show confirmation dialog for duplicates
async function showDuplicateConfirmation(title, message, question) {
    return new Promise((resolve) => {
        // Create overlay
        const overlay = document.createElement('div');
        overlay.className = 'confirmation-overlay';
        
        // Create dialog
        const dialog = document.createElement('div');
        dialog.className = 'confirmation-dialog';
        dialog.innerHTML = `
            <h3 style="margin: 0 0 10px 0; color: #f59e0b;">⚠️ ${title}</h3>
            <p style="margin: 10px 0; color: #333; font-weight: 500;">${message}</p>
            <p style="margin: 15px 0; color: #666;">${question}</p>
            <div class="confirmation-buttons">
                <button class="btn-confirm-yes">Yes, Update</button>
                <button class="btn-confirm-no">No, Cancel</button>
            </div>
        `;
        
        // Add to document
        document.body.appendChild(overlay);
        document.body.appendChild(dialog);
        
        // Handle button clicks
        dialog.querySelector('.btn-confirm-yes').onclick = () => {
            overlay.remove();
            dialog.remove();
            resolve(true);
        };
        
        dialog.querySelector('.btn-confirm-no').onclick = () => {
            overlay.remove();
            dialog.remove();
            resolve(false);
        };
        
        // Handle escape key
        const handleEscape = (e) => {
            if (e.key === 'Escape') {
                overlay.remove();
                dialog.remove();
                resolve(false);
                document.removeEventListener('keydown', handleEscape);
            }
        };
        document.addEventListener('keydown', handleEscape);
    });
}

// Simple function to show invoice details
function viewInvoiceDetails(invoiceId) {
    window.open(`/api/invoices/${invoiceId}`, '_blank');
}

// Update existing bill with correct amount
async function updateBillInNetSuite(invoiceId) {
    // Find the button that was clicked
    const button = document.querySelector(`button[onclick*="updateBillInNetSuite('${invoiceId}')"]`);
    if (!button) return;
    
    const originalText = button.innerHTML;
    const originalBg = button.style.backgroundColor;
    
    // Show loading state
    button.disabled = true;
    button.innerHTML = '⏳ UPDATING...';
    button.style.backgroundColor = '#fbbf24';
    
    try {
        const response = await fetch(`/api/netsuite/invoice/${invoiceId}/update-bill`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });
        
        const result = await response.json();
        
        if (response.ok && result.success) {
            button.innerHTML = '✅ UPDATED!';
            button.style.backgroundColor = '#10b981';
            button.style.color = 'white';
            
            console.log(`Bill updated successfully with amount: $${result.amount}`);
            
            setTimeout(() => {
                location.reload();
            }, 2000);
        } else {
            throw new Error(result.error || 'Failed to update bill');
        }
    } catch (error) {
        console.error('Error updating bill:', error);
        button.innerHTML = '❌ FAILED';
        button.style.backgroundColor = '#ef4444';
        button.style.color = 'white';
        
        setTimeout(() => {
            button.innerHTML = originalText;
            button.style.backgroundColor = originalBg;
            button.style.color = '';
            button.disabled = false;
        }, 3000);
    }
}

// Export functions for use
window.createBillInNetSuite = createBillInNetSuite;
window.updateBillInNetSuite = updateBillInNetSuite;
window.viewInvoiceDetails = viewInvoiceDetails;