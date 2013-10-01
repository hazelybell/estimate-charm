import unittest
from UCUtil import *
import os, os.path, zmq, sys
from lexPythonMQ import *

somePythonCode = "print (1+2**2)"
someLexemes = [{'end': (1, 5), 'start': (1, 0), 'type': 'NAME', 'value': 'print'},
                {'end': (1, 8), 'start': (1, 7), 'type': 'OP', 'value': '('},
                {'end': (1, 9), 'start': (1, 8), 'type': 'NUMBER', 'value': '1'},
                {'end': (1, 10), 'start': (1, 9), 'type': 'OP', 'value': '+'},
                {'end': (1, 11), 'start': (1, 10), 'type': 'NUMBER', 'value': '2'},
                {'end': (1, 13), 'start': (1, 11), 'type': 'OP', 'value': '**'},
                {'end': (1, 14), 'start': (1, 13), 'type': 'NUMBER', 'value': '2'},
                {'end': (1, 15), 'start': (1, 14), 'type': 'OP', 'value': ')'},
                {'end': (2, 0), 'start': (2, 0), 'type': 'ENDMARKER', 'value': ''}]
indentLexeme =  {'end': (3, 8), 'start': (3, 0), 'type': 'INDENT', 'value': '        '}
lotsOfPythonCode = """
def mult(x, y):
    r = 0
    for _ in range(0, x):
        r = r + y

print mul(1, 2)
"""

l = LexPy()
        

class testUCUtil(unittest.TestCase):
    def testToBool(self):
        self.assertFalse(toBool("false"), 'toBool false not false')
        self.assertTrue(toBool("true"), 'toBool true not true')
    def testEnvCorpus(self):
        dir=os.path.dirname(readCorpus)
        self.assertTrue(os.access(dir, os.X_OK & os.R_OK & os.W_OK))
        self.assertTrue(os.path.isdir(dir))
        dir=os.path.dirname(writeCorpus)
        self.assertTrue(os.access(dir, os.X_OK & os.R_OK & os.W_OK))
        self.assertTrue(os.path.isdir(dir))
        dir=os.path.dirname(logFilePath)
        self.assertTrue(os.access(dir, os.X_OK & os.R_OK & os.W_OK))
        self.assertTrue(os.path.isdir(dir))
    def testEnvMitlm(self):
        self.assertTrue(os.access(estimateNgramPath, os.X_OK & os.R_OK))
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
    def testLexExpectedLength(self):
        r = l.lex(somePythonCode)
        self.assertEquals(len(r), 9)
    def testLexExpectedFormat(self):
        r = l.lex(somePythonCode)
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
        r = l.lex(somePythonCode)
        self.assertEquals(r[0]['end'][0], 1)
        self.assertEquals(r[0]['end'][1], 5)
        self.assertEquals(r[0]['start'][0], 1)
        self.assertEquals(r[0]['start'][1], 0)
        self.assertEquals(r[0]['type'], 'NAME')
        self.assertEquals(r[0]['value'], 'print')
        
class testUCUtilWithCorpus(unittest.TestCase):
    @classmethod
    def setUpClass(self):
        print "x"
    @classmethod
    def tearDownClass(self):
        print "y"

        

#hamburgers