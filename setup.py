"""Compatibility setup.py for older pip versions."""
from setuptools import setup, find_packages

setup(
    name="lucycode",
    version="0.3.0",
    description="Lucy Code — An AI-powered agentic coding assistant CLI",
    packages=find_packages(),
    python_requires=">=3.9",
    install_requires=[
        "rich>=13.7",
        "click>=8.1",
        "pydantic>=2.5",
        "pyyaml>=6.0",
        "tiktoken>=0.7",
        "prompt-toolkit>=3.0.40",
        "pynput>=1.7.0",
        "mss>=9.0.0",
        "Pillow>=10.2.0",
        "tree-sitter>=0.22.0",
        "tree-sitter-python",
        "tree-sitter-javascript",
        "tree-sitter-typescript",
    ],
    extras_require={
        "cloud": ["anthropic>=0.40.0"],
        "offline": ["aiohttp>=3.9"],
        "local": ["llama-cpp-python>=0.2.75"],
        "all": ["anthropic>=0.40.0", "aiohttp>=3.9", "llama-cpp-python>=0.2.75"],
    },
    entry_points={
        "console_scripts": [
            "lucy=lucy.main:cli",
        ],
    },
)
