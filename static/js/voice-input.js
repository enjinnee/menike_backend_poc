/**
 * Voice Input Manager
 * Handles continuous microphone input and speech-to-text transcription using Web Speech API
 * Designed for avatar-driven conversations with automatic listening
 */

class VoiceInputManager {
    constructor(options = {}) {
        this.isListening = false;
        this.recognition = null;
        this.isSupported = false;
        this.continuousMode = options.continuousMode !== false; // Default to continuous
        this.autoRestart = options.autoRestart !== false; // Auto-restart after speech ends
        this.language = options.language || 'en-US';
        this.isPaused = false; // Pause listening while avatar is talking
        this.restartTimeout = null;

        // Callbacks
        this.onTranscript = options.onTranscript || (() => {});
        this.onInterimTranscript = options.onInterimTranscript || (() => {});
        this.onListeningStart = options.onListeningStart || (() => {});
        this.onListeningEnd = options.onListeningEnd || (() => {});
        this.onError = options.onError || (() => {});
    }

    /**
     * Initialize the voice input manager
     * @returns {Promise<boolean>} - Whether initialization was successful
     */
    async initialize() {
        // Check for Web Speech API support
        const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;

        if (!SpeechRecognition) {
            console.error('Web Speech API not supported in this browser');
            this.onError('speech-not-supported');
            return false;
        }

        try {
            // Request microphone permission
            await navigator.mediaDevices.getUserMedia({ audio: true });

            this.recognition = new SpeechRecognition();
            this.recognition.continuous = true;  // Keep listening continuously
            this.recognition.interimResults = true;  // Get partial results
            this.recognition.lang = this.language;
            this.recognition.maxAlternatives = 1;

            // Handle speech recognition results
            this.recognition.onresult = (event) => {
                let interimTranscript = '';
                let finalTranscript = '';

                for (let i = event.resultIndex; i < event.results.length; i++) {
                    const transcript = event.results[i][0].transcript;
                    if (event.results[i].isFinal) {
                        finalTranscript += transcript;
                    } else {
                        interimTranscript += transcript;
                    }
                }

                if (interimTranscript) {
                    this.onInterimTranscript(interimTranscript);
                }

                if (finalTranscript && finalTranscript.trim()) {
                    this.onTranscript(finalTranscript.trim());
                }
            };

            // Handle recognition end - auto-restart if in continuous mode
            this.recognition.onend = () => {
                console.log('Speech recognition ended');
                this.isListening = false;
                this.onListeningEnd();

                // Auto-restart if in continuous mode and not paused
                if (this.continuousMode && this.autoRestart && !this.isPaused) {
                    this.restartTimeout = setTimeout(() => {
                        if (!this.isPaused && this.recognition) {
                            console.log('Auto-restarting speech recognition');
                            this.startListening();
                        }
                    }, 300); // Small delay before restarting
                }
            };

            // Handle recognition start
            this.recognition.onstart = () => {
                this.isListening = true;
                this.onListeningStart();
            };

            // Handle errors
            this.recognition.onerror = (event) => {
                console.error('Speech recognition error:', event.error);

                switch (event.error) {
                    case 'not-allowed':
                        this.isListening = false;
                        this.onError('microphone-denied');
                        break;
                    case 'no-speech':
                        // No speech detected - this is normal, will auto-restart
                        console.log('No speech detected, will restart...');
                        break;
                    case 'network':
                        this.onError('network-error');
                        break;
                    case 'aborted':
                        // User cancelled or paused
                        break;
                    default:
                        this.onError(event.error);
                }
            };

            this.isSupported = true;
            console.log('Voice input initialized successfully (continuous mode)');
            return true;

        } catch (error) {
            console.error('Failed to initialize voice input:', error);
            if (error.name === 'NotAllowedError') {
                this.onError('microphone-denied');
            } else {
                this.onError('initialization-failed');
            }
            return false;
        }
    }

    /**
     * Start listening for voice input
     */
    startListening() {
        if (!this.recognition) {
            console.error('Voice input not initialized');
            this.onError('not-initialized');
            return;
        }

        if (this.isListening) {
            console.log('Already listening');
            return;
        }

        this.isPaused = false;

        // Clear any pending restart
        if (this.restartTimeout) {
            clearTimeout(this.restartTimeout);
            this.restartTimeout = null;
        }

        try {
            this.recognition.start();
        } catch (error) {
            // May already be started
            console.log('Recognition start issue:', error.message);
        }
    }

    /**
     * Stop listening for voice input
     */
    stopListening() {
        if (!this.recognition) {
            return;
        }

        // Clear any pending restart
        if (this.restartTimeout) {
            clearTimeout(this.restartTimeout);
            this.restartTimeout = null;
        }

        if (!this.isListening) {
            return;
        }

        try {
            this.recognition.stop();
        } catch (error) {
            console.error('Failed to stop listening:', error);
        }
    }

    /**
     * Pause listening temporarily (e.g., while avatar is speaking)
     * Will not auto-restart until resumed
     */
    pause() {
        console.log('Pausing voice input');
        this.isPaused = true;

        // Clear any pending restart
        if (this.restartTimeout) {
            clearTimeout(this.restartTimeout);
            this.restartTimeout = null;
        }

        this.stopListening();
    }

    /**
     * Resume listening after pause
     */
    resume() {
        console.log('Resuming voice input');
        this.isPaused = false;

        // Small delay before resuming to avoid picking up avatar's speech
        setTimeout(() => {
            if (!this.isPaused) {
                this.startListening();
            }
        }, 500);
    }

    /**
     * Abort the current recognition session
     */
    abort() {
        this.isPaused = true;

        if (this.restartTimeout) {
            clearTimeout(this.restartTimeout);
            this.restartTimeout = null;
        }

        if (this.recognition && this.isListening) {
            try {
                this.recognition.abort();
                this.isListening = false;
            } catch (error) {
                console.error('Failed to abort recognition:', error);
            }
        }
    }

    /**
     * Set the recognition language
     * @param {string} language - Language code (e.g., 'en-US', 'es-ES')
     */
    setLanguage(language) {
        this.language = language;
        if (this.recognition) {
            this.recognition.lang = language;
        }
    }

    /**
     * Check if voice input is currently listening
     * @returns {boolean}
     */
    isCurrentlyListening() {
        return this.isListening;
    }

    /**
     * Check if voice input is paused
     * @returns {boolean}
     */
    isCurrentlyPaused() {
        return this.isPaused;
    }

    /**
     * Check if voice input is supported
     * @returns {boolean}
     */
    isVoiceSupported() {
        return this.isSupported;
    }

    /**
     * Clean up resources
     */
    destroy() {
        this.isPaused = true;
        this.autoRestart = false;

        if (this.restartTimeout) {
            clearTimeout(this.restartTimeout);
            this.restartTimeout = null;
        }

        if (this.recognition) {
            this.abort();
            this.recognition = null;
        }
        this.isSupported = false;
    }
}

// Export for use in main app
window.VoiceInputManager = VoiceInputManager;
