/**
 * NetSuite Integration Dashboard JavaScript
 * Handles real-time updates, sync operations, and dashboard interactions
 */

// Dashboard state management
let dashboardState = {
    connected: false,
    accountId: null,
    lastSync: null,
    activities: [],
    statistics: {},
    refreshInterval: null
};

// Initialize dashboard on load
document.addEventListener('DOMContentLoaded', () => {
    console.log('NetSuite Dashboard initializing...');
    
    // Initial data load
    checkNetSuiteStatus();
    loadActivities();
    loadStatistics();
    
    // Set up auto-refresh (every 30 seconds)
    dashboardState.refreshInterval = setInterval(() => {
        console.log('Auto-refreshing dashboard...');
        checkNetSuiteStatus();
        loadActivities();
        loadStatistics();
    }, 30000);
    
    // Set up event listeners
    setupEventListeners();
});

// Set up all event listeners
function setupEventListeners() {
    // Test Connection button
    const testBtn = document.getElementById('testConnectionBtn');
    if (testBtn) {
        testBtn.addEventListener('click', testConnection);
    }
    
    // Refresh Activities button
    const refreshBtn = document.getElementById('refreshActivitiesBtn');
    if (refreshBtn) {
        refreshBtn.addEventListener('click', loadActivities);
    }
    
    // Sync Vendor button
    const syncVendorBtn = document.getElementById('syncVendorBtn');
    if (syncVendorBtn) {
        syncVendorBtn.addEventListener('click', syncVendor);
    }
    
    // Sync Invoice button
    const syncInvoiceBtn = document.getElementById('syncInvoiceBtn');
    if (syncInvoiceBtn) {
        syncInvoiceBtn.addEventListener('click', syncInvoice);
    }
    
    // Bulk Sync buttons
    const bulkVendorsBtn = document.getElementById('bulkSyncVendorsBtn');
    if (bulkVendorsBtn) {
        bulkVendorsBtn.addEventListener('click', () => bulkSync('vendors'));
    }
    
    const bulkInvoicesBtn = document.getElementById('bulkSyncInvoicesBtn');
    if (bulkInvoicesBtn) {
        bulkInvoicesBtn.addEventListener('click', () => bulkSync('invoices'));
    }
}

// Check NetSuite connection status
async function checkNetSuiteStatus() {
    try {
        const response = await fetch('/api/netsuite/status');
        const data = await response.json();
        
        if (data.success) {
            updateConnectionStatus(data);
            updateAvailableActions(data.available_actions || []);
        }
    } catch (error) {
        console.error('Error checking NetSuite status:', error);
        updateConnectionStatus({ connected: false, error: 'Failed to check status' });
    }
}

// Update connection status display
function updateConnectionStatus(data) {
    // Update connection indicator
    const indicator = document.getElementById('connectionIndicator');
    if (indicator) {
        if (data.connected) {
            indicator.classList.remove('disconnected');
            indicator.classList.add('connected');
        } else {
            indicator.classList.remove('connected');
            indicator.classList.add('disconnected');
        }
    }
    
    // Update status text
    const statusText = document.getElementById('connectionStatus');
    if (statusText) {
        statusText.textContent = data.connected ? 'Connected' : 'Disconnected';
        statusText.className = `status-value ${data.connected ? 'connected' : 'disconnected'}`;
    }
    
    // Update account ID
    const accountId = document.getElementById('accountId');
    const statusAccountId = document.getElementById('statusAccountId');
    if (accountId) {
        accountId.textContent = data.account_id || 'Not Connected';
    }
    if (statusAccountId) {
        statusAccountId.textContent = data.account_id || '-';
    }
    
    // Update base URL
    const baseUrl = document.getElementById('baseUrl');
    if (baseUrl && data.base_url) {
        // Truncate long URLs for display
        const url = data.base_url;
        baseUrl.textContent = url.length > 40 ? url.substring(0, 40) + '...' : url;
        baseUrl.title = url; // Full URL on hover
    }
    
    // Update last sync
    if (data.last_sync) {
        const lastSync = document.getElementById('lastSync');
        if (lastSync) {
            lastSync.textContent = formatTimestamp(data.last_sync);
        }
    }
    
    // Update last API call
    const lastApiCall = document.getElementById('lastApiCall');
    if (lastApiCall && data.last_sync) {
        lastApiCall.textContent = formatTimestamp(data.last_sync);
    }
    
    // Store state
    dashboardState.connected = data.connected;
    dashboardState.accountId = data.account_id;
}

// Update available actions list
function updateAvailableActions(actions) {
    const actionList = document.getElementById('actionList');
    if (!actionList) return;
    
    actionList.innerHTML = '';
    
    if (!actions || actions.length === 0) {
        actionList.innerHTML = '<div class="empty-state">No actions available</div>';
        return;
    }
    
    actions.forEach(action => {
        const button = document.createElement('button');
        button.className = 'action-button';
        button.textContent = action;
        button.addEventListener('click', () => performAction(action));
        actionList.appendChild(button);
    });
}

// Load sync activities
async function loadActivities() {
    try {
        const response = await fetch('/api/netsuite/activities?limit=20');
        const data = await response.json();
        
        if (data.success) {
            displayActivities(data.activities || []);
        }
    } catch (error) {
        console.error('Error loading activities:', error);
    }
}

// Display activities in table
function displayActivities(activities) {
    const tbody = document.getElementById('activityTableBody');
    if (!tbody) return;
    
    if (!activities || activities.length === 0) {
        tbody.innerHTML = `
            <tr>
                <td colspan="6" class="empty-state">
                    <div class="empty-state-icon">📊</div>
                    <div>No sync activities yet</div>
                </td>
            </tr>
        `;
        return;
    }
    
    tbody.innerHTML = '';
    
    activities.forEach(activity => {
        const row = document.createElement('tr');
        
        // Timestamp
        const timestampCell = document.createElement('td');
        timestampCell.textContent = formatTimestamp(activity.timestamp);
        timestampCell.style.fontSize = '12px';
        row.appendChild(timestampCell);
        
        // Type
        const typeCell = document.createElement('td');
        typeCell.textContent = activity.entity_type || '-';
        row.appendChild(typeCell);
        
        // Entity
        const entityCell = document.createElement('td');
        entityCell.textContent = activity.entity_id ? activity.entity_id.substring(0, 8) + '...' : '-';
        entityCell.title = activity.entity_id || '';
        row.appendChild(entityCell);
        
        // Status
        const statusCell = document.createElement('td');
        const statusBadge = document.createElement('span');
        statusBadge.className = `status-badge ${activity.status || 'pending'}`;
        statusBadge.textContent = activity.status || 'pending';
        statusCell.appendChild(statusBadge);
        row.appendChild(statusCell);
        
        // Duration
        const durationCell = document.createElement('td');
        if (activity.duration_ms) {
            durationCell.textContent = `${activity.duration_ms}ms`;
        } else {
            durationCell.textContent = '-';
        }
        row.appendChild(durationCell);
        
        // Details
        const detailsCell = document.createElement('td');
        if (activity.error_message) {
            detailsCell.innerHTML = `<span style="color: #dc3545; font-size: 12px;" title="${activity.error_message}">Error</span>`;
        } else if (activity.netsuite_id) {
            detailsCell.innerHTML = `<span style="color: #28a745; font-size: 12px;">NS: ${activity.netsuite_id}</span>`;
        } else {
            detailsCell.textContent = activity.details || activity.action || '-';
        }
        row.appendChild(detailsCell);
        
        tbody.appendChild(row);
    });
}

// Load sync statistics
async function loadStatistics() {
    try {
        const response = await fetch('/api/netsuite/statistics');
        const data = await response.json();
        
        if (data.success && data.statistics) {
            displayStatistics(data.statistics);
        }
    } catch (error) {
        console.error('Error loading statistics:', error);
    }
}

// Display statistics
function displayStatistics(stats) {
    // Update vendor stats
    const vendorsSynced = document.getElementById('totalVendorsSynced');
    if (vendorsSynced) {
        vendorsSynced.textContent = stats.vendors?.total_synced || '0';
    }
    
    // Update invoice stats
    const invoicesSynced = document.getElementById('totalInvoicesSynced');
    if (invoicesSynced) {
        invoicesSynced.textContent = stats.invoices?.total_synced || '0';
    }
    
    // Update failed syncs
    const failedSyncs = document.getElementById('failedSyncs');
    if (failedSyncs) {
        const totalFailed = (stats.vendors?.failed || 0) + (stats.invoices?.failed || 0);
        failedSyncs.textContent = totalFailed;
    }
    
    // Update pending syncs
    const pendingSyncs = document.getElementById('pendingSyncs');
    if (pendingSyncs) {
        const totalPending = (stats.vendors?.pending || 0) + (stats.invoices?.pending || 0);
        pendingSyncs.textContent = totalPending;
    }
    
    // Update success rate
    const successRate = document.getElementById('successRateValue');
    if (successRate) {
        const rate = stats.overall?.success_rate || 0;
        successRate.textContent = `${rate.toFixed(1)}%`;
    }
    
    // Update errors if any failed syncs
    if (stats.overall?.total_failed > 0) {
        loadRecentErrors();
    }
}

// Test NetSuite connection
async function testConnection() {
    const button = document.getElementById('testConnectionBtn');
    if (button) {
        button.disabled = true;
        button.textContent = 'Testing...';
    }
    
    try {
        await checkNetSuiteStatus();
        showSyncResult('Connection test completed', 'success');
    } catch (error) {
        showSyncResult('Connection test failed: ' + error.message, 'error');
    } finally {
        if (button) {
            button.disabled = false;
            button.textContent = 'Test Connection';
        }
    }
}

// Sync vendor
async function syncVendor() {
    const input = document.getElementById('vendorIdInput');
    const button = document.getElementById('syncVendorBtn');
    
    if (!input || !input.value) {
        showSyncResult('Please enter a vendor ID', 'error');
        return;
    }
    
    const vendorId = input.value.trim();
    
    if (button) {
        button.disabled = true;
        button.textContent = 'Syncing...';
    }
    
    try {
        const response = await fetch(`/api/netsuite/sync/vendor/${vendorId}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });
        
        const data = await response.json();
        
        if (data.success) {
            showSyncResult(`Vendor ${data.vendor_name || vendorId} synced successfully! NetSuite ID: ${data.netsuite_id}`, 'success');
            input.value = '';
            // Reload activities and stats
            loadActivities();
            loadStatistics();
        } else {
            showSyncResult(`Failed to sync vendor: ${data.error}`, 'error');
        }
    } catch (error) {
        showSyncResult(`Error syncing vendor: ${error.message}`, 'error');
    } finally {
        if (button) {
            button.disabled = false;
            button.textContent = 'Sync';
        }
    }
}

// Sync invoice
async function syncInvoice() {
    const input = document.getElementById('invoiceIdInput');
    const button = document.getElementById('syncInvoiceBtn');
    
    if (!input || !input.value) {
        showSyncResult('Please enter an invoice ID', 'error');
        return;
    }
    
    const invoiceId = input.value.trim();
    
    if (button) {
        button.disabled = true;
        button.textContent = 'Syncing...';
    }
    
    try {
        const response = await fetch(`/api/netsuite/sync/invoice/${invoiceId}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });
        
        const data = await response.json();
        
        if (data.success) {
            showSyncResult(`Invoice ${invoiceId} synced successfully! NetSuite Bill ID: ${data.netsuite_bill_id}`, 'success');
            input.value = '';
            // Reload activities and stats
            loadActivities();
            loadStatistics();
        } else {
            showSyncResult(`Failed to sync invoice: ${data.error}`, 'error');
        }
    } catch (error) {
        showSyncResult(`Error syncing invoice: ${error.message}`, 'error');
    } finally {
        if (button) {
            button.disabled = false;
            button.textContent = 'Sync';
        }
    }
}

// Bulk sync
async function bulkSync(type) {
    const button = document.getElementById(`bulkSync${type === 'vendors' ? 'Vendors' : 'Invoices'}Btn`);
    
    if (button) {
        button.disabled = true;
        button.textContent = 'Syncing...';
    }
    
    try {
        const response = await fetch('/api/netsuite/sync/bulk', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ type, limit: 10 })
        });
        
        const data = await response.json();
        
        if (data.success) {
            const message = `Bulk sync completed: ${data.synced_count} synced, ${data.failed_count} failed`;
            showSyncResult(message, data.failed_count > 0 ? 'warning' : 'success');
            
            // Display details
            if (data.synced_items && data.synced_items.length > 0) {
                console.log('Synced items:', data.synced_items);
            }
            if (data.failed_items && data.failed_items.length > 0) {
                console.error('Failed items:', data.failed_items);
            }
            
            // Reload activities and stats
            loadActivities();
            loadStatistics();
        } else {
            showSyncResult(`Bulk sync failed: ${data.error}`, 'error');
        }
    } catch (error) {
        showSyncResult(`Error during bulk sync: ${error.message}`, 'error');
    } finally {
        if (button) {
            button.disabled = false;
            button.textContent = `Sync Pending ${type === 'vendors' ? 'Vendors' : 'Invoices'}`;
        }
    }
}

// Perform action based on button clicked
function performAction(action) {
    switch(action) {
        case 'Test Connection':
            testConnection();
            break;
        case 'View Sync History':
            loadActivities();
            break;
        case 'Bulk Sync Vendors':
            bulkSync('vendors');
            break;
        case 'Bulk Sync Invoices':
            bulkSync('invoices');
            break;
        default:
            console.log('Action not implemented:', action);
    }
}

// Load recent errors
async function loadRecentErrors() {
    try {
        const response = await fetch('/api/netsuite/activities?limit=10');
        const data = await response.json();
        
        if (data.success && data.activities) {
            const errors = data.activities.filter(a => a.status === 'failed');
            displayErrors(errors);
        }
    } catch (error) {
        console.error('Error loading recent errors:', error);
    }
}

// Display errors
function displayErrors(errors) {
    const errorLog = document.getElementById('errorLog');
    if (!errorLog) return;
    
    if (!errors || errors.length === 0) {
        errorLog.innerHTML = `
            <div class="empty-state">
                <div class="empty-state-icon">✅</div>
                <div>No errors to display</div>
            </div>
        `;
        return;
    }
    
    errorLog.innerHTML = '';
    
    errors.slice(0, 5).forEach(error => {
        const errorItem = document.createElement('div');
        errorItem.className = 'error-item';
        
        errorItem.innerHTML = `
            <div class="error-timestamp">${formatTimestamp(error.timestamp)}</div>
            <div class="error-message">${error.error_message || 'Unknown error'}</div>
            <button class="retry-button" onclick="retrySync('${error.entity_type}', '${error.entity_id}')">
                Retry
            </button>
        `;
        
        errorLog.appendChild(errorItem);
    });
}

// Retry sync for failed item
async function retrySync(entityType, entityId) {
    if (entityType === 'vendor') {
        document.getElementById('vendorIdInput').value = entityId;
        await syncVendor();
    } else if (entityType === 'invoice') {
        document.getElementById('invoiceIdInput').value = entityId;
        await syncInvoice();
    }
}

// Show sync result message
function showSyncResult(message, type) {
    const resultsDiv = document.getElementById('syncResults');
    const contentDiv = document.getElementById('syncResultContent');
    
    if (resultsDiv && contentDiv) {
        resultsDiv.style.display = 'block';
        
        let bgColor = '#f8f9fa';
        let textColor = '#333';
        
        switch(type) {
            case 'success':
                bgColor = '#d4edda';
                textColor = '#155724';
                break;
            case 'error':
                bgColor = '#f8d7da';
                textColor = '#721c24';
                break;
            case 'warning':
                bgColor = '#fff3cd';
                textColor = '#856404';
                break;
        }
        
        contentDiv.style.backgroundColor = bgColor;
        contentDiv.style.color = textColor;
        contentDiv.innerHTML = `
            <strong>${type === 'success' ? '✅' : type === 'error' ? '❌' : '⚠️'} ${message}</strong>
        `;
        
        // Auto-hide after 5 seconds
        setTimeout(() => {
            resultsDiv.style.display = 'none';
        }, 5000);
    }
}

// Format timestamp for display
function formatTimestamp(timestamp) {
    if (!timestamp) return 'Never';
    
    const date = new Date(timestamp);
    const now = new Date();
    const diff = now - date;
    
    // If less than 1 minute ago
    if (diff < 60000) {
        return 'Just now';
    }
    
    // If less than 1 hour ago
    if (diff < 3600000) {
        const minutes = Math.floor(diff / 60000);
        return `${minutes} minute${minutes > 1 ? 's' : ''} ago`;
    }
    
    // If less than 24 hours ago
    if (diff < 86400000) {
        const hours = Math.floor(diff / 3600000);
        return `${hours} hour${hours > 1 ? 's' : ''} ago`;
    }
    
    // Otherwise show date and time
    return date.toLocaleString();
}

// Cleanup on page unload
window.addEventListener('beforeunload', () => {
    if (dashboardState.refreshInterval) {
        clearInterval(dashboardState.refreshInterval);
    }
});