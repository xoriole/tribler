import os
import re
import shutil
import sys
from pathlib import Path

from setuptools import find_packages
from cx_Freeze import setup, Executable

# Copy src/run_tribler.py --> src/tribler/run.py to make it accessible in entry_points scripts.
shutil.copy("src/run_tribler.py", "src/tribler/run.py")

# Assuming src/run_tribler.py is your main script
executable = Executable(
    script="src/run_tribler.py",
    base="Win32GUI" if sys.platform == "win32" else None,
    icon='build/win/resources/tribler.ico' if sys.platform == 'win32' else 'build/mac/resources/tribler.icns',
)

# Add additional packages and modules to include
packages = [
    "aiohttp_apispec",
    "sentry_sdk",
    "ipv8",
    "PIL",
    "pkg_resources",
    "pydantic",
    "pyqtgraph",
    "PyQt5.QtTest",
    "requests",
    "tribler.core",
    "tribler.gui",
    "faker"
    # Add more packages as needed
]

# Include files and directories
include_files = [
    ("src/tribler/gui/qt_resources", "qt_resources"),
    ("src/tribler/gui/images", "images"),
    ("src/tribler/gui/i18n", "i18n"),
    ("src/tribler/core", "tribler_source/tribler/core"),
    ("src/tribler/gui", "tribler_source/tribler/gui"),
    ("build/win/resources", "tribler_source/resources"),
    # Add more files/directories as needed
]

# Excludes
excludes = ['wx', 'PyQt4', 'FixTk', 'tcl', 'tk', '_tkinter', 'tkinter', 'Tkinter', 'matplotlib']

build_exe_options = {
    "packages": packages,
    "excludes": excludes,
    "include_files": include_files,
}

def read_version_from_file(file_path):
    with open(file_path, "r", encoding="utf-8") as file:
        file_content = file.read()
    # Use regular expression to find the version pattern
    version_match = re.search(r"^version_id = ['\"]([^'\"]*)['\"]", file_content, re.M)
    if version_match:
        version_str = version_match.group(1)
        return version_str.split("-")[0]
    raise RuntimeError("Unable to find version string.")


version_file = os.path.join('src', 'tribler', 'core', 'version.py')
version = read_version_from_file(version_file)


def read_requirements(file_name, directory='.'):
    file_path = os.path.join(directory, file_name)
    requirements = []
    with open(file_path, 'r', encoding='utf-8') as file:
        for line in file:
            # Check for a nested requirements file
            if line.startswith('-r'):
                nested_file = line.split(' ')[1].strip()
                requirements += read_requirements(nested_file, directory)
            elif not line.startswith('#') and line.strip() != '':
                requirements.append(line.strip().split('#')[0].strip())
    return requirements


base_dir = os.path.dirname(os.path.abspath(__file__))

install_requires = read_requirements('requirements-build.txt', base_dir)
extras_require = {
    'dev': read_requirements('requirements-test.txt', base_dir),
}


setup(
    name="tribler",
    version=version,
    description="Privacy enhanced BitTorrent client with P2P content discovery",
    long_description=Path('README.rst').read_text(encoding="utf-8"),
    long_description_content_type="text/x-rst",
    author="Tribler Team",
    author_email="info@tribler.org",
    url="https://github.com/Tribler/tribler",
    keywords='BitTorrent client, file sharing, peer-to-peer, P2P, TOR-like network',
    python_requires='>=3.8',
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    include_package_data=True,
    install_requires=install_requires,
    extras_require=extras_require,
    entry_points={
        "gui_scripts": [
            "tribler=tribler.run:main",
        ]
    },
    classifiers=[
        "Development Status :: 5 - Production/Stable",
        "Intended Audience :: Developers",
        "Intended Audience :: End Users/Desktop",
        "License :: OSI Approved :: GNU General Public License v3 (GPLv3)",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Topic :: Communications :: File Sharing",
        "Topic :: Security :: Cryptography",
        "Operating System :: OS Independent",
    ],
    options={"build_exe": build_exe_options},
    executables=[executable]
)
