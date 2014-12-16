#!/usr/bin/perl

# copper.pl -- Customize the copper framework.
#
#    Copyright 2006, 2007, 2008, 2013, 2014 Joshua Charles Campbell
#
#    This file is part of UnnaturalCode.
#    
#    UnnaturalCode is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    UnnaturalCode is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with UnnaturalCode.  If not, see <http://www.gnu.org/licenses/>.

use strict;
use warnings;

use File::Spec;
use Data::Dumper;
use File::Temp qw(tempfile);

my $command = shift;
my @tests;
my @files;
my $i = 0;

# Whitespace is important here, please make sure that there is no extra whitespace in the following heredoc
# use an editor that shows it if you need to
my $output_legal_bs = <<EOF;
Portions Copyright 2006-2008 Joshua Charles Campbell.

This program is free software; you can redistribute it and/or
modify it under the terms of the GNU General Public License
as published by the Free Software Foundation; either version 3
of the License, or (at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

The output of this program includes substantial portions that
are preprocessed (copied) from text in the original program, copper.pl
due to the nature of that program.  Therefore, this output is subject
to the same license as that program.
See http://www.gnu.org/licenses/gpl-faq.html#GPLOutput for more information.

You should have received a copy of the GNU General Public License
along with this program; if not, write to the Free Software
Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA
02110-1301, USA.
EOF

my $copper_perl_input_files;
if ($command eq 'cc') { # proxy for the c compiler, preprocess the files
	die "Didn't set COPPER_PERL_INPUT_FILES in the Makefile?" unless $ENV{COPPER_PERL_INPUT_FILES};
	my @copper_perl_input_files = map { s/\\(\W)/$1/g; $_ } split(m/(?<!\\):/, $ENV{COPPER_PERL_INPUT_FILES});
	my @cc_argv;
	my @temps;
	my $do_pp;
	foreach my $ccarg (@ARGV) {
		my $yes = 0;
		foreach my $input_file (@copper_perl_input_files) {
			$yes++ if $ccarg eq $input_file;
		}
		if ($yes) {
                        my ($prefix, $suffix) = ($ccarg =~ m/^(.+)(\.[^.]+)$/);
                        my $ppoutname = "$prefix.tests$suffix";
                        -e $ppoutname and die;
                        open(my $ppout, ">", $ppoutname) or die;
			print STDERR "preprocessing $ccarg to $ppoutname\n";
			open PPIN, '<', $ccarg;
			push @temps, $ppoutname;
			while (<PPIN>) {
				my $testcode;
                                my $line = PPIN->input_line_number();
				if (m/^TEST\(\(/) {
					my $test = "$ccarg:$.";
					my $function = $test;
					$function =~ s/\W/_/g;
					print $ppout "#define TEST_$function(x) struct test_result $function() { struct test_result r; r.pass = (x); r.text = #x; r.name = \"$function\"; return r; }\n";
					print $ppout "#line $line$/";
					s/^TEST/TEST_$function/;
				} elsif (m/^TEST\(\{/) {
                                        my $test = "$ccarg:$.";
                                        my $function = $test;
                                        $function =~ s/\W/_/g;
                                        my $function_inside = $function . "_test";
                                        print $ppout "#define TEST_$function(x) static void $function_inside() x struct test_result $function() { copper_global_test_result.pass = 1; copper_global_test_result.text = \"\"; copper_global_test_result.name = \"$function\"; $function_inside(); return copper_global_test_result; }\n";
                                        print $ppout "#line $line$/";
                                        s/^TEST/TEST_$function/;
                                }
				print $ppout $_;
			}
			close PPIN;
                        print $ppout $/;
			close $ppout;
			push @cc_argv, $ppoutname;
		} else {
			push @cc_argv, $ccarg;
		}
	}
	my $cc = $ENV{COPPER_REAL_CC} ? $ENV{COPPER_REAL_CC} : 'cc'; 
	unshift @cc_argv, $cc, "-DENABLE_TESTING", "-DENABLE_DEBUG";
	print STDERR join(" ", "RUNNING", @cc_argv) . "\n";
	my $r = system(@cc_argv) >> 8;
  	unlink foreach @temps;
	exit $r; # don't do the rest of the script
}

my ($selfvol,$selfdir,$selffile) = File::Spec->splitpath($0);
my $selfbase = $selffile;
$selfbase =~ s/\.pl$//;

my $tester_name;
if ($ENV{COPPER_TEST_PROGRAM}) {
	$tester_name = '${COPPER_TEST_PROGRAM}';
} else {
	$tester_name = "./$selfbase-run";
}

my $input_files;
if ($ENV{COPPER_INPUT_FILES}) {
	if (@ARGV == 0) {
		die "No files but there are files listed in the environment variable.  Please call from your makefile like $0 $command \${COPPER_INPUT_FILES}.";
	}
	$input_files = "\${COPPER_INPUT_FILES}";
} else {
	if (@ARGV == 0) {
		die "No input files."
	}
	$input_files = join(" ", @ARGV);
}
$copper_perl_input_files = join(":", map { quotemeta } @ARGV);

my $object_files;
if ($ENV{COPPER_OBJECT_FILES}) {
	$object_files = "\${COPPER_OBJECT_FILES}";
} else {
	my @ofiles = @ARGV;
	s/\.c$/.o/ foreach @ofiles;
	$object_files = join(" ", @ofiles);
}

-r $_ or die "No such file $_" foreach @ARGV;

while(<>) {
	if (m/^TEST/) {
		push @tests, "$ARGV:$.";
		$i++;
		push @files, "$ARGV";
	}
} continue {
  close ARGV if eof; # Thanks perldoc
}

my @functions = @tests;
s/\W/_/g foreach @functions;

if ($command eq 'makefile') {
	print "# Automatically generated makefile by copper.pl. Edit at your own risk.\n";
	$output_legal_bs =~ s/^(?=.+$)/# /gm;
	print $output_legal_bs . "\n";
	print "COPPER_REAL_CC := \${CC}\n";
	print "CC = $0 cc\n";
	print "COPPER_PERL_INPUT_FILES = $copper_perl_input_files\n";
	print "export\n\n";
	print "copper_tests.c: $input_files\n";
	print "\t$0 tests \$+ >\$\@\n\n";
	print "$tester_name: copper_tests.c copper-internal.c copper.c $object_files\n";
	print "\t\${CC} \${CFLAGS} \${CPPFLAGS} -o $tester_name \$+\n\n";
	foreach my $i (0..$#tests) {
		print "$functions[$i]: $tester_name \n";
		print "\t$tester_name $i\n";
	}
	print "\ncopper_test_all: " . join(" ", @functions) . "\n\n";
	print "copper_clean:\n";
	print "		- rm -f $tester_name copper_tests.c";
} elsif ($command eq 'tests') {
	print "/* This file automatically generated by $0\n";
	$output_legal_bs =~ s/^(?=.+$)/ * /gm;
	print "$output_legal_bs */\n\n";
	print "#include \"copper.h\"\n\n";
	print "int copper_tests_count = " . scalar(@functions) . ";\n\n";
	print "extern struct test_result $_();\n" foreach @functions;
	print "\nstruct test_result (*tests[])(void) = {\n";
	print "\t$_,\n" foreach @functions;
	print "};\n\n";
} else {
	die;
}
