from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
SOURCE_DIRECTORIES = (
    PROJECT_ROOT / "app",
    PROJECT_ROOT / "webapp",
)


def test_source_files_do_not_contain_corrupted_placeholders() -> None:
    corrupted_files: list[str] = []

    for directory in SOURCE_DIRECTORIES:
        for path in directory.rglob("*"):
            if not path.is_file() or path.suffix not in {".py", ".js", ".html", ".css"}:
                continue

            content = path.read_text(encoding="utf-8")

            if "???" in content or "�" in content:
                corrupted_files.append(str(path.relative_to(PROJECT_ROOT)))

    assert not corrupted_files, "Обнаружены повреждённые строки: " + ", ".join(
        corrupted_files
    )
