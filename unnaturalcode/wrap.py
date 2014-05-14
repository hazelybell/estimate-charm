#!/usr/bin/env python
#    Copyright 2013 Joshua Charles Campbell, Alex Wilson
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

def main():
    import re
    import runpy
    import sys
    import traceback
    from copy import copy

    from logging import debug, info, warning, error
    
    savedSysPath = deepcopy(sys.path)
    
    name_err_extract = re.compile(r"^name\s+'([^']+)'")
    
    def get_file_line(filename, line):
    	try:
    		with open(filename) as f:
    			return filename.readlines()[line - 1]
    	except:
    		return None
    # TODO: run this fn in a seperate proc using os.fork
    def runit():
      program = sys.argv[1]
      del sys.argv[1]
      try:
          r = runpy.run_path(program)
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
      return ((None, "None", [(path, None, None, None)]))
      
      e = runit()
      
      if e[0] == None:
        return
      
      sys.path = savedSysPath;
      
      from ucUser import pyUser
      ucpy = pyUser()
      
      worst = ucpy.sm.worstWindows(pythonSource(somePythonCodeFromProject))
      
      from __future__ import print_function
      print(repr(worst[0]), file=sys.stderr)


if __name__ == '__main__':
    main()
