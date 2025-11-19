# polymcp/cli/__init__.py
"""
PolyMCP CLI - Command Line Interface
Production-ready CLI for managing PolyMCP projects, servers, and agents.
"""

__version__ = "1.2.3"

from .main import cli, main  # ← Aggiungi main qui!

__all__ = ['cli', 'main']  # ← E qui!
