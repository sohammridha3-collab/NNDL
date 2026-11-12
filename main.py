"""
Canonical Launcher for Inclusive Resume & Job Matching API (SDG 10)
Standardized local entry point: http://127.0.0.1:8001
"""
import os
import socket
import sys
from pathlib import Path

# Canonical directory anchors
ROOT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = ROOT_DIR / "backend"

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


def check_port_availability(host: str, port: int) -> bool:
    """
    Verifies that the requested host:port is free to bind.
    Never terminates or kills processes.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        try:
            s.bind((host, port))
            return True
        except OSError:
            return False


def main():
    import uvicorn

    # Deployment host/port resolution
    is_production = os.getenv("ENVIRONMENT", "").lower() == "production" or bool(os.getenv("RENDER"))
    default_host = "0.0.0.0" if is_production else "127.0.0.1"
    host = os.getenv("HOST", default_host)
    
    port_env = os.getenv("PORT")
    port = int(port_env) if port_env and port_env.isdigit() else 8001

    # Port conflict verification - report conflict clearly without killing processes or port-hopping
    if not check_port_availability(host, port):
        print("\n" + "!" * 76, file=sys.stderr)
        print(f"  [ERROR] PORT CONFLICT DETECTED: http://{host}:{port} is already in use.", file=sys.stderr)
        print(f"  Another application or process is actively listening on port {port}.", file=sys.stderr)
        print(f"  To resolve this:", file=sys.stderr)
        print(f"    1. Stop the application occupying port {port}, OR", file=sys.stderr)
        print(f"    2. Specify a custom port via environment variable: PORT=8002 python main.py", file=sys.stderr)
        print(f"  Startup aborted cleanly to prevent unauthorized interference.", file=sys.stderr)
        print("!" * 76 + "\n", file=sys.stderr)
        sys.exit(1)

    print("\n" + "=" * 76)
    print("  >>> INCLUSIVE RESUME & JOB MATCHING API (SDG 10) <<<")
    print(f"  -> Local API Service:      http://{host}:{port}")
    print(f"  -> Interactive Swagger UI: http://{host}:{port}/docs")
    print(f"  -> Health Check Endpoint:  http://{host}:{port}/health")
    print(f"  -> Readiness Check Probe:  http://{host}:{port}/ready")
    print(f"  -> Frontend Application:   http://127.0.0.1:5500/frontend/ (or index.html)")
    print("=" * 76 + "\n")

    from app.main import app

    uvicorn.run(
        app,
        host=host,
        port=port,
        log_level="info"
    )


if __name__ == "__main__":
    main()
