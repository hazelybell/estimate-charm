# ------- UTILITY FUNCTIONS ---------------------------------------------------

import os, sys, re, json

ws = re.compile('^\s+$')

def slurp(fn):
    return open(fn).read()

def toBool(inputString):
    return json.loads(inputString)

# From http://www.python.org/dev/peps/pep-0318/#examples 2013-09-30
# Public Domain
def singleton(cls):
    instances = {}
    def getinstance():
        if cls not in instances:
            instances[cls] = cls()
        return instances[cls]
    return getinstance
# End Public Domain