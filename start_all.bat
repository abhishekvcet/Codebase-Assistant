@echo off
echo 🚀 Starting Intelligent Codebase Assistant...

:: 1. Start the API Server in a new window
echo Starting API Server in background...
start "Codebase Assistant - Backend" cmd /k "python main.py"

:: 2. Wait for server to initialize
echo Waiting for server to start...
timeout /t 5 /nobreak >nul

:: 3. Launch the Web UI
echo Opening Web UI...
python -m cli.cli web

:: 4. Launch Interactive CLI
echo Starting Interactive Mode...
python -m cli.cli cli
