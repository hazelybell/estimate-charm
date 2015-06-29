#    Copyright 2013, 2014 Joshua Charles Campbell
#
#    This file is part of UnnaturalCode.
#    
#    UnnaturalCode is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    UnnaturalCode is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with UnnaturalCode.  If not, see <http://www.gnu.org/licenses/>.
# ------- UTILITY FUNCTIONS ---------------------------------------------------

import os, sys, re, json

def slurp(fn):
    return open(fn).read()

def toBool(inputString):
    return json.loads(inputString)

# From http://www.python.org/dev/peps/pep-0318/#examples 2013-09-30
# Public Domain, edited to take args
def singleton(cls):
    instances = {}
    def getinstance(*a, **k):
        if cls not in instances:
            instances[cls] = cls(*a, **k)
        return instances[cls]
    return getinstance
# End Public Domain