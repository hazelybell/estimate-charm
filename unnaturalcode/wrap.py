#!/usr/bin/env python
#    Copyright 2013, 2014 Joshua Charles Campbell, Alex Wilson
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

def main(mode="wrap"):
    import re
    import runpy
    import sys
    import traceback
    from copy import deepcopy
    import logging
    import os
    import imputil
    from logging import debug, info, warning, error
    #logging.getLogger().setLevel(logging.DEBUG)
    
    savedSysPath = deepcopy(sys.path)
    program = sys.argv[1]
    del sys.argv[1]

    # TODO: run this fn in a seperate proc using os.fork
    def runit():
      sys.path.insert(0, os.getcwd())
      if not mode == "check":
        sys.path.insert(0, os.path.dirname(program))
      virtualEnvActivate = os.getenv("VIRTUALENV_ACTIVATE", None)
      if not virtualEnvActivate is None:
        execfile(virtualEnvActivate, dict(__file__=virtualEnvActivate))
      try:
          if mode == "check":
            r = runpy.run_module(program)
          else:
            r = runpy.run_path(program, run_name="__main__")
      except SyntaxError as se:
          ei = sys.exc_info();
          traceback.print_exc();
          eip = (ei[0], str(ei[1]), traceback.extract_tb(ei[2]))
          try:
            eip[2].append(ei[1][1])
          except IndexError:
            eip[2].append((se.filename, se.lineno, None, None))
          return (eip)
      except Exception as e:
          ei = sys.exc_info();
          traceback.print_exc();
          eip = (ei[0], str(ei[1]), traceback.extract_tb(ei[2]))
          return (eip)
      return ((None, "None", [(program, None, None, None)]))
      
    e = runit()
    
    if e[0] == None:
      return
    
    source = open(e[2][-1][0]).read()
    
    sys.path = savedSysPath;
    
    from unnaturalcode.ucUser import pyUser
    ucpy = pyUser()
    
    worst = ucpy.sm.worstWindows(ucpy.lm(source))
    print("Suggest checking around %s:%d:%d" % (program, worst[0][0][10][2][0], worst[0][0][10][2][1]), file=sys.stderr)
    print("Near:\n" + ucpy.lm(worst[0][0]).settle().deLex())
    
    ucpy.release()
    
def check():
  main(mode="check")

if __name__ == '__main__':
    main()