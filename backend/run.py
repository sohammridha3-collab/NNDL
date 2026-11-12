"""
Convenience launcher delegating directly to canonical main.py.
Standardized local entry point: http://127.0.0.1:8001
"""
import sys
from pathlib import Path

# Add project root to sys.path
backend_dir = Path(__file__).resolve().parent
root_dir = backend_dir.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from main import main

if __name__ == "__main__":
    main()
