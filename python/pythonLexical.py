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
        if lexeme['type'] == 'COMMENT':
            return '<'+lexeme['type']+'>'
        elif ws.match(str(lexeme['value'])) :
            return '<'+lexeme['type']+'>'
        elif len(lexeme['value']) > 0 :
            return lexeme['value']
        else:
            return '<'+lexeme['type']+'>'
    
    def deLex(self, lexemes):
        line = 1
        col = 0
        src = ""
        for l in lexemes:
            for i in range(line, l['start'][0]):
                src += os.linesep
                col = 0
                line += 1
            for i in range(col, l['start'][1]):
                src += " "
                col += 1
            src += l['value']
            col += len(l['value'])
            nls = l['value'].count(os.linesep)
            if (nls > 0):
                line += nls
                col = len(l['value'].splitlines().pop())
        return src
    
    def isntComment(self, lexeme):
        return not (lexeme['type'] == 'COMMENT')
    
    def unComment(self, lexemes):
        return filter(self.isntComment, lexemes)
    
    def scrub(self, lexemes):
        """Clean up python source code removing extra whitespace tokens and comments"""
        ls = self.unComment(lexemes)
        i = 0
        r = []
        for i in range(0, len(ls)):
            if ls[i]['type'] == 'NL':
                continue
            elif ls[i]['type'] == 'NEWLINE' and ls[i+1]['type'] == 'NEWLINE':
                continue
            elif ls[i]['type'] == 'NEWLINE' and ls[i+1]['type'] == 'INDENT':
                continue
            else:
                r.append(ls[i])
        return r
    
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
