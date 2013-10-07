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

import unittest

from ucUtil import *
from unnaturalCode import *
from sourceModel import *
from pythonLexical import *
from mitlmCorpus import *

import os, os.path, zmq, sys, shutil
from tempfile import *

from ucTestData import *

ucGlobal = None

def setUpModule():
    global ucGlobal
    ucGlobal = unnaturalCode()

class testUcUtil(unittest.TestCase):
    def testToBool(self):
        self.assertFalse(toBool("false"), 'toBool false not false')
        self.assertTrue(toBool("true"), 'toBool true not true')
    def testWS(self):
        self.assertTrue(ws.match('        '))
        self.assertTrue(ws.match(indentLexeme['value']))

class testUnnaturalCode(unittest.TestCase):
    @classmethod
    def setUpClass(self):
        #self.uc = unnaturalCode()
        pass
    def testSingleton(self):
        ucA = unnaturalCode()
        ucB = unnaturalCode()
        self.assertEquals(ucA, ucB)
    def testEnvBools(self):
        self.assertEquals(type(ucGlobal.forceTrain), bool)
        self.assertEquals(type(ucGlobal.forceValidate), bool)
    def testLoggingEnv(self):
        dir=os.path.dirname(ucGlobal.logFilePath)
        self.assertTrue(os.access(dir, os.X_OK & os.R_OK & os.W_OK))
        self.assertTrue(os.path.isdir(dir))
    def testZctx(self):
        self.assertEquals(type(ucGlobal.zctx), zmq.core.context.Context)
    @classmethod
    def tearDownClass(self):
        #del self.uc
        pass

class testMitlmCorpus(unittest.TestCase):
    def testEnvMitlm(self):
        cm = mitlmCorpus()
        self.assertTrue(os.access(cm.estimateNgramPath, os.X_OK & os.R_OK))
    def testDefaultCorpusEnv(self):
        cm = mitlmCorpus()
        dir=os.path.dirname(cm.readCorpus)
        self.assertTrue(os.access(dir, os.X_OK & os.R_OK & os.W_OK))
        self.assertTrue(os.path.isdir(dir))
        dir=os.path.dirname(cm.writeCorpus)
        self.assertTrue(os.access(dir, os.X_OK & os.R_OK & os.W_OK))
        self.assertTrue(os.path.isdir(dir))
    def testCorpify(self):
        sm = sourceModel(cm=mitlmCorpus())
        self.assertEquals(sm.corpify(someLexemes), 'print ( 1 + 2 ** 2 ) <ENDMARKER>')
        
class testPythonLexical(unittest.TestCase):
    @classmethod
    def setUpClass(self):
        self.lm = pythonLexical()
    def testLexExpectedLength(self):
        r = self.lm.lex(somePythonCode)
        self.assertEquals(len(r), 9)
    def testLexExpectedFormat(self):
        r = self.lm.lex(somePythonCode)
        self.assertTrue(isinstance(r[0], dict))
        self.assertTrue(isinstance(r[0]['end'], tuple))
        self.assertTrue(isinstance(r[0]['end'][0], int))
        self.assertTrue(isinstance(r[0]['end'][1], int))
        self.assertTrue(isinstance(r[0]['start'], tuple))
        self.assertTrue(isinstance(r[0]['start'][0], int))
        self.assertTrue(isinstance(r[0]['start'][1], int))
        self.assertTrue(isinstance(r[0]['type'], str))
        self.assertTrue(isinstance(r[0]['value'], str))
    def testLexExpectedToken(self):
        r = self.lm.lex(somePythonCode)
        self.assertEquals(r[0]['end'][0], 1)
        self.assertEquals(r[0]['end'][1], 5)
        self.assertEquals(r[0]['start'][0], 1)
        self.assertEquals(r[0]['start'][1], 0)
        self.assertEquals(r[0]['type'], 'NAME')
        self.assertEquals(r[0]['value'], 'print')
    def testStringify1(self):
        self.assertEquals(self.lm.stringify1(someLexemes[0]), 'print')
        self.assertEquals(self.lm.stringify1(someLexemes[8]), '<ENDMARKER>')
        self.assertEquals(self.lm.stringify1(indentLexeme), '<INDENT>')
    @classmethod
    def tearDownClass(self):
        del self.lm
            
class testSourceModelWithFiles(unittest.TestCase):
    @classmethod
    def setUpClass(self):
        self.td = mkdtemp(prefix='ucUnitTest-')
        assert os.access(self.td, os.X_OK & os.R_OK & os.W_OK)
        assert os.path.isdir(self.td)
        readCorpus = os.path.join(self.td, 'ucCorpus') 
        logFilePath = os.path.join(self.td, 'ucLogFile')
        self.uc = unnaturalCode(logFilePath=logFilePath)
        self.cm = mitlmCorpus(readCorpus=readCorpus, writeCorpus=readCorpus, uc=ucGlobal)
        self.lm = pythonLexical()
        self.sm = sourceModel(cm=self.cm, lm=self.lm)
    def testEnvCorpus(self):
        dir=os.path.dirname(self.cm.readCorpus)
        self.assertTrue(os.access(dir, os.X_OK & os.R_OK & os.W_OK))
        self.assertTrue(os.path.isdir(dir))
    def testEnvWriteCorpus(self):
        dir=os.path.dirname(self.cm.writeCorpus)
        self.assertTrue(os.access(dir, os.X_OK & os.R_OK & os.W_OK))
        self.assertTrue(os.path.isdir(dir))
    def testEnvLog(self):
        dir=os.path.dirname(self.uc.logFilePath)
        self.assertTrue(os.access(dir, os.X_OK & os.R_OK & os.W_OK))
        self.assertTrue(os.path.isdir(dir))
    def testEnvSocket(self):
        dir=os.path.dirname(re.sub('^\w+://', '', self.cm.mitlmSocketPath))
        self.assertTrue(os.access(dir, os.X_OK & os.R_OK & os.W_OK))
        self.assertTrue(os.path.isdir(dir))
    def testEnvMitlm(self):
        self.assertTrue(os.access(self.cm.estimateNgramPath, os.X_OK & os.R_OK))
    def testTrainString(self):
        self.sm.trainString(lotsOfPythonCode)
        self.sm.trainString(somePythonCode)
    @classmethod
    def tearDownClass(self):
        shutil.rmtree(self.td)


def tearDownModule():
    global ucGlobal
    del ucGlobal
    
# rwfubmqqoiigevcdefhmidzavjwg
