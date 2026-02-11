# Omni-Agent - Multimodal Voice Assistant

A sophisticated AI voice assistant with computer vision and long-term memory capabilities.

## Features

- 🎙️ **Real-time Voice Interaction**: Low-latency audio processing (~200-400ms)
- 👁️ **Computer Vision**: Analyzes video stream for gestures, objects, and text
- 🧠 **Long-term Memory**: Remembers user preferences, progress, and past conversations
- 🌍 **Multilingual**: Native support for all world languages
- 📚 **Teacher Mode**: Helps with language learning and pronunciation
- 🔍 **Real-time Search**: Google Search integration for current events

## Tech Stack

- **Models**: 
  - Gemini 2.5 Flash (audio/video)
  - Gemma 3 27B (text)
  - Gemini Embedding 001 (RAG)
- **Platform**: LiveKit Cloud (WebRTC)
- **Memory**: Mem0 + Qdrant Cloud
- **Backend**: Python 3.10+
- **Frontend**: Vanilla JS PWA

## Setup

### 1. Clone and Install

```bash
cd omni-agent
pip install -r requirements.txt
```

### 2. Get API Keys

- **Google AI**: https://aistudio.google.com/app/apikey
- **LiveKit**: https://cloud.livekit.io/
- **Mem0**: https://mem0.ai/
- **Qdrant**: https://cloud.qdrant.io/

### 3. Configure Environment

Copy `backend/.env` and add your API keys:

```env
GOOGLE_API_KEY=your_key_here
LIVEKIT_URL=wss://your-url.livekit.cloud
LIVEKIT_API_KEY=your_key
LIVEKIT_API_SECRET=your_secret
MEM0_API_KEY=your_key
QDRANT_URL=https://your-url.qdrant.io
QDRANT_API_KEY=your_key
```

### 4. Run Locally

```bash
# Terminal 1: Token server
cd backend && python server.py

# Terminal 2: Agent
cd backend && python agent.py

# Open frontend/index.html in browser
```

## Deployment

Deploy to Render using `render.yaml`:

```bash
render.yaml
```

## Project Structure

```
omni-agent/
├── backend/
│   ├── agent.py      # Main agent with LiveKit + Gemini + Mem0
│   ├── server.py     # Flask token server
│   └── .env          # Environment variables
├── frontend/
│   ├── index.html    # PWA interface
│   ├── app.js        # LiveKit client logic
│   └── style.css     # Styling
├── render.yaml       # Deployment config
└── README.md         # This file
```

## License

MIT
