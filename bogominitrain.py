#!/usr/bin/env python

"""
Version 0.9
Requires bogofilter 0.94.4 or later.

Example:
  bogominitrain.py -fnv -b "-o 0.95,0.35" hamfile spamfile

Notes:

    This is a python rewrite of the original perl bogominitrain.pl that is
    included with bogofilter. I rewrote it so I could debug it. The original
    had a problem with my spamfile of 25000 message. It would just hang.

    This version also handles arguments a bit differently. It takes 1 hamfile
    and 1 spamfile instead of the shell expanded string. It also will
    automatically find your bogofilter database, so it isn't required on the
    command line. Though you can provide it if you want to.

    There are a couple other small changes. Just run with -h for a rundown.

    It still uses the  "train on error" process just like the original. Thus
    building minimal wordlists that can still correctly score all messages.
    This aspect of the script is unchanged from the perl version.

    It may be a good idea to run this script command several times or use the
    '-f' option to run the script until no scoring errors occur (training to
    exhaustion).

    Tips snipped from the original docs:

    To improve bogofilter's accuracy, use bogofilter's -o option to
    create a "security margin" around your normal cutoff during
    training.  The script will train so that the messages will avoid
    this interval, i.e., all messages in your training mboxes will be
    marked as ham or spam with values far from your production cutoff.
    For example you might want to use spam_cutoff=0.5 and '-o 0.8,0.2'
    as bogofilter options.  If you would rather use tri-state mode, you
    can just center this around 0.5 and again use '-o 0.8,0.2'.

    To correct the classification of a message, just move it to the correct
    mbox and repeat the full training process (which will add a few messages to
    the existing database).

"""

from optparse import OptionParser, make_option
import mailbox
import sys, os, re, time

option_list = [
    make_option("-b", "--bogofilter", dest="bogofilter",
        help="Passed through to bogofilter as arguments (put in quotes)."),
    make_option("-c", "--compact", action="store_true", dest="compact",
        default=False, help="Compacts the database at the end."),
    make_option("-d", "--database-directory", dest="database",
        metavar="DIRECTORY", help="Bogofilter database directory."),
    make_option("-f", "--force", action="store_true", dest="force",
        default=False, help="Runs the program until no errors remain."),
    make_option("-i", "--info", action="store_true", dest="info",
        default=False, help="Show extended documentation and exit."),
    make_option("-n", "--noreps", action="store_true", dest="noreps",
        default=False, help="Prevents messages from being added more than"
            "once. Recommended to use with -f to prevent errors left at end."),
    make_option("-s", "--save", action="store_true", dest="save",
        default=False, help="Saves the messages used for training to files"
            " bogominitrain.ham and bogominitrain.spam"),
    make_option("-v", "--verbose", action="count", dest="verbose",
        help="This switch produces info on messages used for training. "
            "Given twice also lists messages not used for training."),
    ]
usage = "usage %prog [options] ham-mbox spam-mbox"
version = __doc__.split('\n')[1]

parser = OptionParser(usage=usage, option_list=option_list, version=version)
(options, args) = parser.parse_args()

if options.info:
    print __doc__
    sys.exit(0)

if len(args) < 2:
    print "Not enough arguments."
    parser.print_help()
    sys.exit(1)
else:
    hambox_file, spambox_file = args


# Find database directory if not specified
if not options.database:
    # start with shortcut for common case
    default = os.path.expandvars("$HOME/.bogofilter")
    if os.path.exists(default):
        options.database = default
    # ok. how about environmental var.
    if os.environ.has_key('BOGOFILTER_DIR'):
        options.database = os.environ['BOGOFILTER_DIR']
    # No. Then lets check the config files.
    config_files=[os.path.expandvars("$HOME/.bogofilter.cf"),
            "/etc/bogofilter.cf"]
    find_dir = re.compile("[^#]*\s*bogofilter_dir=([^#]+).*").match
    for config_file in config_files:
        if options.database: break
        if os.path.exists(config_file):
             for line in open(config_file):
                 dir_match = find_dir(line)
                 if dir_match:
                     options.database = dir_match.group(1).strip()
                     break
    if options.database:
        # fully expand path
        db = os.path.expanduser(options.database)
        options.database = os.path.expandvars(db)
    else:
        print >> sys.stderr, (
                "Database directory could not be determined.\n"
                "Please use -d argument to specify it.\n"
                "See help (-h) for options")
        sys.exit(1)

# set some initial values
bogofilter = "bogofilter"
if options.bogofilter:
    bogofilter = "%s %s" % (bogofilter, options.bogofilter)
bogofilter = "%s -d %s" % (bogofilter, options.database)

wordlist = os.path.join(options.database, 'wordlist.db')
if os.path.exists(wordlist):
    print "Starting with database containing:"
    os.system("bogoutil -w %s .MSG_COUNT" % options.database)

if not (os.path.exists(wordlist) and os.path.getsize(wordlist)):
    os.system(bogofilter + " -n < /dev/null")

try:
    hambox = mailbox.UnixMailbox(file(hambox_file,'r'), lambda fp: fp)
    spambox = mailbox.UnixMailbox(file(spambox_file,'r'), lambda fp: fp)
except IOError, arg:
    print
    print 'Cannot open spam/ham file!'
    print arg.strerror, arg.filename
    sys.exit(1)

runs = 0
ham_total = sum(1 for _ in hambox)
spam_total = sum(1 for _ in spambox)
status_conv = ("spam", "ham", "unsure", "error" )
trainedham = dict.fromkeys(range(1,ham_total+1),0)
trainedspam = dict.fromkeys(range(1,spam_total+1),0)

def eof(mbox):
    seekp = mbox.seekp
    result = not bool(mbox.next())
    mbox.seekp = seekp
    return result

def process(mbox, mtype, added, trained, count, ocount, total, ototal):
    """ mbox    = hambox, spambox
        mtype   = "spam","ham"
        added   = ham_added, spam_added
        trained = trainedspam, trainedham
        count   = ham_count, spam_count
        ocount  = opposite count
        total   = ham_total, spam_total
        ototal  = opposite total
    """
    if not (eof(mbox) or (count*ototal > ocount*total)):
        msg = mbox.next()
        if msg:
            msg = msg.read()
            count += 1
            pipe = popen(bogofilter,"w")
            pipe.write(msg)
            # bitshift to convert to exit status
            status = status_conv[(pipe.close() or 0) >> 8]
            if not status == mtype:
                if not (options.noreps and trained[count]):
                    trainer = mtype == "ham" and " -n" or " -s"
                    pipe = popen(bogofilter+trainer,"w")
                    pipe.write(msg)
                    pipe.close()
                    added += 1
                    trained[count] += 1
                    if options.verbose:
                        print status,
                        print "Training %s message %s" % (mtype, count),
                        if trained[count] > 1:
                            print "(%s)" % trained[count]
                        print
                    if options.save:
                        open("bogominitrain.%s" % mtype,"a").write(msg)
                elif options.verbose:
                    print status,
                    print "-- Skipping %s message %s" % (mtype, count)
            elif options.verbose:
                print status,
                print "-- Not training %s message %s" % (mtype, count)
            #
    return count, added

# reset mbox objects back to beginning
hambox.seekp = 0
spambox.seekp = 0

popen = os.popen
while True:
    starttime = time.time()
    runs += 1
    ham_added = spam_added = 0
    ham_count = spam_count = 0
    skip_ham = skip_spam = 0

    while True:
        ham_count, ham_added = process(
                hambox, "ham", ham_added, trainedham,
                ham_count, spam_count, ham_total, spam_total)
        spam_count, spam_added = process(
                spambox, "spam", spam_added, trainedspam,
                spam_count, ham_count, spam_total, ham_total)
        # 2-loop exit
        if eof(hambox) and eof(spambox):
            break

    hambox.seekp = 0
    spambox.seekp = 0

    print
    print "End of run #%d (in %.2fs):" % (runs ,(time.time() - starttime))
    print "Read %d ham and %d spam." % (ham_count, spam_count)
    print "Added %d ham (skipping %d) and" % (ham_added, skip_ham),
    print "%d spam (skipping %d) to the database" % (spam_added, skip_spam)
    os.system("bogoutil -w %s .MSG_COUNT" % options.database)

    false_negs = false_pos = 0
    if (ham_added + spam_added) != 0:
        starttime = time.time()
        false_negs = int(popen("cat %s | %s -TM | grep -cv \^S"
                % (spambox_file,bogofilter)).read())
        false_pos = int(popen("cat %s | %s -TM | grep -cv \^H"
                % (hambox_file,bogofilter)).read())
        print
        print "False Negatives", false_negs
        print "False Positives", false_pos
        print "Verification done in %.2fs" % (time.time() - starttime)
        time.sleep(2)

    # main loop exit
    if (false_negs+false_pos)==0 or (ham_added+spam_added)==0 or \
            not options.force:
        break

if options.force:
    print
    print "%d run%s" % (runs ,(runs>1 and "s")),
    print "needed to close off."

if options.compact:
  print "Compacting database ..."
  os.system("bf_compact %s && rm -rf %s.old" % ((options.database,)*2))



