/**
 * NetSuite Integration Dashboard JavaScript
 * Enhanced with vendors/invoices tabs, selection management, and bulk sync
 */

// Toast Notification Function
function showToast(message, type = 'info', duration = 5000) {
    const container = document.getElementById('toast-container');
    
    const icons = {
        success: '✅',
        error: '❌',
        warning: '⚠️',
        info: 'ℹ️'
    };
    
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.innerHTML = `
        <span class="toast-icon">${icons[type]}</span>
        <span class="toast-message">${message}</span>
        <span class="toast-close" onclick="this.parentElement.remove()">✕</span>
    `;
    
    container.appendChild(toast);
    
    // Auto-remove after duration
    setTimeout(() => {
        toast.style.animation = 'fadeOut 0.3s ease-out';
        setTimeout(() => toast.remove(), 300);
    }, duration);
}

// Helper function for button loading states
function setButtonLoading(button, loading) {
    if (loading) {
        button.disabled = true;
        button.dataset.originalText = button.innerHTML;
        button.innerHTML = '<span class="spinner">⟳</span> Syncing...';
    } else {
        button.disabled = false;
        button.innerHTML = button.dataset.originalText || 'Sync';
    }
}

// Dashboard state management
let dashboardState = {
    connected: false,
    accountId: null,
    lastSync: null,
    statistics: {},
    refreshInterval: null,
    vendors: {
        data: [],
        selectedIds: new Set(),
        currentPage: 1,
        totalPages: 1,
        totalCount: 0,
        search: '',
        filter: 'all'
    },
    invoices: {
        data: [],
        selectedIds: new Set(),
        currentPage: 1,
        totalPages: 1,
        totalCount: 0,
        search: '',
        filter: 'all'
    },
    activeTab: 'vendors'
};

// Custom confirmation modal variables
let confirmationResolver = null;

// Custom confirmation modal functions
function showConfirmModal(title, message, confirmText = 'Confirm') {
    return new Promise((resolve) => {
        confirmationResolver = resolve;
        
        document.getElementById('modal-title').textContent = title;
        document.getElementById('modal-message').textContent = message;
        document.getElementById('modal-confirm-btn').textContent = confirmText;
        document.getElementById('confirmation-modal').style.display = 'flex';
    });
}

function closeConfirmModal(confirmed) {
    document.getElementById('confirmation-modal').style.display = 'none';
    if (confirmationResolver) {
        confirmationResolver(confirmed);
        confirmationResolver = null;
    }
}

// Initialize dashboard on load
document.addEventListener('DOMContentLoaded', () => {
    console.log('NetSuite Dashboard initializing...');
    
    // Initial data load
    checkNetSuiteStatus();
    loadStatistics();
    
    // Load initial tab data
    loadVendors();
    loadInvoices();
    
    // Set up auto-refresh (every 30 seconds)
    dashboardState.refreshInterval = setInterval(() => {
        console.log('Auto-refreshing dashboard...');
        checkNetSuiteStatus();
        loadStatistics();
        // Refresh current tab data
        if (dashboardState.activeTab === 'vendors') {
            loadVendors();
        } else {
            loadInvoices();
        }
    }, 30000);
    
    // Set up event listeners
    setupEventListeners();
    setupTabListeners();
    
    // Set up modal keyboard support
    setupModalKeyboardSupport();
});

// Set up keyboard support for the modal
function setupModalKeyboardSupport() {
    // Add ESC key to close modal
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
            const modal = document.getElementById('confirmation-modal');
            if (modal && modal.style.display !== 'none') {
                closeConfirmModal(false);
            }
        }
    });
    
    // Close modal when clicking outside
    const modal = document.getElementById('confirmation-modal');
    if (modal) {
        modal.addEventListener('click', (e) => {
            if (e.target.classList.contains('modal-overlay')) {
                closeConfirmModal(false);
            }
        });
    }
}

// Set up tab switching listeners
function setupTabListeners() {
    const tabButtons = document.querySelectorAll('.tab-btn');
    tabButtons.forEach(button => {
        button.addEventListener('click', (e) => {
            const tabName = e.target.getAttribute('data-tab');
            switchTab(tabName);
        });
    });
}

// Switch between tabs
function switchTab(tabName) {
    // Update active tab in state
    dashboardState.activeTab = tabName;
    
    // Update tab buttons
    document.querySelectorAll('.tab-btn').forEach(btn => {
        if (btn.getAttribute('data-tab') === tabName) {
            btn.classList.add('active');
        } else {
            btn.classList.remove('active');
        }
    });
    
    // Update tab content
    document.querySelectorAll('.tab-content').forEach(content => {
        content.classList.remove('active');
    });
    
    const activeContent = document.getElementById(`${tabName}-tab`);
    if (activeContent) {
        activeContent.classList.add('active');
    }
    
    // Load data for the active tab
    if (tabName === 'vendors') {
        loadVendors();
    } else if (tabName === 'invoices') {
        loadInvoices();
    }
}

// Load vendors data
async function loadVendors(page = 1) {
    try {
        const params = new URLSearchParams({
            page: page,
            limit: 20,
            search: dashboardState.vendors.search,
            filter: dashboardState.vendors.filter
        });
        
        const response = await fetch(`/api/netsuite/vendors/all?${params}`);
        const data = await response.json();
        
        if (data.success) {
            dashboardState.vendors.data = data.vendors;
            dashboardState.vendors.currentPage = data.pagination.page;
            dashboardState.vendors.totalPages = data.pagination.total_pages;
            dashboardState.vendors.totalCount = data.pagination.total;
            
            displayVendors();
            updateVendorsPagination();
        }
    } catch (error) {
        console.error('Error loading vendors:', error);
        showError('Failed to load vendors');
    }
}

// Display vendors in table
function displayVendors() {
    const tbody = document.getElementById('vendors-tbody');
    if (!tbody) return;
    
    const vendors = dashboardState.vendors.data;
    
    if (!vendors || vendors.length === 0) {
        tbody.innerHTML = `
            <tr>
                <td colspan="8" class="empty-state">
                    <div class="empty-state-icon">📁</div>
                    <div>No vendors found</div>
                </td>
            </tr>
        `;
        return;
    }
    
    tbody.innerHTML = '';
    
    vendors.forEach(vendor => {
        const row = document.createElement('tr');
        const isSelected = dashboardState.vendors.selectedIds.has(vendor.vendor_id);
        
        if (isSelected) {
            row.classList.add('selected');
        }
        
        row.innerHTML = `
            <td>
                <input type="checkbox" 
                       class="data-checkbox vendor-checkbox" 
                       data-vendor-id="${vendor.vendor_id}"
                       ${isSelected ? 'checked' : ''}
                       onchange="toggleVendorSelection('${vendor.vendor_id}')">
            </td>
            <td style="font-size: 12px;">${vendor.vendor_id}</td>
            <td style="font-weight: 500;">${vendor.name || '-'}</td>
            <td style="font-size: 13px;">${vendor.emails || '-'}</td>
            <td style="font-size: 13px;">${vendor.countries || '-'}</td>
            <td>${getSyncStatusBadge(vendor.sync_status)}</td>
            <td style="font-size: 12px;">${vendor.netsuite_internal_id || '-'}</td>
            <td class="actions-cell">
                <button class="btn-create" onclick="createInNetSuite('vendor', '${vendor.vendor_id}')">
                    Create New
                </button>
                <button class="btn-update" onclick="updateInNetSuite('vendor', '${vendor.vendor_id}')">
                    Update
                </button>
            </td>
        `;
        
        tbody.appendChild(row);
    });
    
    updateSelectionInfo('vendors');
}

// Load invoices data
async function loadInvoices(page = 1) {
    try {
        const params = new URLSearchParams({
            page: page,
            limit: 20,
            search: dashboardState.invoices.search,
            filter: dashboardState.invoices.filter
        });
        
        const response = await fetch(`/api/netsuite/invoices/all?${params}`);
        const data = await response.json();
        
        if (data.success) {
            dashboardState.invoices.data = data.invoices;
            dashboardState.invoices.currentPage = data.pagination.page;
            dashboardState.invoices.totalPages = data.pagination.total_pages;
            dashboardState.invoices.totalCount = data.pagination.total;
            
            displayInvoices();
            updateInvoicesPagination();
        }
    } catch (error) {
        console.error('Error loading invoices:', error);
        showError('Failed to load invoices');
    }
}

// Display invoices in table
function displayInvoices() {
    const tbody = document.getElementById('invoices-tbody');
    if (!tbody) return;
    
    const invoices = dashboardState.invoices.data;
    
    if (!invoices || invoices.length === 0) {
        tbody.innerHTML = `
            <tr>
                <td colspan="9" class="empty-state">
                    <div class="empty-state-icon">📄</div>
                    <div>No invoices found</div>
                </td>
            </tr>
        `;
        return;
    }
    
    tbody.innerHTML = '';
    
    invoices.forEach(invoice => {
        const row = document.createElement('tr');
        const isSelected = dashboardState.invoices.selectedIds.has(invoice.invoice_id);
        
        if (isSelected) {
            row.classList.add('selected');
        }
        
        const formattedAmount = formatCurrency(invoice.total_amount, invoice.currency);
        const formattedDate = formatDate(invoice.invoice_date);
        
        row.innerHTML = `
            <td>
                <input type="checkbox" 
                       class="data-checkbox invoice-checkbox" 
                       data-invoice-id="${invoice.invoice_id}"
                       ${isSelected ? 'checked' : ''}
                       onchange="toggleInvoiceSelection('${invoice.invoice_id}')">
            </td>
            <td style="font-size: 12px;">${invoice.invoice_id}</td>
            <td style="font-weight: 500;">${invoice.invoice_number || '-'}</td>
            <td>${invoice.vendor_name || '-'}</td>
            <td style="font-size: 13px;">${formattedDate}</td>
            <td style="font-weight: 600;">${formattedAmount}</td>
            <td>${getSyncStatusBadge(invoice.sync_status)}</td>
            <td style="font-size: 12px;">${invoice.netsuite_bill_id || '-'}</td>
            <td class="actions-cell">
                ${!invoice.netsuite_bill_id || invoice.netsuite_bill_id === 'null' || invoice.netsuite_bill_id === 'None' ? `
                    <button class="btn-create" onclick="createInNetSuite('invoice', '${invoice.invoice_id}')">
                        📋 Create Bill
                    </button>
                ` : `
                    <button class="btn-update" onclick="updateInNetSuite('invoice', '${invoice.invoice_id}')">
                        🔄 Update Bill
                    </button>
                `}
            </td>
        `;
        
        tbody.appendChild(row);
    });
    
    updateSelectionInfo('invoices');
}

// Get sync status badge HTML
function getSyncStatusBadge(status, action) {
    const statusMap = {
        'synced': { class: 'synced', icon: '🟢', text: 'Synced' },
        'created': { class: 'synced', icon: '🆕', text: 'Created' },
        'updated': { class: 'synced', icon: '🔄', text: 'Updated' },
        'not-synced': { class: 'not-synced', icon: '🔴', text: 'Not Synced' },
        'not_synced': { class: 'not-synced', icon: '🔴', text: 'Not Synced' },
        'not_found': { class: 'failed', icon: '❌', text: 'Not Found' },
        'duplicate': { class: 'failed', icon: '⚠️', text: 'Duplicate' },
        'failed': { class: 'failed', icon: '⚠️', text: 'Failed' },
        'syncing': { class: 'syncing', icon: '🟡', text: 'Syncing' }
    };
    
    // If action is provided, adjust status
    if (action === 'created' && status === 'synced') {
        status = 'created';
    } else if (action === 'updated' && status === 'synced') {
        status = 'updated';
    }
    
    const statusInfo = statusMap[status] || statusMap['not-synced'];
    
    return `
        <span class="sync-status ${statusInfo.class}">
            <span class="status-icon">${statusInfo.icon}</span>
            ${statusInfo.text}
        </span>
    `;
}

// Toggle vendor selection
function toggleVendorSelection(vendorId) {
    if (dashboardState.vendors.selectedIds.has(vendorId)) {
        dashboardState.vendors.selectedIds.delete(vendorId);
    } else {
        dashboardState.vendors.selectedIds.add(vendorId);
    }
    
    // Update row appearance
    const checkbox = document.querySelector(`.vendor-checkbox[data-vendor-id="${vendorId}"]`);
    if (checkbox) {
        const row = checkbox.closest('tr');
        if (dashboardState.vendors.selectedIds.has(vendorId)) {
            row.classList.add('selected');
        } else {
            row.classList.remove('selected');
        }
    }
    
    updateSelectionInfo('vendors');
}

// Toggle invoice selection
function toggleInvoiceSelection(invoiceId) {
    if (dashboardState.invoices.selectedIds.has(invoiceId)) {
        dashboardState.invoices.selectedIds.delete(invoiceId);
    } else {
        dashboardState.invoices.selectedIds.add(invoiceId);
    }
    
    // Update row appearance
    const checkbox = document.querySelector(`.invoice-checkbox[data-invoice-id="${invoiceId}"]`);
    if (checkbox) {
        const row = checkbox.closest('tr');
        if (dashboardState.invoices.selectedIds.has(invoiceId)) {
            row.classList.add('selected');
        } else {
            row.classList.remove('selected');
        }
    }
    
    updateSelectionInfo('invoices');
}

// Toggle all vendors
function toggleAllVendors(checkbox) {
    if (checkbox.checked) {
        // Select all vendors on current page
        dashboardState.vendors.data.forEach(vendor => {
            dashboardState.vendors.selectedIds.add(vendor.vendor_id);
        });
    } else {
        // Deselect all vendors on current page
        dashboardState.vendors.data.forEach(vendor => {
            dashboardState.vendors.selectedIds.delete(vendor.vendor_id);
        });
    }
    
    // Update all checkboxes
    document.querySelectorAll('.vendor-checkbox').forEach(cb => {
        cb.checked = checkbox.checked;
        const row = cb.closest('tr');
        if (checkbox.checked) {
            row.classList.add('selected');
        } else {
            row.classList.remove('selected');
        }
    });
    
    updateSelectionInfo('vendors');
}

// Toggle all invoices
function toggleAllInvoices(checkbox) {
    if (checkbox.checked) {
        // Select all invoices on current page
        dashboardState.invoices.data.forEach(invoice => {
            dashboardState.invoices.selectedIds.add(invoice.invoice_id);
        });
    } else {
        // Deselect all invoices on current page
        dashboardState.invoices.data.forEach(invoice => {
            dashboardState.invoices.selectedIds.delete(invoice.invoice_id);
        });
    }
    
    // Update all checkboxes
    document.querySelectorAll('.invoice-checkbox').forEach(cb => {
        cb.checked = checkbox.checked;
        const row = cb.closest('tr');
        if (checkbox.checked) {
            row.classList.add('selected');
        } else {
            row.classList.remove('selected');
        }
    });
    
    updateSelectionInfo('invoices');
}

// Update selection info
function updateSelectionInfo(type) {
    const count = type === 'vendors' ? 
        dashboardState.vendors.selectedIds.size :
        dashboardState.invoices.selectedIds.size;
    
    const infoElement = document.getElementById(`${type.slice(0, -1)}-selection-info`);
    const countElement = document.getElementById(`${type.slice(0, -1)}-selection-count`);
    
    if (infoElement && countElement) {
        if (count > 0) {
            infoElement.style.display = 'block';
            countElement.textContent = count;
        } else {
            infoElement.style.display = 'none';
        }
    }
}

// Filter vendors
function filterVendors() {
    const search = document.getElementById('vendor-search').value;
    const filter = document.getElementById('vendor-filter').value;
    
    dashboardState.vendors.search = search;
    dashboardState.vendors.filter = filter;
    dashboardState.vendors.currentPage = 1;
    
    loadVendors(1);
}

// Filter invoices
function filterInvoices() {
    const search = document.getElementById('invoice-search').value;
    const filter = document.getElementById('invoice-filter').value;
    
    dashboardState.invoices.search = search;
    dashboardState.invoices.filter = filter;
    dashboardState.invoices.currentPage = 1;
    
    loadInvoices(1);
}

// Sync selected vendors
async function syncSelectedVendors() {
    const selectedIds = Array.from(dashboardState.vendors.selectedIds);
    
    if (selectedIds.length === 0) {
        showError('Please select vendors to sync');
        return;
    }
    
    const button = event.target;
    button.disabled = true;
    button.textContent = `Syncing ${selectedIds.length} vendor(s)...`;
    
    try {
        const response = await fetch('/api/netsuite/sync/vendors/bulk', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ vendor_ids: selectedIds })
        });
        
        const data = await response.json();
        
        if (data.success) {
            const summary = data.summary;
            showSuccess(
                `Sync completed: ${summary.successful} successful, ${summary.failed} failed, ${summary.already_synced} already synced`
            );
            
            // Clear selection and reload
            dashboardState.vendors.selectedIds.clear();
            loadVendors(dashboardState.vendors.currentPage);
            loadStatistics();
        } else {
            showError(`Sync failed: ${data.error}`);
        }
    } catch (error) {
        showError(`Error during sync: ${error.message}`);
    } finally {
        button.disabled = false;
        button.textContent = '🔄 Sync Selected to NetSuite';
    }
}

// Sync selected invoices
async function syncSelectedInvoices() {
    const selectedIds = Array.from(dashboardState.invoices.selectedIds);
    
    if (selectedIds.length === 0) {
        showError('Please select invoices to sync');
        return;
    }
    
    const button = event.target;
    button.disabled = true;
    button.textContent = `Syncing ${selectedIds.length} invoice(s)...`;
    
    try {
        const response = await fetch('/api/netsuite/sync/invoices/bulk', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ invoice_ids: selectedIds })
        });
        
        const data = await response.json();
        
        if (data.success) {
            const summary = data.summary;
            showSuccess(
                `Sync completed: ${summary.successful} successful, ${summary.failed} failed, ${summary.already_synced} already synced`
            );
            
            // Clear selection and reload
            dashboardState.invoices.selectedIds.clear();
            loadInvoices(dashboardState.invoices.currentPage);
            loadStatistics();
        } else {
            showError(`Sync failed: ${data.error}`);
        }
    } catch (error) {
        showError(`Error during sync: ${error.message}`);
    } finally {
        button.disabled = false;
        button.textContent = '🔄 Sync Selected to NetSuite';
    }
}

// Sync single vendor
async function syncSingleVendor(vendorId) {
    const button = event.target;
    button.disabled = true;
    button.textContent = 'Syncing...';
    
    try {
        const response = await fetch(`/api/netsuite/sync/vendor/${vendorId}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });
        
        const data = await response.json();
        
        if (data.success) {
            showSuccess(`Vendor synced successfully! NetSuite ID: ${data.netsuite_id}`);
            loadVendors(dashboardState.vendors.currentPage);
            loadStatistics();
        } else {
            showError(`Failed to sync vendor: ${data.error}`);
        }
    } catch (error) {
        showError(`Error syncing vendor: ${error.message}`);
    } finally {
        button.disabled = false;
        button.textContent = 'Sync';
    }
}

// Sync single invoice
async function syncSingleInvoice(invoiceId) {
    const button = event.target;
    button.disabled = true;
    button.textContent = 'Syncing...';
    
    try {
        const response = await fetch(`/api/netsuite/sync/invoice/${invoiceId}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });
        
        const data = await response.json();
        
        if (data.success) {
            showSuccess(`Invoice synced successfully! NetSuite Bill ID: ${data.netsuite_bill_id}`);
            loadInvoices(dashboardState.invoices.currentPage);
            loadStatistics();
        } else {
            showError(`Failed to sync invoice: ${data.error}`);
        }
    } catch (error) {
        showError(`Error syncing invoice: ${error.message}`);
    } finally {
        button.disabled = false;
        button.textContent = 'Sync';
    }
}

// Update vendors pagination
function updateVendorsPagination() {
    const container = document.getElementById('vendors-pagination');
    if (!container) return;
    
    container.innerHTML = '';
    
    const state = dashboardState.vendors;
    
    // Previous button
    const prevBtn = document.createElement('button');
    prevBtn.className = 'pagination-btn';
    prevBtn.textContent = '← Previous';
    prevBtn.disabled = state.currentPage === 1;
    prevBtn.onclick = () => loadVendors(state.currentPage - 1);
    container.appendChild(prevBtn);
    
    // Page info
    const pageInfo = document.createElement('span');
    pageInfo.className = 'page-info';
    pageInfo.textContent = `Page ${state.currentPage} of ${state.totalPages} (${state.totalCount} vendors)`;
    container.appendChild(pageInfo);
    
    // Next button
    const nextBtn = document.createElement('button');
    nextBtn.className = 'pagination-btn';
    nextBtn.textContent = 'Next →';
    nextBtn.disabled = state.currentPage === state.totalPages;
    nextBtn.onclick = () => loadVendors(state.currentPage + 1);
    container.appendChild(nextBtn);
}

// Update invoices pagination
function updateInvoicesPagination() {
    const container = document.getElementById('invoices-pagination');
    if (!container) return;
    
    container.innerHTML = '';
    
    const state = dashboardState.invoices;
    
    // Previous button
    const prevBtn = document.createElement('button');
    prevBtn.className = 'pagination-btn';
    prevBtn.textContent = '← Previous';
    prevBtn.disabled = state.currentPage === 1;
    prevBtn.onclick = () => loadInvoices(state.currentPage - 1);
    container.appendChild(prevBtn);
    
    // Page info
    const pageInfo = document.createElement('span');
    pageInfo.className = 'page-info';
    pageInfo.textContent = `Page ${state.currentPage} of ${state.totalPages} (${state.totalCount} invoices)`;
    container.appendChild(pageInfo);
    
    // Next button
    const nextBtn = document.createElement('button');
    nextBtn.className = 'pagination-btn';
    nextBtn.textContent = 'Next →';
    nextBtn.disabled = state.currentPage === state.totalPages;
    nextBtn.onclick = () => loadInvoices(state.currentPage + 1);
    container.appendChild(nextBtn);
}

// Load recent activity
async function loadRecentActivity() {
    try {
        const response = await fetch('/api/netsuite/activities?limit=10');
        const data = await response.json();
        
        if (data.success) {
            displayRecentActivity(data.activities || []);
        }
    } catch (error) {
        console.error('Error loading recent activity:', error);
    }
}

// Display recent activity
function displayRecentActivity(activities) {
    const container = document.getElementById('activityLog');
    if (!container) return;
    
    if (!activities || activities.length === 0) {
        container.innerHTML = `
            <div class="empty-state">
                <div class="empty-state-icon">📊</div>
                <div>No recent activity</div>
            </div>
        `;
        return;
    }
    
    container.innerHTML = '';
    
    activities.forEach(activity => {
        const item = document.createElement('div');
        item.style.padding = '8px';
        item.style.borderBottom = '1px solid #e0e0e0';
        
        const statusColor = activity.status === 'success' ? '#28a745' : 
                          activity.status === 'failed' ? '#dc3545' : '#ffc107';
        
        item.innerHTML = `
            <div style="display: flex; justify-content: space-between; align-items: center;">
                <div>
                    <strong style="color: ${statusColor};">
                        ${activity.entity_type} ${activity.status}
                    </strong>
                    <div style="font-size: 12px; color: #666;">
                        ${formatTimestamp(activity.timestamp)}
                    </div>
                </div>
                <div style="font-size: 12px;">
                    ${activity.netsuite_id || activity.entity_id || ''}
                </div>
            </div>
        `;
        
        container.appendChild(item);
    });
}

// Format currency
function formatCurrency(amount, currency = 'USD') {
    return new Intl.NumberFormat('en-US', {
        style: 'currency',
        currency: currency
    }).format(amount || 0);
}

// Format date
function formatDate(dateString) {
    if (!dateString) return '-';
    const date = new Date(dateString);
    return date.toLocaleDateString('en-US', {
        year: 'numeric',
        month: 'short',
        day: 'numeric'
    });
}

// Show success message
function showSuccess(message) {
    showToast(message, 'success');
}

// Show error message
function showError(message) {
    showToast(message, 'error', 8000);
}

// Show notification - wrapper for showToast
function showNotification(message, type) {
    // Map the type to our toast types
    const toastType = type === 'error' ? 'error' :
                     type === 'success' ? 'success' :
                     type === 'warning' ? 'warning' : 'info';
    
    // Call the showToast function
    const duration = type === 'error' ? 8000 : 5000;
    showToast(message, toastType, duration);
}

// Add CSS animations
const style = document.createElement('style');
style.textContent = `
    @keyframes slideIn {
        from {
            transform: translateX(100%);
            opacity: 0;
        }
        to {
            transform: translateX(0);
            opacity: 1;
        }
    }
    
    @keyframes slideOut {
        from {
            transform: translateX(0);
            opacity: 1;
        }
        to {
            transform: translateX(100%);
            opacity: 0;
        }
    }
`;
document.head.appendChild(style);

// Original functions (kept for compatibility)

// Set up all event listeners
function setupEventListeners() {
    // Test Connection button
    const testBtn = document.getElementById('testConnectionBtn');
    if (testBtn) {
        testBtn.addEventListener('click', testConnection);
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
        const url = data.base_url;
        baseUrl.textContent = url.length > 40 ? url.substring(0, 40) + '...' : url;
        baseUrl.title = url;
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
        showSuccess('Connection test completed');
    } catch (error) {
        showError('Connection test failed: ' + error.message);
    } finally {
        if (button) {
            button.disabled = false;
            button.textContent = 'Test Connection';
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
            loadRecentActivity();
            break;
        default:
            console.log('Action not implemented:', action);
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

// Individual Create action with confirmation
async function createInNetSuite(type, id) {
    const typeCapitalized = type.charAt(0).toUpperCase() + type.slice(1);
    
    // Use custom modal instead of browser confirm
    const confirmed = await showConfirmModal(
        `Create New ${typeCapitalized}`,
        `Are you sure you want to create a NEW ${type} in NetSuite? This will create a new record even if one already exists.`,
        'Create New'
    );
    
    if (!confirmed) {
        return;
    }
    
    try {
        showNotification(`Creating new ${type} in NetSuite...`, 'info');
        
        const response = await fetch(`/api/netsuite/${type}/${id}/create`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            }
        });
        
        const data = await response.json();
        
        if (data.success) {
            showSuccess(`🆕 ${typeCapitalized} created successfully in NetSuite!`);
            // Reload the data to show updated status
            if (type === 'vendor') {
                loadVendors();
            } else if (type === 'invoice') {
                loadInvoices();
            }
        } else {
            showError(`Failed to create ${type}: ${data.error || 'Unknown error'}`);
        }
    } catch (error) {
        console.error(`Error creating ${type}:`, error);
        showError(`Error creating ${type}: ${error.message}`);
    }
}

// Individual Update action with confirmation
async function updateInNetSuite(type, id) {
    const typeCapitalized = type.charAt(0).toUpperCase() + type.slice(1);
    
    // Use custom modal instead of browser confirm
    const confirmed = await showConfirmModal(
        `Update ${typeCapitalized}`,
        `Are you sure you want to update the existing ${type} in NetSuite? This will search for an existing record and update it.`,
        'Update'
    );
    
    if (!confirmed) {
        return;
    }
    
    try {
        showNotification(`Updating ${type} in NetSuite...`, 'info');
        
        // Use update-bill endpoint for invoices, update for vendors
        const endpoint = type === 'invoice' 
            ? `/api/netsuite/${type}/${id}/update-bill`
            : `/api/netsuite/${type}/${id}/update`;
        
        const response = await fetch(endpoint, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            }
        });
        
        const data = await response.json();
        
        if (data.success) {
            showSuccess(`🔄 ${typeCapitalized} updated successfully in NetSuite!`);
            // Reload the data to show updated status
            if (type === 'vendor') {
                loadVendors();
            } else if (type === 'invoice') {
                loadInvoices();
            }
        } else {
            if (data.error && data.error.includes('not found')) {
                showError(`❌ ${typeCapitalized} not found in NetSuite for update`);
            } else {
                showError(`Failed to update ${type}: ${data.error || 'Unknown error'}`);
            }
        }
    } catch (error) {
        console.error(`Error updating ${type}:`, error);
        showError(`Error updating ${type}: ${error.message}`);
    }
}

// Bulk sync with action selection
async function bulkSyncSelected(type) {
    const actionSelect = type === 'vendors' ? 
        document.getElementById('vendor-bulk-action-type') : 
        document.getElementById('invoice-bulk-action-type');
    
    if (!actionSelect) {
        showError('Action type selector not found');
        return;
    }
    
    const action = actionSelect.value;
    const selectedIds = Array.from(dashboardState[type].selectedIds);
    
    if (selectedIds.length === 0) {
        showWarning(`Please select at least one ${type.slice(0, -1)} to ${action}`);
        return;
    }
    
    const actionText = action === 'create' ? 'CREATE NEW' : 'UPDATE EXISTING';
    const confirmMessage = `Are you sure you want to ${actionText} ${selectedIds.length} ${type} in NetSuite?`;
    
    // Use custom modal instead of browser confirm
    const modalTitle = `Bulk ${action === 'create' ? 'Create' : 'Update'} ${type.charAt(0).toUpperCase() + type.slice(1)}`;
    const confirmed = await showConfirmModal(
        modalTitle,
        confirmMessage,
        action === 'create' ? 'Create All' : 'Update All'
    );
    
    if (!confirmed) {
        return;
    }
    
    try {
        // Show initial progress notification
        showToast(`Processing ${selectedIds.length} ${type}...`, 'info');
        
        // Simulate progress tracking (will be updated with real progress in future)
        let completed = 0;
        
        const response = await fetch(`/api/netsuite/${type}/bulk/${action}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                [`${type.slice(0, -1)}_ids`]: selectedIds
            })
        });
        
        const data = await response.json();
        
        if (data.success) {
            const summary = data.summary;
            if (summary.successful > 0 && summary.failed > 0) {
                showWarning(`Bulk ${action} completed: ${summary.successful} successful, ${summary.failed} failed`);
            } else if (summary.successful > 0) {
                showSuccess(`✅ Successfully ${action}d ${summary.successful} ${type} in NetSuite!`);
            } else {
                showError(`All ${type} failed to ${action}`);
            }
            
            // Clear selections and reload data
            dashboardState[type].selectedIds.clear();
            if (type === 'vendors') {
                loadVendors();
            } else {
                loadInvoices();
            }
        } else {
            showError(`Bulk ${action} failed: ${data.error || 'Unknown error'}`);
        }
    } catch (error) {
        console.error(`Error in bulk ${action}:`, error);
        showError(`Error in bulk ${action}: ${error.message}`);
    }
}

// Helper function to show warning messages
function showWarning(message) {
    showToast(message, 'warning');
}

// Cleanup on page unload
window.addEventListener('beforeunload', () => {
    if (dashboardState.refreshInterval) {
        clearInterval(dashboardState.refreshInterval);
    }
});