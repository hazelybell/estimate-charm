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
        #exclude = ["testdata"]
      ),
    entry_points = {
        "console_scripts": [
            "estimatecharm = estimatecharm.estimateCharm:main",
        ],
    },
    author = "Joshua Charles Campbell",
    description = "Code Charm Estimation Tool",
    author_email='joshua2@ualberta.ca',
    url='https://github.com/orezpraw/estimate-charm',
    download_url='https://github.com/orezpraw/estimate-charm/tarball/0.1',
    license='AGPL3+',
    include_package_data = True,
    install_requires = requires,
    tests_require=tests_require,
    zip_safe = False,
)
