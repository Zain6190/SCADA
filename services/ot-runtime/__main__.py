# python -m ot_runtime  (run from services/ot-runtime)
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Allow `python -m ot_runtime` when cwd is services/ot-runtime
sys.path.insert(0, str(Path(__file__).resolve().parent))

from ot_runtime.runtime import OtRuntime


def main() -> None:
    parser = argparse.ArgumentParser(description="Run software OT ticks (no hardware)")
    parser.add_argument("--ticks", type=int, default=1)
    parser.add_argument("--minutes", type=float, default=15.0, help="Simulated minutes per tick")
    args = parser.parse_args()

    runtime = OtRuntime(sim_minutes=args.minutes)
    last = None
    for _ in range(args.ticks):
        last = runtime.tick()
    print(json.dumps({
        "ticks": runtime.ticks,
        "published": len(last.published) if last else 0,
        "devices": last.devices if last else [],
    }, default=str, indent=2))


if __name__ == "__main__":
    main()
