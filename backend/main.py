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

# Model ID (оставляем ваш)
MODEL_ID = "models/gemini-2.5-flash-native-audio-preview-12-2025"

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
    print("\n[PROXY] Клиент подключен. Устанавливаем соединение с Google от имени сервера...")
    sys.stdout.flush()

    # Инициализация клиента
    # Используем v1alpha, так как audio-preview API пока там
    client = genai.Client(api_key=GOOGLE_API_KEY, http_options={'api_version': 'v1alpha'})
    
    try:
        # !!! ГЛАВНОЕ ИЗМЕНЕНИЕ !!!
        # Мы НЕ ждем setup от клиента. Мы создаем сессию ПРЯМО СЕЙЧАС.
        # Это гарантирует, что IP адрес запроса будет IP адресом сервера (Render, Oregon).
        
        config = {
            "response_modalities": ["AUDIO"],
            "generation_config": {"response_modalities": ["AUDIO"]}
        }
        
        async with client.aio.live.connect(model=MODEL_ID, config=config) as session:
            print("[PROXY] Сессия с Google Gemini установлена (Server-side control).")
            
            # Сообщаем клиенту, что все готово (имитация setup_complete)
            await websocket.send_text(json.dumps({
                "server_content": {"setup_complete": {}}
            }))
            sys.stdout.flush()

            async def google_to_client():
                """Пересылка сообщений от Google к Клиенту."""
                try:
                    async for message in session.receive():
                        # Обработка разных форматов ответов от SDK
                        content = getattr(message, 'server_content', None) or getattr(message, 'serverContent', None)
                        
                        if content:
                            # Если это setup_complete (на всякий случай), пропускаем, так как мы уже отправили свой
                            if hasattr(content, 'setup_complete') or hasattr(content, 'setupComplete'):
                                continue

                            # Формируем ответ для браузера
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
                """Пересылка сообщений от Клиента к Google."""
                try:
                    while True:
                        data = await websocket.receive_text()
                        message = json.loads(data)
                        
                        # Если клиент пытается прислать setup, игнорируем, так как сервер уже взял контроль
                        if "setup" in message:
                            print("[DEBUG] Клиент прислал setup, но сервер уже управляет сессией. Игнорируем.")
                            sys.stdout.flush()
                            continue
                        
                        # Пробрасываем остальные сообщения (аудио, текст)
                        # Проверяем наличие реальных данных перед отправкой
                        if "realtime_input" in message or "realtimeInput" in message or "client_content" in message or "clientContent" in message:
                            await session.send(message)
                                
                except WebSocketDisconnect:
                    print("[PROXY] Клиент разорвал соединение")
                except Exception as e:
                    print(f"[DEBUG] Ошибка в client_to_google: {e}")
                sys.stdout.flush()

            # Запускаем обе задачи
            await asyncio.gather(google_to_client(), client_to_google())

    except Exception as e_conn:
        print(f"\n[КРИТИЧЕСКАЯ ОШИБКА ПОДКЛЮЧЕНИЯ] Ошибка при открытии сокета Google: {e_conn}")
        
        # Выводим понятную ошибку пользователю
        if "User location is not supported" in str(e_conn) or "1007" in str(e_conn):
            print("\n" + "!"*60)
            print("ОШИБКА: Регион (IP) не поддерживается Google Gemini.")
            print("Сервер должен быть запущен в поддерживаемом регионе (например, US West).")
            print("!"*60 + "\n")
        else:
            print(f"[DEBUG] Тип ошибки: {type(e_conn)}")
            sys.stdout.flush()
        
        # Пытаемся закрыть websocket с кодом ошибки, чтобы клиент понял, что случилось
        try:
            await websocket.close(code=1011, reason="Server failed to connect to Google API")
        except:
            pass

# Serve static files
if os.path.exists(FRONTEND_DIR):
    # Монтируем статику, если папка существует
    # Обратите внимание: при монтировании корня "/" он перекрывает маршрут "/" выше, 
    # но FastAPI обычно приоритизирует маршруты в порядке добавления или точность совпадения.
    # Чтобы избежать конфликтов, лучше использовать отдельный префикс для статики или проверить порядок.
    # В данном случае get_index уже задан, но StaticFiles("/", ...) может его перехватить в зависимости от версии.
    # Для надежности оставим как есть, так как get_index обычно имеет приоритет над файловой системой.
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")
    
    # Или отдаем фронтенд так (если mount выше перекрывает):
    # app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")

if __name__ == "__main__":
    import uvicorn
    # Используем 0.0.0.0 для доступа извне (Render)
    uvicorn.run(app, host="0.0.0.0", port=5000)
