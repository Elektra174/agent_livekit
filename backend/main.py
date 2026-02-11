import asyncio
import os
import sys
import traceback
import pyaudio
import numpy as np
from google import genai
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Audio configuration
FORMAT = pyaudio.paInt16
CHANNELS = 1
RATE = 16000 # Recommended rate for Gemini audio
CHUNK = 1024 # Buffer size

# System Prompt
SYSTEM_PROMPT = """Ты — добрый и весёлый ИИ-друг для детей по имени Омни-Агент.
Твоя задача — быть тёплым, поддерживающим и интересным собеседником.
Говори просто, весело и подбадривающе.
Твой голос должен выражать эмоции: смейся, меняй интонацию.
"""

class DirectOmniAgent:
    def __init__(self):
        self.client = genai.Client(
            api_key=os.getenv("GOOGLE_API_KEY"),
            http_options={'api_version': 'v1alpha'}
        )
        self.p = pyaudio.PyAudio()
        self.model_id = "models/gemini-2.5-flash-native-audio-preview-12-2025"
        
        # Audio streams
        self.input_stream = None
        self.output_stream = None

    def _setup_audio(self):
        """Initialize microphone and speaker streams."""
        print(f"[*] Initializing audio at {RATE}Hz...")
        self.input_stream = self.p.open(
            format=FORMAT,
            channels=CHANNELS,
            rate=RATE,
            input=True,
            frames_per_buffer=CHUNK
        )
        self.output_stream = self.p.open(
            format=FORMAT,
            channels=CHANNELS,
            rate=RATE,
            output=True,
            frames_per_buffer=CHUNK
        )

    async def _send_audio_loop(self, session):
        """Continuously read from microphone and send to Gemini."""
        print("[*] Listening... (Speak now)")
        try:
            while True:
                data = self.input_stream.read(CHUNK, exception_on_overflow=False)
                # Send as bytes for the live connect session using send_realtime_input
                await session.send_realtime_input(audio=data)
                await asyncio.sleep(0) # Yield for other tasks
        except Exception as e:
            print(f"[!] Error in send loop: {e}")

    async def _receive_audio_loop(self, session):
        """Continuously receive responses from Gemini and play them."""
        print("[*] Ready to receive responses...")
        try:
            async for message in session.receive():
                if message.server_content and message.server_content.model_turn:
                    parts = message.server_content.model_turn.parts
                    for part in parts:
                        if part.inline_data:
                            # Play the audio data received from Gemini
                            audio_data = part.inline_data.data
                            self.output_stream.write(audio_data)
                
                # Turn signaling or other message types can be handled here
        except Exception as e:
            print(f"[!] Error in receive loop: {e}")
            traceback.print_exc()

    async def run(self):
        """Start the live session."""
        self._setup_audio()
        
        config = {
            "system_instruction": SYSTEM_PROMPT,
            "generation_config": {
                "response_modalities": ["audio"]
            }
        }

        print(f"[*] Connecting to {self.model_id}...")
        try:
            async with self.client.aio.live.connect(model=self.model_id, config=config) as session:
                # Run send and receive loops concurrently
                await asyncio.gather(
                    self._send_audio_loop(session),
                    self._receive_audio_loop(session)
                )
        except Exception as e:
            print(f"[!] Connection failed: {e}")
        finally:
            self._cleanup()

    def _cleanup(self):
        """Stop and close all streams."""
        print("[*] Cleaning up audio streams...")
        if self.input_stream:
            self.input_stream.stop_stream()
            self.input_stream.close()
        if self.output_stream:
            self.output_stream.stop_stream()
            self.output_stream.close()
        self.p.terminate()

if __name__ == "__main__":
    agent = DirectOmniAgent()
    try:
        asyncio.run(agent.run())
    except KeyboardInterrupt:
        print("\n[*] Agent stopped by user.")
