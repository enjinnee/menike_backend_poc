/**
 * HeyGen LiveAvatar Manager
 * Handles HeyGen LiveAvatar initialization, video streaming, and speech
 * Uses @heygen/liveavatar-web-sdk
 */

class HeyGenAvatarManager {
    constructor(options = {}) {
        this.session = null;
        this.sessionToken = null;
        this.avatarId = null;
        this.voiceId = null;
        this.isActive = false;
        this.isTalking = false;
        this.videoElement = options.videoElement;
        this.onReady = options.onReady || (() => {});
        this.onTalkingStart = options.onTalkingStart || (() => {});
        this.onTalkingEnd = options.onTalkingEnd || (() => {});
        this.onError = options.onError || (() => {});
        this.onDisconnect = options.onDisconnect || (() => {});
    }

    /**
     * Initialize the HeyGen LiveAvatar with a session token from the backend
     * @param {string} sessionId - The current chat session ID
     * @returns {Promise<boolean>} - Whether initialization was successful
     */
    async initialize(sessionId) {
        try {
            // Get token from backend (keeps API key secure server-side)
            const response = await fetch('/api/heygen/token', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ session_id: sessionId })
            });

            const data = await response.json();
            if (data.error) {
                throw new Error(data.error);
            }

            this.sessionToken = data.token;
            this.avatarId = data.avatar_id;
            this.voiceId = data.voice_id;

            console.log('Got LiveAvatar token, initializing SDK...');
            console.log('Avatar ID:', this.avatarId);
            console.log('Voice ID:', this.voiceId);

            // Dynamically import the HeyGen LiveAvatar SDK
            const module = await import('https://esm.sh/@heygen/liveavatar-web-sdk');
            const { LiveAvatarSession } = module;

            // Create LiveAvatarSession instance
            this.session = new LiveAvatarSession(this.sessionToken, {
                voiceChat: true  // Enable voice chat mode
            });

            // Debug: Log all events emitted by the session
            const originalEmit = this.session.emit?.bind(this.session);
            if (originalEmit) {
                this.session.emit = (event, ...args) => {
                    console.log('[LiveAvatar Event]', event, args);
                    return originalEmit(event, ...args);
                };
            }

            // Listen for all possible event names (both old and new naming conventions)
            const eventNames = [
                'session_started', 'session_ended', 'session.started', 'session.stopped',
                'stream', 'stream_ready', 'STREAM_READY',
                'avatar_talking', 'avatar_start_talking', 'avatar_stop_talking',
                'AVATAR_START_TALKING', 'AVATAR_STOP_TALKING',
                'avatar.speak_started', 'avatar.speak_ended',
                'connected', 'disconnected', 'STREAM_DISCONNECTED',
                'error', 'room_connected', 'track_subscribed'
            ];

            eventNames.forEach(eventName => {
                this.session.on(eventName, (event) => {
                    console.log(`[LiveAvatar] Event "${eventName}":`, event);
                });
            });

            // Set up actual handlers
            this.session.on('session_started', (event) => {
                console.log('LiveAvatar session started', event);
                this.isActive = true;
                this.onReady();
            });

            this.session.on('avatar_start_talking', () => {
                console.log('Avatar started talking');
                this.isTalking = true;
                this.onTalkingStart();
            });

            this.session.on('avatar_stop_talking', () => {
                console.log('Avatar stopped talking');
                this.isTalking = false;
                this.onTalkingEnd();
            });

            this.session.on('stream_ready', (event) => {
                console.log('LiveAvatar stream ready', event);
                if (this.videoElement && event.stream) {
                    this.videoElement.srcObject = event.stream;
                    this.videoElement.play().catch(e => console.error('Video play error:', e));
                }
            });

            // Also try 'stream' event name
            this.session.on('stream', (event) => {
                console.log('LiveAvatar stream received', event);
                if (this.videoElement && event.stream) {
                    this.videoElement.srcObject = event.stream;
                    this.videoElement.play().catch(e => console.error('Video play error:', e));
                }
            });

            this.session.on('session_ended', () => {
                console.log('LiveAvatar session ended');
                this.isActive = false;
                this.onDisconnect();
            });

            this.session.on('error', (error) => {
                console.error('LiveAvatar error:', error);
                this.onError(error);
            });

            // Start the avatar session
            console.log('Starting LiveAvatar session...');
            await this.session.start();

            return true;
        } catch (error) {
            console.error('LiveAvatar initialization error:', error);
            this.onError(error);
            return false;
        }
    }

    /**
     * Make the avatar speak the given text
     * @param {string} text - The text for the avatar to speak
     * @returns {Promise<boolean>} - Whether the speak command was successful
     */
    async speak(text) {
        if (!this.session || !this.isActive) {
            console.error('Avatar not initialized or not active');
            return false;
        }

        if (!text || !text.trim()) {
            console.warn('Empty text provided to speak');
            return false;
        }

        try {
            console.log('Avatar speaking:', text.substring(0, 50) + '...');
            // Use the speak method to make the avatar say the text
            await this.session.speak(text.trim());
            return true;
        } catch (error) {
            console.error('Avatar speak error:', error);
            return false;
        }
    }

    /**
     * Interrupt the avatar if it's currently speaking
     */
    async interrupt() {
        if (this.session && this.isTalking) {
            try {
                await this.session.interrupt();
            } catch (error) {
                console.error('Avatar interrupt error:', error);
            }
        }
    }

    /**
     * Stop and clean up the avatar session
     */
    async stop() {
        if (this.session) {
            try {
                await this.session.stop();
                console.log('Avatar stopped');
            } catch (error) {
                console.error('Stop avatar error:', error);
            } finally {
                this.session = null;
                this.isActive = false;
                this.isTalking = false;
                this.sessionToken = null;

                // Clear video element
                if (this.videoElement) {
                    this.videoElement.srcObject = null;
                }
            }
        }
    }

    /**
     * Check if the avatar is currently active
     * @returns {boolean}
     */
    isAvatarActive() {
        return this.isActive;
    }

    /**
     * Check if the avatar is currently speaking
     * @returns {boolean}
     */
    isAvatarTalking() {
        return this.isTalking;
    }
}

// Export for use in main app
window.HeyGenAvatarManager = HeyGenAvatarManager;
