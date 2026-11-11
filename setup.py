"""Compatibility setup.py with native C extensions builder."""
import os
import subprocess
try:
    from setuptools import setup, find_packages
    from setuptools.command.build_py import build_py
    from setuptools.command.develop import develop
    _HAS_SETUPTOOLS = True
except ImportError:
    from distutils.core import setup
    find_packages = lambda: ["lucy"]
    build_py = object
    develop = object
    _HAS_SETUPTOOLS = False


def build_native_extensions():
    native_dir = os.path.join(os.path.dirname(__file__), "native")
    if os.path.exists(native_dir) and os.path.exists(os.path.join(native_dir, "Makefile")):
        try:
            subprocess.run(["make", "-C", native_dir], check=False)
        except Exception:
            pass


class CustomBuildPy(build_py):
    def run(self):
        build_native_extensions()
        super().run()


class CustomDevelop(develop):
    def run(self):
        build_native_extensions()
        super().run()


cmdclass_dict = {}
if _HAS_SETUPTOOLS:
    cmdclass_dict = {
        "build_py": CustomBuildPy,
        "develop": CustomDevelop,
    }

setup(
    name="lucycode",
    version="0.3.0",
    description="Lucy Code — An AI-powered agentic coding assistant CLI",
    packages=find_packages(),
    cmdclass=cmdclass_dict,
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
        "weights": [
            "llama-cpp-python>=0.2.75",
            "torch>=2.0.0",
            "transformers>=4.38.0",
            "accelerate>=0.26.0",
        ],
        "all": ["anthropic>=0.40.0", "aiohttp>=3.9", "llama-cpp-python>=0.2.75"],
    },
    entry_points={
        "console_scripts": [
            "lucy=lucy.main:cli",
        ],
    },
)
