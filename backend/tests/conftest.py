import os
import sys
from pathlib import Path

os.environ["DATABASE_URL"] = "sqlite:///data/test-resumate.db"
os.environ.setdefault("JWT_SECRET_KEY", "test-secret")

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
