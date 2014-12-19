# Makefile UnnaturalGrams with test framework integration.
#
#    Copyright 2006, 2007, 2008, 2013, 2014 Joshua Charles Campbell
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
SOURCES=ugapi.c db.c hsuglass.c vocabulary.c attribute.c hgvector.c
COPPER_INPUT_FILES=$(SOURCES)
CFLAGS=-g -O0 -Wall -Wextra -Werror -Wfatal-errors -Wno-error=unused-parameter \
       -llmdb -fplan9-extensions

default : ugapi.o

copper.make : copper.pl
	./copper.pl makefile $(COPPER_INPUT_FILES) >$@

clean : copper_clean
	- rm -f *.o copper.make

check : copper_test_all

include copper.make
