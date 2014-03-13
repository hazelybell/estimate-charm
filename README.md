# About

UnnaturalCode is a system with the purpose of augmenting the compiler's own
syntax error location strategies. It is designed to assist the developer in
locating syntax errors in their software. For more information, please consult
the the [UnnaturalCode
paper](http://webdocs.cs.ualberta.ca/~joshua2/syntax.pdf) (preprint).

* [About the Authors](AUTHORS.md)

UnnaturalCode should be considered proof-of-concept quality software. The
primary author of UnnaturalCode can be reached at <unnaturalcode@orezpraw.com>.

# Installation

## Prerequisites

### Install packaged dependencies

Ubuntu/Debian:

```bash
sudo apt-get install python-zmq libzmq-dev \
    automake autoconf gfortran python-nose
```

Fedora:

```bash
sudo yum install python-zmq automake autoconf gcc-gfortran python-nose
# the version of zeromq3-devel on Fedora 19+ does not include zmq.hpp.
# grab it directly from upstream and drop it in for now
sudo wget https://raw.github.com/zeromq/cppzmq/master/zmq.hpp \
    -O /usr/include/zmq.hpp
```

### Get/install modified mitlm:

```bash
git clone \
    https://github.com/orezpraw/MIT-Language-Modeling-Toolkit.git mitlm
cd mitlm
./autogen.sh
make
sudo make install
sudo ldconfig
```

# Running

```bash
cd python
# Ubuntu
FAST=1 nose2-2.7 -B --log-capture
# Fedora
nosetests
```

# Licensing

Assume that UnnaturalCode is licensed under the AGPL3+ unless otherwise
specified.

&copy; 2010-2012 Abram Hindle, Prem Devanbu, Earl T. Barr, Daryl Posnett

&copy; 2012-2014 Joshua Charles Campbell, Abram Hindle, Alex Wilson

UnnaturalCode is free software: you can redistribute it and/or modify it under
the terms of the GNU Affero General Public License as published by the Free
Software Foundation, either version 3 of the License, or (at your option) any
later version.

UnnaturalCode is distributed in the hope that it will be useful, but WITHOUT
ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
FOR A PARTICULAR PURPOSE.  See the GNU Affero General Public License for more
details.

You should have received a copy of the GNU Affero General Public License along
with UnnaturalCode.  If not, see <http://www.gnu.org/licenses/>.
