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
import os, zmq, signal, os.path, subprocess, fcntl, time
from unnaturalCode import *
from logging import debug, info, warning, error

class mitlmCorpus(object):
    
    def __init__(self, readCorpus=None, writeCorpus=None, estimateNgramPath=None, uc=unnaturalCode(), order=10):
        self.readCorpus = (readCorpus or os.getenv("ucCorpus", "/tmp/ucCorpus"))
        self.writeCorpus = (writeCorpus or os.getenv("ucWriteCorpus", self.readCorpus))
        self.mitlmSocketPath = "ipc://%s/%s-%i-%i" % (os.path.dirname(self.readCorpus), "ucMitlmSocket", os.getpid(), id(self))
        self.estimateNgramPath = (estimateNgramPath or os.getenv("ESTIMATENGRAM", os.popen('which estimate-ngram').read()))
        self.corpusFile = False
        self.mitlmSocket = None
        self.mitlmProc = None
        self.order = order
        self.zctx = uc.zctx
    
    def checkMitlm(self):
        while self.mitlmProc:
            try:
                info(self.mitlmProc.stdout.read())
            except:
                break
    
    def startMitlm(self):
        """Start MITLM estimate-ngram in 0MQ entropy query mode, unless already running."""
        if not self.mitlmSocket == None :
            assert not self.mitlmSocket.closed
            assert self.mitlmProc.poll() == None
            # Already running
            self.checkMitlm()
            return
        assert os.path.exists(self.readCorpus), "No such corpus."
        assert not ws.match(slurp(self.readCorpus)), "Corpus is full of whitespace!"
        assert os.path.exists(self.estimateNgramPath), "No such estimate-ngram."
        self.mitlmProc = subprocess.Popen([self.estimateNgramPath, "-t", self.readCorpus, "-o", str(self.order+1), "-s", "ModKN", "-u", "-live-prob", self.mitlmSocketPath], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        debug("Started MITLM as PID %i." % self.mitlmProc.pid)
        
        fd = self.mitlmProc.stdout.fileno()
        fl = fcntl.fcntl(fd, fcntl.F_GETFL)
        fcntl.fcntl(fd, fcntl.F_SETFL, fl | os.O_NONBLOCK)
        self.checkMitlm()
        self.mitlmSocket = self.zctx.socket(zmq.REQ)
        self.mitlmSocket.connect(self.mitlmSocketPath)
        self.mitlmSocket.send("for ( i =")
        r = float(self.mitlmSocket.recv())
        debug("MITLM said %f" % r)
        self.checkMitlm()
        
    def stopMitlm(self):
        """Stop MITLM estimate-ngram, unless not running."""
        self.checkMitlm()
        if self.mitlmSocket:
            self.mitlmSocket.setsockopt(zmq.LINGER, 0)
            self.mitlmSocket.close()
            assert self.mitlmSocket.closed
            #os.remove(self.mitlmSocketPath)
            self.mitlmSocket = None
        if self.mitlmProc:
            rc = None
            debug("Waiting for MITLM to shut down...")
            while self.mitlmProc and (rc == None):
                self.mitlmProc.terminate()
                time.sleep(0.1)
                rc = self.mitlmProc.poll()
            self.mitlmProc = None
            debug("MITLM exited with status %r" % (rc))
            
    def corpify(self, lexemes):
        """Stringify lexed source: produce space-seperated sequence of lexemes"""
        assert isinstance(lexemes, list)
        assert len(lexemes)
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
            self.corpusFile = None

    def addToCorpus(self, lexemes):
        """Adds a string of lexemes to the corpus"""
        assert isinstance(lexemes, list)
        assert len(lexemes)
        self.openCorpus()
        cl = self.corpify(lexemes)
        #debug(cl)
        assert(len(cl))
        assert (not ws.match(cl)), "Adding blank line to corpus!"
        print(cl, file=self.corpusFile)
        self.corpusFile.flush()
        self.stopMitlm()
    
    def queryCorpus(self, lexemes):
        self.startMitlm()
        qString = self.corpify(lexemes)
        self.mitlmSocket.send(qString)
        r = float(self.mitlmSocket.recv())
        return r
    
    def release(self):
        """Close files and stop MITLM"""
        self.closeCorpus()
        self.stopMitlm()
        
    def __del__(self):
        """I am a destructor, but release should be called explictly."""
        assert not self.mitlmProc, "Destructor called before release()"
        assert not self.mitlmSocket, "Destructor called before release()"
        assert not self.corpusFile, "Destructor called before release()"
        #super(mitlmCorpus, self).__del__()

# rwfubmqqoiigevcdefhmidzavjwg
