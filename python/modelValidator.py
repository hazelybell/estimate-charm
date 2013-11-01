#!/usr/bin/python
#    Copyright 2013 Joshua Charles Campbell
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

from ucUtil import *
from unnaturalCode import *
from logging import debug, info, warning, error

class modelValidation(object):
    
    def __init__(self, source=None, language=pythonSource, resultsDir=None):
        self.resultsDir = ((resultsDir or os.getenv("ucResultsDir", None)) or mkdtemp(prefix='ucValidation-'))
        if isinstance(source, str):
            pass
        elif isinstance(source, list):
            pass
        else:
            raise TypeError("Constructor arguments!")

        assert os.access(self.
        