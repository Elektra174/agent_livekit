import os
import json
import asyncio
import base64
import sys
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from google import genai
from dotenv import load_dotenv

# --- Configuration ---
load_dotenv()

app = FastAPI()

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRONTEND_DIR = os.path.join(BASE_DIR, "frontend")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

# СТРОГО ЗАДАННАЯ МОДЕЛЬ
MODEL_ID = "models/gemini-2.5-flash-native-audio-preview-12-2025"

if not GOOGLE_API_KEY:
    print("CRITICAL: GOOGLE_API_KEY is not set.")
    sys.stdout.flush()

@app.get("/")
async def get_index():
    index_path = os.path.join(FRONTEND_DIR, "index.html")
    if not os.path.exists(index_path):
        return {"error": f"Frontend index.html not found at {index_path}"}
    return FileResponse(index_path)

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    print(f"[PROXY] Client connected. Initializing session with {MODEL_ID}...")
    sys.stdout.flush()

    # Инициализация клиента Google
    # v1alpha требуется для Live API функций
    client = genai.Client(api_key=GOOGLE_API_KEY, http_options={'api_version': 'v1alpha'})
    
    try:
        # === СЕРВЕРНАЯ ИНИЦИАЛИЗАЦИЯ (SERVER-SIDE CONTROL) ===
        # Мы создаем сессию здесь, на сервере.
        # Это гарантирует, что Google видит IP сервера (Oregon), а не клиента.
        
        config = {
            "generation_config": {
                "response_modalities": ["AUDIO"], # Запрашиваем только аудио
                "speech_config": {
                    "voice_config": {
                        "prebuilt_voice_config": {
                            "voice_name": "Puck" # Можно изменить на Aoede, Charon, etc.
                        }
                    }
                }
            },
            "system_instruction": {
                "parts": [{"text": "Ты — дружелюбный ИИ-помощник Омни. Отвечай кратко и по делу."}]
            }
        }

        async with client.aio.live.connect(model=MODEL_ID, config=config) as session:
            print("[PROXY] Successfully connected to Google API.")
            
            # Отправляем клиенту сигнал, что мы готовы слушать
            await websocket.send_text(json.dumps({"server_content": {"setup_complete": {}}}))
            sys.stdout.flush()

            # === ЗАДАЧА 1: Google -> Клиент ===
            async def google_to_client():
                try:
                    async for response in session.receive():
                        # SDK возвращает объект response
                        content = getattr(response, 'server_content', None) or getattr(response, 'serverContent', None)
                        
                        if content:
                            # Если это setup_complete, игнорируем (мы уже отправили)
                            if getattr(content, 'setup_complete', None):
                                continue

                            # Подготовка данных для отправки браузеру
                            # Используем camelCase ключи, как принято в JSON API
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
                                    
                                    # Текст
                                    if hasattr(part, 'text') and part.text:
                                        part_dict["text"] = part.text
                                    
                                    # Аудио (inlineData)
                                    inline_data = getattr(part, 'inline_data', None) or getattr(part, 'inlineData', None)
                                    if inline_data:
                                        # Конвертируем байты в base64 строку
                                        part_dict["inlineData"] = {
                                            "data": base64.b64encode(inline_data.data).decode("utf-8"),
                                            "mimeType": inline_data.mime_type
                                        }
                                    
                                    if part_dict:
                                        response_data["serverContent"]["modelTurn"]["parts"].append(part_dict)
                            
                            # Отправляем JSON в браузер
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
                        
                        # Пробрасываем реальный ввод (аудио/текст) в Google
                        # Клиент использует camelCase (realtimeInput), SDK может принять это
                        if "realtimeInput" in message:
                            await session.send(message)
                        elif "client_content" in message: # На случай старого формата
                            await session.send(message)
                                
                except WebSocketDisconnect:
                    print("[PROXY] Client disconnected.")
                except Exception as e:
                    print(f"[ERROR] client_to_google error: {e}")
                sys.stdout.flush()

            # Запускаем обе задачи параллельно
            await asyncio.gather(google_to_client(), client_to_google())

    except Exception as e_conn:
        error_msg = str(e_conn)
        print(f"\n[CRITICAL CONNECTION ERROR] {error_msg}")
        
        if "User location is not supported" in error_msg:
            print("Region check failed even with server-side connection.")
            print("Ensure Render server is in a supported region (e.g., Oregon).")
        
        sys.stdout.flush()
        try:
            await websocket.close(code=1011)
        except:
            pass

# Serve static files
if os.path.exists(FRONTEND_DIR):
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5000)
