# Makefile for the Copper framework distribution and an example makefile.
# This file is a part of the Copper framework.
# Copyright 2006-2008 Joshua Charles Campbell.

# The Copper framework is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 3
# of the License, or (at your option) any later version.

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# The output of this program includes substantial portions that
# are preprocessed (copied) from text in this program due to the
# nature of this program.  Therefore, this output is subject to the same
# license as this program.
# See http://www.gnu.org/licenses/gpl-faq.html#GPLOutput for
# more information.

# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.

COPPER_INPUT_FILES = testexamples.c

default : copper.o

copper.make : copper.pl
	./copper.pl makefile testexamples.c >$@

clean : copper_clean
	- rm -f testexamples.o copper.make

check : copper_test_all

include copper.make
