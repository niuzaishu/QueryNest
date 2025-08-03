#!/usr/bin/env python3
"""Setup script for QueryNest"""

from setuptools import setup, find_packages

setup(
    name="querynest",
    version="1.0.0",
    description="QueryNest MCP MongoDB查询服务",
    author="QueryNest Team",
    python_requires=">=3.8",
    py_modules=["mcp_server", "config"],
    packages=["database", "scanner", "mcp_tools", "utils"],
    install_requires=[
        "mcp>=1.0.0",
        "pymongo>=4.0.0",
        "motor>=3.3.0",
        "pydantic>=2.0.0",
        "pydantic-settings>=2.0.0",
        "pyyaml>=6.0",
        "structlog>=23.0.0",
        "nltk>=3.8",
        "scikit-learn>=1.3.0",
        "numpy>=1.24.0",
        "python-dotenv>=1.0.0",
        "dnspython>=2.0.0",  # motor依赖
        "tornado>=5.0"       # motor依赖
    ],
    entry_points={
        "console_scripts": [
            "querynest-mcp=mcp_server:cli_main",
        ]
    },
    package_data={"": ["*.yaml", "*.yml"]},
    include_package_data=True,
)