import asyncio
import sys
import os
from dotenv import load_dotenv

# Загружаем переменные окружения
load_dotenv()

from livekit.agents import cli, WorkerOptions
from agent import entrypoint

if __name__ == "__main__":
    # Fix for Windows and Python 3.12+ (asyncio loop handling & Proactor policy)
    if os.name == 'nt':
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

    # Workaround for Python 3.12+ where get_event_loop() doesn't create a loop
    try:
        asyncio.get_event_loop()
    except RuntimeError:
        asyncio.set_event_loop(asyncio.new_event_loop())

    # Запускаем агента с указанием точки входа
    try:
        cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint))
    except KeyboardInterrupt:
        print("Агент остановлен пользователем")
    except Exception as e:
        print(f"Ошибка при запуске агента: {e}")
        sys.exit(1)