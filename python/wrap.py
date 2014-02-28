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
import re, runpy, sys, traceback

from logging import debug, info, warning, error

print sys.path

name_err_extract = re.compile(r"^name\s+'([^']+)'")

def get_file_line(filename, line):
	try:
		with open(filename) as f:
			return filename.readlines()[line - 1]
	except:
		return None

try:
	runpy.run_path(sys.argv[1])
except SyntaxError as se:
	print 'syntax error: {} {}:{}'.format(se.filename, se.lineno - 1,
		se.offset)
except NameError as ne:
	exctype, _, tb = sys.exc_info()
	filename, line, func, text = traceback.extract_tb(tb)[-1]
	name = name_err_extract.match(ne.message).group(1)
	# note: text has all leading whitespace stripped, so the column
	# we find for name will not be quite right.
	column = (get_file_line(filename, line) or text).index(name)
	print 'name error: {} {}:{}'.format(filename, line, column)

print [m.__file__ for m in sys.modules.values() if hasattr(m, '__file__')] + [sys.argv[1]]

