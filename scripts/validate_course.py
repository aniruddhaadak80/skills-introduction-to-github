#!/usr/bin/env python3
"""Structural validation for the Introduction to GitHub course template.

The course is driven by `skills/action-update-step@v2`, which rebuilds README.md
as `<header> + .github/steps/<step>.md + <footer>` and keeps `.github/steps/-step.txt`
in sync. That contract is invisible to a reader, so it is easy to break by hand
editing one side of it. This script asserts the contract still holds.

It is deliberately offline and deterministic: no network, no GitHub API.

    python scripts/validate_course.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STEPS_DIR = ROOT / ".github" / "steps"
WORKFLOWS_DIR = ROOT / ".github" / "workflows"
README = ROOT / "README.md"
IMAGES_DIR = ROOT / "images"

problems: list[str] = []


def fail(msg: str) -> None:
    problems.append(msg)


def block(text: str, tag: str) -> str:
    """Emulate the action's `awk '/<tag>/,/<\\/tag>/'` extraction."""
    m = re.search(rf"<{tag}>.*?</{tag}>", text, re.S)
    return m.group(0) if m else ""


def step_file(step: str) -> Path | None:
    """The action resolves a step with the glob `.github/steps/[<step>]-*.md`."""
    matches = sorted(STEPS_DIR.glob(f"[{step}]-*.md"))
    return matches[0] if len(matches) == 1 else None


def norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


# --- 1. the current step is resolvable ------------------------------------- #

step_file_txt = STEPS_DIR / "-step.txt"
if not step_file_txt.exists():
    fail(".github/steps/-step.txt is missing")
    current = None
else:
    current = step_file_txt.read_text(encoding="utf-8").strip()

if current:
    if step_file(current) is None:
        fail(f"-step.txt says step {current!r} but no unique .github/steps/[{current}]-*.md exists")

# --- 2. README.md is exactly header + current step + footer ----------------- #

if current and README.exists() and step_file(current) is not None:
    readme = README.read_text(encoding="utf-8")
    header, footer = block(readme, "header"), block(readme, "footer")
    if not header:
        fail("README.md has no <header> block")
    if not footer:
        fail("README.md has no <footer> block")
    body = step_file(current).read_text(encoding="utf-8").strip()
    rebuilt = f"{header}\n\n{body}\n\n{footer}".strip()
    if norm(rebuilt) != norm(readme):
        fail(
            "README.md is out of sync with "
            f".github/steps/{step_file(current).name}: it should be exactly "
            "<header> + the current step file + <footer>"
        )

# --- 3. every step file heading matches its filename ----------------------- #

for path in sorted(STEPS_DIR.glob("*.md")):
    if path.name == "-step.txt":
        continue
    text = path.read_text(encoding="utf-8")
    stem = path.name.split("-", 1)[0]
    if text.strip() == "<!-- readme -->":
        # The step-0 marker: the action keeps the current README verbatim.
        if stem != "0":
            fail(f"{path.name} is the '<!-- readme -->' marker but is not the step-0 file")
        continue
    heading = re.search(r"^##\s+(.+)$", text, re.M)
    if heading is None:
        fail(f"{path.name} has no '## ' heading")
        continue
    title = heading.group(1).strip()
    if stem == "X":
        if not title.lower().startswith("finish"):
            fail(f"{path.name} heading is {title!r}, expected the Finish step")
    elif not re.match(rf"^Step\s+{re.escape(stem)}\b", title):
        fail(f"{path.name} heading is {title!r}, expected 'Step {stem}: ...'")

# --- 4. every workflow transition resolves to a real step ------------------- #

for path in sorted(WORKFLOWS_DIR.glob("*.yml")):
    text = path.read_text(encoding="utf-8")
    for to_step in re.findall(r"^\s*to_step:\s*(\S+)\s*$", text, re.M):
        if step_file(to_step) is None:
            fail(f"{path.name}: to_step {to_step!r} has no .github/steps/[{to_step}]-*.md")
    for from_step in re.findall(r"^\s*from_step:\s*(\S+)\s*$", text, re.M):
        if from_step != "0" and step_file(from_step) is None:
            fail(f"{path.name}: from_step {from_step!r} has no .github/steps/[{from_step}]-*.md")

# --- 5. every referenced image exists --------------------------------------- #

markdown_files = [README] + sorted(STEPS_DIR.glob("*.md"))
for path in markdown_files:
    if not path.exists():
        continue
    for name in re.findall(r"/images/([A-Za-z0-9_.-]+\.png)", path.read_text(encoding="utf-8")):
        if not (IMAGES_DIR / name).exists():
            fail(f"{path.relative_to(ROOT).as_posix()} references missing image images/{name}")

# --- 6. the course footer link must resolve --------------------------------- #
# The upstream template points at the skills/.github discussion board; the
# organisation-level URL that a fork was pointed at does not exist and 404s.

COURSE_DISCUSSIONS = "https://github.com/skills/.github/discussions"
for path in markdown_files:
    if not path.exists():
        continue
    text = path.read_text(encoding="utf-8")
    for url in re.findall(r"https?://[^\s)\]\"'>]+", text):
        if "discussions" in url and url != COURSE_DISCUSSIONS:
            fail(
                f"{path.relative_to(ROOT).as_posix()} links to {url!r}, "
                f"which is not the course discussion board ({COURSE_DISCUSSIONS})"
            )

# --- report ----------------------------------------------------------------- #

if problems:
    print(f"FAIL: {len(problems)} problem(s)")
    for p in problems:
        print(f"  - {p}")
    sys.exit(1)

print(f"OK: course structure valid (current step: {current})")
