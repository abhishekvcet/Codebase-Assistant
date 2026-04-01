"""
Codebase Assistant — Main Server Entry Point
Start the backend server by running: python main.py
"""

import sys
import os
from pathlib import Path
import uvicorn

# Ensure the root directory is in sys.path for module imports
ROOT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT_DIR))

try:
    from shared.config import settings
    host = settings.API_HOST
    port = settings.API_PORT
    log_level = settings.LOG_LEVEL.lower()
except ImportError:
    # Defaults if shared.config is unavailable
    host = "localhost"
    port = 8000
    log_level = "info"

def start_server():
    """Start the FastAPI backend server."""
    print(f"\n🚀 Starting Intelligent Codebase Assistant...")
    print(f"   Server: http://{host}:{port}")
    print(f"   Logs  : {log_level}\n")
    
    uvicorn.run(
        "services.api_gateway.main:app", 
        host=host, 
        port=port, 
        reload=True,
        log_level=log_level
    )

if __name__ == "__main__":
    start_server()
