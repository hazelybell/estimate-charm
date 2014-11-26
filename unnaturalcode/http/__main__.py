import os
import sys

# Do some path non-sense to make unnaturalcode_http look like a module.
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from unnaturalcode_http import server

if __name__ == '__main__':
    server()
