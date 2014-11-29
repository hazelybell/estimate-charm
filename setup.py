#!/usr/bin/env python
import sys
from setuptools import setup, find_packages

from unnaturalcode import __version__

with open('requirements.txt') as f:
    requires = [l.strip() for l in f.readlines()]

with open('test-requirements.txt') as f:
    tests_require = [l.strip() for l in f.readlines()]

setup(
    name = "unnaturalcode",
    version = __version__,
    packages = find_packages(
        exclude = ["testdata"]
      ),
    entry_points = {
        "console_scripts": [
            "ucwrap = unnaturalcode.wrap:main",
            "uclearn = unnaturalcode.learn:main",
            "uccheck = unnaturalcode.wrap:check"
        ],
    },
    author = "Joshua Charles Campbell",
    description = "Compiler Error Augmentation System",
    license='AGPL3+',
    include_package_data = True,
    install_requires = requires,
    tests_require=tests_require,
    zip_safe = False,
)
