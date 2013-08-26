import argparse, operator, runpy, sys, traceback


try:
	runpy.run_path(sys.argv[1])
except SyntaxError as se:
	print 'syntax error: {} {}:{}'.format(se.filename, se.lineno, se.offset)
except NameError as ne:
	exctype, _, tb = sys.exc_info()
	where = traceback.extract_tb(tb)[-1]
	print 'name error: {} {}:{}'.format(where[0], where[1], 0)

print [m.__file__ for m in sys.modules.values() if hasattr(m, '__file__')] + [sys.argv[1]]

