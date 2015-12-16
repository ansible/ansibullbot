#!/usr/bin/python

# THIS IS ALSO NOT A GREAT SCRIPT
# (copied and pasted from prbot!)

# REQUIREMENTS:
# * What should this actually do?
# 
# First, what is BASIC BASIC TRIAGE? It's "where's the bug and who owns it?"
# 
# Which means: name of file. We can infer the maintainer from that, and then
# the maintainer can ask the necessary questions.
# 
# IF: nothing found in [module: foo] or [filename: foo] 
# THEN boilerplate should be "can someone help by entering the name of file or module 
#   affected in this format [filename: foo.py]? This is to determine maintainer to ping."
# 
# IF: [module: foo.py] is found
# THEN: did a bot ping the maintainer? If not, ping the maintainer.
# 
# IF BOTH THESE THINGS ARE TRUE, IGNORE.
#
# (Note: we can add timeouts later.)

import requests, json, yaml, sys, argparse, time

parser = argparse.ArgumentParser(description='Triage various PR queues for Ansible. (NOTE: only useful if you have commit access to the repo in question.)')
parser.add_argument("ghuser", type=str, help="Github username of triager")
parser.add_argument("ghpass", type=str, help="Github password of triager")
parser.add_argument("ghrepo", type=str, choices=['core','extras'], help="Repo to be triaged")
parser.add_argument('--verbose', '-v', action='store_true', help="Verbose output")
parser.add_argument('--debug', '-d', action='store_true', help="Debug output")
parser.add_argument('--pause', '-p', action='store_true', help="Always pause between issues")
parser.add_argument('--issue', '-i', type=str, help="Triage only the specified issue")
args=parser.parse_args()

#------------------------------------------------------------------------------------
# Here's initialization of various things. 
#------------------------------------------------------------------------------------
ghuser=args.ghuser
ghpass=args.ghpass
ghrepo=args.ghrepo
repo_url = 'https://api.github.com/repos/ansible/ansible-modules-' + ghrepo + '/issues'
if args.issue:
    single_issue = args.issue
else:
    single_issue= ''
if args.verbose:
    verbose = 'true'
else:
    verbose = ''
if args.debug:
    debug = 'true'
else:
    debug = ''
if args.pause:
    always_pause = 'true'
else:
    always_pause = ''
args = {'state':'open', 'page':1}
botlist = ['gregdek','robynbergeron']

#------------------------------------------------------------------------------------
# Here's the boilerplate text.
#------------------------------------------------------------------------------------
boilerplate = {
    'ping': "Ping @{m} to let you know about this issue. Thanks!"
}

#------------------------------------------------------------------------------------
# Here's the triage function. It takes a PR id and does all of the necessary triage
# stuff.
#------------------------------------------------------------------------------------

def triage(urlstring):
    #----------------------------------------------------------------------------
    # Get the more detailed PR data from the API:
    #----------------------------------------------------------------------------
    if verbose:
        print "URLSTRING: ", urlstring
    issue = requests.get(urlstring, auth=(ghuser,ghpass)).json()

    #++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
    # DEBUG: Dump JSON to /tmp for analysis if needed
    #++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
    if debug:
        debugfileid = '/tmp/issue-' + str(issue['number'])
        print "DEBUG JSON TO: ", debugfileid
        debugfile = open(debugfileid, 'w')
        print >>debugfile, json.dumps(issue, ensure_ascii=True, indent=4, separators=(',', ': '))
        debugfile.close()

    #----------------------------------------------------------------------------
    # Are we a pull request? If so, then break. We don't do pull requests.
    #----------------------------------------------------------------------------
    try:
        if issue['pull_request']:
            print "Ignoring Pull Request ", issue['number']
            return
    except:
        # noop
        pass
        
    #----------------------------------------------------------------------------
    # Pull the list of labels.
    #----------------------------------------------------------------------------
    issue_labels = []
    for label in issue['labels']:
        issue_labels.append(label['name'])
    
    #----------------------------------------------------------------------------
    # Get and print key info about the issue.
    #----------------------------------------------------------------------------
    print " "
    print "****************************************************"
    print issue['number'], '---', issue['title']
    issue_submitter = issue['user']['login']
    print "  Labels: ", issue_labels
    print "  Submitter: ", issue_submitter
    # print "  Maintainer(s): ", issue_maintainers
    # print "  Filename(s): ", issue_filename
    print " "
    if verbose:
        print issue['body']

    #----------------------------------------------------------------------------
    # NOW: We have everything we need to do actual triage. In triage, we 
    # assess the actions that need to be taken and push them into a list. 
    # Get our comments, and set our empty actions list.
    #----------------------------------------------------------------------------
  
    comments = requests.get(issue['comments_url'], auth=(ghuser,ghpass), verify=False)
    actions = []
 
    #----------------------------------------------------------------------------
    # Kill all P3-P5 tags, every time. No more low priority tags.
    #----------------------------------------------------------------------------
    if ('P3') in issue_labels:
        actions.append("unlabel: P3")
    if ('P4') in issue_labels:
        actions.append("unlabel: P4")
    if ('P5') in issue_labels:
        actions.append("unlabel: P5")

    #----------------------------------------------------------------------------
    # OK, now we start walking through comment-based actions, and push whatever
    # we find into the action list. 
    #
    # NOTE: we walk through comments MOST RECENT FIRST. Whenever we find a
    # meaningful state change from the comments, we break; thus, we are always
    # acting on what we perceive to be the most recent meaningful comment, and
    # we ignore all older comments.
    #
    # In this case, we're looking to figure out four things:
    #   - issue_filename. What file is this issue being reported against?
    #   - issue_maintainer. Which we can only determine from issue_filename.
    #   - maintainer_pinged. Have we reached out to the maintainer yet?
    #   - maintainer_active. If we have reached out, is the maintainer
    #     actively handling the issue?
    # 
    # This requires multiple passes through each set of comments to figure out.
    # (At least it does for me.)
    #----------------------------------------------------------------------------

    #----------------------------------------------------------------------------
    # First pass: look for the presence of issue_filename. If not found, 
    # ask for help triaging and tag with "needs_triage". Note that most
    # recent *always* wins, and it doesn't matter who entered it.
    #----------------------------------------------------------------------------

    issue_filename = ''
    for comment in reversed(comments.json()):
            
        if verbose:
            print " " 
            print "==========>  Comment at ", comment['created_at'], " from: ", comment['user']['login']
            print comment['body']

        if ('[module' in comment['body']):
            # FIXME: this should be changed to a regex. We can't assume
            # long-term that this text is alone in the comment.
            issue_filename = (comment['body'].split(':')[-1]).rstrip()
            print "  Filename found: ", issue_filename 
            break

    #----------------------------------------------------------------------------
    # No filename found? That means it needs to be triaged.
    #----------------------------------------------------------------------------

    if (issue_filename == ''):
        actions.append('boilerplate: triage_needed')
        actions.append('label: triage_needed')    

    #----------------------------------------------------------------------------
    # Filename found? Good. Now try to find the maintainer in the lookup.
    #----------------------------------------------------------------------------

    else:   

        # Identify maintainers 

        maintainers_found = ''
        if ghrepo == "core":
            f = open('MAINTAINERS-CORE.txt')
        elif ghrepo == "extras":
            f = open('MAINTAINERS-EXTRAS.txt')
        for line in f:
            if issue_filename in line:
                issue_maintainers = (line.split(': ')[-1]).rstrip()
                maintainers_found = 'True'
                break
        f.close()

        if not maintainers_found:
            print "  WARNING: no maintainers found for this file"
            issue_maintainers = ''

        else:

            #--------------------------------------------------------------------
            # OK, we have a filename and a maintainer. Now let's look to see if
            # at least one maintainer has been pinged by a bot. If yes, we're 
            # done! If not, ping the maintainers!
            #--------------------------------------------------------------------

            maintainer_pinged = ''
            for comment in reversed(comments.json()):
                if (comment['user']['login'] in botlist):
                    for maintainer in issue_maintainers:
                        if maintainer in comment['body']:
                            maintainer_pinged = 'yes'

            if maintainer_pinged:
                actions.append('boilerplate: ping_maintainer')    

    #----------------------------------------------------------------------------
    # OK, triage is done! Now let's print out the list of actions we tallied.
    #
    # In assisted mode, we will ask the user whether we want to take the 
    # recommended actions.
    #
    # In autonomous mode (future), we will take the actions automatically.
    #----------------------------------------------------------------------------

    print " "
    print "RECOMMENDED ACTIONS for ", issue['html_url']
    if actions == []:
        print "  None required"
    else:
        for action in actions:
            print "  ", action

    print " "

    cont = ''

    # If there are actions, ask if we should take them. Otherwise, skip.
    if (not (actions == [])) or (always_pause):
        cont = raw_input("Take recommended actions (y/N)?")

    if cont in ('Y','y'):

        #------------------------------------------------------------------------
        # Now we start actually writing to the issue itself.
        #------------------------------------------------------------------------
        print "LABELS_URL: ", issue['labels_url']
        print "COMMENTS_URL: ", issue['comments_url']
        for action in actions:

            if "unlabel" in action:
                oldlabel = action.split(': ')[-1]
                # Don't remove it if it isn't there
                if oldlabel in issue_labels:
                    issue_actionurl = issue['labels_url'].split("{")[0] + "/" + oldlabel
                    # print "URL for DELETE: ", issue_actionurl
                    try:
                        r = requests.delete(issue_actionurl, auth=(ghuser,ghpass))
                        # print r.text
                    except requests.exceptions.RequestException as e:
                        print e
                        sys.exit(1)

            if "newlabel" in action:
                newlabel = action.split(': ')[-1]
                if newlabel not in issue_labels:
                    issue_actionurl = issue['labels_url'].split("{")[0]
                    payload = '["' + newlabel +'"]'
                    # print "URL for POST: ", issue_actionurl
                    # print "  PAYLOAD: ", payload
                    try:
                        r = requests.post(issue_actionurl, data=payload, auth=(ghuser, ghpass))
                        # print r.text
                    except requests.exceptions.RequestException as e:
                        print e
                        sys.exit(1)

            if "boilerplate" in action:
                # A hack to make the @ signs line up for multiple maintainers
                mtext = issue_maintainers.replace(' ', ' @')
                stext = issue_submitter
                boilerout = action.split(': ')[-1]
                newcomment = boilerplate[boilerout].format(m=mtext,s=stext)
                payload = '{"body": "' + newcomment + '"}'
                issue_actionurl = issue['comments_url']
                # print "URL for POST: ", issue_actionurl
                # print "  PAYLOAD: ", payload
                try:
                    r = requests.post(issue_actionurl, data=payload, auth=(ghuser, ghpass))
                    # print r.text
                except requests.exceptions.RequestException as e:
                    print e
                    sys.exit(1)
                        
    else:
        print "Skipping."


#====================================================================================
# MAIN CODE START, EH?
#====================================================================================


#------------------------------------------------------------------------------------
# If we're running in single PR mode, run triage on the single PR.
#------------------------------------------------------------------------------------
if single_issue:
    single_issue_url = "https://api.github.com/repos/ansible/ansible-modules-" + ghrepo + "/issues/" + single_issue
    triage(single_issue_url)

#------------------------------------------------------------------------------------
# Otherwise, go get all open PRs and run through them.
#------------------------------------------------------------------------------------
else:
    # First, get number of pages using pagination in Link Headers. Thanks 
    # requests library for making this relatively easy!
    r = requests.get(repo_url, params=args, auth=(ghuser,ghpass))
    lastpage = int(str(r.links['last']['url']).split('=')[-1])

    # Set range for 1..2 for testing only
    # for page in range(1,2):

    for page in range(1,lastpage):
        issue_args = {'state':'open', 'page':page}
        r = requests.get(repo_url, params=issue_args, auth=(ghuser,ghpass))

        #----------------------------------------------------------------------------
        # For every open PR:
        #----------------------------------------------------------------------------
        for shortissue in r.json():
 
            # Do some nifty triage!
            triage(shortissue['url'])


#====================================================================================
# That's all, folks!
#====================================================================================
