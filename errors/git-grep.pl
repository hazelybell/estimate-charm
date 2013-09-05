#!/usr/bin/perl
use strict;
use FileHandle;
#use Text::CSV;
use Digest::MD5 qw(md5 md5_hex md5_base64);
use Term::ANSIColor;
# $|=1;
my $case_sensitive = 1;
use VCI; #to install: cpan VCI; cpan -f VCI

my ($repo, $grep) = @ARGV;

if (@ARGV == 3) {
    ($case_sensitive, $repo, $grep) = @ARGV;
    if ($case_sensitive eq '-cs') {
        $case_sensitive = 1;
    } elsif ($case_sensitive eq '-i') {
        $case_sensitive = 0;
    } else {
        die "-cs or -i expected: @ARGV";
    }
}


my $repo = VCI->connect(
                              type => 'Git', 
                              repo => ($repo || die "Provide a repo path!"),
);
bluewarn("Connected to git");
my $projects = $repo->projects;
my $project = $repo->get_project( name=>'');
my $history = $project->get_history_by_time( start => 0, end => time());
my $commits = $history->commits();
bluewarn("Got History");

my %last = ();
my %content = (); # store refs to scalars!
foreach my $commit (@$commits) {
    #my $contents = $commit->contents();
    my $cid   = $commit->revision();
    my $author = $commit->author();
    my $committer = $commit->committer();
    my $comment = $commit->message();    
    if (($case_sensitive && $comment =~ /$grep/) || (!$case_sensitive && $comment =~ /$grep/i)) {
    	warn color("bold red"), $cid, color("reset");
        print join("\t",$cid,$author).$/;
	yellowwarn($comment);
    }
}
sub bluewarn {
    warn color("blue"),@_,color("reset");
}
sub yellowwarn {
    warn color("yellow"),@_,color("reset");
}
