(function() {
    'use strict';

    const WIDGET_ID = 'payouts-agent-widget';
    const API_ENDPOINT = '/api/agent/chat';

    const TOOL_ICONS = {
        'search_gmail_invoices': '📧',
        'search_netsuite_vendor': '🔍',
        'create_netsuite_vendor': '👤',
        'create_netsuite_bill': '📄',
        'get_bill_status': '📋',
        'match_vendor_to_database': '⚖️',
        'run_bigquery': '🗄️',
        'get_subscription_summary': '📊',
        'search_database_first': '🔍',
        'check_gmail_status': '📧',
        'get_top_vendors_by_spend': '💰',
        'process_uploaded_invoice': '📄',
        'import_vendor_csv': '📋',
        'pull_netsuite_vendors': '🔄',
        'get_vendor_full_profile': '🔮',
        'deep_search': '🏊',
        'get_invoice_pdf_link': '📎',
        'check_netsuite_health': '🔍',
        'show_vendors_table': '📊',
        'show_invoices_table': '🧾'
    };

    const TOOL_LABELS = {
        'search_gmail_invoices': 'Searched Gmail',
        'search_netsuite_vendor': 'Checked NetSuite',
        'create_netsuite_vendor': 'Created Vendor',
        'create_netsuite_bill': 'Created Bill',
        'get_bill_status': 'Checked Status',
        'match_vendor_to_database': 'Matched Vendor',
        'run_bigquery': 'Queried Database',
        'get_subscription_summary': 'Got Subscriptions',
        'search_database_first': 'Searched Database',
        'check_gmail_status': 'Checked Gmail',
        'get_top_vendors_by_spend': 'Top Vendors by Spend',
        'process_uploaded_invoice': 'Processed Invoice',
        'import_vendor_csv': 'Imported CSV',
        'pull_netsuite_vendors': 'Synced NetSuite',
        'get_vendor_full_profile': 'Full Vendor Profile',
        'deep_search': 'Deep AI Search',
        'get_invoice_pdf_link': 'Got PDF Link',
        'check_netsuite_health': 'NetSuite Health',
        'show_vendors_table': 'Vendor Table',
        'show_invoices_table': 'Invoice Table'
    };

    function getSessionId() {
        let sessionId = localStorage.getItem('payouts_session_id');
        if (!sessionId) {
            sessionId = 'sess_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);
            localStorage.setItem('payouts_session_id', sessionId);
        }
        return sessionId;
    }

    function clearSession() {
        localStorage.removeItem('payouts_session_id');
        messages = [];
    }

    let isOpen = false;
    let isLoading = false;
    let messages = [];
    let widgetContainer = null;
    let chatWindow = null;
    let floatingButton = null;
    let selectedFile = null;

    function injectStyles() {
        if (document.getElementById('payouts-agent-widget-styles')) return;

        const styles = document.createElement('style');
        styles.id = 'payouts-agent-widget-styles';
        styles.textContent = `
            #payouts-agent-widget {
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
                position: fixed;
                bottom: 24px;
                right: 24px;
                z-index: 99999;
            }

            #payouts-chat-button {
                width: 60px;
                height: 60px;
                border-radius: 50%;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                border: none;
                cursor: pointer;
                box-shadow: 0 4px 20px rgba(102, 126, 234, 0.4);
                display: flex;
                align-items: center;
                justify-content: center;
                transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
                position: relative;
            }

            #payouts-chat-button:hover {
                transform: scale(1.1);
                box-shadow: 0 6px 28px rgba(102, 126, 234, 0.5);
            }

            #payouts-chat-button svg {
                width: 28px;
                height: 28px;
                fill: white;
                transition: transform 0.3s ease;
            }

            #payouts-chat-button.open svg {
                transform: rotate(90deg);
            }

            #payouts-chat-window {
                position: absolute;
                bottom: 80px;
                right: 0;
                width: 400px;
                max-width: calc(100vw - 48px);
                height: 550px;
                max-height: calc(100vh - 120px);
                background: #ffffff;
                border-radius: 16px;
                box-shadow: 0 10px 40px rgba(0, 0, 0, 0.15), 0 0 0 1px rgba(0, 0, 0, 0.05);
                display: flex;
                flex-direction: column;
                overflow: hidden;
                opacity: 0;
                transform: translateY(20px) scale(0.95);
                pointer-events: none;
                transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
            }

            #payouts-chat-window.open {
                opacity: 1;
                transform: translateY(0) scale(1);
                pointer-events: auto;
            }

            .payouts-chat-header {
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                padding: 18px 20px;
                display: flex;
                align-items: center;
                justify-content: space-between;
            }

            .payouts-chat-header-info {
                display: flex;
                align-items: center;
                gap: 12px;
            }

            .payouts-chat-avatar {
                width: 42px;
                height: 42px;
                background: rgba(255, 255, 255, 0.2);
                border-radius: 50%;
                display: flex;
                align-items: center;
                justify-content: center;
                font-size: 20px;
            }

            .payouts-chat-title {
                font-size: 16px;
                font-weight: 600;
                margin: 0;
            }

            .payouts-chat-subtitle {
                font-size: 12px;
                opacity: 0.85;
                margin: 0;
            }

            .payouts-status-indicator {
                display: flex;
                align-items: center;
                gap: 8px;
                padding: 4px 12px;
                background: rgba(255, 255, 255, 0.15);
                border-radius: 20px;
                font-size: 11px;
                margin-left: auto;
                margin-right: 12px;
            }

            .payouts-status-dot {
                width: 8px;
                height: 8px;
                border-radius: 50%;
                animation: payouts-pulse 2s ease-in-out infinite;
            }

            .payouts-status-dot.online {
                background: #10b981;
                box-shadow: 0 0 8px rgba(16, 185, 129, 0.6);
            }

            .payouts-status-dot.offline {
                background: #ef4444;
                box-shadow: 0 0 8px rgba(239, 68, 68, 0.6);
            }

            .payouts-status-dot.checking {
                background: #f59e0b;
                animation: payouts-blink 0.8s ease-in-out infinite;
            }

            @keyframes payouts-pulse {
                0%, 100% { opacity: 1; }
                50% { opacity: 0.6; }
            }

            @keyframes payouts-blink {
                0%, 100% { opacity: 1; }
                50% { opacity: 0.3; }
            }

            .payouts-status-services {
                display: flex;
                gap: 6px;
            }

            .payouts-service-badge {
                display: inline-flex;
                align-items: center;
                gap: 3px;
                font-size: 10px;
                opacity: 0.9;
            }

            .payouts-service-badge.connected {
                color: #a7f3d0;
            }

            .payouts-service-badge.disconnected {
                color: #fecaca;
            }

            .payouts-chat-close {
                background: rgba(255, 255, 255, 0.2);
                border: none;
                color: white;
                width: 32px;
                height: 32px;
                border-radius: 50%;
                cursor: pointer;
                display: flex;
                align-items: center;
                justify-content: center;
                transition: background 0.2s;
            }

            .payouts-chat-close:hover {
                background: rgba(255, 255, 255, 0.3);
            }

            .payouts-chat-messages {
                flex: 1;
                overflow-y: auto;
                padding: 20px;
                display: flex;
                flex-direction: column;
                gap: 16px;
                background: #f8f9ff;
            }

            .payouts-message {
                display: flex;
                flex-direction: column;
                max-width: 85%;
                animation: payouts-message-in 0.3s ease;
            }

            @keyframes payouts-message-in {
                from {
                    opacity: 0;
                    transform: translateY(10px);
                }
                to {
                    opacity: 1;
                    transform: translateY(0);
                }
            }

            .payouts-message.user {
                align-self: flex-end;
            }

            .payouts-message.assistant {
                align-self: flex-start;
            }

            .payouts-message-bubble {
                padding: 12px 16px;
                border-radius: 16px;
                font-size: 14px;
                line-height: 1.5;
                word-wrap: break-word;
            }

            .payouts-message.user .payouts-message-bubble {
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                border-bottom-right-radius: 4px;
            }

            .payouts-message.assistant .payouts-message-bubble {
                background: white;
                color: #1f2937;
                border-bottom-left-radius: 4px;
                box-shadow: 0 1px 3px rgba(0, 0, 0, 0.08);
            }

            .payouts-tool-badges {
                display: flex;
                flex-wrap: wrap;
                gap: 6px;
                margin-bottom: 8px;
            }

            .payouts-tool-badge {
                display: inline-flex;
                align-items: center;
                gap: 4px;
                padding: 4px 10px;
                background: linear-gradient(135deg, rgba(102, 126, 234, 0.1) 0%, rgba(118, 75, 162, 0.1) 100%);
                border: 1px solid rgba(102, 126, 234, 0.2);
                border-radius: 12px;
                font-size: 11px;
                font-weight: 500;
                color: #667eea;
                animation: payouts-badge-in 0.3s ease;
            }

            @keyframes payouts-badge-in {
                from {
                    opacity: 0;
                    transform: scale(0.8);
                }
                to {
                    opacity: 1;
                    transform: scale(1);
                }
            }

            .payouts-tool-badge.loading {
                background: linear-gradient(135deg, rgba(251, 191, 36, 0.15) 0%, rgba(245, 158, 11, 0.15) 100%);
                border-color: rgba(251, 191, 36, 0.3);
                color: #b45309;
            }

            .payouts-tool-badge .badge-icon {
                font-size: 12px;
            }

            .payouts-loading-indicator {
                display: flex;
                align-items: center;
                gap: 8px;
                padding: 12px 16px;
                background: white;
                border-radius: 16px;
                border-bottom-left-radius: 4px;
                box-shadow: 0 1px 3px rgba(0, 0, 0, 0.08);
                align-self: flex-start;
                max-width: 85%;
            }

            .payouts-loading-dots {
                display: flex;
                gap: 4px;
            }

            .payouts-loading-dot {
                width: 8px;
                height: 8px;
                background: #667eea;
                border-radius: 50%;
                animation: payouts-dot-bounce 1.4s ease-in-out infinite both;
            }

            .payouts-loading-dot:nth-child(1) { animation-delay: -0.32s; }
            .payouts-loading-dot:nth-child(2) { animation-delay: -0.16s; }

            @keyframes payouts-dot-bounce {
                0%, 80%, 100% {
                    transform: scale(0.6);
                    opacity: 0.6;
                }
                40% {
                    transform: scale(1);
                    opacity: 1;
                }
            }

            .payouts-chat-input-area {
                padding: 16px;
                background: white;
                border-top: 1px solid #e5e7eb;
                display: flex;
                flex-direction: column;
                gap: 8px;
            }

            .payouts-file-indicator {
                display: none;
                align-items: center;
                gap: 8px;
                padding: 8px 12px;
                background: linear-gradient(135deg, rgba(102, 126, 234, 0.1) 0%, rgba(118, 75, 162, 0.1) 100%);
                border: 1px solid rgba(102, 126, 234, 0.2);
                border-radius: 8px;
                font-size: 12px;
                color: #667eea;
            }

            .payouts-file-indicator.active {
                display: flex;
            }

            .payouts-file-indicator .file-icon {
                font-size: 16px;
            }

            .payouts-file-indicator .file-name {
                flex: 1;
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
                font-weight: 500;
            }

            .payouts-file-indicator .file-remove {
                background: none;
                border: none;
                color: #667eea;
                cursor: pointer;
                padding: 2px;
                display: flex;
                align-items: center;
                justify-content: center;
                border-radius: 50%;
                transition: background 0.2s;
            }

            .payouts-file-indicator .file-remove:hover {
                background: rgba(102, 126, 234, 0.2);
            }

            .payouts-input-row {
                display: flex;
                gap: 10px;
                align-items: flex-end;
            }

            .payouts-chat-input {
                flex: 1;
                padding: 12px 16px;
                border: 2px solid #e5e7eb;
                border-radius: 24px;
                font-size: 14px;
                resize: none;
                outline: none;
                font-family: inherit;
                line-height: 1.4;
                max-height: 120px;
                transition: border-color 0.2s;
            }

            .payouts-chat-input:focus {
                border-color: #667eea;
            }

            .payouts-chat-input::placeholder {
                color: #9ca3af;
            }

            .payouts-file-input {
                display: none;
            }

            .payouts-upload-btn {
                width: 44px;
                height: 44px;
                border-radius: 50%;
                background: #f3f4f6;
                border: 2px solid #e5e7eb;
                cursor: pointer;
                display: flex;
                align-items: center;
                justify-content: center;
                transition: all 0.2s;
                flex-shrink: 0;
            }

            .payouts-upload-btn:hover {
                background: #e5e7eb;
                border-color: #667eea;
            }

            .payouts-upload-btn.has-file {
                background: linear-gradient(135deg, rgba(102, 126, 234, 0.15) 0%, rgba(118, 75, 162, 0.15) 100%);
                border-color: #667eea;
            }

            .payouts-upload-btn svg {
                width: 20px;
                height: 20px;
                stroke: #6b7280;
                transition: stroke 0.2s;
            }

            .payouts-upload-btn:hover svg,
            .payouts-upload-btn.has-file svg {
                stroke: #667eea;
            }

            .payouts-chat-send {
                width: 44px;
                height: 44px;
                border-radius: 50%;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                border: none;
                cursor: pointer;
                display: flex;
                align-items: center;
                justify-content: center;
                transition: all 0.2s;
                flex-shrink: 0;
            }

            .payouts-chat-send:hover:not(:disabled) {
                transform: scale(1.05);
                box-shadow: 0 4px 12px rgba(102, 126, 234, 0.4);
            }

            .payouts-chat-send:disabled {
                opacity: 0.5;
                cursor: not-allowed;
            }

            .payouts-chat-send svg {
                width: 20px;
                height: 20px;
                fill: white;
            }

            .payouts-welcome-message {
                text-align: center;
                padding: 20px;
                color: #6b7280;
            }

            .payouts-welcome-message h3 {
                color: #1f2937;
                margin: 0 0 8px 0;
                font-size: 16px;
            }

            .payouts-welcome-message p {
                margin: 0;
                font-size: 13px;
                line-height: 1.5;
            }

            .payouts-quick-actions {
                display: flex;
                flex-wrap: wrap;
                gap: 8px;
                margin-top: 16px;
                justify-content: center;
            }

            .payouts-quick-action {
                padding: 8px 14px;
                background: white;
                border: 1px solid #e5e7eb;
                border-radius: 20px;
                font-size: 12px;
                color: #4b5563;
                cursor: pointer;
                transition: all 0.2s;
            }

            .payouts-quick-action:hover {
                background: #f3f4f6;
                border-color: #667eea;
                color: #667eea;
            }

            /* Action buttons in chat messages (e.g., Connect Gmail) */
            .chat-action-btn {
                display: inline-block;
                padding: 10px 20px;
                margin: 8px 0;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white !important;
                text-decoration: none;
                border-radius: 20px;
                font-size: 13px;
                font-weight: 600;
                transition: all 0.2s ease;
                box-shadow: 0 2px 8px rgba(102, 126, 234, 0.3);
            }

            .chat-action-btn:hover {
                transform: translateY(-2px);
                box-shadow: 0 4px 12px rgba(102, 126, 234, 0.4);
            }

            .chat-action-btn:active {
                transform: translateY(0);
            }

            /* Data table styles for rich rendering */
            .payouts-table-wrapper {
                overflow-x: auto;
                margin: 8px 0;
                border-radius: 8px;
                border: 1px solid #e5e7eb;
            }

            .payouts-data-table {
                width: 100%;
                border-collapse: collapse;
                font-size: 12px;
                min-width: 200px;
            }

            .payouts-data-table th {
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                padding: 10px 12px;
                text-align: left;
                font-weight: 600;
                white-space: nowrap;
            }

            .payouts-data-table td {
                padding: 8px 12px;
                border-bottom: 1px solid #e5e7eb;
                text-align: left;
            }

            .payouts-data-table tr:nth-child(even) {
                background: #f8f9ff;
            }

            .payouts-data-table tr:nth-child(odd) {
                background: white;
            }

            .payouts-data-table tr:hover td {
                background: rgba(102, 126, 234, 0.08);
            }

            .payouts-data-table tr:last-child td {
                border-bottom: none;
            }

            /* Invoice Card Styles - Rich visual cards for extracted invoices */
            .invoice-card {
                background: white;
                border: 1px solid #e5e7eb;
                border-radius: 12px;
                padding: 16px;
                margin: 12px 0;
                box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
                transition: all 0.2s ease;
            }

            .invoice-card:hover {
                border-color: #667eea;
                box-shadow: 0 4px 16px rgba(102, 126, 234, 0.15);
            }

            .invoice-header {
                display: flex;
                justify-content: space-between;
                align-items: flex-start;
                margin-bottom: 12px;
            }

            .vendor-name {
                font-size: 16px;
                font-weight: 600;
                color: #1f2937;
            }

            .amount {
                font-size: 18px;
                font-weight: 700;
                color: #059669;
            }

            .invoice-details {
                display: flex;
                flex-wrap: wrap;
                gap: 12px;
                margin-bottom: 12px;
                font-size: 13px;
                color: #6b7280;
            }

            .invoice-status {
                display: flex;
                flex-wrap: wrap;
                gap: 8px;
                margin-bottom: 12px;
                font-size: 12px;
            }

            .invoice-status .matched {
                background: #d1fae5;
                color: #059669;
                padding: 4px 10px;
                border-radius: 12px;
            }

            .invoice-status .new-vendor {
                background: #fef3c7;
                color: #d97706;
                padding: 4px 10px;
                border-radius: 12px;
            }

            .invoice-status .synced {
                background: #dbeafe;
                color: #2563eb;
                padding: 4px 10px;
                border-radius: 12px;
            }

            .invoice-status .not-synced {
                background: #f3f4f6;
                color: #6b7280;
                padding: 4px 10px;
                border-radius: 12px;
            }

            .invoice-actions {
                display: flex;
                flex-wrap: wrap;
                gap: 8px;
                margin-top: 12px;
                padding-top: 12px;
                border-top: 1px solid #e5e7eb;
            }

            .invoice-actions button,
            .invoice-actions a {
                padding: 8px 14px;
                border-radius: 8px;
                font-size: 12px;
                font-weight: 500;
                cursor: pointer;
                text-decoration: none;
                display: inline-flex;
                align-items: center;
                gap: 4px;
                transition: all 0.2s ease;
                border: none;
            }

            .approve-btn {
                background: #d1fae5;
                color: #059669;
            }

            .approve-btn:hover {
                background: #a7f3d0;
            }

            .reject-btn {
                background: #fee2e2;
                color: #dc2626;
            }

            .reject-btn:hover {
                background: #fecaca;
            }

            .create-bill-btn {
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
            }

            .create-bill-btn:hover {
                transform: translateY(-1px);
                box-shadow: 0 4px 12px rgba(102, 126, 234, 0.3);
            }

            .view-pdf-btn {
                background: #f3f4f6;
                color: #4b5563;
            }

            .view-pdf-btn:hover {
                background: #e5e7eb;
            }

            /* Progress indicator for scanning operations */
            .scan-progress {
                background: linear-gradient(135deg, rgba(102, 126, 234, 0.1) 0%, rgba(118, 75, 162, 0.1) 100%);
                border: 1px solid rgba(102, 126, 234, 0.2);
                border-radius: 12px;
                padding: 16px;
                margin: 12px 0;
            }

            .scan-progress-header {
                display: flex;
                align-items: center;
                gap: 8px;
                margin-bottom: 12px;
                font-weight: 600;
                color: #667eea;
            }

            .scan-progress-bar {
                height: 8px;
                background: #e5e7eb;
                border-radius: 4px;
                overflow: hidden;
                margin-bottom: 8px;
            }

            .scan-progress-fill {
                height: 100%;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                border-radius: 4px;
                transition: width 0.3s ease;
            }

            .scan-progress-text {
                font-size: 12px;
                color: #6b7280;
            }

            /* Vendor card styles */
            .vendor-card {
                background: white;
                border: 1px solid #e5e7eb;
                border-radius: 12px;
                padding: 14px;
                margin: 8px 0;
                display: flex;
                align-items: center;
                gap: 12px;
            }

            .vendor-card:hover {
                border-color: #667eea;
            }

            .vendor-avatar {
                width: 40px;
                height: 40px;
                border-radius: 8px;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                display: flex;
                align-items: center;
                justify-content: center;
                color: white;
                font-weight: 600;
                font-size: 14px;
            }

            .vendor-info {
                flex: 1;
            }

            .vendor-info .name {
                font-weight: 600;
                color: #1f2937;
                font-size: 14px;
            }

            .vendor-info .details {
                font-size: 12px;
                color: #6b7280;
            }

            /* Comprehensive Vendor Profile Card */
            .payouts-vendor-card {
                background: white;
                border: 1px solid #e5e7eb;
                border-radius: 12px;
                padding: 16px;
                margin: 12px 0;
                box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
            }

            .payouts-vendor-card .vendor-header {
                display: flex;
                align-items: center;
                gap: 12px;
                margin-bottom: 16px;
                padding-bottom: 12px;
                border-bottom: 1px solid #f3f4f6;
            }

            .payouts-vendor-card .vendor-header h2,
            .payouts-vendor-card .vendor-header h3 {
                margin: 0;
                font-size: 18px;
                font-weight: 600;
                color: #1f2937;
            }

            .payouts-vendor-card .vendor-details {
                display: grid;
                grid-template-columns: repeat(2, 1fr);
                gap: 10px;
                margin-bottom: 14px;
            }

            .payouts-vendor-card .vendor-details > div {
                font-size: 13px;
                color: #4b5563;
            }

            .payouts-vendor-card .vendor-details strong {
                color: #6b7280;
                font-weight: 500;
            }

            .payouts-vendor-card .vendor-financials {
                background: linear-gradient(135deg, rgba(102, 126, 234, 0.08) 0%, rgba(118, 75, 162, 0.08) 100%);
                border-radius: 8px;
                padding: 12px;
                display: flex;
                gap: 16px;
                flex-wrap: wrap;
            }

            .payouts-vendor-card .vendor-financials > div {
                font-size: 13px;
                color: #4b5563;
            }

            .payouts-vendor-card .vendor-financials strong {
                color: #1f2937;
            }

            .payouts-vendor-card .sync-status {
                display: inline-flex;
                align-items: center;
                gap: 6px;
                padding: 4px 12px;
                border-radius: 20px;
                font-size: 12px;
                font-weight: 500;
            }

            .payouts-vendor-card .sync-status.synced {
                background: #d1fae5;
                color: #059669;
            }

            .payouts-vendor-card .sync-status.not-synced {
                background: #fef3c7;
                color: #d97706;
            }

            /* Invoice Profile Card */
            .payouts-invoice-card {
                background: white;
                border: 1px solid #e5e7eb;
                border-radius: 12px;
                padding: 16px;
                margin: 12px 0;
                box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
            }

            .payouts-invoice-card .invoice-header {
                display: flex;
                justify-content: space-between;
                align-items: flex-start;
                margin-bottom: 12px;
            }

            .payouts-invoice-card .invoice-header h3 {
                margin: 0;
                font-size: 16px;
                font-weight: 600;
                color: #1f2937;
            }

            .payouts-invoice-card .invoice-amount {
                font-size: 20px;
                font-weight: 700;
                color: #059669;
            }

            .payouts-invoice-card .invoice-meta {
                display: grid;
                grid-template-columns: repeat(2, 1fr);
                gap: 8px;
                font-size: 13px;
                color: #6b7280;
                margin-bottom: 12px;
            }

            .payouts-invoice-card .invoice-actions {
                display: flex;
                flex-wrap: wrap;
                gap: 8px;
                padding-top: 12px;
                border-top: 1px solid #f3f4f6;
            }

            /* Match Result Card */
            .payouts-match-card {
                background: linear-gradient(135deg, rgba(16, 185, 129, 0.08) 0%, rgba(5, 150, 105, 0.08) 100%);
                border: 1px solid rgba(16, 185, 129, 0.2);
                border-radius: 12px;
                padding: 16px;
                margin: 12px 0;
            }

            .payouts-match-card .match-header {
                display: flex;
                align-items: center;
                gap: 8px;
                margin-bottom: 12px;
                font-weight: 600;
                color: #059669;
            }

            .payouts-match-card .match-confidence {
                display: inline-flex;
                align-items: center;
                padding: 4px 12px;
                background: #d1fae5;
                color: #059669;
                border-radius: 20px;
                font-size: 12px;
                font-weight: 600;
            }

            .payouts-match-card .match-details {
                font-size: 13px;
                color: #4b5563;
            }

            /* Gmail Email List */
            .payouts-gmail-list {
                display: flex;
                flex-direction: column;
                gap: 8px;
                margin: 12px 0;
            }

            .payouts-email-item {
                background: white;
                border: 1px solid #e5e7eb;
                border-radius: 10px;
                padding: 12px;
                display: flex;
                gap: 12px;
                transition: all 0.2s ease;
                cursor: pointer;
            }

            .payouts-email-item:hover {
                border-color: #667eea;
                box-shadow: 0 2px 8px rgba(102, 126, 234, 0.15);
            }

            .payouts-email-item .email-icon {
                width: 36px;
                height: 36px;
                border-radius: 8px;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                display: flex;
                align-items: center;
                justify-content: center;
                color: white;
                font-size: 16px;
                flex-shrink: 0;
            }

            .payouts-email-item .email-content {
                flex: 1;
                min-width: 0;
            }

            .payouts-email-item .email-subject {
                font-weight: 600;
                font-size: 14px;
                color: #1f2937;
                white-space: nowrap;
                overflow: hidden;
                text-overflow: ellipsis;
            }

            .payouts-email-item .email-from {
                font-size: 12px;
                color: #6b7280;
                white-space: nowrap;
                overflow: hidden;
                text-overflow: ellipsis;
            }

            .payouts-email-item .email-date {
                font-size: 11px;
                color: #9ca3af;
            }

            .payouts-email-item .email-actions {
                display: flex;
                gap: 6px;
                align-items: center;
            }

            .payouts-email-item .email-actions button {
                padding: 6px 12px;
                border-radius: 6px;
                border: none;
                font-size: 11px;
                cursor: pointer;
                transition: all 0.2s;
            }

            .payouts-email-item .process-btn {
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
            }

            .payouts-email-item .view-btn {
                background: #f3f4f6;
                color: #4b5563;
            }

            /* Quick Actions Bar */
            .payouts-quick-actions-bar {
                display: flex;
                flex-wrap: wrap;
                gap: 6px;
                padding: 12px 16px;
                background: #f8f9ff;
                border-top: 1px solid #e5e7eb;
            }

            .payouts-quick-action-btn {
                padding: 8px 14px;
                background: white;
                border: 1px solid #e5e7eb;
                border-radius: 20px;
                font-size: 12px;
                color: #4b5563;
                cursor: pointer;
                display: inline-flex;
                align-items: center;
                gap: 6px;
                transition: all 0.2s ease;
            }

            .payouts-quick-action-btn:hover {
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                border-color: transparent;
                transform: translateY(-1px);
            }

            .payouts-quick-action-btn .action-icon {
                font-size: 14px;
            }

            /* Inline Action Buttons in Messages */
            .payouts-inline-actions {
                display: flex;
                flex-wrap: wrap;
                gap: 8px;
                margin-top: 12px;
            }

            .payouts-action-btn {
                padding: 8px 16px;
                border-radius: 8px;
                border: none;
                font-size: 12px;
                font-weight: 500;
                cursor: pointer;
                display: inline-flex;
                align-items: center;
                gap: 6px;
                transition: all 0.2s ease;
            }

            .payouts-action-btn.primary {
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
            }

            .payouts-action-btn.primary:hover {
                transform: translateY(-1px);
                box-shadow: 0 4px 12px rgba(102, 126, 234, 0.3);
            }

            .payouts-action-btn.success {
                background: #d1fae5;
                color: #059669;
            }

            .payouts-action-btn.danger {
                background: #fee2e2;
                color: #dc2626;
            }

            .payouts-action-btn.secondary {
                background: #f3f4f6;
                color: #4b5563;
            }

            @media (max-width: 480px) {
                #payouts-agent-widget {
                    bottom: 16px;
                    right: 16px;
                }

                #payouts-chat-window {
                    width: calc(100vw - 32px);
                    height: calc(100vh - 100px);
                    bottom: 70px;
                    right: -8px;
                }

                #payouts-chat-button {
                    width: 54px;
                    height: 54px;
                }

                .payouts-upload-btn {
                    width: 40px;
                    height: 40px;
                }

                .payouts-chat-send {
                    width: 40px;
                    height: 40px;
                }

                .invoice-card {
                    padding: 12px;
                }

                .invoice-actions {
                    flex-direction: column;
                }

                .invoice-actions button,
                .invoice-actions a {
                    width: 100%;
                    justify-content: center;
                }
            }

            /* ============================================
               COMPREHENSIVE INVOICE WORKFLOW COMPONENTS
               ============================================ */

            /* 1. Enhanced Invoice Card with Full Details */
            .invoice-workflow-card {
                background: white;
                border: 1px solid #e5e7eb;
                border-radius: 16px;
                padding: 20px;
                margin: 16px 0;
                box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08);
            }

            .invoice-workflow-card .invoice-main-header {
                display: flex;
                justify-content: space-between;
                align-items: flex-start;
                margin-bottom: 16px;
                gap: 12px;
            }

            .invoice-workflow-card .vendor-info-section {
                flex: 1;
            }

            .invoice-workflow-card .vendor-name-large {
                font-size: 18px;
                font-weight: 700;
                color: #1f2937;
                margin: 0 0 4px 0;
            }

            .invoice-workflow-card .invoice-id-badge {
                display: inline-block;
                background: #f3f4f6;
                color: #6b7280;
                padding: 3px 10px;
                border-radius: 6px;
                font-size: 12px;
                font-weight: 500;
            }

            .invoice-workflow-card .amount-section {
                text-align: right;
            }

            .invoice-workflow-card .amount-large {
                font-size: 24px;
                font-weight: 700;
                color: #059669;
            }

            .invoice-workflow-card .currency-badge {
                display: inline-block;
                background: #dbeafe;
                color: #2563eb;
                padding: 2px 8px;
                border-radius: 4px;
                font-size: 11px;
                font-weight: 600;
                margin-left: 4px;
            }

            .invoice-workflow-card .invoice-details-grid {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
                gap: 12px;
                padding: 16px;
                background: #f8fafc;
                border-radius: 10px;
                margin-bottom: 16px;
            }

            .invoice-workflow-card .detail-item {
                display: flex;
                flex-direction: column;
                gap: 2px;
            }

            .invoice-workflow-card .detail-label {
                font-size: 11px;
                color: #6b7280;
                text-transform: uppercase;
                letter-spacing: 0.5px;
            }

            .invoice-workflow-card .detail-value {
                font-size: 14px;
                color: #1f2937;
                font-weight: 500;
            }

            .invoice-workflow-card .line-items-section {
                margin-bottom: 16px;
            }

            .invoice-workflow-card .line-items-toggle {
                display: flex;
                align-items: center;
                gap: 8px;
                padding: 10px 14px;
                background: #f3f4f6;
                border: none;
                border-radius: 8px;
                cursor: pointer;
                font-size: 13px;
                color: #4b5563;
                width: 100%;
                transition: all 0.2s;
            }

            .invoice-workflow-card .line-items-toggle:hover {
                background: #e5e7eb;
            }

            .invoice-workflow-card .line-items-table {
                margin-top: 12px;
                border: 1px solid #e5e7eb;
                border-radius: 8px;
                overflow: hidden;
                display: none;
            }

            .invoice-workflow-card .line-items-table.open {
                display: block;
            }

            .invoice-workflow-card .line-items-table table {
                width: 100%;
                border-collapse: collapse;
                font-size: 12px;
            }

            .invoice-workflow-card .line-items-table th {
                background: #f8fafc;
                padding: 10px 12px;
                text-align: left;
                font-weight: 600;
                color: #4b5563;
                border-bottom: 1px solid #e5e7eb;
            }

            .invoice-workflow-card .line-items-table td {
                padding: 10px 12px;
                border-bottom: 1px solid #f3f4f6;
                color: #1f2937;
            }

            .invoice-workflow-card .line-items-table tr:last-child td {
                border-bottom: none;
            }

            /* 2. Enhanced Match Result Section */
            .match-result-section {
                margin: 16px 0;
                border-radius: 12px;
                overflow: hidden;
            }

            .match-result-section.verdict-match {
                background: linear-gradient(135deg, rgba(16, 185, 129, 0.1) 0%, rgba(5, 150, 105, 0.05) 100%);
                border: 1px solid rgba(16, 185, 129, 0.3);
            }

            .match-result-section.verdict-new {
                background: linear-gradient(135deg, rgba(245, 158, 11, 0.1) 0%, rgba(217, 119, 6, 0.05) 100%);
                border: 1px solid rgba(245, 158, 11, 0.3);
            }

            .match-result-section.verdict-ambiguous {
                background: linear-gradient(135deg, rgba(99, 102, 241, 0.1) 0%, rgba(79, 70, 229, 0.05) 100%);
                border: 1px solid rgba(99, 102, 241, 0.3);
            }

            .match-result-header {
                padding: 14px 16px;
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: 12px;
            }

            .match-verdict-badge {
                display: flex;
                align-items: center;
                gap: 8px;
                font-weight: 600;
                font-size: 14px;
            }

            .match-verdict-badge.matched {
                color: #059669;
            }

            .match-verdict-badge.new-vendor {
                color: #d97706;
            }

            .match-verdict-badge.ambiguous {
                color: #4f46e5;
            }

            .confidence-indicator {
                display: flex;
                align-items: center;
                gap: 8px;
            }

            .confidence-bar {
                width: 80px;
                height: 8px;
                background: rgba(0, 0, 0, 0.1);
                border-radius: 4px;
                overflow: hidden;
            }

            .confidence-fill {
                height: 100%;
                border-radius: 4px;
                transition: width 0.5s ease;
            }

            .confidence-fill.high {
                background: linear-gradient(90deg, #10b981 0%, #059669 100%);
            }

            .confidence-fill.medium {
                background: linear-gradient(90deg, #f59e0b 0%, #d97706 100%);
            }

            .confidence-fill.low {
                background: linear-gradient(90deg, #ef4444 0%, #dc2626 100%);
            }

            .confidence-text {
                font-size: 12px;
                font-weight: 600;
            }

            .match-result-body {
                padding: 0 16px 16px;
            }

            .matched-vendor-card {
                background: white;
                border-radius: 10px;
                padding: 14px;
                display: flex;
                align-items: center;
                gap: 14px;
                margin-bottom: 12px;
            }

            .matched-vendor-avatar {
                width: 48px;
                height: 48px;
                border-radius: 10px;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                display: flex;
                align-items: center;
                justify-content: center;
                color: white;
                font-weight: 700;
                font-size: 18px;
            }

            .matched-vendor-details {
                flex: 1;
            }

            .matched-vendor-name {
                font-weight: 600;
                color: #1f2937;
                font-size: 15px;
                margin-bottom: 4px;
            }

            .matched-vendor-meta {
                display: flex;
                flex-wrap: wrap;
                gap: 12px;
                font-size: 12px;
                color: #6b7280;
            }

            .match-reasoning {
                background: rgba(0, 0, 0, 0.03);
                border-radius: 8px;
                padding: 12px;
                font-size: 13px;
                color: #4b5563;
                line-height: 1.5;
            }

            .match-reasoning::before {
                content: '🧠 ';
            }

            /* 3. Vendor Selection Dropdown */
            .vendor-select-section {
                margin: 16px 0;
                background: white;
                border: 1px solid #e5e7eb;
                border-radius: 12px;
                padding: 16px;
            }

            .vendor-select-header {
                display: flex;
                align-items: center;
                gap: 8px;
                margin-bottom: 12px;
                font-weight: 600;
                color: #1f2937;
            }

            .vendor-search-input {
                width: 100%;
                padding: 12px 14px;
                border: 1px solid #e5e7eb;
                border-radius: 10px;
                font-size: 14px;
                outline: none;
                transition: all 0.2s;
                margin-bottom: 12px;
            }

            .vendor-search-input:focus {
                border-color: #667eea;
                box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.15);
            }

            .vendor-candidates-list {
                max-height: 200px;
                overflow-y: auto;
                border: 1px solid #e5e7eb;
                border-radius: 10px;
            }

            .vendor-candidate-item {
                display: flex;
                align-items: center;
                gap: 12px;
                padding: 12px 14px;
                cursor: pointer;
                transition: all 0.2s;
                border-bottom: 1px solid #f3f4f6;
            }

            .vendor-candidate-item:last-child {
                border-bottom: none;
            }

            .vendor-candidate-item:hover {
                background: #f8fafc;
            }

            .vendor-candidate-item.selected {
                background: linear-gradient(135deg, rgba(102, 126, 234, 0.1) 0%, rgba(118, 75, 162, 0.1) 100%);
                border-left: 3px solid #667eea;
            }

            .vendor-candidate-avatar {
                width: 36px;
                height: 36px;
                border-radius: 8px;
                background: #e5e7eb;
                display: flex;
                align-items: center;
                justify-content: center;
                color: #4b5563;
                font-weight: 600;
                font-size: 14px;
            }

            .vendor-candidate-info {
                flex: 1;
            }

            .vendor-candidate-name {
                font-weight: 500;
                color: #1f2937;
                font-size: 14px;
            }

            .vendor-candidate-email {
                font-size: 12px;
                color: #6b7280;
            }

            .vendor-candidate-confidence {
                font-size: 11px;
                padding: 2px 8px;
                border-radius: 10px;
                font-weight: 500;
            }

            .vendor-candidate-confidence.high {
                background: #d1fae5;
                color: #059669;
            }

            .vendor-candidate-confidence.medium {
                background: #fef3c7;
                color: #d97706;
            }

            /* 4. New Vendor Form */
            .new-vendor-form-section {
                margin: 16px 0;
                background: white;
                border: 1px solid #e5e7eb;
                border-radius: 12px;
                overflow: hidden;
            }

            .new-vendor-form-header {
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                padding: 14px 16px;
                display: flex;
                align-items: center;
                gap: 10px;
                font-weight: 600;
            }

            .new-vendor-form-body {
                padding: 16px;
            }

            .form-row {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
                gap: 12px;
                margin-bottom: 12px;
            }

            .form-field {
                display: flex;
                flex-direction: column;
                gap: 4px;
            }

            .form-field label {
                font-size: 12px;
                font-weight: 500;
                color: #4b5563;
            }

            .form-field input,
            .form-field select {
                padding: 10px 12px;
                border: 1px solid #e5e7eb;
                border-radius: 8px;
                font-size: 14px;
                outline: none;
                transition: all 0.2s;
            }

            .form-field input:focus,
            .form-field select:focus {
                border-color: #667eea;
                box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.15);
            }

            .form-field input.prefilled {
                background: #f0fdf4;
                border-color: #86efac;
            }

            .form-field .prefill-indicator {
                font-size: 10px;
                color: #059669;
            }

            /* 5. Action Bar */
            .invoice-action-bar {
                display: flex;
                flex-wrap: wrap;
                gap: 10px;
                padding: 16px;
                background: #f8fafc;
                border-top: 1px solid #e5e7eb;
                border-radius: 0 0 16px 16px;
            }

            .action-btn {
                padding: 12px 20px;
                border-radius: 10px;
                border: none;
                font-size: 13px;
                font-weight: 600;
                cursor: pointer;
                display: inline-flex;
                align-items: center;
                gap: 8px;
                transition: all 0.2s;
            }

            .action-btn:disabled {
                opacity: 0.5;
                cursor: not-allowed;
            }

            .action-btn.primary-action {
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                flex: 1;
                justify-content: center;
            }

            .action-btn.primary-action:hover:not(:disabled) {
                transform: translateY(-2px);
                box-shadow: 0 6px 20px rgba(102, 126, 234, 0.35);
            }

            .action-btn.secondary-action {
                background: white;
                color: #4b5563;
                border: 1px solid #e5e7eb;
            }

            .action-btn.secondary-action:hover:not(:disabled) {
                background: #f3f4f6;
            }

            .action-btn.success-action {
                background: #059669;
                color: white;
            }

            .action-btn.success-action:hover:not(:disabled) {
                background: #047857;
            }

            .action-status {
                display: inline-flex;
                align-items: center;
                gap: 6px;
                padding: 6px 12px;
                border-radius: 20px;
                font-size: 12px;
                font-weight: 500;
            }

            .action-status.loading {
                background: #dbeafe;
                color: #2563eb;
            }

            .action-status.success {
                background: #d1fae5;
                color: #059669;
            }

            .action-status.error {
                background: #fee2e2;
                color: #dc2626;
            }

            .action-status .spinner {
                width: 14px;
                height: 14px;
                border: 2px solid currentColor;
                border-top-color: transparent;
                border-radius: 50%;
                animation: spin 0.8s linear infinite;
            }

            @keyframes spin {
                to { transform: rotate(360deg); }
            }

            /* PDF Link Button */
            .pdf-link-btn {
                display: inline-flex;
                align-items: center;
                gap: 6px;
                padding: 8px 14px;
                background: #fef3c7;
                color: #92400e;
                border-radius: 8px;
                font-size: 12px;
                font-weight: 500;
                text-decoration: none;
                transition: all 0.2s;
            }

            .pdf-link-btn:hover {
                background: #fde68a;
            }

            /* NetSuite Status Badge */
            .netsuite-status-badge {
                display: inline-flex;
                align-items: center;
                gap: 6px;
                padding: 4px 12px;
                border-radius: 20px;
                font-size: 11px;
                font-weight: 600;
            }

            .netsuite-status-badge.synced {
                background: #dbeafe;
                color: #1d4ed8;
            }

            .netsuite-status-badge.not-synced {
                background: #f3f4f6;
                color: #6b7280;
            }

            .netsuite-status-badge.pending {
                background: #fef3c7;
                color: #d97706;
            }

            /* Responsive adjustments for invoice workflow */
            @media (max-width: 480px) {
                .invoice-workflow-card {
                    padding: 14px;
                }

                .invoice-workflow-card .invoice-main-header {
                    flex-direction: column;
                    align-items: flex-start;
                }

                .invoice-workflow-card .amount-section {
                    text-align: left;
                    margin-top: 8px;
                }

                .invoice-workflow-card .invoice-details-grid {
                    grid-template-columns: 1fr 1fr;
                }

                .match-result-header {
                    flex-direction: column;
                    align-items: flex-start;
                    gap: 8px;
                }

                .form-row {
                    grid-template-columns: 1fr;
                }

                .invoice-action-bar {
                    flex-direction: column;
                }

                .action-btn {
                    width: 100%;
                    justify-content: center;
                }
            }
        `;
        document.head.appendChild(styles);
    }

    function createWidget() {
        if (document.getElementById(WIDGET_ID)) return;

        widgetContainer = document.createElement('div');
        widgetContainer.id = WIDGET_ID;

        chatWindow = document.createElement('div');
        chatWindow.id = 'payouts-chat-window';
        chatWindow.innerHTML = `
            <div class="payouts-chat-header">
                <div class="payouts-chat-header-info">
                    <div class="payouts-chat-avatar">🤖</div>
                    <div>
                        <h4 class="payouts-chat-title">Payouts AI</h4>
                        <p class="payouts-chat-subtitle">Ask me anything about invoices & vendors</p>
                    </div>
                </div>
                <div class="payouts-status-indicator" id="payouts-status-indicator">
                    <div class="payouts-status-dot checking" id="payouts-status-dot"></div>
                    <div class="payouts-status-services">
                        <span class="payouts-service-badge" id="gmail-status">📧 Checking...</span>
                        <span class="payouts-service-badge" id="netsuite-status">🔗 Checking...</span>
                    </div>
                </div>
                <button class="payouts-chat-close" aria-label="Close chat">
                    <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                        <path d="M1 1L13 13M1 13L13 1" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
                    </svg>
                </button>
            </div>
            <div class="payouts-chat-messages" id="payouts-messages-container">
                <div class="payouts-welcome-message">
                    <h3>Welcome to Payouts AI</h3>
                    <p>I'm your AP automation assistant. I can manage vendors, process invoices, scan Gmail, and sync with NetSuite.</p>
                    <div class="payouts-quick-actions">
                        <button class="payouts-quick-action" data-message="Import vendors from NetSuite">🔄 Import from NetSuite</button>
                        <button class="payouts-quick-action" data-message="Show me all my vendors">📋 Show Vendors</button>
                        <button class="payouts-quick-action" data-message="Scan Gmail for invoices">📧 Scan Gmail</button>
                        <button class="payouts-quick-action" data-message="Show my recent invoices">🧾 My Invoices</button>
                    </div>
                </div>
            </div>
            <div class="payouts-chat-input-area">
                <div class="payouts-file-indicator" id="payouts-file-indicator">
                    <span class="file-icon">📎</span>
                    <span class="file-name" id="payouts-file-name"></span>
                    <button class="file-remove" id="payouts-file-remove" aria-label="Remove file">
                        <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                            <path d="M1 1L13 13M1 13L13 1" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
                        </svg>
                    </button>
                </div>
                <div class="payouts-input-row">
                    <input 
                        type="file" 
                        class="payouts-file-input" 
                        id="payouts-file-input"
                        accept=".pdf,.csv"
                    />
                    <button class="payouts-upload-btn" id="payouts-upload-btn" aria-label="Upload file">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                            <path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48"/>
                        </svg>
                    </button>
                    <textarea 
                        class="payouts-chat-input" 
                        id="payouts-chat-input"
                        placeholder="Ask about invoices, vendors, or subscriptions..."
                        rows="1"
                    ></textarea>
                    <button class="payouts-chat-send" id="payouts-send-btn" aria-label="Send message">
                        <svg viewBox="0 0 24 24" fill="none">
                            <path d="M22 2L11 13M22 2L15 22L11 13M22 2L2 9L11 13" stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
                        </svg>
                    </button>
                </div>
            </div>
        `;

        floatingButton = document.createElement('button');
        floatingButton.id = 'payouts-chat-button';
        floatingButton.setAttribute('aria-label', 'Open chat with Payouts AI');
        floatingButton.innerHTML = `
            <svg viewBox="0 0 24 24" fill="none">
                <path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z" fill="currentColor"/>
            </svg>
        `;

        widgetContainer.appendChild(chatWindow);
        widgetContainer.appendChild(floatingButton);
        document.body.appendChild(widgetContainer);

        attachEventListeners();
    }

    function attachEventListeners() {
        floatingButton.addEventListener('click', toggleChat);

        const closeBtn = chatWindow.querySelector('.payouts-chat-close');
        closeBtn.addEventListener('click', closeChat);

        const input = document.getElementById('payouts-chat-input');
        const sendBtn = document.getElementById('payouts-send-btn');
        const fileInput = document.getElementById('payouts-file-input');
        const uploadBtn = document.getElementById('payouts-upload-btn');
        const fileRemoveBtn = document.getElementById('payouts-file-remove');

        sendBtn.addEventListener('click', sendMessage);

        input.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                sendMessage();
            }
        });

        input.addEventListener('input', () => {
            input.style.height = 'auto';
            input.style.height = Math.min(input.scrollHeight, 120) + 'px';
        });

        uploadBtn.addEventListener('click', () => {
            fileInput.click();
        });

        fileInput.addEventListener('change', handleFileSelect);

        fileRemoveBtn.addEventListener('click', clearSelectedFile);

        const quickActions = chatWindow.querySelectorAll('.payouts-quick-action');
        quickActions.forEach(btn => {
            btn.addEventListener('click', () => {
                const message = btn.getAttribute('data-message');
                if (message) {
                    document.getElementById('payouts-chat-input').value = message;
                    sendMessage();
                }
            });
        });
    }

    function handleFileSelect(e) {
        const file = e.target.files[0];
        if (file) {
            selectedFile = file;
            const fileIndicator = document.getElementById('payouts-file-indicator');
            const fileName = document.getElementById('payouts-file-name');
            const uploadBtn = document.getElementById('payouts-upload-btn');

            fileName.textContent = file.name;
            fileIndicator.classList.add('active');
            uploadBtn.classList.add('has-file');
        }
    }

    function clearSelectedFile() {
        selectedFile = null;
        const fileInput = document.getElementById('payouts-file-input');
        const fileIndicator = document.getElementById('payouts-file-indicator');
        const uploadBtn = document.getElementById('payouts-upload-btn');

        fileInput.value = '';
        fileIndicator.classList.remove('active');
        uploadBtn.classList.remove('has-file');
    }

    function toggleChat() {
        isOpen = !isOpen;
        chatWindow.classList.toggle('open', isOpen);
        floatingButton.classList.toggle('open', isOpen);

        if (isOpen) {
            setTimeout(() => {
                document.getElementById('payouts-chat-input').focus();
            }, 300);
        }
    }

    function closeChat() {
        isOpen = false;
        chatWindow.classList.remove('open');
        floatingButton.classList.remove('open');
    }

    async function sendMessage() {
        const input = document.getElementById('payouts-chat-input');
        const message = input.value.trim();

        if ((!message && !selectedFile) || isLoading) return;

        const displayMessage = selectedFile 
            ? (message || `Uploaded: ${selectedFile.name}`)
            : message;

        input.value = '';
        input.style.height = 'auto';

        addMessage('user', displayMessage);
        showLoading();

        try {
            const sessionId = getSessionId();
            let response;

            if (selectedFile) {
                const formData = new FormData();
                formData.append('message', message);
                formData.append('thread_id', sessionId);
                formData.append('file', selectedFile);

                response = await fetch(API_ENDPOINT, {
                    method: 'POST',
                    body: formData
                });

                clearSelectedFile();
            } else {
                response = await fetch(API_ENDPOINT, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({ 
                        message,
                        thread_id: sessionId
                    })
                });
            }

            const data = await response.json();
            hideLoading();

            if (data.success) {
                const tools = data.tools_used || [];
                addMessage('assistant', data.response, tools);
            } else {
                addMessage('assistant', 'Sorry, I encountered an error. Please try again.');
            }
        } catch (error) {
            hideLoading();
            addMessage('assistant', 'Sorry, I could not connect to the server. Please check your connection and try again.');
        }
    }

    function addMessage(role, content, tools = []) {
        const container = document.getElementById('payouts-messages-container');
        
        const welcomeMsg = container.querySelector('.payouts-welcome-message');
        if (welcomeMsg) {
            welcomeMsg.remove();
        }

        const messageDiv = document.createElement('div');
        messageDiv.className = `payouts-message ${role}`;

        let html = '';

        if (role === 'assistant' && tools.length > 0) {
            html += '<div class="payouts-tool-badges">';
            tools.forEach(tool => {
                const icon = TOOL_ICONS[tool] || '⚙️';
                const label = TOOL_LABELS[tool] || tool;
                html += `<span class="payouts-tool-badge"><span class="badge-icon">${icon}</span>${label}</span>`;
            });
            html += '</div>';
        }

        const formattedContent = formatContent(content);
        html += `<div class="payouts-message-bubble">${formattedContent}</div>`;

        messageDiv.innerHTML = html;
        container.appendChild(messageDiv);

        container.scrollTop = container.scrollHeight;

        messages.push({ role, content, tools });
    }

    function formatContent(content) {
        if (!content) return '';
        
        const htmlPatterns = [
            /<div\s+class="[^"]*"[\s\S]*?<\/div>/i,
            /<table[\s\S]*?<\/table>/i,
            /<a\s+[^>]*class="chat-action-btn"[^>]*>/i,
            /<button[\s\S]*?<\/button>/i,
            /<ul[\s\S]*?<\/ul>/i,
            /<h[1-6][\s\S]*?<\/h[1-6]>/i
        ];
        
        const containsStructuredHtml = htmlPatterns.some(pattern => pattern.test(content));
        
        if (containsStructuredHtml) {
            let processed = content;
            
            processed = processed.replace(/<table(?![^>]*class=)/gi, '<table class="payouts-data-table"');
            
            processed = processed.replace(/<div class="vendor-profile"/gi, '<div class="payouts-vendor-card"');
            processed = processed.replace(/<div class="invoice-card"/gi, '<div class="payouts-invoice-card"');
            processed = processed.replace(/<div class="match-result"/gi, '<div class="payouts-match-card"');
            processed = processed.replace(/<div class="gmail-list"/gi, '<div class="payouts-gmail-list"');
            processed = processed.replace(/<div class="email-item"/gi, '<div class="payouts-email-item"');
            
            const textParts = processed.split(/(<[^>]+>)/);
            processed = textParts.map(part => {
                if (part.startsWith('<')) {
                    return part;
                }
                return part.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
                          .replace(/\n/g, '<br>');
            }).join('');
            
            return processed;
        }
        
        let formatted = content
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;');
        
        formatted = formatted.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
        formatted = formatted.replace(/\n/g, '<br>');
        
        return formatted;
    }

    function showLoading() {
        isLoading = true;
        const container = document.getElementById('payouts-messages-container');
        
        const loadingDiv = document.createElement('div');
        loadingDiv.id = 'payouts-loading-message';
        loadingDiv.className = 'payouts-loading-indicator';
        loadingDiv.innerHTML = `
            <div class="payouts-tool-badges">
                <span class="payouts-tool-badge loading"><span class="badge-icon">⚙️</span>Processing...</span>
            </div>
            <div class="payouts-loading-dots">
                <span class="payouts-loading-dot"></span>
                <span class="payouts-loading-dot"></span>
                <span class="payouts-loading-dot"></span>
            </div>
        `;
        container.appendChild(loadingDiv);
        container.scrollTop = container.scrollHeight;

        document.getElementById('payouts-send-btn').disabled = true;
    }

    function hideLoading() {
        isLoading = false;
        const loadingMsg = document.getElementById('payouts-loading-message');
        if (loadingMsg) {
            loadingMsg.remove();
        }
        document.getElementById('payouts-send-btn').disabled = false;
    }

    async function checkAgentStatus() {
        const statusDot = document.getElementById('payouts-status-dot');
        const gmailStatus = document.getElementById('gmail-status');
        const netsuiteStatus = document.getElementById('netsuite-status');
        
        if (!statusDot || !gmailStatus || !netsuiteStatus) return;
        
        try {
            const response = await fetch('/api/agent/status');
            const data = await response.json();
            
            if (data.success) {
                if (data.gmail.connected) {
                    gmailStatus.textContent = '📧 Gmail';
                    gmailStatus.className = 'payouts-service-badge connected';
                } else {
                    gmailStatus.textContent = '📧 Offline';
                    gmailStatus.className = 'payouts-service-badge disconnected';
                }
                
                if (data.netsuite.connected) {
                    netsuiteStatus.textContent = '🔗 NetSuite';
                    netsuiteStatus.className = 'payouts-service-badge connected';
                } else {
                    netsuiteStatus.textContent = '🔗 Offline';
                    netsuiteStatus.className = 'payouts-service-badge disconnected';
                }
                
                const isOnline = data.gmail.connected || data.netsuite.connected;
                statusDot.className = 'payouts-status-dot ' + (isOnline ? 'online' : 'offline');
            }
        } catch (error) {
            console.error('Failed to check agent status:', error);
            statusDot.className = 'payouts-status-dot offline';
            gmailStatus.textContent = '📧 Unknown';
            netsuiteStatus.textContent = '🔗 Unknown';
        }
    }

    function startStatusPolling() {
        checkAgentStatus();
        setInterval(checkAgentStatus, 30000);
    }

    function init() {
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', () => {
                injectStyles();
                createWidget();
                startStatusPolling();
            });
        } else {
            injectStyles();
            createWidget();
            startStatusPolling();
        }
    }

    init();

    window.PayoutsAgentWidget = {
        open: () => {
            isOpen = true;
            chatWindow.classList.add('open');
            floatingButton.classList.add('open');
        },
        close: closeChat,
        toggle: toggleChat,
        sendMessage: (msg) => {
            document.getElementById('payouts-chat-input').value = msg;
            sendMessage();
        },
        clearSession: clearSession
    };

    window.approveInvoice = async function(invoiceId) {
        try {
            const response = await fetch('/api/agent/feedback', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ 
                    invoice_id: invoiceId, 
                    action: 'approve',
                    thread_id: getSessionId()
                })
            });
            const data = await response.json();
            if (data.success) {
                const btn = document.querySelector(`[onclick="approveInvoice('${invoiceId}')"]`);
                if (btn) {
                    btn.textContent = '✅ Approved';
                    btn.disabled = true;
                    btn.style.background = '#10b981';
                    btn.style.color = 'white';
                }
                window.PayoutsAgentWidget.sendMessage(`Invoice ${invoiceId} has been approved. Please confirm.`);
            }
        } catch (error) {
            console.error('Approve failed:', error);
            alert('Failed to approve invoice. Please try again.');
        }
    };

    window.rejectInvoice = async function(invoiceId) {
        const reason = prompt('Why is this not an invoice? (optional)');
        try {
            const response = await fetch('/api/agent/feedback', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ 
                    invoice_id: invoiceId, 
                    action: 'reject',
                    reason: reason || 'Not an invoice',
                    thread_id: getSessionId()
                })
            });
            const data = await response.json();
            if (data.success) {
                const btn = document.querySelector(`[onclick="rejectInvoice('${invoiceId}')"]`);
                if (btn) {
                    btn.textContent = '❌ Rejected';
                    btn.disabled = true;
                }
                const card = btn?.closest('.invoice-card');
                if (card) {
                    card.style.opacity = '0.5';
                }
            }
        } catch (error) {
            console.error('Reject failed:', error);
            alert('Failed to reject. Please try again.');
        }
    };

    window.createBill = async function(invoiceId, vendorId, amount, currency) {
        try {
            window.PayoutsAgentWidget.open();
            window.PayoutsAgentWidget.sendMessage(`Create a NetSuite bill for invoice ${invoiceId}`);
        } catch (error) {
            console.error('Create bill failed:', error);
        }
    };

    window.viewInvoicePdf = function(url) {
        window.open(url, '_blank');
    };

    // ============================================
    // INVOICE WORKFLOW HANDLERS
    // ============================================

    // Toggle line items visibility
    window.toggleLineItems = function(invoiceId) {
        const table = document.querySelector(`#line-items-${invoiceId}`);
        const toggle = document.querySelector(`#line-items-toggle-${invoiceId}`);
        if (table) {
            table.classList.toggle('open');
            if (toggle) {
                const isOpen = table.classList.contains('open');
                toggle.innerHTML = isOpen 
                    ? '📋 Hide Line Items ▲' 
                    : '📋 Show Line Items ▼';
            }
        }
    };

    // Select vendor from dropdown
    window.selectVendor = function(invoiceId, vendorId, vendorName) {
        const candidates = document.querySelectorAll(`#vendor-candidates-${invoiceId} .vendor-candidate-item`);
        candidates.forEach(c => c.classList.remove('selected'));
        
        const selected = document.querySelector(`[data-vendor-id="${vendorId}"]`);
        if (selected) {
            selected.classList.add('selected');
        }

        // Enable sync button
        const syncBtn = document.querySelector(`#sync-btn-${invoiceId}`);
        if (syncBtn) {
            syncBtn.disabled = false;
            syncBtn.dataset.vendorId = vendorId;
            syncBtn.dataset.vendorName = vendorName;
        }

        // Update selection display
        const selectionDisplay = document.querySelector(`#selected-vendor-${invoiceId}`);
        if (selectionDisplay) {
            selectionDisplay.innerHTML = `<span class="action-status success">✓ Selected: ${vendorName}</span>`;
        }
    };

    // Search vendors in dropdown
    window.searchVendors = async function(invoiceId, searchTerm) {
        if (searchTerm.length < 2) return;
        
        const container = document.querySelector(`#vendor-candidates-${invoiceId}`);
        if (!container) return;

        container.innerHTML = '<div style="padding: 12px; text-align: center; color: #6b7280;">Searching...</div>';

        try {
            const response = await fetch('/api/vendors/search?q=' + encodeURIComponent(searchTerm));
            const data = await response.json();
            
            if (data.success && data.vendors.length > 0) {
                let html = '';
                data.vendors.forEach(v => {
                    const initials = (v.name || 'V').substring(0, 2).toUpperCase();
                    html += `
                        <div class="vendor-candidate-item" data-vendor-id="${v.id}" onclick="selectVendor('${invoiceId}', '${v.id}', '${v.name.replace(/'/g, "\\'")}')">
                            <div class="vendor-candidate-avatar">${initials}</div>
                            <div class="vendor-candidate-info">
                                <div class="vendor-candidate-name">${v.name}</div>
                                <div class="vendor-candidate-email">${v.email || 'No email'}</div>
                            </div>
                        </div>
                    `;
                });
                container.innerHTML = html;
            } else {
                container.innerHTML = '<div style="padding: 12px; text-align: center; color: #6b7280;">No vendors found</div>';
            }
        } catch (error) {
            container.innerHTML = '<div style="padding: 12px; text-align: center; color: #dc2626;">Search failed</div>';
        }
    };

    // Show create vendor form with prefilled data
    window.showCreateVendorForm = function(invoiceId, vendorData) {
        const formContainer = document.querySelector(`#create-vendor-form-${invoiceId}`);
        if (!formContainer) return;

        const data = typeof vendorData === 'string' ? JSON.parse(vendorData) : vendorData;
        
        formContainer.style.display = 'block';
        formContainer.innerHTML = `
            <div class="new-vendor-form-section">
                <div class="new-vendor-form-header">
                    <span>➕</span> Create New Vendor
                </div>
                <div class="new-vendor-form-body">
                    <div class="form-row">
                        <div class="form-field">
                            <label>Company Name *</label>
                            <input type="text" id="new-vendor-name-${invoiceId}" value="${data.name || ''}" class="${data.name ? 'prefilled' : ''}" required>
                            ${data.name ? '<span class="prefill-indicator">Auto-filled from invoice</span>' : ''}
                        </div>
                        <div class="form-field">
                            <label>Tax ID / VAT</label>
                            <input type="text" id="new-vendor-taxid-${invoiceId}" value="${data.tax_id || ''}" class="${data.tax_id ? 'prefilled' : ''}">
                            ${data.tax_id ? '<span class="prefill-indicator">Auto-filled from invoice</span>' : ''}
                        </div>
                    </div>
                    <div class="form-row">
                        <div class="form-field">
                            <label>Email</label>
                            <input type="email" id="new-vendor-email-${invoiceId}" value="${data.email || ''}" class="${data.email ? 'prefilled' : ''}">
                            ${data.email ? '<span class="prefill-indicator">Auto-filled from invoice</span>' : ''}
                        </div>
                        <div class="form-field">
                            <label>Phone</label>
                            <input type="tel" id="new-vendor-phone-${invoiceId}" value="${data.phone || ''}">
                        </div>
                    </div>
                    <div class="form-row">
                        <div class="form-field" style="grid-column: 1/-1;">
                            <label>Address</label>
                            <input type="text" id="new-vendor-address-${invoiceId}" value="${data.address || ''}" class="${data.address ? 'prefilled' : ''}">
                            ${data.address ? '<span class="prefill-indicator">Auto-filled from invoice</span>' : ''}
                        </div>
                    </div>
                    <div class="form-row">
                        <div class="form-field">
                            <label>City</label>
                            <input type="text" id="new-vendor-city-${invoiceId}" value="${data.city || ''}">
                        </div>
                        <div class="form-field">
                            <label>Country</label>
                            <input type="text" id="new-vendor-country-${invoiceId}" value="${data.country || ''}">
                        </div>
                    </div>
                    <div class="invoice-action-bar" style="margin-top: 16px; padding: 0; background: transparent; border-top: none;">
                        <button class="action-btn secondary-action" onclick="hideCreateVendorForm('${invoiceId}')">Cancel</button>
                        <button class="action-btn primary-action" onclick="createVendorFromForm('${invoiceId}')">
                            <span>💾</span> Create Vendor
                        </button>
                    </div>
                </div>
            </div>
        `;
    };

    window.hideCreateVendorForm = function(invoiceId) {
        const formContainer = document.querySelector(`#create-vendor-form-${invoiceId}`);
        if (formContainer) {
            formContainer.style.display = 'none';
        }
    };

    // Create vendor from form
    window.createVendorFromForm = async function(invoiceId) {
        const name = document.querySelector(`#new-vendor-name-${invoiceId}`)?.value;
        const taxId = document.querySelector(`#new-vendor-taxid-${invoiceId}`)?.value;
        const email = document.querySelector(`#new-vendor-email-${invoiceId}`)?.value;
        const phone = document.querySelector(`#new-vendor-phone-${invoiceId}`)?.value;
        const address = document.querySelector(`#new-vendor-address-${invoiceId}`)?.value;
        const city = document.querySelector(`#new-vendor-city-${invoiceId}`)?.value;
        const country = document.querySelector(`#new-vendor-country-${invoiceId}`)?.value;

        if (!name) {
            alert('Company name is required');
            return;
        }

        const btn = document.querySelector(`#create-vendor-form-${invoiceId} .action-btn.primary-action`);
        if (btn) {
            btn.disabled = true;
            btn.innerHTML = '<div class="spinner"></div> Creating...';
        }

        try {
            const response = await fetch('/api/vendors/create', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    invoice_id: invoiceId,
                    name, tax_id: taxId, email, phone, address, city, country
                })
            });
            const data = await response.json();

            if (data.success) {
                hideCreateVendorForm(invoiceId);
                
                // Update invoice card to show vendor created
                const statusArea = document.querySelector(`#match-status-${invoiceId}`);
                if (statusArea) {
                    statusArea.innerHTML = `
                        <div class="match-result-section verdict-match">
                            <div class="match-result-header">
                                <div class="match-verdict-badge matched">✅ Vendor Created</div>
                            </div>
                            <div class="match-result-body">
                                <div class="matched-vendor-card">
                                    <div class="matched-vendor-avatar">${name.substring(0,2).toUpperCase()}</div>
                                    <div class="matched-vendor-details">
                                        <div class="matched-vendor-name">${name}</div>
                                        <div class="matched-vendor-meta">
                                            ${email ? `<span>📧 ${email}</span>` : ''}
                                            ${data.vendor_id ? `<span>ID: ${data.vendor_id}</span>` : ''}
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>
                    `;
                }

                // Enable sync button
                const syncBtn = document.querySelector(`#sync-btn-${invoiceId}`);
                if (syncBtn) {
                    syncBtn.disabled = false;
                    syncBtn.dataset.vendorId = data.vendor_id;
                    syncBtn.dataset.vendorName = name;
                }

                window.PayoutsAgentWidget.sendMessage(`I created a new vendor "${name}" for invoice ${invoiceId}. Ready to sync to NetSuite.`);
            } else {
                throw new Error(data.error || 'Failed to create vendor');
            }
        } catch (error) {
            if (btn) {
                btn.disabled = false;
                btn.innerHTML = '<span>💾</span> Create Vendor';
            }
            alert('Failed to create vendor: ' + error.message);
        }
    };

    // Sync vendor to NetSuite
    window.syncVendorToNetsuite = async function(invoiceId) {
        const syncBtn = document.querySelector(`#sync-btn-${invoiceId}`);
        if (!syncBtn) return;

        const vendorId = syncBtn.dataset.vendorId;
        const vendorName = syncBtn.dataset.vendorName;

        syncBtn.disabled = true;
        syncBtn.innerHTML = '<div class="spinner"></div> Syncing...';

        try {
            const response = await fetch('/api/netsuite/sync-vendor', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ vendor_id: vendorId, invoice_id: invoiceId })
            });
            const data = await response.json();

            if (data.success) {
                syncBtn.innerHTML = '✅ Synced to NetSuite';
                syncBtn.className = 'action-btn success-action';
                syncBtn.disabled = true;

                // Show status
                const statusDisplay = document.querySelector(`#sync-status-${invoiceId}`);
                if (statusDisplay) {
                    statusDisplay.innerHTML = `<span class="netsuite-status-badge synced">✓ NetSuite ID: ${data.netsuite_id}</span>`;
                }

                // Enable create bill button
                const billBtn = document.querySelector(`#bill-btn-${invoiceId}`);
                if (billBtn) {
                    billBtn.disabled = false;
                    billBtn.dataset.netsuiteVendorId = data.netsuite_id;
                }
            } else {
                throw new Error(data.error || 'Sync failed');
            }
        } catch (error) {
            syncBtn.disabled = false;
            syncBtn.innerHTML = '🔄 Sync to NetSuite';
            alert('Sync failed: ' + error.message);
        }
    };

    // Create bill in NetSuite
    window.createBillInNetsuite = async function(invoiceId) {
        const billBtn = document.querySelector(`#bill-btn-${invoiceId}`);
        if (!billBtn) return;

        const netsuiteVendorId = billBtn.dataset.netsuiteVendorId;

        billBtn.disabled = true;
        billBtn.innerHTML = '<div class="spinner"></div> Creating Bill...';

        try {
            const response = await fetch('/api/netsuite/create-bill', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    invoice_id: invoiceId,
                    vendor_netsuite_id: netsuiteVendorId
                })
            });
            const data = await response.json();

            if (data.success) {
                billBtn.innerHTML = '✅ Bill Created';
                billBtn.className = 'action-btn success-action';

                // Show bill info
                const billStatus = document.querySelector(`#bill-status-${invoiceId}`);
                if (billStatus) {
                    billStatus.innerHTML = `
                        <span class="netsuite-status-badge synced">
                            📄 Bill #${data.bill_id || data.tranId || 'Created'}
                        </span>
                    `;
                }

                window.PayoutsAgentWidget.sendMessage(`Bill created successfully for invoice ${invoiceId}! NetSuite Bill ID: ${data.bill_id || 'N/A'}`);
            } else {
                throw new Error(data.error || 'Failed to create bill');
            }
        } catch (error) {
            billBtn.disabled = false;
            billBtn.innerHTML = '📄 Create Bill in NetSuite';
            alert('Failed to create bill: ' + error.message);
        }
    };

    // Use selected/matched vendor and enable actions
    window.useMatchedVendor = function(invoiceId, vendorId, vendorName, netsuiteId) {
        // Enable sync button (or skip if already synced)
        const syncBtn = document.querySelector(`#sync-btn-${invoiceId}`);
        if (syncBtn) {
            syncBtn.dataset.vendorId = vendorId;
            syncBtn.dataset.vendorName = vendorName;
            
            if (netsuiteId) {
                syncBtn.innerHTML = '✅ Already in NetSuite';
                syncBtn.className = 'action-btn success-action';
                syncBtn.disabled = true;
                
                // Enable bill button directly
                const billBtn = document.querySelector(`#bill-btn-${invoiceId}`);
                if (billBtn) {
                    billBtn.disabled = false;
                    billBtn.dataset.netsuiteVendorId = netsuiteId;
                }
            } else {
                syncBtn.disabled = false;
            }
        }
    };

})();
