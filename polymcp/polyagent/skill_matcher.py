"""
skill_matcher.py — Production-grade Skill Matcher

Matches a natural language query to the most relevant tools/skills.

Key properties:
- Multilingual-friendly (Italian + English) stopwords
- Lightweight stemming (no external deps)
- Deterministic, stable scoring
- BM25-like scoring on tool name + description (weighted fields)
- Boosts for name matches and exact phrase matches
- Penalizes overly generic tools unless query aligns
- Production hardening: input validation, resource limits, stable ties, cacheable index

Recommended usage (production):
1) Build an index once (or whenever skills change):
      idx = SkillMatcher().build_index_from_skills(skills_dict)
2) Match queries against the index:
      results = SkillMatcher().match_index("query", idx, top_k=10)

Backward-friendly:
- You can still call match(query, skills) and it will build a temporary index,
  but that's slower for repeated queries.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

JsonDict = Dict[str, Any]


# -------------------------
# Data models
# -------------------------

@dataclass(frozen=True)
class MatchResult:
    tool_name: str
    category: str
    score: float
    description: str
    source: Optional[str] = None
    tool: Optional[JsonDict] = None


@dataclass(frozen=True)
class _Doc:
    """Internal compiled document representation."""
    category: str
    name: str
    desc: str
    source: Optional[str]
    tool: JsonDict

    name_norm: str
    desc_norm: str

    name_toks: Tuple[str, ...]
    desc_toks: Tuple[str, ...]
    all_toks: Tuple[str, ...]  # name + desc


@dataclass(frozen=True)
class MatchIndex:
    """
    Precomputed corpus index for fast repeated matching.
    - docs: compiled tools
    - idf: token -> idf
    - avgdl: average doc length
    - df: token -> document frequency (optional, useful for debugging)
    """
    docs: Tuple[_Doc, ...]
    idf: Dict[str, float]
    avgdl: float
    doc_count: int


# -------------------------
# Matcher
# -------------------------

class SkillMatcher:
    """
    Production-grade skill matcher with security hardening.

    Main improvement vs naive implementations:
    - Supports precompiled index to avoid recomputing IDF/TF each time.
    """

    # Security limits (hard caps)
    MAX_QUERY_LENGTH = 1000
    MAX_TOOLS_COUNT = 10000
    MAX_DESCRIPTION_LENGTH = 5000
    MAX_TOOL_NAME_LENGTH = 200
    MAX_CATEGORY_NAME_LENGTH = 100
    MAX_TOKENS_PER_TEXT = 500
    MAX_TOKEN_LEN = 50

    # Regex is intentionally simple (no nested quantifiers)
    _TOKEN_RE = re.compile(r"[0-9A-Za-zÀ-ÿ_]+", re.UNICODE)
    _WS_RE = re.compile(r"\s+", re.UNICODE)

    def __init__(
        self,
        *,
        min_score: float = 0.15,
        name_boost: float = 2.2,
        exact_phrase_boost: float = 1.6,
        max_desc_chars: int = 600,
        debug: bool = False,
        max_query_length: Optional[int] = None,
        max_tools_count: Optional[int] = None,
        # BM25-ish params
        k1: float = 1.5,
        b: float = 0.75,
        # Field weighting (name generally more important)
        name_field_weight: float = 1.35,
        desc_field_weight: float = 1.00,
    ):
        self.min_score = float(min_score)
        self.name_boost = float(name_boost)
        self.exact_phrase_boost = float(exact_phrase_boost)
        self.max_desc_chars = min(int(max_desc_chars), self.MAX_DESCRIPTION_LENGTH)
        self.debug = bool(debug)

        self.max_query_length = int(max_query_length or self.MAX_QUERY_LENGTH)
        self.max_tools_count = int(max_tools_count or self.MAX_TOOLS_COUNT)

        self.k1 = float(k1)
        self.b = float(b)
        self.name_field_weight = float(name_field_weight)
        self.desc_field_weight = float(desc_field_weight)

        # Stopwords (IT + EN), minimal but effective
        self.stopwords = set(
            """
            a ad al allo agli all ai alle anche ancora avanti avere
            che chi ci cio cioe come con contro da dal dallo dai dagli dalle
            del dello dei degli delle dentro di dove e è ed era eri ero essere
            fa fai fanno fare fino fra fu ha hai hanno ho i il in indietro io
            la le lei li lo loro lui ma me mi mia mie miei mio molta molte molti molto
            ne nel nello nei negli nelle no noi non nuovo o od ogni ora per pero perché
            piu più poco poi prima proprio quale quali quando quanto quasi qui
            se sei siamo sia si sì solo sono sopra su sua sue sugli sul sulla sulle
            tra troppo tu tuo tuoi tutta tutte tutti tutto un una uno
            voi
            the a an and or but if then else when where who what why how
            to of in on at by for from with without into onto over under
            is are was were be been being do does did doing done
            i you he she it we they me him her us them my your his their our
            this that these those there here
            """.split()
        )

        # “Generic” tokens that appear in many tool names; used for penalty
        self.generic_terms = set(
            """
            tool tools run execute call request fetch get post list create update delete
            read write open close start stop process action handle helper util utility
            """.split()
        )

        # Common intent tokens that should reduce generic penalty if present in query
        self.intent_terms = set(
            """
            file filesystem path directory folder json csv sql database query email mail notify notification
            browser web screenshot click playwright github git auth token encrypt decrypt
            """.split()
        )

    # -------------------------
    # Public API (high-level)
    # -------------------------

    def match(
        self,
        query: str,
        skills: Dict[str, Dict[str, Any]],
        *,
        top_k: int = 10,
    ) -> List[MatchResult]:
        """
        Convenience: builds a temporary index and matches once.
        For repeated usage, prefer build_index_from_skills + match_index.
        """
        idx = self.build_index_from_skills(skills)
        return self.match_index(query, idx, top_k=top_k)

    def build_index_from_skills(self, skills: Dict[str, Dict[str, Any]]) -> MatchIndex:
        """
        Build a compiled index from SkillLoader-like structure:
          {
            "filesystem": {"tools": [...], ...},
            "api": {"tools": [...], ...},
          }
        """
        tools: List[Tuple[str, JsonDict]] = []

        for cat, payload in (skills or {}).items():
            if not isinstance(cat, str) or not cat or len(cat) > self.MAX_CATEGORY_NAME_LENGTH:
                continue
            if not isinstance(payload, dict):
                continue

            tlist = payload.get("tools", [])
            if not isinstance(tlist, list):
                continue

            for t in tlist:
                if isinstance(t, dict):
                    tools.append((cat, t))
                    if len(tools) >= self.max_tools_count:
                        break
            if len(tools) >= self.max_tools_count:
                break

        return self.build_index(tools)

    def build_index(self, tools: Sequence[Tuple[str, JsonDict]]) -> MatchIndex:
        """
        Build a compiled corpus index from a flat list of (category, tool_dict).
        This is the recommended production entrypoint (cache the result).
        """
        docs: List[_Doc] = []
        capped = tools[: self.max_tools_count] if len(tools) > self.max_tools_count else tools

        for category, tool in capped:
            if not isinstance(category, str) or len(category) > self.MAX_CATEGORY_NAME_LENGTH:
                continue
            if not isinstance(tool, dict):
                continue

            name = str(tool.get("name", "")).strip()
            if not name or len(name) > self.MAX_TOOL_NAME_LENGTH:
                continue

            desc = str(tool.get("description", "") or "").strip()
            if len(desc) > self.MAX_DESCRIPTION_LENGTH:
                desc = desc[: self.MAX_DESCRIPTION_LENGTH]

            source = tool.get("_server_name") or tool.get("_server_url")
            source_str = str(source) if source is not None else None

            name_norm = self._normalize(name)
            desc_norm = self._normalize(desc)

            name_toks = tuple(self._tokens(name_norm))
            desc_toks = tuple(self._tokens(desc_norm))
            if not name_toks and not desc_toks:
                continue

            all_toks = name_toks + desc_toks

            docs.append(
                _Doc(
                    category=category,
                    name=name,
                    desc=desc,
                    source=source_str,
                    tool=tool,
                    name_norm=name_norm,
                    desc_norm=desc_norm,
                    name_toks=name_toks,
                    desc_toks=desc_toks,
                    all_toks=all_toks,
                )
            )

        idf, avgdl = self._compute_idf_and_avgdl(docs)
        return MatchIndex(docs=tuple(docs), idf=idf, avgdl=avgdl, doc_count=len(docs))

    def match_index(self, query: str, index: MatchIndex, *, top_k: int = 10) -> List[MatchResult]:
        """
        Match a query against a precomputed index.
        """
        q = self._validate_query(query)
        if not q or index.doc_count == 0:
            return []

        top_k = max(1, min(int(top_k), 100))

        q_norm = self._normalize(q)
        q_tokens = self._tokens(q_norm)
        if not q_tokens:
            return []

        scored: List[MatchResult] = []
        avgdl = max(1e-9, float(index.avgdl))
        idf = index.idf

        q_token_set = set(q_tokens)

        for d in index.docs:
            # Fielded BM25 scoring (name + desc with weights)
            score_name = self._bm25_like(q_tokens, d.name_toks, idf, avgdl)
            score_desc = self._bm25_like(q_tokens, d.desc_toks, idf, avgdl)
            score = self.name_field_weight * score_name + self.desc_field_weight * score_desc

            # Exact phrase boost (normalized)
            if len(q_norm) >= 4 and (q_norm in d.name_norm or q_norm in d.desc_norm):
                score *= self.exact_phrase_boost

            # Strong boost for name hits
            score *= self._name_match_boost(q_tokens, d.name_toks)

            # Penalize generic tool names unless query aligns
            score *= self._generic_penalty(q_token_set, d.name_toks)

            if score >= self.min_score:
                scored.append(
                    MatchResult(
                        tool_name=d.name,
                        category=d.category,
                        score=float(score),
                        description=self._truncate(d.desc, self.max_desc_chars),
                        source=d.source,
                        tool=d.tool,
                    )
                )

        # Stable ordering: score desc, then tool_name asc, then category asc
        scored.sort(key=lambda r: (-r.score, r.tool_name.lower(), r.category.lower()))
        return scored[:top_k]

    # -------------------------
    # Validation
    # -------------------------

    def _validate_query(self, query: str) -> str:
        if not isinstance(query, str):
            return ""
        q = query.strip()
        if not q:
            return ""
        if len(q) > self.max_query_length:
            q = q[: self.max_query_length]
        return q

    # -------------------------
    # Scoring internals
    # -------------------------

    def _compute_idf_and_avgdl(self, docs: Sequence[_Doc]) -> Tuple[Dict[str, float], float]:
        """
        IDF with smoothing:
          idf(t) = log(1 + (N - df + 0.5)/(df + 0.5))
        """
        df: Dict[str, int] = {}
        total_len = 0

        for d in docs:
            toks = d.all_toks
            total_len += len(toks)
            seen = set(toks)
            for t in seen:
                df[t] = df.get(t, 0) + 1

        N = len(docs)
        if N == 0:
            return {}, 0.0

        out: Dict[str, float] = {}
        for t, f in df.items():
            denom = f + 0.5
            out[t] = math.log(1.0 + (N - f + 0.5) / denom)

        avgdl = total_len / float(N) if N > 0 else 0.0
        return out, avgdl

    def _bm25_like(self, q_tokens: Sequence[str], doc_tokens: Sequence[str], idf: Dict[str, float], avgdl: float) -> float:
        """
        BM25-like scoring with k1/b tuning.
        Normalized by sqrt(query_len) for stability across long queries.
        """
        if not doc_tokens:
            return 0.0

        tf: Dict[str, int] = {}
        for t in doc_tokens:
            tf[t] = tf.get(t, 0) + 1

        dl = float(len(doc_tokens))
        k1 = self.k1
        b = self.b
        safe_avgdl = max(1e-9, float(avgdl))

        score = 0.0
        for qt in q_tokens:
            f = tf.get(qt)
            if not f:
                continue
            term_idf = idf.get(qt, 0.0)
            denom = f + k1 * (1.0 - b + b * (dl / safe_avgdl))
            if denom <= 0:
                continue
            score += term_idf * (f * (k1 + 1.0) / denom)

        qlen_norm = max(1.0, math.sqrt(float(len(q_tokens))))
        return score / qlen_norm

    def _name_match_boost(self, q_tokens: Sequence[str], name_tokens: Sequence[str]) -> float:
        if not name_tokens:
            return 1.0
        name_set = set(name_tokens)
        hits = sum(1 for t in q_tokens if t in name_set)
        if hits <= 0:
            return 1.0
        # Diminishing returns: 1 hit gives partial boost, 2+ saturates
        frac = min(1.0, hits / 2.0)
        return 1.0 + (self.name_boost - 1.0) * frac

    def _generic_penalty(self, q_token_set: set, name_tokens: Sequence[str]) -> float:
        """
        Penalize tools whose name is dominated by generic terms,
        unless query contains:
        - the same generic terms, or
        - intent signals (domain terms).
        """
        if not name_tokens:
            return 1.0

        name_toks = [t for t in name_tokens if t]  # already small
        if not name_toks:
            return 1.0

        generic_in_name = [t for t in name_toks if t in self.generic_terms]
        if not generic_in_name:
            return 1.0

        # If query contains any generic term appearing in name, do not penalize
        if any(t in q_token_set for t in generic_in_name):
            return 1.0

        # If query has intent signals, reduce penalty (user is specific)
        if any(t in q_token_set for t in self.intent_terms):
            return 0.94

        # If name is mostly generic terms, stronger penalty
        ratio = len(generic_in_name) / max(1, len(name_toks))
        if ratio >= 0.60:
            return 0.82
        return 0.90

    # -------------------------
    # Text normalization/tokenization
    # -------------------------

    def _normalize(self, text: str) -> str:
        s = (text or "").strip().lower()
        if not s:
            return ""
        # Cap before regex work (defensive)
        if len(s) > self.MAX_DESCRIPTION_LENGTH:
            s = s[: self.MAX_DESCRIPTION_LENGTH]
        # normalize quotes/backticks
        s = s.replace("`", "'")
        # collapse whitespace
        s = self._WS_RE.sub(" ", s)
        return s

    def _tokens(self, text: str) -> List[str]:
        if not text:
            return []
        # Cap before regex scan
        if len(text) > self.MAX_DESCRIPTION_LENGTH:
            text = text[: self.MAX_DESCRIPTION_LENGTH]

        raw = self._TOKEN_RE.findall(text)
        if not raw:
            return []

        if len(raw) > self.MAX_TOKENS_PER_TEXT:
            raw = raw[: self.MAX_TOKENS_PER_TEXT]

        out: List[str] = []
        for tok in raw:
            t = tok.lower()
            if len(t) > self.MAX_TOKEN_LEN:
                t = t[: self.MAX_TOKEN_LEN]
            t = self._stem_light(t)
            if not t or len(t) <= 1:
                continue
            if t in self.stopwords:
                continue
            out.append(t)

        return out

    def _stem_light(self, token: str) -> str:
        """
        Lightweight stemming IT/EN without dependencies.
        Conservative: improves recall without destroying precision.
        """
        t = token
        if not t:
            return ""

        # English possessive
        if len(t) > 2 and t.endswith("'s"):
            t = t[:-2]

        # English suffixes (conservative)
        if len(t) > 5 and t.endswith("ingly"):
            t = t[:-5]
        elif len(t) > 4 and t.endswith("ing"):
            t = t[:-3]
        elif len(t) > 4 and t.endswith("edly"):
            t = t[:-4]
        elif len(t) > 3 and t.endswith("ed"):
            t = t[:-2]
        elif len(t) > 3 and t.endswith("ly"):
            t = t[:-2]
        elif len(t) > 3 and t.endswith("s"):
            # plural, keep short words intact
            t = t[:-1]

        # Italian suffixes (very conservative)
        for suf in ("mente", "zione", "zioni", "amento", "amenti", "azione", "azioni"):
            if len(t) > (len(suf) + 3) and t.endswith(suf):
                t = t[: -len(suf)]
                break

        # Remove a single trailing vowel for Italian inflections (only if alphabetic)
        if len(t) > 4 and t[-1] in ("a", "e", "i", "o"):
            # Avoid killing acronyms/identifiers with digits/underscore
            if t.isalpha():
                t = t[:-1]

        return t

    def _truncate(self, s: str, n: int) -> str:
        s = s or ""
        if len(s) <= n:
            return s
        return s[: max(0, n - 1)].rstrip() + "…"

import difflib
from typing import Optional

class FuzzyMatcher(SkillMatcher):
    def __init__(self, enable_fuzzy: bool = True, fuzzy_boost: float = 1.12, **kwargs):
        super().__init__(**kwargs)
        self.enable_fuzzy = bool(enable_fuzzy)
        self.fuzzy_boost = float(fuzzy_boost)

    def match_index(self, query: str, index: MatchIndex, *, top_k: int = 10) -> List[MatchResult]:
        results = super().match_index(query, index, top_k=top_k)

        if not self.enable_fuzzy:
            return results

        q = self._normalize(self._validate_query(query))
        if not q:
            return results

        # Light re-rank/boost: only if close-ish
        boosted = []
        for r in results:
            name_n = self._normalize(r.tool_name)
            # hard caps to keep it cheap
            if len(q) > 200 or len(name_n) > 200:
                boosted.append(r)
                continue

            sim = difflib.SequenceMatcher(a=q, b=name_n).ratio()
            if sim >= 0.72:
                r = MatchResult(
                    tool_name=r.tool_name,
                    category=r.category,
                    score=r.score * (1.0 + (sim - 0.72) * (self.fuzzy_boost - 1.0) / (1.0 - 0.72)),
                    description=r.description,
                    source=r.source,
                    tool=r.tool,
                )
            boosted.append(r)

        boosted.sort(key=lambda x: (-x.score, x.tool_name.lower(), x.category.lower()))
        return boosted[:top_k]


# -------------------------
# Convenience function
# -------------------------

def match_query_to_tools(query: str, skills: Dict[str, Dict[str, Any]], top_k: int = 10) -> List[MatchResult]:
    """
    Convenience helper for one-shot usage.
    For repeated usage, prefer:
        m = FuzzyMatcher()
        idx = m.build_index_from_skills(skills)
        m.match_index(query, idx, top_k=top_k)
    """
    m = FuzzyMatcher()
    idx = m.build_index_from_skills(skills)
    return m.match_index(query, idx, top_k=top_k)
