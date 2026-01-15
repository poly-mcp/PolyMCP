#!/usr/bin/env python3
"""
Multi-Server MCP Setup with Docker Sandbox - Detailed Version
Production example with detailed Docker logging and monitoring.
"""

import os
import sys
import time
import json
import tempfile
import shutil
import subprocess
import multiprocessing
from pathlib import Path
from typing import Dict, Any, Optional, List
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

from polymcp.polyagent import PolyAgent, OllamaProvider, OpenAIProvider
from polymcp.polymcp_toolkit import expose_tools
from polymcp.sandbox import DockerExecutionResult


# =============================================================================
# DOCKER SANDBOX EXECUTOR - DETAILED VERSION
# =============================================================================

class DockerSandboxExecutor:
    """Docker sandbox with detailed logging and monitoring."""
    
    DEFAULT_IMAGE = "python:3.11-slim"
    
    DEFAULT_LIMITS = {
        "cpu_quota": 50000,      # 50% of one CPU
        "mem_limit": "256m",      # 256MB RAM
        "memswap_limit": "256m",  # No swap
        "pids_limit": 50,         # Max 50 processes
    }
    
    def __init__(
        self, 
        timeout: float = 30.0, 
        docker_image: str = DEFAULT_IMAGE,
        verbose: bool = True
    ):
        self.timeout = timeout
        self.docker_image = docker_image
        self.verbose = verbose
        self.docker_available = False
        self.docker_client = None
        self.docker_info = {}
        
        # Detailed stats
        self.stats = {
            "executions": 0,
            "docker_executions": 0,
            "fallback_executions": 0,
            "successes": 0,
            "failures": 0,
            "total_time": 0.0,
            "total_cpu_time": 0.0,
            "total_memory_mb": 0.0,
            "containers_created": 0,
            "containers_cleaned": 0,
            "execution_history": [],
        }
        
        self._init_docker()
    
    def _log(self, message: str, level: str = "INFO"):
        """Print detailed log message."""
        if self.verbose:
            timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
            prefix = {
                "INFO": "[INFO]",
                "DOCKER": "[DOCKER]",
                "CONTAINER": "[CONTAINER]",
                "SECURITY": "[SECURITY]",
                "RESOURCE": "[RESOURCE]",
                "ERROR": "[ERROR]",
                "SUCCESS": "[SUCCESS]",
                "FALLBACK": "[FALLBACK]",
                "STATS": "[STATS]",
            }.get(level, "[INFO]")
            
            color = {
                "DOCKER": "\033[36m",      # Cyan
                "CONTAINER": "\033[34m",   # Blue
                "SECURITY": "\033[33m",    # Yellow
                "SUCCESS": "\033[32m",     # Green
                "ERROR": "\033[31m",       # Red
                "RESOURCE": "\033[35m",    # Magenta
            }.get(level, "")
            
            reset = "\033[0m" if color else ""
            print(f"  {color}{timestamp} {prefix} {message}{reset}")
    
    def _init_docker(self):
        """Initialize Docker with detailed information."""
        try:
            import docker
            self._log("Initializing Docker client...", "DOCKER")
            
            self.docker_client = docker.from_env()
            
            # Test connection
            self._log("Testing Docker connection...", "DOCKER")
            self.docker_client.ping()
            
            # Get Docker info
            info = self.docker_client.info()
            self.docker_info = {
                "server_version": info.get("ServerVersion", "Unknown"),
                "os": info.get("OperatingSystem", "Unknown"),
                "kernel": info.get("KernelVersion", "Unknown"),
                "containers": info.get("Containers", 0),
                "images": info.get("Images", 0),
                "cpu_count": info.get("NCPU", 0),
                "memory_gb": round(info.get("MemTotal", 0) / (1024**3), 2),
                "driver": info.get("Driver", "Unknown"),
            }
            
            self._log(f"Docker version: {self.docker_info['server_version']}", "DOCKER")
            self._log(f"Host OS: {self.docker_info['os']}", "DOCKER")
            self._log(f"Resources: {self.docker_info['cpu_count']} CPUs, {self.docker_info['memory_gb']} GB RAM", "DOCKER")
            
            # Check/pull image
            self._log(f"Checking image: {self.docker_image}", "DOCKER")
            try:
                image = self.docker_client.images.get(self.docker_image)
                size_mb = round(image.attrs['Size'] / (1024**2), 2)
                self._log(f"Image ready: {self.docker_image} ({size_mb} MB)", "DOCKER")
            except docker.errors.ImageNotFound:
                self._log(f"Pulling image: {self.docker_image}...", "DOCKER")
                image = self.docker_client.images.pull(self.docker_image)
                size_mb = round(image.attrs['Size'] / (1024**2), 2)
                self._log(f"Image pulled: {size_mb} MB", "DOCKER")
            
            self.docker_available = True
            self._log("Docker is fully operational", "SUCCESS")
            
            # Show security configuration
            self._log("Security configuration:", "SECURITY")
            self._log("  - Network: DISABLED", "SECURITY")
            self._log("  - Filesystem: READ-ONLY", "SECURITY")
            self._log("  - User: nobody (non-root)", "SECURITY")
            self._log("  - Capabilities: ALL DROPPED", "SECURITY")
            self._log("  - Memory limit: 256 MB", "SECURITY")
            self._log("  - CPU limit: 50% of 1 core", "SECURITY")
            
        except ImportError:
            self._log("Docker SDK not installed (pip install docker)", "ERROR")
            self._log("Falling back to restricted subprocess mode", "FALLBACK")
        except Exception as e:
            self._log(f"Docker initialization failed: {e}", "ERROR")
            self._log("Using FALLBACK mode with restrictions", "FALLBACK")
    
    def execute(self, code: str) -> DockerExecutionResult:
        """Execute code with detailed monitoring."""
        self.stats["executions"] += 1
        
        self._log(f"{'='*60}", "INFO")
        self._log(f"Execution #{self.stats['executions']}", "INFO")
        self._log(f"Code length: {len(code)} chars, {len(code.splitlines())} lines", "INFO")
        self._log(f"First line: {code.split(chr(10))[0][:50]}...", "INFO")
        
        if self.docker_available:
            self._log("Mode: DOCKER (full isolation)", "DOCKER")
            return self._docker_execute(code)
        else:
            self._log("Mode: FALLBACK (restricted subprocess)", "FALLBACK")
            return self._fallback_execute(code)
    
    def _docker_execute(self, code: str) -> DockerExecutionResult:
        """Execute in Docker with detailed monitoring."""
        start_time = time.time()
        self.stats["docker_executions"] += 1
        container = None
        temp_dir = None
        
        execution_record = {
            "execution_id": self.stats["executions"],
            "timestamp": datetime.now().isoformat(),
            "code_preview": code[:100],
        }
        
        try:
            # Create temp directory
            temp_dir = Path(tempfile.mkdtemp())
            code_file = temp_dir / "code.py"
            code_file.write_text(code)
            self._log(f"Code written to: {code_file}", "DOCKER")
            
            # Container configuration
            self._log("Container configuration:", "CONTAINER")
            self._log(f"  Image: {self.docker_image}", "CONTAINER")
            self._log(f"  CPU limit: {self.DEFAULT_LIMITS['cpu_quota']/100000:.1f} cores", "CONTAINER")
            self._log(f"  Memory limit: {self.DEFAULT_LIMITS['mem_limit']}", "CONTAINER")
            self._log(f"  Process limit: {self.DEFAULT_LIMITS['pids_limit']}", "CONTAINER")
            self._log(f"  Timeout: {self.timeout}s", "CONTAINER")
            
            # Create container
            self._log("Creating container...", "CONTAINER")
            container = self.docker_client.containers.create(
                image=self.docker_image,
                command=["python", "/workspace/code.py"],
                detach=True,
                name=f"sandbox-{self.stats['executions']}-{int(time.time())}",
                volumes={
                    str(temp_dir.absolute()): {
                        "bind": "/workspace",
                        "mode": "ro"  # Read-only mount
                    }
                },
                working_dir="/workspace",
                
                # Resource limits
                cpu_quota=self.DEFAULT_LIMITS["cpu_quota"],
                cpu_period=100000,  # Default period
                mem_limit=self.DEFAULT_LIMITS["mem_limit"],
                memswap_limit=self.DEFAULT_LIMITS["memswap_limit"],
                pids_limit=self.DEFAULT_LIMITS["pids_limit"],
                
                # Security settings
                network_disabled=True,
                read_only=True,
                tmpfs={"/tmp": "size=10m,mode=1777"},
                user="nobody",
                privileged=False,
                cap_drop=["ALL"],
                security_opt=["no-new-privileges"],
                
                # Labels for tracking
                labels={
                    "created_by": "docker-sandbox",
                    "execution_id": str(self.stats["executions"]),
                    "timestamp": str(int(time.time())),
                }
            )
            
            self.stats["containers_created"] += 1
            container_id = container.short_id
            execution_record["container_id"] = container_id
            
            self._log(f"Container created: {container_id}", "CONTAINER")
            self._log(f"Container name: {container.name}", "CONTAINER")
            
            # Start container
            self._log("Starting container...", "CONTAINER")
            container.start()
            
            # Monitor execution
            self._log(f"Executing (timeout: {self.timeout}s)...", "CONTAINER")
            
            # Wait with timeout
            try:
                result = container.wait(timeout=self.timeout)
                exit_code = result['StatusCode']
            except Exception:
                self._log("Timeout reached, killing container", "ERROR")
                container.kill()
                raise TimeoutError(f"Execution exceeded {self.timeout}s")
            
            # Get logs
            logs = container.logs(stdout=True, stderr=True).decode('utf-8')
            
            # Get resource stats
            try:
                stats = container.stats(stream=False)
                cpu_stats = self._extract_cpu_stats(stats)
                mem_stats = self._extract_memory_stats(stats)
                
                self._log(f"CPU used: {cpu_stats['cpu_percent']:.2f}%", "RESOURCE")
                self._log(f"Memory used: {mem_stats['memory_mb']:.2f} MB ({mem_stats['memory_percent']:.1f}%)", "RESOURCE")
                
                self.stats["total_cpu_time"] += cpu_stats.get("cpu_total_usage", 0)
                self.stats["total_memory_mb"] += mem_stats.get("memory_mb", 0)
                
                execution_record["resource_usage"] = {
                    "cpu_percent": cpu_stats['cpu_percent'],
                    "memory_mb": mem_stats['memory_mb'],
                }
            except Exception as e:
                self._log(f"Could not get resource stats: {e}", "ERROR")
                execution_record["resource_usage"] = None
            
            # Calculate execution time
            execution_time = time.time() - start_time
            self.stats["total_time"] += execution_time
            
            # Determine success
            success = (exit_code == 0)
            if success:
                self.stats["successes"] += 1
                self._log(f"Exit code: {exit_code}", "SUCCESS")
                self._log(f"Execution time: {execution_time:.3f}s", "SUCCESS")
                
                # Show output preview
                output_preview = logs.strip()[:200]
                if len(logs.strip()) > 200:
                    output_preview += "..."
                self._log(f"Output: {output_preview}", "SUCCESS")
            else:
                self.stats["failures"] += 1
                self._log(f"Exit code: {exit_code}", "ERROR")
                self._log(f"Error: {logs.strip()[:200]}", "ERROR")
            
            execution_record.update({
                "success": success,
                "execution_time": round(execution_time, 3),
                "exit_code": exit_code,
            })
            self.stats["execution_history"].append(execution_record)
            
            # Keep only last 10 executions in history
            if len(self.stats["execution_history"]) > 10:
                self.stats["execution_history"].pop(0)
            
            return DockerExecutionResult(
                success=success,
                output=logs if success else "",
                error=logs if not success else None,
                execution_time=round(execution_time, 3),
                exit_code=exit_code,
                container_id=container_id,
                resource_usage={
                    "cpu_percent": cpu_stats.get('cpu_percent', 0),
                    "memory_mb": mem_stats.get('memory_mb', 0),
                } if 'cpu_stats' in locals() else None
            )
        
        except TimeoutError as e:
            self.stats["failures"] += 1
            execution_record["success"] = False
            execution_record["error"] = "timeout"
            self.stats["execution_history"].append(execution_record)
            
            self._log(str(e), "ERROR")
            return DockerExecutionResult(
                success=False,
                output="",
                error=str(e),
                execution_time=self.timeout,
                exit_code=124,
                container_id=container.short_id if container else None
            )
        
        except Exception as e:
            self.stats["failures"] += 1
            execution_record["success"] = False
            execution_record["error"] = str(e)
            self.stats["execution_history"].append(execution_record)
            
            self._log(f"Docker execution failed: {e}", "ERROR")
            return DockerExecutionResult(
                success=False,
                output="",
                error=str(e),
                execution_time=time.time() - start_time,
                exit_code=1
            )
        
        finally:
            # Cleanup
            if container:
                try:
                    container.remove(force=True)
                    self.stats["containers_cleaned"] += 1
                    self._log(f"Container {container.short_id} removed", "CONTAINER")
                except Exception as e:
                    self._log(f"Container cleanup failed: {e}", "ERROR")
            
            if temp_dir and temp_dir.exists():
                shutil.rmtree(temp_dir, ignore_errors=True)
                self._log("Temp files cleaned", "INFO")
            
            # Show stats summary
            success_rate = (self.stats["successes"] / self.stats["executions"] * 100) if self.stats["executions"] > 0 else 0
            self._log(f"Stats: {self.stats['executions']} total, {success_rate:.1f}% success rate", "STATS")
    
    def _fallback_execute(self, code: str) -> DockerExecutionResult:
        """Fallback execution with restrictions."""
        start_time = time.time()
        self.stats["fallback_executions"] += 1
        
        # Security checks for fallback
        dangerous_patterns = [
            ('import os', 'OS access'),
            ('import subprocess', 'Process execution'),
            ('import sys', 'System access'),
            ('__import__', 'Dynamic import'),
            ('eval(', 'Dynamic evaluation'),
            ('exec(', 'Dynamic execution'),
            ('open(', 'File access'),
            ('input(', 'User input'),
        ]
        
        for pattern, description in dangerous_patterns:
            if pattern in code:
                self.stats["failures"] += 1
                self._log(f"BLOCKED: {description} ('{pattern}')", "FALLBACK")
                self._log("Install Docker for unrestricted execution", "FALLBACK")
                
                return DockerExecutionResult(
                    success=False,
                    output="",
                    error=f"Security: {description} not allowed in fallback mode",
                    execution_time=0.0,
                    exit_code=1,
                    container_id="fallback"
                )
        
        self._log("Security check passed", "FALLBACK")
        self._log("Executing with subprocess (5s timeout)...", "FALLBACK")
        
        try:
            result = subprocess.run(
                [sys.executable, "-c", code],
                capture_output=True,
                text=True,
                timeout=5,
                cwd=tempfile.gettempdir()
            )
            
            execution_time = time.time() - start_time
            success = result.returncode == 0
            
            if success:
                self.stats["successes"] += 1
                self._log(f"Exit code: {result.returncode}", "SUCCESS")
                self._log(f"Output: {result.stdout.strip()[:100]}", "SUCCESS")
            else:
                self.stats["failures"] += 1
                self._log(f"Exit code: {result.returncode}", "ERROR")
                self._log(f"Error: {result.stderr.strip()[:100]}", "ERROR")
            
            return DockerExecutionResult(
                success=success,
                output=result.stdout if success else "",
                error=result.stderr if not success else None,
                execution_time=round(execution_time, 3),
                exit_code=result.returncode,
                container_id="fallback"
            )
        
        except subprocess.TimeoutExpired:
            self.stats["failures"] += 1
            self._log("Timeout in fallback mode", "ERROR")
            return DockerExecutionResult(
                success=False,
                output="",
                error="Timeout (5s limit in fallback)",
                execution_time=5.0,
                exit_code=124,
                container_id="fallback"
            )
        
        except Exception as e:
            self.stats["failures"] += 1
            self._log(f"Fallback execution failed: {e}", "ERROR")
            return DockerExecutionResult(
                success=False,
                output="",
                error=str(e),
                execution_time=time.time() - start_time,
                exit_code=1,
                container_id="fallback"
            )
    
    def _extract_cpu_stats(self, stats: Dict) -> Dict:
        """Extract CPU usage statistics."""
        try:
            cpu_stats = stats.get("cpu_stats", {})
            precpu_stats = stats.get("precpu_stats", {})
            
            # Calculate CPU usage percentage
            cpu_delta = cpu_stats.get("cpu_usage", {}).get("total_usage", 0) - \
                        precpu_stats.get("cpu_usage", {}).get("total_usage", 0)
            system_delta = cpu_stats.get("system_cpu_usage", 0) - \
                           precpu_stats.get("system_cpu_usage", 0)
            
            cpu_percent = 0.0
            if system_delta > 0 and cpu_delta > 0:
                cpu_percent = (cpu_delta / system_delta) * cpu_stats.get("online_cpus", 1) * 100.0
            
            return {
                "cpu_percent": cpu_percent,
                "cpu_total_usage": cpu_stats.get("cpu_usage", {}).get("total_usage", 0) / 1e9,  # Convert to seconds
            }
        except Exception:
            return {"cpu_percent": 0.0, "cpu_total_usage": 0.0}
    
    def _extract_memory_stats(self, stats: Dict) -> Dict:
        """Extract memory usage statistics."""
        try:
            mem_stats = stats.get("memory_stats", {})
            
            mem_usage = mem_stats.get("usage", 0)
            mem_limit = mem_stats.get("limit", 1)
            mem_percent = (mem_usage / mem_limit) * 100.0 if mem_limit > 0 else 0.0
            
            return {
                "memory_bytes": mem_usage,
                "memory_mb": mem_usage / (1024**2),
                "memory_percent": mem_percent,
                "memory_limit_mb": mem_limit / (1024**2),
            }
        except Exception:
            return {"memory_bytes": 0, "memory_mb": 0.0, "memory_percent": 0.0}
    
    def get_detailed_stats(self) -> Dict:
        """Get detailed execution statistics."""
        success_rate = (self.stats["successes"] / self.stats["executions"] * 100) \
                       if self.stats["executions"] > 0 else 0.0
        
        avg_time = self.stats["total_time"] / self.stats["executions"] \
                   if self.stats["executions"] > 0 else 0.0
        
        avg_cpu = self.stats["total_cpu_time"] / self.stats["docker_executions"] \
                  if self.stats["docker_executions"] > 0 else 0.0
        
        avg_memory = self.stats["total_memory_mb"] / self.stats["docker_executions"] \
                     if self.stats["docker_executions"] > 0 else 0.0
        
        return {
            "docker_info": self.docker_info,
            "execution_stats": {
                "total_executions": self.stats["executions"],
                "docker_executions": self.stats["docker_executions"],
                "fallback_executions": self.stats["fallback_executions"],
                "successes": self.stats["successes"],
                "failures": self.stats["failures"],
                "success_rate": round(success_rate, 2),
                "containers_created": self.stats["containers_created"],
                "containers_cleaned": self.stats["containers_cleaned"],
            },
            "performance_stats": {
                "total_time_seconds": round(self.stats["total_time"], 2),
                "average_time_seconds": round(avg_time, 3),
                "average_cpu_seconds": round(avg_cpu, 3),
                "average_memory_mb": round(avg_memory, 2),
            },
            "recent_executions": self.stats["execution_history"][-5:],
        }
    
    def get_status(self) -> Dict:
        """Get current executor status."""
        return {
            "mode": "docker" if self.docker_available else "fallback",
            "docker_available": self.docker_available,
            "docker_version": self.docker_info.get("server_version", "N/A"),
            "docker_os": self.docker_info.get("os", "N/A"),
            "image": self.docker_image if self.docker_available else None,
            "resource_limits": self.DEFAULT_LIMITS if self.docker_available else None,
            "security_features": {
                "network_isolation": True,
                "filesystem_readonly": True,
                "non_root_user": True,
                "capabilities_dropped": True,
                "resource_limits": True,
            } if self.docker_available else {
                "restricted_imports": True,
                "timeout_limit": "5 seconds",
            },
        }


# Global executor instance
_executor: Optional[DockerSandboxExecutor] = None

def get_executor() -> DockerSandboxExecutor:
    global _executor
    if _executor is None:
        _executor = DockerSandboxExecutor(timeout=30.0, verbose=True)
    return _executor


# =============================================================================
# TEXT ANALYSIS TOOLS
# =============================================================================

def summarize(text: str, max_sentences: int = 3) -> str:
    """Summarize text by extracting key sentences."""
    import re
    if not text:
        return "No text provided"
    sentences = re.split(r'[.!?]+', text)
    sentences = [s.strip() for s in sentences if s.strip()]
    if len(sentences) <= max_sentences:
        return text.strip()
    return '. '.join(sentences[:max_sentences]) + '.'


def word_count(text: str) -> Dict[str, int]:
    """Count words and characters in text."""
    if not text:
        return {"error": "No text provided"}
    words = text.split()
    return {
        "characters": len(text),
        "words": len(words),
        "lines": len(text.splitlines()),
        "average_word_length": round(sum(len(w) for w in words) / len(words), 2) if words else 0
    }


# =============================================================================
# UTILITY TOOLS
# =============================================================================

def generate_password(length: int = 16) -> str:
    """Generate a secure random password."""
    import random
    import string
    if length < 4:
        return "Error: Length must be at least 4"
    chars = string.ascii_letters + string.digits + "!@#$%^&*"
    return ''.join(random.choice(chars) for _ in range(length))


def calculate_statistics(numbers: list) -> Dict[str, float]:
    """Calculate statistical measures for numbers."""
    if not numbers:
        return {"error": "Empty list"}
    
    n = len(numbers)
    mean = sum(numbers) / n
    sorted_nums = sorted(numbers)
    median = sorted_nums[n//2] if n % 2 else (sorted_nums[n//2-1] + sorted_nums[n//2]) / 2
    
    return {
        "count": n,
        "mean": round(mean, 2),
        "median": round(median, 2),
        "min": min(numbers),
        "max": max(numbers),
        "sum": sum(numbers),
        "range": max(numbers) - min(numbers)
    }


# =============================================================================
# CODE EXECUTION TOOLS
# =============================================================================

def execute_python(code: str) -> Dict[str, Any]:
    """
    Execute Python code in Docker sandbox.
    
    Args:
        code: Python code to execute
        
    Returns:
        Detailed execution result
    """
    if not code:
        return {"error": "No code provided"}
    
    executor = get_executor()
    result = executor.execute(code)
    
    response = {
        "success": result.success,
        "output": result.output.strip() if result.output else "",
        "error": result.error,
        "execution_time": result.execution_time,
        "exit_code": result.exit_code,
        "container_id": result.container_id,
        "mode": "docker" if executor.docker_available else "fallback",
    }
    
    # Add resource usage if available
    if result.resource_usage:
        response["resource_usage"] = result.resource_usage
    
    return response


def get_docker_status() -> Dict[str, Any]:
    """Get detailed Docker executor status."""
    return get_executor().get_status()


def get_docker_stats() -> Dict[str, Any]:
    """Get detailed execution statistics."""
    return get_executor().get_detailed_stats()


# =============================================================================
# SERVER FUNCTIONS
# =============================================================================

def start_text_server():
    """Text analysis server on port 8000."""
    import uvicorn
    app = expose_tools(
        tools=[summarize, word_count],
        title="Text Analysis Server"
    )
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="error")


def start_utility_server():
    """Utility tools server on port 8001."""
    import uvicorn
    app = expose_tools(
        tools=[generate_password, calculate_statistics],
        title="Utility Server"
    )
    uvicorn.run(app, host="0.0.0.0", port=8001, log_level="error")


def start_code_server():
    """Code execution server on port 8002."""
    import uvicorn
    app = expose_tools(
        tools=[execute_python, get_docker_status, get_docker_stats],
        title="Code Execution Server"
    )
    uvicorn.run(app, host="0.0.0.0", port=8002, log_level="error")


# =============================================================================
# MAIN
# =============================================================================

def create_llm_provider():
    if os.getenv("OPENAI_API_KEY"):
        try:
            return OpenAIProvider(model="gpt-4")
        except:
            pass
    print("Using Ollama")
    return OllamaProvider(model="gpt-oss:120b-cloud")


def main():
    print("\n" + "="*70)
    print("Multi-Server MCP Setup with Detailed Docker Monitoring")
    print("="*70 + "\n")
    
    # Initialize Docker with detailed info
    print("Initializing Docker executor...\n")
    executor = get_executor()
    print()
    
    # Show Docker status
    status = executor.get_status()
    print("-"*70)
    print("DOCKER STATUS")
    print("-"*70)
    print(f"Mode: {status['mode'].upper()}")
    if status['docker_available']:
        print(f"Docker Version: {status['docker_version']}")
        print(f"Docker OS: {status['docker_os']}")
        print(f"Image: {status['image']}")
        print("\nResource Limits:")
        if status['resource_limits']:
            print(f"  CPU: {status['resource_limits']['cpu_quota']/100000:.1f} cores")
            print(f"  Memory: {status['resource_limits']['mem_limit']}")
            print(f"  Processes: {status['resource_limits']['pids_limit']}")
        print("\nSecurity Features:")
        for feature, enabled in status['security_features'].items():
            print(f"  {feature.replace('_', ' ').title()}: {'Yes' if enabled else 'No'}")
    else:
        print("\nFallback Mode Active:")
        for feature, value in status['security_features'].items():
            print(f"  {feature.replace('_', ' ').title()}: {value}")
    print("-"*70 + "\n")
    
    # Start servers
    print("Starting MCP servers...")
    servers = [
        multiprocessing.Process(target=start_text_server, daemon=True, name="text"),
        multiprocessing.Process(target=start_utility_server, daemon=True, name="utility"),
        multiprocessing.Process(target=start_code_server, daemon=True, name="code"),
    ]
    
    for server in servers:
        server.start()
        print(f"  Started: {server.name} server")
    
    time.sleep(3)
    
    print("\nServers running:")
    print("  :8000 - Text Analysis (summarize, word_count)")
    print("  :8001 - Utilities (password, statistics)")
    print("  :8002 - Code Execution (execute, status, stats)")
    
    # Create agent
    print("\nCreating agent...")
    llm = create_llm_provider()
    agent = PolyAgent(
        llm_provider=llm,
        mcp_servers=[
            "http://localhost:8000/mcp",
            "http://localhost:8001/mcp",
            "http://localhost:8002/mcp",
        ],
        verbose=True
    )
    
    total_tools = sum(len(t) for t in agent.tools_cache.values())
    print(f"Agent ready with {total_tools} tools\n")
    
    # Examples with Docker monitoring
    print("="*70)
    print("Running Examples with Docker Monitoring")
    print("="*70 + "\n")
    
    examples = [
        ("Simple calculation", "print(2 + 2)"),
        ("System info", "import platform; print(f'OS: {platform.system()}, Python: {platform.python_version()}')"),
        ("Resource test", "data = [i**2 for i in range(1000)]; print(f'Generated {len(data)} numbers, sum = {sum(data)}')"),
    ]
    
    for name, code in examples:
        print(f"\nExample: {name}")
        print("-"*50)
        print(f"Code: {code[:60]}{'...' if len(code) > 60 else ''}")
        print()
        
        try:
            response = agent.run(f"Execute this Python code: {code}")
            print(f"\nResult: {response}\n")
        except Exception as e:
            print(f"Error: {e}\n")
        
        time.sleep(1)
    
    # Interactive mode
    print("="*70)
    print("Interactive Mode")
    print("="*70)
    print("\nCommands:")
    print("  docker-status  - Show Docker configuration")
    print("  docker-stats   - Show detailed execution statistics") 
    print("  servers        - List connected servers")
    print("  tools          - List available tools")
    print("  quit           - Exit")
    print("\nOr type Python code to execute\n")
    
    while True:
        try:
            user_input = input(">>> ").strip()
            
            if not user_input:
                continue
            
            if user_input.lower() in ['quit', 'exit', 'q']:
                break
            
            if user_input.lower() == 'docker-status':
                response = agent.run("Get Docker executor status")
                print(f"\n{response}\n")
                continue
            
            if user_input.lower() == 'docker-stats':
                response = agent.run("Get detailed Docker execution statistics")
                print(f"\n{response}\n")
                continue
            
            if user_input.lower() == 'servers':
                print("\nConnected servers:")
                for i, server in enumerate(agent.mcp_servers, 1):
                    tool_count = len(agent.tools_cache.get(server, []))
                    print(f"  {i}. {server} ({tool_count} tools)")
                print()
                continue
            
            if user_input.lower() == 'tools':
                print("\nAvailable tools by server:")
                for server, tools in agent.tools_cache.items():
                    port = server.split(':')[2].split('/')[0]
                    print(f"  Port {port}: {', '.join(tools)}")
                print()
                continue
            
            # Execute as Python code
            print()
            response = agent.run(f"Execute this Python code: {user_input}")
            print(f"\nResult: {response}\n")
        
        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"\nError: {e}\n")
    
    # Show final statistics
    print("\n" + "="*70)
    print("FINAL STATISTICS")
    print("="*70)
    
    final_stats = executor.get_detailed_stats()
    
    print("\nExecution Summary:")
    for key, value in final_stats["execution_stats"].items():
        print(f"  {key.replace('_', ' ').title()}: {value}")
    
    print("\nPerformance Summary:")
    for key, value in final_stats["performance_stats"].items():
        print(f"  {key.replace('_', ' ').title()}: {value}")
    
    if final_stats["recent_executions"]:
        print("\nRecent Executions:")
        for exec_record in final_stats["recent_executions"][-3:]:
            print(f"  #{exec_record['execution_id']}: {exec_record.get('container_id', 'N/A')} - "
                  f"{'Success' if exec_record.get('success') else 'Failed'} "
                  f"({exec_record.get('execution_time', 0):.2f}s)")
    
    print("="*70)
    
    # Cleanup
    for server in servers:
        server.terminate()
    
    print("\nGoodbye!\n")


if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()
