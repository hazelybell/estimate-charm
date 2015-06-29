#!/usr/bin/python
#    Copyright 2013, 2014, 2015 Joshua Charles Campbell, Alex Wilson
#
#    This file is part of EstimateCharm.
#    
#    EstimateCharm is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    EstimateCharm is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with EstimateCharm.  If not, see <http://www.gnu.org/licenses/>.

from estimatecharm.unnaturalCode import *
from logging import debug, info, warning, error

from estimatecharm import flexibleTokenize

import sys, token;
try:
  from cStringIO import StringIO
except ImportError:
  from io import StringIO

COMMENT = 53

ws = re.compile('\s')

class pythonLexeme(ucLexeme):
    
    @classmethod
    def stringify(cls, t, v):
        """
        Stringify a lexeme: produce a string describing it.
        In the case of comments, strings, indents, dedents, and newlines, and
        the endmarker, a string with '<CATEGORY-NAME>' is returned.  Else, its
        actual text is returned.
        """
        if t == 'COMMENT':
            return '<'+t+'>'
        # Josh though this would be a good idea for some strange reason:
        elif len(v) > 20 :
            return '<'+t+'>'
        elif ws.match(str(v)) :
            return '<'+t+'>'
        elif t == 'STRING' :
            return '<'+t+'>'
        elif len(v) > 0 :
            return v
        else:
            # This covers for <DEDENT> case, and also, probably some other
            # special cases...
            return '<' + t + '>'
    
    @classmethod
    def fromTuple(cls, tup):
        if isinstance(tup[0], int):
            t0 = token.tok_name[tup[0]]
        else:
            t0 = tup[0]
        return tuple.__new__(cls, (t0, str(tup[1]), ucPos(tup[2]), ucPos(tup[3]), cls.stringify(t0, str(tup[1]))))
          
    def comment(self):
        return (self.ltype == 'COMMENT')
      

class pythonSource(ucSource):
    
    def lex(self, code, mid_line=False):
        tokGen = flexibleTokenize.generate_tokens(StringIO(code).readline,
            mid_line)
        return [pythonLexeme.fromTuple(t) for t in tokGen]
    
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
        ls = copy(self)
        assert len(ls)
        i = 0
        r = []
        for i in range(0, len(ls)):
            if ls[i].comment():
                continue
            elif ls[i].ltype == 'NL':
                continue
            elif ls[i].ltype == 'NEWLINE' and i < len(ls)-1 and ls[i+1].ltype == 'NEWLINE':
                continue
            elif ls[i].ltype == 'NEWLINE' and i < len(ls)-1 and ls[i+1].ltype == 'INDENT':
                continue
            else:
                r.append(ls[i])
        assert len(r)
        return pythonSource(r)