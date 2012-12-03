#!/usr/bin/perl
use strict;

$\ = $/;
use IPC::Open3;
use Symbol;
use ZeroMQ qw/:all/;

my $real_javac = $ENV{JAVAC_WRAPPER_REAL_JAVAC} ? $ENV{JAVAC_WRAPPER_REAL_JAVAC} : qx{which javac};
chomp $real_javac;

my @inputfiles = ();

open LOGFILE, '>>', $ENV{JAVAC_WRAPPER_LOGFILE} ? $ENV{JAVAC_WRAPPER_LOGFILE} : "/tmp/javac-logfile" or die;
open TOKFILE, '>>', $ENV{JAVAC_WRAPPER_ADDCORPUS} ? $ENV{JAVAC_WRAPPER_ADDCORPUS} : "/tmp/javac-tokfile" or die;
my $corpus = $ENV{JAVAC_WRAPPER_CORPUS} ? $ENV{JAVAC_WRAPPER_CORPUS} : "/tmp/javac-tokfile";
my $estimateNgram = $ENV{JAVAC_WRAPPER_ESTIMATENGRAM} ? $ENV{JAVAC_WRAPPER_ESTIMATENGRAM} : qx{which estimate-ngram};

my @JAVAC_INPUTFILES_LISTS = grep(m/^@/, @ARGV);
my @ARGV_NO_LISTS = grep(!m/^@|\.java/i, @ARGV);
my $order = 3;

for my $list (@JAVAC_INPUTFILES_LISTS) {
  $list =~ s/^@//;
  chomp $list;
  open LIST, '<', $list or die;
    while (<LIST>) {
      chomp;
      push @inputfiles, $_;
    }
  close LIST;
}
@inputfiles = grep(m/\.java/, @inputfiles, @ARGV);
for (@inputfiles) {
  print LOGFILE;
}

my $status;
my $main_compile_status;
my @files_mentioned;
my @possible_bad_files;

sub attempt_compile {
  print LOGFILE join(' ', @_);
  my $ccout = gensym;
  my $pid = open3("<&STDIN", $ccout, $ccout, $real_javac, @_) or die $?;
  my $compile_error = 0;

  while (<$ccout>) {
    chomp;
    print;
    if (m/\.java/i) {
      print LOGFILE "javac said: " . $_;
      my ($file) = ($_ =~ m/(\S+\.java):/i);
      print LOGFILE "Possible error location: $file";
      push @files_mentioned, $file;
      $compile_error++;
    }
  }

  waitpid($pid, 0);
  $status = $? >> 8;
  my $signal = $? & 0xFF;
  if ($status) {
    $compile_error++;
  }
  return !$compile_error;  
}



my ($lmout, $lmin, $lmpid);

sub startMITLM {
  die "No corpus: $corpus" unless -e $corpus;
  my @run = ('-t', $corpus, '-o', $order, '-s', 'KN', '-live-prob');
  print "Corpus ok. MITLM starting: $estimateNgram " . join(" ", @run);
  $lmpid = open3($lmin, $lmout, $lmout, $estimateNgram, @run) or print $?;
  print "Started MITLM as pid $lmpid";
  while(my $line = <$lmout>) {
      chomp($line);
      print "[mitlm] $line";
      last if $line =~ /Live Entropy Ready/;
      #IO::Handle::flush($child_in);
  }
  print "MITLM ready";  
}

  sub javaCommentHack {
      my ($text) = @_;
      my @a = $text=~ m/(\*\/|\/\*)/igm;
      my %h = ();
      foreach my $a (@a) {
	  $h{$a}++;
      }
      if ($h{"/*"} < $h{"*/"}) {
	  $text =~ s#^.*\*/##;
      }
      return $text;
  };

my $ctxt = ZeroMQ::Context->new();    
my $socket = ZeroMQ::Socket->new( $ctxt, ZMQ_REQ );
$socket->connect( "tcp://127.0.0.1:32132" ); # java lexer
# 
#   sub lex {
#       my @in = @_;
#       # note it says java here
#       my $in =  javaCommentHack( join("", @in));
#       $in =~ s/\s+/ /g;
# #       $in .= $/;
#       print STDOUT "-comments +code +java$/" . $in;
#       $socket->send( "-comments +code +java$/" . $in);
#       my $msg = $socket->recv();
#       my $out = $msg->data();
#       print "OUT OUT OUT " . length($out);
#       $out =~ s/ +([\r\n] )*/<SPACE>/g;
#       $out =~ s/[\r\n]+/ /g;
#       # by clearing up excessive whitespace we seem to lex better
#       $out =~ s/  */ /g;
# #       $out =~ s/<SPACE>/\n/g;
#       #$out =~ s/; /;\n/g;
# 
#       return $out;
#   };

    sub lex {
        my @in = @_;
        # note it says java here
        $socket->send( "-comments +code +java$/" . javaCommentHack(join("", @in)  ));
        my $msg = $socket->recv();
        my $out = $msg->data();
#         $out =~ s/[\r\n]/ /g;
        # by clearing up excessive whitespace we seem to lex better
#         $out =~ s/  */ /g;
        $out =~ s/ +([\r\n] )*/<SPACE>/g;
        #$out =~ s/; /;\n/g;
        return $out;
    };



 sub lexAfile {
     my ($file) = @_;
     open INPUTFILE, '<', $file or die;
     my $slurped = '';
     while (<INPUTFILE>) {
#       s/\n//gs;
# 	$lexed .= lex($_);
	$slurped .= $_;
     }
     close INPUTFILE;
     return lex($slurped);
}

sub findNworst {
  my ($n, @toks) = @_;
  if (@toks > $order * 2) {
    my @possibilities = (findNworst($n, @toks[0..($#toks/2)+$order-1]), findNworst($n, @toks[($#toks/2)-$order+1..$#toks]));
    sort { $a->[1] <=> $b->[1] } @possibilities;
    return @possibilities[0..$n-1];
  } else {
    print $lmin join(" ", @toks);
    my $entropy;
    while(my $line = <$lmout>) {
	chomp($line);
        print STDERR "MITLM said $line";
	last if (($entropy) = ($line =~ m/Live Entropy ([-\d.]+)/));
    }
    return [ [ @toks ], $entropy ];
  }
}

unless (attempt_compile(@ARGV)) {
  @possible_bad_files = @files_mentioned;
  $main_compile_status = $status;
  print LOGFILE "FAIL";
  # we need to determine exactly which file failed because of this dumb compile a ton at once bs
  for my $source (@possible_bad_files) {
    unless (attempt_compile(@ARGV_NO_LISTS, $source)) {
      print("Maybe the error was in $source?");
      my @toks = split(' ', lexAfile($source));
      print "Slurped " . @toks . " tokens.";
      startMITLM();
      my @worst = findNworst(3, @toks);
      print("Check near " . join(' ', $worst[0][0]));
      print("With entropy " . $worst[0][1]);
    }
  }
} else {
  print LOGFILE "COMPILE OK";
  $status = 0;
  my $lexed = '';
  for my $file (@inputfiles) {
      print TOKFILE lexAfile($file);
  }
}

for (@files_mentioned) { print LOGFILE; }

close LOGFILE;


$socket->close();
$ctxt->term();

exit $status;
