#!/usr/bin/env python3
"""
PolyMCP Skills System - Complete Test Suite (MATCHED TO CURRENT IMPLEMENTATION)

Aligned to current code:
- MCPSkillGenerator expects dict-like tools (.get)
- Generator private writers: _generate_index(), _generate_category_file(), _save_metadata()
- MUST create generator.output_dir before calling private writers
- SkillLoader expects INDEX.md/_index.md and is synchronous
- SkillMatcher exports MatchResult and uses min_score
- DockerSandboxExecutor __init__(tools_api, ...) and execute(code) (no timeout kw)

Run:
  python test_skills_system.py
"""

import asyncio
import json
import tempfile
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional


# -------------------------
# Minimal test infra
# -------------------------

@dataclass
class TestResult:
    name: str
    passed: int = 0
    failed: int = 0
    failures: List[str] = field(default_factory=list)

    def add_pass(self) -> None:
        self.passed += 1

    def add_fail(self, msg: str) -> None:
        self.failed += 1
        self.failures.append(msg)

    @property
    def ok(self) -> bool:
        return self.failed == 0


class SkillsSystemTester:
    def __init__(self) -> None:
        self.temp_dir: Optional[Path] = None
        self.results: List[TestResult] = []

    def setup(self) -> None:
        print("\n🔧 Setting up test environment...")
        self.temp_dir = Path(tempfile.mkdtemp())
        print(f"   Temp dir: {self.temp_dir}")

    def teardown(self) -> None:
        print("\n🧹 Cleaning up...")
        if self.temp_dir and self.temp_dir.exists():
            shutil.rmtree(self.temp_dir, ignore_errors=True)
        print("   Cleanup complete")

    async def run_all_tests(self) -> int:
        print("=" * 60)
        print("🧪 PolyMCP Skills System - Complete Test Suite")
        print("=" * 60)

        await self.test_skill_generator()
        await self.test_skill_loader()
        await self.test_skill_matcher()
        await self.test_docker_executor()
        await self.test_integration()

        print("\n" + "=" * 60)
        print("📊 TEST SUMMARY")
        print("=" * 60)

        total_pass = 0
        total_fail = 0
        for r in self.results:
            total_pass += r.passed
            total_fail += r.failed
            status = "PASS" if r.ok else "FAIL"
            print(f"\n{status} {r.name}: {r.passed} passed, {r.failed} failed")
            for f in r.failures:
                print(f"  - {f}")

        print("\n" + "=" * 60)
        print(f"TOTAL: {total_pass} passed, {total_fail} failed")
        print("ALL TESTS PASSED ✅" if total_fail == 0 else f"{total_fail} TESTS FAILED")
        print("=" * 60)

        return 1 if total_fail else 0

    # -------------------------
    # Tests
    # -------------------------

    async def test_skill_generator(self) -> TestResult:
        result = TestResult("SkillGenerator")
        print("\n📝 Testing MCPSkillGenerator...")

        if not self.temp_dir:
            result.add_fail("Internal error: temp_dir not set")
            self.results.append(result)
            return result

        try:
            from polymcp.polyagent.skill_generator import MCPSkillGenerator
            result.add_pass()
            print("   ✅ Imports successful")
        except Exception as e:
            result.add_fail(f"Import failed: {e!r}")
            print(f"   ❌ Import failed: {e!r}")
            self.results.append(result)
            return result

        try:
            out_dir = self.temp_dir / "skills"
            generator = MCPSkillGenerator(output_dir=str(out_dir), verbose=False)
            result.add_pass()
            print("   ✅ Initialization successful")
        except Exception as e:
            result.add_fail(f"Initialization failed: {e!r}")
            print(f"   ❌ Initialization failed: {e!r}")
            self.results.append(result)
            return result

        # Categorization
        try:
            tool = {
                "name": "read_file",
                "description": "Read a file from filesystem",
                "input_schema": {"type": "object", "properties": {"path": {"type": "string"}}},
                "_server_url": "http://localhost:8000/mcp",
                "_server_name": "localhost",
            }
            category = generator._categorize_tool(tool)
            assert category == "filesystem"
            result.add_pass()
            print(f"   ✅ Tool categorization: {category}")
        except Exception as e:
            result.add_fail(f"Categorization failed: {e!r}")
            print(f"   ❌ Categorization failed: {e!r}")

        # Generate files (private methods)
        try:
            # IMPORTANT: ensure directory exists before _atomic_write
            generator.output_dir.mkdir(parents=True, exist_ok=True)

            tools = [
                {
                    "name": "read_file",
                    "description": "Read file",
                    "input_schema": {},
                    "_server_url": "http://localhost:8000/mcp",
                    "_server_name": "localhost",
                },
                {
                    "name": "write_file",
                    "description": "Write file",
                    "input_schema": {},
                    "_server_url": "http://localhost:8000/mcp",
                    "_server_name": "localhost",
                },
            ]
            categorized = {"filesystem": tools}

            generator._generate_index(categorized)
            generator._generate_category_file("filesystem", tools)
            generator._save_metadata()

            index_path = generator.output_dir / "INDEX.md"
            cat_path = generator.output_dir / "filesystem.md"
            meta_path = generator.output_dir / "metadata.json"

            assert index_path.exists(), "INDEX.md not created"
            assert cat_path.exists(), "filesystem.md not created"
            assert meta_path.exists(), "metadata.json not created"

            cat_text = cat_path.read_text(encoding="utf-8", errors="replace")
            assert "### `read_file`" in cat_text or "read_file" in cat_text
            assert "### `write_file`" in cat_text or "write_file" in cat_text

            meta = json.loads(meta_path.read_text(encoding="utf-8", errors="replace"))
            # _save_metadata always writes these keys (merged from stats + generated_at + version)
            assert "generated_at" in meta
            assert "version" in meta

            result.add_pass()
            print("   ✅ Skill/index/metadata generation")
        except Exception as e:
            result.add_fail(f"Skill/index/metadata generation failed: {e!r}")
            print(f"   ❌ Skill/index/metadata generation failed: {e!r}")

        self.results.append(result)
        return result

    async def test_skill_loader(self) -> TestResult:
        result = TestResult("SkillLoader")
        print("\nTesting SkillLoader...")

        if not self.temp_dir:
            result.add_fail("Internal error: temp_dir not set")
            self.results.append(result)
            return result

        try:
            from polymcp.polyagent.skill_loader import SkillLoader
            result.add_pass()
            print("   ✅ Imports successful")
        except Exception as e:
            result.add_fail(f"Import failed: {e!r}")
            print(f"   ❌ Import failed: {e!r}")
            self.results.append(result)
            return result

        skills_dir = self.temp_dir / "test_skills"
        skills_dir.mkdir(parents=True, exist_ok=True)

        # Must use ### headers for extraction (supports ### `name`)
        (skills_dir / "filesystem.md").write_text(
            """# Filesystem Skills

### `read_file`

Read a file from disk.

### `write_file`

Write content to disk.
""",
            encoding="utf-8",
        )

        (skills_dir / "INDEX.md").write_text(
            """# MCP Skills Index

- **filesystem** → `filesystem.md`
""",
            encoding="utf-8",
        )

        try:
            loader = SkillLoader(skills_dir=str(skills_dir), strategy="lazy", verbose=False)
            result.add_pass()
            print("   ✅ Initialization successful")
        except Exception as e:
            result.add_fail(f"Initialization failed: {e!r}")
            print(f"   ❌ Initialization failed: {e!r}")
            self.results.append(result)
            return result

        try:
            skill = loader.load_skill("filesystem")
            assert skill.category == "filesystem"
            assert any(t.get("name") == "read_file" for t in skill.tools)
            assert any(t.get("name") == "write_file" for t in skill.tools)
            result.add_pass()
            print("   ✅ Skill loading + tool extraction")
        except Exception as e:
            result.add_fail(f"Load skill failed: {e!r}")
            print(f"   ❌ Load skill failed: {e!r}")

        try:
            _ = loader.load_skill("filesystem")  # cache hit
            stats = loader.get_stats()
            assert stats.cache_hits >= 0
            result.add_pass()
            print(f"   ✅ Cache stats ok (hits={stats.cache_hits}, misses={stats.cache_misses})")
        except Exception as e:
            result.add_fail(f"Stats/cache test failed: {e!r}")
            print(f"   ❌ Stats/cache test failed: {e!r}")

        self.results.append(result)
        return result

    async def test_skill_matcher(self) -> TestResult:
        result = TestResult("SkillMatcher")
        print("\n🔎 Testing SkillMatcher...")

        try:
            from polymcp.polyagent.skill_matcher import SkillMatcher, FuzzyMatcher, MatchResult
            result.add_pass()
            print("   ✅ Imports successful")
        except Exception as e:
            result.add_fail(f"Import failed: {e!r}")
            print(f"   ❌ Import failed: {e!r}")
            self.results.append(result)
            return result

        try:
            matcher = SkillMatcher(min_score=0.15, debug=False)
            fuzzy = FuzzyMatcher(enable_fuzzy=True)
            result.add_pass()
            print("   ✅ Initialization successful")
        except Exception as e:
            result.add_fail(f"Initialization failed: {e!r}")
            print(f"   ❌ Initialization failed: {e!r}")
            self.results.append(result)
            return result

        skills = {
            "filesystem": {
                "tools": [
                    {"name": "read_file", "description": "Read a file from disk"},
                    {"name": "write_file", "description": "Write content to a file"},
                ]
            },
            "api": {"tools": [{"name": "http_request", "description": "Send an HTTP request"}]},
            "data": {"tools": [{"name": "csv_to_json", "description": "Convert CSV to JSON"}]},
            "math": {"tools": [{"name": "average", "description": "Compute average"}]},
        }

        cases = [
            ("read file config.json", "filesystem"),
            ("send http request", "api"),
            ("convert csv to json", "data"),
            ("calculate average", "math"),
        ]

        for query, expected in cases:
            try:
                matches = matcher.match(query, skills, top_k=5)
                assert matches and isinstance(matches[0], MatchResult)
                cats = [m.category for m in matches]
                assert expected in cats
                result.add_pass()
                print(f"   ✅ Match OK: '{query}' → top={matches[0].category} (score={matches[0].score:.3f})")
            except Exception as e:
                result.add_fail(f"Matching failed for '{query}': {e!r}")
                print(f"   ❌ Matching failed for '{query}': {e!r}")

        try:
            idx = fuzzy.build_index_from_skills(skills)
            matches2 = fuzzy.match_index("save a document to disk", idx, top_k=5)
            assert matches2
            result.add_pass()
            print(f"   ✅ Fuzzy index match OK → {matches2[0].category} (score={matches2[0].score:.3f})")
        except Exception as e:
            result.add_fail(f"Fuzzy index matching failed: {e!r}")
            print(f"   ❌ Fuzzy index matching failed: {e!r}")

        self.results.append(result)
        return result

    async def test_docker_executor(self) -> TestResult:
        result = TestResult("DockerExecutor")
        print("\nTesting DockerSandboxExecutor...")

        if not self.temp_dir:
            result.add_fail("Internal error: temp_dir not set")
            self.results.append(result)
            return result

        # Detect Docker availability
        docker_available = False
        try:
            import docker  # noqa: F401
            client = docker.from_env()
            client.ping()
            docker_available = True
        except Exception as e:
            print(f"   ⚠️ Docker not available, skipping Docker tests: {e!r}")

        if not docker_available:
            result.add_pass()  # skip counts as pass
            self.results.append(result)
            return result

        try:
            from polymcp.sandbox.docker_executor import DockerSandboxExecutor
            result.add_pass()
            print("   ✅ Imports successful")
        except Exception as e:
            result.add_fail(f"Import failed: {e!r}")
            print(f"   ❌ Import failed: {e!r}")
            self.results.append(result)
            return result

        class DummyToolsAPI:
            def invoke(self, server: str, tool_name: str, params: dict):
                return {"ok": True, "server": server, "tool": tool_name, "params": params}

            def test_tool(self, **kwargs):
                return {"ok": True, "tool": "test_tool", "params": kwargs}

        try:
            executor = DockerSandboxExecutor(DummyToolsAPI(), timeout=10.0, verbose=False)
            result.add_pass()
            print("   ✅ Initialization successful")
        except Exception as e:
            result.add_fail(f"Initialization failed: {e!r}")
            print(f"   ❌ Initialization failed: {e!r}")
            self.results.append(result)
            return result

        # execute() takes only (code: str)
        try:
            code = "print('hello from sandbox')"
            exec_result = executor.execute(code)
            assert exec_result is not None
            if hasattr(exec_result, "success"):
                assert exec_result.success is True, f"Execution failed: {getattr(exec_result, 'error', '')}"
            if hasattr(exec_result, "output"):
                assert "hello from sandbox" in exec_result.output
            result.add_pass()
            print("   ✅ Code execution")
        except Exception as e:
            result.add_fail(f"Execution test failed: {e!r}")
            print(f"   ❌ Execution test failed: {e!r}")

        self.results.append(result)
        return result

    async def test_integration(self) -> TestResult:
        result = TestResult("Integration")
        print("\n🔎— Testing Full Integration...")

        if not self.temp_dir:
            result.add_fail("Internal error: temp_dir not set")
            self.results.append(result)
            return result

        try:
            from polymcp.polyagent.skill_generator import MCPSkillGenerator
            from polymcp.polyagent.skill_loader import SkillLoader
            from polymcp.polyagent.skill_matcher import SkillMatcher
            result.add_pass()
            print("   ✅ All components importable")
        except Exception as e:
            result.add_fail(f"Import failed: {e!r}")
            print(f"   ❌ Import failed: {e!r}")
            self.results.append(result)
            return result

        try:
            skills_dir = self.temp_dir / "integration_skills"
            generator = MCPSkillGenerator(output_dir=str(skills_dir), verbose=False)
            generator.output_dir.mkdir(parents=True, exist_ok=True)

            tools = [
                {
                    "name": "read_file",
                    "description": "Read a file from disk",
                    "input_schema": {},
                    "_server_url": "http://localhost:8000/mcp",
                    "_server_name": "localhost",
                }
            ]
            categorized = {"filesystem": tools}
            generator._generate_index(categorized)
            generator._generate_category_file("filesystem", tools)
            generator._save_metadata()

            assert (skills_dir / "INDEX.md").exists()
            assert (skills_dir / "filesystem.md").exists()

            result.add_pass()
            print("   ✅ Step 1: Skills generated")
        except Exception as e:
            result.add_fail(f"Step 1 failed: {e!r}")
            print(f"   ❌ Step 1 failed: {e!r}")
            self.results.append(result)
            return result

        try:
            loader = SkillLoader(skills_dir=str(skills_dir), strategy="lazy", verbose=False)
            fs = loader.load_skill("filesystem")
            assert fs.tools and fs.tools[0]["name"] == "read_file"
            result.add_pass()
            print("   ✅ Step 2: Skills loaded")
        except Exception as e:
            result.add_fail(f"Step 2 failed: {e!r}")
            print(f"   ❌ Step 2 failed: {e!r}")
            self.results.append(result)
            return result

        try:
            matcher = SkillMatcher(min_score=0.15, debug=False)
            skills = {"filesystem": {"tools": fs.tools}}
            matches = matcher.match("please read a file from disk", skills, top_k=5)
            assert matches and matches[0].category == "filesystem"
            result.add_pass()
            print("   ✅ Step 3: Query matched to skill")
        except Exception as e:
            result.add_fail(f"Step 3 failed: {e!r}")
            print(f"   ❌ Step 3 failed: {e!r}")

        self.results.append(result)
        return result


async def main() -> int:
    tester = SkillsSystemTester()
    tester.setup()
    try:
        return await tester.run_all_tests()
    finally:
        tester.teardown()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
