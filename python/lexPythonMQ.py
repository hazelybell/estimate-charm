#!/usr/bin/python

import re, sys, tokenize, zmq;
from StringIO import StringIO

def err(msg):
	sys.err.write(str(msg) + '\n')
	

class LexPyMQ(object):
	def __init__(self):
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
			self.socket.send_json(list(tokenize.generate_tokens(StringIO(code).readline)))

if __name__ == '__main__':
	LexPyMQ().run()
