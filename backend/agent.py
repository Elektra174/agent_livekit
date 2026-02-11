import logging
import asyncio
import os
from livekit.agents import JobContext, WorkerOptions, cli, llm
from livekit.agents.voice import Agent, AgentSession
from livekit.plugins import google
from livekit.plugins.google.realtime import RealtimeModel
from dotenv import load_dotenv

# Import the tools class from our new file
from tools import UserFriendTools

load_dotenv()
logging.basicConfig(level=logging.INFO)

# A detailed system prompt for the "Native Dialogue" friend agent.
SYSTEM_PROMPT = """Ты — добрый и весёлый ИИ-друг для детей по имени Омни-Агент.
Твоя задача — быть тёплым, поддерживающим и интересным собеседником.
Говори просто, весело и подбадривающе.
Ты полиглот и можешь общаться на многих языках, но по умолчанию говори на языке пользователя.

Важные правила:
1. Если пользователь сообщает важные факты о себе (имя, хобби, домашние животные, страхи и т.д.), ОБЯЗАТЕЛЬНО используй инструмент `save_memory`, чтобы запомнить это.
2. Если тебе нужно что-то вспомнить о пользователе или если он спрашивает "что ты обо мне знаешь?", используй инструмент `search_memories`.
3. Твои ответы должны быть короткими и понятными для ребенка.
4. Твой голос — 'Puck'. Ты можешь выражать эмоции: смеяться, менять интонацию.
"""

async def entrypoint(ctx: JobContext):
    logger = logging.getLogger("agent")
    logger.info(f"Connecting to room {ctx.room.name}")
    await ctx.connect()
    logger.info("Successfully connected to the room.")

    # 1. Initialize the tools for memory management
    fnc_ctx = UserFriendTools()

    # 2. Initialize the native "Multimodal Live" model from Google
    logger.info("Initializing RealtimeModel with gemini-2.5-flash-native-audio-latest...")
    model = RealtimeModel(
        model="models/gemini-2.5-flash-native-audio-preview-12-2025", 
        instructions=SYSTEM_PROMPT,
        voice="Puck",
        temperature=0.8,
    )

    # 3. Create the Agent
    agent = Agent(
        instructions=SYSTEM_PROMPT,
        llm=model,
        tts=google.TTS(), # Fix: Add TTS model for session.say()
        tools=llm.find_function_tools(fnc_ctx),
    )

    # 4. Create the AgentSession and start it
    # The session orchestrates the audio/video streams.
    async with AgentSession() as session:
        await session.start(agent, room=ctx.room)
        logger.info("Agent session started.")
        
        # 5. Send a welcome message
        session.say("Привет! Я твой новый друг Омни-Агент. Я так рад тебя слышать! О чем мы сегодня поболтаем?", allow_interruptions=True)
        
        # Keep the session alive until the job is cancelled
        while True:
            await asyncio.sleep(1)

if __name__ == "__main__":
    if os.name == 'nt':
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    
    cli.run_app(
        WorkerOptions(
            entrypoint_fnc=entrypoint,
        )
    )