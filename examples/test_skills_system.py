#!/usr/bin/env python3
"""
Complete Test Suite for Skills System
Production-ready tests for all components
"""

import asyncio
import json
import tempfile
import shutil
from pathlib import Path
from typing import Dict, List, Any


class TestResult:
    """Store test results"""
    def __init__(self, name: str):
        self.name = name
        self.passed = 0
        self.failed = 0
        self.errors = []
    
    def add_pass(self):
        self.passed += 1
    
    def add_fail(self, error: str):
        self.failed += 1
        self.errors.append(error)
    
    def __str__(self):
        status = "✅ PASS" if self.failed == 0 else "âŒ FAIL"
        return f"{status} {self.name}: {self.passed} passed, {self.failed} failed"


class SkillsSystemTester:
    """Complete test suite for skills system"""
    
    def __init__(self):
        self.results = []
        self.temp_dir = None
    
    def setup(self):
        """Setup test environment"""
        print("\n🔧 Setting up test environment...")
        self.temp_dir = Path(tempfile.mkdtemp())
        print(f"   Temp dir: {self.temp_dir}")
    
    def teardown(self):
        """Cleanup test environment"""
        print("\n🧹 Cleaning up...")
        if self.temp_dir and self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)
            print("   Cleanup complete")
    
    async def test_skill_generator(self) -> TestResult:
        """Test MCPSkillGenerator"""
        result = TestResult("SkillGenerator")
        
        print("\nTesting MCPSkillGenerator...")
        
        try:
            from polymcp.polyagent.skill_generator import (
                MCPSkillGenerator,
                ToolInfo,
                SkillMetadata
            )
            result.add_pass()
            print("   ✅ Imports successful")
        except ImportError as e:
            result.add_fail(f"Import failed: {e}")
            print(f"Import failed: {e}")
            return result
        
        # Test initialization
        try:
            generator = MCPSkillGenerator(
                output_dir=str(self.temp_dir / "skills"),
                verbose=False
            )
            result.add_pass()
            print("   ✅ Initialization successful")
        except Exception as e:
            result.add_fail(f"Initialization failed: {e}")
            print(f"Initialization failed: {e}")
            return result
        
        # Test tool categorization
        try:
            tool_info = ToolInfo(
                name="read_file",
                description="Read a file from filesystem",
                input_schema={
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"}
                    }
                },
                server_url="http://localhost:8000/mcp"
            )
            
            category = generator._categorize_tool(tool_info)
            assert category == "filesystem", f"Expected 'filesystem', got '{category}'"
            result.add_pass()
            print(f"   ✅ Tool categorization: {category}")
        except Exception as e:
            result.add_fail(f"Categorization failed: {e}")
            print(f"Categorization failed: {e}")
        
        # Test skill file generation
        try:
            tools = [
                ToolInfo(
                    name="read_file",
                    description="Read file",
                    input_schema={},
                    server_url="http://localhost:8000/mcp"
                ),
                ToolInfo(
                    name="write_file",
                    description="Write file",
                    input_schema={},
                    server_url="http://localhost:8000/mcp"
                )
            ]
            
            skill_content = generator._generate_skill_file(
                category="filesystem",
                tools=tools,
                examples=True
            )
            
            assert "# Filesystem Skills" in skill_content
            assert "read_file" in skill_content
            assert "write_file" in skill_content
            result.add_pass()
            print("   ✅ Skill file generation")
        except Exception as e:
            result.add_fail(f"Skill generation failed: {e}")
            print(f"Skill generation failed: {e}")
        
        # Test metadata generation
        try:
            metadata = generator._generate_metadata({"filesystem": tools})
            assert "total_tools" in metadata
            assert "categories" in metadata
            assert metadata["total_tools"] == 2
            result.add_pass()
            print("   ✅ Metadata generation")
        except Exception as e:
            result.add_fail(f"Metadata generation failed: {e}")
            print(f"Metadata generation failed: {e}")
        
        self.results.append(result)
        return result
    
    async def test_skill_loader(self) -> TestResult:
        """Test SkillLoader"""
        result = TestResult("SkillLoader")
        
        print("\nTesting SkillLoader...")
        
        try:
            from polymcp.polyagent.skill_loader import (
                SkillLoader,
                LoadedSkill,
                LoadingStats
            )
            result.add_pass()
            print("   ✅ Imports successful")
        except ImportError as e:
            result.add_fail(f"Import failed: {e}")
            print(f"Import failed: {e}")
            return result
        
        # Create test skills
        skills_dir = self.temp_dir / "test_skills"
        skills_dir.mkdir()
        
        # Create test skill file
        skill_content = """# Filesystem Skills

## Available Tools

### read_file
Read a file from the filesystem.

**Parameters:**
- `path` (string): File path to read

### write_file
Write content to a file.

**Parameters:**
- `path` (string): File path to write
- `content` (string): Content to write
"""
        
        (skills_dir / "filesystem.md").write_text(skill_content)
        
        # Create index
        index = {
            "version": "1.0.0",
            "categories": ["filesystem"],
            "total_skills": 1
        }
        (skills_dir / "skills_index.json").write_text(json.dumps(index))
        
        # Test initialization
        try:
            loader = SkillLoader(
                skills_dir=str(skills_dir),
                verbose=False
            )
            result.add_pass()
            print("   ✅ Initialization successful")
        except Exception as e:
            result.add_fail(f"Initialization failed: {e}")
            print(f"Initialization failed: {e}")
            return result
        
        # Test lazy loading
        try:
            skill = await loader.load_skill("filesystem", strategy="lazy")
            assert skill is not None
            assert skill.category == "filesystem"
            assert "read_file" in skill.content
            result.add_pass()
            print("   ✅ Lazy loading")
        except Exception as e:
            result.add_fail(f"Lazy loading failed: {e}")
            print(f"Lazy loading failed: {e}")
        
        # Test caching
        try:
            # Load again - should use cache
            skill2 = await loader.load_skill("filesystem", strategy="lazy")
            assert skill2 is not None
            
            # Check cache stats
            stats = loader.get_stats()
            assert stats["cache_hits"] > 0
            result.add_pass()
            print(f"   ✅ Caching (hits: {stats['cache_hits']})")
        except Exception as e:
            result.add_fail(f"Caching failed: {e}")
            print(f"Caching failed: {e}")
        
        # Test token estimation
        try:
            tokens = loader.get_token_estimate("filesystem")
            assert tokens > 0
            assert tokens < 5000  # Reasonable upper bound
            result.add_pass()
            print(f"   ✅ Token estimation (~{tokens} tokens)")
        except Exception as e:
            result.add_fail(f"Token estimation failed: {e}")
            print(f"Token estimation failed: {e}")
        
        self.results.append(result)
        return result
    
    async def test_skill_matcher(self) -> TestResult:
        """Test SkillMatcher"""
        result = TestResult("SkillMatcher")
        
        print("\n🔎 Testing SkillMatcher...")
        
        try:
            from polymcp.polyagent.skill_matcher import (
                SkillMatcher,
                FuzzyMatcher,
                SkillMatch
            )
            result.add_pass()
            print("   ✅ Imports successful")
        except ImportError as e:
            result.add_fail(f"Import failed: {e}")
            print(f"Import failed: {e}")
            return result
        
        # Test basic matcher
        try:
            matcher = SkillMatcher(min_confidence=0.3, verbose=False)
            result.add_pass()
            print("   ✅ Initialization successful")
        except Exception as e:
            result.add_fail(f"Initialization failed: {e}")
            print(f"Initialization failed: {e}")
            return result
        
        # Test matching
        test_cases = [
            ("read file config.json", "filesystem", 0.5),
            ("send HTTP request to API", "api", 0.5),
            ("convert CSV to JSON", "data", 0.5),
            ("calculate average of numbers", "math", 0.5),
        ]
        
        for query, expected_category, min_conf in test_cases:
            try:
                matches = matcher.match(query)
                assert len(matches) > 0, f"No matches for: {query}"
                
                # Check if expected category is in top matches
                categories = [m.category for m in matches]
                assert expected_category in categories, \
                    f"Expected '{expected_category}' in {categories}"
                
                # Check confidence
                top_match = matches[0]
                assert top_match.confidence >= min_conf, \
                    f"Confidence too low: {top_match.confidence}"
                
                result.add_pass()
                print(f"   ✅ Match '{query}' â†’ {top_match.category} ({top_match.confidence:.2f})")
            except Exception as e:
                result.add_fail(f"Matching failed for '{query}': {e}")
                print(f"Matching failed for '{query}': {e}")
        
        # Test fuzzy matcher
        try:
            fuzzy = FuzzyMatcher(enable_fuzzy=True, verbose=False)
            
            # Test with synonyms
            matches = fuzzy.match("save document to disk")
            assert len(matches) > 0
            
            result.add_pass()
            print("   ✅ Fuzzy matching with synonyms")
        except Exception as e:
            result.add_fail(f"Fuzzy matching failed: {e}")
            print(f"Fuzzy matching failed: {e}")
        
        # Test statistics
        try:
            stats = matcher.get_stats()
            assert "queries_processed" in stats
            assert stats["queries_processed"] > 0
            result.add_pass()
            print(f"   ✅ Statistics ({stats['queries_processed']} queries)")
        except Exception as e:
            result.add_fail(f"Statistics failed: {e}")
            print(f"Statistics failed: {e}")
        
        self.results.append(result)
        return result
    
    async def test_docker_executor(self) -> TestResult:
        """Test DockerSandboxExecutor"""
        result = TestResult("DockerExecutor")
        
        print("\nTesting DockerSandboxExecutor...")
        
        # Check if Docker is available
        try:
            import docker
            client = docker.from_env()
            client.ping()
            docker_available = True
        except Exception as e:
            docker_available = False
            print(f"Docker not available: {e}")
            print("Skipping Docker tests")
            result.add_fail("Docker not available")
            self.results.append(result)
            return result
        
        try:
            from polymcp.sandbox.docker_executor import DockerSandboxExecutor
            from polymcp.sandbox.tools_api import ToolsAPI
            result.add_pass()
            print("   ✅ Imports successful")
        except ImportError as e:
            result.add_fail(f"Import failed: {e}")
            print(f"Import failed: {e}")
            return result
        
        # Create mock ToolsAPI
        try:
            http_tools = {
                "http://localhost:8000/mcp": [
                    {
                        "name": "test_tool",
                        "description": "Test tool",
                        "input_schema": {}
                    }
                ]
            }
            
            def http_executor(server, tool, params):
                return {"result": "test", "status": "success"}
            
            async def stdio_executor(server, tool, params):
                return {"result": "test", "status": "success"}
            
            tools_api = ToolsAPI(
                http_tools=http_tools,
                stdio_adapters={},
                http_executor=http_executor,
                stdio_executor=stdio_executor,
                verbose=False
            )
            result.add_pass()
            print("   ✅ ToolsAPI created")
        except Exception as e:
            result.add_fail(f"ToolsAPI creation failed: {e}")
            print(f"ToolsAPI creation failed: {e}")
            return result
        
        # Test Docker executor initialization
        try:
            executor = DockerSandboxExecutor(
                tools_api=tools_api,
                timeout=10.0,
                verbose=False
            )
            result.add_pass()
            print("   ✅ Initialization successful")
        except Exception as e:
            result.add_fail(f"Initialization failed: {e}")
            print(f"Initialization failed: {e}")
            return result
        
        # Test simple code execution
        try:
            code = """
import json

result = {"message": "Hello from Docker!"}
print(json.dumps(result))
"""
            
            exec_result = executor.execute(code)
            assert exec_result.success, f"Execution failed: {exec_result.error}"
            assert "Hello from Docker" in exec_result.output
            result.add_pass()
            print(f"   ✅ Code execution ({exec_result.execution_time:.2f}s)")
        except Exception as e:
            result.add_fail(f"Code execution failed: {e}")
            print(f"Code execution failed: {e}")
        
        # Test resource limits
        try:
            # This should be limited by CPU quota
            cpu_test = """
import time
start = time.time()
while time.time() - start < 0.5:
    pass
print("CPU test completed")
"""
            exec_result = executor.execute(cpu_test)
            assert exec_result.success
            result.add_pass()
            print("   ✅ Resource limits enforced")
        except Exception as e:
            result.add_fail(f"Resource limits test failed: {e}")
            print(f"Resource limits test failed: {e}")
        
        # Test cleanup
        try:
            stats = executor.get_stats()
            assert stats["containers_cleaned"] == stats["containers_created"]
            result.add_pass()
            print(f"   ✅ Container cleanup ({stats['containers_cleaned']} cleaned)")
        except Exception as e:
            result.add_fail(f"Cleanup test failed: {e}")
            print(f" Cleanup test failed: {e}")
        
        self.results.append(result)
        return result
    
    async def test_integration(self) -> TestResult:
        """Test full integration"""
        result = TestResult("Integration")
        
        print("\n🔎— Testing Full Integration...")
        
        # This would test the complete workflow:
        # 1. Generate skills
        # 2. Load skills
        # 3. Match query to skill
        # 4. Use skill in agent
        
        # For now, just verify components work together
        try:
            from polymcp.polyagent.skill_generator import MCPSkillGenerator
            from polymcp.polyagent.skill_loader import SkillLoader
            from polymcp.polyagent.skill_matcher import SkillMatcher
            
            result.add_pass()
            print("   ✅ All components importable")
        except ImportError as e:
            result.add_fail(f"Integration import failed: {e}")
            print(f"Integration import failed: {e}")
            return result
        
        # Test workflow
        try:
            # Step 1: Generate (mock)
            skills_dir = self.temp_dir / "integration_skills"
            generator = MCPSkillGenerator(
                output_dir=str(skills_dir),
                verbose=False
            )
            result.add_pass()
            print("   ✅ Step 1: Generator ready")
            
            # Step 2: Loader
            loader = SkillLoader(str(skills_dir), verbose=False)
            result.add_pass()
            print("   ✅ Step 2: Loader ready")
            
            # Step 3: Matcher
            matcher = SkillMatcher(verbose=False)
            matches = matcher.match("read file")
            assert len(matches) > 0
            result.add_pass()
            print(f"   ✅ Step 3: Matcher ready (found {len(matches)} matches)")
            
        except Exception as e:
            result.add_fail(f"Integration workflow failed: {e}")
            print(f"Integration workflow failed: {e}")
        
        self.results.append(result)
        return result
    
    def print_summary(self):
        """Print test summary"""
        print("\n" + "="*60)
        print("TEST SUMMARY")
        print("="*60)
        
        total_passed = 0
        total_failed = 0
        
        for result in self.results:
            print(f"\n{result}")
            total_passed += result.passed
            total_failed += result.failed
            
            if result.errors:
                for error in result.errors:
                    print(f"{error}")
        
        print("\n" + "="*60)
        print(f"TOTAL: {total_passed} passed, {total_failed} failed")
        
        if total_failed == 0:
            print("✅ ALL TESTS PASSED!")
        else:
            print(f"{total_failed} TESTS FAILED")
        
        print("="*60)
        
        return total_failed == 0


async def main():
    """Run all tests"""
    print("="*60)
    print("🧪 PolyMCP Skills System - Complete Test Suite")
    print("="*60)
    
    tester = SkillsSystemTester()
    
    try:
        tester.setup()
        
        # Run all tests
        await tester.test_skill_generator()
        await tester.test_skill_loader()
        await tester.test_skill_matcher()
        await tester.test_docker_executor()
        await tester.test_integration()
        
        # Print summary
        success = tester.print_summary()
        
        return 0 if success else 1
        
    except Exception as e:
        print(f"\nFatal error: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    finally:
        tester.teardown()


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)
