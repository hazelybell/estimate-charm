# Installation

## Prerequisites

### Install packaged dependencies

Ubuntu/Debian:

```bash
sudo apt-get install libzmq-dev automake autoconf gfortran python-virtualenv
```

Fedora:

```bash
sudo yum install automake autoconf gcc-gfortran python-virtualenv
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

# Testing

```bash
test -d venv || virtualenv venv
. venv/bin/activate
python setup.py nosetests
```

# Running

```bash
test -d venv || virtualenv venv
. venv/bin/activate
python setup.py develop
ucwrap /path/to/some/python.py
```
