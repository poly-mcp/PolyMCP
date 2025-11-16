from setuptools import setup, find_packages
from pathlib import Path

# ===== Legge README.md =====
readme_path = Path(__file__).parent / "README.md"
long_description = readme_path.read_text(encoding="utf-8") if readme_path.exists() else ""

# ===== Version dinamica da polymcp/version.py =====
version_file = Path(__file__).parent / "polymcp/version.py"
version = "0.0.0"  # fallback
if version_file.exists():
    namespace = {}
    with open(version_file, "r", encoding="utf-8") as f:
        exec(f.read(), namespace)
        version = namespace.get("__version__", version)

# ===== Setup =====
setup(
    name="polymcp",  # Nome della libreria su PyPI
    version=version,
    author="PolyMCP",
    author_email="noreply@example.com",
    description="Universal MCP Agent & Toolkit for intelligent LLM tool orchestration",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/llm-use/polymcp",
    packages=find_packages(exclude=["tests", "examples", "docs"]),
    include_package_data=True,  # include files aggiuntivi come version.py
    zip_safe=False,
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
        "all": ["openai>=1.10.0", "anthropic>=0.8.0"],
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
    entry_points={"console_scripts": []},
)
