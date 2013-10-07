#! /usr/bin/perl -w
use strict;

# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

# Print the text of each "incoming message received" from a Debian bug log,
# SMTP-style. (Each message is terminated by a "." on a line by itself; any
# "." characters at the beginning of a line in the message are escaped by
# prepending another ".".)

# use lib '/srv/debzilla.no-name-yet.com/perl';
use Debbugs::Log;

sub read_log ($)
{
    my $file = shift;

    local *LOG;
    open LOG, "< $file" or die "can't open $file: $!";
    my @records = read_log_records(*LOG);
    close LOG;

    return @records;
}

sub filter_records (@)
{
    my @out;

    for my $record (@_) {
        if ($record->{type} eq 'incoming-recv') {
            push @out, $record->{text};
        } elsif ($record->{type} eq 'autocheck') {
            # Strange old format. Grab all lines beginning with X, strip off
            # the X, and return the concatenation.
            # Debbugs::Log should probably do this somehow ...
            my $text = $record->{text};
            my @xlines = grep /^X/, split /\n/, $text;
            my $foundautofwd = 0;
            my $outtext = '';
            for my $xline (@xlines) {
                if (not $foundautofwd and
                        $xline =~ /^X-Debian-Bugs(-\w+)?: This is an autoforward from \S+/) {
                    $foundautofwd = 1;
                    next;
                }
                $xline =~ s/^X//;
                $outtext .= "$xline\n";
            }
            push @out, $outtext;
        }
    }

    return @out;
}

sub print_text (@)
{
    for my $text (@_) {
        $text =~ s/^\./../m;                    # escape dots
        $text .= "\n" unless $text =~ /\n\z/;   # ensure newline terminator
        print $text, ".\n";
    }
}

my $file = shift;
print_text(filter_records(read_log($file)));
