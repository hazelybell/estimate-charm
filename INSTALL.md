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

# Install UnnaturalCode

```bash
python setup.py develop
```

# Testing

First time:
```bash
test -d venv || virtualenv venv
. venv/bin/activate
pip install -r requirements.txt
nose2-2.7
```

You will need some environment variables set:

```bash
export ESTIMATENGRAM="/usr/local/bin/estimate-ngram"
export LD_LIBRARY_PATH="/usr/local/lib:$LD_LIBRARY_PATH"
```

**ALTERNATIVELY** once the virtualenv is setup, source `source_this.sh`
which will attempt to export _all_ environment variables automatically,
and add `uctest` which will run nose2 `FAST`:

```bash
source source_this.sh
uctest
```


# Running

```bash
export PATH="/path/to/unnaturalcode/unnaturalcode:$PATH"
python setup.py develop
uclearn /usr/lib/python2.7/*.py
uclearn /path/to/some/known-good-python.py
ucwrap /path/to/some/python.py
uccheck some.python.module
```

