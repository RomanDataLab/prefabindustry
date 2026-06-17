#!/usr/bin/env python3
"""
Check Mapbox token via configix.apiManager.
Run from prefab root: python -m configix.check_mapbox
"""
import sys
from pathlib import Path

# Ensure prefab root is on path
sys.path.insert(0, str(Path(__file__).parent.parent))

from configix.apiManager import get_mapbox_config


def main():
    cfg = get_mapbox_config()
    if cfg is None:
        print("Mapbox config: NOT LOADED (error during config load)")
        sys.exit(1)
    tok = cfg.get("MAPBOX_ACCESS_TOKEN")
    style = cfg.get("MAPBOX_STYLE")
    if not tok:
        print("Mapbox token: MISSING")
        sys.exit(1)
    print("Mapbox token: OK")
    print("  Prefix:", tok[:24] + "..." if len(tok) > 24 else tok)
    print("Mapbox style:", style or "(default)")
    sys.exit(0)


if __name__ == "__main__":
    main()
