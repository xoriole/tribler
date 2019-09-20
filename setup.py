from __future__ import absolute_import

from setuptools import find_packages, setup

from Tribler.Core.version import version_id

with open('README.rst', 'r') as f:
    long_description = f.read()

with open('LICENSE', 'r') as f:
    licenses = f.read()

data_dirs = [
    'Tribler.Test.data',
    'Tribler.Test.data.41aea20908363a80d44234e8fef07fab506cd3b4',
    'Tribler.Test.data.contentdir',
    'Tribler.Test.Core.Category.data.Tribler.Core.Category',
    'Tribler.Test.Core.data',
    'Tribler.Test.Core.data.config_files',
    'Tribler.Test.Core.data.libtorrent',
    'Tribler.Test.Core.data.torrent_creation_files',
    'Tribler.Test.Core.data.upgrade_databases',
]

setup(
    name='libtribler',
    description='Tribler core functionality package',
    long_description=long_description,
    license=licenses,
    version=str(version_id),
    url='https://github.com/Tribler/tribler',
    author='Tribler team from Delft University of Technology',
    author_email='info@tribler.org',
    package_data={'': ['*.*']},
    packages=find_packages() + data_dirs,
    install_requires=[
        "PyQt5",
        "Twisted",
        "cryptography",
        "libnacl",
        "pony",
        "lz4",
        "psutil",
        "networkx",
        "pyqtgraph",
        "matplotlib",
        "chardet",
        "cherrypy",
        "configobj",
        "netifaces",
        "six",
        "bitcoinlib"
    ],
    classifiers=[
        "Development Status :: 5 - Production/Stable",
        "Framework :: Twisted",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: GNU Lesser General Public License v3 (LGPLv3)",
        "Natural Language :: English",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 2.7",
        "Programming Language :: Python :: 3.5",
        "Programming Language :: Python :: 3.6",
        "Programming Language :: Python :: 3.7",
        "Topic :: Scientific/Engineering",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "Topic :: System :: Distributed Computing",
        "Topic :: System :: Networking"
    ]
)
