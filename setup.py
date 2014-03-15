#!/usr/bin/env python
from setuptools import setup, find_packages

libraries = [l.strip() for l in open('requirements.txt').readlines()]

# To set __version__
__version__ = 'unknown'
execfile('unnaturalcode/_version.py')

setup(
    name = "unnaturalcode",
    version = __version__,
    packages = find_packages(),
    entry_points = {
        "console_scripts": [
            "ucwrap = unnaturalcode.wrap:main",
        ],
    },
    author = "Joshua Charles Campbell",
    description = "Compiler Error Augmentation System",
    include_package_data = True,
    install_requires = libraries,
    zip_safe = False,
)
