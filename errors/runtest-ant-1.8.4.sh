#!/bin/bash

export LD_LIBRARY_PATH="/home/joshua/projects/mitlm/.libs"
export JAVAC_WRAPPER_ESTIMATENGRAM="/home/joshua/projects/ngram-complete-dist/errors/mitlm.sh"
export JAVAC_WRAPPER_LOGFILE="/home/joshua/projects/ngrams-errors/asetests/log-ant-1.7.0"
export JAVAC_WRAPPER_CORPUS="/home/joshua/projects/ngrams-errors/asetests/corpus-ant-1.7.0"
export JAVAC_WRAPPER_VALIDATE="$1 $2"

testlucene="`mktemp -d /tmp/ant.XXXX`"

cd $testlucene && \
rsync -aP /home/joshua/projects/apache-ant-1.8.4/ ./ && \
ant clean

while ant -lib /usr/share/java/ivy.jar
do      ant clean
done
