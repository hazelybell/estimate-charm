#!/usr/bin/perl
use strict;
use Term::ANSIColor;
use ZeroMQ qw/:all/;
use Getopt::Long;

my $SERVER_PORT = 28673;

$|=1;

my $client = 1;
my $ctxt;
my $socket;

warn color("blue"),"Enabling ZeroMQ",color("reset");

$ctxt = ZeroMQ::Context->new();    
$socket = ZeroMQ::Socket->new( $ctxt, ZMQ_REQ );
$socket->connect( "tcp://127.0.0.1:32132" ); # java parser

warn color("blue"),"Java Lexer Connected",color("reset");

my @input = <>;
$socket->send( join("",@input) );
my $msg = $socket->recv();
my $out = $msg->data();
print $out,$/;
$socket->close();
$ctxt->term();
