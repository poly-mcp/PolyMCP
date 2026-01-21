"""
skill_loader.py — Production-grade MCP Skill Loader

Loads and manages MCP skill markdown files with:
- Multiple loading strategies (lazy, eager, index-only)
- Intelligent caching with TTL + file-change invalidation
- Token estimation and budgeting utilities
- Error recovery and robust parsing
- Thread-safe operations
- Optional parallel loading (real implementation)
- Security hardening (path traversal, size limits, category validation)

Compatible with both generator naming conventions:
- INDEX.md + metadata.json
- _index.md + _metadata.json
"""

from __future__ import annotations

import json
import logging
import re
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError as FuturesTimeoutError
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

JsonDict = Dict[str, Any]


# -------------------------
# Models
# -------------------------

@dataclass(frozen=True)
class FileFingerprint:
    """Fingerprint for change detection without reading entire file each time."""
    mtime_ns: int
    size: int


@dataclass
class LoadedSkill:
    """Represents a loaded skill with metadata."""
    category: str
    content: str
    tools: List[JsonDict]
    tokens: int
    loaded_at: datetime
    file_path: Path
    fingerprint: FileFingerprint

    def is_expired(self, ttl_seconds: int) -> bool:
        return (datetime.now() - self.loaded_at) > timedelta(seconds=ttl_seconds)


@dataclass
class LoadingStats:
    """Statistics for skill loading operations."""
    total_skills_loaded: int = 0
    total_tokens_loaded: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    load_time_ms: float = 0.0
    strategy_used: str = ""
    categories_loaded: List[str] = field(default_factory=list)

    @property
    def cache_hit_rate(self) -> float:
        total = self.cache_hits + self.cache_misses
        return 0.0 if total == 0 else (self.cache_hits / total) * 100.0


# -------------------------
# Loader
# -------------------------

class SkillLoader:
    """
    Production-grade skill loader with caching and strategies.

    Strategies:
    - "lazy": load index + load skills on demand (default)
    - "eager": load index + all skills immediately
    - "index_only": only load index (no category files)

    Cache:
    - TTL-based
    - invalidated if file changes (mtime+size)

    Security:
    - Path traversal protection (incl. symlink escape best-effort)
    - File size limits
    - Category name validation
    - Tool count limits
    - Timeout on parallel operations
    """

    INDEX_CANDIDATES = ("INDEX.md", "_index.md")
    METADATA_CANDIDATES = ("metadata.json", "_metadata.json")

    # Security limits (defaults)
    MAX_FILE_SIZE = 10_000_000  # 10MB
    MAX_TOOLS_PER_SKILL = 1000
    MAX_CATEGORY_NAME_LENGTH = 100
    PARALLEL_TIMEOUT_S = 30.0

    # Category: alnum/_/-
    _CATEGORY_RE = re.compile(r"^[a-zA-Z0-9_\-]+$")

    # Tool headings: ### name or ### `name`
    _H3_HEADER_RE = re.compile(
        r"^###\s+(?P<title>`[^`]+`|[^\n#]+)\s*$",
        re.MULTILINE,
    )

    def __init__(
        self,
        skills_dir: str = "./mcp_skills",
        cache_ttl: int = 3600,
        strategy: str = "lazy",
        verbose: bool = False,
        max_workers: int = 4,
        strict_utf8: bool = True,
        max_file_size: Optional[int] = None,
        max_tools_per_skill: Optional[int] = None,
    ):
        self.skills_dir = Path(skills_dir).resolve()
        self.cache_ttl = int(cache_ttl)
        self.strategy = str(strategy).strip()
        self.verbose = bool(verbose)
        self.max_workers = max(1, min(int(max_workers), 16))
        self.strict_utf8 = bool(strict_utf8)

        self.max_file_size = int(max_file_size or self.MAX_FILE_SIZE)
        self.max_tools_per_skill = int(max_tools_per_skill or self.MAX_TOOLS_PER_SKILL)

        # Thread-safety
        self._lock = threading.RLock()

        # Caches
        self._cache: Dict[str, LoadedSkill] = {}
        self._index_cache: Optional[str] = None
        self._index_fingerprint: Optional[FileFingerprint] = None
        self._metadata: Dict[str, Any] = {}

        # Stats
        self.stats = LoadingStats(strategy_used=self.strategy)

        if not self.skills_dir.exists() or not self.skills_dir.is_dir():
            raise FileNotFoundError(f"Skills directory not found or not a directory: {self.skills_dir}")

        if self.strategy not in ("lazy", "eager", "index_only"):
            raise ValueError("strategy must be one of: 'lazy', 'eager', 'index_only'")

        self._load_metadata()
        self.load_index()  # warm index (and validate structure)

        if self.strategy == "eager":
            self.load_all(parallel=True)

    # -------------------------
    # Public API
    # -------------------------

    def load_index(self, force_reload: bool = False) -> str:
        """
        Load the skills index (INDEX.md or _index.md).
        Cache invalidates if the file changes.
        """
        index_path = self._find_first_existing(self.INDEX_CANDIDATES)
        if not index_path:
            raise FileNotFoundError(f"Index file not found. Tried: {self.INDEX_CANDIDATES} in {self.skills_dir}")

        self._validate_path_in_dir(index_path)
        fp = self._fingerprint(index_path)

        # size check
        if fp.size > self.max_file_size:
            raise ValueError(f"Index file too large ({fp.size} bytes, max {self.max_file_size}): {index_path}")

        with self._lock:
            if not force_reload and self._index_cache is not None and self._index_fingerprint == fp:
                self._stats_hit()
                return self._index_cache

            self._stats_miss()

        content = self._read_text(index_path)

        with self._lock:
            self._index_cache = content
            self._index_fingerprint = fp
            self._stats_add_tokens(self._estimate_tokens(content))

        if self.verbose:
            logger.info("Loaded index from %s (~%d tokens)", index_path.name, self._estimate_tokens(content))

        return content

    def load_skill(self, category: str, force_reload: bool = False) -> LoadedSkill:
        """
        Load a category markdown file (e.g. filesystem.md).
        Cache invalidates on TTL expiration or file change.
        """
        category = self._validate_category_name(category)
        file_path = self._safe_join(self.skills_dir, f"{category}.md")

        if not file_path.exists() or not file_path.is_file():
            raise FileNotFoundError(f"Skill file not found: {file_path}")

        self._validate_path_in_dir(file_path)
        fp = self._fingerprint(file_path)

        if fp.size > self.max_file_size:
            raise ValueError(f"File too large ({fp.size} bytes, max {self.max_file_size}): {file_path}")

        with self._lock:
            cached = self._cache.get(category)
            if not force_reload and cached is not None:
                if not cached.is_expired(self.cache_ttl) and cached.fingerprint == fp:
                    self._stats_hit()
                    if self.verbose:
                        logger.info("Cache hit: %s", category)
                    return cached
                # invalidate
                self._cache.pop(category, None)

            self._stats_miss()

        # Load outside lock
        content = self._read_text(file_path)
        tools = self._extract_tools_from_content(content)

        if len(tools) > self.max_tools_per_skill:
            if self.verbose:
                logger.warning("Truncating %d tools to %d for category %s", len(tools), self.max_tools_per_skill, category)
            tools = tools[: self.max_tools_per_skill]

        tokens = self._estimate_tokens(content)

        skill = LoadedSkill(
            category=category,
            content=content,
            tools=tools,
            tokens=tokens,
            loaded_at=datetime.now(),
            file_path=file_path,
            fingerprint=fp,
        )

        with self._lock:
            self._cache[category] = skill
            self._stats_skill_loaded(category, tokens)

        if self.verbose:
            logger.info("Loaded skill: %s (~%d tokens, %d tools)", category, tokens, len(tools))

        return skill

    def load_multiple(
        self,
        categories: List[str],
        parallel: bool = False,
        timeout: Optional[float] = None
    ) -> Dict[str, LoadedSkill]:
        """
        Load multiple categories, optionally in parallel.
        Missing categories are skipped (best-effort).
        """
        start = datetime.now()
        cats = [c for c in (categories or []) if isinstance(c, str) and c.strip()]
        if not cats:
            return {}

        timeout_s = float(timeout or self.PARALLEL_TIMEOUT_S)

        loaded: Dict[str, LoadedSkill] = {}

        if not parallel or len(cats) == 1:
            for c in cats:
                try:
                    loaded[c] = self.load_skill(c)
                except FileNotFoundError:
                    if self.verbose:
                        logger.warning("Skipped missing category: %s", c)
                except Exception as e:
                    if self.verbose:
                        logger.error("Failed loading %s: %s", c, str(e))
            self._add_elapsed_ms(start)
            return loaded

        with ThreadPoolExecutor(max_workers=self.max_workers) as ex:
            futures = {ex.submit(self.load_skill, c): c for c in cats}
            try:
                for fut in as_completed(futures, timeout=timeout_s):
                    c = futures[fut]
                    try:
                        loaded[c] = fut.result()
                    except FileNotFoundError:
                        if self.verbose:
                            logger.warning("Skipped missing category: %s", c)
                    except Exception as e:
                        if self.verbose:
                            logger.error("Failed loading %s: %s", c, str(e))
            except FuturesTimeoutError:
                if self.verbose:
                    logger.error("Parallel loading timeout after %.2f seconds", timeout_s)
                for fut in futures:
                    fut.cancel()

        self._add_elapsed_ms(start)
        return loaded

    def load_all(self, parallel: bool = True, timeout: Optional[float] = None) -> Dict[str, LoadedSkill]:
        """Load all categories found in the directory."""
        if self.verbose:
            logger.info("Loading all skills from %s...", self.skills_dir)
        return self.load_multiple(self.get_available_categories(), parallel=parallel, timeout=timeout)

    def get_available_categories(self) -> List[str]:
        """List *.md files excluding index/special files."""
        cats: Set[str] = set()
        for p in self.skills_dir.glob("*.md"):
            try:
                self._validate_path_in_dir(p)
            except ValueError:
                continue

            if p.name in self.INDEX_CANDIDATES:
                continue
            if p.name.startswith("_"):
                continue

            stem = p.stem
            try:
                stem = self._validate_category_name(stem)
                cats.add(stem)
            except ValueError:
                if self.verbose:
                    logger.warning("Skipping invalid category name: %s", stem)
        return sorted(cats)

    def clear_cache(self, category: Optional[str] = None) -> None:
        with self._lock:
            if category:
                category = self._validate_category_name(category)
                self._cache.pop(category, None)
                if self.verbose:
                    logger.info("Cleared cache: %s", category)
            else:
                self._cache.clear()
                self._index_cache = None
                self._index_fingerprint = None
                if self.verbose:
                    logger.info("Cleared all cache")

    def get_cached_categories(self) -> List[str]:
        with self._lock:
            return list(self._cache.keys())

    def get_stats(self) -> LoadingStats:
        # Return a snapshot to avoid races/inconsistent reads
        with self._lock:
            return replace(self.stats, categories_loaded=list(self.stats.categories_loaded))

    def get_total_skills(self) -> int:
        return len(self.get_available_categories())

    def estimate_tokens(self, tools: List[Dict[str, Any]]) -> int:
        """
        Estimate token count for a list of tools (name + description + schema + overhead).
        Deterministic heuristic (not model-specific).
        """
        total = 0
        for t in tools or []:
            name = str(t.get("name", ""))
            desc = str(t.get("description", ""))
            schema = t.get("inputSchema", t.get("input_schema", {}))
            schema_str = json.dumps(schema, ensure_ascii=False) if isinstance(schema, (dict, list)) else str(schema)
            total += max(1, len(name) // 4)
            total += max(1, len(desc) // 4)
            total += max(1, len(schema_str) // 4)
            total += 40
        return total

    # -------------------------
    # Metadata
    # -------------------------

    def _load_metadata(self) -> None:
        meta_path = self._find_first_existing(self.METADATA_CANDIDATES)
        if not meta_path:
            with self._lock:
                self._metadata = {}
            if self.verbose:
                logger.info("No metadata file found (tried %s)", self.METADATA_CANDIDATES)
            return

        try:
            self._validate_path_in_dir(meta_path)
            fp = self._fingerprint(meta_path)
            if fp.size > self.max_file_size:
                raise ValueError(f"Metadata file too large ({fp.size} bytes, max {self.max_file_size})")

            text = self._read_text(meta_path)
            data = json.loads(text) if text else {}
            if not isinstance(data, dict):
                data = {}

            with self._lock:
                self._metadata = data

            if self.verbose:
                logger.info("Loaded metadata from %s", meta_path.name)

        except Exception as e:
            with self._lock:
                self._metadata = {}
            if self.verbose:
                logger.warning("Failed to load metadata from %s: %s", getattr(meta_path, "name", "<unknown>"), e)

    def get_metadata(self) -> Dict[str, Any]:
        with self._lock:
            return dict(self._metadata)

    # -------------------------
    # Security validators
    # -------------------------

    def _validate_category_name(self, category: str) -> str:
        category = (category or "").strip()
        if not category:
            raise ValueError("category must be a non-empty string")

        if len(category) > self.MAX_CATEGORY_NAME_LENGTH:
            raise ValueError(f"category name too long (max {self.MAX_CATEGORY_NAME_LENGTH}): {category[:50]}...")

        # Block traversal and null bytes
        if any(x in category for x in ("/", "\\", "\0")) or ".." in category:
            raise ValueError(f"Invalid category name (path traversal): {category}")

        if not self._CATEGORY_RE.match(category):
            raise ValueError(f"Invalid category name (invalid characters): {category}")

        return category

    def _validate_path_in_dir(self, path: Path) -> None:
        """
        Validate that 'path' resolves within skills_dir.
        Best-effort protection against traversal and symlink escapes.
        """
        try:
            base = self.skills_dir.resolve()
            resolved = path.resolve()
            resolved.relative_to(base)
        except Exception:
            raise ValueError(f"Path traversal detected: {path}")

    def _safe_join(self, base: Path, *parts: str) -> Path:
        """
        Safely join path components and validate the result is within base.
        """
        # Avoid accepting absolute parts
        for part in parts:
            if not part or part.startswith(("/", "\\")):
                raise ValueError(f"Invalid path component: {part!r}")

        result = (base.joinpath(*parts)).resolve()
        try:
            result.relative_to(base)
        except ValueError:
            raise ValueError(f"Path traversal detected: {'/'.join(parts)}")
        return result

    # -------------------------
    # Parsing
    # -------------------------

    def _extract_tools_from_content(self, content: str) -> List[Dict[str, Any]]:
        """
        Extract tools from markdown.

        Supports:
        - ### tool_name
        - ### `tool_name`

        Captures a conservative description slice for each tool.
        """
        if not content:
            return []

        matches = list(self._H3_HEADER_RE.finditer(content))
        if not matches:
            return []

        tools: List[Dict[str, Any]] = []

        for i, m in enumerate(matches):
            title = (m.group("title") or "").strip()
            if title.startswith("`") and title.endswith("`"):
                title = title[1:-1].strip()

            start = m.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(content)
            block = content[start:end].strip()

            desc = self._extract_description(block)
            if title:
                tools.append({"name": title, "description": desc})

        return tools

    def _extract_description(self, block: str) -> str:
        if not block:
            return ""

        # Cut before subheaders like #### Example / Best practices
        idx = block.find("\n#### ")
        if idx != -1:
            block = block[:idx].strip()

        # Remove fenced code blocks (examples often pollute description)
        block = self._strip_fenced_code(block)

        # Normalize whitespace: keep first paragraph group deterministically
        lines = [ln.rstrip() for ln in block.splitlines()]

        while lines and not lines[0].strip():
            lines.pop(0)

        out_lines: List[str] = []
        blank_after_content = False
        for ln in lines:
            if not ln.strip():
                if out_lines:
                    blank_after_content = True
                if blank_after_content:
                    break
                out_lines.append("")
            else:
                out_lines.append(ln)

        return "\n".join(out_lines).strip()

    def _strip_fenced_code(self, text: str) -> str:
        # Remove triple-backtick fenced blocks (non-greedy)
        return re.sub(r"```.*?```", "", text, flags=re.DOTALL)

    # -------------------------
    # IO helpers
    # -------------------------

    def _read_text(self, path: Path) -> str:
        """
        Robust text read:
        - UTF-8 by default
        - if strict_utf8=False, uses errors='replace'
        """
        self._validate_path_in_dir(path)
        if self.strict_utf8:
            return path.read_text(encoding="utf-8")
        return path.read_text(encoding="utf-8", errors="replace")

    def _fingerprint(self, path: Path) -> FileFingerprint:
        st = path.stat()
        return FileFingerprint(mtime_ns=st.st_mtime_ns, size=st.st_size)

    def _find_first_existing(self, candidates: Tuple[str, ...]) -> Optional[Path]:
        for name in candidates:
            p = self.skills_dir / name
            if p.exists() and p.is_file():
                return p
        return None

    def _estimate_tokens(self, content: str) -> int:
        return max(1, len(content) // 4)

    def _add_elapsed_ms(self, start: datetime) -> None:
        elapsed = (datetime.now() - start).total_seconds() * 1000.0
        with self._lock:
            self.stats.load_time_ms += elapsed

    # -------------------------
    # Stats helpers (locked)
    # -------------------------

    def _stats_hit(self) -> None:
        with self._lock:
            self.stats.cache_hits += 1

    def _stats_miss(self) -> None:
        with self._lock:
            self.stats.cache_misses += 1

    def _stats_add_tokens(self, tokens: int) -> None:
        with self._lock:
            self.stats.total_tokens_loaded += int(tokens)

    def _stats_skill_loaded(self, category: str, tokens: int) -> None:
        with self._lock:
            self.stats.total_skills_loaded += 1
            self.stats.total_tokens_loaded += int(tokens)
            if category not in self.stats.categories_loaded:
                self.stats.categories_loaded.append(category)
