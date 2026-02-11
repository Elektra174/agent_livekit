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

MODEL_ID = "models/gemini-2.5-flash-native-audio-preview-12-2025"

if not GOOGLE_API_KEY:
    print("CRITICAL: GOOGLE_API_KEY is not set.")
    sys.exit(1)

# Настройка клиента Gemini (New SDK)
client = genai.Client(
    api_key=GOOGLE_API_KEY,
    http_options={'api_version': 'v1alpha'}
)

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    print(f"[PROXY] Client connected. Model: {MODEL_ID}")
    sys.stdout.flush()

    try:
        config = {
            "system_instruction": "Ты — дружелюбный ИИ-помощник Омни. Отвечай кратко и по делу. Ты общаешься голосом, поэтому твои ответы должны быть разговорными.",
            "response_modalities": ["AUDIO"],
            "speech_config": {
                "voice_config": {
                    "prebuilt_voice_config": {
                        "voice_name": "Puck"
                    }
                }
            },
            # Автоматическое сжатие контекста при превышении 20 000 токенов
            "context_window_compression": {
                "sliding_window": {},
                "trigger_tokens": 20000
            }
        }

        # Проверяем, прислал ли клиент токен для восстановления сессии
        initial_message = await websocket.receive_text()
        initial_data = json.loads(initial_message)
        if "setup" in initial_data and "resumption_handle" in initial_data["setup"]:
            config["resumption_handle"] = initial_data["setup"]["resumption_handle"]
            print(f"[PROXY] Attempting to resume session with handle: {config['resumption_handle'][:10]}...")

        async with client.aio.live.connect(model=MODEL_ID, config=config) as session:
            print("[PROXY] Successfully connected to Gemini Live API!")
            # Уведомляем фронтенд о готовности
            await websocket.send_text(json.dumps({"server_content": {"setup_complete": {}}}))
            sys.stdout.flush()

            # --- ЗАДАЧА 1: Google -> Клиент ---
            async def google_to_client():
                try:
                    async for message in session.receive():
                        if message.server_content and message.server_content.model_turn:
                            parts = message.server_content.model_turn.parts
                            
                            response_data = {
                                "serverContent": {
                                    "modelTurn": {
                                        "parts": []
                                    }
                                }
                            }
                            
                            for part in parts:
                                part_dict = {}
                                if part.text:
                                    part_dict["text"] = part.text
                                
                                if part.inline_data:
                                    part_dict["inlineData"] = {
                                        "data": base64.b64encode(part.inline_data.data).decode("utf-8"),
                                        "mimeType": part.inline_data.mime_type
                                    }
                                
                                if part_dict:
                                    response_data["serverContent"]["modelTurn"]["parts"].append(part_dict)
                            
                            if response_data["serverContent"]["modelTurn"]["parts"]:
                                await websocket.send_text(json.dumps(response_data))
                        
                        # Передаем токены возобновления сессии клиенту
                        if message.session_resumption_update:
                            update = message.session_resumption_update
                            if update.new_handle:
                                print(f"[PROXY] Received new resumption handle: {update.new_handle[:10]}...")
                                await websocket.send_text(json.dumps({
                                    "serverContent": {
                                        "resumptionToken": update.new_handle
                                    }
                                }))

                except Exception as e:
                    print(f"[ERROR] google_to_client error: {e}")
                    sys.stdout.flush()

            # --- ЗАДАЧА 2: Клиент -> Google ---
            async def client_to_google():
                try:
                    while True:
                        data = await websocket.receive_text()
                        message = json.loads(data)
                        
                        if "realtimeInput" in message:
                            chunks = message["realtimeInput"].get("mediaChunks", [])
                            for chunk in chunks:
                                if "data" in chunk:
                                    audio_bytes = base64.b64decode(chunk["data"])
                                    # В новом google-genai передаем аудио как словарь или объект Blob
                                    await session.send_realtime_input(audio={
                                        "data": audio_bytes,
                                        "mime_type": "audio/pcm;rate=16000"
                                    })
                        
                        elif "client_content" in message:
                            # Обработка текстовых сообщений от клиента (если есть)
                            if "turns" in message["client_content"]:
                                await session.send_client_content(
                                    turns=message["client_content"]["turns"],
                                    turn_complete=message["client_content"].get("turn_complete", True)
                                )
                                
                except WebSocketDisconnect:
                    print("[PROXY] Client disconnected.")
                except Exception as e:
                    print(f"[ERROR] client_to_google error: {e}")
                sys.stdout.flush()

            await asyncio.gather(google_to_client(), client_to_google())

    except Exception as e_conn:
        error_msg = str(e_conn)
        print(f"\n[CRITICAL CONNECTION ERROR] {error_msg}")
        sys.stdout.flush()
        try:
            await websocket.close(code=1011)
        except:
            pass

if os.path.exists(FRONTEND_DIR):
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 5000))
    uvicorn.run(app, host="0.0.0.0", port=port)
