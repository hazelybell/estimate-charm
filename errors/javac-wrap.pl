#!/usr/bin/perl
use strict;

$\ = $/;
$|=1;

use IPC::Open3;
use IPC::Open2;
use IO::Handle;
# use Symbol;
use List::Util qw(max min);
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
my $order = 10;
my $step = 1;
my $block = 2*$order;
my $N = 5;

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
my %files_mentioned;
my %possible_bad_files;

sub attempt_compile {
  print LOGFILE join(' ', @_);
  my $ccout;
  my $pid = open3("<&STDIN", $ccout, $ccout, $real_javac, @_) or die $?;
  my $compile_error = 0;

  while (<$ccout>) {
    chomp;
    print $_;
    if (m/\.java/i) {
      print LOGFILE "javac said: " . $_;
      my ($file) = ($_ =~ m/(\S+\.java):/i);
      print LOGFILE "Possible error locatplotion: $file";
      $files_mentioned{$file}++;
      $compile_error++;
    }
  }
  print "waiting...";
  waitpid($pid, 0);
  $status = $? >> 8;
  print "return $?";
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
  print STDERR  "Corpus ok. MITLM starting: $estimateNgram " . join(" ", @run);
  $lmpid = open2($lmout, $lmin, join(" ", "(", $estimateNgram, @run, ";)")) or print $?;
  print STDERR "Started MITLM as pid $lmpid";
  while(my $line = <$lmout>) {
      chomp($line);
      print STDERR "[mitlm] $line";
      if ($line =~ m/Live Entropy Ready/) {
	print STDERR "MITLM ready";  
	last;
      }
  }
  print $lmin "for ( i =$/";
  print $!;
  print STDERR "made it";
  my $i = 0;
  while(my $line = <$lmout>) {
      chomp($line);
      print "MITLM said $line";
      $i++ if ($line =~ m/Live Entropy ([-\d.]+)/);
      last if $i >= 2;
  }
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
        $socket->send( "-comments +code +java +lines$/" . javaCommentHack(join("", @in)  ));
        my $msg = $socket->recv();
        my $out = $msg->data();
        my @outlines = ($out =~ m/.+?\s\d+:\d+[\r\n]/sg);
        my $outst = [];
        foreach (@outlines) {
          chomp;
          s/^\s+\s/<SPACE> /;
          my ($token, $line, $char) = m/^(.+?)\s(\d+):(\d+)/s;
          push @$outst, [$token, $line, $char];
        }
        return $outst;
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

sub toksToTrain {
  my ($toks) = @_;
  return join(" ", "<SPACE> " x $order, (map { $_->[0] } @$toks), "<SPACE> " x $order);
}

sub toksToQuery {
  my ($toks) = @_;
  return join(" ", map { $_->[0] } @$toks);
}

sub toksToCode {
  my ($toks) = @_;
  my $lastline = 0;
  my $code = '';
  for (@$toks) {
    my ($tok, $line, $char) = @$_;
    $tok = ' ' if ($tok eq '<SPACE>');
    if ($line > $lastline) {
      $code .= $/;
      $lastline = $line;
    }
    $code .= $tok;
  }
  return $code;
}

sub findNworst {
  my (@toks) = @_;
  my @possibilities;
  for (my $i = 0; $i < ($#toks-($block)); $i += $step) {
#     print STDOUT toksToQuery([ @toks[$i..$i+($block-1)] ]);
    print $lmin toksToQuery([ @toks[$i..$i+($block-1)] ]);
    my $entropy;
    while(my $line = <$lmout>) {
	chomp($line);
#         print "MITLM said $line";
	last if (($entropy) = ($line =~ m/Live Entropy ([-\d.]+)/));
    }
    push @possibilities, [ [ @toks[$i..$i+($block-1)] ], $entropy ];
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
	print(STDERR "Maybe the error was in $source?");
	my @toks = @{lexAfile($source)};
	print STDERR "Slurped " . @toks . " tokens.";
	
	my @worst = findNworst(@toks);
	for my $i (0..$N) {
          print(STDERR "Check near " . $worst[$i][0][0][1].":".$worst[$i][0][0][2]
            . " to " . $worst[$i][0][$#{$worst[$i][0]}][1].":".$worst[$i][0][$#{$worst[$i][0]}][2]);
# 	  my $code = join('', @{$worst[$i][0]});
# 	  print(STDERR "Check near " .$code);
	  print(STDERR "With entropy " . $worst[$i][1]);
	}
      }
    }
  } else {
    print LOGFILE "COMPILE OK";
    print "COMPILE OK";
    $status = 0;
    my $lexed = '';
      for my $file (@inputfiles) {
	  print TOKFILE toksToTrain(lexAfile($file));
      }
    }
  } else {
    startMITLM();
    my $correct = 0;
    my $tries = 0;
    for my $source (@inputfiles) {
      my @toks = split(' ', lexAfile($source));
      print STDERR "Slurped " . @toks . " tokens.";
      if (scalar(@toks) < 10) { next; }
      my @worst = findNworst(@toks);
      my @worst = findNworst(@toks);
      for my $i (0..$N) {
        my $code = join('', @{$worst[$i][0]});
        $code =~ s/<SPACE>/ /g;
        print(STDERR "Check near " .$code);
        print(STDERR "With entropy " . $worst[$i][1]);
      }
      my @thresh;
      for my $i (0..$#worst) {
	$thresh[$i] = $worst[$i][1];
      }
      print STDERR "THRESHOLD $thresh[0]";
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
        my $code = join('', @toks[$loc-$order..$loc+$order]);
        $code =~ s/<SPACE>/ /g;
        print(STDERR "Error inserted near " .$code);
	my @mutatedWorst = findNworst(@mutatedToks);
	$tries++;
	my $at = $N;
	for my $i (0..$#mutatedWorst) {
	  if ($thresh[$i] < $mutatedWorst[$i][1]) {
	    print "$i";
            $code = join('', @{$mutatedWorst[$i][0]});
            $code =~ s/<SPACE>/ /g;
            print(STDERR "Check near " .$code);
            print(STDERR "With entropy " . $mutatedWorst[$i][1]);
            $at = $i;
	    last;
	  }
	}
	$correct++ if ($at < $N);
	print STDERR "Accuracy: " . $correct/$tries;
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
