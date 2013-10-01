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
from mitlmCorpus import *
from pythonLexical import *
import os, zmq

zctx = None

@singleton
class unnaturalCode(object):
    def __init__(self):
        global zctx
        assert not zctx
        self.zctx = zmq.Context()
        zctx = self.zctx
        self.forceTrain = toBool(os.getenv("ucForceTrain", "false"))
        self.forceValidate = toBool(os.getenv("ucValidate", "false"))

class sourceModel(object):
    
    def __init__(self, cm=mitlmCorpus(), lm=pythonLexical()):
        self.cm = cm
        self.lm = lm
    
    # Blindly train on a set of files whether or not it compiles...
    def trainFile(self, files):
        files = [files] if isinstance(files, str) else files
        assert isinstance(files, list)
        for fi in files:
            sourceCode = slurp(fi)
            trainString(sourceCode)

    # Corpify a string
    def corpify(self, lexemes):
        return self.cm.corpify(map(self.lm.stringify1, lexemes))
    
    # Train on a source code string
    def trainString(self, sourceCode):
        pass