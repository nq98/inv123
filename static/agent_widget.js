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
        'match_vendor_to_database': '🔗',
        'run_bigquery': '🗄️',
        'get_subscription_summary': '📊',
        'search_database_first': '🔍',
        'check_gmail_status': '📧',
        'get_top_vendors_by_spend': '💰',
        'process_uploaded_invoice': '📄',
        'import_vendor_csv': '📋',
        'pull_netsuite_vendors': '🔄'
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
        'pull_netsuite_vendors': 'Synced NetSuite'
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
                <button class="payouts-chat-close" aria-label="Close chat">
                    <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                        <path d="M1 1L13 13M1 13L13 1" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
                    </svg>
                </button>
            </div>
            <div class="payouts-chat-messages" id="payouts-messages-container">
                <div class="payouts-welcome-message">
                    <h3>Welcome to Payouts AI</h3>
                    <p>I can help you search invoices, manage vendors, check NetSuite bills, and analyze subscriptions. You can also upload PDF invoices or CSV files.</p>
                    <div class="payouts-quick-actions">
                        <button class="payouts-quick-action" data-message="Show me my SaaS subscription summary">📊 Subscription Summary</button>
                        <button class="payouts-quick-action" data-message="Search for recent Gmail invoices">📧 Search Gmail</button>
                        <button class="payouts-quick-action" data-message="Find vendors with overdue bills">💰 Overdue Bills</button>
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
        const actionButtonPattern = /<a\s+href="([^"]+)"[^>]*class="chat-action-btn"[^>]*>([^<]+)<\/a>/g;
        const preservedButtons = [];
        let buttonIndex = 0;
        
        let processed = content.replace(actionButtonPattern, (match, url, text) => {
            const placeholder = `__ACTION_BTN_${buttonIndex}__`;
            preservedButtons.push({ placeholder, url, text });
            buttonIndex++;
            return placeholder;
        });

        const tablePattern = /<table[^>]*>[\s\S]*?<\/table>/gi;
        const preservedTables = [];
        let tableIndex = 0;

        processed = processed.replace(tablePattern, (match) => {
            const placeholder = `__TABLE_${tableIndex}__`;
            let styledTable = match
                .replace(/<table[^>]*>/gi, '<div class="payouts-table-wrapper"><table class="payouts-data-table">')
                .replace(/<\/table>/gi, '</table></div>');
            preservedTables.push({ placeholder, html: styledTable });
            tableIndex++;
            return placeholder;
        });
        
        let formatted = processed
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;');
        
        formatted = formatted.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
        formatted = formatted.replace(/\n/g, '<br>');
        
        preservedButtons.forEach(({ placeholder, url, text }) => {
            const buttonHtml = `<a href="${url}" class="chat-action-btn" onclick="event.stopPropagation();">${text}</a>`;
            formatted = formatted.replace(placeholder, buttonHtml);
        });

        preservedTables.forEach(({ placeholder, html }) => {
            formatted = formatted.replace(placeholder, html);
        });
        
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

    function init() {
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', () => {
                injectStyles();
                createWidget();
            });
        } else {
            injectStyles();
            createWidget();
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

})();
