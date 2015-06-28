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
import math

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
        self.lines = self.lexed[-1].end.line
        self.lineStart = [-1 for i in range(0, self.lines+1)]
        self.lineTokens = [0 for i in range(0, self.lines+1)]
        for i in range(0, len(self.scrubbed)):
          line = self.scrubbed[i].start.line
          self.lineTokens[line] = self.lineTokens[line] + 1
          for j in range(line, 0, -1):
            if self.lineStart[j] == -1:
              self.lineStart[j] = i
            else:
              break
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
        self.mutantFilePath = mutantFilePath
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
          n = len(fi.scrubbed)
          l = fi.lexed[-1].end.line
          if fi.path in self.progress:
            progress = self.progress[fi.path]
            errors = self.errors[fi.path]
            mutations = self.mutations[fi.path]
            charm = self.charm[fi.path]
          else:
            progress = [0 for i in range(1,l+3)]
            progress[0] = None # Line numbers start with 1
            errors = [0 for i in range(1,l+3)]
            errors[0] = None
            charm = [0 for i in range(1,l+3)]
            charm[0] = None
            mutations = 0
          info("Testing " + str(progress) + " " + fi.path)
          delta = float("inf")
          mi = 0
          while (delta > deltamax):
            mi = mi + 1
            mline = (mi % l) + 1
            if fi.lineTokens[mline] > 0:
              merror = mutation(self, fi, mline)
              if merror is not None:
                info(merror)
                break
              runException = fi.runMutant()
              errorLine = None
              filename = None
              func = None
              text = None
              if (runException[0] == None):
                exceptionName = "None"
              else:
                exceptionName = runException[0].__name__
                for location in reversed(runException[2]):
                  if (location[0] == fi.mutantFilePath):
                    filename, errorLine, func, text = location
                    break
              if errorLine == None:
                errorLine = l+1
              if errorLine > l+1: # This can be caused by inserting giant multi-line string literals, in python docstrinsg
                errorLine = l+1
              mutLine = fi.mutatedLocation.start.line
              #info(" ".join(map(str, [fi.path, mutLine, l, fi.mutatedLocation])))
              #info(" ".join(map(str, [filename, errorLine, func, text])))
              #info(runException)
              if (mutLine == errorLine):
                online = True
              else:
                online = False
              errors[errorLine] = errors[errorLine] + 1
              progress[mutLine] = progress[mutLine] + 1
              mutations = mutations + 1
              assert(l>0)
              assert(mutations>0)
              charm[mutLine] = (errors[mutLine]-progress[mutLine])/(float(mutations)/float(l))
              if errorLine <= l:
                charm[errorLine] = (errors[errorLine]-progress[errorLine])/(float(mutations)/float(l))
              delta = 1.0/math.sqrt(float(mutations)/float(l))
              info(" ".join(map(str, [
                  str(mutations) + "/" + str(int(math.ceil(float(l)/(deltamax*deltamax)))),
                  mutLine, errorLine,
                  errors[errorLine],
                  progress[mutLine],
                  charm[mutLine],
                  delta
                ])))
              self.detailsCsv.writerow([
                fi.path, 
                mutLine,
                errorLine,
                errors[errorLine],
                progress[mutLine],
                mutations,
                charm[mutLine],
                delta,
                mutation.__name__, 
                fi.mutatedLocation.type,
                nonWord.sub('', fi.mutatedLocation.value), 
                exceptionName, 
                online,
                filename,
                func])
              self.detailsFile.flush()
          for li in range(1,l):
            self.csv.writerow([
              fi.path,
              li,
              progress[li],
              errors[li],
              charm[li],
              delta
            ])
            
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
            
    def replaceRandom(self, vFile, targetLine=None):
        ls = copy(vFile.scrubbed)
        token = ls[randint(0, len(ls)-1)]
        if targetLine == None:
          pos = randint(0, len(ls)-2)
        else:
          lineStart = vFile.lineStart[targetLine]
          nextLineStart = len(vFile.scrubbed)
          if targetLine < vFile.lines:
            nextLineStart = vFile.lineStart[targetLine+1]
          if (lineStart > nextLineStart):
            pos = randint(lineStart, nextLineStart-1)
          else:
            pos = lineStart
          #print str(targetLine)
          #print repr(ls[pos])
          assert(ls[pos].start.line <= targetLine and targetLine <= ls[pos].end.line)
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
              self.mutations[row[0]] = self.mutations[row[0]] + row[2]
              self.errors[row[0]][row[1]] = row[3]
              self.charm[row[0]][row[1]] = row[4]
          self.csvFile.close()
        except (IOError):
          pass
        self.csvFile = open(self.results + ".new", 'w')
        self.csv = csv.writer(self.csvFile)
        self.csv.writerow([
          "file",
          "line",
          "mutants",
          "errors",
          "charm",
          "delta"
        ])
        self.detailsFile = open(self.details, 'a')
        self.detailsCsv = csv.writer(self.detailsFile)
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
