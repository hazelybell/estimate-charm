zctx = None

@singleton
class unnaturalCode(object):
    def __init__(self):
        global zctx
        assert not zctx
        self.zctx = zmq.Context()
        zctx = self.zctx
        self.forceTrain = toBool(os.getenv("ucForceTrain", "false"))
        self.forceValidate = toBool(os.getenv("ucValidate", "false"))

class sourceModel(object):
    
    def __init__(self, cm=corpusModel(), lm=pythonLexicalModel()):
        self.cm = cm
        self.lm = lm
    
    # Blindly train on a set of files whether or not it compiles...
    def trainFile(self, files):
        files = [files] if isinstance(files, str) else files
        assert isinstance(files, list)
        for fi in files:
            sourceCode = slurp(fi)
            trainString(sourceCode)

    # Corpify a string
    def corpify(self, lexemes):
        return cm.corpify(map(lm.stringify1, inputLexed))
    
    # Train on a source code string
    def trainString(self, sourceCode):
        pass