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

import os

class mitlmCorpus(object):
    
    def __init__(self, readCorpus=None, writeCorpus=None, logFilePath=None, estimateNgramPath=None):
        self.readCorpus = (readCorpus or os.getenv("ucCorpus", "/tmp/ucCorpus"))
        self.writeCorpus = (writeCorpus or os.getenv("ucWriteCorpus", self.readCorpus))
        self.logFilePath = (logFilePath or os.getenv("ucLogFile", "/tmp/ucLog-%i" % os.getpid()))
        self.mitlmSocketPath = "ipc://%s-%i-%i" % (os.path.dirname(self.logFilePath), os.getpid(), id(self))
        self.estimateNgramPath = (estimateNgramPath or os.getenv("ESTIMATENGRAM", os.popen('which estimate-ngram').read()))
    
    def startMitlm(self):
        assert exists(self.readCorpus), "No such corpus."
        assert exists(self.estimateNgramPath), "No such estimate-ngram."
        self.mitlmPID = os.fork()
        if self.mitlmPID == 0:
            os.execv(self.estimateNgramPath, ["-t", self.readCorpus, "-o", order+1, "-s", "ModKN", "-u", "-live-prob", self.mitlmSocketPath])
            assert false, "Failed to exec."
        print "Started MITLM as PID %i." % self.mitlmPID
        self.mitlmSocket = zctx.socket(zmq.REQ)
        self.mitlmSocket.connect(mitlmSocketPath)
        self.mitlmSocket.send("for ( i =")
        r = float(self.mitlmSocket.recv().data())
        print "MITLM said %f" % r
    
    # Stringify lexed source: produce space-seperated sequence of lexemes
    def corpify(self, lexemes):
        assert isinstance(lexemes, list)
        return " ".join(lexemes)

