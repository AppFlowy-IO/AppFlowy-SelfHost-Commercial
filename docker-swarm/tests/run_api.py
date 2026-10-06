#!/usr/bin/env python3
"""Run the API smoke suite using docker-swarm/.local or SWARM_TEST_DIR."""
import subprocess
import sys
from pathlib import Path

raise SystemExit(subprocess.call([
    sys.executable, str(Path(__file__).with_name("api_smoke.py")), *sys.argv[1:]
]))
