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

from __future__ import print_function
import os, zmq, signal, os.path, subprocess, fcntl, time
import errno
from unnaturalcode.unnaturalCode import *
from logging import debug, info, warning, error, getLogger
from multiprocessing import Process
from functools import wraps

allWhitespace = re.compile('^\s+$')

ucParanoid = os.getenv("PARANOID", False)

mitlmLogger = getLogger('MITLM')

CROSS_ENTROPY_PREFIX = 'x'
PREDICTION_PREFIX = 'p'



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
                msg = self.mitlmProc.stdout.readline().rstrip('\n')
                if not allWhitespace.match(msg):
                  mitlmLogger.info()
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
        assert not allWhitespace.match(slurp(self.readCorpus)), "Corpus is full of whitespace!"
        assert os.path.exists(self.estimateNgramPath), "No such estimate-ngram."
        self.mitlmProc = subprocess.Popen([self.estimateNgramPath,
            "-t", self.readCorpus,
            "-o", str(self.order),
            "-s", "ModKN",
            "-u",
            "-live-prob", self.mitlmSocketPath], stdout=subprocess.PIPE)
        debug("Started MITLM as PID %i." % self.mitlmProc.pid)

        fd = self.mitlmProc.stdout.fileno()
        fl = fcntl.fcntl(fd, fcntl.F_GETFL)
        fcntl.fcntl(fd, fcntl.F_SETFL, fl | os.O_NONBLOCK)

        # Test the ZMQ connection.
        time.sleep(1)
        self.checkMitlm()
        self.mitlmSocket = self.zctx.socket(zmq.REQ)
        self.mitlmSocket.connect(self.mitlmSocketPath)
        self.checkMitlm()
        self.sendEntropyRequest(['for', '(', 'i', '='])
        self.checkMitlm()
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
            chill_rm(normalize_path(self.mitlmSocketPath))
            self.mitlmSocket = None
            self.mitlmSocketPath = None
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
        assert (not allWhitespace.match(cl)), "Adding blank line to corpus!"
        print(cl, file=self.corpusFile)
        self.corpusFile.flush()
        self.stopMitlm()

    def _corpified(wrappedMethod):
        "Decorator. Automatically deals with lexemes for the wrapped method."
        @wraps(wrappedMethod)
        def method(self, lexemes, *args, **kwargs):
            qString = self.corpify(lexemes)
            return wrappedMethod(self, qString, *args, **kwargs)
        return method

    def _waitForZMQResponse(self):
        assert self.mitlmSocket
        while True:
          self.checkMitlm()
          try:
            self.mitlmSocket.poll(timeout=1000)
            return self.mitlmSocket.recv(flags=zmq.NOBLOCK)
          except zmq.ZMQError:
              pass

    def queryCorpus(self, request):
        self.startMitlm()
        self.sendEntropyRequest(request)
        r = float(self._waitForZMQResponse())
        if r >= 70.0:
          warning("Infinity: %s" % qString)
          self.checkMitlm()
          assert False
        return r

    def predictCorpus(self, lexemes):
        self.startMitlm()
        self.sendPredictionRequest(lexemes)
        return self.parsePredictionResult(self._waitForZMQResponse(),
                remove_prefix=len(lexemes))


    @_corpified
    def sendEntropyRequest(self, request):
        # Coerce into bytes, if required.
        return self._send(CROSS_ENTROPY_PREFIX + request)

    @_corpified
    def sendPredictionRequest(self, request):
        return self._send(PREDICTION_PREFIX + request)

    def _send(self, string):
        "Sends a string to zmq. Ensures MITLM is initialized."
        assert self.mitlmSocket
        if isinstance(string, unicode):
            string = string.encode('utf-8')
        return self.mitlmSocket.send(string)

    @staticmethod
    def parsePredictionResult(resultString, remove_prefix):
        lines = resultString.split('\n')

        def split_tail(text):
            return text.split()[remove_prefix:]

        def cleanLine(line):
            components = line.split('\t', 1)
            assert len(components) == 2
            entropy_str, text = components
            return float(entropy_str), split_tail(text)

        return [cleanLine(line) for line in lines if line.strip() != ""]


    def release(self):
        """Close files and stop MITLM"""
        self.closeCorpus()
        self.stopMitlm()

    def __del__(self):
        """I am a destructor, but release should be called explictly."""
        assert not self.mitlmProc, "Destructor called before release()"
        assert not self.mitlmSocket, "Destructor called before release()"
        assert not self.corpusFile, "Destructor called before release()"

def chill_rm(filename):
    """
    rm, but silently ignore errors if the given file does not exist. 
    """
    try:
        os.remove(filename)
    except OSError as error:
        # Ignore the error if the file does not exist.
        if error.errno == errno.ENOENT:
            pass
        else:
            raise error

def normalize_path(path):
    """
    Returns a path without a dangling ipc:// in front of it.

    >>> path1 = 'ipc:///home/ucuser/.unnaturalCode/socket'
    >>> path2 =       '/home/ucuser/.unnaturalCode/socket'
    >>> normalize_path(path1) == normalize_path(path2)
    True
    """

    if path.startswith('ipc://'):
        _head, _sep, tail = path.partition('ipc://')
        return tail
    return path

