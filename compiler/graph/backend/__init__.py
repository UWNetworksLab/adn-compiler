from __future__ import annotations

import importlib
import os
from pathlib import Path
from typing import Dict

from compiler.graph.ir import GraphIR

BACKEND_CONFIG_DIR = os.path.join(Path(__file__).parent, "config")


def scriptgen(girs: Dict[str, GraphIR], backend: str, app: str, app_manifest_file: str):
    """
    Call corresponding scripg generation procedure according to the backend name.

    Args:
        girs: A dictionary mapping edge name to corresponding graphir.
        backend: backend name.
        service_pos: A dictionary mapping service name to hostname.
    """
    try:
        module = importlib.import_module(f"compiler.graph.backend.{backend}")
    except:
        raise ValueError(f"backend {backend} not supported")
    generator = getattr(module, f"scriptgen_{backend}")
    generator(girs, app, app_manifest_file)
