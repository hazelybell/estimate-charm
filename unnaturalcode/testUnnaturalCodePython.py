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

"""Typically ran with FAST="True" nose2-2.7 -B --log-capture

Other things to consider:

export ESTIMATENGRAM="/home/joshua/projects/mitlm/.libs/estimate-ngram" 
export TEST_FILE_LIST=/home/wz/ucPython/all
export LD_LIBRARY_PATH="/home/joshua/projects/mitlm/.libs"
source ~/ucPython/bin/activate
export VIRTUALENV_ACTIVATE=/home/joshua/ucPython/bin/activate_this.py
"""

import unittest
from logging import debug, info, warning, error

from ucUtil import *
from unnaturalCode import *
from sourceModel import *
from pythonSource import *
from mitlmCorpus import *
from modelValidator import *

import os, os.path, zmq, sys, shutil, token, gc
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
        self.assertTrue(isinstance(ucGlobal.zctx, zmq.backend.Context))
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
        self.assertEquals(sm.corpify(pythonSource(someLexemes)), 'print ( 1 + 2 ** 2 ) <ENDMARKER>')
        
class testPythonLexical(unittest.TestCase):
    @classmethod
    def setUpClass(self):
        pass
    def testLexExpectedLength(self):
        r = pythonSource(somePythonCode)
        self.assertEquals(len(r), 9)
    def testLexExpectedFormat(self):
        r = pythonSource(somePythonCode)
        self.assertTrue(isinstance(r, ucSource))
        self.assertTrue(isinstance(r[0], ucLexeme))
        self.assertTrue(isinstance(r[0].end, tuple))
        self.assertTrue(isinstance(r[0].end.l, int))
        self.assertTrue(isinstance(r[0].end.c, int))
        self.assertTrue(isinstance(r[0].start, tuple))
        self.assertTrue(isinstance(r[0].start[0], int))
        self.assertTrue(isinstance(r[0].start[1], int))
        self.assertTrue(isinstance(r[0].type, str))
        self.assertTrue(isinstance(r[0].value, str))
    def testLexExpectedToken(self):
        r = pythonSource(somePythonCode)
        self.assertEquals(r[0].end[0], 1)
        self.assertEquals(r[0].end[1], 5)
        self.assertEquals(r[0].start[0], 1)
        self.assertEquals(r[0].start[1], 0)
        self.assertEquals(r[0].type, 'NAME')
        self.assertEquals(r[0].value, 'print')
    def testColumns(self):
        r = pythonSource(lotsOfPythonCode)
        self.assertEquals(r[1].columns(), 3) # this should be the "def" token
        self.assertEquals(r[0].lines(), 0)
    def testDeleteOne(self):
        r = pythonSource(lotsOfPythonCode)
        x = r.pop(1)
        self.assertEquals(x.value, 'def')
        r.check()
        r.pop(6)
        r.check()
        r.pop(1)
        r.check()
        r.pop(1)
        r.check()
        r.pop(1)
        r.check()
        r.pop(1)
        r.check()
        r.pop(1)
        r.check()
        r.pop(1)
        r.check()
        r.pop(1)
        r.check()
        r.pop(1)
        r.check()
        r.pop(1)
        r.check()
        r.pop(1)
        r.check()
    def testDeleteOneTwo(self):
        r = pythonSource(codeWithDeleteFailure)
        x = r.pop(2)
        r.check()
        r.pop(2)
        r.check()
        r.pop(2)
        r.check()
    def testStringify1(self):
        self.assertEquals(str(pythonSource(someLexemes)[0]), 'print')
        self.assertEquals(str(pythonSource(someLexemes)[8]), '<ENDMARKER>')
        self.assertEquals(str(pythonLexeme.fromDict(indentLexeme)), '<INDENT>')
    def testLexDeLex(self):
        self.assertEquals(lotsOfPythonCode, (pythonSource(lotsOfPythonCode).deLex()))
        self.assertEquals(codeWithComments, (pythonSource(codeWithComments).deLex()))
    def testComment(self):
        self.assertTrue(pythonLexeme.fromTuple((COMMENT, '# wevie stunder', (1, 0), (1, 0))).comment())
        self.assertFalse(pythonLexeme.fromTuple((token.INDENT, '    ', (2, 0), (2, 0))).comment())
    def testExclusiveEnd(self):
        r = pythonSource("1+2")
        self.assertTrue(r[0].start.c + 1 == r[0].end.c) # First token is r[0]
        self.assertTrue(r[2].start.c + 1 == r[2].end.c)
    def testPoppin(self):
        r = pythonSource("1+2")
        r.pop(0)
        r.pop(0)
        r.pop(0)
    def testPopBug(self):
        # AssertionError: [('OP', '=', (76, 44), (76, 45)), ('NEWLINE', '\n', (76, 3), (76, 4))]
        r = pythonSource("a=1+2\na")
        r.pop(4)
        r.check()
        r = pythonSource("a=1+2\na")
        r.pop(5)
        r.check()
        r = pythonSource("a=1+2\n\n")
        r.pop(4)
        r.check()
        r = pythonSource("a=1\n\n")
        r.pop(2)
        r.check()
        r = pythonSource("for _ in range(0, x):\n\ta=1\n\n")
        x = r.pop(14)
        r.check()
        self.assertEquals(x.value, '1')
        r = pythonSource("for _ in range(0, x):\n\ta=1\n\n")
        x = r.pop(9)
        r.check()
        self.assertEquals(x.value, ':')
    @classmethod
    def tearDownClass(self):
        pass
            
class testSourceModelWithFiles(unittest.TestCase):
    @classmethod
    def setUpClass(self):
        self.td = mkdtemp(prefix='ucTest-')
        assert os.access(self.td, os.X_OK & os.R_OK & os.W_OK)
        assert os.path.isdir(self.td)
        readCorpus = os.path.join(self.td, 'ucCorpus') 
        logFilePath = os.path.join(self.td, 'ucLogFile')
        self.uc = unnaturalCode(logFilePath=logFilePath)
        self.cm = mitlmCorpus(readCorpus=readCorpus, writeCorpus=readCorpus, uc=ucGlobal)
        self.sm = sourceModel(cm=self.cm, language=pythonSource)
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
    def testTrainFile(self):
        self.sm.trainFile(testProject1File)
    @unittest.skipIf(os.getenv("FAST", False), "Skipping slow tests...")
    def testTrainProject(self):
        self.sm.trainFile(testProjectFiles)
    @classmethod
    def tearDownClass(self):
        self.sm.release()
        shutil.rmtree(self.td)

@unittest.skipIf(os.getenv("FAST", False), "Skipping slow tests...")
class testTrainedSourceModel(unittest.TestCase):
    @classmethod
    def setUpClass(self):
        self.td = mkdtemp(prefix='ucTest-')
        assert os.access(self.td, os.X_OK & os.R_OK & os.W_OK)
        assert os.path.isdir(self.td)
        readCorpus = os.path.join(self.td, 'ucCorpus') 
        logFilePath = os.path.join(self.td, 'ucLogFile')
        self.uc = unnaturalCode(logFilePath=logFilePath)
        self.cm = mitlmCorpus(readCorpus=readCorpus, writeCorpus=readCorpus, uc=ucGlobal)
        self.lm = pythonSource
        self.sm = sourceModel(cm=self.cm, language=pythonSource)
        self.sm.trainFile(testProjectFiles)
    def testQueryCorpus(self):
        ls = self.sm.stringifyAll(ucSource(someLexemes))
        r = self.cm.queryCorpus(self.sm.stringifyAll(ucSource(someLexemes)))
        self.assertGreater(r, 0.1)
        self.assertLess(r, 70.0)
    def testQueryCorpusString(self):
        r = self.sm.queryString(somePythonCodeFromProject)
        self.assertLess(r, 70.0)
        self.assertGreater(r, 0.1)
    def testWindowedQuery(self):
        r = self.sm.windowedQuery(pythonSource(somePythonCodeFromProject))
        debug(type(r))
        debug(type(r[0]))
        debug(type(r[0][0]))
        self.assertLess(r[0][1], 70.0)
        self.assertGreater(r[0][1], 0.1)
    def testWorst(self):
        r = self.sm.worstWindows(pythonSource(somePythonCodeFromProject))
        for i in range(0, len(r)-2):
            self.assertTrue(r[i][1] >= r[i+1][1])
    @classmethod
    def tearDownClass(self):
        self.sm.release()
        shutil.rmtree(self.td)

@unittest.skipIf(os.getenv("FAST", False), "Skipping slow tests...")
class testValidatorLong(unittest.TestCase):
    @classmethod
    def setUpClass(self):
        self.td = mkdtemp(prefix='ucTest-')
        assert os.access(self.td, os.X_OK & os.R_OK & os.W_OK)
        assert os.path.isdir(self.td)
    def testValidatorFiles(self):
        v = modelValidation(source=testProjectFiles, language=pythonSource, corpus=mitlmCorpus, resultsDir=self.td)
        v.validate(mutation=INSERT, n=10)
        v.validate(mutation=REPLACE, n=10)
        v.validate(mutation=DELETE, n=10)
        # TODO: assert csvs
        v.release()
    @classmethod
    def tearDownClass(self):
        shutil.rmtree(self.td)

class testValidator(unittest.TestCase):
    @classmethod
    def setUpClass(self):
        self.td = mkdtemp(prefix='ucTest-')
        assert os.access(self.td, os.X_OK & os.R_OK & os.W_OK)
        assert os.path.isdir(self.td)
    def testValidatorFile(self):
        v = modelValidation(source=[testProject1File], language=pythonSource, corpus=mitlmCorpus, resultsDir=self.td)
        v.genCorpus()
        v.validate(mutation=DELETE, n=10)
        v.validate(mutation=INSERT, n=10)
        v.validate(mutation=REPLACE, n=10)
        # TODO: assert csvs
        v.release()
    @classmethod
    def tearDownClass(self):
        shutil.rmtree(self.td)
    
        
def tearDownModule():
    global ucGlobal
    del ucGlobal
    # ~~~ valgrind for python ~~~
    gc.collect()
    for i in gc.get_objects():
        if isinstance(i, (mitlmCorpus, modelValidation)):
            i.__del__()

# rwfubmqqoiigevcdefhmidzavjwg
