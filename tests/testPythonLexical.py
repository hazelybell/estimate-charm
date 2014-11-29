"""

"""

import unittest
from logging import debug, info, warning, error

from unnaturalcode.ucUtil import *
from unnaturalcode.unnaturalCode import *
from unnaturalcode.sourceModel import *
from unnaturalcode.pythonSource import *
from unnaturalcode.mitlmCorpus import *
from unnaturalcode.modelValidator import *

import os, os.path, zmq, sys, shutil, token, gc
from tempfile import *

from unnaturalcode.ucTestData import *

# Helper. Given a list of lexemes, gives the stringified version
# of the ith lexeme.
strlex = lambda lexemes, i: str(pythonSource(lexemes)[i])
# Helper. Same as strlex, but takes a single dict representing a lexeme.
strlexd = lambda lexeme: str(pythonLexeme.fromDict(lexeme))

ucGlobal = None

logging.getLogger(__name__).setLevel(logging.DEBUG)


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
    def testLexMidlineModeSingleLine(self):
        r_normal = pythonSource(somePythonCode)
        r_mid_line = pythonSource(somePythonCode, mid_line=True)
        # This small one line example has no indent or anything.
        self.assertEquals(len(r_normal), 9)
        self.assertEquals(len(r_mid_line), 8)
        self.assertEquals(r_normal[-1].type, 'ENDMARKER')
        self.assertNotEquals(r_mid_line[-1].type, 'ENDMARKER')
    def testLexMidlineModeExcerpt(self):
        r_normal = pythonSource(incompletePythonCode)
        r_mid_line = pythonSource(incompletePythonCode, mid_line=True)
        self.assertEquals(len(r_normal), 13)
        self.assertEquals(len(r_mid_line), 11)
        self.assertEquals(r_normal[-1].type, 'ENDMARKER')
        self.assertEquals(r_normal[-2].type, 'DEDENT')
        self.assertEquals(r_mid_line[-1].value, 'ran')
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
    def testStringifyStandard(self):
        self.assertEquals(str(pythonSource(someLexemes)[0]), 'print')
        self.assertEquals(str(pythonSource(someLexemes)[8]), '<ENDMARKER>')
        self.assertEquals(str(pythonLexeme.fromDict(indentLexeme)), '<INDENT>')
    def testStringifyLegacyBehaviour(self):
        tooLong = {'type': 'NAME', 'start': (0, 0), 'end': (0, 45),
                   'value': 'iAmADickBagIdentifierWithMoreThan32Characters'}
        comment = {'type': 'COMMENT', 'start': (0, 0), 'end': (0, 35),
                   'value': '#!/bin/dd if=/dev/zero of=/dev/sda1'}
        string = {'type': 'STRING', 'start': (0, 0), 'end': (0, 35),
                  'value': 'u"Hello, World!"'}
        self.assertEquals(strlexd(tooLong), '<NAME>')
        self.assertEquals(strlexd(comment), '<COMMENT>')
        self.assertEquals(strlexd(string), '<STRING>')
    def testStringifyDedent(self):
        self.assertEquals(strlex([dedentLexeme], 0), '<DEDENT>')
        self.assertEquals(str(pythonLexeme.fromDict(dedentLexeme)), '<DEDENT>')
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

