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

# Load environment variables
load_dotenv()

app = FastAPI()

# Configuration
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRONTEND_DIR = os.path.join(BASE_DIR, "frontend")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

# Model from the working "Джун" project
MODEL_ID = "models/gemini-2.0-flash-exp" 

if not GOOGLE_API_KEY:
    print("WARNING: GOOGLE_API_KEY is not set!")
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
    print("\n[PROXY] Клиент подключен")
    sys.stdout.flush()

    # Use v1beta for live features
    client = genai.Client(api_key=GOOGLE_API_KEY, http_options={'api_version': 'v1beta'})
    
    try:
        print(f"[PROXY] Попытка подключения к Google Gemini ({MODEL_ID})...")
        sys.stdout.flush()
        
        # We pass the essential config here to satisfy the SDK and Gemini
        config = {"response_modalities": ["AUDIO"]}
        
        try:
            async with client.aio.live.connect(model=MODEL_ID, config=config) as session:
                print("[PROXY] Сессия с Google Gemini успешно установлена")
                sys.stdout.flush()
                
                # This flag ensures we don't send the setup twice if the client sends one
                setup_sent_to_google = True 

                async def google_to_client():
                    """Forward messages from Gemini to the browser."""
                    try:
                        async for message in session.receive():
                            content = getattr(message, 'server_content', None) or getattr(message, 'serverContent', None)
                            
                            if content:
                                # Forward setup_complete to client so it knows we are ready
                                if getattr(content, 'setup_complete', None) or getattr(content, 'setupComplete', None):
                                    await websocket.send_text(json.dumps({"server_content": {"setup_complete": {}}}))
                                    continue

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
                        sys.stdout.flush()

                async def client_to_google():
                    """Forward messages from the browser to Gemini."""
                    nonlocal setup_sent_to_google
                    try:
                        while True:
                            data = await websocket.receive_text()
                            message = json.loads(data)
                            
                            if "setup" in message:
                                if setup_sent_to_google:
                                    print("[DEBUG] Клиент прислал setup, но сессия уже инициализирована. Игнорируем дубликат.")
                                else:
                                    print(f"[DEBUG] Пересылка setup от клиента: {message['setup']}")
                                    await session.send(message)
                                    setup_sent_to_google = True
                                sys.stdout.flush()
                            
                            elif "realtime_input" in message or "realtimeInput" in message:
                                await session.send(message)
                            elif "client_content" in message or "clientContent" in message:
                                await session.send(message)
                                
                    except WebSocketDisconnect:
                        print("[PROXY] Клиент разорвал соединение")
                    except Exception as e:
                        print(f"[DEBUG] Ошибка в client_to_google: {e}")
                    sys.stdout.flush()

                # Run both tasks concurrently
                await asyncio.gather(google_to_client(), client_to_google())

        except Exception as e_conn:
            print(f"\n[КРИТИЧЕСКАЯ ОШИБКА ПОДКЛЮЧЕНИЯ] Ошибка при открытии сокета Google: {e_conn}")
            print(f"[DEBUG] Тип ошибки: {type(e_conn)}")
            sys.stdout.flush()
            raise e_conn

    except Exception as e:
        error_msg = str(e)
        if "User location is not supported" in error_msg:
            print("\n" + "!"*60)
            print("ОШИБКА: Твой регион не поддерживается Google Gemini Multimodal Live API.")
            print("!"*60 + "\n")
        sys.stdout.flush()
        try:
            await websocket.close()
        except:
            pass

# Serve static files
if os.path.exists(FRONTEND_DIR):
    app.mount("/", StaticFiles(directory=FRONTEND_DIR), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5000)
