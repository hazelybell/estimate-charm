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
use Data::Dumper;
use Digest::MD5 qw(md5 md5_hex md5_base64);
use List::Util;
use Text::CSV;
use File::Basename;

my $real_javac = $ENV{PYTHON_WRAPPER_REAL_PYTHON} ? $ENV{PYTHON_WRAPPER_REAL_PYTHON} : qx{which javac};
chomp $real_javac;

my @inputfiles = ();

my $logfile = $ENV{PYTHON_WRAPPER_LOGFILE} ? $ENV{PYTHON_WRAPPER_LOGFILE} : "/tmp/javac-logfile";
open LOGFILE, '>>', $logfile or die;

open TOKFILE, '>>', $ENV{PYTHON_WRAPPER_ADDCORPUS} ? $ENV{PYTHON_WRAPPER_ADDCORPUS} : "/tmp/javac-tokfile" or die;
my $corpus = $ENV{PYTHON_WRAPPER_CORPUS} ? $ENV{PYTHON_WRAPPER_CORPUS} : "/tmp/javac-tokfile";
my $estimateNgram = $ENV{PYTHON_WRAPPER_ESTIMATENGRAM} ? $ENV{PYTHON_WRAPPER_ESTIMATENGRAM} : qx{which estimate-ngram};
my $forcetrain = $ENV{PYTHON_WRAPPER_TRAIN} ? $ENV{PYTHON_WRAPPER_TRAIN} : 0;
my $validate = $ENV{PYTHON_WRAPPER_VALIDATE} ? $ENV{PYTHON_WRAPPER_VALIDATE} : 0;

my @PYTHON_INPUTFILES_LISTS = grep(m/^@/, @ARGV);
my @ARGV_NO_LISTS = grep(!m/^@|\.py/i, @ARGV);
my $order = 10;
my $step = 1;
my $block = 2*$order;
my $N = 5;

for my $list (@PYTHON_INPUTFILES_LISTS) {
  $list =~ s/^@//;
  chomp $list;
  open LIST, '<', $list or die;
    while (<LIST>) {
      chomp;
      push @inputfiles, $_;
    }
  close LIST;
}
@inputfiles = grep(m/\.py/, @inputfiles, @ARGV);
for (@ARGV) {
  print LOGFILE;
}

my $main_compile_status;
my %possible_bad_files;

sub attempt_compile {
#   print LOGFILE join(' ', @_);
  my $ccout;
  my $pid = open3("<&STDIN", $ccout, $ccout, $real_javac, @_) or die $?;
  my $compile_error = 0;
  my %files_mentioned;
  my $status;
  my @results;

  while (<$ccout>) {
    chomp;
    print $_;
    if (m/\.java/i) {
#       print LOGFILE "javac said: " . $_;
      my ($file, $line) = ($_ =~ m/(\S+\.java):(\d+):/i);
#       print LOGFILE "Possible error location: $file";
      $files_mentioned{$file}++;
      $compile_error++;
      push @results, [$file, $line];
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
  return (!$compile_error, $status, \%files_mentioned, \@results);
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
  print $lmin "for ( i =";
  print $!;
  my $i = 0;
  while(my $line = <$lmout>) {
      chomp($line);
      print "MITLM said $line";
      $i++ if ($line =~ m/Live Entropy ([-\d.]+)/);
      last if $i >= 1;
  }
  print STDERR "MITLM seems okay";
}

my $ctxt = ZeroMQ::Context->new();    
my $socket = ZeroMQ::Socket->new( $ctxt, ZMQ_REQ );
$socket->connect( "tcp://127.0.0.1:32132" ); # java lexer

    sub lex {
        my @in = @_;
        # note it says java here
        my %query = ( comments => 0, code => 1, python => 1, body => (join('', @in)  ));
        $socket->send_as( json => \%query );
        my $response = $socket->recv_as('json');
        print Dumper $response;
        die;
        my @outlines = ($response =~ m/.+?\s\d+:\d+[\r\n]/sg);
        my $outst = [];
        foreach (@outlines) {
          chomp;
          s/^\s+\s/<SPACE> /;
          my ($token, $line, $char) = m/^(.+?)\s(\d+):(\d+)/s;
          push @$outst, [$token, $line, $char];
        }
        return $outst;
    };

sub slurpAFile {
  my ($file) = @_;
  open INPUTFILE, '<', $file or die;
  my $slurped = '';
  while (<INPUTFILE>) {
#       s/\n//gs;
#       $lexed .= lex($_);
    $slurped .= $_;
  }
  close INPUTFILE;
  return $slurped;
}

sub replaceAFile {
  local $/ = '';
  local $\ = '';
  my ($file, $text) = @_;
  open OUTPUTFILE, '>', $file or die;
  print OUTPUTFILE $text or die;
  close OUTPUTFILE or die;
}

sub lexAfile {
    my ($file) = @_;
    return lex(slurpAFile($file));
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
  my $lastline = 1;
  my $code = '';
  for (@$toks) {
    my ($tok, $line, $char) = @$_;
    $tok = ' ' if ($tok eq '<SPACE>');
    if ($line > $lastline) {
      $code .= $/ x ($line-$lastline);
      $lastline = $line;
    }
    $code .= $tok;
  }
  return $code;
}

sub findNWorst {
  my ($toks) = @_;
  my @toks = @$toks;
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
  return \@possibilities;
}

sub printNWorst {
  my ($worst) = @_;
  for my $i (0..$N) {
#     print (STDERR Dumper $worst);
    print(STDERR "Check near " . $worst->[$i][0][0][1].":".$worst->[$i][0][0][2]
      . " to " . $worst->[$i][0][$#{$worst->[$i][0]}][1].":".$worst->[$i][0][$#{$worst->[$i][0]}][2]);
#         my $code = join('', @{$worst[$i][0]});
#         print(STDERR "Check near " .$code);
    print(STDERR "With entropy " . $worst->[$i][1]);
  }
}

unless ($validate) {
    my ($success, $status, $files_mentioned);
    ($success, $status, $files_mentioned) = attempt_compile(@ARGV) unless $forcetrain;
    unless ($success || $forcetrain) {
      %possible_bad_files = %$files_mentioned;
      $main_compile_status = $status;
      startMITLM();
#       print LOGFILE "FAIL";
      # we need to determine exactly which file failed because of this dumb compile a ton at once bs
      for my $source (keys(%possible_bad_files)) {
        my ($return) = attempt_compile(@ARGV_NO_LISTS, $source);
        unless ($return) {
          print(STDERR "Maybe the error was in $source?");
          my @toks = @{lexAfile($source)};
          print STDERR "Slurped " . @toks . " tokens.";
          
          printNWorst(findNWorst(\@toks));
        }
      }
    } else {
#       print LOGFILE "COMPILE OK";
      print "COMPILE OK";
      $status = 0;
      my $lexed = '';
      for my $file (@inputfiles) {
          print TOKFILE toksToTrain(lexAfile($file));
      }
    }
  } else {
    my ($validateMode, $validateNumber) = split(' ', $validate);
    my $testlogfile = dirname($logfile)."/javactestlog-".$validateMode."-".substr(md5_base64(join(chr(0),@inputfiles)),0,5);
    my $csv = Text::CSV->new ( { binary => 1, eol => "\n" } )  # should set binary attribute.
                    or die "Cannot use CSV: ".Text::CSV->error_diag ();
    my $testlogfh;
    open $testlogfh, ">>:encoding(utf8)", "$testlogfile" or die "$testlogfile: $!";
    $csv->print($testlogfh, [qw|file tokens Nmean U J JU UJ|]);
    startMITLM();
    for my $source (@inputfiles) {
      my $oursum = 0;
      my $jcsum = 0;
      my $combineda = 0;
      my $combinedb = 0;
      my $tries = 0;
      my $originalsource = slurpAFile($source);
      my @toks = @{lex($originalsource)};
      print STDERR "Slurped " . @toks . " tokens.";
      if (scalar(@toks) < 10) { next; }
      my $worst = findNWorst(\@toks);
      printNWorst($worst);
      my @worst = @$worst;
      my %possibleToks = ();
      for (@toks) {
	$possibleToks{$_->[0]}++;
      }
      my @possibleToks = keys(%possibleToks);
      while ($tries < $validateNumber) {
	my @mutatedToks = @toks;
	my $loc = int(rand($#mutatedToks));
	my $mutline = $toks[$loc][1];
	my $mutchar = $toks[$loc][2];
# 	die "$mutline:$mutchar";
	if ($validateMode =~ m/d/) {
	  splice(@mutatedToks, $loc, 1);
	} elsif ($validateMode =~ m/r/) {
	  splice(@mutatedToks, $loc, 1, [$possibleToks[int(rand($#possibleToks))], $mutline, $mutchar]);
	} elsif ($validateMode =~ m/i/) {
	  splice(@mutatedToks, $loc, 0, [$possibleToks[int(rand($#possibleToks))], $mutline, $mutchar]);
	} elsif ($validateMode =~ m/R/) {
	  splice(@mutatedToks, $loc, 1, [" XXXXXXXX ", $mutline, $mutchar]);
	} elsif ($validateMode =~ m/I/) {
	  splice(@mutatedToks, $loc, 0, [" XXXXXXXX ", $mutline, $mutchar]);
	} else {
	  die "what?"
	}
	replaceAFile($source, toksToCode(\@mutatedToks));
	print STDERR "Mutated $source:$mutline:$mutchar";
	my $ourResults = findNWorst(\@mutatedToks);
	printNWorst($ourResults);
        my $ourindex = 0;
	foreach(@$ourResults) {
          $ourindex++;
          if ($_->[0][0][1] <= $mutline) {
            if ($_->[0][$#{$_->[0]}][1] >= $mutline) {
              if ($_->[0][0][1] < $mutline || $_->[0][0][2] <= $mutchar+10) {
                if ($_->[0][$#{$_->[0]}][1] > $mutline || $_->[0][$#{$_->[0]}][2] >= $mutchar-10) {
                  print "Correct: $ourindex";
                  last;
                }
              }
            }
          }
	}
        my ($success, $status, $files_mentioned, $javacresults) = attempt_compile(@ARGV_NO_LISTS, $source);
        next if $success;
        my $jcindex = 0;
        my $jcpresent = 0;
        foreach(@$javacresults) {
          $jcindex++;
          if ($_->[0] =~ m/$source/) {
            if ($_->[1] == $mutline) {
              $jcpresent++;
              last;
            }
          }
        }
        $jcindex = 10000000 unless $jcpresent;
        $jcsum += 1.0/$jcindex;
        $oursum += 1.0/$ourindex;
        $combineda += max(1.0/(2.0*$jcindex-1), 1.0/(2.0*$ourindex));
        $combinedb += max(1.0/(2.0*$jcindex), 1.0/(2.0*$ourindex-1));
	$tries += 1;
	replaceAFile($source, $originalsource);
        print STDERR "Our MRR: " . $oursum/$tries;
        print STDERR "JavaC MRR: " . $jcsum/$tries;
        print STDERR "JavaC,Our MRR: " . $combineda/$tries;
        print STDERR "Our,JavaC MRR: " . $combinedb/$tries;
      }
      $csv->print($testlogfh, [basename($source), scalar(@toks), $validateNumber, $oursum/$tries, $jcsum/$tries, $combineda/$tries, $combinedb/$tries]);
   }
}

for (%possible_bad_files) { print LOGFILE; }

close LOGFILE;
defined ($lmin) and close $lmin;
defined ($lmout) and close $lmout;

$socket->close();
$ctxt->term();

exit $main_compile_status;
