#!/usr/bin/python

import tokenize;
import zmq;

context = zmq.Context()
socket = context.socket(zmq.REP)
socket.bind("tcp://lo:32132")

while True:
    # Wait for next request from client
    message = socket.recv()