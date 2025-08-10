class RealtimeMessaging {
    constructor(conversationId, userId, otherUserId) {
        this.conversationId = conversationId;
        this.userId = userId;
        this.otherUserId = otherUserId;
        this.websocket = null;
        this.typingTimeout = null;
        this.reconnectAttempts = 0;
        this.maxReconnectAttempts = 5;
        this.reconnectDelay = 1000;
        
        this.init();
    }

    init() {
        this.connectWebSocket();
        this.setupEventListeners();
    }

    connectWebSocket() {
        try {
            // Connect to FastAPI WebSocket server
            const wsUrl = `ws://localhost:8000/ws/${this.conversationId}/${this.userId}`;
            this.websocket = new WebSocket(wsUrl);
            
            this.websocket.onopen = () => {
                console.log('WebSocket connected to FastAPI server');
                this.reconnectAttempts = 0;
                this.showConnectionStatus('connected');
            };
            
            this.websocket.onmessage = (event) => {
                this.handleWebSocketMessage(event.data);
            };
            
            this.websocket.onclose = (event) => {
                console.log('WebSocket disconnected:', event.code, event.reason);
                this.showConnectionStatus('disconnected');
                this.handleReconnect();
            };
            
            this.websocket.onerror = (error) => {
                console.error('WebSocket error:', error);
                this.showConnectionStatus('error');
            };
            
        } catch (error) {
            console.error('Failed to connect WebSocket:', error);
            this.showConnectionStatus('error');
        }
    }

    setupEventListeners() {
        const messageInput = document.getElementById('message-input');
        const messageForm = document.getElementById('message-form');
        
        if (messageInput) {
            // Typing indicator
            messageInput.addEventListener('input', () => {
                this.sendTypingIndicator(true);
                this.resetTypingTimeout();
            });
            
            // Stop typing indicator
            messageInput.addEventListener('blur', () => {
                this.sendTypingIndicator(false);
            });
        }
        
        if (messageForm) {
            messageForm.addEventListener('submit', (e) => {
                e.preventDefault();
                this.sendMessage();
            });
        }
    }

    handleWebSocketMessage(data) {
        try {
            const message = JSON.parse(data);
            
            switch (message.type) {
                case 'new_message':
                    this.handleNewMessage(message);
                    break;
                case 'typing_indicator':
                    this.handleTypingIndicator(message);
                    break;
                default:
                    console.log('Unknown message type:', message.type);
            }
        } catch (error) {
            console.error('Error parsing WebSocket message:', error);
        }
    }

    handleNewMessage(message) {
        // Don't show our own messages twice
        if (message.sender_id === this.userId) {
            return;
        }
        
        // Add message to UI
        this.addMessageToUI(message, false);
        
        // Scroll to bottom
        this.scrollToBottom();
        
        // Play notification sound (optional)
        this.playNotificationSound();
        
        // Update conversation list if it exists
        this.updateConversationList(message);
    }

    handleTypingIndicator(message) {
        // Don't show our own typing indicator
        if (message.user_id === this.userId) {
            return;
        }
        
        if (message.is_typing) {
            this.showTypingIndicator(message.user_id);
        } else {
            this.hideTypingIndicator(message.user_id);
        }
    }

    sendMessage() {
        const messageInput = document.getElementById('message-input');
        const content = messageInput.value.trim();
        
        if (!content) return;
        
        // Add message to UI immediately (optimistic update)
        const tempMessage = {
            sender_id: this.userId,
            content: content,
            sent_at: new Date().toISOString(),
            message_id: 'temp_' + Date.now()
        };
        
        this.addMessageToUI(tempMessage, true);
        
        // Clear input
        messageInput.value = '';
        
        // Scroll to bottom
        this.scrollToBottom();
        
        // Send via WebSocket
        if (this.websocket && this.websocket.readyState === WebSocket.OPEN) {
            this.websocket.send(JSON.stringify({
                type: 'message',
                content: content
            }));
        } else {
            // Fallback to HTTP if WebSocket is not available
            this.sendMessageViaHTTP(content);
        }
        
        // Stop typing indicator
        this.sendTypingIndicator(false);
    }

    sendTypingIndicator(isTyping) {
        if (this.websocket && this.websocket.readyState === WebSocket.OPEN) {
            this.websocket.send(JSON.stringify({
                type: isTyping ? 'typing' : 'typing_stop',
                is_typing: isTyping
            }));
        }
    }

    resetTypingTimeout() {
        if (this.typingTimeout) {
            clearTimeout(this.typingTimeout);
        }
        
        this.typingTimeout = setTimeout(() => {
            this.sendTypingIndicator(false);
        }, 1000);
    }

    addMessageToUI(message, isOwnMessage) {
        const messagesContainer = document.getElementById('messages-container');
        if (!messagesContainer) return;
        
        const messageDiv = document.createElement('div');
        messageDiv.className = `flex ${isOwnMessage ? 'justify-end' : 'justify-start'}`;
        messageDiv.id = `message-${message.message_id}`;
        
        const messageBubble = document.createElement('div');
        messageBubble.className = `max-w-[70%] ${isOwnMessage ? 'bg-primary text-white' : 'bg-gray-100 dark:bg-gray-700 text-gray-900 dark:text-white'} rounded-lg px-4 py-2 shadow-sm`;
        
        const messageContent = document.createElement('p');
        messageContent.textContent = message.content;
        messageBubble.appendChild(messageContent);
        
        const messageTime = document.createElement('p');
        messageTime.className = `text-xs ${isOwnMessage ? 'text-white/80' : 'text-gray-500 dark:text-gray-400'} mt-1`;
        
        const timestamp = new Date(message.sent_at);
        messageTime.textContent = timestamp.toLocaleTimeString('en-US', { 
            hour: 'numeric', 
            minute: '2-digit' 
        });
        messageBubble.appendChild(messageTime);
        
        messageDiv.appendChild(messageBubble);
        messagesContainer.appendChild(messageDiv);
        
        // If this is a temporary message, we can remove the ID later when confirmed
        if (message.message_id.startsWith('temp_')) {
            messageDiv.dataset.temp = 'true';
        }
    }

    showTypingIndicator(userId) {
        // Remove existing typing indicator
        this.hideTypingIndicator(userId);
        
        const messagesContainer = document.getElementById('messages-container');
        if (!messagesContainer) return;
        
        const typingDiv = document.createElement('div');
        typingDiv.id = `typing-${userId}`;
        typingDiv.className = 'flex items-center space-x-2 text-sm text-gray-500 dark:text-gray-400 animate-pulse';
        
        // Get username for typing indicator
        const otherUserElement = document.querySelector('[data-other-user-id]');
        const otherUsername = otherUserElement ? otherUserElement.dataset.otherUsername : 'Someone';
        
        typingDiv.innerHTML = `
            <span>${otherUsername} is typing</span>
            <div class="flex space-x-1">
                <div class="w-1.5 h-1.5 bg-gray-400 dark:bg-gray-500 rounded-full animate-bounce"></div>
                <div class="w-1.5 h-1.5 bg-gray-400 dark:bg-gray-500 rounded-full animate-bounce" style="animation-delay: 0.1s"></div>
                <div class="w-1.5 h-1.5 bg-gray-400 dark:bg-gray-500 rounded-full animate-bounce" style="animation-delay: 0.2s"></div>
            </div>
        `;
        
        messagesContainer.appendChild(typingDiv);
        this.scrollToBottom();
    }

    hideTypingIndicator(userId) {
        const typingIndicator = document.getElementById(`typing-${userId}`);
        if (typingIndicator) {
            typingIndicator.remove();
        }
    }

    scrollToBottom() {
        const messagesContainer = document.getElementById('messages-container');
        if (messagesContainer) {
            messagesContainer.scrollTop = messagesContainer.scrollHeight;
        }
    }

    showConnectionStatus(status) {
        const statusElement = document.getElementById('connection-status');
        if (!statusElement) return;
        
        const statusMap = {
            connected: { text: 'Connected', class: 'text-green-500' },
            disconnected: { text: 'Disconnected', class: 'text-red-500' },
            error: { text: 'Connection Error', class: 'text-red-500' },
            connecting: { text: 'Connecting...', class: 'text-yellow-500' }
        };
        
        const statusInfo = statusMap[status] || statusMap.error;
        statusElement.textContent = statusInfo.text;
        statusElement.className = `text-sm ${statusInfo.class}`;
    }

    handleReconnect() {
        if (this.reconnectAttempts < this.maxReconnectAttempts) {
            this.reconnectAttempts++;
            this.showConnectionStatus('connecting');
            
            setTimeout(() => {
                console.log(`Attempting to reconnect... (${this.reconnectAttempts}/${this.maxReconnectAttempts})`);
                this.connectWebSocket();
            }, this.reconnectDelay * this.reconnectAttempts);
        } else {
            console.error('Max reconnection attempts reached');
            this.showConnectionStatus('error');
        }
    }

    sendMessageViaHTTP(content) {
        // Fallback to HTTP POST if WebSocket is not available
        const formData = new FormData();
        formData.append('listing_id', document.querySelector('input[name="listing_id"]')?.value || '');
        formData.append('recipient_id', document.querySelector('input[name="recipient_id"]')?.value || '');
        formData.append('content', content);
        
        fetch('/send_message', {
            method: 'POST',
            body: formData
        })
        .then(response => response.json())
        .then(data => {
            if (data.status === 'success') {
                console.log('Message sent via HTTP fallback');
            }
        })
        .catch(error => {
            console.error('Error sending message via HTTP:', error);
        });
    }

    updateConversationList(message) {
        // Update the conversation list in the sidebar if it exists
        const conversationElement = document.querySelector(`[data-conversation-id="${this.conversationId}"]`);
        if (conversationElement) {
            const lastMessageElement = conversationElement.querySelector('.last-message');
            if (lastMessageElement) {
                lastMessageElement.textContent = message.content;
            }
            
            const timestampElement = conversationElement.querySelector('.last-timestamp');
            if (timestampElement) {
                const timestamp = new Date(message.sent_at);
                timestampElement.textContent = timestamp.toLocaleTimeString('en-US', { 
                    hour: 'numeric', 
                    minute: '2-digit' 
                });
            }
        }
    }

    playNotificationSound() {
        // Optional: Play a notification sound for new messages
        try {
            const audio = new Audio('/static/assets/sounds/notification.mp3');
            audio.volume = 0.3;
            audio.play().catch(e => console.log('Could not play notification sound'));
        } catch (error) {
            // Sound file not available, ignore
        }
    }

    disconnect() {
        if (this.websocket) {
            this.websocket.close();
        }
        if (this.typingTimeout) {
            clearTimeout(this.typingTimeout);
        }
    }
}

// Export for use in other scripts
if (typeof module !== 'undefined' && module.exports) {
    module.exports = RealtimeMessaging;
}
