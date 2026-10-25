"""Strip JS string literals + comments then check paren/brace balance.

Used as a fast smoke test for the mini-app components after a sprint
that adds new JSX (where naive char counting trips on emojis, i18n
strings containing parens, etc).
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _strip(src: str) -> str:
    # Block comments
    src = re.sub(r"/\*[\s\S]*?\*/", "", src)
    # Line comments — but skip URLs (http:// etc)
    src = re.sub(r"(?<![:'\"a-zA-Z])//[^\n]*", "", src)
    # String literals
    src = re.sub(r"'(?:\\.|[^'\\])*'", "''", src)
    src = re.sub(r'"(?:\\.|[^"\\])*"', '""', src)
    # Template literals (greedy enough for non-nested cases)
    src = re.sub(r"`(?:\\.|[^`\\])*`", "``", src)
    return src


def _check(name: str, opens: str, closes: str, src: str) -> bool:
    o = src.count(opens)
    c = src.count(closes)
    ok = (o == c)
    flag = "OK" if ok else "FAIL"
    print(f"  {flag} {name}: {o}/{c} (delta={o - c})")
    return ok


def main() -> int:
    fnames = [
        "miniapp/components/tabs.js",
        "miniapp/components/ui.js",
        "miniapp/components/app.js",
    ]
    all_ok = True
    for fn in fnames:
        src = (ROOT / fn).read_text(encoding="utf-8")
        stripped = _strip(src)
        print(f"\n{fn}:")
        ok = True
        ok &= _check("braces  ", "{", "}", stripped)
        ok &= _check("parens  ", "(", ")", stripped)
        ok &= _check("brackets", "[", "]", stripped)
        all_ok &= ok
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
