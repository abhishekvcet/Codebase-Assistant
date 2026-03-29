/**
 * CodeAssist AI — Frontend Application
 * 
 * Features:
 *   • Chat with AI via multiple LLM providers
 *   • Model selector (Auto / Local / Groq / Gemini)
 *   • Markdown rendering with syntax highlighting
 *   • localStorage-based chat history
 *   • Auto-scroll, loading animations
 *   • Responsive sidebar with history management
 */

// ── Configuration ──────────────────────────────────────────────────

const API_URL = window.location.origin;
const STORAGE_KEY = 'codeassist_chats';
const MAX_HISTORY = 50;

// ── State ──────────────────────────────────────────────────────────

let state = {
    chats: [],          // [{id, title, messages: [{role, content, model, latency, provider, fallback}]}]
    activeChatId: null,
    isLoading: false,
};

// ── DOM Elements ───────────────────────────────────────────────────

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);

const chatMessages = $('#chatMessages');
const chatContainer = $('#chatContainer');
const messageInput = $('#messageInput');
const sendBtn = $('#sendBtn');
const modelSelector = $('#modelSelector');
const modelHint = $('#modelHint');
const newChatBtn = $('#newChatBtn');
const chatHistory = $('#chatHistory');
const emptyState = $('#emptyState');
const sidebarToggle = $('#sidebarToggle');
const sidebar = $('#sidebar');
const chatTitle = $('#chatTitle');
const statusDot = $('#statusDot');
const statusText = $('#statusText');

// ── Initialization ─────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', () => {
    loadState();
    setupEventListeners();
    checkHealth();
    renderHistory();

    if (state.activeChatId) {
        renderChat();
    }

    // Configure marked
    if (window.marked) {
        marked.setOptions({
            breaks: true,
            gfm: true,
            highlight: (code, lang) => {
                if (window.hljs && lang && hljs.getLanguage(lang)) {
                    return hljs.highlight(code, { language: lang }).value;
                }
                return code;
            },
        });
    }
});

// ── Event Listeners ────────────────────────────────────────────────

function setupEventListeners() {
    // Send message
    sendBtn.addEventListener('click', sendMessage);
    messageInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendMessage();
        }
    });

    // Auto-resize textarea
    messageInput.addEventListener('input', () => {
        messageInput.style.height = 'auto';
        messageInput.style.height = Math.min(messageInput.scrollHeight, 160) + 'px';
        sendBtn.disabled = !messageInput.value.trim();
    });

    // Model selector
    modelSelector.addEventListener('change', () => {
        const hints = {
            auto: 'Auto mode — AI picks the best model for your query',
            local: 'Local mode — Using Ollama (phi3/llama3) on your machine',
            groq: 'Groq mode — Fast cloud inference for debugging',
            gemini: 'Gemini mode — Deep reasoning for complex analysis',
        };
        modelHint.textContent = hints[modelSelector.value] || '';
    });

    // New chat
    newChatBtn.addEventListener('click', createNewChat);

    // Sidebar toggle
    sidebarToggle.addEventListener('click', toggleSidebar);

    // Suggestion chips
    $$('.chip').forEach(chip => {
        chip.addEventListener('click', () => {
            messageInput.value = chip.dataset.query;
            messageInput.dispatchEvent(new Event('input'));
            sendMessage();
        });
    });

    // Theme toggle
    const themeToggle = $('#themeToggle');
    themeToggle.addEventListener('click', toggleTheme);
    loadTheme();
}

// ── Theme Management ───────────────────────────────────────────────

function toggleTheme() {
    const html = document.documentElement;
    const current = html.getAttribute('data-theme');
    const next = current === 'light' ? 'dark' : 'light';
    html.setAttribute('data-theme', next);
    localStorage.setItem('codeassist_theme', next);
    updateThemeIcon(next);
}

function loadTheme() {
    const saved = localStorage.getItem('codeassist_theme') || 'dark';
    document.documentElement.setAttribute('data-theme', saved);
    updateThemeIcon(saved);
}

function updateThemeIcon(theme) {
    const btn = $('#themeToggle');
    if (theme === 'light') {
        btn.innerHTML = `
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/>
            </svg>`;
        btn.title = 'Switch to Dark Mode';
    } else {
        btn.innerHTML = `
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <circle cx="12" cy="12" r="5"/>
                <path d="M12 1v2M12 21v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M1 12h2M21 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42"/>
            </svg>`;
        btn.title = 'Switch to Light Mode';
    }
}

// ── Chat Management ────────────────────────────────────────────────

function createNewChat() {
    const chat = {
        id: generateId(),
        title: 'New Chat',
        messages: [],
        createdAt: Date.now(),
    };

    state.chats.unshift(chat);
    state.activeChatId = chat.id;
    saveState();
    renderHistory();
    renderChat();
    messageInput.focus();
}

function getActiveChat() {
    return state.chats.find(c => c.id === state.activeChatId);
}

function switchChat(chatId) {
    state.activeChatId = chatId;
    saveState();
    renderHistory();
    renderChat();

    // Close sidebar on mobile
    if (window.innerWidth <= 768) {
        sidebar.classList.add('collapsed');
    }
}

function deleteChat(chatId) {
    state.chats = state.chats.filter(c => c.id !== chatId);
    if (state.activeChatId === chatId) {
        state.activeChatId = state.chats.length > 0 ? state.chats[0].id : null;
    }
    saveState();
    renderHistory();
    renderChat();
}

// ── Send Message ───────────────────────────────────────────────────

async function sendMessage() {
    const query = messageInput.value.trim();
    if (!query || state.isLoading) return;

    // Ensure we have an active chat
    if (!state.activeChatId) {
        createNewChat();
    }

    const chat = getActiveChat();

    // Update title from first message
    if (chat.messages.length === 0) {
        chat.title = query.slice(0, 60) + (query.length > 60 ? '…' : '');
        renderHistory();
    }

    // Add user message
    chat.messages.push({
        role: 'user',
        content: query,
        timestamp: Date.now(),
    });

    // Clear input
    messageInput.value = '';
    messageInput.style.height = 'auto';
    sendBtn.disabled = true;

    // Render user message
    renderChat();
    scrollToBottom();

    // Show loading
    state.isLoading = true;
    showTypingIndicator();

    const model = modelSelector.value;

    try {
        const response = await fetch(`${API_URL}/chat`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ query, model }),
        });

        if (!response.ok) {
            const err = await response.json().catch(() => ({ detail: 'Server error' }));
            throw new Error(err.detail || `HTTP ${response.status}`);
        }

        const data = await response.json();

        // Add assistant message
        chat.messages.push({
            role: 'assistant',
            content: data.answer,
            model: data.model_used,
            provider: data.provider,
            latency: data.latency_ms,
            fallback: data.fallback_used,
            timestamp: Date.now(),
        });

    } catch (error) {
        console.error('Chat error:', error);
        chat.messages.push({
            role: 'assistant',
            content: `**Error:** ${error.message}\n\nPlease check that the backend is running at \`${API_URL}\` and your LLM providers are configured.`,
            model: 'error',
            provider: 'system',
            latency: 0,
            fallback: false,
            timestamp: Date.now(),
        });
    }

    state.isLoading = false;
    removeTypingIndicator();
    saveState();
    renderChat();
    scrollToBottom();
}

// ── Rendering ──────────────────────────────────────────────────────

function renderChat() {
    const chat = getActiveChat();

    if (!chat || chat.messages.length === 0) {
        emptyState.style.display = 'flex';
        chatTitle.textContent = 'CodeAssist AI';
        // Remove all messages but keep empty state
        const messages = chatMessages.querySelectorAll('.message');
        messages.forEach(m => m.remove());
        return;
    }

    emptyState.style.display = 'none';
    chatTitle.textContent = chat.title;

    // Clear existing messages
    const existing = chatMessages.querySelectorAll('.message');
    existing.forEach(m => m.remove());

    // Render all messages
    chat.messages.forEach((msg) => {
        const el = createMessageElement(msg);
        chatMessages.appendChild(el);
    });

    // Highlight code blocks
    chatMessages.querySelectorAll('pre code').forEach(block => {
        if (window.hljs) hljs.highlightElement(block);
    });
}

function createMessageElement(msg) {
    const div = document.createElement('div');
    div.className = `message ${msg.role}`;

    const avatarText = msg.role === 'assistant' ? 'AI' : 'U';

    let contentHTML = '';
    if (msg.role === 'assistant') {
        contentHTML = renderMarkdown(msg.content);
    } else {
        contentHTML = escapeHTML(msg.content);
    }

    let metaHTML = '';
    if (msg.role === 'assistant' && msg.model && msg.model !== 'error') {
        metaHTML = `
            <div class="message-meta">
                <span class="model-badge">${msg.model}</span>
                <span class="latency">⏱ ${Math.round(msg.latency || 0)}ms</span>
                ${msg.fallback ? '<span class="fallback-badge">fallback</span>' : ''}
                <span>${msg.provider || ''}</span>
            </div>
        `;
    }

    div.innerHTML = `
        <div class="message-avatar">${avatarText}</div>
        <div class="message-body">
            <div class="message-content">${contentHTML}</div>
            ${metaHTML}
        </div>
    `;

    // Add copy buttons to code blocks
    setTimeout(() => {
        div.querySelectorAll('pre').forEach(pre => {
            const code = pre.querySelector('code');
            if (!code) return;

            const lang = (code.className.match(/language-(\w+)/) || [])[1] || '';
            const header = document.createElement('div');
            header.className = 'code-header';
            header.innerHTML = `
                <span>${lang}</span>
                <button class="copy-btn" onclick="copyCode(this)">Copy</button>
            `;
            pre.insertBefore(header, code);
        });
    }, 10);

    return div;
}

function renderMarkdown(text) {
    if (window.marked) {
        return marked.parse(text);
    }
    // Fallback: basic formatting
    return text
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/\n/g, '<br>')
        .replace(/`([^`]+)`/g, '<code>$1</code>')
        .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
}

function escapeHTML(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// ── Typing Indicator ───────────────────────────────────────────────

function showTypingIndicator() {
    const existing = chatMessages.querySelector('.typing-message');
    if (existing) return;

    const div = document.createElement('div');
    div.className = 'message assistant typing-message';
    div.innerHTML = `
        <div class="message-avatar">AI</div>
        <div class="message-body">
            <div class="message-content">
                <div class="typing-indicator">
                    <div class="typing-dot"></div>
                    <div class="typing-dot"></div>
                    <div class="typing-dot"></div>
                </div>
            </div>
        </div>
    `;
    chatMessages.appendChild(div);
    scrollToBottom();
}

function removeTypingIndicator() {
    const el = chatMessages.querySelector('.typing-message');
    if (el) el.remove();
}

// ── History Sidebar ────────────────────────────────────────────────

function renderHistory() {
    chatHistory.innerHTML = '';

    if (state.chats.length === 0) {
        chatHistory.innerHTML = '<div style="padding: 16px; color: var(--text-tertiary); font-size: 0.85rem; text-align: center;">No conversations yet</div>';
        return;
    }

    state.chats.forEach(chat => {
        const item = document.createElement('div');
        item.className = `history-item ${chat.id === state.activeChatId ? 'active' : ''}`;
        item.innerHTML = `
            <span class="history-item-text">${escapeHTML(chat.title)}</span>
            <button class="history-item-delete" title="Delete chat">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M18 6L6 18M6 6l12 12"/>
                </svg>
            </button>
        `;

        item.querySelector('.history-item-text').addEventListener('click', () => {
            switchChat(chat.id);
        });

        item.querySelector('.history-item-delete').addEventListener('click', (e) => {
            e.stopPropagation();
            deleteChat(chat.id);
        });

        chatHistory.appendChild(item);
    });
}

// ── Sidebar Toggle ─────────────────────────────────────────────────

function toggleSidebar() {
    sidebar.classList.toggle('collapsed');
}

// ── Copy Code ──────────────────────────────────────────────────────

window.copyCode = function(btn) {
    const pre = btn.closest('pre');
    const code = pre.querySelector('code');
    if (!code) return;

    navigator.clipboard.writeText(code.textContent).then(() => {
        btn.textContent = 'Copied!';
        setTimeout(() => { btn.textContent = 'Copy'; }, 2000);
    });
};

// ── Health Check ───────────────────────────────────────────────────

async function checkHealth() {
    try {
        const resp = await fetch(`${API_URL}/health`);
        const data = await resp.json();

        const hasProvider = data.providers.ollama === 'available'
            || data.providers.groq === 'configured'
            || data.providers.gemini === 'configured';

        statusDot.className = `status-dot ${hasProvider ? 'online' : 'offline'}`;

        const parts = [];
        if (data.providers.ollama === 'available') parts.push('Ollama ✓');
        if (data.providers.groq === 'configured') parts.push('Groq ✓');
        if (data.providers.gemini === 'configured') parts.push('Gemini ✓');
        statusText.textContent = parts.length > 0 ? parts.join(' · ') : 'No providers';
    } catch {
        statusDot.className = 'status-dot offline';
        statusText.textContent = 'Backend offline';
    }
}

// ── Scroll ─────────────────────────────────────────────────────────

function scrollToBottom() {
    requestAnimationFrame(() => {
        chatContainer.scrollTop = chatContainer.scrollHeight;
    });
}

// ── State Persistence ──────────────────────────────────────────────

function saveState() {
    try {
        const serializable = {
            chats: state.chats.slice(0, MAX_HISTORY),
            activeChatId: state.activeChatId,
        };
        localStorage.setItem(STORAGE_KEY, JSON.stringify(serializable));
    } catch (e) {
        console.warn('Failed to save state:', e);
    }
}

function loadState() {
    try {
        const saved = localStorage.getItem(STORAGE_KEY);
        if (saved) {
            const parsed = JSON.parse(saved);
            state.chats = parsed.chats || [];
            state.activeChatId = parsed.activeChatId || null;
        }
    } catch (e) {
        console.warn('Failed to load state:', e);
    }
}

// ── Utilities ──────────────────────────────────────────────────────

function generateId() {
    return Date.now().toString(36) + Math.random().toString(36).slice(2, 8);
}
