#!/usr/bin/perl
use strict;
use Parallel::ForkManager;
use FileHandle;
use IPC::Open2;
#use Text::CSV;
use Digest::MD5 qw(md5 md5_hex md5_base64);
use Term::ANSIColor;
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
        warn color("blue"),"Reading $filein and writing $fileout",color("reset");
        open(my $fd, $filein);
        my @in = <$fd>;
        close($fd);
        $socket->send( "+comment +code$/" . join("", @in)  );
        my $msg = $socket->recv();
        my $out = $msg->data();
        $out =~ s/[\r\n]/ /g;
        $out =~ s/; /;\n/g;
        open(my $fd, ">", $fileout);
        print $fd $out;
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
my $order = $ENV{ORDER} || 3;

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
                my $md5 = md5_base64($content);
                my $diff = ($md5 eq $last{$name})?1:0;
                #warn "$name $diff $md5 $last{$name}$/";
                $last{$name} = $md5;
                if (!$diff) {
                    $newcontent{$name} = \$content;
                    $diffs++;
                }
            }
        };
        if ($@) {
            warn color("yellow on_magenta"),$@,color("reset");
        }
    }


    # if there were difference lets calculate some entropy
    if ($diffs > 0) {
        # write out the text to a file
        my $corpus_file = "$TMPDIR/${nicetime}-$cid-corpus";
        my $lex_corpus_file  = "$TMPDIR/${nicetime}-$cid-corpus.lexed.txt";
        my $commit_file = "$TMPDIR/${nicetime}-$cid";
        my $lex_commit_file  = "$TMPDIR/${nicetime}-$cid.lexed.txt";
        my $corpus_length = write_corpus( $corpus_file, \%content );
        my $commit_length = write_corpus( $commit_file, \%newcontent );
        warn color("green"),"$cid $corpus_length $commit_length",color("reset");
        # lex it
        lex_file( $corpus_file, $lex_corpus_file );
        lex_file( $commit_file, $lex_commit_file );
        # entropy it
        my %entropy = entropy_measures( $lex_corpus_file, $lex_commit_file, smoothing => "ModKN" );
        {
            open(my $fd, ">", "$OUTPUTDIR/${nicetime}-${cid}-${order}");
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
            print $fd $str;
            close($fd);
            #clean up the created files
            unlink($corpus_file);
            unlink($lex_corpus_file);
            unlink($commit_file);
            unlink($lex_commit_file);
        }
    }

    # update the content
    for my $key (keys %newcontent) {
        $content{$key} = $newcontent{$key};
    }
}

if ($ZEROMQ) {
    $socket->close();
    $ctxt->term();
}

sub run_estimate {
    my ($corpus, $commit, %h) = @_;
    my $smooth = $h{smoothing} || "ModKN";
    my @v = `$ESTIMATE -o $order -t $corpus -smoothing $smooth -eval-perp $commit`;
    #warn @v;
    my $line = pop @v;
    chomp($line);
    my @vals = split(/\s+/, $line);
    my $perplexity = $vals[2];
    $perplexity = ($perplexity =~ /^[0-9\.Ee+-]+$/)?$perplexity:0;
    my $cross_entropy = ($perplexity==0)?0:(log($perplexity)/log(2));
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
        $corpus_length += length($$valref);
        print $fd $$valref;
    }
    close( $fd );
    return $corpus_length;
}
sub bluewarn {
    warn color("blue"),@_,color("reset");
}
