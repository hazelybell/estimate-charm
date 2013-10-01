#!/usr/bin/env python
import re, runpy, sys, traceback

from UCUtil import *

startMitlm()

name_err_extract = re.compile(r"^name\s+'([^']+)'")

def get_file_line(filename, line):
	try:
		with open(filename) as f:
			return filename.readlines()[line - 1]
	except:
		return None

# NOTE: errors have line info 1-indexed, so we subtract 1
try:
	runpy.run_path(sys.argv[1])
except SyntaxError as se:
	print 'syntax error: {} {}:{}'.format(se.filename, se.lineno - 1,
		se.offset)
except NameError as ne:
	exctype, _, tb = sys.exc_info()
	filename, line, func, text = traceback.extract_tb(tb)[-1]
	line = line - 1
	name = name_err_extract.match(ne.message).group(1)
	# note: text has all leading whitespace stripped, so the column
	# we find for name will not be quite right.
	column = (get_file_line(filename, line) or text).index(name)
	print 'name error: {} {}:{}'.format(filename, line, column)

print [m.__file__ for m in sys.modules.values() if hasattr(m, '__file__')] + [sys.argv[1]]

