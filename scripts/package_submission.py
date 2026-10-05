"""Build a narrow source ZIP. Never traverse workspace caches or temporary files."""

import argparse
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parent.parent
DOCUMENTS = ("acceptance.md", "architecture.md", "assessment-audit.md", "dashboard.md", "demo.md", "handover.md")
EVIDENCE_FILES = ("acceptance.json", "evidence.json", "routing.json", "report.html", "demo.sqlite3",
                  "marketing.png", "arabic-support.png", "product.png", "tech.png")


def package(evidence: Path, output: Path) -> int:
    evidence = evidence.resolve()
    if not evidence.is_relative_to(ROOT / "artifacts") or not all((evidence / name).is_file() for name in ("acceptance.json", "evidence.json", "report.html")):
        raise ValueError("Choose a complete evidence directory under artifacts.")
    files = [ROOT / name for name in ("README.md", "pyproject.toml", "uv.lock", ".gitignore")]
    files.extend(ROOT / "docs" / name for name in DOCUMENTS)
    files.append(ROOT / "scripts" / "package_submission.py")
    for directory, extensions in (("hissatech", {".py", ".html", ".css", ".js"}), ("tests", {".py", ".js"}), ("data", {".json"})):
        files.extend(path for path in (ROOT / directory).rglob("*") if path.is_file() and path.suffix in extensions and "__pycache__" not in path.parts)
    files.extend(evidence / name for name in EVIDENCE_FILES if (evidence / name).is_file())
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(files):
            archive.write(path, path.relative_to(ROOT).as_posix())
    return len(files)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=ROOT / "dist" / "hissatech-submission.zip")
    args = parser.parse_args()
    print(f"Packaged {package(args.evidence, args.output)} files: {args.output}")


if __name__ == "__main__":
    main()
