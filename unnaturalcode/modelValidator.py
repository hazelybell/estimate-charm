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
from pythonSource import *
from mitlmCorpus import *
from sourceModel import *

from logging import debug, info, warning, error
from random import randint
from os import path

import csv
import runpy
import sys
from shutil import copyfile

virtualEnvActivate = os.getenv("VIRTUALENV_ACTIVATE", None)

if not virtualEnvActivate is None:
    execfile(virtualEnvActivate, dict(__file__=virtualEnvActivate))

print sys.path

class validationFile(object):
    
    def __init__(self, path, language):
        self.path = path
        self.lm = language
        self.f = open(path)
        self.original = self.f.read()
        self.lexed = self.lm(self.original)
        self.scrubbed = self.lexed.scrubbed()
        self.f.close()
        self.mutatedLexemes = None
        self.mutatedLocation = None
        info("Running %s", self.path)
        runpy.run_path(self.path)
    
    def mutate(self, lexemes, location):
        assert isinstance(lexemes, ucSource)
        self.mutatedLexemes = lexemes
        self.mutatedLocation = location
        
class modelValidation(object):
    
    def addValidationFile(self, files):
          """Add a file for validation..."""
          files = [files] if isinstance(files, str) else files
          assert isinstance(files, list)
          for fi in files:
            self.validFiles.append(validationFile(fi, self.lm))
    
    def genCorpus(self):
          """Create the corpus from the known-good file list."""
          for fi in self.validFiles:
            self.sm.trainLexemes(fi.scrubbed)
    
    def validate(self, mutation, n):
        """Run main validation loop."""
        trr = 0 # total reciprocal rank
        tr = 0 # total rank
        ttn = 0 # total in top n
        assert n > 0
        for fi in self.validFiles:
          assert isinstance(fi, validationFile)
          info("Testing " + fi.path)
          for i in range(0, n):
            mutation(self, fi)
            worst = self.sm.worstWindows(fi.mutatedLexemes)
            for i in range(0, len(worst)):
                #debug(str(worst[i][0][0].start) + " " + str(fi.mutatedLocation.start) + " " + str(worst[i][1]))
                if worst[i][0][0].start < fi.mutatedLocation.start and worst[i][0][-1].end > fi.mutatedLocation.end:
                    #debug(">>>> Rank %i (%s)" % (i, fi.path))
                    self.csv.writerow([fi.path, mutation.__name__, i, worst[i][1]])
                    self.csvFile.flush()
                    trr += 1/float(i+1)
                    tr += float(i)
                    if i < 5:
                        ttn += 1
                    break
        mrr = trr/float(len(self.validFiles) * n)
        mr = tr/float(len(self.validFiles) * n)
        mtn = ttn/float(len(self.validFiles) * n)
        info("MRR %f MR %f M5+ %f" % (mrr, mr, mtn))
            
    def deleteRandom(self, vFile):
        """Delete a random token from a file."""
        ls = copy(vFile.scrubbed)
        token = ls.pop(randint(0, len(ls)-1))
        vFile.mutate(ls, token)
            
    def insertRandom(self, vFile):
        ls = copy(vFile.scrubbed)
        token = ls[randint(0, len(ls))]
        pos = randint(0, len(ls))
        ls.insert(pos, token)
        token = ls[pos]
        vFile.mutate(ls, token)
            
    def replaceRandom(self, vFile):
        ls = copy(vFile.scrubbed)
        token = ls[randint(0, len(ls))]
        pos = randint(0, len(ls))
        ls.pop(pos)
        ls.insert(pos, token)
        token = ls[pos]
        vFile.mutate(ls, token)
      
    def __init__(self, source=None, language=pythonSource, resultsDir=None, corpus=mitlmCorpus):
        self.resultsDir = ((resultsDir or os.getenv("ucResultsDir", None)) or mkdtemp(prefix='ucValidation-'))
        if isinstance(source, str):
            raise NotImplementedError
        elif isinstance(source, list):
            self.validFileNames = source
        else:
            raise TypeError("Constructor arguments!")

        assert os.access(self.resultsDir, os.X_OK & os.R_OK & os.W_OK)
        self.csvPath = path.join(self.resultsDir, 'results.csv')
        self.csvFile = open(self.csvPath, 'a')
        self.csv = csv.writer(self.csvFile)
        
        self.corpusPath = os.path.join(self.resultsDir, 'validationCorpus')
        self.cm = corpus(readCorpus=self.corpusPath, writeCorpus=self.corpusPath, order=10)
        self.lm = language
        self.sm = sourceModel(cm=self.cm, language=self.lm)
        self.validFiles = list()
        self.addValidationFile(self.validFileNames)
        self.genCorpus()

    def release(self):
        """Close files and stop MITLM"""
        self.cm.release()
        self.cm = None
        
    def __del__(self):
        """I am a destructor, but release should be called explictly."""
        assert not self.cm, "Destructor called before release()"

DELETE = modelValidation.deleteRandom
INSERT = modelValidation.insertRandom
REPLACE = modelValidation.replaceRandom

