"""Apply the exact source patch validated locally; removed before release."""
import base64
import gzip
import hashlib
import subprocess
from pathlib import Path

encoded = "".join(Path(f"tools/v170-patch-{i}.b64").read_text().strip() for i in range(4))
patch = gzip.decompress(base64.b64decode(encoded, validate=True))
expected = "edc40ffc9104d00b2dbae51bd5a1d1f2aa08a09cddefe3df325d05e6fb96c53d"
if hashlib.sha256(patch).hexdigest() != expected:
    raise SystemExit("Patch checksum mismatch; no files changed")
subprocess.run(["git", "apply", "--check", "-"], input=patch, check=True)
subprocess.run(["git", "apply", "-"], input=patch, check=True)
expected_files = {
    "codex-usage": "4af1954bd1dd79c3b1a7308ec29c6dd7d5992a75594a1932fd4fc87e14a4f483",
    "tests/test_gpt6.py": "62f775b81d0ab4a1ea74fe995ad28e5c7e2c7db05b55b1e8e9266831dcd171bf",
    "tests/test_codex_usage.py": "b40502eaec43ad06f605296330e63077b04a93541d5aea57f3ab6fa58bcf4d3f",
    "docs/v1.7.0-gpt6.md": "893868f21cf58c243bc08e888e4b6f01e7031ae89d1d039d3d3f76de8c57a9a1",
    "README.md": "0e99987d0fef19b09425cd23ffa6f78b2199148c42ab1051a6d037e67f4af91f",
    "README.zh-CN.md": "c58b55459ddcf87dc1c66b8300423049715ce8eb6eb4f331c81e601b8aeba7f9",
    "CHANGELOG.md": "cce0274cc6b52a490a78962c6a04180986d536fa35d03dc825f360a4446a3c23",
}
for name, expected_hash in expected_files.items():
    if hashlib.sha256(Path(name).read_bytes()).hexdigest() != expected_hash:
        raise SystemExit(f"Source checksum mismatch: {name}")
print("All seven source files match the locally tested v1.7.0 patch")
