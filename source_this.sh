#!/bin/false

# YOU MUST SOURCE THIS FILE.

# Place to find projects (namely, MITLM).
if [ -z "${PROJECT_PREFIX+x}" ]; then
    PROJECT_PREFIX=$HOME
fi

# Set MITLM path.
if [ -z "${MITLM+x}" ]; then
    MITLM=$PROJECT_PREFIX/mitlm
fi

# Set the virtualenv path.
if [ -z "${VENV+x}" ]; then
    VENV=$PWD/venv

fi

# Create the virutalenv if it doesn't exist.
if [ ! -d $VENV ]; then
    virtualenv $VENV
    FRESH_INSTALL=1
fi

# Activate the virtualenv.
source $VENV/bin/activate

# Install everything...
if [ $FRESH_INSTALL ]; then
    pip install -r requirements.txt
    pip install -r test-requirements.txt
    pip install -e .
fi

export ESTIMATENGRAM=$MITLM/estimate-ngram
export LD_LIBRARY_PATH=$MITLM/.libs
export VIRTUALENV_ACTIVATE=$VENV/bin/activate_this.py

if [ -z "${TEST_FILE_LIST+x}" ]; then
    TEST_FILE_LIST=$PWD/example-test-file.txt
fi
export TEST_FILE_LIST

uctest () {
    FAST="True" nose2-2.7 -B --log-capture
}

unset FRESH_INSTALL
