#!/usr/bin/python

# Very simple reporting script for status of new modules in Ansible extras. 
# No auth, no args. Just pulling basic query data and parsing it for reporting
# to the Ansible community (ansible-project and ansible-devel mailing lists).
#
# Will use the new_issue_alert.j2 template.

# FIXME:
#  * In loop: Pick out all PRs in last week by issue['created_at']
#  * In loop: Pick out oldest unreviewed PRs by issue['created_at'] (in community review)
#  * Be sure to include individual URLs ['pull_request']['html_url']

import requests, json, sys, argparse, time

repo_url = 'https://api.github.com/repos/ansible/ansible-modules-extras/issues?labels=new_plugin'
args = {'state':'open', 'page':1}

# Get number of pages 
r = requests.get(repo_url, params=args)
try:
    lastpage = int(str(r.links['last']['url']).split('=')[-1])
except:
    lastpage = 1

total_prs = 0
latest_module_string = ''
oldest_module_string = ''
oldest_module_time = time.time()

for page in range(1,lastpage):
    pull_args = {'state':'open', 'page':page}
    r = requests.get(repo_url, params=pull_args)

    for issue in r.json():
        total_prs += 1
        issue_time = time.mktime((time.strptime(issue['created_at'], "%Y-%m-%dT%H:%M:%SZ")))
        issue_age = int((time.time()-issue_time)/86400)
        if issue_age < 7:
            latest_module_string += issue['title'] + "\n"
            latest_module_string += issue['html_url'] + "\n\n"
        if issue_time < oldest_module_time:
            oldest_module_time = issue_time
            oldest_module_string = issue['title'] + " (" + str(issue_age) + " days old)\n" + issue['html_url']+ "\n\n"
            

# Final report
print "Total PRs: ", total_prs
print "Latest new module PRs this week: \n", latest_module_string
print "Oldest new module PR: \n", oldest_module_string

