import os

from setuptools import find_packages, setup

# Read the contents of your public README file for the PyPI project page
theme_dir = os.path.abspath(os.path.dirname(__file__))
with open(os.path.join(theme_dir, "README.md"), encoding="utf-8") as f:
    long_description = f.read()

# Base stable version
BASE_VERSION = "0.1.1"

# Check if running inside GitHub Actions and processing a dev build
if os.environ.get("WORKTREE_DEV_BUILD") == "true":
    run_number = os.environ.get("GITHUB_RUN_NUMBER", "0")
    VERSION = f"{BASE_VERSION}.dev{run_number}"
else:
    VERSION = BASE_VERSION

setup(
    name="getworktree",
    version=VERSION,
    author="Worktree Team",
    author_email="hello@getworktree.io",
    description="Isolated git worktree developer workflows and AI agent workspaces.",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com",
    project_urls={
        "Homepage": "https://getworktree.io",
        "Bug Tracker": "https://github.com/issues",
    },
    classifiers=[
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.13",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Environment :: Console",
        "Topic :: Software Development :: Version Control :: Git",
    ],
    # Automatically finds the code sub-folders inside your repository
    packages=find_packages(exclude=["tests*", "docs*"]),
    python_requires=">=3.13",
    # Baseline external libraries your CLI needs to run
    install_requires=[
        "typer[all]>=0.9.0",  # Automatically bundles rich and shellingham out of the box
        "jsonschema>=4.0.0",
        "pyyaml>=6.0.0",
        "pydantic>=2.0.0",
    ],
    extras_require={
        "dev": [
            "pytest>=8.0.0",
            "pytest-cov>=4.0.0",
            "ruff>=0.6.0",
            "invoke>=2.0.0",
        ],
        "cursor": [
            "cursor-sdk>=1.0.26,<2",
        ],
    },
    package_data={"getworktree": ["schemas/*.json", "core/templates/*/*.yml"]},
    include_package_data=True,
    # CRITICAL: Maps the terminal execution command
    # Typing 'wt' in the terminal will run the main() function inside getworktree/cli.py
    entry_points={
        "console_scripts": [
            "wt=getworktree.cli:app",
        ],
    },
)
