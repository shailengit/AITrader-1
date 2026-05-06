"""Setup script for cli-anything-tradecraft."""

from setuptools import setup, find_namespace_packages

setup(
    name="cli-anything-tradecraft",
    version="0.1.0",
    description="CLI harness for TradeCraft - Sector Rotation, AI Screener, and QuantGen Strategy Builder",
    author="TradeCraft CLI Team",
    url="https://github.com/shailendrakaushik/TradeCraft",
    packages=find_namespace_packages(include=["cli_anything.*"]),
    namespace_packages=["cli_anything"],
    include_package_data=True,
    python_requires=">=3.8",
    install_requires=[
        "click>=8.0",
    ],
    extras_require={
        "dev": [
            "pytest>=7.0",
            "pytest-cov>=4.0",
        ],
    },
    entry_points={
        "console_scripts": [
            "cli-anything-tradecraft=cli_anything.tradecraft.tradecraft_cli:main",
        ],
    },
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
    ],
)
