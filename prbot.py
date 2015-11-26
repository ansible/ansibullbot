#!/usr/bin/python

# THIS IS STILL NOT A GREAT SCRIPT
# (maybe one day it will be a good one)

# TODOs:
#   * Fix handling of multi-file PRs (and decide policy)
#   * Simplify to only the useful output

# Useful! https://developer.github.com/v3/pulls/
# Useful! https://developer.github.com/v3/issues/comments/

import requests, json, yaml, sys, pprint

ghuser=sys.argv[1]
ghpass=sys.argv[2]
ghrepo=sys.argv[3]
repo_url = 'https://api.github.com/repos/ansible/ansible-modules-' + ghrepo + '/pulls'
args = {'state':'open', 'page':1}
botlist = ['gregdek','robynbergeron']

#------------------------------------------------------------------------------------
# Go get all open PRs.
#------------------------------------------------------------------------------------

# First, get number of pages using pagination in Link Headers. Thanks 
# requests library for making this relatively easy!
r = requests.get(repo_url, params=args, auth=(ghuser,ghpass))
lastpage = int(str(r.links['last']['url']).split('=')[-1])

# Set range for 1..2 for testing only
for page in range(1,2):
# for page in range(1,lastpage):
    args = {'state':'open', 'page':page}
    r = requests.get(repo_url, params=args, auth=(ghuser,ghpass))

    #--------------------------------------------------------------------------------
    # For every open PR:
    #--------------------------------------------------------------------------------
    for shortpull in r.json():

        #----------------------------------------------------------------------------
        # Get the more detailed PR data from the API:
        #----------------------------------------------------------------------------
        pull = requests.get(shortpull['url'], auth=(ghuser,ghpass)).json()

        #++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
        # DEBUG: Dump JSON to /tmp for analysis if needed
        #++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
        # debugfileid = '/tmp/' + str(pull['number'])
        # debugfile = open(debugfileid, 'w')
        # debugstring = str(pull)
        # print >>debugfile, debugstring
        # debugfile.close()
        
        #----------------------------------------------------------------------------
        # Initialize empty list of PR labels; we'll need it later.
        #----------------------------------------------------------------------------
        pr_labels = []

        #----------------------------------------------------------------------------
        # Get the number ID of the PR.
        #----------------------------------------------------------------------------
        pr_number = pull['number']
        print " "
        print pr_number 
        
        #----------------------------------------------------------------------------
        # Get the ID of the submitter of the PR.
        #----------------------------------------------------------------------------
        pr_submitter = pull['user']['login']
        print "  Submitter: ", pr_submitter

        #----------------------------------------------------------------------------
        # Now pull the list of files being edited.
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
                filename = line.split(' b/')[1]
                # Another split gives us the extension.
                fileextension = filename.split('.')[-1]
                if fileextension == 'py':
                    pyfilecounter += 1
        # if multiple .py files are included in the diff, complain.
        if pyfilecounter == 0:
            print "  WARN: no python files in this PR"
        if pyfilecounter > 1:
            print "  WARN: multiple python files in this PR"
        if pyfilecounter == 1:
            print "  Filename:", filename

        #----------------------------------------------------------------------------
        # NEXT: Look up the file in the DB to see who maintains it.
        # (Warn if there's more than one; we can't handle that case yet.)
        #----------------------------------------------------------------------------
        maintainer_found = 0
        if ghrepo == "core":
            f = open('MAINTAINERS-CORE.txt')
        elif ghrepo == "extras":
            f = open('MAINTAINERS-EXTRAS.txt')
        for line in f:
            if filename in line:
                pr_maintainer = (line.split(': ')[-1]).rstrip()
                print "  Maintainer: ", pr_maintainer
                maintainer_found = 1
                break
        f.close()
        if (maintainer_found == 0):
            print "  WARN: No Maintainer Found"
            pr_maintainer = ''

        #----------------------------------------------------------------------------
        # Pull the list of labels on this PR and shove them into pr_labels.
        #----------------------------------------------------------------------------
        issue = requests.get(pull['issue_url'], auth=(ghuser,ghpass)).json()

        # Print labels for now, so we know whether we're doing the right things
        for label in issue['labels']:
            pr_labels.append(label['name'])
        print "  Labels: ", pr_labels

        comments = requests.get(pull['comments_url'], auth=(ghuser,ghpass), verify=False)

        #----------------------------------------------------------------------------
        # NOW: We have everything we need to do actual triage. In triage, we 
        # assess the actions that need to be taken and push them into a list.
        #
        # First, we handle the "no labels at all" case, which means "totally new".
        #----------------------------------------------------------------------------

        # Set an empty list of actions
        actions = []

        if len(pr_labels) == 0:
            if (pr_maintainer == 'ansible'):
                actions.append("label: core_review")
                actions.append("boilerplate: core_review_existing_module")
            elif (pr_maintainer == ''):
                # We assume that no maintainer means new module
                actions.append("label: community_review")
                actions.append("label: new_plugin")
                actions.append("boilerplate: community_review_new_module")
            elif (pr_submitter in pr_maintainer):
                actions.append("label: shipit")
                actions.append("label: owner_pr")
                actions.append("boilerplate: shipit_owner_pr")
            else:
                actions.append("label: community_review")
                actions.append("boilerplate: community_review_existing_module")

        #----------------------------------------------------------------------------
        # OK, now we start walking through comment-based actions, and push them 
        # into the list.
        #----------------------------------------------------------------------------
        for comment in reversed(comments.json()):
            
            print "  Commenter: ", comment['user']['login']
            if (comment['user']['login'] in botlist):
                print "  STATUS: no useful state change since last pass (", comment['user']['login'], ")"
                break

            if pull['mergeable'] == 'false':
                actions.append("label: needs_rebase")
                actions.append("boilerplate: needs_rebase")
                break

            if ((comment['user']['login'] == pr_maintainer)
              and ('shipit' in comment['body'])):
                actions.append("label: shipit")
                actions.append("boilerplate: shipit")
                break

            if ((comment['user']['login'] == pr_maintainer)
              and ('needs_revision' in comment['body'])):
                actions.append("label: needs_revision")
                actions.append("boilerplate: needs_revision")
                break

            if ((comment['user']['login'] == pr_submitter)
              and ('ready_for_review' in comment['body'])):
                if (pr_mainainer == 'ansible'):
                    actions.append("label: core_review")
                    actions.append("boilerplate: back_to_core_review")
                else:
                    actions.append("label: community_review")
                    actions.append("boilerplate: back_to_community_review")
                break

        #----------------------------------------------------------------------------
        # Done. Now let's print out the list of actions we tallied.
        # (Next step will be to use these actions to write to the PRs
        # via the Github API.)
        #----------------------------------------------------------------------------

        print "Actions:"
        if actions == []:
            print "  None required"
        else:
            for action in actions:
                print "  ", action

######################################################################################
