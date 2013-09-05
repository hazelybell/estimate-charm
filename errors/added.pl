#!/usr/bin/perl
use strict;
use Parallel::ForkManager;
use FileHandle;
use IPC::Open2;
#use Text::CSV;
use Digest::MD5 qw(md5 md5_hex md5_base64);
use Term::ANSIColor;
use Data::Dumper;
# $|=1;

my $ZEROMQ = 1;

#my $pm = Parallel::ForkManager->new($processes);

# PATHS FOR IMPORTANT EXECUTABLES
my $TMPDIR = "/tmp/git-walker";
my $OUTPUTDIR = "./git-walker-output";
my $ESTIMATE="$ENV{HOME}/projects/ngrams/src/mitlm/usr/bin/estimate-ngram";
my $LEXJAVA="$ENV{HOME}/projects/ngrams/antlr/LexJava";

sub lex_file {
    system("$LEXJAVA +code +comments  $_[0] > $_[1]");
}
my $ctxt;
my $socket;
if ($ZEROMQ) {
    warn color("blue"),"Enabling ZeroMQ",color("reset");
    use ZeroMQ qw/:all/;
    $ctxt = ZeroMQ::Context->new();    
    $socket = ZeroMQ::Socket->new( $ctxt, ZMQ_REQ );
    $socket->connect( "tcp://127.0.0.1:32132" );
    *lex_file = sub {
        my ($filein, $fileout) = @_;
        my $in = "";
        if (ref($filein)) {
            $in = $$filein;
            $filein = "<STRING>";
        } else {
            open(my $fd, $filein);
            my @in = <$fd>;
            close($fd);
            $in = join("", @in);
        }
        warn color("blue"),"Reading $filein and writing $fileout",color("reset");
        $socket->send( "+comment +code$/" . $in );
        my $msg = $socket->recv();
        my $out = $msg->data();
        $out =~ s/[\r\n]/ /g;
        $out =~ s/; /;\n/g;
        open(my $fd, ">", $fileout);
        print $fd $out;
        print $fd $/;
        close($fd);
    };
    warn color("blue"),"ZeroMQ Enabled",color("reset");
}


mkdir($TMPDIR);
mkdir($OUTPUTDIR);

use VCI; #to install: cpan VCI; cpan -f VCI

my $repo = VCI->connect(
                              type => 'Git', 
                              repo => ($ARGV[0] || die "Provide a repo path!"),
);
bluewarn("Connected to git");
my $order = $ARGV[1] || 3;
# drop the head of ARGV
shift @ARGV;
shift @ARGV;
my $grepping = 0;
my %look_for_commits = ();
if (@ARGV) {
	my $filename = shift @ARGV;
	open(my $fd, $filename);
	my @commits = <$fd>;
	close($fd);
	chomp(@commits);
	foreach my $commit (@commits) {
		if ($commit =~ /^[a-zA-Z0-9]+$/) {
			$look_for_commits{$commit} = 1;
		}
	}
	$grepping = keys %look_for_commits;
}

# first arg is the revision to start from
my $start_revision = $ARGV[1] || undef;

my $projects = $repo->projects;
my $project = $repo->get_project( name=>'');
my $history = $project->get_history_by_time( start => 0, end => time());
my $commits = $history->commits();
bluewarn("Got History");

#my $csv = Text::CSV->new;

my %last = ();
my %content = (); # store refs to scalars!
foreach my $commit (@$commits) {
    #my $contents = $commit->contents();
    my $cid   = $commit->revision();
    
    # skip til we find it
    if ($start_revision) {
        if ($cid eq $start_revision) {
            $start_revision = undef;
        } else {
            next;
        }
    }
    $start_revision = undef;
    warn color("bold red"), $cid, color("reset");
    my $author = $commit->author();
    my $committer = $commit->committer();
    my $time  = $commit->time();
    my $nicetime = $time;
    my @contents = @{ $commit->contents() };
    my %newcontent = ();
    my $diffs = 0;
    for my $commitable (@contents) {
        eval {
            my $name = $commitable->name;
            if ($name =~ /\.java$/) {
                my $content = $commitable->content();
                $content{$name} = \$content;
            } #if
        }; #eval
        if ($@) {
            warn color("yellow on_magenta"),$@,color("reset");
        } #if
    } # for
    # 
    # 
    # if there were difference lets calculate some entropy
    my $diff = $commit->as_diff();
    my $files = $diff->files;
    foreach my $file (@$files) {
        my $path    = $file->path;
        next unless ($path =~ /\.java$/);
        my $changes = $file->changes;
        my @out = ();
        foreach my $change (@$changes) {
            if ($change->{type} eq 'ADD' || $change->{type} eq 'MODIFY') {
                push @out, $change->text();
            }
        }
        if (@out) {
            # value ref 
            my $str = join($/,@out).$/;
            $newcontent{$path} = \$str;
        }
    }
    #warn Dumper(\%newcontent);
    yellowwarn( "Number of files changed: ".scalar(keys %newcontent) );
    if ( keys %newcontent ) {
        # write out the text to a file
        my $corpus_file      = "$TMPDIR/${nicetime}-$cid-corpus-added";
        my $lex_corpus_file  = "$TMPDIR/${nicetime}-$cid-corpus-added.lexed.txt";
        my $commit_file      = "$TMPDIR/${nicetime}-$cid-added";
        my $lex_commit_file  = "$TMPDIR/${nicetime}-$cid-added.lexed.txt";
        my $corpus_length = write_corpus( $corpus_file, \%content );
        my $commit_length = write_corpus( $commit_file, \%newcontent );
        warn color("green"),"$cid $corpus_length $commit_length",color("reset");
        # lex it
        lex_file( $corpus_file, $lex_corpus_file );
        lex_file( $commit_file, $lex_commit_file );
        # entropy it
        my %entropy = entropy_measures( $lex_corpus_file, $lex_commit_file, smoothing => "ModKN" );
        {
            open(my $outfd, ">", "$OUTPUTDIR/${nicetime}-${cid}-${order}-added");
            my $str = join(" ",$nicetime, $cid, $corpus_length, $commit_length, 
                           map { floform($_) } ($entropy{perplexity}, 
                                                $entropy{cross_entropy},
                                                $entropy{corcor}->{perplexity},
                                                $entropy{corcor}->{cross_entropy},
                                                $entropy{comcom}->{perplexity},
                                                $entropy{comcom}->{cross_entropy},
                                                $entropy{comcor}->{perplexity},
                                                $entropy{comcor}->{cross_entropy},
                                                $entropy{corcor}->{perplexity} -  $entropy{corcom}->{perplexity})
                          ).$/;
            print $str;
            print $outfd $str;
            close($outfd);
            #clean up the created files
            unlink($corpus_file);
            unlink($lex_corpus_file);
            unlink($commit_file);
            unlink($lex_commit_file);

        }
    }
}

if ($ZEROMQ) {
    $socket->close();
    $ctxt->term();
}

sub run_estimate {
    my ($corpus, $commit, %h) = @_;
    my $smooth = $h{smoothing} || "ModKN";
    my $perplexity = "NaN";
    my $cross_entropy = "NaN"; 
    my @v = ();
    if ($corpus eq $commit) {
        @v = `$ESTIMATE -f 10 -o $order -t $corpus -smoothing $smooth -eval-perp $commit`;
        my ($perp,$crap,$cross) = @v[ $#v-2 .. $#v ]; # last 3 elements
        #0.030	Perplexity Evaluations:
        #0.030		./estimate-ngram	39.782
        #0.030	Cross Entropy Evaluations:
        #0.030		./estimate-ngram	5.138
        chomp($perp);
        chomp($cross);
        my @vals = split(/\s+/, $perp);
        $perplexity = $vals[2];
        $perplexity = ($perplexity =~ /^[0-9\.Ee+-]+$/)?$perplexity:"NaN";
        my @vals = split(/\s+/, $cross);
        $cross_entropy = $vals[2];
        $cross_entropy = ($cross_entropy =~ /^[0-9\.Ee+-]+$/)?$cross_entropy:"NaN";
    } else {
        @v = `$ESTIMATE -o $order -t $corpus -smoothing $smooth -eval-perp $commit`;
        my $line = pop @v;
        chomp($line);
        my @vals = split(/\s+/, $line);
        $perplexity = $vals[2];
        $perplexity = ($perplexity =~ /^[0-9\.Ee+-]+$/)?$perplexity:"NaN";
        $cross_entropy = ($perplexity==0)?"NaN":(log($perplexity)/log(2));
    }
    return (
            perplexity => $perplexity,
            cross_entropy => $cross_entropy,
           );    
}
sub entropy_measures {
    my ($corpus, $commit, %h) = @_;
    my %corcom = run_estimate( $corpus, $commit, %h);
    my %corcor = run_estimate( $corpus, $corpus, %h);
    my %comcom = run_estimate( $commit, $commit, %h);
    my %comcor = run_estimate( $commit, $corpus, %h);
    return (
            perplexity => $corcom{perplexity},
            cross_entropy => $corcom{cross_entropy},
            corcom => \%corcom,
            corcor => \%corcor,
            comcom => \%comcom,
            comcor => \%comcor,
           );    
}
sub floform {
    my ($v) = @_;
    sprintf('%0.5g',$v);
}

sub write_corpus {
    my ($corpus_file, $content) = @_;
    my $corpus_length = 0;
    open( my $fd , ">", $corpus_file);
    while (my($key,$valref) = each %$content) {
        if (ref($valref)) {
            $corpus_length += length($$valref);
            print $fd $$valref;
        }
    }
    close( $fd );
    return $corpus_length;
}
sub bluewarn {
    warn color("blue"),@_,color("reset");
}
sub yellowwarn {
    warn color("yellow"),@_,color("reset");
}
