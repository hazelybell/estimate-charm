#!/usr/bin/env python
import sys
from setuptools import setup, find_packages

requires = [l.strip() for l in open('requirements.txt').readlines()]

if 'test' in sys.argv:
    sys.argv.remove('test')
    sys.argv.append('nosetests')

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
    install_requires = requires,
    setup_requires = ['nose>=1.0'],
    zip_safe = False,
)
