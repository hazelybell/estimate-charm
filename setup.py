#!/usr/bin/env python
import sys
from setuptools import setup, find_packages

from estimatecharm import __version__

with open('requirements.txt') as f:
    requires = [l.strip() for l in f.readlines()]

with open('test-requirements.txt') as f:
    tests_require = [l.strip() for l in f.readlines()]

setup(
    name = "estimatecharm",
    version = __version__,
    packages = find_packages(
        exclude = ["testdata"]
      ),
    entry_points = {
        "console_scripts": [
            "ucwrap = estimatecharm.wrap:main",
            "uclearn = estimatecharm.learn:main",
            "uccheck = estimatecharm.wrap:check"
        ],
    },
    author = "Joshua Charles Campbell",
    description = "Code Charm Estimation Tool",
    license='AGPL3+',
    include_package_data = True,
    install_requires = requires,
    tests_require=tests_require,
    zip_safe = False,
)
