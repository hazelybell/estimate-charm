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

from ucUtil import *
from unnaturalCode import *
from logging import debug, info, warning, error

import sys, token, tokenize, zmq;
from cStringIO import StringIO

COMMENT = 53

class pythonLexeme(ucLexeme):
    
    def __new__(cls, *args):
        if isinstance(args[0], ucLexeme):
            return ucLexeme.__new__(cls, *args)
        elif isinstance(args[0], tuple):
            tup = args[0]
            # tup = [type, val, [startrow, col], [endrow, col], line]
            if isinstance(tup[0], int):
              t0 = token.tok_name[tup[0]]
            else:
              t0 = tup[0]
            return ucLexeme.__new__(cls, t0, str(tup[1]), ucPos(tup[2]), ucPos(tup[3]))
        else:
            return ucLexeme.__new__(cls, *args)

    def __str__(self):
        """Stringify a lexeme: produce text describing its value"""
        if self.ltype == 'COMMENT':
            return '<'+self.ltype+'>'
        elif ws.match(str(self.val)) :
            return '<'+self.ltype+'>'
        elif len(self.val) > 0 :
            return self.val
        else:
            return self.type
          
    def comment(self):
        return (self.ltype == 'COMMENT')
      

class pythonSource(ucSource):
    
    def extend(self, arg):
        if isinstance(arg, str):
          super(pythonSource, self).extend(self.lex(arg))
        else:
            for a in arg:
                if isinstance(a, str):
                    assert len(a)>1
                    super(pythonSource, self).extend(self.lex(a))
                else:
                    super(pythonSource, self).extend([a])

    def lex(self, code):
        return [pythonLexeme(tok) for tok in \
            tokenize.generate_tokens(StringIO(code).readline)]
    
    def deLex(self):
        line = 1
        col = 0
        src = ""
        for l in self:
            for i in range(line, l.start.line):
                src += os.linesep
                col = 0
                line += 1
            for i in range(col, l.start.col):
                src += " "
                col += 1
            src += l.val
            col += len(l.val)
            nls = l.val.count(os.linesep)
            if (nls > 0):
                line += nls
                col = len(l.val.splitlines().pop())
        return src
    
    def unCommented(self):
        assert len(self)
        return filter(lambda a: not a.comment(), copy(self))
    
    def scrubbed(self):
        """Clean up python source code removing extra whitespace tokens and comments"""
        ls = self.unCommented()
        assert len(ls)
        i = 0
        r = []
        for i in range(0, len(ls)):
            if ls[i].ltype == 'NL':
                continue
            elif ls[i].ltype == 'NEWLINE' and ls[i+1].ltype == 'NEWLINE':
                continue
            elif ls[i].ltype == 'NEWLINE' and ls[i+1].ltype == 'INDENT':
                continue
            else:
                r.append(ls[i])
        assert len(r)
        return pythonSource(r)

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
