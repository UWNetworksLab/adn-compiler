import os
from pathlib import Path


TEST_DIR = Path(__file__).parent
ROOT_DIR = TEST_DIR.parent

proto_base_dir = os.path.join(ROOT_DIR, "examples/proto")