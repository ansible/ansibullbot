#!/usr/bin/python

# THIS IS STILL NOT A GREAT SCRIPT
# (maybe one day it will be a good one)

# TODOs:
#   * Fix handling of multi-file PRs (and decide policy)
#   * Simplify to only the useful output

# Useful! https://developer.github.com/v3/pulls/
# Useful! https://developer.github.com/v3/issues/comments/

import requests, json, yaml, sys, pprint, argparse

parser = argparse.ArgumentParser(description='Triage various PR queues for Ansible.')
parser.add_argument("ghuser", type=str, help="Github username of triager")
parser.add_argument("ghpass", type=str, help="Github password of triager")
parser.add_argument("ghrepo", type=str, choices=['core','extras'], help="Repo to be triaged")
parser.add_argument('--verbose', '-v', action='store_true', help="Verbose output")
parser.add_argument('--pr', type=str, help="Triage only the specified pr")
args=parser.parse_args()

#------------------------------------------------------------------------------------
# Here's initialization of various things. 
#------------------------------------------------------------------------------------
ghuser=args.ghuser
ghpass=args.ghpass
ghrepo=args.ghrepo
repo_url = 'https://api.github.com/repos/ansible/ansible-modules-' + ghrepo + '/pulls'
if args.pr:
    single_pr = args.pr
else:
    single_pr = ''
if args.verbose:
    verbose = true
else:
    verbose = ''
args = {'state':'open', 'page':1}
botlist = ['gregdek','robynbergeron']

#------------------------------------------------------------------------------------
# Here's the boilerplate text.
#------------------------------------------------------------------------------------
boilerplate = {
    'shipit': "Thanks again to @{s} for this PR, and thanks @{m} for reviewing. Marking for inclusion.",
    'community_review_existing': 'Thanks @{s}. @{m} please review according to guidelines (http://docs.ansible.com/ansible/developing_modules.html#module-checklist) and comment with text \'shipit\' or \'needs_revision\' as appropriate.',
    'core_review_existing': 'Thanks @{s} for this PR. This module is maintained by the Ansible core team, so it can take a while for patches to be reviewed. Thanks for your patience.',
    'community_review_new': 'Thanks @{s} for this new module. When this module receives \'shipit\' comments from two community members and any \'needs_revision\' comments have been resolved, we will mark for inclusion.',
    'shipit_owner_pr': 'Thanks @{s}. Since you are the owner of this module, we are marking this PR for inclusion.',
    'needs_rebase': 'Thanks @{s} for this PR. Unfortunately, it is not mergeable in its current state due to merge conflicts. Please rebase your PR. When you are done, please comment with text \'ready_for_review\' and we will put this PR back into review.',
    'needs_revision': 'Thanks @{s} for this PR. The maintainer of this module has asked for revisions to this PR. Please make the suggested revisions. When you are done, please comment with text \'ready_for_review\' and we will put this PR back into review.'
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
    pull = requests.get(urlstring, auth=(ghuser,ghpass)).json()

    #++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
    # DEBUG: Dump JSON to /tmp for analysis if needed
    #++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
    #debugfileid = '/tmp/' + str(pull['number'])
    #debugfile = open(debugfileid, 'w')
    #debugstring = str(pull)
    #print >>debugfile, debugstring
    #debugfile.close()
        
    #----------------------------------------------------------------------------
    # Initialize an empty local list of PR labels; we'll need it later.
    #----------------------------------------------------------------------------
    pr_labels = []
    
    #----------------------------------------------------------------------------
    # Pull the list of files being edited so we can find maintainers.
    # (Warn if there's more than one; we can't handle that case yet.)
    #----------------------------------------------------------------------------
    # Now pull the text of the diff.
    diff = requests.get(pull['diff_url'], auth=(ghuser,ghpass), verify=False).text

    # Grep the diff for affected files.
    pyfilecounter = 0
    for line in diff.split('\n'):
        # The 'diff --git' line contains the file name.
        if 'diff --git' in line:
            # This split gives us the file name.
            pr_filename = line.split(' b/')[1]
            # Another split gives us the extension.
            pr_fileextension = pr_filename.split('.')[-1]
            if pr_fileextension == 'py':
                pyfilecounter += 1
    # if multiple .py files are included in the diff, complain.
    if pyfilecounter == 0:
        if verbose:
            print "  WARN: no python files in this PR"
    if pyfilecounter > 1:
        if verbose:
            print "  WARN: multiple python files in this PR"
    if verbose:
        print "  Filename:", pr_filename

    #----------------------------------------------------------------------------
    # Look up the files in the local DB to see who maintains them.
    # (Warn if there's more than one; we can't handle that case yet.)
    #----------------------------------------------------------------------------
    maintainer_found = 0
    if ghrepo == "core":
        f = open('MAINTAINERS-CORE.txt')
    elif ghrepo == "extras":
        f = open('MAINTAINERS-EXTRAS.txt')
    for line in f:
        if pr_filename in line:
            pr_maintainer = (line.split(': ')[-1]).rstrip()
            maintainer_found = 1
            break
    f.close()
    if (maintainer_found == 0):
        pr_maintainer = ''

    #----------------------------------------------------------------------------
    # Pull the list of labels on this PR and shove them into pr_labels.
    #----------------------------------------------------------------------------
    issue = requests.get(pull['issue_url'], auth=(ghuser,ghpass)).json()

    # Print labels for now, so we know whether we're doing the right things
    for label in issue['labels']:
        pr_labels.append(label['name'])

    #----------------------------------------------------------------------------
    # Get and print key info about the PR.
    #----------------------------------------------------------------------------
    print " "
    print "****************************************************"
    print pull['number'], '---', pull['title']
    pr_submitter = pull['user']['login']
    print "  Labels: ", pr_labels
    print "  Submitter: ", pr_submitter
    print "  Maintainer(s): ", pr_maintainer
    print "  Filename(s): ", pr_filename
    print " "
    if verbose:
        print pull['body']

    #----------------------------------------------------------------------------
    # Set our empty list of actions. At the conclusion of triage, this list will
    # contain the set of actions that we forward to the Github API.
    #----------------------------------------------------------------------------
    actions = []

    #----------------------------------------------------------------------------
    # NOW: We have everything we need to do actual triage. In triage, we 
    # assess the actions that need to be taken and push them into a list.
    #
    # First, we handle the "no triaged labels" case: i.e. if none of the 
    # following labels are present: community_review, core_review, needs_revision,
    # needs_rebase, shipit.
    #----------------------------------------------------------------------------

    comments = requests.get(pull['comments_url'], auth=(ghuser,ghpass), verify=False)

    # if (len(pr_labels) == 0):
    if (('community_review' not in pr_labels)
      and ('core_review' not in pr_labels)
      and ('needs_revision' not in pr_labels)
      and ('needs_info' not in pr_labels)
      and ('needs_rebase' not in pr_labels)
      and ('shipit' not in pr_labels)):
        if (pr_maintainer == 'ansible'):
            actions.append("newlabel: core_review")
            actions.append("boilerplate: core_review_existing")
        elif (pr_maintainer == ''):
            # We assume that no maintainer means new module
            actions.append("newlabel: community_review")
            actions.append("newlabel: new_plugin")
            actions.append("boilerplate: community_review_new")
        elif (pr_submitter in pr_maintainer):
            actions.append("newlabel: shipit")
            actions.append("newlabel: owner_pr")
            actions.append("boilerplate: shipit_owner_pr")
        else:
            actions.append("newlabel: community_review")
            actions.append("boilerplate: community_review_existing")
 
    #------------------------------------------------------------------------
    # Does this PR need to be (newly) rebased? If so, label and boilerplate.
    #------------------------------------------------------------------------
    if (pull['mergeable'] == 'false'):
        print "WARN: not mergeable!"
        if ('needs_rebase' not in pr_labels):
            actions.append("newlabel: needs_rebase")
            actions.append("boilerplate: needs_rebase")

    #------------------------------------------------------------------------
    # Has PR been rebased at our request? If so, remove needs_rebase
    # label and put into the appropriate review state.
    #------------------------------------------------------------------------
    if ((pull['mergeable'] == 'true')
      and ('needs_rebase' in pr_labels)):
        actions.append("unlabel: needs_rebase")
        if (pr_maintainer == 'ansible'):
            actions.append("newlabel: core_review")
            actions.append("boilerplate: core_review")
        elif (pr_maintainer == ''):
            actions.append("newlabel: community_review")
            actions.append("boilerplate: community_review_new")
        else:
            actions.append("newlabel: community_review")
            actions.append("boilerplate: community_review_existing")

    #----------------------------------------------------------------------------
    # Now let's add filename-based labels: cloud, windows, networking.
    # label and put into the appropriate review state.
    #----------------------------------------------------------------------------
    if (pr_filename.split('/')[0] == 'cloud') and ('cloud' not in pr_labels):
        actions.append("newlabel: cloud")
    if (pr_filename.split('/')[0] == 'network') and ('networking' not in pr_labels):
        actions.append("newlabel: networking")
    if (pr_filename.split('/')[0] == 'windows') and ('windows' not in pr_labels):
        actions.append("newlabel: windows")

    #----------------------------------------------------------------------------
    # OK, now we start walking through comment-based actions, and push them 
    # into the list. 
    #
    # NOTE: we walk through comments MOST RECENT FIRST.
    #----------------------------------------------------------------------------
    for comment in reversed(comments.json()):
            
        if verbose:
            print " " 
            print "==========>  Comment at ", comment['created_at'], " from: ", comment['user']['login']
            print comment['body']

        #------------------------------------------------------------------------
        # Is the last comment from a bot user?  Then break.
        #------------------------------------------------------------------------
        if (comment['user']['login'] in botlist):
            if verbose:
                print "  STATUS: no useful state change since last pass (", comment['user']['login'], ")"
            break

        #------------------------------------------------------------------------
        # Has maintainer said 'shipit'? Then label/boilerplate/break.
        #------------------------------------------------------------------------
        if ((comment['user']['login'] == pr_maintainer)
          and ('shipit' in comment['body'])):
            actions.append("unlabel: community_review")
            actions.append("unlabel: core_review")
            actions.append("unlabel: needs_info")
            actions.append("unlabel: needs_revision")
            actions.append("newlabel: shipit")
            actions.append("boilerplate: shipit")
            break

        #------------------------------------------------------------------------
        # Has maintainer said 'needs_revision'? Then label/boilerplate/break.
        #------------------------------------------------------------------------
        if ((comment['user']['login'] == pr_maintainer)
          and ('needs_revision' in comment['body'])):
            actions.append("unlabel: community_review")
            actions.append("unlabel: core_review")
            actions.append("unlabel: needs_info")
            actions.append("unlabel: shipit")
            actions.append("newlabel: needs_revision")
            actions.append("boilerplate: needs_revision")
            break

        #------------------------------------------------------------------------
        # Has submitter said 'ready_for_review'? Then label/boilerplate/break.
        #------------------------------------------------------------------------
        if ((comment['user']['login'] == pr_submitter)
          and ('ready_for_review' in comment['body'])):
            actions.append("unlabel: needs_revision")
            actions.append("unlabel: needs_info")
            if (pr_maintainer == 'ansible'):
                actions.append("newlabel: core_review")
                actions.append("boilerplate: core_review")
            elif (pr_maintainer == ''):
                actions.append("newlabel: community_review")
                actions.append("boilerplate: community_review_new")
            else:
                actions.append("newlabel: community_review")
                actions.append("boilerplate: community_review_existing")
            break

    #----------------------------------------------------------------------------
    # OK, this PR is done! Now let's print out the list of actions we tallied.
    #
    # In assisted mode, we will ask the user whether we want to take the 
    # recommended actions.
    #
    # In autonomous mode (future), we will take the actions automatically.
    #----------------------------------------------------------------------------

    print " "
    print "RECOMMENDED ACTIONS for ", pull['html_url']
    if actions == []:
        print "  None required"
    else:
        for action in actions:
            print "  ", action

    print " "

    cont = ''

    # If there are actions, ask if we should take them. Otherwise, skip.
    if not (actions == []):
        cont = raw_input("Take recommended actions (y/N)?")

    if cont in ('Y','y'):

        #------------------------------------------------------------------------
        # Now we start actually writing to the issue itself.
        #------------------------------------------------------------------------
        print "LABELS_URL: ", issue['labels_url']
        print "COMMENTS_URL: ", pull['comments_url']
        for action in actions:

            if "unlabel" in action:
                oldlabel = action.split(': ')[-1]
                # Don't remove it if it isn't there
                if oldlabel in pr_labels:
                    pr_actionurl = issue['labels_url'].split("{")[0] + "/" + oldlabel
                    # print "URL for DELETE: ", pr_actionurl
                    try:
                        r = requests.delete(pr_actionurl, auth=(ghuser,ghpass))
                        # print r.text
                    except requests.exceptions.RequestException as e:
                        print e
                        sys.exit(1)

            if "newlabel" in action:
                newlabel = action.split(': ')[-1]
                if newlabel not in pr_labels:
                    pr_actionurl = issue['labels_url'].split("{")[0]
                    payload = '["' + newlabel +'"]'
                    # print "URL for POST: ", pr_actionurl
                    # print "  PAYLOAD: ", payload
                    try:
                        r = requests.post(pr_actionurl, data=payload, auth=(ghuser, ghpass))
                        # print r.text
                    except requests.exceptions.RequestException as e:
                        print e
                        sys.exit(1)

            if "boilerplate" in action:
                # A hack to make the @ signs line up for multiple maintainers
                mtext = pr_maintainer.replace(' ', ' @')
                stext = pr_submitter
                boilerout = action.split(': ')[-1]
                newcomment = boilerplate[boilerout].format(m=mtext,s=stext)
                payload = '{"body": "' + newcomment + '"}'
                pr_actionurl = issue['comments_url']
                # print "URL for POST: ", pr_actionurl
                # print "  PAYLOAD: ", payload
                try:
                    r = requests.post(pr_actionurl, data=payload, auth=(ghuser, ghpass))
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
if single_pr:
    single_pr_url = "https://api.github.com/repos/ansible/ansible-modules-" + ghrepo + "/pulls/" + single_pr
    triage(single_pr_url)

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
        pull_args = {'state':'open', 'page':page}
        r = requests.get(repo_url, params=pull_args, auth=(ghuser,ghpass))

        #----------------------------------------------------------------------------
        # For every open PR:
        #----------------------------------------------------------------------------
        for shortpull in r.json():
 
            # Do some nifty triage!
            triage(shortpull['url'])


#====================================================================================
# That's all, folks!
#====================================================================================
