"""
System Diagnostics and Connectivity Verifier
Inclusive Resume & Job Matching API (SDG 10)
"""
import os
import sys
from pathlib import Path

# Anchor paths
ROOT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = ROOT_DIR / "backend"

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

# Pre-load .env
try:
    from dotenv import load_dotenv
    env_path = ROOT_DIR / ".env"
    if env_path.exists():
        load_dotenv(env_path)
except ImportError:
    pass


def run_diagnostics():
    print("=" * 76)
    print("  INCLUSIVE ATS & JOB MATCHING SYSTEM: CONNECTIVITY DIAGNOSTICS")
    print("=" * 76)

    # 1. Dependency Validation
    print("\n[1] DEPENDENCY VERIFICATION:")
    missing = []
    for pkg in ["pydantic", "email_validator", "dotenv", "fastapi", "uvicorn", "sqlalchemy", "torch", "sentence_transformers"]:
        try:
            __import__(pkg)
            print(f"  ✓ {pkg:<22} : Available")
        except ImportError as e:
            print(f"  ✗ {pkg:<22} : MISSING ({e})")
            missing.append(pkg)

    if missing:
        print(f"\n  [WARNING] Missing dependencies detected: {missing}")
        print("  Run: pip install -r backend/requirements.txt")
    else:
        print("  ✓ All essential backend dependencies are installed.")

    # 2. Configuration & Path Anchoring
    print("\n[2] PATH ANCHORING & CONFIGURATION:")
    from app.core.config import settings, redact_sensitive_url
    print(f"  • Root Anchor       : {settings.ROOT_DIR}")
    print(f"  • Backend Anchor    : {settings.APP_DIR}")
    print(f"  • Resolved DB URL   : {redact_sensitive_url(settings.DATABASE_URL)}")
    print(f"  • Model Path        : {settings.MODEL_PATH} ({'EXISTS' if Path(settings.MODEL_PATH).exists() else 'NOT FOUND'})")
    print(f"  • Upload Directory  : {settings.UPLOAD_DIR} ({'EXISTS' if Path(settings.UPLOAD_DIR).exists() else 'NOT FOUND'})")
    print(f"  • Allowed Origins   : {len(settings.cors_origins)} origins configured")

    # 3. Database Connectivity & Schema
    print("\n[3] DATABASE CONNECTIVITY & PERSISTENCE:")
    from app.db.session import engine
    from sqlalchemy import inspect
    try:
        inspector = inspect(engine)
        tables = inspector.get_table_names()
        print(f"  ✓ Database connected successfully: {len(tables)} tables verified.")
        for t in sorted(tables):
            print(f"    - {t}")
    except Exception as e:
        print(f"  ✗ Database connection failed: {e}")

    # 4. ML Model Status
    print("\n[4] ML INFERENCE ENGINE:")
    from app.ml.inference import MLInferenceService
    status = MLInferenceService.status_dict()
    print(f"  • Initial State     : {status.get('state')}")
    print(f"  • Artifact Path     : {status.get('model_path')}")
    print(f"  • Threshold         : {status.get('threshold')}")
    print(f"  • Ready for Scorer  : {status.get('is_ready')}")

    # 5. Local Port Availability
    print("\n[5] PORT 8001 LOCAL BINDING:")
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("127.0.0.1", 8001))
        s.close()
        print("  ✓ Port 8001 is AVAILABLE for binding.")
    except OSError:
        print("  ! Port 8001 is currently occupied by another process.")

    print("\n" + "=" * 76)
    print("  CANONICAL STARTUP COMMAND (WINDOWS PowerShell / CMD):")
    print("    python main.py")
    print("=" * 76 + "\n")


if __name__ == "__main__":
    run_diagnostics()

