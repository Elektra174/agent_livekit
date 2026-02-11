#!/bin/bash
python backend/server.py & # Запуск сервера в фоновом режиме
python backend/agent.py start # Запуск агента
