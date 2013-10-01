#!/usr/bin/python
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

import sys, token, tokenize, zmq;
from StringIO import StringIO
from ucUtil import *

class pythonLexical(object):
    
    def __init__(self):
        pass

    def lex(self, code):
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
    
    # Stringify a lexeme: produce text describing its value
    def stringify1(self, lexeme):
        if ws.match(str(lexeme['value'])) :
            return '<'+lexeme['type']+'>'
        elif len(lexeme['value']) > 0 :
            return lexeme['value']
        else:
            return '<'+lexeme['type']+'>'
        
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
			assert msg.get('python'), 'received non-python code'
			code = msg.get('body', '')
			self.socket.send_json(list(tokenize.generate_tokens(StringIO(code).readline)))

if __name__ == '__main__':
	LexPyMQ(LexPy()).run()
