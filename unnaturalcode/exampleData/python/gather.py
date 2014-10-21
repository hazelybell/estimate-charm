#!/usr/bin/env python
import sys
import unnaturalcode.modelValidator

source = sys.argv[1]
destination = sys.argv[2]

from unnaturalcode import modelValidator, pythonSource
import tempfile

# Taken from http://stackoverflow.com/questions/3964681/find-all-files-in-directory-with-extension-txt-with-python 2014-10-21
for root, dirs, files in os.walk(source):
  for afile in files:
    if afile.endswith(".py"):
      filepath = os.path.join(root, afile)
      try:
        print("Checking " + fi.path)
        vfile = modelValidator.validationFile(filepath, pythonSource, tempfile.gettempdir())
        testProjectFiles.append(vfile.path)
      except:
        pass
