import re
from pathlib import Path


def annotate_tests(directory: str) -> None:
    root = Path(directory)
    for path in root.rglob("test_*.py"):
        if not path.is_file():
            continue
        content = path.read_text(encoding="utf-8")

        # Match "def test_name(...):" but NOT "def test_name(...) ->"
        # This handles both sync and async def
        pattern = r"(def test_[^(]+\([^)]*\))(\s*):"

        def replacement(match: re.Match[str]) -> str:
            signature = match.group(1)
            whitespace = match.group(2)
            if "->" in signature:
                return match.group(0)
            return f"{signature} -> None{whitespace}:"

        new_content = re.sub(pattern, replacement, content)

        if new_content != content:
            print(f"Annotated {path}")
            path.write_text(new_content, encoding="utf-8")


if __name__ == "__main__":
    annotate_tests("tests")
