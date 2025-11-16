"""
PolyMCP - Universal MCP Agent & Toolkit
"""

from setuptools import setup, find_packages
from pathlib import Path

# Read README for long description
readme_path = Path(__file__).parent / "README.md"
long_description = ""
if readme_path.exists():
    with open(readme_path, encoding="utf-8") as f:
        long_description = f.read()

# Dynamic version: read from polymcp/version.py
version_file = Path(__file__).parent / "polymcp" / "version.py"
version = "0.0.0.dev0"
if version_file.exists():
    with open(version_file, "r", encoding="utf-8") as f:
        exec(f.read())

setup(
    name="polymcp",
    version=version,
    author="PolyMCP",
    author_email="",
    description="Universal MCP Agent & Toolkit for intelligent LLM tool orchestration",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/llm-use/polymcp",
    packages=find_packages(exclude=["tests", "examples", "docs"]),
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "Topic :: Scientific/Engineering :: Artificial Intelligence",
    ],
    python_requires=">=3.8",
    install_requires=[
        "fastapi>=0.109.0",
        "uvicorn[standard]>=0.27.0",
        "pydantic>=2.5.0",
        "requests>=2.31.0",
        "docstring-parser>=0.15",
    ],
    extras_require={
        "openai": ["openai>=1.10.0"],
        "anthropic": ["anthropic>=0.8.0"],
        "all": [
            "openai>=1.10.0",
            "anthropic>=0.8.0",
        ],
        "dev": [
            "pytest>=7.4.0",
            "pytest-asyncio>=0.23.0",
            "pytest-cov>=4.1.0",
            "black>=23.12.0",
            "flake8>=7.0.0",
            "mypy>=1.8.0",
            "httpx>=0.26.0",
        ],
    },
    entry_points={
        "console_scripts": [],
    },
    include_package_data=True,
    zip_safe=False,
    keywords="mcp agent llm ai openai anthropic claude fastapi tools",
    project_urls={
        "Bug Reports": "https://github.com/llm-use/polymcp/issues",
        "Source": "https://github.com/llm-use/polymcp",
        "Documentation": "https://github.com/llm-use/polymcp#readme",
    },
)
