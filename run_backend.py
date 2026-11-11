import os
import socket
import sys
from pathlib import Path

# Add backend directory to sys.path
root_dir = Path(__file__).resolve().parent
backend_dir = root_dir / "backend"
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

# Switch working directory to backend so relative paths resolve cleanly
os.chdir(str(backend_dir))

import uvicorn

def get_available_port(default_port: int = 8000, host: str = "127.0.0.1") -> int:
    env_p = os.getenv("PORT")
    if env_p and env_p.isdigit():
        return int(env_p)
    for p in range(default_port, default_port + 20):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind((host, p))
                return p
        except OSError:
            continue
    return default_port

if __name__ == "__main__":
    host = "127.0.0.1"
    port = get_available_port(8000, host)

    print("\n" + "=" * 70)
    print(" >>> Inclusive Resume & Job Matching API is starting up... <<<")
    print(f" -> Local Web Service:      http://{host}:{port}")
    print(f" -> Interactive Swagger UI: http://{host}:{port}/docs")
    print(f" -> Alternative Redoc UI:   http://{host}:{port}/redoc")
    print(f" -> Health Check Endpoint:  http://{host}:{port}/health")
    if port != 8000:
        print(f" [Note: Port 8000 was busy; automatically shifted to available port {port}]")
    print("=" * 70 + "\n")
    uvicorn.run("app.main:app", host=host, port=port, reload=True, app_dir=str(backend_dir))
