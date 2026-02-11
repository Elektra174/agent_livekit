/**
 * Omni-Agent Frontend - Direct Connect Version
 * 
 * This version connects directly to Google Gemini Multimodal Live API 
 * via WebSockets from the browser.
 */

class DirectOmniAgentApp {
    constructor() {
        console.log('[DEBUG] DirectOmniAgentApp initializing...');

        // UI Elements
        this.energyOrb = document.getElementById('energyOrb');
        this.statusBadge = document.querySelector('.status-badge span');
        this.statusIndicator = document.querySelector('.status-badge .w-1\\.5, .status-badge .w-2');
        this.messages = document.getElementById('messages');
        this.startSessionBtn = document.getElementById('startSessionBtn');
        this.endSessionBtn = document.getElementById('endSessionBtn');
        this.visionToggleBtn = document.getElementById('visionToggleBtn');
        this.visionCamera = document.getElementById('visionCamera');
        this.voiceIcon = document.getElementById('voiceIcon');
        this.textChatWindow = document.getElementById('textChatWindow');

        // State
        this.ws = null;
        this.isConnected = false;
        this.isVisionEnabled = false;
        this.config = null;

        // Audio processing
        this.audioContext = null;
        this.processor = null;
        this.inputSource = null;
        this.audioWorkletNode = null;
        this.playbackBuffer = [];
        this.isPlaying = false;

        // Orb animation state
        this.analyser = null;
        this.animationFrameId = null;
        this.currentScale = 1.0;
        this.targetScale = 1.0;

        this.initEventListeners();
    }

    initEventListeners() {
        // Handlers are now managed by index.html to avoid duplicate calls.
        // We just keep the UI element references in the constructor.
    }

    async connect() {
        if (this.isConnected) return;

        try {
            this.setConnectionStatus('connecting');
            this.addMessage("Инициализация подключения...", "system");

            // 1. Request microphone access
            const stream = await navigator.mediaDevices.getUserMedia({
                audio: {
                    channelCount: 1,
                    sampleRate: 16000,
                    echoCancellation: true,
                    noiseSuppression: true
                }
            });

            // 2. Connect WebSocket to our local PROXY
            const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
            const url = `${protocol}//${window.location.host}/ws`;

            // Cleanup existing if any
            if (this.ws) {
                this.ws.onclose = null;
                this.ws.close();
            }

            this.ws = new WebSocket(url);

            this.ws.onopen = () => {
                console.log("[DEBUG] WebSocket opened to local proxy, readyState:", this.ws.readyState);

                if (this.ws.readyState !== WebSocket.OPEN) {
                    console.warn("[DEBUG] WebSocket NOT open yet despite onopen. Waiting...");
                    return;
                }

                this.isConnected = true;
                this.setConnectionStatus('connected');
                this.addMessage("Соединение установлено. Я слушаю!", "success");

                // Show chat window
                this.textChatWindow?.classList.remove('opacity-0', 'translate-y-10', 'pointer-events-none');

                // Send initial setup
                const savedLanguage = localStorage.getItem('target_lang') || 'Russian';
                const setupMessage = {
                    setup: {
                        system_instruction: {
                            parts: [{ text: `Ты — добрый и весёлый ИИ-друг для детей по имени Омни-Агент. Говори на языке: ${savedLanguage}. Говори просто, весело и подбадривающе.` }]
                        }
                    }
                };

                console.log("[DEBUG] Sending setup message to proxy...");
                this.ws.send(JSON.stringify(setupMessage));

                // Start audio processing
                this.initAudio(stream);
            };

            this.ws.onmessage = async (event) => {
                let data = event.data;
                if (data instanceof Blob) {
                    data = await data.text();
                }
                try {
                    const response = JSON.parse(data);
                    this.handleServerMessage(response);
                } catch (e) {
                    console.error("Failed to parse message:", data, e);
                }
            };

            this.ws.onclose = () => this.disconnect();
            this.ws.onerror = (err) => {
                console.error("WS Error:", err);
                this.addMessage("Ошибка соединения", "error");
            };

        } catch (error) {
            console.error("Session start error:", error);
            this.addMessage("Не удалось начать сессию: " + error.message, "error");
            this.setConnectionStatus('disconnected');
        }
    }

    async initAudio(stream) {
        this.audioContext = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: 16000 });

        // Input setup (Microphone)
        this.inputSource = this.audioContext.createMediaStreamSource(stream);

        // Using ScriptProcessor for simplicity in this migration (AudioWorklet is better but more complex to setup with external files)
        this.processor = this.audioContext.createScriptProcessor(2048, 1, 1);

        this.processor.onaudioprocess = (e) => {
            if (!this.isConnected || !this.ws || this.ws.readyState !== WebSocket.OPEN) return;

            const inputData = e.inputBuffer.getChannelData(0);
            // Convert Float32 to Int16 PCM
            const pcmData = this.float32ToInt16(inputData);

            // Send to Gemini
            const audioMessage = {
                realtime_input: {
                    media_chunks: [{
                        data: btoa(String.fromCharCode(...new Uint8Array(pcmData.buffer))),
                        mime_type: "audio/pcm"
                    }]
                }
            };

            try {
                this.ws.send(JSON.stringify(audioMessage));
            } catch (err) {
                console.error("[DEBUG] Failed to send audio:", err);
            }
        };

        this.inputSource.connect(this.processor);
        this.processor.connect(this.audioContext.destination);

        // Setup analyser for orb animation
        this.analyser = this.audioContext.createAnalyser();
        this.analyser.fftSize = 256;
        this.animateEnergyOrb();
    }

    handleServerMessage(response) {
        if (response.server_content) {
            const content = response.server_content;
            if (content.model_turn) {
                const parts = content.model_turn.parts;
                for (const part of parts) {
                    if (part.inline_data) {
                        this.queuePlayback(part.inline_data.data);
                    }
                    if (part.text) {
                        this.addMessage(part.text, "chat", "agent");
                    }
                }
            }
        }
    }

    queuePlayback(base64Audio) {
        const binaryString = atob(base64Audio);
        const bytes = new Uint8Array(binaryString.length);
        for (let i = 0; i < binaryString.length; i++) {
            bytes[i] = binaryString.charCodeAt(i);
        }

        const int16Array = new Int16Array(bytes.buffer);
        const float32Array = new Float32Array(int16Array.length);
        for (let i = 0; i < int16Array.length; i++) {
            float32Array[i] = int16Array[i] / 32768.0;
        }

        this.playbackBuffer.push(float32Array);
        if (!this.isPlaying) this.playNextChunk();
    }

    async playNextChunk() {
        if (this.playbackBuffer.length === 0) {
            this.isPlaying = false;
            this.targetScale = 1.0;
            return;
        }

        this.isPlaying = true;
        const chunk = this.playbackBuffer.shift();
        const buffer = this.audioContext.createBuffer(1, chunk.length, 16000);
        buffer.getChannelData(0).set(chunk);

        const source = this.audioContext.createBufferSource();
        source.buffer = buffer;
        source.connect(this.audioContext.destination);

        // Connect source to analyser for animation
        source.connect(this.analyser);

        source.onended = () => this.playNextChunk();
        source.start();

        this.targetScale = 1.5; // Scale up when speaking
    }

    float32ToInt16(buffer) {
        let l = buffer.length;
        let buf = new Int16Array(l);
        while (l--) {
            buf[l] = Math.min(1, buffer[l]) * 0x7FFF;
        }
        return buf;
    }

    disconnect() {
        this.isConnected = false;
        if (this.ws) this.ws.close();
        if (this.audioContext) this.audioContext.close();

        this.setConnectionStatus('disconnected');
        this.addMessage("Сессия завершена", "system");
        this.textChatWindow?.classList.add('opacity-0', 'translate-y-10');

        this.stopEnergyOrbAnimation();
    }

    toggleVision() {
        this.isVisionEnabled = !this.isVisionEnabled;
        if (this.isVisionEnabled) {
            navigator.mediaDevices.getUserMedia({ video: true }).then(stream => {
                this.visionCamera.srcObject = stream;
                this.visionCamera.classList.remove('hidden', 'opacity-0');
                this.voiceIcon.classList.add('hidden');
                this.energyOrb.classList.add('border-2', 'border-cyan-400');
            });
        } else {
            const stream = this.visionCamera.srcObject;
            if (stream) stream.getTracks().forEach(t => t.stop());
            this.visionCamera.classList.add('hidden', 'opacity-0');
            this.voiceIcon.classList.remove('hidden');
            this.energyOrb.classList.remove('border-2', 'border-cyan-400');
        }
    }

    animateEnergyOrb() {
        if (!this.analyser) return;
        const dataArray = new Uint8Array(this.analyser.frequencyBinCount);

        const update = () => {
            this.analyser.getByteFrequencyData(dataArray);
            let sum = dataArray.reduce((a, b) => a + b, 0);
            const avg = sum / dataArray.length;

            // Dynamic scaling based on actual audio volume
            const volumeScale = 1.0 + (avg / 128);
            this.currentScale += (volumeScale - this.currentScale) * 0.2;

            if (this.energyOrb) {
                this.energyOrb.style.transform = `scale(${this.currentScale})`;
            }
            this.animationFrameId = requestAnimationFrame(update);
        };
        update();
    }

    stopEnergyOrbAnimation() {
        if (this.animationFrameId) cancelAnimationFrame(this.animationFrameId);
        if (this.energyOrb) this.energyOrb.style.transform = 'scale(1)';
    }

    setConnectionStatus(status) {
        const text = { 'connected': 'Connected', 'connecting': 'Connecting...', 'disconnected': 'Disconnected' };
        if (this.statusBadge) this.statusBadge.textContent = text[status];

        if (this.statusIndicator) {
            this.statusIndicator.className = this.statusIndicator.className.replace(/bg-\w+-\d+/, '');
            const colors = { 'connected': 'bg-green-500', 'connecting': 'bg-yellow-500', 'disconnected': 'bg-red-500' };
            this.statusIndicator.classList.add(colors[status]);
        }
    }

    addMessage(text, type, role = 'agent') {
        const wrapper = document.createElement('div');
        wrapper.className = `flex w-full mb-1 ${role === 'user' ? 'justify-end' : 'justify-start'}`;
        const bubble = document.createElement('div');
        bubble.className = `px-4 py-2 rounded-2xl text-sm ${role === 'user' ? 'bg-primary text-white' : 'bg-white/10 text-cyan-5'}`;
        bubble.textContent = (role === 'user' ? "👤 " : "🤖 ") + text;
        wrapper.appendChild(bubble);
        this.messages.appendChild(wrapper);
        this.messages.scrollTop = this.messages.scrollHeight;
    }
}

document.addEventListener('DOMContentLoaded', () => {
    window.mainApp = new DirectOmniAgentApp();
});