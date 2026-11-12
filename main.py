"""
Canonical Launcher for Inclusive Resume & Job Matching API (SDG 10)
Standardized local entry point: http://127.0.0.1:8001
"""
import os
import socket
import subprocess
import sys
from pathlib import Path

# Canonical directory anchors
ROOT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = ROOT_DIR / "backend"

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

# Pre-load environment variables from project root .env
try:
    from dotenv import load_dotenv
    env_file = ROOT_DIR / ".env"
    if env_file.exists():
        load_dotenv(env_file)
except ImportError:
    pass


def check_port_availability(host: str, port: int) -> bool:
    """
    Verifies that the requested host:port is free to bind.
    Never terminates or kills processes.
    """
    check_host = "127.0.0.1" if host in ("localhost", "0.0.0.0") else host
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        try:
            s.bind((check_host, port))
            return True
        except OSError:
            return False


def get_occupying_process_info(port: int) -> str:
    """Attempts to identify the PID occupying the port on Windows for diagnostics."""
    if sys.platform == "win32":
        try:
            output = subprocess.check_output(
                f'netstat -ano -p tcp | findstr ":{port}"',
                shell=True,
                text=True,
                stderr=subprocess.DEVNULL
            )
            for line in output.strip().splitlines():
                if f":{port}" in line and "LISTENING" in line:
                    parts = line.strip().split()
                    pid = parts[-1]
                    return f"PID {pid}"
        except (subprocess.SubprocessError, OSError):
            return "another application"
    return "another application"


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
        occupant = get_occupying_process_info(port)
        print("\n" + "!" * 76, file=sys.stderr)
        print(f"  [ERROR] PORT CONFLICT DETECTED: http://{host}:{port} is already in use.", file=sys.stderr)
        print(f"  Port {port} is currently occupied by {occupant}.", file=sys.stderr)
        print("  To resolve this:", file=sys.stderr)
        print(f"    1. Stop the application occupying port {port}, OR", file=sys.stderr)
        print("    2. Specify a custom port via environment variable: PORT=8002 python main.py", file=sys.stderr)
        print("  Startup aborted cleanly to prevent unauthorized interference.", file=sys.stderr)
        print("!" * 76 + "\n", file=sys.stderr)
        sys.exit(1)

    print("\n" + "=" * 76)
    print("  >>> INCLUSIVE RESUME & JOB MATCHING API (SDG 10) <<<")
    print(f"  -> Local API Service:      http://{host}:{port}")
    print(f"  -> Interactive Swagger UI: http://{host}:{port}/docs")
    print(f"  -> Health Check Endpoint:  http://{host}:{port}/health")
    print(f"  -> Readiness Check Probe:  http://{host}:{port}/ready")
    print("  -> Frontend Application:   http://127.0.0.1:5500/frontend/ (or index.html)")
    print("=" * 76 + "\n")

    uvicorn.run(
        "app.main:app",
        host=host,
        port=port,
        reload=False,
        log_level="info",
        app_dir=str(BACKEND_DIR)
    )


if __name__ == "__main__":
    main()
