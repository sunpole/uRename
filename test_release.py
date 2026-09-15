"""Integration checks for public release metadata and archive privacy."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parent


class ReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="urename_release_test_")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        shutil.copytree(ROOT / "tools", self.root / "tools", ignore=shutil.ignore_patterns("__pycache__"))
        for filename in ("version.json", "VERSION.md", "CHANGELOG.md"):
            shutil.copyfile(ROOT / filename, self.root / filename)

    def run_script(self, name, *args):
        return subprocess.run([sys.executable, "-B", str(self.root / "tools" / name), *args],
                              cwd=self.root, capture_output=True, text=True, encoding="utf-8")

    def test_version_consistency_and_bump(self):
        current = json.loads((self.root / "version.json").read_text(encoding="utf-8"))["version"]
        major, minor, patch = map(int, current.split("."))
        next_version = f"{major}.{minor}.{patch + 1}"
        result = self.run_script("release.py", "--check", "--tag", "v" + current)
        self.assertEqual(result.returncode, 0, result.stderr)
        result = self.run_script("release.py", "--bump", "patch", "--note", "Test change", "--date", "2026-09-16")
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads((self.root / "version.json").read_text(encoding="utf-8"))
        self.assertEqual(data["version"], next_version)
        self.assertIn("Test change", (self.root / "CHANGELOG.md").read_text(encoding="utf-8"))
        self.assertEqual(self.run_script("release.py", "--check", "--tag", "v" + next_version).returncode, 0)
        self.assertNotEqual(self.run_script("release.py", "--check", "--tag", "v" + current).returncode, 0)
        (self.root / "VERSION.md").write_text("stale", encoding="utf-8")
        self.assertNotEqual(self.run_script("release.py", "--check").returncode, 0)

    def test_archive_does_not_include_live_settings(self):
        for filename in ("uRename.py", "run_rename.bat", "preview_rename.bat", "files.example.txt",
                         "mask.example.txt", "README.md", "README.txt", "LICENSE"):
            shutil.copyfile(ROOT / filename, self.root / filename)
        (self.root / "files.txt").write_text("PRIVATE_SENTINEL_PATH", encoding="utf-8")
        (self.root / "mask.txt").write_text("PRIVATE_SENTINEL_MASK", encoding="utf-8")
        result = self.run_script("package_release.py")
        self.assertEqual(result.returncode, 0, result.stderr)
        archive = next((self.root / "dist").glob("*.zip"))
        with zipfile.ZipFile(archive) as package:
            for name in package.namelist():
                self.assertNotIn(b"PRIVATE_SENTINEL", package.read(name))
            prefix = "uRename-v" + json.loads((self.root / "version.json").read_text(encoding="utf-8"))["version"] + "/"
            self.assertEqual(package.read(prefix + "files.txt"), b"")
            self.assertEqual(package.read(prefix + "mask.txt"), (self.root / "mask.example.txt").read_bytes())

    def test_site_contains_version_and_release_notes(self):
        shutil.copytree(ROOT / "docs", self.root / "docs")
        result = self.run_script("build_site.py")
        self.assertEqual(result.returncode, 0, result.stderr)
        page = (self.root / "_site" / "index.html").read_text(encoding="utf-8")
        self.assertNotIn("{{", page)
        data = json.loads((self.root / "version.json").read_text(encoding="utf-8"))
        self.assertIn("v" + data["version"], page)
        self.assertIn(data["releases"][0]["title"], page)


if __name__ == "__main__":
    unittest.main()
