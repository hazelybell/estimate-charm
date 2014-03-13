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

