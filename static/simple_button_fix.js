// Simple, reliable button implementation for Create Bill
function setupCreateBillButton(invoiceId) {
    const button = document.querySelector(`button[onclick*="${invoiceId}"]`);
    if (!button) return;
    
    // Make button look normal and clickable
    button.style.cursor = 'pointer';
    button.style.opacity = '1';
    button.disabled = false;
    button.className = 'btn btn-primary btn-sm';
    button.innerHTML = '📋 Create Bill';
}

// Ultra-simple Create Bill function
async function simpleCreateBill(invoiceId) {
    // Get the button
    const button = event.target;
    const originalText = button.innerHTML;
    
    // Show loading state
    button.innerHTML = '⏳ Creating...';
    button.disabled = true;
    button.style.backgroundColor = '#fbbf24';
    
    try {
        // Just call the API directly
        const response = await fetch(`/api/netsuite/invoice/${invoiceId}/create`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });
        
        const result = await response.json();
        
        if (response.ok || result.success) {
            // Success! 
            button.innerHTML = '✅ BILL CREATED!';
            button.style.backgroundColor = '#10b981';
            
            // Reload after 2 seconds to refresh the list
            setTimeout(() => {
                location.reload();
            }, 2000);
        } else {
            // Error
            button.innerHTML = '❌ Failed';
            button.style.backgroundColor = '#ef4444';
            
            // Reset after 3 seconds
            setTimeout(() => {
                button.innerHTML = originalText;
                button.disabled = false;
                button.style.backgroundColor = '';
            }, 3000);
        }
    } catch (error) {
        // Network error
        button.innerHTML = '❌ Error';
        button.style.backgroundColor = '#ef4444';
        
        // Reset after 3 seconds
        setTimeout(() => {
            button.innerHTML = originalText;
            button.disabled = false;
            button.style.backgroundColor = '';
        }, 3000);
    }
}

// Override the existing function
window.createBillInNetSuite = simpleCreateBill;

// Fix all buttons on page load
document.addEventListener('DOMContentLoaded', function() {
    // Find all invoice buttons and fix them
    const buttons = document.querySelectorAll('button[onclick*="createBillInNetSuite"]');
    buttons.forEach(button => {
        // Extract invoice ID
        const match = button.onclick.toString().match(/createBillInNetSuite\('([^']+)'\)/);
        if (match && match[1]) {
            setupCreateBillButton(match[1]);
        }
    });
});