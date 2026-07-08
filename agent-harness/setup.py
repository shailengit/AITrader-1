"""Setup script for tradecraft CLI."""
from setuptools import setup, find_namespace_packages

setup(
    name="tradecraft-cli",
    version="0.2.0",
    description="TradeCraft CLI — strategy creation, backtesting, coach analytics, Markov learning",
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
            "tradecraft=cli_anything.tradecraft.main:cli",
        ],
    },
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
    ],
)
