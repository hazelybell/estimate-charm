#!/usr/bin/python

import sys, token, tokenize, zmq;
from StringIO import StringIO

def err(msg):
	sys.err.write(str(msg) + '\n')


class LexPy(object):
	
	def __init__(self):
		pass

	def lex(code):
		def tup_to_dict(tup):
			# tup = [type, val, [startrow, col], [endrow, col], line]
			return {
				'type': token.tok_name[tup[0]],
				'value': tup[1],
				'start': tup[2],
				'end': tup[3],
			}

		return [tup_to_dict(tok) for tok in \
			tokenize.generate_tokens(StringIO(code).readline)]
		

class LexPyMQ(object):
	def __init__(self, lexer):
		self.lexer = lexer
		self.zctx = zmq.Context()
		self.socket = self.zctx.socket(zmq.REP)

	def run(self):
		self.socket.bind("tcp://lo:32132")

		while True:
			msg = self.socket.recv_json(0)
			# there are definitely new lines in the code
			if not msg.get('python'):
				err('received non-python code')
			code = msg.get('body', '')
			self.socket.send_json(self.lexer.lex(code))

if __name__ == '__main__':
	LexPyMQ(LexPy()).run()
