#!/usr/bin/perl
use strict;

$\ = $/;
$|=1;

use IPC::Open3;
use IPC::Open2;
use IO::Handle;
# use Symbol;
$SIG{PIPE} = 'IGNORE';
use ZeroMQ qw/:all/;

my $real_javac = $ENV{JAVAC_WRAPPER_REAL_JAVAC} ? $ENV{JAVAC_WRAPPER_REAL_JAVAC} : qx{which javac};
chomp $real_javac;

my @inputfiles = ();

open LOGFILE, '>>', $ENV{JAVAC_WRAPPER_LOGFILE} ? $ENV{JAVAC_WRAPPER_LOGFILE} : "/tmp/javac-logfile" or die;
open TOKFILE, '>>', $ENV{JAVAC_WRAPPER_ADDCORPUS} ? $ENV{JAVAC_WRAPPER_ADDCORPUS} : "/tmp/javac-tokfile" or die;
my $corpus = $ENV{JAVAC_WRAPPER_CORPUS} ? $ENV{JAVAC_WRAPPER_CORPUS} : "/tmp/javac-tokfile";
my $estimateNgram = $ENV{JAVAC_WRAPPER_ESTIMATENGRAM} ? $ENV{JAVAC_WRAPPER_ESTIMATENGRAM} : qx{which estimate-ngram};
my $forcetrain = $ENV{JAVAC_WRAPPER_TRAIN} ? $ENV{JAVAC_WRAPPER_TRAIN} : 0;
my $validate = $ENV{JAVAC_WRAPPER_VALIDATE} ? $ENV{JAVAC_WRAPPER_VALIDATE} : 0;

my @JAVAC_INPUTFILES_LISTS = grep(m/^@/, @ARGV);
my @ARGV_NO_LISTS = grep(!m/^@|\.java/i, @ARGV);
my $order = 7;

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
@inputfiles = grep(m/\.java/, @inputfiles, @ARGV, @ARGV_NO_LISTS);
for (@inputfiles) {
  print LOGFILE;
}

my $status;
my $main_compile_status;
my %files_mentioned;
my %possible_bad_files;

sub attempt_compile {
  print LOGFILE join(' ', @_);
  my $ccout;
  my $pid = open3("<&STDIN", $ccout, $ccout, $real_javac, @_) or die $?;
  my $compile_error = 0;

  while (<$ccout>) {
    chomp;
    print;
    if (m/\.java/i) {
      print LOGFILE "javac said: " . $_;
      my ($file) = ($_ =~ m/(\S+\.java):/i);
      print LOGFILE "Possible error location: $file";
      $files_mentioned{$file}++;
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

my ($lmout, $lmerr, $lmin, $lmpid);

sub startMITLM {
  die "No corpus: $corpus" unless -e $corpus;
  my @run = ('-t', $corpus, '-o', $order, '-s', 'ModKN', '-u', '-live-prob');
  print "Corpus ok. MITLM starting: $estimateNgram " . join(" ", @run);
  $lmpid = open2($lmout, $lmin, join(" ", "(", $estimateNgram, @run, ";)")) or print $?;
  print "Started MITLM as pid $lmpid";
  while(my $line = <$lmout>) {
      chomp($line);
      print "[mitlm] $line";
      if ($line =~ m/Live Entropy Ready/) {
	print "MITLM ready";  
	last;
      }
  }
  print $lmin "for ( i =$/";
  print $!;
  print "made it";
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
        $out =~ s/[\r\n]/ /g;
        # by clearing up excessive whitespace we seem to lex better
        $out =~ s/\s\s+/ <SPACE> /g;
#         $out =~ s/  */ /g;
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
  my @possibilities;
  my $x = 3;
  for (my $i = 0; $i < ($#toks-($x*$order)); $i += $order) {
#     print join(" ", @toks[$i..$i+($x*$order)]);
    print $lmin join(" ", @toks[$i..$i+($x*$order-1)]);
    my $entropy;
    while(my $line = <$lmout>) {
	chomp($line);
#         print "MITLM said $line";
	last if (($entropy) = ($line =~ m/Live Entropy ([-\d.]+)/));
    }
    push @possibilities, [ [ @toks[$i..$i+($x*$order-1)] ], $entropy ];
  }
  @possibilities = sort { $b->[1] <=> $a->[1] } @possibilities;
  return @possibilities;
}

unless ($validate) {
  unless (attempt_compile(@ARGV) || $forcetrain) {
    %possible_bad_files = %files_mentioned;
    $main_compile_status = $status;
    startMITLM();
    print LOGFILE "FAIL";
    # we need to determine exactly which file failed because of this dumb compile a ton at once bs
    for my $source (keys(%possible_bad_files)) {
      unless (attempt_compile(@ARGV_NO_LISTS, $source)) {
	print("Maybe the error was in $source?");
	my @toks = split(' ', lexAfile($source));
	print "Slurped " . @toks . " tokens.";
	my @worst = findNworst(3, @toks);
	for my $i (0..4) {
	  my $code = join('', @{$worst[$i][0]});
	  $code =~ s/<SPACE>/ /g;
	  print("Check near " .$code);
	  print("With entropy " . $worst[$i][1]);
	}
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
  } else {
    startMITLM();
    my $correct = 0;
    my $tries = 0;
    my $x = 0;
    print STDERR scalar(@inputfiles);
    for my $source (@inputfiles) {
      my @toks = split(' ', lexAfile($source));
      print "Slurped " . @toks . " tokens.";
      if (scalar(@toks) < 3*$order) { next; }
      $x = ($x+1) % 8;
      if (scalar(@toks) >= 25) { `cp $source big/$source` };
      next;
      my @worst = findNworst(3, @toks);
      my @worst = findNworst(3, @toks);
	for my $i (0..4) {
	  my $code = join('', @{$worst[$i][0]});
	  $code =~ s/<SPACE>/ /g;
	  print("Check near " .$code);
	  print("With entropy " . $worst[$i][1]);
	}
      my @thresh;
      for my $i (0..4) {
	$thresh[$i] = $worst[$i][1];
      }
      print "THRESHOLD $thresh[0]";
      my ($validateMode, $validateNumber) = split(' ', $validate);
      my %possibleToks = ();
      for (@toks) {
	$possibleToks{$_}++;
      }
      my @possibleToks = keys(%possibleToks);
      for my $i (1..$validateNumber) {
	my @mutatedToks = @toks;
	my $loc = int(rand($#mutatedToks));
	if ($validateMode =~ m/d/) {
	  splice(@mutatedToks, $loc, 1);
	} elsif ($validateMode =~ m/r/) {
	  splice(@mutatedToks, $loc, 1, $possibleToks[int(rand($#possibleToks))]);
	} elsif ($validateMode =~ m/i/) {
	  splice(@mutatedToks, $loc, 0, $possibleToks[int(rand($#possibleToks))]);
	} elsif ($validateMode =~ m/R/) {
	  splice(@mutatedToks, $loc, 1, " XXXXXXXX ");
	} elsif ($validateMode =~ m/I/) {
	  splice(@mutatedToks, $loc, 0, " XXXXXXXX ");
	} else {
	  die "what?"
	}
	my @mutatedWorst = findNworst(3, @mutatedToks);
	for my $i (0..4) {
	  my $code = join('', @{$mutatedWorst[$i][0]});
	  $code =~ s/<SPACE>/ /g;
	  print("Check near " .$code);
	  print("With entropy " . $mutatedWorst[$i][1]);
	}
	$tries++;
	for my $i (0..4) {
	  if ($thresh[$i] < $mutatedWorst[$i][1]) {
	    $correct++;
	    print "CORRECT!!!";
	    last;
	  }
	}
	print "Accuracy: " . $correct/$tries;
      }
   }
}

for (%files_mentioned) { print LOGFILE; }

close LOGFILE;
defined ($lmin) and close $lmin;
defined ($lmout) and close $lmout;

$socket->close();
$ctxt->term();

exit $status;
