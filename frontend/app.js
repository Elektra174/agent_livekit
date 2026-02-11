// Omni-Agent Frontend

// Check if LiveKit client library is loaded
if (typeof LivekitClient === 'undefined') {
    console.error('LiveKit client library is not loaded. Please check the script tag in index.html.');
    document.addEventListener('DOMContentLoaded', () => {
        const status = document.getElementById('status');
        if (status) {
            status.textContent = 'Error: LiveKit library not loaded. Please refresh the page.';
            status.style.color = '#ef4444';
        }
    });
    throw new Error('LiveKit client library is not loaded');
}

class OmniAgentApp {
    constructor() {
        console.log('[DEBUG] OmniAgentApp constructor called');
        this.room = null;
        this.localVideo = document.getElementById('localVideo');
        this.remoteVideo = document.getElementById('remoteVideo');
        this.startSessionBtn = document.getElementById('startSessionBtn');
        this.micBtn = document.getElementById('micBtn'); // Может быть null
        this.cameraBtn = document.getElementById('cameraBtn'); // Может быть null
        this.endSessionBtn = document.getElementById('endSessionBtn');
        this.visionBtn = document.getElementById('visionToggleBtn');
        this.status = document.getElementById('status');
        this.messages = document.getElementById('messages');
        this.userTranscript = document.getElementById('userTranscript');
        this.agentTranscript = document.getElementById('agentTranscript');
        this.roomNameInput = document.getElementById('roomName');
        this.participantNameInput = document.getElementById('participantName');
        this.energyOrb = document.getElementById('energyOrb');
        this.visionBtn = document.getElementById('visionToggleBtn');  // Используем одну переменную, соответствующую HTML
        this.textChatWindow = document.getElementById('textChatWindow');

        // Store current room and participant names
        this.currentRoomName = null;
        this.currentParticipantName = null;

        this.isMicEnabled = false;
        this.isCameraEnabled = false;
        this.isVisionEnabled = false;
        this.isConnected = false;
        this.localStream = null;
        this.reconnectAttempts = 0;
        this.maxReconnectAttempts = 3;
        this.reconnectDelay = 2000;

        // Audio analysis properties for energy orb animation
        this.audioContext = null;
        this.analyser = null;
        this.audioSource = null;
        this.animationFrameId = null;
        this.currentScale = 1.0;
        this.targetScale = 1.0;

        this.initEventListeners();
    }

    initEventListeners() {
        if (this.startSessionBtn) this.startSessionBtn.addEventListener('click', () => this.connect());
        if (this.micBtn) this.micBtn.addEventListener('click', () => this.toggleMic());
        if (this.cameraBtn) this.cameraBtn.addEventListener('click', () => this.toggleCamera());
        if (this.visionBtn) this.visionBtn.addEventListener('click', () => this.toggleVision());
        if (this.endSessionBtn) this.endSessionBtn.addEventListener('click', () => this.disconnect());

        // Add event listener for Gemini Pro button if it exists
        const geminiProButton = document.querySelector('.gemini-pro-button');
        if (geminiProButton) {
            geminiProButton.addEventListener('click', () => this.openGeminiApp());
        }
    }

    openGeminiApp() {
        const webUrl = "https://gemini.google.com/app";

        // Пытаемся открыть ссылку.
        // Если приложение установлено, оно перехватит этот URL.
        window.location.href = webUrl;
    }

    async connect() {
        // Показываем диалоговое окно чата
        if (this.textChatWindow) {
            this.textChatWindow.classList.remove('opacity-0', 'translate-y-10', 'pointer-events-none');
            this.textChatWindow.classList.add('opacity-100', 'translate-y-0');
        }

        const roomName = this.roomNameInput.value.trim() || 'default-room';
        const participantName = this.participantNameInput.value.trim() || 'user-' + Date.now();

        // Store current room and participant names
        this.currentRoomName = roomName;
        this.currentParticipantName = participantName;

        try {
            this.updateStatus('Requesting camera and microphone access...');
            this.setConnectionStatus('connecting');

            // Get user media for camera and microphone
            this.localStream = await navigator.mediaDevices.getUserMedia({
                video: {
                    width: { ideal: 1280 },
                    height: { ideal: 720 },
                    facingMode: 'user'
                },
                audio: {
                    echoCancellation: true,
                    noiseSuppression: true,
                    autoGainControl: true
                }
            });

            this.localVideo.srcObject = this.localStream;
            this.isCameraEnabled = true;
            this.isMicEnabled = true;
            if (this.cameraBtn) this.cameraBtn.classList.add('active');
            if (this.micBtn) this.micBtn.classList.add('active');

            this.updateStatus('Camera connected. Cleaning up existing connections...');

            // Cleanup existing connection if any
            if (this.room) {
                console.log('[DEBUG] Cleaning up existing room connection before new attempt...');
                try {
                    await this.room.disconnect();
                } catch (e) {
                    console.warn('[DEBUG] Room cleanup error:', e);
                }
                this.room = null;
            }

            // Get token from backend server
            const tokenData = await this.getToken(roomName, participantName);

            // Connect to LiveKit room
            await this.connectToLiveKit(tokenData, roomName, participantName);

            this.addMessage("Система инициализирована. Я слушаю.", "system");

        } catch (error) {
            console.error('Connection error:', error);
            this.updateStatus('Error: ' + error.message);
            this.setConnectionStatus('disconnected');
            this.addMessage('Connection failed: ' + error.message, 'error');
        }
    }

    getSettingsFromStorage() {
        // Read settings from localStorage
        const settings = {
            selected_voice_api: localStorage.getItem('selected_voice_api') || 'aoede',
            target_lang: localStorage.getItem('target_lang') || 'English',
            teacher_mode: localStorage.getItem('teacher_mode') === 'true',
            speech_speed: parseFloat(localStorage.getItem('speech_speed')) || 1.1
        };
        console.log('[DEBUG] Settings from localStorage:', settings);
        return settings;
    }

    async getToken(roomName, participantName) {
        try {
            // Get settings from localStorage
            const settings = this.getSettingsFromStorage();

            const response = await fetch('/token', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    room_name: roomName,
                    participant_name: participantName,
                    metadata: JSON.stringify(settings)
                })
            });

            if (!response.ok) {
                throw new Error(`Failed to get token: ${response.status}`);
            }

            const data = await response.json();
            console.log('[DEBUG] Token response:', data);
            console.log('[DEBUG] Token URL:', data.url);
            console.log('[DEBUG] Token value (first 50 chars):', data.token ? data.token.substring(0, 50) + '...' : 'null');
            return data;
        } catch (error) {
            console.error('Token fetch error:', error);
            throw new Error('Could not obtain access token. Please ensure the backend server is running.');
        }
    }

    async connectToLiveKit(tokenData, roomName, participantName) {
        try {
            console.log('[DEBUG] connectToLiveKit called with tokenData:', tokenData);
            console.log('[DEBUG] roomName:', roomName, 'participantName:', participantName);

            const url = tokenData.url;
            const token = tokenData.token;

            console.log('[DEBUG] Extracted URL:', url);
            console.log('[DEBUG] URL type:', typeof url);
            console.log('[DEBUG] URL format check - starts with wss://:', url ? url.startsWith('wss://') : 'null');
            console.log('[DEBUG] URL format check - starts with ws://:', url ? url.startsWith('ws://') : 'null');

            // Create LiveKit room connection
            const roomOptions = {
                adaptiveStream: true,
                dynacast: true,
                videoCaptureDefaults: {
                    resolution: {
                        width: 1280,
                        height: 720,
                        frameRate: 30
                    }
                },
                audioCaptureDefaults: {
                    autoGainControl: true,
                    echoCancellation: true,
                    noiseSuppression: true
                }
            };

            const connectOptions = {
                autoSubscribe: true,
                rtcConfiguration: {
                    iceServers: [
                        { urls: 'stun:stun.l.google.com:19302' }
                    ]
                }
            };

            // Connect to the room
            this.room = new LivekitClient.Room(roomOptions);

            // Set up room event listeners
            this.setupRoomEventListeners();

            console.log('[DEBUG] Calling room.connect with URL:', url);
            await this.room.connect(url, token, connectOptions);
            console.log('[DEBUG] room.connect succeeded');

            this.isConnected = true;
            this.reconnectAttempts = 0;
            this.setConnectionStatus('connected');
            this.updateStatus(`Connected to room: ${roomName}`);
            this.addMessage(`Joined room: ${roomName} as ${participantName}`, 'info');

            // Enable buttons
            this.startSessionBtn.disabled = true;
            if (this.micBtn) this.micBtn.disabled = false;
            if (this.cameraBtn) this.cameraBtn.disabled = false;
            this.visionBtn.disabled = false;
            this.endSessionBtn.disabled = false;

            // NEW: Wait for connected state if necessary
            if (this.room.state !== LivekitClient.RoomState.Connected) {
                console.log("[DEBUG] Waiting for room to reach 'connected' state...");
                await new Promise((resolve) => this.room.once(LivekitClient.RoomEvent.Connected, resolve));
            }

            try {
                await this.publishLocalTracks();

                // Automatically dispatch agent (Commented out for implicit dispatch)
                /*
                console.log("[DEBUG] Dispatching agent...");
                if (this.room.localParticipant.dispatchAgent) {
                    await this.room.localParticipant.dispatchAgent();
                    this.addMessage('Агент вызван автоматически', 'success');
                } else {
                    console.warn("[DEBUG] dispatchAgent not found on localParticipant. Ensure LiveKit SDK is up to date.");
                }
                */
            } catch (pErr) {
                console.error('[DEBUG] Error during post-connection setup:', pErr);
            }

        } catch (error) {
            console.error('[DEBUG] LiveKit connection error:', error);
            console.error('[DEBUG] Error message:', error.message);
            console.error('[DEBUG] Error stack:', error.stack);
            this.updateStatus('LiveKit connection failed: ' + error.message);
            this.setConnectionStatus('disconnected');
            throw error;
        }
    }

    // startAgent removed. We use room.localParticipant.dispatchAgent() now.

    setupRoomEventListeners() {
        // Room connected
        this.room.on(LivekitClient.RoomEvent.Connected, () => {
            console.log('[DEBUG] RoomEvent.Connected received');
            this.isConnected = true;
            this.setConnectionStatus('connected');
            this.addMessage('Connection stable.', 'success');
        });

        // Room disconnected
        this.room.on(LivekitClient.RoomEvent.Disconnected, (reason) => {
            console.log('Disconnected from room:', reason);
            this.isConnected = false;
            this.setConnectionStatus('disconnected');
            this.updateStatus('Disconnected from room');
            this.addMessage('Disconnected: ' + reason, 'warning');

            // Attempt reconnection if not intentional
            if (reason !== 'client_initiated' && this.reconnectAttempts < this.maxReconnectAttempts) {
                this.attemptReconnect();
            }
        });

        // Participant connected
        this.room.on(LivekitClient.RoomEvent.ParticipantConnected, (participant) => {
            console.log('Participant connected:', participant.identity);
            this.addMessage(`${participant.identity} joined the room`, 'info');
        });

        // Participant disconnected
        this.room.on(LivekitClient.RoomEvent.ParticipantDisconnected, (participant) => {
            console.log('Participant disconnected:', participant.identity);
            this.addMessage(`${participant.identity} left the room`, 'warning');

            // Clear remote video if this was the only participant
            if (this.remoteVideo.srcObject) {
                this.remoteVideo.srcObject = null;
            }
        });

        // Track subscribed
        this.room.on(LivekitClient.RoomEvent.TrackSubscribed, (track, publication, participant) => {
            console.log('Track subscribed:', track.kind, 'from', participant.identity);
            this.handleRemoteTrack(track, participant);
        });

        // Track unsubscribed
        this.room.on(LivekitClient.RoomEvent.TrackUnsubscribed, (track, publication, participant) => {
            console.log('Track unsubscribed:', track.kind, 'from', participant.identity);
            if (track.kind === 'video' && this.remoteVideo.srcObject) {
                this.remoteVideo.srcObject = null;
            }
            if (track.kind === 'audio') {
                // Stop energy orb animation when audio track is unsubscribed
                this.stopEnergyOrbAnimation();
            }
        });

        // Track published
        this.room.on(LivekitClient.RoomEvent.TrackPublished, (publication, participant) => {
            console.log('Track published:', publication.kind, 'by', participant.identity);
        });

        // Track muted/unmuted
        this.room.on(LivekitClient.RoomEvent.TrackMuted, (publication, participant) => {
            console.log('Track muted:', publication.kind, 'by', participant.identity);
            if (publication.kind === 'audio') {
                this.addMessage(`${participant.identity} muted their microphone`, 'info');
            }
        });

        this.room.on(LivekitClient.RoomEvent.TrackUnmuted, (publication, participant) => {
            console.log('Track unmuted:', publication.kind, 'by', participant.identity);
            if (publication.kind === 'audio') {
                this.addMessage(`${participant.identity} unmuted their microphone`, 'info');
            }
        });

        // Data received (for transcriptions)
        this.room.on(LivekitClient.RoomEvent.DataReceived, (data, participant) => {
            try {
                const message = JSON.parse(new TextDecoder().decode(data));
                this.handleDataMessage(message, participant);
            } catch (error) {
                console.error('Error parsing data message:', error);
            }
        });

        // Connection quality
        this.room.on(LivekitClient.RoomEvent.ConnectionQualityChanged, (quality) => {
            console.log('Connection quality:', quality);
            this.updateConnectionQuality(quality);
        });

        // Room metadata changed
        this.room.on(LivekitClient.RoomEvent.RoomMetadataChanged, (metadata) => {
            console.log('Room metadata changed:', metadata);
        });
    }

    async publishLocalTracks() {
        try {
            // Ensure we are in connected state. If we just connected, room.state might 
            // take a few milliseconds to update or might be in a stable state.
            if (this.room.state !== LivekitClient.RoomState.Connected) {
                console.log(`[DEBUG] Room state is ${this.room.state}, waiting for 'connected'...`);
                // Wait up to 2 seconds for connected state
                let attempts = 0;
                while (this.room.state !== LivekitClient.RoomState.Connected && attempts < 20) {
                    await new Promise(resolve => setTimeout(resolve, 100));
                    attempts++;
                }
            }

            if (this.room.state !== LivekitClient.RoomState.Connected) {
                console.warn('Room is not in connected state after waiting, skipping track publishing. Current state:', this.room.state);
                return;
            }

            // Publish video track
            if (this.localStream.getVideoTracks().length > 0) {
                await this.room.localParticipant.publishTrack(
                    this.localStream.getVideoTracks()[0],
                    {
                        name: 'camera',
                        simulcast: true
                    }
                );
                console.log('Video track published');
            }

            // Publish audio track
            if (this.localStream.getAudioTracks().length > 0) {
                await this.room.localParticipant.publishTrack(
                    this.localStream.getAudioTracks()[0],
                    {
                        name: 'microphone'
                    }
                );
                console.log('Audio track published');
            }

        } catch (error) {
            console.error('Error publishing tracks:', error);
            this.addMessage('Failed to publish tracks: ' + error.message, 'error');
        }
    }

    handleRemoteTrack(track, participant) {
        if (track.kind === 'video') {
            // Attach video track to remote video element
            track.attach(this.remoteVideo);
            this.addMessage(`Receiving video from ${participant.identity}`, 'info');
        } else if (track.kind === 'audio') {
            // Attach audio track to remote video element (for audio playback)
            track.attach(this.remoteVideo);
            this.addMessage(`Receiving audio from ${participant.identity}`, 'info');
            // Set up audio analysis for energy orb animation
            this.setupAudioAnalysis(track);
        }
    }

    setupAudioAnalysis(track) {
        try {
            // Create audio context if not already created
            if (!this.audioContext) {
                this.audioContext = new (window.AudioContext || window.webkitAudioContext)();
            }

            // Resume audio context if suspended (required by some browsers)
            if (this.audioContext.state === 'suspended') {
                this.audioContext.resume();
            }

            // Create analyser node
            this.analyser = this.audioContext.createAnalyser();
            this.analyser.fftSize = 256;
            this.analyser.smoothingTimeConstant = 0.8;

            // Get the media stream from the track
            const stream = new MediaStream([track.mediaStreamTrack]);

            // Create audio source from the stream
            this.audioSource = this.audioContext.createMediaStreamSource(stream);
            this.audioSource.connect(this.analyser);

            // Start animating the energy orb
            this.animateEnergyOrb();

            console.log('Audio analysis set up for energy orb animation');
        } catch (error) {
            console.error('Error setting up audio analysis:', error);
        }
    }

    animateEnergyOrb() {
        if (!this.analyser || !this.energyOrb) {
            return;
        }

        const dataArray = new Uint8Array(this.analyser.frequencyBinCount);

        const updateOrb = () => {
            if (!this.analyser || !this.energyOrb) {
                return;
            }

            // Get frequency data
            this.analyser.getByteFrequencyData(dataArray);

            // Calculate average volume
            let sum = 0;
            for (let i = 0; i < dataArray.length; i++) {
                sum += dataArray[i];
            }
            const averageVolume = sum / dataArray.length;

            // Normalize volume to 0-1 range
            const normalizedVolume = averageVolume / 255;

            // Calculate target scale based on volume
            if (normalizedVolume < 0.1) {
                this.targetScale = 1.0; // Low volume
            } else if (normalizedVolume < 0.3) {
                this.targetScale = 1.2; // Medium volume
            } else {
                this.targetScale = 1.5; // High volume
            }

            // Smooth transition to target scale
            const smoothingFactor = 0.1;
            this.currentScale += (this.targetScale - this.currentScale) * smoothingFactor;

            // Apply scale to energy orb
            this.energyOrb.style.transform = `scale(${this.currentScale})`;

            // Continue animation
            this.animationFrameId = requestAnimationFrame(updateOrb);
        };

        // Start the animation loop
        updateOrb();
    }

    stopEnergyOrbAnimation() {
        if (this.animationFrameId) {
            cancelAnimationFrame(this.animationFrameId);
            this.animationFrameId = null;
        }

        // Reset orb scale to default
        if (this.energyOrb) {
            this.energyOrb.style.transform = 'scale(1.0)';
        }

        this.currentScale = 1.0;
        this.targetScale = 1.0;
    }

    handleDataMessage(message, participant) {
        if (message.type === 'transcription') {
            if (message.role === 'user') {
                this.updateUserTranscript(message.text);
            } else if (message.role === 'agent') {
                this.updateAgentTranscript(message.text);
            }
        } else if (message.type === 'chat') {
            this.addMessage(`${message.text}`, 'chat', message.role || 'agent');
        }
    }

    updateUserTranscript(text) {
        this.userTranscript.textContent = text || '';
        this.userTranscript.parentElement.classList.toggle('active', !!text);
    }

    updateAgentTranscript(text) {
        this.agentTranscript.textContent = text || '';
        this.agentTranscript.parentElement.classList.toggle('active', !!text);
    }

    async toggleMic() {
        if (!this.room || !this.isConnected) return;

        try {
            if (this.isMicEnabled) {
                await this.room.localParticipant.setMicrophoneEnabled(false);
                this.isMicEnabled = false;
                if (this.micBtn) this.micBtn.classList.remove('active');
                this.addMessage('Microphone disabled', 'info');
            } else {
                await this.room.localParticipant.setMicrophoneEnabled(true);
                this.isMicEnabled = true;
                if (this.micBtn) this.micBtn.classList.add('active');
                this.addMessage('Microphone enabled', 'info');
            }
        } catch (error) {
            console.error('Error toggling microphone:', error);
            this.addMessage('Failed to toggle microphone: ' + error.message, 'error');
        }
    }

    async toggleCamera() {
        if (!this.room || !this.isConnected) return;

        try {
            if (this.isCameraEnabled) {
                await this.room.localParticipant.setCameraEnabled(false);
                this.isCameraEnabled = false;
                if (this.cameraBtn) this.cameraBtn.classList.remove('active');
                this.addMessage('Camera disabled', 'info');
            } else {
                await this.room.localParticipant.setCameraEnabled(true);
                this.isCameraEnabled = true;
                if (this.cameraBtn) this.cameraBtn.classList.add('active');
                this.addMessage('Camera enabled', 'info');
            }
        } catch (error) {
            console.error('Error toggling camera:', error);
            this.addMessage('Failed to toggle camera: ' + error.message, 'error');
        }
    }

    async toggleVision() {
        if (!this.room || !this.isConnected) return;

        try {
            // Toggle camera through LiveKit
            const isEnabled = !this.room.localParticipant.isCameraEnabled;
            await this.room.localParticipant.setCameraEnabled(isEnabled);

            const energyOrb = document.getElementById('energyOrb');
            const voiceIcon = document.getElementById('voiceIcon');
            const visionCamera = document.getElementById('visionCamera');
            const visionBtn = this.visionBtn;

            if (isEnabled) {
                // Effect of "Opening the Eye"
                if (visionCamera) {
                    visionCamera.classList.remove('hidden');
                    setTimeout(() => visionCamera.classList.remove('opacity-0'), 10);
                }
                if (voiceIcon) {
                    voiceIcon.classList.add('hidden');
                }

                // Change orb style: add neon outline
                if (energyOrb) {
                    energyOrb.classList.add('border-2', 'border-cyan-400', 'shadow-[0_0_30px_rgba(34,211,238,0.6)]');
                }
                if (visionBtn) {
                    visionBtn.classList.add('vision-on');
                    const iconElement = visionBtn.querySelector('.material-icons');
                    if (iconElement) {
                        iconElement.textContent = 'visibility';
                    }
                }

                this.isVisionEnabled = true;
                this.addMessage("Vision ACTIVATED: Агент смотрит через сферу 👁️", 'system');
            } else {
                // Return to voice mode
                if (visionCamera) {
                    visionCamera.classList.add('opacity-0');
                    setTimeout(() => {
                        visionCamera.classList.add('hidden');
                        if (voiceIcon) {
                            voiceIcon.classList.remove('hidden');
                        }
                    }, 500);
                }

                if (energyOrb) {
                    energyOrb.classList.remove('border-2', 'border-cyan-400', 'shadow-[0_0_30px_rgba(34,211,238,0.6)]');
                }
                if (visionBtn) {
                    visionBtn.classList.remove('vision-on');
                    const iconElement = visionBtn.querySelector('.material-icons');
                    if (iconElement) {
                        iconElement.textContent = 'visibility_off';
                    }
                }

                this.isVisionEnabled = false;
                this.addMessage("Vision DEACTIVATED: Агент только слушает 🌑", 'system');
            }
        } catch (error) {
            console.error('Error toggling vision:', error);
            this.addMessage('Failed to toggle vision: ' + error.message, 'error');
        }
    }

    async disconnect() {
        try {
            // Stop energy orb animation
            this.stopEnergyOrbAnimation();

            // Clean up audio context
            if (this.audioContext) {
                await this.audioContext.close();
                this.audioContext = null;
            }
            this.analyser = null;
            this.audioSource = null;

            if (this.room) {
                await this.room.disconnect();
                this.room = null;
            }

            if (this.localStream) {
                this.localStream.getTracks().forEach(track => track.stop());
                this.localStream = null;
            }

            this.localVideo.srcObject = null;
            this.remoteVideo.srcObject = null;

            this.isConnected = false;
            this.isMicEnabled = false;
            this.isCameraEnabled = false;
            this.isVisionEnabled = false;

            this.setConnectionStatus('disconnected');
            this.updateStatus('Disconnected');
            this.addMessage('Disconnected from room', 'info');

            // Hide chat window
            if (this.textChatWindow) {
                this.textChatWindow.classList.add('opacity-0', 'translate-y-10');
                this.textChatWindow.classList.remove('opacity-100', 'translate-y-0');
            }

            // Reset buttons
            this.startSessionBtn.disabled = false;
            if (this.micBtn) this.micBtn.disabled = true;
            if (this.cameraBtn) this.cameraBtn.disabled = true;
            this.visionBtn.disabled = true;
            this.endSessionBtn.disabled = true;
            if (this.micBtn) this.micBtn.classList.remove('active');
            if (this.cameraBtn) this.cameraBtn.classList.remove('active');

            // Reset vision button to OFF state
            this.visionBtn.classList.remove('vision-on');
            const iconElement = this.visionBtn.querySelector('.material-icons');
            if (iconElement) {
                iconElement.textContent = 'visibility_off';
            }

            // Clear transcriptions
            this.updateUserTranscript('');
            this.updateAgentTranscript('');

        } catch (error) {
            console.error('Disconnect error:', error);
            this.addMessage('Error during disconnect: ' + error.message, 'error');
        }
    }

    async attemptReconnect() {
        this.reconnectAttempts++;
        this.updateStatus(`Attempting to reconnect (${this.reconnectAttempts}/${this.maxReconnectAttempts})...`);

        setTimeout(async () => {
            if (!this.isConnected && this.reconnectAttempts <= this.maxReconnectAttempts) {
                try {
                    await this.connect();
                } catch (error) {
                    console.error('Reconnect attempt failed:', error);
                }
            }
        }, this.reconnectDelay);
    }

    updateStatus(text) {
        this.status.textContent = text;
    }

    setConnectionStatus(status) {
        // Update the status text in the navigation bar
        const statusBadge = document.querySelector('.status-badge span');
        if (statusBadge) {
            const statusText = {
                'connecting': 'Connecting...',
                'connected': 'Connected',
                'disconnected': 'Disconnected'
            };
            statusBadge.textContent = statusText[status] || status;
        }

        // Update the status indicator color
        const statusIndicator = document.querySelector('.status-badge .w-1\\.5, .status-badge .w-2');
        if (statusIndicator) {
            statusIndicator.className = statusIndicator.className.replace(/bg-\w+-\d+/, '');
            if (status === 'connected') {
                statusIndicator.classList.add('bg-green-500');
            } else if (status === 'connecting') {
                statusIndicator.classList.add('bg-yellow-500');
            } else { // disconnected
                statusIndicator.classList.add('bg-red-500');
            }
        }
    }

    updateConnectionQuality(quality) {
        const qualityIndicator = document.getElementById('qualityIndicator');
        if (qualityIndicator) {
            qualityIndicator.className = 'quality-indicator ' + quality;
            const qualityText = {
                'excellent': 'Excellent',
                'good': 'Good',
                'poor': 'Poor'
            };
            qualityIndicator.textContent = qualityText[quality] || quality;
        }
    }

    addMessage(text, type, role = 'agent') {
        const wrapper = document.createElement('div');
        wrapper.className = `flex w-full mb-1 ${role === 'user' ? 'justify-end' : 'justify-start'}`;

        const bubble = document.createElement('div');
        bubble.className = `px-4 py-2 rounded-2xl text-sm ${role === 'user'
            ? 'bg-primary text-white rounded-tr-none'
            : 'bg-white/10 text-cyan-5 border border-white/5 rounded-tl-none'
            }`;

        // Логи браузера помечаем иконкой
        bubble.textContent = text.startsWith('🌐') ? text : (role === 'user' ? `👤 ${text}` : `🤖 ${text}`);

        wrapper.appendChild(bubble);
        this.messages.appendChild(wrapper);
        this.messages.scrollTop = this.messages.scrollHeight;
    }
}

// Initialize app when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    window.mainApp = new OmniAgentApp();
});

// Also initialize immediately if DOM is already loaded
if (document.readyState === 'loading') {
    // Still loading, DOMContentLoaded will fire later
} else {
    // DOM is already loaded, initialize immediately
    window.mainApp = new OmniAgentApp();
}