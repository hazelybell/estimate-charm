#    Copyright 2013, 2014, 2015 Joshua Charles Campbell
#
#    This file is part of EstimateCharm.
#
#    EstimateCharm is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    EstimateCharm is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with EstimateCharm.  If not, see <http://www.gnu.org/licenses/>.

"""
Typically ran with FAST="True" py.test

See `source_this.sh` in the repository root for enivornment variables that
must be set.
"""

import unittest
from logging import debug, info, warning, error

from unnaturalcode.unnaturalCode import *
from unnaturalcode.pythonSource import *
from unnaturalcode.estimateCharm import *

import os, os.path, zmq, sys, shutil, token, gc
from glob import glob
from tempfile import *

from unnaturalcode.ucTestData import *

logging.getLogger(__name__).setLevel(logging.DEBUG)

class testEstimateCharm(unittest.TestCase):
    @classmethod
    def setUpClass(self):
        #self.uc = unnaturalCode()
        pass
    @classmethod
    def tearDownClass(self):
        #del self.uc
        pass

# rwfubmqqoiigevcdefhmidzavjwg
