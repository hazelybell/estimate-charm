# About

UnnaturalCode is a system with the purpose of augmenting the compiler's own
syntax error location strategies. It is designed to assist the developer in
locating syntax errors in their software. For more information, please consult
the current draft of the [UnnaturalCode
paper](http://webdocs.cs.ualberta.ca/~joshua2/syntax.pdf) (on submission).

UnnaturalCode should be considered proof-of-concept quality software. The
primary author of UnnaturalCode can be reached at <unnaturalcode@orezpraw.com>.

# Installation

## Prerequisites

### Install packaged dependencies

Ubuntu/Debian:

```bash
sudo apt-get install libzmq-dev
```

Fedora:

```bash
sudo yum install zeromq3-devel
```

### Get [pyzmq](https://github.com/zeromq/pyzmq):

```bash
virtualenv dev     # create a new, empty virtualenv
. dev/bin/activate # enable it, sandboxing us from the system-installed python libraries
pip install pyzmq  # install pyzmq into our virtualenv
```

### Get modified mitlm:

```bash
git clone \
    https://github.com/orezpraw/MIT-Language-Modeling-Toolkit.git mitlm
cd mitlm
./autogen.sh
make
export ESTIMATENGRAM="`pwd`/.libs/estimate-ngram"
export LD_LIBRARY_PATH="`pwd`/.libs"
```

# Running

```bash
. dev/bin/activate
ESTIMATENGRAM="/path/to/estimate-ngram"
LD_LIBRARY_PATH="/path/to/mitlm/libs"
run_some_command
```

# Licensing

Assume that UnnaturalCode is licensed under the AGPL3+ unless otherwise
specified. The antlr/ directory is licensed under GPL2+, see that directory for
more information.

Copyright 2010,2011,2012  
Abram Hindle, Prem Devanbu, Earl T. Barr, Daryl Posnett

Copyright 2012, 2013  
Joshua Charles Campbell, Abram Hindle, Alex Wilson

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
