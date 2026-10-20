"""python kural.py <tool> '<json arguments>': one call to tkcore.agent_tools. Finds the repository from this file's
place in it (agents/skills/thirukkural/scripts/), or from THIRUKKURAL_REPO."""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.environ.get("THIRUKKURAL_REPO", str(Path(__file__).resolve().parents[4])))
from tkcore.agent_tools import call  # noqa: E402

print(json.dumps(call(sys.argv[1], json.loads(sys.argv[2] if len(sys.argv) > 2 else "{}")), ensure_ascii=False, indent=1))
