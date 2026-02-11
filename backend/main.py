import os
import json
import asyncio
import base64
import sys
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from google import genai
from dotenv import load_dotenv

# --- Configuration ---
load_dotenv()

app = FastAPI()

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRONTEND_DIR = os.path.join(BASE_DIR, "frontend")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

# МОДЕЛЬ
# Если при деплое будет ошибка 1007 (Region not supported), попробуйте сменить на:
# MODEL_ID = "models/gemini-2.0-flash-exp"
MODEL_ID = "models/gemini-2.5-flash-native-audio-preview-12-2025"

if not GOOGLE_API_KEY:
    print("CRITICAL: GOOGLE_API_KEY is not set.")
    sys.stdout.flush()

# Маршрут WebSocket должен быть определен ДО монтирования статики
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    print(f"[PROXY] Client connected. Initializing session with {MODEL_ID}...")
    sys.stdout.flush()

    # Инициализация клиента Google
    client = genai.Client(api_key=GOOGLE_API_KEY, http_options={'api_version': 'v1alpha'})
    
    try:
        # === ИСПРАВЛЕННАЯ КОНФИГУРАЦИЯ ===
        # SDK требовал вынести поля response_modalities и speech_config 
        # напрямую в корень config, а не в generation_config.
        
        config = {
            "response_modalities": ["AUDIO"],
            "speech_config": {
                "voice_config": {
                    "prebuilt_voice_config": {
                        "voice_name": "Puck"
                    }
                }
            },
            "system_instruction": {
                "parts": [{"text": "Ты — дружелюбный ИИ-помощник Омни. Отвечай кратко и по делу."}]
            }
        }

        async with client.aio.live.connect(model=MODEL_ID, config=config) as session:
            print("[PROXY] Successfully connected to Google API.")
            await websocket.send_text(json.dumps({"server_content": {"setup_complete": {}}}))
            sys.stdout.flush()

            # === ЗАДАЧА 1: Google -> Клиент ===
            async def google_to_client():
                try:
                    async for response in session.receive():
                        content = getattr(response, 'server_content', None) or getattr(response, 'serverContent', None)
                        
                        if content:
                            if getattr(content, 'setup_complete', None):
                                continue

                            response_data = {
                                "serverContent": {
                                    "modelTurn": {
                                        "parts": []
                                    }
                                }
                            }
                            
                            model_turn = getattr(content, 'model_turn', None) or getattr(content, 'modelTurn', None)
                            if model_turn:
                                for part in model_turn.parts:
                                    part_dict = {}
                                    if hasattr(part, 'text') and part.text:
                                        part_dict["text"] = part.text
                                    
                                    inline_data = getattr(part, 'inline_data', None) or getattr(part, 'inlineData', None)
                                    if inline_data:
                                        part_dict["inlineData"] = {
                                            "data": base64.b64encode(inline_data.data).decode("utf-8"),
                                            "mimeType": inline_data.mime_type
                                        }
                                    
                                    if part_dict:
                                        response_data["serverContent"]["modelTurn"]["parts"].append(part_dict)
                            
                            if response_data["serverContent"]["modelTurn"]["parts"]:
                                await websocket.send_text(json.dumps(response_data))

                except Exception as e:
                    print(f"[ERROR] google_to_client error: {e}")
                    sys.stdout.flush()

            # === ЗАДАЧА 2: Клиент -> Google ===
            async def client_to_google():
                try:
                    while True:
                        data = await websocket.receive_text()
                        message = json.loads(data)
                        
                        if "realtimeInput" in message:
                            await session.send(message)
                        elif "client_content" in message:
                            await session.send(message)
                                
                except WebSocketDisconnect:
                    print("[PROXY] Client disconnected.")
                except Exception as e:
                    print(f"[ERROR] client_to_google error: {e}")
                sys.stdout.flush()

            await asyncio.gather(google_to_client(), client_to_google())

    except Exception as e_conn:
        error_msg = str(e_conn)
        print(f"\n[CRITICAL CONNECTION ERROR] {error_msg}")
        
        # Если ошибка региона, даем подсказку
        if "User location is not supported" in error_msg or "1007" in error_msg:
            print("Решение: Попробуйте сменить MODEL_ID на 'models/gemini-2.0-flash-exp' в коде.")
            print("Модель 2.5 может быть недоступна в регионе Oregon (us-west).")
        
        sys.stdout.flush()
        try:
            await websocket.close(code=1011)
        except:
            pass

# --- Serve Static Files (Frontend) ---
if os.path.exists(FRONTEND_DIR):
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5000)
