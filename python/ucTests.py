import unittest
from UCUtil import *
from lexPythonMQ import *
import os, os.path, zmq, sys, shutil
from tempfile import *
from ucTestData import *

class testUCUtil(unittest.TestCase):
    def testToBool(self):
        self.assertFalse(toBool("false"), 'toBool false not false')
        self.assertTrue(toBool("true"), 'toBool true not true')
    def testDefaultCorpusEnv(self):
        cm = corpusModel()
        dir=os.path.dirname(cm.readCorpus)
        self.assertTrue(os.access(dir, os.X_OK & os.R_OK & os.W_OK))
        self.assertTrue(os.path.isdir(dir))
        dir=os.path.dirname(cm.writeCorpus)
        self.assertTrue(os.access(dir, os.X_OK & os.R_OK & os.W_OK))
        self.assertTrue(os.path.isdir(dir))
        dir=os.path.dirname(cm.logFilePath)
        self.assertTrue(os.access(dir, os.X_OK & os.R_OK & os.W_OK))
        self.assertTrue(os.path.isdir(dir))
    def testEnvMitlm(self):
        cm = corpusModel()
        self.assertTrue(os.access(cm.estimateNgramPath, os.X_OK & os.R_OK))
    def testEnvBools(self):
        self.assertEquals(type(forceTrain), bool)
        self.assertEquals(type(forceValidate), bool)
    def testZctx(self):
        self.assertEquals(type(zctx), zmq.core.context.Context)
    def testCorpify1(self):
        self.assertEquals(corpify1(someLexemes[0]), 'print')
        self.assertEquals(corpify1(someLexemes[8]), '<ENDMARKER>')
        self.assertEquals(corpify1(indentLexeme), '<INDENT>')
    def testCorpify(self):
        self.assertEquals(corpify(someLexemes), 'print ( 1 + 2 ** 2 ) <ENDMARKER>')
    def testWS(self):
        self.assertTrue(ws.match('        '))
        self.assertTrue(ws.match(indentLexeme['value']))
            
        
class testLexPy(unittest.TestCase):
    @classmethod
    def setUpClass(self):
        self.l = LexPy()
    def testLexExpectedLength(self):
        r = self.l.lex(somePythonCode)
        self.assertEquals(len(r), 9)
    def testLexExpectedFormat(self):
        r = self.l.lex(somePythonCode)
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
        r = self.l.lex(somePythonCode)
        self.assertEquals(r[0]['end'][0], 1)
        self.assertEquals(r[0]['end'][1], 5)
        self.assertEquals(r[0]['start'][0], 1)
        self.assertEquals(r[0]['start'][1], 0)
        self.assertEquals(r[0]['type'], 'NAME')
        self.assertEquals(r[0]['value'], 'print')
    @classmethod
    def tearDownClass(self):
        del self.l
            
class testCorpusModelWithFiles(unittest.TestCase):
    @classmethod
    def setUpClass(self):
        self.td = mkdtemp(prefix='ucUnitTest-')
        assert os.access(self.td, os.X_OK & os.R_OK & os.W_OK)
        assert os.path.isdir(self.td)
        readCorpus = os.path.join(self.td, 'ucCorpus') 
        logFilePath = os.path.join(self.td, 'ucLogFile')
        self.cm = corpusModel(readCorpus=readCorpus, writeCorpus=readCorpus, logFilePath=logFilePath)
    def testEnvCorpus(self):
        dir=os.path.dirname(self.cm.readCorpus)
        self.assertTrue(os.access(dir, os.X_OK & os.R_OK & os.W_OK))
        self.assertTrue(os.path.isdir(dir))
    def testEnvWriteCorpus(self):
        dir=os.path.dirname(self.cm.writeCorpus)
        self.assertTrue(os.access(dir, os.X_OK & os.R_OK & os.W_OK))
        self.assertTrue(os.path.isdir(dir))
    def testEnvLog(self):
        dir=os.path.dirname(self.cm.logFilePath)
        self.assertTrue(os.access(dir, os.X_OK & os.R_OK & os.W_OK))
        self.assertTrue(os.path.isdir(dir))
    def testEnvSocket(self):
        dir=os.path.dirname(re.sub('^\w+://', '', self.cm.mitlmSocketPath))
        self.assertTrue(os.access(dir, os.X_OK & os.R_OK & os.W_OK))
        self.assertTrue(os.path.isdir(dir))
    def testEnvMitlm(self):
        self.assertTrue(os.access(self.cm.estimateNgramPath, os.X_OK & os.R_OK))
    @classmethod
    def tearDownClass(self):
        shutil.rmtree(self.td)

#hamburgers