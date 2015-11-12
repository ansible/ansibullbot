#!/usr/bin/python

# THIS IS A VERY BAD SCRIPT
# (maybe one day it will be a good one)

# Useful! https://developer.github.com/v3/pulls/
# Useful! https://developer.github.com/v3/issues/comments/

import requests, json, yaml, sys, pprint

ghuser=sys.argv[1]
ghpass=sys.argv[2]
ghrepo=sys.argv[3]
repo_url = 'https://api.github.com/repos/ansible/ansible-modules-' + ghrepo + '/pulls'
args = {'state':'open', 'page':1}

#------------------------------------------------------------------------------------
# Go get all open PRs.
#------------------------------------------------------------------------------------

# First, get number of pages using pagination in Link Headers. Thanks 
# requests library for making this relatively easy!
r = requests.get(repo_url, params=args, auth=(ghuser,ghpass))
lastpage = int(str(r.links['last']['url']).split('=')[-1])

# Set range for 1..2 for testing only
# for page in range(1,2):
for page in range(1,lastpage):
    args = {'state':'open', 'page':page}
    r = requests.get(repo_url, params=args, auth=(ghuser,ghpass))

    #--------------------------------------------------------------------------------
    # For every open PR:
    #--------------------------------------------------------------------------------
    for pull in r.json():

        
        #----------------------------------------------------------------------------
        # Initialize empty list of PR labels; we'll need it later.
        #----------------------------------------------------------------------------
        pr_labels = []

        #----------------------------------------------------------------------------
        # Get the number ID of the PR.
        #----------------------------------------------------------------------------
        pr_number = pull['number']
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
        # NEXT: Look up the file in the DB to see who owns it.
        # (Warn if there's more than one; we can't handle that case yet.)
        #----------------------------------------------------------------------------
        if ghrepo == "core":
            f = open('MAINTAINERS-CORE.txt')
        elif ghrepo == "extras":
            f = open('MAINTAINERS-EXTRAS.txt')
        for line in f:
            if filename in line:
                pr_maintainer = line.split(': ')[-1] 
                print "  Maintainer: ", pr_maintainer
                break
        f.close()

        #----------------------------------------------------------------------------
        # NEXT: Pull the comments from this PR and put them into an array
        # we can search.
        #----------------------------------------------------------------------------
        print "  Comments URL: ", pull['comments_url']
        comments = requests.get(pull['comments_url'], auth=(ghuser,ghpass), verify=False)
        # Print comments for now, so we know whether we're doing the right things
        for comment in comments.json():
             print "  Comment by: ", comment['user']['login']

        #----------------------------------------------------------------------------
        # OK, now we know who submitted the PR, and who owns it. Now we pull the 
        # list of labels on this PR, and take the appropriate action.
        #----------------------------------------------------------------------------
        issue = requests.get(pull['issue_url'], auth=(ghuser,ghpass)).json()

        # Print labels for now, so we know whether we're doing the right things
        for label in issue['labels']:
            pr_labels.append(label['name'])
            print "  Label: ", label['name']

        # No labels? New issue!
        if len(pr_labels) == 0:
            print "  Status: New PR"
            
        #----------------------------------------------------------------------------
        # Community review? Look for comments for the reviews and take action.
        #----------------------------------------------------------------------------
        if 'community_review' in pr_labels:
            print "  Status: In community review"

        # Find needs_revision
        if 'needs_revision' in pr_labels:
            print "  Status: Needs revision"

######################################################################################


#PSEUDOCODE: COMMUNITY_REVIEW 
#for each PR found:
#	find all maintainers for this module
#	foreach comment, counting back from the bottom:
#	if you find a comment with a recognizable tag from an authorized maintainer:
#apply the tag
#apply the boilerplate (include the author of the PR)
#(FIXME: handle case of no comments for 2 weeks and other timeout cases)
#send email with the results.
#
#PSEUDOCODE: NEEDS_REVISION
#for each PR found:
#	foreach comment, counting back from the bottom:
#	if the contributor commented 'ready_for_review'
#		put it in (community_review) or (core_review)
#		# this is library that we call to pick out maintainer
#		attach boilerplate
#	(handle timeout)
#	(handle email)
#
#PSEUDOCODE: NEEDS_REBASE
#for each PR found:
#	is it rebased? (how does the API determine if it merges cleanly)
#	if so, move to (community_review) or (core_review)
#	(handle timeout)
#	(handle email)
#

