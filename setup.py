from setuptools import setup, find_packages
import os

# Legge README.md
here = os.path.abspath(os.path.dirname(__file__))
with open(os.path.join(here, 'README.md'), encoding='utf-8') as f:
    long_description = f.read()

setup(
    name="polymcp",
    version="0.0.1",
    author="PolyMCP",
    author_email="noreply@example.com",
    description="Universal MCP Agent & Toolkit for intelligent LLM tool orchestration",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/llm-use/polymcp",
    packages=find_packages(exclude=["tests*", "examples*", "docs*"]),
    package_data={
        "polymcp": ["*.py"],
    },
    include_package_data=True,
    zip_safe=False,
    python_requires=">=3.8",
    license="MIT",  # AGGIUNGI QUESTO
    classifiers=[   # AGGIUNGI QUESTI
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
    ],
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
)
