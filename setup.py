#!/usr/bin/env python
import sys
from setuptools import setup, find_packages

from unnaturalcode import __version__

with open('requirements.txt') as requirements:
    requires = [l.strip() for l in requirements.readlines()]

if 'test' in sys.argv:
    sys.argv.remove('test')
    sys.argv.append('nosetests')

setup(
    name = "unnaturalcode",
    version = __version__,
    packages = find_packages(),
    entry_points = {
        "console_scripts": [
            "ucwrap = unnaturalcode.wrap:main",
            "uclearn = unnaturalcode.learn:main",
            "uccheck = unnaturalcode.wrap:check"
        ],
    },
    author = "Joshua Charles Campbell",
    description = "Compiler Error Augmentation System",
    include_package_data = True,
    install_requires = requires,
    setup_requires = ['nose>=1.0'],
    zip_safe = False,
)
