"""
skills_sh.py — Load and match skills.sh skills for agent prompts.

Skills are installed under ~/.agents/skills/<skill>/SKILL.md
This module reads those files, parses frontmatter, and builds a compact
context block for LLM prompts.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional

@dataclass
class SkillShEntry:
    name: str
    description: str
    content: str
    path: Path


_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
_KV_RE = re.compile(r"^([a-zA-Z0-9_\-]+)\s*:\s*(.*)$")
_WORD_RE = re.compile(r"[a-z0-9_]+")


def _parse_frontmatter(text: str) -> tuple[dict, str]:
    match = _FRONTMATTER_RE.match(text)
    if not match:
        return {}, text
    fm = {}
    for line in match.group(1).splitlines():
        m = _KV_RE.match(line.strip())
        if not m:
            continue
        key = m.group(1).strip()
        val = m.group(2).strip().strip('"').strip("'")
        fm[key] = val
    rest = text[match.end():]
    return fm, rest


def _default_skills_dirs(extra_dirs: Optional[Iterable[str]] = None) -> List[Path]:
    dirs: List[Path] = []
    env_dirs = os.environ.get("POLYMCP_SKILLS_DIRS") or os.environ.get("SKILLS_DIRS")
    if env_dirs:
        for part in env_dirs.split(os.pathsep):
            part = part.strip()
            if part:
                dirs.append(Path(part).expanduser())

    if extra_dirs:
        for d in extra_dirs:
            if d:
                dirs.append(Path(d).expanduser())

    # Project-local options
    cwd = Path.cwd()
    dirs.extend([
        cwd / ".agents" / "skills",
        cwd / ".skills",
    ])

    # Global user skills.sh location
    home = Path.home()
    dirs.append(home / ".agents" / "skills")

    # De-dup and keep existing
    unique: List[Path] = []
    seen = set()
    for d in dirs:
        d = d.resolve()
        if str(d) in seen:
            continue
        seen.add(str(d))
        if d.exists() and d.is_dir():
            unique.append(d)
    return unique


def load_skills_sh(extra_dirs: Optional[Iterable[str]] = None, max_chars: int = 12000) -> List[SkillShEntry]:
    entries: List[SkillShEntry] = []
    for base in _default_skills_dirs(extra_dirs):
        for skill_dir in base.iterdir():
            if not skill_dir.is_dir():
                continue
            skill_file = skill_dir / "SKILL.md"
            if not skill_file.exists():
                continue
            try:
                text = skill_file.read_text(encoding="utf-8")
            except Exception:
                try:
                    text = skill_file.read_text(encoding="latin-1")
                except Exception:
                    continue
            if len(text) > max_chars:
                text = text[:max_chars]
            fm, rest = _parse_frontmatter(text)
            name = fm.get("name") or skill_dir.name
            desc = fm.get("description") or ""
            entries.append(
                SkillShEntry(
                    name=str(name),
                    description=str(desc),
                    content=rest.strip(),
                    path=skill_file,
                )
            )
    return entries


def match_skills_sh(
    query: str,
    skills: List[SkillShEntry],
    max_skills: int = 4,
) -> List[SkillShEntry]:
    if not skills:
        return []

    query_tokens = set(_WORD_RE.findall((query or "").lower()))
    if not query_tokens:
        return skills[:max_skills]

    def score(entry: SkillShEntry) -> float:
        haystack = f"{entry.name} {entry.description} {entry.content[:1500]}".lower()
        entry_tokens = set(_WORD_RE.findall(haystack))
        if not entry_tokens:
            return 0.0

        overlap = len(query_tokens & entry_tokens)
        if overlap == 0:
            return 0.0

        coverage = overlap / max(1, len(query_tokens))
        density = overlap / max(1, len(entry_tokens))
        phrase_bonus = 0.2 if query.strip().lower() in haystack else 0.0
        return (coverage * 0.75) + (density * 0.25) + phrase_bonus

    ranked = [(score(entry), entry) for entry in skills]
    ranked.sort(key=lambda item: item[0], reverse=True)
    selected = [entry for entry_score, entry in ranked if entry_score > 0.0]
    if not selected:
        return skills[:max_skills]
    return selected[:max_skills]


def build_skills_context(
    query: str,
    skills: List[SkillShEntry],
    max_skills: int = 4,
    max_total_chars: int = 5000,
    max_per_skill_chars: int = 1800,
) -> str:
    if not skills:
        return ""

    selected = match_skills_sh(query, skills, max_skills=max_skills)
    if not selected:
        return ""

    blocks: List[str] = []
    total = 0
    for s in selected:
        content = s.content
        if len(content) > max_per_skill_chars:
            content = content[:max_per_skill_chars].rstrip() + "\n[truncated]"
        block = f"### {s.name}\nDescription: {s.description}\n\n{content}"
        if total + len(block) > max_total_chars:
            break
        blocks.append(block)
        total += len(block)

    if not blocks:
        return ""
    return "SKILLS CONTEXT (skills.sh):\n\n" + "\n\n".join(blocks)
