#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Record stage timing and sampled disk use while retaining the complete command log."""

import argparse
import json
from pathlib import Path
import shutil
import subprocess
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("name")
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    folder = Path("build/evidence")
    folder.mkdir(parents=True, exist_ok=True)
    samples = []
    start = time.monotonic()
    with (folder / f"{args.name}.log").open("w") as log:
        process = subprocess.Popen(args.command, stdout=log, stderr=subprocess.STDOUT)
        while True:
            disk = shutil.disk_usage(".")
            samples.append(
                {
                    "seconds": round(time.monotonic() - start, 1),
                    "used_bytes": disk.used,
                    "free_bytes": disk.free,
                }
            )
            try:
                status = process.wait(timeout=15)
                break
            except subprocess.TimeoutExpired:
                pass
    result = {
        "exit_code": status,
        "seconds": round(time.monotonic() - start, 1),
        "disk_samples": samples,
    }
    (folder / f"{args.name}.json").write_text(json.dumps(result, indent=2) + "\n")
    print(
        f"{args.name}: exit {status}, {result['seconds']} seconds; "
        f"minimum sampled free space {min(s['free_bytes'] for s in samples)} bytes"
    )
    if status:
        print((folder / f"{args.name}.log").read_text()[-6000:])
    return status


if __name__ == "__main__":
    raise SystemExit(main())
