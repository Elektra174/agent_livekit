/**
 * Omni-Agent Frontend - Client Version
 * 
 * Подключается к локальному прокси, который транслирует данные в Google.
 * Прокси берет на себя подключение к API (Server-Side Control).
 */

class DirectOmniAgentApp {
    constructor() {
        console.log('[DEBUG] DirectOmniAgentApp initializing...');

        // State
        this.ws = null;
        this.isConnected = false;
        this.isVisionEnabled = false;
        this.isReconnecting = false;
        this.reconnectAttempts = 0;
        this.maxReconnectAttempts = 5;
        this.resumptionToken = localStorage.getItem('gemini_resumption_token');

        // UI Elements
        this.energyOrb = document.getElementById('energyOrb');
        this.statusBadge = document.querySelector('.status-badge span');
        this.statusIndicator = document.querySelector('.status-badge .w-1\\.5, .status-badge .w-2');
        this.messages = document.getElementById('messages');
        this.chatMessages = document.getElementById('chatMessages');
        this.chatModal = document.getElementById('chatModal');
        this.closeChatBtn = document.getElementById('closeChatBtn');
        this.modalOverlay = document.getElementById('modalOverlay');

        // Audio Context
        this.audioContext = null;
        this.processor = null;
        this.inputSource = null;
        this.stream = null;
        this.playbackBuffer = [];
        this.isPlaying = false;

        // Animation
        this.analyser = null;
        this.animationFrameId = null;
        this.currentScale = 1.0;

        this.initEventListeners();
    }

    initEventListeners() {
        if (this.closeChatBtn) {
            this.closeChatBtn.onclick = () => this.hideChat();
        }
        if (this.modalOverlay) {
            this.modalOverlay.onclick = () => this.hideChat();
        }
    }

    showChat() {
        if (this.chatModal) {
            this.chatModal.classList.remove('hidden');
            document.body.style.overflow = 'hidden';
        }
    }

    hideChat() {
        if (this.chatModal) {
            this.chatModal.classList.add('hidden');
            document.body.style.overflow = '';
        }
    }

    async connect() {
        if (this.isConnected || (this.ws && this.ws.readyState === WebSocket.OPEN)) {
            return;
        }

        try {
            this.setConnectionStatus('connecting');
            if (!this.isReconnecting) {
                this.addMessage("Подключение к Омни...", "system");
                this.showChat();
            }

            // 1. Получаем доступ к микрофону если еще нет
            if (!this.stream) {
                this.stream = await navigator.mediaDevices.getUserMedia({
                    audio: {
                        channelCount: 1,
                        sampleRate: 16000,
                        echoCancellation: true,
                        noiseSuppression: true,
                        autoGainControl: true
                    }
                });
            }

            // 2. Открываем WebSocket к нашему серверу (Backend)
            const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
            const url = `${protocol}//${window.location.host}/ws`;

            if (this.ws) {
                this.ws.onclose = null;
                this.ws.onerror = null;
                this.ws.close();
            }

            this.ws = new WebSocket(url);

            this.ws.onopen = () => {
                console.log("[DEBUG] WebSocket connected.");
                this.isConnected = true;
                this.isReconnecting = false;
                this.reconnectAttempts = 0;

                // Отправляем setup с токеном возобновления, если он есть
                const setupMessage = {
                    setup: {}
                };
                if (this.resumptionToken) {
                    setupMessage.setup.resumption_handle = this.resumptionToken;
                }
                this.ws.send(JSON.stringify(setupMessage));

                // Запускаем обработку аудио с микрофона
                this.initAudio(this.stream);

                // Запускаем пинг для предотвращения таймаута на Render
                this.pingInterval = setInterval(() => {
                    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
                        this.ws.send(JSON.stringify({ client_content: { ping: true } }));
                    }
                }, 20000);
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
                    console.error("JSON Parse Error:", e);
                }
            };

            this.ws.onclose = () => {
                if (this.isConnected && !this.isReconnecting) {
                    this.handleDisconnect();
                }
            };
            this.ws.onerror = (err) => {
                console.error("WS Error:", err);
                this.addMessage("Ошибка соединения с сервером", "error");
                this.setConnectionStatus('disconnected');
            };

        } catch (error) {
            console.error("Connect Error:", error);
            this.addMessage("Ошибка: " + error.message, "error");
            this.setConnectionStatus('disconnected');
        }
    }

    async initAudio(stream) {
        // Gemini Multimodal Live API использует 24000 Гц для вывода
        this.audioContext = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: 24000 });
        this.inputSource = this.audioContext.createMediaStreamSource(stream);

        // Создаем ScriptProcessor для чтения аудио
        this.processor = this.audioContext.createScriptProcessor(2048, 1, 1);

        this.processor.onaudioprocess = (e) => {
            if (!this.isConnected || !this.ws || this.ws.readyState !== WebSocket.OPEN) return;

            const inputData = e.inputBuffer.getChannelData(0);
            const pcmData = this.float32ToInt16(inputData);

            // Формируем сообщение в формате realtimeInput
            const audioMessage = {
                realtimeInput: {
                    mediaChunks: [{
                        data: this.arrayBufferToBase64(pcmData.buffer),
                        mimeType: "audio/pcm;rate=24000"
                    }]
                }
            };

            try {
                this.ws.send(JSON.stringify(audioMessage));
            } catch (err) {
                // Игнорируем ошибки отправки, если сокет закрылся в процессе
            }
        };

        this.inputSource.connect(this.processor);
        this.processor.connect(this.audioContext.destination);

        // Анализатор для анимации
        this.analyser = this.audioContext.createAnalyser();
        this.analyser.fftSize = 256;
        this.inputSource.connect(this.analyser);
        this.animateEnergyOrb();
    }

    handleServerMessage(response) {
        // 1. Проверяем готовность сервера
        if (response.server_content && response.server_content.setup_complete) {
            this.setConnectionStatus('connected');
            if (!this.isReconnecting) {
                this.addMessage("Омни на связи!", "success");
            }
            return;
        }

        // 1.1 Токен возобновления
        if (response.serverContent && response.serverContent.resumptionToken) {
            this.resumptionToken = response.serverContent.resumptionToken;
            localStorage.setItem('gemini_resumption_token', this.resumptionToken);
            return;
        }

        // 1.2 Транскрипция ввода пользователя (VAD)
        if (response.serverContent && response.serverContent.inputTranscription) {
            const transcript = response.serverContent.inputTranscription.text;
            if (transcript) {
                this.addChatBubble(transcript, 'user');
            }
        }

        // 2. Обрабатываем контент (Текст или Аудио)
        // Примечание: backend отправляет camelCase (serverContent)
        if (response.serverContent && response.serverContent.modelTurn) {
            const parts = response.serverContent.modelTurn.parts;

            let textOutput = "";

            for (const part of parts) {
                if (part.inlineData && part.inlineData.data) {
                    // Добавляем аудио в очередь на воспроизведение
                    this.queuePlayback(part.inlineData.data);
                }
                if (part.text) {
                    textOutput += part.text;
                }
            }

            if (textOutput) {
                this.addMessage(textOutput, "chat", "agent");
                this.addChatBubble(textOutput, 'agent');
            }
        }
    }

    addChatBubble(text, role) {
        if (!this.chatMessages) return;

        const wrapper = document.createElement('div');
        wrapper.className = `flex w-full mb-4 animate-in slide-in-from-bottom-2 duration-300 ${role === 'user' ? 'justify-end' : 'justify-start'}`;

        const bubble = document.createElement('div');
        // Premium styles
        if (role === 'user') {
            bubble.className = "max-w-[85%] px-5 py-3 rounded-2xl bg-gradient-to-br from-primary to-purple-600 text-white shadow-lg text-sm leading-relaxed border border-white/10";
        } else {
            bubble.className = "max-w-[85%] px-5 py-3 rounded-2xl bg-white/5 backdrop-blur-md text-slate-100 shadow-md text-sm leading-relaxed border border-white/5";
        }

        bubble.textContent = text;
        wrapper.appendChild(bubble);
        this.chatMessages.appendChild(wrapper);
        this.chatMessages.scrollTop = this.chatMessages.scrollHeight;
    }

    handleDisconnect() {
        this.isConnected = false;
        if (this.reconnectAttempts < this.maxReconnectAttempts) {
            this.isReconnecting = true;
            this.reconnectAttempts++;
            const delay = Math.min(1000 * Math.pow(2, this.reconnectAttempts), 10000);
            this.setConnectionStatus('connecting');
            this.addMessage(`Связь прервана. Переподключение (${this.reconnectAttempts}/${this.maxReconnectAttempts})...`, "system");
            setTimeout(() => this.connect(), delay);
        } else {
            this.disconnect();
        }
    }

    queuePlayback(base64Audio) {
        try {
            const binaryString = atob(base64Audio);
            const bytes = new Uint8Array(binaryString.length);
            for (let i = 0; i < binaryString.length; i++) {
                bytes[i] = binaryString.charCodeAt(i);
            }

            // Превращаем байты в Int16 PCM, затем в Float32 для Web Audio API
            const int16Array = new Int16Array(bytes.buffer);
            const float32Array = new Float32Array(int16Array.length);
            for (let i = 0; i < int16Array.length; i++) {
                float32Array[i] = int16Array[i] / 32768.0;
            }

            this.playbackBuffer.push(float32Array);
            if (!this.isPlaying) this.playNextChunk();
        } catch (e) {
            console.error("Playback decoding error", e);
        }
    }

    async playNextChunk() {
        if (this.playbackBuffer.length === 0) {
            this.isPlaying = false;
            this.currentScale = 1.0; // Сброс анимации
            return;
        }

        this.isPlaying = true;
        const chunk = this.playbackBuffer.shift();
        // Указываем 24000, так как Gemini присылает данные именно в этой частоте
        const buffer = this.audioContext.createBuffer(1, chunk.length, 24000);
        buffer.getChannelData(0).set(chunk);

        const source = this.audioContext.createBufferSource();
        source.buffer = buffer;
        source.connect(this.audioContext.destination);

        // Анимация при воспроизведении
        this.targetScale = 1.5;

        source.onended = () => this.playNextChunk();
        source.start();
    }

    float32ToInt16(buffer) {
        const l = buffer.length;
        const buf = new Int16Array(l);
        for (let i = 0; i < l; i++) {
            // Ограничиваем диапазон и конвертируем
            let s = Math.max(-1, Math.min(1, buffer[i]));
            buf[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;
        }
        return buf;
    }

    arrayBufferToBase64(buffer) {
        let binary = '';
        const bytes = new Uint8Array(buffer);
        const len = bytes.byteLength;
        for (let i = 0; i < len; i++) {
            binary += String.fromCharCode(bytes[i]);
        }
        return window.btoa(binary);
    }

    disconnect() {
        this.isConnected = false;
        this.isReconnecting = false;
        this.reconnectAttempts = 0;
        if (this.ws) {
            this.ws.onclose = null;
            this.ws.close();
        }
        if (this.audioContext) this.audioContext.close();
        if (this.pingInterval) clearInterval(this.pingInterval);
        if (this.stream) {
            this.stream.getTracks().forEach(track => track.stop());
            this.stream = null;
        }

        this.setConnectionStatus('disconnected');
        this.addMessage("Сессия завершена", "system");
        this.stopEnergyOrbAnimation();
        this.hideChat();
    }

    toggleVision() {
        this.isVisionEnabled = !this.isVisionEnabled;
        if (this.isVisionEnabled) {
            navigator.mediaDevices.getUserMedia({ video: true }).then(stream => {
                this.visionCamera.srcObject = stream;
                this.visionCamera.classList.remove('hidden', 'opacity-0');
                this.voiceIcon?.classList.add('hidden');
                this.energyOrb?.classList.add('border-2', 'border-cyan-400');
            });
        } else {
            const stream = this.visionCamera.srcObject;
            if (stream) stream.getTracks().forEach(t => t.stop());
            this.visionCamera.classList.add('hidden', 'opacity-0');
            this.voiceIcon?.classList.remove('hidden');
            this.energyOrb?.classList.remove('border-2', 'border-cyan-400');
        }
    }

    animateEnergyOrb() {
        if (!this.analyser) return;
        const dataArray = new Uint8Array(this.analyser.frequencyBinCount);
        const update = () => {
            this.analyser.getByteFrequencyData(dataArray);
            let sum = 0;
            for (let i = 0; i < dataArray.length; i++) sum += dataArray[i];
            const avg = sum / dataArray.length;

            // Плавная анимация масштаба
            const volumeScale = 1.0 + (avg / 100);
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
        if (this.messages) {
            this.messages.appendChild(wrapper);
            this.messages.scrollTop = this.messages.scrollHeight;
        }
    }
}

document.addEventListener('DOMContentLoaded', () => {
    window.mainApp = new DirectOmniAgentApp();
});
