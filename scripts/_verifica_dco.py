# -*- coding: utf-8 -*-
"""署 EVERY COMMIT SIGNED OFF — the Developer Certificate of Origin, checked.

    python scripts/_verifica_dco.py <base> <head>     # the commits base..head
    python scripts/_verifica_dco.py origin/main HEAD  # before you open a pull request

CONTRIBUTING.md asks every commit to carry the DCO sign-off
(`Signed-off-by: Name <email>`, what `git commit -s` writes). This is the check:
for each commit in `base..head` it looks for a sign-off whose e-mail is the
commit's author or committer. Merge commits are skipped — they bring no change
of their own (GitHub's "Update branch" makes them) — and so are the commits of
GitHub's own bots (Dependabot keeps the CI's actions current; a bot cannot
certify the DCO).

The continuous integration runs it on every pull request (the `dco` job of
`.github/workflows/ci.yml`) with the pull request's base and head.

How to fix a commit that fails:
    git commit --amend -s --no-edit             # the last commit
    git rebase --signoff <base>                 # every commit of the branch
then push again (`git push --force-with-lease`).
"""
from __future__ import annotations

import os
import re
import subprocess
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SIGNOFF = re.compile(r"^Signed-off-by:\s*(?P<name>.+?)\s*<(?P<email>[^<>\s]+@[^<>\s]+)>\s*$", re.M)
SEP = "\x1e"  # record separator between commits, \x1f between fields


def commits(base: str, head: str, cwd: str | None = None) -> list[dict]:
    fmt = "%H%x1f%P%x1f%an%x1f%ae%x1f%ce%x1f%B" + SEP
    r = subprocess.run(["git", "log", f"--format={fmt}", f"{base}..{head}"], cwd=cwd,
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip() or "git log failed")
    out = []
    for bloco in r.stdout.split(SEP):
        bloco = bloco.strip("\n")
        if not bloco:
            continue
        sha, pais, autor, a_mail, c_mail, corpo = bloco.split("\x1f", 5)
        out.append({"sha": sha, "parents": pais.split(), "author": autor,
                    "author_email": a_mail, "committer_email": c_mail, "message": corpo})
    return out


def check(base: str, head: str, cwd: str | None = None) -> tuple[int, list[str]]:
    """(commits checked, problems). A problem names the commit and what is missing."""
    lista = commits(base, head, cwd)
    problemas = []
    vistos = 0
    for c in lista:
        if len(c["parents"]) > 1 or c["author_email"].lower().endswith("[bot]@users.noreply.github.com"):
            continue
        vistos += 1
        mails = {m.group("email").lower() for m in SIGNOFF.finditer(c["message"])}
        titulo = (c["message"].splitlines() or [""])[0][:72]
        if not mails:
            problemas.append(f"{c['sha'][:10]} \"{titulo}\" — no Signed-off-by line")
        elif not mails & {c["author_email"].lower(), c["committer_email"].lower()}:
            problemas.append(f"{c['sha'][:10]} \"{titulo}\" — signed off as {sorted(mails)}, "
                             f"but the author is <{c['author_email']}>")
    return vistos, problemas


def wrong_repository(cwd: str | None = None) -> str | None:
    """Why the repository git finds from `cwd` is not the one to check — or None.

    A copy of this project with no `.git` of its own, kept inside ANOTHER
    repository, makes git walk up and answer for that one: its commits would be
    checked and blamed on this project."""
    r = subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=cwd,
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        return None  # not a repository at all: `git log` says so itself
    top = os.path.normcase(os.path.realpath(r.stdout.strip()))
    me = os.path.normcase(os.path.realpath(ROOT))
    if top != me and os.path.commonpath([top, me]) == top:
        return (f"this project has no git repository of its own — git answered for the one "
                f"around it ({r.stdout.strip()}). Run `git init` in {ROOT} first.")
    return None


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__)
        return 2
    base, head = sys.argv[1], sys.argv[2]
    why = wrong_repository()
    if why:
        print(f"❌ {why}")
        return 2
    try:
        vistos, problemas = check(base, head)
    except RuntimeError as e:
        print(f"❌ could not read the commits {base}..{head}: {e}")
        return 2
    print(f"署 DCO — {vistos} commit(s) in {base[:12]}..{head[:12]} (merges and bots skipped)")
    for p in problemas:
        print(f"  ❌ {p}")
    if problemas:
        print("\nEvery commit needs `Signed-off-by: Your Name <you@example.com>` — see CONTRIBUTING.md.\n"
              "Fix the last commit with `git commit --amend -s --no-edit`, or the whole branch with\n"
              f"`git rebase --signoff {base[:12]}`, then `git push --force-with-lease`.")
        print(f"RESULT: {len(problemas)} commit(s) not signed off")
        return 1
    print("RESULT: every commit is signed off")
    return 0


if __name__ == "__main__":
    sys.exit(main())
