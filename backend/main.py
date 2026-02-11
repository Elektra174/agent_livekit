import os
import json
import asyncio
import base64
import sys
import subprocess
import time
import httpx
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

# НАСТРОЙКИ ТУННЕЛЯ
# Логин и IP вашего Google Cloud Shell
CLOUD_SHELL_USER = "azmaksim2019" 
CLOUD_SHELL_IP = "34.141.247.197" 

MODEL_ID = "models/gemini-2.5-flash-native-audio-preview-12-2025"

if not GOOGLE_API_KEY:
    print("CRITICAL: GOOGLE_API_KEY is not set.")
    sys.stdout.flush()

# --- SSH TUNNEL FUNCTION ---
def setup_ssh_tunnel():
    """Пытается создать SOCKS5 прокси через Google Cloud Shell."""
    print("[TUNNEL] Attempting SSH Tunnel setup...")
    sys.stdout.flush()
    
    # 1. Генерируем ключ, если его нет (для автологина)
    key_path = os.path.expanduser("~/.ssh/google_tunnel")
    if not os.path.exists(key_path):
        print("[TUNNEL] Generating SSH key...")
        subprocess.run(["ssh-keygen", "-t", "rsa", "-f", key_path, "-N", ""], check=True)
        print("[TUNNEL] Key generated.")
        print(f"[TUNNEL] PLEASE ADD THIS PUBLIC KEY to Cloud Shell ~/.ssh/authorized_keys:")
        with open(key_path + ".pub", "r") as f:
            print(f.read().strip())
        sys.stdout.flush()

    # 2. Проверяем, открыт ли порт
    # Google Cloud Shell обычно блокирует порт 22 извне.
    # Команда проверит, доступен ли порт 22 на Cloud Shell.
    try:
        # Используем nc (netcat) для проверки доступности порта 22
        check = subprocess.run(
            ["nc", "-zv", "-w", "2", CLOUD_SHELL_IP, "22"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        if check.returncode != 0:
            print(f"[TUNNEL] WARNING: Port 22 on {CLOUD_SHELL_IP} is CLOSED/BLOCKED.")
            print("[TUNNEL] This is normal for Cloud Shell. Cannot establish tunnel.")
            return False
    except Exception as e:
        print(f"[TUNNEL] Check failed (nc might be missing): {e}")
        # Продолжаем попытку на всякий случай

    # 3. Запуск туннеля
    ssh_cmd = [
        "ssh", 
        "-f", 
        "-N", 
        "-D", "8888",
        "-i", key_path,
        "-o", "StrictHostKeyChecking=no",
        "-o", "ConnectTimeout=5",
        "-o", "ServerAliveInterval=10",
        f"{CLOUD_SHELL_USER}@{CLOUD_SHELL_IP}"
    ]

    try:
        subprocess.run(ssh_cmd, check=True)
        print(f"[TUNNEL] SUCCESS: Tunnel established via {CLOUD_SHELL_USER}@{CLOUD_SHELL_IP}")
        return True
    except subprocess.CalledProcessError as e:
        print(f"[TUNNEL] FAILED: Could not connect via SSH.")
        print(f"[TUNNEL] Error: {e}")
        return False

# Запускаем туннель при старте
tunnel_active = setup_ssh_tunnel()

# Если туннель активен, указываем библиотеке использовать его
# genai SDK поддерживает прокси через переменные окружения или настройки http_client
if tunnel_active:
    os.environ['ALL_PROXY'] = 'socks5://localhost:8888'
    os.environ['all_proxy'] = 'socks5://localhost:8888'
    print("[TUNNEL] Proxy configured for Google API calls.")
    sys.stdout.flush()

# Маршрут WebSocket
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    print(f"[PROXY] Client connected. Model: {MODEL_ID}. Tunnel: {'ACTIVE' if tunnel_active else 'FAILED'}")
    sys.stdout.flush()

    # Инициализация клиента Google
    # SDK автоматически подхватит переменные ALL_PROXY если туннель активен
    client = genai.Client(api_key=GOOGLE_API_KEY, http_options={'api_version': 'v1alpha'})
    
    try:
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
            print("[PROXY] Successfully connected to Google API!")
            await websocket.send_text(json.dumps({"server_content": {"setup_complete": {}}}))
            sys.stdout.flush()

            # --- ЗАДАЧА 1: Google -> Клиент ---
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

            # --- ЗАДАЧА 2: Клиент -> Google ---
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
        sys.stdout.flush()
        try:
            await websocket.close(code=1011)
        except:
            pass

if os.path.exists(FRONTEND_DIR):
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5000)
