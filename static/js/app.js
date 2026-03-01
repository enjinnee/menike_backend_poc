// ---------------------------------------------------------------------------
// JWT-aware fetch wrapper
// ---------------------------------------------------------------------------
function authFetch(url, options = {}) {
    const token = localStorage.getItem('access_token');
    if (!token) {
        window.location.href = '/auth/login';
        return Promise.reject(new Error('No token'));
    }

    options.headers = options.headers || {};
    options.headers['Authorization'] = `Bearer ${token}`;

    return fetch(url, options).then(response => {
        if (response.status === 401) {
            localStorage.removeItem('access_token');
            window.location.href = '/auth/login';
            throw new Error('Authentication required');
        }
        return response;
    });
}

// ---------------------------------------------------------------------------
// Global state
// ---------------------------------------------------------------------------
let currentSessionId = null;
let isGenerating = false;
let hasGeneratedItinerary = false;
let pendingRegenerate = false;
let videoModeEnabled = false;
let avatarManager = null;
let voiceInputManager = null;
let heygenConfigured = false;
let isProcessingVoice = false;
let currentItinerary = null;
let currentVideoUrl = null;  // URL of the video for the active session

// ---------------------------------------------------------------------------
// DOM Elements
// ---------------------------------------------------------------------------
const messageInput = document.getElementById('messageInput');
const sendBtn = document.getElementById('sendBtn');
const chatMessages = document.getElementById('chatMessages');
const newChatBtn = document.getElementById('newChatBtn');
const itineraryPanel = document.getElementById('itineraryPanel');
const itineraryContent = document.getElementById('itineraryContent');
const closePanel = document.getElementById('closePanel');
const loadingSpinner = document.getElementById('loadingSpinner');
const headerStatus = document.getElementById('headerStatus');
const inputContainer = document.getElementById('inputContainer');
const logoutBtn = document.getElementById('logoutBtn');
const itineraryUpdatingOverlay = document.getElementById('itineraryUpdatingOverlay');

// Mobile elements
const sidebarToggle = document.getElementById('sidebarToggle');
const sidebarOverlay = document.getElementById('sidebarOverlay');
const sidebar = document.querySelector('.sidebar');
const viewItineraryBtn = document.getElementById('viewItineraryBtn');
const backToChat = document.getElementById('backToChat');

// Video mode elements
const videoModeToggle = document.getElementById('videoModeToggle');
const avatarContainer = document.getElementById('avatarContainer');
const avatarVideo = document.getElementById('avatarVideo');
const avatarStatus = document.getElementById('avatarStatus');
const voiceInputContainer = document.getElementById('voiceInputContainer');
const voiceButton = document.getElementById('voiceButton');
const voiceStatus = document.getElementById('voiceStatus');
const interimTranscript = document.getElementById('interimTranscript');
const exitVideoMode = document.getElementById('exitVideoMode');

// ---------------------------------------------------------------------------
// Initialize
// ---------------------------------------------------------------------------
const GREETING_TEXT =
    "Hello! 👋 I'm so excited to meet you! I'm Manike, and I absolutely LOVE helping people " +
    "discover amazing destinations and create unforgettable adventures! ✨\n\n" +
    "Let's get started! First things first - what's your name? 😊";

document.addEventListener('DOMContentLoaded', () => {
    if (!localStorage.getItem('access_token')) {
        window.location.href = '/auth/login';
        return;
    }
    // Show greeting locally — no DB session created until the user sends their first message.
    addMessageToChat('assistant', GREETING_TEXT);
    updateHeaderStatus('Ready to help');
    setupEventListeners();
    checkHeygenConfig();
    loadAndRenderSessions();
});

function initializeSession() {
    return authFetch('/api/session/new', { method: 'POST' })
        .then(async response => {
            const data = await response.json();
            if (!response.ok) {
                const msg = data?.detail || `Server error ${response.status}`;
                throw new Error(msg);
            }
            return data;
        })
        .then(data => {
            currentSessionId = data.session_id;
            loadAndRenderSessions();
            return data.session_id;
        });
}

function setupEventListeners() {
    sendBtn.addEventListener('click', sendMessage);
    messageInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendMessage();
        }
    });
    messageInput.addEventListener('input', () => {
        sendBtn.disabled = !messageInput.value.trim();
    });

    newChatBtn.addEventListener('click', startNewChat);
    closePanel.addEventListener('click', closeItineraryPanel);

    logoutBtn.addEventListener('click', () => {
        localStorage.removeItem('access_token');
        window.location.href = '/auth/login';
    });

    if (videoModeToggle) videoModeToggle.addEventListener('click', toggleVideoMode);
    if (voiceButton) voiceButton.addEventListener('click', handleVoiceButtonClick);
    if (exitVideoMode) exitVideoMode.addEventListener('click', disableVideoMode);

    // Resume-session modal
    const closeResumeBtn = document.getElementById('closeResumeModal');
    if (closeResumeBtn) closeResumeBtn.addEventListener('click', closeResumeModal);
    const resumeBackdrop = document.getElementById('resumeModalBackdrop');
    if (resumeBackdrop) resumeBackdrop.addEventListener('click', closeResumeModal);
    const resumeConfirmBtn = document.getElementById('resumeConfirmBtn');
    if (resumeConfirmBtn) resumeConfirmBtn.addEventListener('click', confirmResumeSession);
    const resumeCancelBtn = document.getElementById('resumeCancelBtn');
    if (resumeCancelBtn) resumeCancelBtn.addEventListener('click', closeResumeModal);

    // Delete-session modal
    const closeDeleteBtn = document.getElementById('closeDeleteModal');
    if (closeDeleteBtn) closeDeleteBtn.addEventListener('click', closeDeleteModal);
    const deleteBackdrop = document.getElementById('deleteModalBackdrop');
    if (deleteBackdrop) deleteBackdrop.addEventListener('click', closeDeleteModal);
    const deleteCancelBtn = document.getElementById('deleteCancelBtn');
    if (deleteCancelBtn) deleteCancelBtn.addEventListener('click', closeDeleteModal);
    const deleteConfirmBtn = document.getElementById('deleteConfirmBtn');
    if (deleteConfirmBtn) deleteConfirmBtn.addEventListener('click', confirmDeleteSession);

    // Mobile sidebar toggle
    if (sidebarToggle) {
        sidebarToggle.addEventListener('click', toggleSidebar);
    }
    if (sidebarOverlay) {
        sidebarOverlay.addEventListener('click', closeSidebar);
    }

    // Mobile itinerary view button
    if (viewItineraryBtn) {
        viewItineraryBtn.addEventListener('click', openItineraryMobile);
    }
    if (backToChat) {
        backToChat.addEventListener('click', closeItineraryPanel);
    }

    // Handle resize: clean up mobile states when switching to desktop
    window.addEventListener('resize', () => {
        if (!isMobile()) {
            closeSidebar();
            itineraryPanel.classList.remove('mobile-open');
            if (viewItineraryBtn) {
                viewItineraryBtn.classList.remove('visible');
                viewItineraryBtn.style.display = 'none';
            }
        } else if (hasGeneratedItinerary && viewItineraryBtn) {
            viewItineraryBtn.style.display = '';
            viewItineraryBtn.classList.add('visible');
        }
    });

    sendBtn.disabled = true;
    messageInput.focus();
}

// ---------------------------------------------------------------------------
// HeyGen config check
// ---------------------------------------------------------------------------
async function checkHeygenConfig() {
    try {
        const response = await authFetch('/api/heygen/config');
        const data = await response.json();
        heygenConfigured = data.configured;
        if (heygenConfigured && videoModeToggle) {
            videoModeToggle.style.display = 'inline-flex';
        }
    } catch (error) {
        console.log('HeyGen not configured');
    }
}

// ---------------------------------------------------------------------------
// Video / Avatar mode
// ---------------------------------------------------------------------------
async function toggleVideoMode() {
    if (videoModeEnabled) disableVideoMode();
    else await enableVideoMode();
}

async function enableVideoMode() {
    if (!currentSessionId) { updateHeaderStatus('Please wait for session to initialize'); return; }

    videoModeToggle.disabled = true;
    videoModeToggle.innerHTML = '<span class="video-icon">...</span> Loading...';
    updateHeaderStatus('Initializing video mode...');

    try {
        voiceInputManager = new VoiceInputManager({
            continuousMode: true,
            autoRestart: true,
            onTranscript: handleVoiceTranscript,
            onInterimTranscript: (text) => { if (interimTranscript) interimTranscript.textContent = text; },
            onListeningStart: () => { if (voiceButton) voiceButton.classList.add('listening'); if (voiceStatus) voiceStatus.textContent = 'Listening...'; },
            onListeningEnd: () => { if (voiceButton) voiceButton.classList.remove('listening'); if (interimTranscript) interimTranscript.textContent = ''; },
            onError: (error) => {
                console.error('Voice input error:', error);
                if (error === 'microphone-denied') { updateHeaderStatus('Microphone access required for video mode.'); disableVideoMode(); }
            }
        });

        const voiceInitialized = await voiceInputManager.initialize();
        if (!voiceInitialized) throw new Error('Failed to initialize voice input');

        avatarManager = new HeyGenAvatarManager({
            videoElement: avatarVideo,
            onReady: () => {
                console.log('Avatar ready');
                avatarStatus.textContent = 'Ready';
                updateHeaderStatus('Video mode active - Manike is ready to help');
                const greeting = "Hello! I'm Manike, your AI travel planning assistant. I'm so excited to help you plan your perfect trip! What's your name?";
                addMessageToChat('assistant', greeting);
                avatarManager.speak(greeting);
            },
            onTalkingStart: () => { avatarStatus.textContent = 'Manike is speaking...'; if (voiceStatus) voiceStatus.textContent = 'Avatar speaking...'; if (voiceInputManager) voiceInputManager.pause(); },
            onTalkingEnd: () => { avatarStatus.textContent = 'Listening to you...'; if (voiceStatus) voiceStatus.textContent = 'Speak now...'; if (voiceInputManager && videoModeEnabled) voiceInputManager.resume(); },
            onError: (error) => { console.error('Avatar error:', error); updateHeaderStatus('Video avatar unavailable. Please try again.'); disableVideoMode(); },
            onDisconnect: () => { console.log('Avatar disconnected'); disableVideoMode(); }
        });

        avatarStatus.textContent = 'Connecting to avatar...';
        const avatarInitialized = await avatarManager.initialize(currentSessionId);
        if (!avatarInitialized) throw new Error('Failed to initialize avatar');

        videoModeEnabled = true;
        showVideoModeUI();
        videoModeToggle.innerHTML = '<span class="video-icon">💬</span> Text Mode';
        videoModeToggle.disabled = false;
    } catch (error) {
        console.error('Failed to enable video mode:', error);
        updateHeaderStatus('Video mode unavailable. Please try again or contact the administrator.');
        disableVideoMode();
    }
}

function disableVideoMode() {
    if (avatarManager) { avatarManager.stop(); avatarManager = null; }
    if (voiceInputManager) { voiceInputManager.destroy(); voiceInputManager = null; }
    videoModeEnabled = false;
    hideVideoModeUI();
    if (videoModeToggle) { videoModeToggle.innerHTML = '<span class="video-icon">🎥</span> Video Mode'; videoModeToggle.disabled = false; }
    updateHeaderStatus('Ready to help');
}

function showVideoModeUI() {
    if (avatarContainer) avatarContainer.style.display = 'block';
    if (inputContainer) inputContainer.style.display = 'none';
    if (voiceInputContainer) voiceInputContainer.style.display = 'flex';
}

function hideVideoModeUI() {
    if (avatarContainer) avatarContainer.style.display = 'none';
    if (inputContainer) inputContainer.style.display = 'flex';
    if (voiceInputContainer) voiceInputContainer.style.display = 'none';
}

function handleVoiceButtonClick() {
    if (!voiceInputManager) return;
    if (avatarManager && avatarManager.isAvatarTalking()) { avatarManager.interrupt(); return; }
    if (voiceInputManager.isCurrentlyPaused()) {
        voiceInputManager.resume();
        if (voiceStatus) voiceStatus.textContent = 'Listening...';
    } else {
        voiceInputManager.pause();
        if (voiceStatus) voiceStatus.textContent = 'Muted - tap to unmute';
    }
}

async function handleVoiceTranscript(transcript) {
    if (!transcript || !transcript.trim() || isProcessingVoice) return;
    const message = transcript.trim();
    if (message.length < 2) return;

    isProcessingVoice = true;
    if (voiceInputManager) voiceInputManager.pause();
    addMessageToChat('user', message);
    showTypingIndicator();
    if (avatarStatus) avatarStatus.textContent = 'Processing...';
    if (voiceStatus) voiceStatus.textContent = 'Processing your response...';

    try {
        if (!currentSessionId) await initializeSession();
        const response = await authFetch('/api/chat/voice', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ session_id: currentSessionId, transcript: message })
        });
        const data = await response.json();

        removeTypingIndicator();

        if (data.error) {
            addMessageToChat('assistant', `Error: ${data.error}`);
            if (voiceInputManager && videoModeEnabled) voiceInputManager.resume();
            return;
        }

        addMessageToChat('assistant', data.response);

        if (avatarManager && avatarManager.isAvatarActive()) {
            await avatarManager.speak(data.response);
        } else {
            if (voiceInputManager && videoModeEnabled) voiceInputManager.resume();
        }

        // Handle auto-generation
        handleAutoGenerate(data);
    } catch (error) {
        removeTypingIndicator();
        console.error('Voice processing error:', error);
        addMessageToChat('assistant', 'Sorry, there was an error. Please try again.');
        if (voiceInputManager && videoModeEnabled) voiceInputManager.resume();
    } finally {
        isProcessingVoice = false;
    }
}

// ---------------------------------------------------------------------------
// Text chat
// ---------------------------------------------------------------------------
function sendMessage() {
    const message = messageInput.value.trim();
    if (!message) return;

    messageInput.disabled = true;
    sendBtn.disabled = true;
    addMessageToChat('user', message);
    messageInput.value = '';
    showTypingIndicator();

    // If no session exists yet, create one before sending the first message.
    const sessionReady = currentSessionId
        ? Promise.resolve(currentSessionId)
        : initializeSession();

    sessionReady
        .then(sessionId => authFetch('/api/chat/send', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ session_id: sessionId, message: message })
        }))
    .then(async response => {
        const data = await response.json();
        if (!response.ok) throw new Error(`http_${response.status}`);
        return data;
    })
    .then(data => {
        removeTypingIndicator();
        if (data.error) {
            addMessageToChat('assistant', 'Sorry, something went wrong. Please try again.');
        } else {
            addMessageToChat('assistant', data.response);
            // Handle auto-generation for both first-time and updates
            handleAutoGenerate(data);
        }
    })
    .catch(error => {
        removeTypingIndicator();
        console.error('Send message error:', error);
        addMessageToChat('assistant', 'Sorry, something went wrong. Please try again.');
    })
    .finally(() => {
        messageInput.disabled = false;
        sendBtn.disabled = false;
        messageInput.focus();
    });
}

// ---------------------------------------------------------------------------
// Auto-generation logic
// ---------------------------------------------------------------------------
function handleAutoGenerate(data) {
    if (data.requirements_complete && !hasGeneratedItinerary && !isGenerating) {
        // First-time auto-generation when all requirements are collected
        autoGenerateItinerary();
    }
    // After the first generation, do NOT auto-regenerate on field changes.
    // The user reviews the itinerary and must explicitly accept or request
    // modifications — the next generation is triggered by a new chat session
    // or a deliberate user action.
}

function autoGenerateItinerary() {
    generateItinerary();
}

function autoRegenerateItinerary() {
    if (itineraryUpdatingOverlay) {
        itineraryUpdatingOverlay.style.display = 'flex';
    }
    updateHeaderStatus('Updating your itinerary...');
    generateItinerary();
}

// ---------------------------------------------------------------------------
// Typing indicator
// ---------------------------------------------------------------------------
function showTypingIndicator() {
    const messageDiv = document.createElement('div');
    messageDiv.className = 'message assistant-message typing-indicator';
    messageDiv.id = 'typingIndicator';
    messageDiv.innerHTML = `
        <div class="message-avatar">🤖</div>
        <div class="message-content">
            <span class="dot"></span><span class="dot"></span><span class="dot"></span>
        </div>`;
    chatMessages.appendChild(messageDiv);
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

function removeTypingIndicator() {
    const indicator = document.getElementById('typingIndicator');
    if (indicator) indicator.remove();
}

// ---------------------------------------------------------------------------
// Chat UI helpers
// ---------------------------------------------------------------------------
function addMessageToChat(role, content) {
    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${role}-message`;

    const avatar = role === 'user' ? '👤' : '🤖';
    const messageContent = document.createElement('div');
    messageContent.className = 'message-content';

    const contentDiv = document.createElement('div');
    contentDiv.innerHTML = parseMessageContent(content);
    messageContent.appendChild(contentDiv);

    messageDiv.innerHTML = `<div class="message-avatar">${avatar}</div>`;
    messageDiv.appendChild(messageContent);
    chatMessages.appendChild(messageDiv);
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

function parseMessageContent(content) {
    let html = content
        .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
        .replace(/__(.*?)__/g, '<strong>$1</strong>')
        .replace(/\*(.*?)\*/g, '<em>$1</em>')
        .replace(/_(.+?)_/g, '<em>$1</em>');

    html = html.replace(/(https?:\/\/[^\s]+)/g, '<a href="$1" target="_blank">$1</a>');
    html = html.replace(/\n/g, '<br>');
    return html;
}

function generateItinerary() {
    const isRegeneration = hasGeneratedItinerary;
    isGenerating = true;

    if (!isRegeneration) {
        loadingSpinner.style.display = 'flex';
        messageInput.disabled = true;
        sendBtn.disabled = true;
    }

    updateHeaderStatus(isRegeneration
        ? 'Updating your itinerary...'
        : 'Generating your itinerary with AI + Milvus matching...');

    authFetch('/itinerary/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: currentSessionId })
    })
    .then(response => {
        if (!response.ok) {
            return response.json().then(err => { throw new Error(err.detail || `Server error ${response.status}`); });
        }
        return response.json();
    })
    .then(data => {
        {
            currentItinerary = data;
            const itineraryToShow = data.rich_itinerary || data;
            displayItinerary(itineraryToShow, data);
            updateHeaderStatus('Itinerary generated successfully!');
            if (!hasGeneratedItinerary) {
                hasGeneratedItinerary = true;
                const panelHint = isMobile()
                    ? 'tap the "View Itinerary" button to see it'
                    : 'view it in the right panel';
                addMessageToChat('assistant', `✅ Your itinerary is ready! You can ${panelHint}. Images and cinematic clips have been matched from the media library.`);
            } else {
                const updateHint = isMobile()
                    ? 'tap "View Itinerary" to see the latest version'
                    : 'check the right panel for the latest version';
                addMessageToChat('assistant', `✅ Your itinerary has been updated — ${updateHint}.`);
            }

            if (data.id) {
                // Remove any existing compile button before adding a fresh one
                const existing = document.getElementById('compileVideoMessage');
                if (existing) existing.remove();
                addCompileVideoButton(data.id);
            }
        }
    })
    .catch(error => {
        console.error('Itinerary generation error:', error);
        addMessageToChat('assistant', '⚠️ Sorry, something went wrong generating your itinerary. Please try again.');
        updateHeaderStatus('Generation failed. Please try again.');
    })
    .finally(() => {
        isGenerating = false;
        loadingSpinner.style.display = 'none';
        if (itineraryUpdatingOverlay) {
            itineraryUpdatingOverlay.style.display = 'none';
        }
        messageInput.disabled = false;
        sendBtn.disabled = false;
        messageInput.focus();

        // If another change came in while we were generating, regenerate again
        pendingRegenerate = false;
    });
}

function displayItinerary(itinerary, rawData) {
    itineraryPanel.style.display = 'block';
    itineraryContent.innerHTML = '';

    // Trip header
    const headerSection = document.createElement('div');
    headerSection.className = 'itinerary-section';
    headerSection.innerHTML = `
        <h4>Trip Details</h4>
        <p><strong>Destination:</strong> ${itinerary.destination || rawData.destination || 'N/A'}</p>
        <p><strong>Duration:</strong> ${itinerary.duration_days || rawData.days || 'N/A'} days</p>
        <p><strong>Dates:</strong> ${itinerary.start_date || 'N/A'} to ${itinerary.end_date || 'N/A'}</p>
        ${itinerary.budget ? `<p><strong>Budget:</strong> $${itinerary.budget} ${itinerary.currency || 'USD'}</p>` : ''}
        <p><strong>DB ID:</strong> <small>${rawData.id || 'N/A'}</small></p>
    `;
    itineraryContent.appendChild(headerSection);

    // Day-by-day schedule
    const days = itinerary.days || [];
    if (days.length > 0) {
        const daysSection = document.createElement('div');
        daysSection.className = 'itinerary-section';
        daysSection.innerHTML = '<h4>Daily Schedule</h4>';

        days.forEach(day => {
            const dayDiv = document.createElement('div');
            dayDiv.className = 'day-itinerary';
            let dayHtml = `<h5>Day ${day.day} — ${day.date}</h5>`;

            if (day.activities && day.activities.length > 0) {
                dayHtml += '<strong>Activities:</strong>';
                day.activities.forEach(act => {
                    const mediaLine = act.image_url
                        ? `<img src="${act.image_url}" alt="${act.title}" style="max-width:100%;border-radius:6px;margin:4px 0;">`
                        : '';
                    const clipLine = '';
                    dayHtml += `<div class="day-item">
                        <strong>• ${act.title}</strong><br>
                        <small>${act.location || ''}</small>
                        ${mediaLine}${clipLine}
                    </div>`;
                });
            }

            if (day.stays && day.stays.length > 0) {
                dayHtml += '<strong>Stays:</strong>';
                day.stays.forEach(stay => {
                    dayHtml += `<div class="day-item">• ${stay.name} (${stay.location})</div>`;
                });
            }

            if (day.rides && day.rides.length > 0) {
                dayHtml += '<strong>Transportation:</strong>';
                day.rides.forEach(ride => {
                    dayHtml += `<div class="day-item">• ${ride.transportation_type}: ${ride.from_location} → ${ride.to_location}</div>`;
                });
            }

            dayDiv.innerHTML = dayHtml;
            daysSection.appendChild(dayDiv);
        });

        itineraryContent.appendChild(daysSection);
    }

    // Fallback: show flat activities list if no rich_itinerary days
    if (days.length === 0 && rawData.activities && rawData.activities.length > 0) {
        const actSection = document.createElement('div');
        actSection.className = 'itinerary-section';
        actSection.innerHTML = '<h4>Activities</h4>';
        rawData.activities.forEach(act => {
            const div = document.createElement('div');
            div.className = 'day-item';
            div.innerHTML = `<strong>Day ${act.day}: ${act.activity_name}</strong> — ${act.location || ''}
                ${act.image_url ? `<br><img src="${act.image_url}" style="max-width:100%;border-radius:6px;margin:4px 0;">` : ''}
                `;
            actSection.appendChild(div);
        });
        itineraryContent.appendChild(actSection);
    }

    // On mobile, show the floating button
    if (isMobile() && viewItineraryBtn) {
        viewItineraryBtn.style.display = '';
        viewItineraryBtn.classList.add('visible');
    }
}

function closeItineraryPanel() {
    if (isMobile()) {
        itineraryPanel.classList.remove('mobile-open');
    } else {
        itineraryPanel.style.display = 'none';
    }
}

function exportItinerary() {
    if (!currentItinerary) return;
    const blob = new Blob([JSON.stringify(currentItinerary, null, 2)], { type: 'application/json' });
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `itinerary_${currentItinerary.id || currentSessionId}.json`;
    document.body.appendChild(a);
    a.click();
    window.URL.revokeObjectURL(url);
    document.body.removeChild(a);
}

// ---------------------------------------------------------------------------
// Session sidebar — backend-persisted chat history
// ---------------------------------------------------------------------------

function escapeHtml(str) {
    return String(str).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}

function formatSessionDate(isoString) {
    const d = new Date(isoString);
    return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
}

async function loadAndRenderSessions() {
    try {
        const response = await authFetch('/api/chat/sessions');
        if (!response.ok) return;
        const sessions = await response.json();

        const mySection = document.getElementById('myChatsSection');
        const myList = document.getElementById('myChatsList');
        const sharedSection = document.getElementById('sharedChatsSection');
        const sharedList = document.getElementById('sharedChatsList');
        if (!mySection || !myList || !sharedSection || !sharedList) return;

        const mine = sessions.filter(s => s.is_owner);
        const shared = sessions.filter(s => !s.is_owner);

        mySection.style.display = 'block';
        myList.innerHTML = '';
        if (mine.length > 0) {
            mine.forEach(s => myList.appendChild(buildSessionItem(s)));
        } else {
            myList.innerHTML = '<p class="empty-chats-msg">No chats yet. Start a new chat above.</p>';
        }

        sharedSection.style.display = 'block';
        sharedList.innerHTML = '';
        if (shared.length > 0) {
            shared.forEach(s => sharedList.appendChild(buildSessionItem(s)));
        } else {
            sharedList.innerHTML = '<p class="empty-chats-msg">No chats have been shared with you yet.</p>';
        }
    } catch (e) {
        console.error('Failed to load chat sessions:', e);
    }
}

function buildSessionItem(session) {
    const item = document.createElement('div');
    item.className = 'past-chat-item';
    item.dataset.sessionId = session.session_id;

    const shareControl = session.is_owner
        ? `<button class="share-toggle-btn${session.is_shared ? ' shared' : ''}"
               title="${session.is_shared ? 'Unshare' : 'Share with team'}"
               data-session="${session.session_id}"
               data-shared="${session.is_shared}">
               ${session.is_shared ? '🔗' : '🔒'}
           </button>
           <button class="delete-chat-btn" title="Delete chat" data-session="${session.session_id}">🗑</button>`
        : `<span class="chat-item-badge">Shared</span>`;

    item.innerHTML = `
        <span class="chat-item-icon">${session.itinerary_id ? '🎬' : '💬'}</span>
        <span class="chat-item-info">
            <div class="chat-item-dest">${escapeHtml(session.title)}</div>
            <div class="chat-item-date">${formatSessionDate(session.updated_at)}</div>
        </span>
        ${shareControl}
    `;

    // Click item body → open resume confirm (skip if the share/delete button was clicked)
    item.addEventListener('click', (e) => {
        if (e.target.closest('.share-toggle-btn') || e.target.closest('.delete-chat-btn')) return;
        openResumeConfirm(session);
        if (isMobile()) closeSidebar();
    });

    // Share toggle
    const shareBtn = item.querySelector('.share-toggle-btn');
    if (shareBtn) {
        shareBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            const currentlyShared = shareBtn.dataset.shared === 'true';
            toggleShareSession(session.session_id, currentlyShared, shareBtn);
        });
    }

    // Delete button
    const deleteBtn = item.querySelector('.delete-chat-btn');
    if (deleteBtn) {
        deleteBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            openDeleteConfirm(session);
        });
    }

    return item;
}

// ---------------------------------------------------------------------------
// Resume session modal
// ---------------------------------------------------------------------------
let _pendingResumeSession = null;

function openResumeConfirm(session) {
    _pendingResumeSession = session;
    document.getElementById('resumeModalTitle').textContent = `Resume: ${escapeHtml(session.title)}`;
    document.getElementById('resumeModalDesc').textContent =
        `Resume your conversation about "${escapeHtml(session.title)}"? Your current chat will be replaced.`;
    document.getElementById('resumeConfirmModal').style.display = 'flex';
}

function closeResumeModal() {
    const modal = document.getElementById('resumeConfirmModal');
    if (modal) modal.style.display = 'none';
    _pendingResumeSession = null;
}

async function confirmResumeSession() {
    if (!_pendingResumeSession) return;
    const session = _pendingResumeSession;
    closeResumeModal();
    await resumeSession(session.session_id);
}

async function resumeSession(sessionId) {
    updateHeaderStatus('Loading session...');
    try {
        const response = await authFetch(`/api/session/${sessionId}/resume`, { method: 'POST' });
        if (!response.ok) {
            await response.json().catch(() => ({}));
            updateHeaderStatus('Could not load this chat. Please try again.');
            return;
        }
        const data = await response.json();

        // Replace current session state
        currentSessionId = data.session_id;
        currentItinerary = null;
        currentVideoUrl = null;
        hasGeneratedItinerary = data.requirements_complete || false;
        pendingRegenerate = false;

        // Render full conversation history
        chatMessages.innerHTML = '';
        data.messages.forEach(msg => addMessageToChat(msg.role, msg.content));

        // If an itinerary was previously generated, restore it in the panel
        if (data.itinerary_id) {
            try {
                const itinResponse = await authFetch(`/itinerary/${data.itinerary_id}`);
                if (itinResponse.ok) {
                    const itinData = await itinResponse.json();
                    currentItinerary = itinData;
                    const itineraryToShow = itinData.rich_itinerary || itinData;
                    displayItinerary(itineraryToShow, itinData);
                    hasGeneratedItinerary = true;
                }
            } catch (e) {
                console.warn('Could not restore itinerary panel:', e);
            }
            const existing = document.getElementById('compileVideoMessage');
            if (existing) existing.remove();
            addCompileVideoButton(data.itinerary_id);
        }

        updateHeaderStatus(`Resumed: ${data.title}`);
        loadAndRenderSessions();
    } catch (e) {
        console.error('Resume error', e);
        updateHeaderStatus('Could not load this chat. Please try again.');
    }
}

// ---------------------------------------------------------------------------
// Share toggle
// ---------------------------------------------------------------------------
async function toggleShareSession(sessionId, currentlyShared, btn) {
    const newShared = !currentlyShared;
    try {
        const response = await authFetch(`/api/session/${sessionId}/share`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ is_shared: newShared }),
        });
        if (!response.ok) {
            console.error('Share toggle failed: status=%d', response.status);
            return;
        }
        // Optimistic UI update
        btn.dataset.shared = String(newShared);
        btn.classList.toggle('shared', newShared);
        btn.title = newShared ? 'Unshare' : 'Share with team';
        btn.textContent = newShared ? '🔗' : '🔒';
    } catch (e) {
        console.error('Share toggle error', e);
    }
}

// ---------------------------------------------------------------------------
// Delete session modal
// ---------------------------------------------------------------------------
let _pendingDeleteSession = null;

function openDeleteConfirm(session) {
    _pendingDeleteSession = session;
    const hasVideo = !!session.itinerary_id;
    document.getElementById('deleteModalDesc').textContent =
        `Are you sure you want to delete "${escapeHtml(session.title)}"?` +
        (hasVideo ? ' The compiled video will also be deleted.' : '') +
        ' This cannot be undone.';
    document.getElementById('deleteConfirmModal').style.display = 'flex';
}

function closeDeleteModal() {
    const modal = document.getElementById('deleteConfirmModal');
    if (modal) modal.style.display = 'none';
    _pendingDeleteSession = null;
}

async function confirmDeleteSession() {
    if (!_pendingDeleteSession) return;
    const session = _pendingDeleteSession;
    closeDeleteModal();

    try {
        const response = await authFetch(`/api/session/${session.session_id}`, { method: 'DELETE' });
        if (!response.ok) {
            console.error('Delete failed: status=%d', response.status);
            return;
        }
        // If the deleted session is the active one, start fresh
        if (currentSessionId === session.session_id) {
            currentSessionId = null;
            currentItinerary = null;
            currentVideoUrl = null;
            hasGeneratedItinerary = false;
            pendingRegenerate = false;
            chatMessages.innerHTML = '';
            itineraryPanel.style.display = 'none';
            addMessageToChat('assistant', GREETING_TEXT);
            updateHeaderStatus('Ready to help');
        }
        loadAndRenderSessions();
    } catch (e) {
        console.error('Delete session error', e);
    }
}

// ---------------------------------------------------------------------------
// New chat
// ---------------------------------------------------------------------------
function startNewChat() {
    // If the current session has no user messages, don't create a new one.
    const hasUserMessages = chatMessages.querySelector('.user-message') !== null;
    if (!hasUserMessages) return;

    if (videoModeEnabled) disableVideoMode();

    // Keep the current session in the DB — it will appear in "My Chats" sidebar.
    // Just drop the local reference so a fresh session is created.
    currentSessionId = null;
    currentItinerary = null;
    currentVideoUrl = null;
    hasGeneratedItinerary = false;
    pendingRegenerate = false;

    chatMessages.innerHTML = '';
    messageInput.value = '';
    messageInput.disabled = false;
    sendBtn.disabled = true;
    itineraryPanel.style.display = 'none';
    itineraryPanel.classList.remove('mobile-open');
    if (viewItineraryBtn) {
        viewItineraryBtn.classList.remove('visible');
        viewItineraryBtn.style.display = 'none';
    }
    // Show greeting locally — session created in DB only when user sends first message.
    addMessageToChat('assistant', GREETING_TEXT);
    updateHeaderStatus('Ready to help');
    messageInput.focus();
}

function updateHeaderStatus(status) {
    if (headerStatus) headerStatus.textContent = status;
}

// ---------------------------------------------------------------------------
// Mobile helpers
// ---------------------------------------------------------------------------
function isMobile() {
    return window.innerWidth <= 768;
}

function toggleSidebar() {
    sidebar.classList.toggle('open');
    sidebarOverlay.classList.toggle('active');
}

function closeSidebar() {
    sidebar.classList.remove('open');
    sidebarOverlay.classList.remove('active');
}

function openItineraryMobile() {
    itineraryPanel.style.display = 'block';
    requestAnimationFrame(() => {
        itineraryPanel.classList.add('mobile-open');
    });
}

// ---------------------------------------------------------------------------
// Cinematic video compilation
// ---------------------------------------------------------------------------
function addCompileVideoButton(itineraryId) {
    const messageDiv = document.createElement('div');
    messageDiv.className = 'message assistant-message';
    messageDiv.id = 'compileVideoMessage';

    const btn = document.createElement('button');
    btn.className = 'btn btn-primary btn-small';
    btn.textContent = '🎬 Accept Itinerary & Create Video';
    btn.onclick = () => {
        btn.disabled = true;
        btn.textContent = '⏳ Compiling...';
        compileAndShowVideo(itineraryId, btn);
    };

    const content = document.createElement('div');
    content.className = 'message-content';
    content.appendChild(btn);

    messageDiv.innerHTML = `<div class="message-avatar">🤖</div>`;
    messageDiv.appendChild(content);
    chatMessages.appendChild(messageDiv);
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

async function compileAndShowVideo(itineraryId, btn) {
    // On error/failure: reset button so user can retry
    const resetBtn = () => {
        if (btn) {
            btn.disabled = false;
            btn.textContent = '🎬 Accept Itinerary & Create Video';
        }
    };

    // On success: replace button with a "done" badge so it's clear compilation finished
    const markBtnDone = () => {
        if (btn) {
            btn.disabled = true;
            btn.textContent = '✅ Video Created';
            btn.className = 'btn btn-success btn-small';
        }
    };

    // Insert a live status message we'll update in place
    const statusDiv = document.createElement('div');
    statusDiv.className = 'message assistant-message';
    statusDiv.id = 'compileStatusMessage';
    statusDiv.innerHTML = `<div class="message-avatar">🤖</div><div class="message-content" id="compileStatusText"><span class="compile-spinner"></span> Compiling your cinematic trip video… 0s</div>`;
    chatMessages.appendChild(statusDiv);
    chatMessages.scrollTop = chatMessages.scrollHeight;

    const startTime = Date.now();
    const elapsedInterval = setInterval(() => {
        const el = document.getElementById('compileStatusText');
        if (el) {
            const elapsed = Math.floor((Date.now() - startTime) / 1000);
            el.innerHTML = `<span class="compile-spinner"></span> Compiling your cinematic trip video… ${elapsed}s`;
        }
    }, 1000);

    const removeStatusMsg = () => {
        clearInterval(elapsedInterval);
        const msg = document.getElementById('compileStatusMessage');
        if (msg) msg.remove();
    };

    // Step 1: kick off compilation
    let kickoffOk = false;
    try {
        const res = await authFetch(`/itinerary/${itineraryId}/compile-video`, { method: 'POST' });
        if (!res.ok) {
            await res.json().catch(() => {});
            removeStatusMsg();
            if (res.status === 400) {
                addMessageToChat('assistant', 'ℹ️ No cinematic clips were matched for this itinerary — video unavailable.');
            } else {
                addMessageToChat('assistant', '⚠️ Could not start video compilation. Please try again or contact the administrator.');
            }
            resetBtn();
            return;
        }
        kickoffOk = true;
    } catch (e) {
        removeStatusMsg();
        console.error('Video compile kickoff error:', e);
        addMessageToChat('assistant', '⚠️ Could not start video compilation. Please try again.');
        resetBtn();
        return;
    }

    if (!kickoffOk) return;

    // Step 2: poll /video-status until compiled or failed
    const pollInterval = setInterval(async () => {
        try {
            const res = await authFetch(`/itinerary/${itineraryId}/video-status`);
            const data = await res.json();

            if (data.status === 'compiled' && data.video_url) {
                clearInterval(pollInterval);
                removeStatusMsg();
                markBtnDone();

                const elapsed = Math.floor((Date.now() - startTime) / 1000);
                showVideoPlayer(data.video_url);

                // Completion message
                addMessageToChat('assistant', `🎉 Your cinematic trip video is ready! (compiled in ${elapsed}s)\nUse the player below to watch or download it.`);

                // End-of-conversation message with "Start New Chat" affordance
                addConversationEndMessage();

            } else if (data.status === 'failed') {
                clearInterval(pollInterval);
                removeStatusMsg();
                addMessageToChat('assistant', '⚠️ Video compilation failed. You can still view your itinerary in the panel.');
                resetBtn();

            }
            // else "processing" or "not_started" — keep polling
        } catch (e) {
            clearInterval(pollInterval);
            removeStatusMsg();
            console.error('Video status poll error:', e);
            addMessageToChat('assistant', '⚠️ Lost contact while checking video status. Please refresh the page to see if it completed.');
            resetBtn();
        }
    }, 3000);
}

function addConversationEndMessage() {
    const messageDiv = document.createElement('div');
    messageDiv.className = 'message assistant-message';
    messageDiv.id = 'conversationEndMessage';

    const content = document.createElement('div');
    content.className = 'message-content conversation-end-content';
    content.innerHTML = `
        <p class="conversation-end-text">
            🌟 That's your trip all wrapped up! Your video is saved above — you can download it any time.
            Ready to plan another adventure?
        </p>
        <button class="btn btn-primary btn-small" id="endNewChatBtn">
            + Start New Chat
        </button>
    `;

    messageDiv.innerHTML = `<div class="message-avatar">🤖</div>`;
    messageDiv.appendChild(content);
    chatMessages.appendChild(messageDiv);
    chatMessages.scrollTop = chatMessages.scrollHeight;

    document.getElementById('endNewChatBtn').addEventListener('click', startNewChat);
}

function showVideoPlayer(url) {
    currentVideoUrl = url;

    // Build an inline video card inside the chat
    const cardDiv = document.createElement('div');
    cardDiv.className = 'message assistant-message';
    cardDiv.id = 'inlinVideoCard';

    const destName = currentItinerary
        ? (currentItinerary.destination || (currentItinerary.rich_itinerary && currentItinerary.rich_itinerary.destination) || 'Your Trip')
        : 'Your Trip';
    const safeFilename = destName.replace(/\s+/g, '-').toLowerCase() + '-trip.mp4';

    const content = document.createElement('div');
    content.className = 'message-content';
    content.style.padding = '0';
    content.style.overflow = 'hidden';
    content.style.maxWidth = '100%';
    content.innerHTML = `
        <div class="video-card">
            <div class="video-card-header">
                <span class="video-card-title">🎬 ${escapeHtml(destName)} — Cinematic Video</span>
                <div class="video-card-actions">
                    <a href="${url}" download="${safeFilename}" class="btn-download">⬇ Download</a>
                </div>
            </div>
            <div class="video-card-player-wrap">
                <video src="${url}" preload="metadata">Your browser does not support the video tag.</video>
                <div class="video-play-overlay" id="videoPlayOverlay">
                    <div class="play-circle">
                        <svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
                            <polygon points="5,3 19,12 5,21"/>
                        </svg>
                    </div>
                </div>
            </div>
        </div>
    `;

    cardDiv.innerHTML = `<div class="message-avatar">🤖</div>`;
    cardDiv.appendChild(content);
    chatMessages.appendChild(cardDiv);
    chatMessages.scrollTop = chatMessages.scrollHeight;

    // Wire up play overlay
    const overlay = content.querySelector('#videoPlayOverlay');
    const video = content.querySelector('video');
    overlay.addEventListener('click', () => {
        overlay.classList.add('hidden');
        video.controls = true;
        video.play().catch(() => {});
    });
}
