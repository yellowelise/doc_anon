import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
os.environ.setdefault('DOC_ANON_DATA_DIR', str(ROOT / '.test-data/resources'))
