import os, sys, token, tokenize, zmq, re
from StringIO import StringIO
from os.path import exists
import os
import json

ws = re.compile('^\s+$')

def toBool(inputString):
    return json.loads(inputString)

def startMitlm():
    assert exists(readCorpus), "No such corpus."
    assert exists(estimateNgramPath), "No such estimate-ngram."
    global mitlmSocketPath
    mitlmSocketPath = "ipc:///tmp/ucSocket-%i" % os.getpid()
    global mitlmPID 
    mitlmPID = os.fork()
    if mitlmPID == 0:
        os.execv(estimateNgramPath, ["-t", readCorpus, "-o", order+1, "-s", "ModKN", "-u", "-live-prob", mitlmSocketPath])
        assert false, "Failed to exec."
    print "Started MITLM as PID %i." % mitlmPID
    global mitlmSocket
    mitlmSocket = zctx.socket(zmq.REQ)
    mitlmSocket.connect(mitlmSocketPath)
    mitlmSocket.send("for ( i =")
    r = float(mitlmSocket.recv().data())
    print "MITLM said %f" % r
    
def corpify1(lexeme):
    if ws.match(str(lexeme['value'])) :
        return '<'+lexeme['type']+'>'
    elif len(lexeme['value']) > 0 :
        return lexeme['value']
    else:
        return '<'+lexeme['type']+'>'
    
    
def corpify(inputLexed):
    return " ".join(map(corpify1, inputLexed))
    

readCorpus = os.getenv("ucCorpus", "/tmp/ucCorpus")
writeCorpus = os.getenv("ucWriteCorpus", readCorpus)
logFilePath = os.getenv("ucLogFile", "/tmp/ucLog-%i" % os.getpid())
#corpusFH = open(writeCorpus, "a")
estimateNgramPath = os.getenv("ESTIMATENGRAM", os.popen('which estimate-ngram').read())
forceTrain = toBool(os.getenv("ucForceTrain", "false"))
forceValidate = toBool(os.getenv("ucValidate", "false"))

zctx = zmq.Context()