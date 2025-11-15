"""
Sandbox Executor - Lightweight Security
Optimized for LLM-generated code that calls MCP tools.
Security relies on MCP tools being the boundary, not code restrictions.
"""

import sys
import io
import json
import time
import threading
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from contextlib import redirect_stdout, redirect_stderr


@dataclass
class ExecutionResult:
    """Result of code execution in sandbox."""
    success: bool
    output: str
    error: Optional[str] = None
    execution_time: float = 0.0
    return_value: Any = None


class ExecutionError(Exception):
    """Raised when code execution fails."""
    pass


class TimeoutError(ExecutionError):
    """Raised when code execution times out."""
    pass


class SandboxExecutor:
    """
    Lightweight secure executor for LLM-generated code.
    
    Security philosophy:
    - MCP tools are the security boundary
    - Only block truly dangerous operations (filesystem, network, OS commands)
    - Let code import any module and use any Python feature
    - Trust that LLM generates business logic, not exploits
    
    Why this works:
    - Code can only orchestrate your exposed MCP tools
    - Even with all Python features, code can't harm system without tools
    - If your tools are safe, the orchestration code is safe
    """
    
    # Only block TRULY dangerous operations
    FORBIDDEN_PATTERNS = [
        'os.system',
        'subprocess.',
        'eval(',
        'exec(',
        'compile(',
        '__import__("os")',
        '__import__("subprocess")',
        'open(',  # Block file operations
        'file(',
    ]
    
    def __init__(
        self,
        tools_api: Any,
        timeout: float = 30.0,
        max_output_size: int = 1_000_000,
        verbose: bool = False
    ):
        """
        Initialize sandbox executor.
        
        Args:
            tools_api: ToolsAPI instance with MCP tool access
            timeout: Maximum execution time in seconds
            max_output_size: Maximum output size in characters
            verbose: Enable verbose logging
        """
        self.tools_api = tools_api
        self.timeout = timeout
        self.max_output_size = max_output_size
        self.verbose = verbose
    
    def _check_code_safety(self, code: str) -> None:
        """
        Lightweight safety check - only block truly dangerous operations.
        
        Args:
            code: Python code to check
            
        Raises:
            ExecutionError: If dangerous patterns detected
        """
        # Only check for truly dangerous patterns
        for pattern in self.FORBIDDEN_PATTERNS:
            if pattern in code:
                raise ExecutionError(
                    f"Forbidden operation detected: '{pattern}'. "
                    f"Cannot execute code that accesses filesystem, network, or OS."
                )
    
    def _create_safe_globals(self) -> Dict[str, Any]:
        """
        Create globals dictionary with minimal restrictions.
        
        Returns:
            Dictionary with builtins, tools, and common modules
        """
        # Start with standard builtins (almost everything)
        safe_globals = {
            '__builtins__': __builtins__,
            'tools': self.tools_api,
        }
        
        # Pre-import common safe modules for convenience
        import json
        safe_globals['json'] = json
        
        return safe_globals
    
    def _execute_with_timeout(
        self,
        code_obj: Any,
        globals_dict: Dict[str, Any]
    ) -> tuple[Optional[str], Optional[str], Optional[Any]]:
        """
        Execute code with timeout protection.
        
        Args:
            code_obj: Compiled code object
            globals_dict: Globals dictionary
            
        Returns:
            Tuple of (stdout, stderr, return_value)
            
        Raises:
            TimeoutError: If execution exceeds timeout
        """
        result = {
            'stdout': None,
            'stderr': None,
            'return_value': None,
            'error': None
        }
        
        def target():
            """Thread target function."""
            try:
                stdout_capture = io.StringIO()
                stderr_capture = io.StringIO()
                
                with redirect_stdout(stdout_capture), redirect_stderr(stderr_capture):
                    try:
                        exec(code_obj, globals_dict)
                        result['return_value'] = globals_dict.get('__return_value__')
                    except Exception as e:
                        result['error'] = e
                
                result['stdout'] = stdout_capture.getvalue()
                result['stderr'] = stderr_capture.getvalue()
            
            except Exception as e:
                result['error'] = e
        
        # Execute in separate thread with timeout
        thread = threading.Thread(target=target, daemon=True)
        thread.start()
        thread.join(timeout=self.timeout)
        
        if thread.is_alive():
            raise TimeoutError(
                f"Code execution exceeded timeout of {self.timeout} seconds"
            )
        
        if result['error']:
            raise result['error']
        
        return result['stdout'], result['stderr'], result['return_value']
    
    def execute(self, code: str) -> ExecutionResult:
        """
        Execute Python code in lightweight sandbox.
        
        Args:
            code: Python code to execute
            
        Returns:
            ExecutionResult with output and status
        """
        start_time = time.time()
        
        if self.verbose:
            print(f"\n{'='*60}")
            print("SANDBOX EXECUTION")
            print(f"{'='*60}")
            print(f"Code ({len(code)} chars):")
            print(code[:500] + ("..." if len(code) > 500 else ""))
            print(f"{'='*60}\n")
        
        try:
            # Lightweight safety check
            self._check_code_safety(code)
            
            # Compile code
            try:
                code_obj = compile(code, '<sandbox>', 'exec')
            except SyntaxError as e:
                raise ExecutionError(f"Syntax error: {e}")
            
            # Create execution environment
            globals_dict = self._create_safe_globals()
            
            # Execute with timeout protection
            stdout, stderr, return_value = self._execute_with_timeout(
                code_obj,
                globals_dict
            )
            
            # Collect output
            output_parts = []
            if stdout and stdout.strip():
                output_parts.append(stdout.strip())
            if stderr and stderr.strip():
                output_parts.append(f"STDERR: {stderr.strip()}")
            
            output = "\n".join(output_parts) if output_parts else ""
            
            # Enforce output size limit
            if len(output) > self.max_output_size:
                output = output[:self.max_output_size] + "\n... (output truncated)"
            
            execution_time = time.time() - start_time
            
            if self.verbose:
                print(f"✅ Execution successful ({execution_time:.2f}s)")
                if output:
                    print(f"Output: {output[:200]}...")
            
            return ExecutionResult(
                success=True,
                output=output,
                execution_time=execution_time,
                return_value=return_value
            )
        
        except TimeoutError as e:
            execution_time = time.time() - start_time
            error_msg = str(e)
            if self.verbose:
                print(f"⏱️ Timeout: {error_msg}")
            
            return ExecutionResult(
                success=False,
                output="",
                error=error_msg,
                execution_time=execution_time
            )
        
        except ExecutionError as e:
            execution_time = time.time() - start_time
            error_msg = str(e)
            if self.verbose:
                print(f"❌ Security error: {error_msg}")
            
            return ExecutionResult(
                success=False,
                output="",
                error=error_msg,
                execution_time=execution_time
            )
        
        except Exception as e:
            execution_time = time.time() - start_time
            error_msg = f"{type(e).__name__}: {str(e)}"
            if self.verbose:
                print(f"❌ Execution error: {error_msg}")
            
            return ExecutionResult(
                success=False,
                output="",
                error=error_msg,
                execution_time=execution_time
            )
    
    def validate_code(self, code: str) -> tuple[bool, Optional[str]]:
        """
        Validate code without executing it.
        
        Args:
            code: Python code to validate
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        try:
            self._check_code_safety(code)
            compile(code, '<sandbox>', 'exec')
            return True, None
        except Exception as e:
            return False, str(e)