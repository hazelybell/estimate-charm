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

# Activate the virtualenv.
source $VENV/bin/activate

ESTIMATENGRAM=$MITLM/estimate-ngram
LD_LIBRARY_PATH=$MITLM/.libs
VIRTUALENV_ACTIVATE=$VENV/bin/activate_this.py

if [ -z "${TEST_FILE_LIST+x}" ]; then
    TEST_FILE_LIST=$PWD/example-test-file.txt
fi

uctest () {
    FAST="True" nose2-2.7 -B --log-capture
}
