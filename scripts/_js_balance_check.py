"""Quick bracket-balance check for the mini-app JS files. Ignores braces inside
strings/comments/template literals. Returns 0 if balanced, otherwise a delta
counts per kind. Not a real parser — good enough for catching gross diffs."""
import sys


def balance(path: str) -> dict[str, int]:
    s = open(path, encoding="utf-8").read()
    counts = {"(": 0, ")": 0, "{": 0, "}": 0, "[": 0, "]": 0}
    BS = chr(92)  # backslash
    BT = chr(96)  # backtick
    in_str = False     # holds the opening quote when inside a string
    in_tmpl = False
    in_line_comment = False
    in_block_comment = False
    i = 0
    while i < len(s):
        c = s[i]
        nxt = s[i + 1] if i + 1 < len(s) else ""
        if in_line_comment:
            if c == "\n":
                in_line_comment = False
        elif in_block_comment:
            if c == "*" and nxt == "/":
                in_block_comment = False
                i += 1
        elif in_str:
            if c == BS:
                i += 1  # skip the escaped char
            elif c == in_str:
                in_str = False
        elif in_tmpl:
            if c == BS:
                i += 1
            elif c == BT:
                in_tmpl = False
            # Note: template-literal interpolations ${...} are well-formed in
            # this codebase; not bothering to track nested braces inside them.
        else:
            if c == "/" and nxt == "/":
                in_line_comment = True
                i += 1
            elif c == "/" and nxt == "*":
                in_block_comment = True
                i += 1
            elif c == '"' or c == "'":
                in_str = c
            elif c == BT:
                in_tmpl = True
            elif c in counts:
                counts[c] += 1
        i += 1
    return counts


def main():
    for f in sys.argv[1:]:
        c = balance(f)
        diff_p = c["("] - c[")"]
        diff_c = c["{"] - c["}"]
        diff_b = c["["] - c["]"]
        ok = (diff_p == 0 and diff_c == 0 and diff_b == 0)
        flag = "OK" if ok else "FAIL"
        print(f"{flag} {f}: paren={diff_p}, brace={diff_c}, bracket={diff_b}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
