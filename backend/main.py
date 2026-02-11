import os
import json
import asyncio
import base64
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from google import genai
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

app = FastAPI()

# Configuration
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRONTEND_DIR = os.path.join(BASE_DIR, "frontend")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
MODEL_ID = "models/gemini-2.5-flash-native-audio-preview-12-2025"

if not GOOGLE_API_KEY:
    print("WARNING: GOOGLE_API_KEY is not set!")

@app.get("/")
async def get_index():
    index_path = os.path.join(FRONTEND_DIR, "index.html")
    if not os.path.exists(index_path):
        return {"error": f"Frontend index.html not found at {index_path}"}
    return FileResponse(index_path)

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    print("\n[PROXY] Клиент подключен")

    client = genai.Client(api_key=GOOGLE_API_KEY, http_options={'api_version': 'v1alpha'})
    
    try:
        print(f"[PROXY] Попытка подключения к Google Gemini ({MODEL_ID})...")
        
        # Обновленная конфигурация (параметры передаются напрямую)
        config = {
            "response_modalities": ["AUDIO"]
        }
        
        async with client.aio.live.connect(model=MODEL_ID, config=config) as session:
            print("[PROXY] Сессия с Google Gemini успешно установлена")
            
            async def google_to_client():
                """Forward messages from Gemini to the browser."""
                try:
                    async for message in session.receive():
                        if message.server_content:
                            response_data = {
                                "server_content": {
                                    "model_turn": {
                                        "parts": []
                                    }
                                }
                            }
                            
                            if message.server_content.model_turn:
                                for part in message.server_content.model_turn.parts:
                                    part_dict = {}
                                    if part.inline_data:
                                        part_dict["inline_data"] = {
                                            "data": base64.b64encode(part.inline_data.data).decode("utf-8"),
                                            "mime_type": part.inline_data.mime_type
                                        }
                                    if part.text:
                                        part_dict["text"] = part.text
                                    response_data["server_content"]["model_turn"]["parts"].append(part_dict)
                            
                            await websocket.send_text(json.dumps(response_data))
                except Exception as e:
                    print(f"[DEBUG] Ошибка в google_to_client: {e}")

            async def client_to_google():
                """Forward messages from the browser to Gemini."""
                try:
                    while True:
                        data = await websocket.receive_text()
                        message = json.loads(data)
                        
                        if "realtime_input" in message:
                            for chunk in message["realtime_input"]["media_chunks"]:
                                pcm_data = base64.b64decode(chunk["data"])
                                # Отправка в формате словаря для совместимости
                                await session.send({
                                    "realtime_input": {
                                        "media_chunks": [{
                                            "data": pcm_data,
                                            "mime_type": "audio/pcm;rate=16000"
                                        }]
                                    }
                                })
                        
                        elif "setup" in message:
                            print(f"[DEBUG] Получена настройка от клиента: {message['setup']}")
                except WebSocketDisconnect:
                    print("[PROXY] Клиент разорвал соединение")
                except Exception as e:
                    print(f"[DEBUG] Ошибка в client_to_google: {e}")

            # Запуск обоих задач параллельно
            await asyncio.gather(google_to_client(), client_to_google())

    except Exception as e:
        error_msg = str(e)
        print(f"\n[КРИТИЧЕСКАЯ ОШИБКА] Не удалось установить сессию с Google: {error_msg}")
        
        if "User location is not supported" in error_msg:
            print("!"*60)
            print("ОШИБКА: Твой регион не поддерживается Google Gemini Multimodal Live API.")
            print("РЕШЕНИЕ: Используй VPN локально или деплой на Render.")
            print("!"*60)
        
        await websocket.close()

# Serve static files
if os.path.exists(FRONTEND_DIR):
    app.mount("/", StaticFiles(directory=FRONTEND_DIR), name="static")

if __name__ == "__main__":
    import uvicorn
    # Запуск на порту 5000
    uvicorn.run(app, host="0.0.0.0", port=5000)
