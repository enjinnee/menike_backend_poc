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
const exportBtn = document.getElementById('exportBtn');
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
document.addEventListener('DOMContentLoaded', () => {
    if (!localStorage.getItem('access_token')) {
        window.location.href = '/auth/login';
        return;
    }
    initializeSession();
    setupEventListeners();
    checkHeygenConfig();
});

function initializeSession() {
    updateHeaderStatus('Starting session...');
    authFetch('/api/session/new', { method: 'POST' })
        .then(response => response.json())
        .then(data => {
            currentSessionId = data.session_id;
            // Show greeting from AI in chat
            chatMessages.innerHTML = '';
            addMessageToChat('assistant', data.greeting);
            updateHeaderStatus('Ready to help');
        })
        .catch(error => {
            console.error('Error creating session:', error);
            updateHeaderStatus('Failed to start session');
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
    exportBtn.addEventListener('click', exportItinerary);

    logoutBtn.addEventListener('click', () => {
        localStorage.removeItem('access_token');
        window.location.href = '/auth/login';
    });

    if (videoModeToggle) videoModeToggle.addEventListener('click', toggleVideoMode);
    if (voiceButton) voiceButton.addEventListener('click', handleVoiceButtonClick);
    if (exitVideoMode) exitVideoMode.addEventListener('click', disableVideoMode);

    document.getElementById('closeVideoBar').addEventListener('click', () => {
        document.getElementById('videoBar').style.display = 'none';
        document.getElementById('finalVideoPlayer').pause();
        document.getElementById('downloadVideoLink').style.display = 'none';
        document.querySelector('.container').style.height = '';
    });

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
    if (!currentSessionId) { alert('Please wait for session to initialize'); return; }

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
                if (error === 'microphone-denied') { alert('Microphone access required for video mode.'); disableVideoMode(); }
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
            onError: (error) => { console.error('Avatar error:', error); alert('Failed to initialize video avatar.'); disableVideoMode(); },
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
        alert('Failed to enable video mode: ' + error.message);
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
    if (!message || !currentSessionId) return;

    messageInput.disabled = true;
    sendBtn.disabled = true;
    addMessageToChat('user', message);
    messageInput.value = '';
    showTypingIndicator();

    authFetch('/api/chat/send', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: currentSessionId, message: message })
    })
    .then(response => response.json())
    .then(data => {
        removeTypingIndicator();
        if (data.error) {
            addMessageToChat('assistant', `Error: ${data.error}`);
        } else {
            addMessageToChat('assistant', data.response);
            // Handle auto-generation for both first-time and updates
            handleAutoGenerate(data);
        }
    })
    .catch(error => {
        removeTypingIndicator();
        console.error('Error:', error);
        addMessageToChat('assistant', 'Sorry, there was an error. Please try again.');
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
    .then(response => response.json())
    .then(data => {
        if (data.detail) {
            alert(`Error: ${data.detail}`);
            updateHeaderStatus('Generation failed');
        } else {
            currentItinerary = data;
            const itineraryToShow = data.rich_itinerary || data;
            displayItinerary(itineraryToShow, data);
            updateHeaderStatus('Itinerary generated successfully!');
            exportBtn.style.display = 'block';

            if (!hasGeneratedItinerary) {
                hasGeneratedItinerary = true;
                const panelHint = isMobile()
                    ? 'tap the "View Itinerary" button to see it'
                    : 'view it in the right panel';
                addMessageToChat('assistant', `✅ Your itinerary has been generated! You can ${panelHint}. Images and cinematic clips have been matched from the media library. Click Export to download as JSON.`);
            } else {
                const updateHint = isMobile()
                    ? 'tap "View Itinerary" to see the latest version'
                    : 'check the right panel for the latest version';
                addMessageToChat('assistant', `✅ Your itinerary has been updated — ${updateHint}.`);
            }

            if (data.id) addCompileVideoButton(data.id);
        }
    })
    .catch(error => {
        console.error('Error:', error);
        alert('Error generating itinerary. Please try again.');
        updateHeaderStatus('Generation failed');
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
                    const clipLine = act.cinematic_clip_url
                        ? `<div style="font-size:12px;color:#3b82f6;">🎬 Clip: ${act.cinematic_clip_url}</div>`
                        : '';
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
                ${act.cinematic_clip_url ? `<br><small style="color:#3b82f6;">🎬 ${act.cinematic_clip_url}</small>` : ''}`;
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
// New chat
// ---------------------------------------------------------------------------
function startNewChat() {
    if (videoModeEnabled) disableVideoMode();

    if (currentSessionId) {
        authFetch(`/api/session/${currentSessionId}`, { method: 'DELETE' }).catch(() => {});
    }

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
    exportBtn.style.display = 'none';
    currentItinerary = null;
    hasGeneratedItinerary = false;
    pendingRegenerate = false;
    document.getElementById('videoBar').style.display = 'none';
    document.getElementById('finalVideoPlayer').src = '';
    document.getElementById('downloadVideoLink').style.display = 'none';
    document.querySelector('.container').style.height = '';
    updateHeaderStatus('Starting new session...');
    messageInput.focus();

    initializeSession();
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
        btn.textContent = 'Compiling...';
        compileAndShowVideo(itineraryId);
    };

    const content = document.createElement('div');
    content.className = 'message-content';
    content.appendChild(btn);

    messageDiv.innerHTML = `<div class="message-avatar">🤖</div>`;
    messageDiv.appendChild(content);
    chatMessages.appendChild(messageDiv);
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

async function compileAndShowVideo(itineraryId) {
    // Show a live elapsed timer while the server compiles
    const timerDiv = document.createElement('div');
    timerDiv.className = 'message assistant-message';
    timerDiv.id = 'compileTimerMessage';
    timerDiv.innerHTML = `<div class="message-avatar">🤖</div><div class="message-content" id="compileTimerText">🎬 Compiling your cinematic trip video… 0s</div>`;
    chatMessages.appendChild(timerDiv);
    chatMessages.scrollTop = chatMessages.scrollHeight;

    const startTime = Date.now();
    const timerInterval = setInterval(() => {
        const elapsed = Math.floor((Date.now() - startTime) / 1000);
        const el = document.getElementById('compileTimerText');
        if (el) el.textContent = `🎬 Compiling your cinematic trip video… ${elapsed}s`;
    }, 1000);

    try {
        const res = await authFetch(`/itinerary/${itineraryId}/compile-video`, { method: 'POST' });

        clearInterval(timerInterval);
        const timerMsg = document.getElementById('compileTimerMessage');
        if (timerMsg) timerMsg.remove();

        if (!res.ok) {
            const err = await res.json().catch(() => ({}));
            if (res.status === 400) {
                addMessageToChat('assistant', 'ℹ️ No cinematic clips were matched for this itinerary — video unavailable.');
            } else {
                addMessageToChat('assistant', `⚠️ Could not compile video: ${err.detail || 'Unknown error'}. You can still view your itinerary above.`);
            }
            return;
        }

        const data = await res.json();
        const videoUrl = data.final_video && data.final_video.video_url;
        if (videoUrl) {
            const elapsed = Math.floor((Date.now() - startTime) / 1000);
            showVideoPlayer(videoUrl);
            addMessageToChat('assistant', `✅ Your cinematic video is ready! (compiled in ${elapsed}s) See the player at the bottom.`);
        } else {
            addMessageToChat('assistant', 'ℹ️ No cinematic clips were matched for this itinerary — video unavailable.');
        }
    } catch (e) {
        clearInterval(timerInterval);
        const timerMsg = document.getElementById('compileTimerMessage');
        if (timerMsg) timerMsg.remove();
        console.error('Video compile error:', e);
        addMessageToChat('assistant', '⚠️ Could not compile video. You can still view your itinerary above.');
    }
}

function showVideoPlayer(url) {
    const videoBar = document.getElementById('videoBar');
    const player = document.getElementById('finalVideoPlayer');
    const downloadLink = document.getElementById('downloadVideoLink');
    player.src = url;
    downloadLink.href = url;
    downloadLink.style.display = 'inline-flex';
    videoBar.style.display = 'block';
    // Shrink the container so the chat input stays above the fixed bar
    const barHeight = videoBar.offsetHeight;
    document.querySelector('.container').style.height = `calc(100vh - ${barHeight}px)`;
}
