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

from __future__ import print_function
import os, zmq, signal, os.path
from unnaturalCode import *

class mitlmCorpus(object):
    
    def __init__(self, readCorpus=None, writeCorpus=None, estimateNgramPath=None, uc=unnaturalCode(), order=10):
        self.readCorpus = (readCorpus or os.getenv("ucCorpus", "/tmp/ucCorpus"))
        self.writeCorpus = (writeCorpus or os.getenv("ucWriteCorpus", self.readCorpus))
        self.mitlmSocketPath = "ipc://%s/%s-%i-%i" % (os.path.dirname(self.readCorpus), "ucMitlmSocket", os.getpid(), id(self))
        self.estimateNgramPath = (estimateNgramPath or os.getenv("ESTIMATENGRAM", os.popen('which estimate-ngram').read()))
        self.corpusFile = False
        self.mitlmSocket = False
        self.mitlmPID = 0
        self.order = order
        self.zctx = uc.zctx
    
    def startMitlm(self):
        """Start MITLM estimate-ngram in 0MQ entropy query mode, unless already running."""
        if self.mitlmSocket:
            assert not self.mitlmSocket.closed
            assert self.mitlmPID
            r = os.waitpid(self.mitlmPID, os.WNOHANG)
            assert r == (0, 0)
            # Already running
            return
        assert os.path.exists(self.readCorpus), "No such corpus."
        assert os.path.exists(self.estimateNgramPath), "No such estimate-ngram."
        self.mitlmPID = os.fork()
        if self.mitlmPID == 0:
            os.execv(self.estimateNgramPath, [self.estimateNgramPath, "-t", self.readCorpus, "-o", str(self.order+1), "-s", "ModKN", "-u", "-live-prob", self.mitlmSocketPath])
            assert false, "Failed to exec."
        debug("Started MITLM as PID %i." % self.mitlmPID)
        self.mitlmSocket = self.zctx.socket(zmq.REQ)
        self.mitlmSocket.connect(self.mitlmSocketPath)
        self.mitlmSocket.send("for ( i =")
        r = float(self.mitlmSocket.recv())
        debug("MITLM said %f" % r)
        
    def stopMitlm(self):
        """Stop MITLM estimate-ngram, unless not running."""
        if self.mitlmSocket:
            self.mitlmSocket.setsockopt(zmq.LINGER, 0)
            self.mitlmSocket.close()
            assert self.mitlmSocket.closed
            os.remove(self.mitlmSocketPath)
            self.mitlmSocket = False
        if self.mitlmPID > 0:
            r = os.waitpid(self.mitlmPID, os.WNOHANG)
            if r == (0, 0):
                os.kill(self.mitlmPID, signal.HUP)
                r = os.waitpid(self.mitlmPID, 0)
            self.mitlmPID = 0
    
    def corpify(self, lexemes):
        """Stringify lexed source: produce space-seperated sequence of lexemes"""
        assert isinstance(lexemes, list)
        return " ".join(lexemes)
    
    def openCorpus(self):
        """Opens the corpus (if necessary)"""
        if (self.corpusFile):
            assert not self.corpusFile.closed
            return
        self.corpusFile = open(self.writeCorpus, 'a')

    def closeCorpus(self):
        """Closes the corpus (if necessary)"""
        if (self.corpusFile):
            self.corpusFile.close()
            assert self.corpusFile.closed

    def addToCorpus(self, lexemes):
        """Adds a string of lexemes to the corpus"""
        self.openCorpus()
        print(self.corpify(lexemes), file=self.corpusFile)
        self.corpusFile.flush()
        self.stopMitlm
    
    def queryCorpus(self, lexemes):
        self.startMitlm()
        qString = self.corpify(lexemes)
        self.mitlmSocket.send(qString)
        r = float(self.mitlmSocket.recv())
        return r
    
    def release(self):
        """Close files and stop MITLM"""
        self.closeCorpus
        self.stopMitlm
        
    def __del__(self):
        """I am a destructor, but release should be called explictly."""
        self.release

# rwfubmqqoiigevcdefhmidzavjwg
