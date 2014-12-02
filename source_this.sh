#!/bin/false

# YOU MUST SOURCE THIS FILE.

# It will set and export required environment variables.  You may set them
# explicitly before sourcing this file.
#
# ESTIMATENGRAM
#   Location of the custom MITLM's ESTIMATENGRAM
# LD_LIBRARY_PATH
#   Must be augmented to account for MITLM
# VIRTUALENV_ACTIVATE
#   Location of `activate_this.py` file for the virutalenv of the project to
#   test on (and NOT UnnaturalCode itself!)
# TEST_FILE_LIST (optional)
#   Location of the file list (one file per line) that contains all of the
#   files to test.
#

# Set MITLM path.
if [ -z "${MITLM+x}" ]; then
    MITLM=$HOME/mitlm
fi

# Set the virtualenv path.
if [ -z "${VENV+x}" ]; then
    VENV=$PWD/venv

fi

# Create the virtualenv if it doesn't exist.
if [ ! -d $VENV ]; then
    virtualenv $VENV
    FRESH_INSTALL=1
fi

# Activate the virtualenv.
source $VENV/bin/activate

# Install everything...
if [ $FRESH_INSTALL ]; then
    pip install -e .
    pip install -r requirements.txt
    pip install -r test-requirements.txt
fi

export ESTIMATENGRAM=$MITLM/estimate-ngram
export LD_LIBRARY_PATH=$MITLM/.libs
export VIRTUALENV_ACTIVATE=$VENV/bin/activate_this.py

# Export any set TEST_FILE_LIST. Otherwise, the tests can just use the
# bundled corpus.
if [ ! -z "${TEST_FILE_LIST+x}" ]; then
    export TEST_FILE_LIST
fi

uctest () {
    FAST="True" py.test
}

unset FRESH_INSTALL
