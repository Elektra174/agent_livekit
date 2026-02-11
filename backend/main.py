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
# Using v1beta as per working project "Джун"
MODEL_ID = "models/gemini-2.0-flash-exp" # Adjusted to a known live model if needed, but keeping user's choice if it works

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

    # Use v1beta for better compatibility with live features
    client = genai.Client(api_key=GOOGLE_API_KEY, http_options={'api_version': 'v1beta'})
    
    try:
        print(f"[PROXY] Попытка подключения к Google Gemini...")
        
        # We start with empty config and wait for 'setup' from client
        async with client.aio.live.connect(model="gemini-2.0-flash-exp") as session:
            print("[PROXY] Сессия с Google Gemini успешно установлена")
            
            async def google_to_client():
                """Forward messages from Gemini to the browser."""
                try:
                    async for message in session.receive():
                        # Support both server_content and serverContent (SDK variability)
                        content = getattr(message, 'server_content', None) or getattr(message, 'serverContent', None)
                        
                        if content:
                            response_data = {
                                "server_content": {
                                    "model_turn": {
                                        "parts": []
                                    }
                                }
                            }
                            
                            model_turn = getattr(content, 'model_turn', None) or getattr(content, 'modelTurn', None)
                            if model_turn:
                                for part in model_turn.parts:
                                    part_dict = {}
                                    inline_data = getattr(part, 'inline_data', None) or getattr(part, 'inlineData', None)
                                    if inline_data:
                                        part_dict["inline_data"] = {
                                            "data": base64.b64encode(inline_data.data).decode("utf-8"),
                                            "mime_type": inline_data.mime_type
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
                        
                        # Forward 'setup' message directly to Gemini
                        if "setup" in message:
                            print(f"[DEBUG] Пересылка setup от клиента: {message['setup']}")
                            await session.send(message)
                        
                        # Forward 'realtime_input' directly
                        elif "realtime_input" in message or "realtimeInput" in message:
                            # The latest SDK expects the whole message structure
                            await session.send(message)
                            
                        # Handle other types of content (client_content, etc.)
                        elif "client_content" in message or "clientContent" in message:
                            await session.send(message)
                            
                except WebSocketDisconnect:
                    print("[PROXY] Клиент разорвал соединение")
                except Exception as e:
                    print(f"[DEBUG] Ошибка в client_to_google: {e}")

            # Запуск обоих задач параллельно
            await asyncio.gather(google_to_client(), client_to_google())

    except Exception as e:
        error_msg = str(e)
        print(f"\n[КРИТИЧЕСКАЯ ОШИБКА] Не удалось установить сессию: {error_msg}")
        await websocket.close()

# Serve static files
if os.path.exists(FRONTEND_DIR):
    app.mount("/", StaticFiles(directory=FRONTEND_DIR), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5000)
