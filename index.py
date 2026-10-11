import sys
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(file)))
BACKEND_DIR = os.path.join(BASE_DIR, "backend")

sys.path.insert(0, BACKEND_DIR)

from app import app