from livekit.agents import llm
import logging
from mem0 import MemoryClient

logger = logging.getLogger("memory-tools")

class UserFriendTools:
    def __init__(self):
        # Initialize Mem0 (assumes API key is in environment variables)
        self.memory = MemoryClient() 

    @llm.function_tool
    async def save_memory(self, fact: str):
        """Запоминает важные факты о пользователе: имена, питомцы, хобби, страхи, любимые фильмы и т.д."""
        logger.info(f"Saving fact: {fact}")
        # Logic to save to Mem0/Qdrant
        self.memory.add(fact, user_id="user_001") # Using a static user_id for now
        return "Я это запомнил!"

    @llm.function_tool
    async def search_memories(self, query: str):
        """Позволяет вспомнить информацию о пользователе, если он спрашивает или если это нужно для поддержания беседы."""
        logger.info(f"Searching memory for: {query}")
        memories = self.memory.search(query, user_id="user_001") # Using a static user_id for now
        if not memories:
            return "Я ничего не нашел по этому поводу."
        return f"Я нашел такие факты: {memories}"
