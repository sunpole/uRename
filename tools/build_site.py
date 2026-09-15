"""Build the documentation site and release history without dependencies."""
import html
from pathlib import Path
import shutil
from release import ROOT, load_metadata, generated_files

def build_site(root=ROOT):
    data = load_metadata(root)
    output = root / "_site"
    output.mkdir(exist_ok=True)
    for name in ("style.css", "mark.svg"):
        shutil.copyfile(root / "docs" / name, output / name)
    entries = []
    for release in data["releases"]:
        groups = []
        for group, notes in release["changes"].items():
            items = "".join("<li>" + html.escape(note) + "</li>" for note in notes)
            groups.append("<h4>" + html.escape(group) + "</h4><ul>" + items + "</ul>")
        entries.append(
            '<article class="release"><div class="release-meta"><span class="pill">v'
            + html.escape(release["version"]) + '</span><time>' + html.escape(release["date"])
            + '</time></div><h3>' + html.escape(release["title"]) + "</h3>" + "".join(groups) + "</article>"
        )
    page = (root / "docs" / "index.html").read_text(encoding="utf-8")
    page = page.replace("{{VERSION}}", html.escape(data["version"]))
    page = page.replace("{{RELEASED}}", html.escape(data["released"]))
    page = page.replace("{{RELEASES}}", "\n".join(entries))
    if "{{" in page:
        raise ValueError("Unresolved site placeholder")
    (output / "index.html").write_text(page, encoding="utf-8")
    shutil.copyfile(root / "version.json", output / "version.json")
    for name, content in generated_files(data).items():
        (output / name).write_text(content, encoding="utf-8")
    (output / ".nojekyll").touch()
    print(output)
    return output

if __name__ == "__main__":
    build_site()
