"""Build a release archive using an explicit public-file allowlist."""
import hashlib
from pathlib import Path
import zipfile
from release import ROOT, load_metadata, release_notes

PUBLIC_FILES = (
    "uRename.py", "run_rename.bat", "preview_rename.bat",
    "files.example.txt", "mask.example.txt", "README.md", "README.txt",
    "LICENSE", "version.json", "VERSION.md", "CHANGELOG.md",
)

def build_package(root=ROOT):
    data = load_metadata(root)
    name = "uRename-v" + data["version"]
    output = root / "dist"
    output.mkdir(exist_ok=True)
    archive = output / (name + ".zip")
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as package:
        for filename in PUBLIC_FILES:
            package.write(root / filename, name + "/" + filename)
        # Never package the user's live settings.
        package.writestr(name + "/files.txt", "")
        package.writestr(name + "/mask.txt", (root / "mask.example.txt").read_text(encoding="utf-8"))
    checksum = hashlib.sha256(archive.read_bytes()).hexdigest()
    (output / "SHA256SUMS.txt").write_text(checksum + "  " + archive.name + "\n", encoding="ascii")
    (output / "release-notes.md").write_text(release_notes(data["releases"][0]), encoding="utf-8")
    print(archive)
    return archive

if __name__ == "__main__":
    build_package()
