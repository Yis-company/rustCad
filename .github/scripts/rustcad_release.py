#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Select an immutable draft, or publish the exact package that passed its gates."""

import argparse
import base64
import filecmp
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile


def require_success(gates):
    if set(gates) != {"select", "verify"} or any(
        job.get("result") != "success" for job in gates.values()
    ):
        raise ValueError("Every required release job must succeed")


def version_from_tag(tag):
    match = re.fullmatch(r"rustcad-v(0\.\d+\.\d+-alpha\.[1-9]\d*)", tag)
    if not match:
        raise ValueError("Expected an immutable rustcad-v0.x.y-alpha.N tag")
    return match[1]


class GitHub:
    def __init__(self, repository):
        if repository != "Yis-company/rustCad":
            raise ValueError("Publication is restricted to Yis-company/rustCad")
        self.repository = repository
        self.base = f"repos/{repository}"

    def api(self, path, **fields):
        command = ["gh", "api", f"{self.base}/{path}"]
        if fields:
            command += ["--method", "PATCH", "--input", "-"]
        result = subprocess.run(
            command,
            input=json.dumps(fields) if fields else None,
            text=True,
            capture_output=True,
            check=True,
        )
        return json.loads(result.stdout)

    def upload(self, tag, path):
        subprocess.run(
            ["gh", "release", "upload", tag, str(path), "--repo", self.repository], check=True
        )

    def download(self, tag, name, folder):
        subprocess.run(
            [
                "gh",
                "release",
                "download",
                tag,
                "--pattern",
                name,
                "--dir",
                str(folder),
                "--repo",
                self.repository,
            ],
            check=True,
        )


def select_draft(github, tag, expected_sha=None):
    version = version_from_tag(tag)
    release = github.api(f"releases/tags/{tag}")
    if not release.get("draft") or not release.get("prerelease"):
        raise ValueError("Only an unpublished alpha draft can be released")
    ref = github.api(f"git/ref/tags/{tag}")["object"]
    # Release Please creates lightweight tags; never accept an ambiguous ref.
    if ref["type"] != "commit" or not re.fullmatch(r"[a-f0-9]{40}", ref["sha"]):
        raise ValueError("Release tag must directly identify a commit")
    sha = ref["sha"]
    if expected_sha is not None and sha != expected_sha:
        raise ValueError("Tag does not identify the tested commit")
    comparison = github.api(f"compare/{sha}...main")
    if comparison["status"] not in ("ahead", "identical"):
        raise ValueError("Release commit must belong to main")
    contents = github.api(f"contents/rustcad-version.txt?ref={sha}")
    if base64.b64decode(contents["content"]).decode().strip() != version:
        raise ValueError("Tagged version file does not match the release")
    return {"sha": sha, "tag": tag, "version": version, "release_id": release["id"]}


def publish(github, tag, sha, gates, folder):
    require_success(gates)
    identity = select_draft(github, tag, sha)
    metadata = json.loads((folder / "rustcad-evidence.json").read_text())
    if any(metadata.get(key) != identity[key] for key in ("sha", "tag", "version")):
        raise ValueError("Package identity does not match the tested release")
    if metadata.get("package_tests_passed") is not True:
        raise ValueError("Packaged GUI and STEP tests must pass")
    if metadata.get("dirty") is not False:
        raise ValueError("Release source must be clean")
    paths = [
        folder / f"rustCad-{identity['version']}-Linux-x86_64.AppImage",
        folder / "rustcad-evidence.json",
    ]
    if any(not path.is_file() or path.stat().st_size == 0 for path in paths):
        raise ValueError("Tested package/evidence is missing or empty")
    existing = github.api(f"releases/{identity['release_id']}/assets?per_page=100")
    names = {path.name for path in paths}
    if any(asset["name"] not in names for asset in existing):
        raise ValueError("Draft contains unexpected assets")
    # A partial upload can be resumed only when existing bytes are identical.
    with tempfile.TemporaryDirectory(prefix="rustcad-assets-") as temp:
        for path in paths:
            matches = [asset for asset in existing if asset["name"] == path.name]
            if matches:
                if len(matches) != 1 or matches[0]["size"] != path.stat().st_size:
                    raise ValueError("Draft asset collision")
                github.download(tag, path.name, Path(temp))
                if not filecmp.cmp(path, Path(temp) / path.name, shallow=False):
                    raise ValueError("Draft asset bytes differ; refusing replacement")
            else:
                github.upload(tag, path)
    # Recheck the ref and draft after uploads, immediately before publication.
    select_draft(github, tag, sha)
    github.api(
        f"releases/{identity['release_id']}", draft=False, prerelease=True, make_latest="false"
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("select", "publish"))
    parser.add_argument("--tag", required=True)
    parser.add_argument("--sha")
    parser.add_argument("--folder", type=Path)
    args = parser.parse_args()
    github = GitHub(os.environ["GITHUB_REPOSITORY"])
    if args.mode == "select":
        identity = select_draft(github, args.tag, args.sha)
        with open(os.environ["GITHUB_OUTPUT"], "a") as output:
            for key, value in identity.items():
                output.write(f"{key}={value}\n")
    else:
        if not args.sha or not args.folder:
            parser.error("publish requires --sha and --folder")
        publish(github, args.tag, args.sha, json.loads(os.environ["RELEASE_GATES"]), args.folder)


if __name__ == "__main__":
    main()
