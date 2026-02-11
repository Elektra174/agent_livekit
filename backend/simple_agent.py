"""
Simple LiveKit Agent - Direct connection to LiveKit room
This agent connects to a LiveKit room and responds to user audio
"""

import os
import asyncio
from dotenv import load_dotenv
from livekit import rtc
from google import genai
from google.genai import types

load_dotenv()

class SimpleLiveKitAgent:
    def __init__(self):
        self.url = os.getenv("LIVEKIT_URL")
        self.api_key = os.getenv("LIVEKIT_API_KEY")
        self.api_secret = os.getenv("LIVEKIT_API_SECRET")
        self.room_name = "default-room"
        self.participant_name = "omni-agent"
        
        # Initialize Google GenAI client
        self.client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))
        
        self.room = None
        self.audio_track = None
        
    async def connect(self):
        """Connect to LiveKit room"""
        print(f"Connecting to LiveKit room: {self.room_name}")
        
        # Create room
        self.room = rtc.Room()
        
        # Set up event handlers (synchronous callbacks)
        self.room.on("track_subscribed", self.on_track_subscribed_sync)
        self.room.on("participant_connected", self.on_participant_connected_sync)
        self.room.on("participant_disconnected", self.on_participant_disconnected_sync)
        
        # Connect to room
        token = self._generate_token()
        await self.room.connect(self.url, token)
        
        print(f"Connected to room: {self.room.name}")
        print(f"Room SID: {await self.room.sid}")
        
        # Skip audio track publishing for now
        # await self.publish_audio()
        
        # Keep running
        print("Agent is running. Press Ctrl+C to stop.")
        print("Listening for user audio...")
        try:
            while True:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            print("\nShutting down...")
            await self.disconnect()
    
    def _generate_token(self):
        """Generate LiveKit access token"""
        from livekit import api
        token = api.AccessToken(self.api_key, self.api_secret) \
            .with_identity(self.participant_name) \
            .with_name(self.participant_name) \
            .with_grants(api.VideoGrants(
                room_join=True,
                room=self.room_name,
                can_publish=True,
                can_subscribe=True,
            ))
        return token.to_jwt()
    
    async def publish_audio(self):
        """Publish audio track to room"""
        # Create audio track with required info
        from livekit.rtc import LocalAudioTrack as LAT
        # Use the int value for SOURCE_MICROPHONE (2)
        self.audio_track = LAT.create_audio_track("omni-agent-audio", 2)
        
        # Publish to room
        publication = await self.room.local_participant.publish_track(
            self.audio_track,
            2
        )
        
        print(f"Published audio track: {publication.sid}")
    
    def on_track_subscribed_sync(self, track, publication, participant):
        """Synchronous callback for track subscription"""
        print(f"Track subscribed: {track.kind} from {participant.identity}")
        
        if track.kind == rtc.TrackKind.KIND_AUDIO:
            # Process audio from user in async task
            asyncio.create_task(self.process_audio(track))
    
    async def on_track_subscribed(self, track, publication, participant):
        """Handle when a track is subscribed"""
        print(f"Track subscribed: {track.kind} from {participant.identity}")
        
        if track.kind == rtc.TrackKind.AUDIO:
            # Process audio from user
            await self.process_audio(track)
    
    async def process_audio(self, audio_track):
        """Process audio from user and generate response"""
        print("Processing audio from user...")
        
        # Read audio frames
        async for frame in audio_track:
            # Convert audio to text (simplified)
            # In a real implementation, you would use STT here
            print(f"Received audio frame: {frame}")
            
            # Generate response using Google GenAI
            response = await self.generate_response("Hello from user")
            
            # Send response as audio
            await self.send_audio_response(response)
    
    async def generate_response(self, text):
        """Generate response using Google GenAI"""
        print(f"Generating response for: {text}")
        
        response = self.client.models.generate_content(
            model="models/gemini-2.5-flash",
            contents=text
        )
        
        return response.text
    
    async def send_audio_response(self, text):
        """Send audio response to room"""
        print(f"Sending audio response: {text}")
        
        # In a real implementation, you would convert text to audio here
        # For now, just log the response
        pass
    
    def on_participant_connected_sync(self, participant):
        """Synchronous callback for participant connection"""
        print(f"Participant connected: {participant.identity}")
    
    def on_participant_disconnected_sync(self, participant):
        """Synchronous callback for participant disconnection"""
        print(f"Participant disconnected: {participant.identity}")
    
    async def on_participant_connected(self, participant):
        """Handle when a participant connects"""
        print(f"Participant connected: {participant.identity}")
    
    async def on_participant_disconnected(self, participant):
        """Handle when a participant disconnects"""
        print(f"Participant disconnected: {participant.identity}")
    
    async def disconnect(self):
        """Disconnect from room"""
        if self.room:
            await self.room.disconnect()
            print("Disconnected from room")

async def main():
    """Main entry point"""
    agent = SimpleLiveKitAgent()
    await agent.connect()

if __name__ == "__main__":
    asyncio.run(main())
