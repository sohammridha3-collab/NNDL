"""
Main entry point for Inclusive Resume & Job Matching API (SDG 10)
Run with: python main.py
"""
import os
import sys
import subprocess
from pathlib import Path

# Add backend directory to sys.path
root_dir = Path(__file__).resolve().parent
backend_dir = root_dir / "backend"
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

def free_port_if_busy(port: int = 8001):
    """Check if port 8001 is held by a stale process and release it."""
    try:
        if sys.platform == "win32":
            output = subprocess.check_output(f"netstat -ano | findstr :{port}", shell=True, text=True, stderr=subprocess.DEVNULL)
            for line in output.strip().splitlines():
                if f":{port}" in line and "LISTENING" in line:
                    parts = line.strip().split()
                    pid = parts[-1]
                    if pid.isdigit() and int(pid) != os.getpid():
                        print(f"[*] Releasing busy port {port} from stale PID {pid}...")
                        subprocess.call(f"taskkill /F /PID {pid}", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass

if __name__ == "__main__":
    import uvicorn

    host = "127.0.0.1"
    port = int(os.getenv("PORT", "8001"))

    free_port_if_busy(port)

    print("\n" + "=" * 72)
    print("  >>> INCLUSIVE ATS BACKEND (SDG 10: REDUCED INEQUALITIES) <<<")
    print(f"  -> Local API Service:      http://{host}:{port}")
    print(f"  -> Swagger Documentation:  http://{host}:{port}/docs")
    print(f"  -> Redoc Alternative UI:   http://{host}:{port}/redoc")
    print(f"  -> Health Check Probe:     http://{host}:{port}/health")
    print(f"  -> Frontend Application:   http://{host}:5500/frontend/")
    print("=" * 72 + "\n")

    uvicorn.run("app.main:app", host=host, port=port, reload=False, app_dir=str(backend_dir))
