#!/bin/bash

export LD_LIBRARY_PATH="/home/joshua/projects/mitlm/.libs"
export JAVAC_WRAPPER_ESTIMATENGRAM="/home/joshua/projects/ngram-complete-dist/errors/mitlm.sh"
export JAVAC_WRAPPER_LOGFILE="/home/joshua/projects/ngrams-errors/asetests/log"
export JAVAC_WRAPPER_CORPUS="/home/joshua/projects/ngrams-errors/asetests/corpus-4.0.0"
export JAVAC_WRAPPER_VALIDATE="$1 $2"

testlucene="`mktemp -d /tmp/lucene.XXXX`"

cd $testlucene && \
rsync -aP /home/joshua/projects/lucene-4.0.0-ok/ ./ && \
ant clean

while ant compile -lib /usr/share/java/ivy.jar
do      ant clean
done