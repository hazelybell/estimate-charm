#!/usr/bin/python
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

from unnaturalcode.ucUtil import *
from unnaturalcode.unnaturalCode import *
from unnaturalcode.pythonSource import *
from unnaturalcode.sourceModel import *

from logging import debug, info, warning, error
import logging
from random import randint
from os import path
import argparse

import csv
import runpy
import sys, traceback
from shutil import copyfile
from tempfile import mkstemp, mkdtemp
import os, re

from multiprocessing import Process, Queue
try:
  from Queue import Empty
except ImportError:
  from queue import Empty
from unnaturalcode import flexibleTokenize

import pdb

virtualEnvActivate = os.getenv("VIRTUALENV_ACTIVATE", None)

nonWord = re.compile('\\W+')
beginsWithWhitespace = re.compile('^\\w')
numeric = re.compile('[0-9]')
punct = re.compile('[~!@#$%^%&*(){}<>.,;\\[\\]`/\\\=\\-+]')
funny = re.compile(flexibleTokenize.Funny)
name = re.compile(flexibleTokenize.Name)

class HaltingError(Exception):
  def __init__(self, value):
    self.value = value
  def __str__(self):
    return repr(self.value)

def runFile(q,path):
    if not virtualEnvActivate is None:
      if sys.version_info >= (3,0):
        exec(compile(open(virtualEnvActivate, "rb").read(), virtualEnvActivate, 'exec'), dict(__file__=virtualEnvActivate))
      else:
        execfile(virtualEnvActivate, dict(__file__=virtualEnvActivate))
    try:
        runpy.run_path(path)
    except SyntaxError as se:
        ei = sys.exc_info();
        eip = (ei[0], str(ei[1]), traceback.extract_tb(ei[2]))
        try:
          eip[2].append(ei[1][1])
        except IndexError:
          eip[2].append((se.filename, se.lineno, None, None))
        q.put(eip)
        return
    except Exception as e:
        ei = sys.exc_info();
        info("run_path exception:", exc_info=ei)
        eip = (ei[0], str(ei[1]), traceback.extract_tb(ei[2]))
        q.put(eip)
        return
    q.put((None, "None", [(path, None, None, None)]))
    
class charmFile(object):
    
    def __init__(self, path, language, tempDir):
        self.path = path
        self.lm = language
        self.f = open(path)
        self.original = self.f.read()
        self.lexed = self.lm(self.original)
        self.scrubbed = self.lexed.scrubbed()
        self.f.close()
        self.mutatedLexemes = None
        self.mutatedLocation = None
        self.tempDir = tempDir
        r = self.run(path)
        info("Ran %s, got %s" % (self.path, r[1]))
        if (r[0] != None):
          raise Exception("Couldn't run file: %s because %s" % (self.path, r[1]))
        #runpy.run_path(self.path)
    
    def run(self, path):
        q = Queue()
        p = Process(target=runFile, args=(q,path,))
        p.start()
        try:
          r = q.get(True, 10)
        except Empty as e:
          r = (HaltingError, "Didn't halt.", [(path, None, None, None)])
        p.terminate()
        p.join()
        assert not p.is_alive()
        #assert r[2][-1][2] != "_get_code_from_file" # This seems to be legit
        return r

    
    def mutate(self, lexemes, location):
        assert isinstance(lexemes, ucSource)
        self.mutatedLexemes = self.lm(lexemes.deLex())
        self.mutatedLocation = location
        
    def runMutant(self):
        (mutantFileHandle, mutantFilePath) = mkstemp(suffix=".py", prefix="mutant", dir=self.tempDir)
        mutantFile = os.fdopen(mutantFileHandle, "w")
        mutantFile.write(self.mutatedLexemes.deLex())
        mutantFile.close()
        r = self.run(mutantFilePath)
        os.remove(mutantFilePath)
        return r
        
class estimateCharm(object):
    
    def addCharmFile(self, files):
          """Add a file for validation..."""
          files = [files] if isinstance(files, str) else files
          assert isinstance(files, list)
          for fi in files:
            vfi = charmFile(fi, self.lm, self.tempDir)
            if len(vfi.lexed) > 1:
              self.charmFiles.append(vfi)
    
    def estimate(self, mutation, deltamax):
        """Run main estimation loop."""
        for fi in self.charmFiles:
          assert isinstance(fi, charmFile)
          if fi.path in self.progress:
            progress = self.progress[fi.path]
          else:
            progress = 0
          info("Testing " + str(progress) + " " + fi.path)
          while (delta > deltamax):
            merror = mutation(self, fi)
            if merror is not None:
              info(merror)
              break
            runException = fi.runMutant()
            if (runException[0] == None):
              exceptionName = "None"
            else:
              exceptionName = runException[0].__name__
            filename, line, func, text = runException[2][-1]
            if (fi.mutatedLocation.start.line == line):
              online = True
            else:
              online = False
            worst = self.sm.worstWindows(fi.mutatedLexemes)
            for j in range(0, len(worst)):
                #debug(str(worst[i][0][0].start) + " " + str(fi.mutatedLocation.start) + " " + str(worst[i][1]))
                if worst[j][0][0].start <= fi.mutatedLocation.start and worst[j][0][-1].end >= fi.mutatedLocation.end:
                    #debug(">>>> Rank %i (%s)" % (i, fi.path))
                    break
            info(" ".join(map(str, [mutation.__name__, j, fi.mutatedLocation.start.line, exceptionName, line])))
            if j >= len(worst):
              error(repr(worst))
              error(repr(fi.mutatedLocation))
              assert False
            self.csv.writerow([
              fi.path, 
              mutation.__name__, 
              j, 
              worst[j][1], 
              fi.mutatedLocation.type,
              fi.mutatedLocation.start.line,
              nonWord.sub('', fi.mutatedLocation.value), 
              exceptionName, 
              online,
              filename,
              line,
              func,
              worst[j][0][0].start.line])
            self.csvFile.flush()
            trr += 1/float(i+1)
            tr += float(i)
            if i < 5:
                ttn += 1
        mrr = trr/float(len(self.charmFiles) * n)
        mr = tr/float(len(self.charmFiles) * n)
        mtn = ttn/float(len(self.charmFiles) * n)
        info("MRR %f MR %f M5+ %f" % (mrr, mr, mtn))
            
    def deleteRandom(self, vFile):
        """Delete a random token from a file."""
        ls = copy(vFile.scrubbed)
        token = ls.pop(randint(0, len(ls)-1))
        if token.type == 'ENDMARKER':
          return self.deleteRandom(vFile)
        vFile.mutate(ls, token)
        return None
            
    def insertRandom(self, vFile):
        ls = copy(vFile.scrubbed)
        token = ls[randint(0, len(ls)-1)]
        pos = randint(0, len(ls)-1)
        inserted = ls.insert(pos, token)
        if inserted[0].type == 'ENDMARKER':
          return self.insertRandom(vFile)
        vFile.mutate(ls, inserted[0])
        return None
            
    def replaceRandom(self, vFile):
        ls = copy(vFile.scrubbed)
        token = ls[randint(0, len(ls)-1)]
        pos = randint(0, len(ls)-2)
        oldToken = ls.pop(pos)
        if oldToken.type == 'ENDMARKER':
          return self.replaceRandom(vFile)
        inserted = ls.insert(pos, token)
        if inserted[0].type == 'ENDMARKER':
          return self.replaceRandom(vFile)
        vFile.mutate(ls, inserted[0])
        return None
        
    def dedentRandom(self, vFile):
        s = copy(vFile.original)
        lines = s.splitlines(True);
        while True:
          line = randint(0, len(lines)-1)
          if beginsWithWhitespace.match(lines[line]):
            lines[line][0] = ''
            break
        vFile.mutatedLexemes = vFile.lm("".join(lines))
        vFile.mutatedLocation = pythonLexeme.fromTuple((token.INDENT, ' ', (line+1, 0), (line+1, 0)))
        return None
        
    def indentRandom(self, vFile):
        s = copy(vFile.original)
        lines = s.splitlines(True);
        line = randint(0, len(lines)-1)
        if beginsWithWhitespace.match(lines[line]):
          lines[line] = lines[line][0] + lines[line]
        else:
          lines[line] = " " + lines[line]
        vFile.mutatedLexemes = vFile.lm("".join(lines))
        vFile.mutatedLocation = pythonLexeme.fromTuple((token.INDENT, ' ', (line+1, 0), (line+1, 0)))
        return None
    
    def punctRandom(self, vFile):
        s = copy(vFile.original)
        charPos = randint(1, len(s)-1)
        linesbefore = s[:charPos].splitlines(True)
        line = len(linesbefore)
        lineChar = len(linesbefore[-1])
        c = s[charPos:charPos+1]
        if (funny.match(c)):
          new = s[:charPos] + s[charPos+1:]
          vFile.mutatedLexemes = vFile.lm(new)
          vFile.mutatedLocation = pythonLexeme.fromTuple((token.OP, c, (line, lineChar), (line, lineChar)))
          return None
        else:
          return self.punctRandom(vFile)
    
    #def keyRandom(self, vFile):
        #s = copy(vFile.original)
        
    def nameRandom(self, vFile):
      return self.deleteWordRandom(vFile)

    def insertWordRandom(self, vFile):
        s = copy(vFile.original)
        while True:
          char = s[randint(1, len(s)-1)]
          charPos = randint(1, len(s)-1)
          linesbefore = s[:charPos].splitlines(True)
          line = len(linesbefore)
          lineChar = len(linesbefore[-1])
          c = s[charPos:charPos+1]
          if (name.match(char)):
            break
        new = s[:charPos] + char + s[charPos:]
        vFile.mutatedLexemes = vFile.lm(new)
        vFile.mutatedLocation = pythonLexeme.fromTuple((token.OP, c, (line, lineChar), (line, lineChar)))
        return None

    def deleteWordRandom(self, vFile):
        s = copy(vFile.original)
        while True:
          charPos = randint(1, len(s)-1)
          linesbefore = s[:charPos].splitlines(True)
          line = len(linesbefore)
          lineChar = len(linesbefore[-1])
          c = s[charPos:charPos+1]
          if (name.match(c)):
            break
        new = s[:charPos] + s[charPos+1:]
        vFile.mutatedLexemes = vFile.lm(new)
        vFile.mutatedLocation = pythonLexeme.fromTuple((token.OP, c, (line, lineChar), (line, lineChar)))
        return None
        
    def insertPunctRandom(self, vFile):
        s = copy(vFile.original)
        if not punct.search(s):
          return "No punctuation"
        while (True):
          char = s[randint(1, len(s)-1)]
          if (punct.match(char)):
            break
        charPos = randint(1, len(s)-1)
        linesbefore = s[:charPos].splitlines(True)
        line = len(linesbefore)
        lineChar = len(linesbefore[-1])
        c = s[charPos:charPos+1]
        new = s[:charPos] + char + s[charPos:]
        vFile.mutatedLexemes = vFile.lm(new)
        vFile.mutatedLocation = pythonLexeme.fromTuple((token.OP, c, (line, lineChar), (line, lineChar)))
        return None

    def deleteNumRandom(self, vFile):
        s = copy(vFile.original)
        if not numeric.search(s):
          return "No numbers"
        positions = [x.start() for x in numeric.finditer(s)]
        while True:
          if (len(positions) == 1):
            charPos = positions[0]
          else:
            charPos = positions[randint(1, len(positions)-1)]
          linesbefore = s[:charPos].splitlines(True)
          line = len(linesbefore)
          lineChar = len(linesbefore[-1])
          c = s[charPos:charPos+1]
          if (numeric.match(c)):
            break
        new = s[:charPos] + s[charPos+1:]
        vFile.mutatedLexemes = vFile.lm(new)
        vFile.mutatedLocation = pythonLexeme.fromTuple((token.OP, c, (line, lineChar), (line, lineChar)))
        return None

    def insertNumRandom(self, vFile):
        s = copy(vFile.original)
        char = str(randint(0, 9))
        charPos = randint(1, len(s)-1)
        linesbefore = s[:charPos].splitlines(True)
        line = len(linesbefore)
        lineChar = len(linesbefore[-1])
        c = s[charPos:charPos+1]
        new = s[:charPos] + char + s[charPos:]
        vFile.mutatedLexemes = vFile.lm(new)
        vFile.mutatedLocation = pythonLexeme.fromTuple((token.OP, c, (line, lineChar), (line, lineChar)))
        return None

    def deletePunctRandom(self, vFile):
        s = copy(vFile.original)
        if not punct.search(s):
          return "No punctuation"
        while True:
          charPos = randint(1, len(s)-1)
          linesbefore = s[:charPos].splitlines(True)
          line = len(linesbefore)
          lineChar = len(linesbefore[-1])
          c = s[charPos:charPos+1]
          if (punct.match(c)):
            break
        new = s[:charPos] + s[charPos+1:]
        vFile.mutatedLexemes = vFile.lm(new)
        vFile.mutatedLocation = pythonLexeme.fromTuple((token.OP, c, (line, lineChar), (line, lineChar)))
        return None

    def colonRandom(self, vFile):
        s = copy(vFile.original)
        while True:
          charPos = randint(1, len(s)-1)
          linesbefore = s[:charPos].splitlines(True)
          line = len(linesbefore)
          lineChar = len(linesbefore[-1])
          c = s[charPos:charPos+1]
          if (c == ':'):
            break
        new = s[:charPos] + s[charPos+1:]
        vFile.mutatedLexemes = vFile.lm(new)
        vFile.mutatedLocation = pythonLexeme.fromTuple((token.OP, c, (line, lineChar), (line, lineChar)))
        return None
      
    def __init__(self, source=None,
                 language=pythonSource,
                 results=None,
                 corpus=None,
                 details=None,
                 activate=None,
                 tempDir="."):
        if isinstance(source, str):
            raise NotImplementedError
        elif isinstance(source, list):
            self.charmFileNames = source
        else:
            raise TypeError("Constructor arguments!")
        self.notReleased = True
        self.progress = dict()
        self.results = results
        self.details = details
        self.tempDir = tempDir
        try:
          self.csvFile = open(self.results, 'r')
          self.csv = csv.reader(self.csvFile)
          for row in self.csv:
              self.progress[row[0]][row[1]] = row[2]
          self.csvFile.close()
        except (IOError):
          pass
        self.csvFile = open(self.results + ".new", 'w')
        self.csv = csv.writer(self.csvFile)
        self.csv.writerow([
          "file",
          "line",
          "datapoints"
        ])
        self.lm = language
        self.charmFiles = list()
        self.addCharmFile(self.charmFileNames)

    def release(self):
        self.notReleased = False
        """Any cleanup goes here..."""
        
    def __del__(self):
        """I am a destructor, but release should be called explictly."""
        assert not self.notReleased, "Destructor called before release()"

DELETE = estimateCharm.deleteRandom
INSERT = estimateCharm.insertRandom
REPLACE = estimateCharm.replaceRandom
PUNCTUATION = estimateCharm.punctRandom
NAMELIKE = estimateCharm.nameRandom
COLON = estimateCharm.colonRandom
DELETEWORDCHAR = estimateCharm.deleteWordRandom
INSERTWORDCHAR = estimateCharm.insertWordRandom
DELETENUMCHAR = estimateCharm.deleteNumRandom
INSERTNUMCHAR = estimateCharm.insertNumRandom
DELETEPUNCTCHAR = estimateCharm.deletePunctRandom
INSERTPUNCTCHAR = estimateCharm.insertPunctRandom
DELETESPACE = estimateCharm.dedentRandom
INSERTSPACE = estimateCharm.indentRandom

def main():
        logging.getLogger().setLevel(logging.DEBUG)
        parser=argparse.ArgumentParser(description="Estimates charm for Python source code.")
        parser.add_argument("input_file", help="Python source file to estimate charm for.", nargs="+")
        parser.add_argument("-o", "--results-file", help="File to store results in.", default="charm.csv")
        parser.add_argument("-d", "--details-file", help="File to store extra detailed results in.", default=None)
        parser.add_argument("-a", "--activate", help="VirtualEnv activate.py to run before input files (if any)", default=None)
        parser.add_argument("-e", "--maximum-error", help="Sets the maximum allowed error (the minimum precision) of the results", default=0.1, type=float)
        args = parser.parse_args()
        v = estimateCharm(source=args.input_file, 
                          language=pythonSource,
                          results=args.results_file,
                          details=args.details_file,
                          activate=args.activate
                         )
        v.estimate(REPLACE, args.maximum_error)
        v.release()

if __name__ == '__main__':
    main()
