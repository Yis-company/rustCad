# SPDX-License-Identifier: LGPL-2.1-or-later
"""Run the fixed corpus with process timeouts and preserve every diagnostic."""

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent


def run(command, directory, label, timeout):
    try:
        process = subprocess.run(command, text=True, capture_output=True, timeout=timeout, cwd=ROOT)
        stdout, stderr, code = process.stdout, process.stderr, process.returncode
    except subprocess.TimeoutExpired as error:
        stdout = error.stdout or b""
        stderr = error.stderr or b""
        stdout = stdout.decode(errors="replace") if isinstance(stdout, bytes) else stdout
        stderr = stderr.decode(errors="replace") if isinstance(stderr, bytes) else stderr
        code = "timeout"
    (directory / f"{label}.stdout.log").write_text(stdout)
    (directory / f"{label}.stderr.log").write_text(stderr)
    return code, stdout


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", nargs="?", type=Path)
    parser.add_argument("--binary", type=Path, help="explicit corpus executable for a pinned build")
    args = parser.parse_args()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    output = (args.output or ROOT / "artifacts" / stamp).resolve()
    output.mkdir(parents=True, exist_ok=False)
    criteria = json.loads((ROOT / "criteria.json").read_text())
    (output / "criteria.json").write_text(json.dumps(criteria, indent=2) + "\n")
    binary = (args.binary or ROOT / "target/debug/examples/corpus").resolve()
    if not binary.is_file():
        parser.error("Build the example first: cargo build --locked --example corpus")
    cases = [
        (name, 0)
        for name in [
            "plate",
            "overlap",
            "reverse",
            "disjoint",
            "face-contact",
            "edge-contact",
            "identical",
            "enclosing",
        ]
    ]
    cases += [("cylinder-gap-out", 0)]
    cases += [
        (name, factor)
        for name in ["box-gap-in", "box-gap-out", "cylinder-gap-in", "cylinder-gap-out"]
        for factor in criteria["gaps_in_modeling_tolerances"]
        if factor > 0
    ]
    results = []
    for scale in criteria["scales"]:
        for name, factor in cases:
            directory = output / f"{name}-s{scale}-g{factor}"
            directory.mkdir()
            code, stdout = run(
                [str(binary), name, str(scale), str(factor), str(directory)],
                directory,
                "rust",
                criteria["per_case_timeout_seconds"],
            )
            record = {
                "case": name,
                "scale": scale,
                "gap_factor": factor,
                "path": str(directory.relative_to(output)),
                "rust_exit": code,
            }
            try:
                report = json.loads(stdout.strip().splitlines()[-1])
            except (json.JSONDecodeError, IndexError):
                report = {"status": "error", "error": f"Rust process failed without JSON: {code}"}
            record["rust"] = report
            record["status"] = "fail"
            if (
                report["status"] == "error"
                and report.get("diagnostic")
                and report.get("precision_error")
            ):
                record["status"] = "precision_error"
            else:
                rust_passed = report["status"] == "pass" and code == 0
                expected = report.get("expected", {})
                if expected.get("solids") == 0 and rust_passed:
                    record["status"] = "pass"
                elif (directory / "shape.step").exists():
                    validation = directory / "occt.json"
                    command = [
                        sys.executable,
                        str(ROOT / "validate_step.py"),
                        str(directory / "shape.step"),
                        str(directory / "expected.json"),
                        "--output",
                        str(validation),
                    ]
                    validator_code, _ = run(
                        command, directory, "occt", criteria["per_case_timeout_seconds"]
                    )
                    record["validator_exit"] = validator_code
                    if validation.exists():
                        record["occt"] = json.loads(validation.read_text())
                    if (
                        rust_passed
                        and validator_code == 0
                        and not record.get("occt", {}).get("errors", ["missing validator result"])
                    ):
                        record["status"] = (
                            "tolerance_equivalent" if report.get("diagnostic") else "pass"
                        )
            results.append(record)
            print(f"{record['status']:22} {directory.name}", flush=True)
            # Save after every case so interruption does not erase observed evidence.
            summary = {
                "counts": dict(Counter(item["status"] for item in results)),
                "cases": results,
            }
            (output / "coverage.json").write_text(json.dumps(summary, indent=2) + "\n")
    counts = Counter(item["status"] for item in results)
    print(json.dumps({"artifacts": str(output), "counts": dict(counts)}, indent=2))
    return counts["fail"] > 0


if __name__ == "__main__":
    raise SystemExit(main())
