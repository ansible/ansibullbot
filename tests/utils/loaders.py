#!/usr/bin/env python

from datetime import datetime
from ansibullbot.wrappers.issuewrapper import IssueWrapper
from test.utils.issue_mock import IssueMock
from test.utils.issuetriager_mock import TriageIssuesMock

SAMPLE_MODULE = {'name': 'xyz'}

def get_triagermock_for_datafile(datafile):
    im = IssueMock(datafile)
    iw = IssueWrapper(repo=None, issue=im)
    triage = TriageIssuesMock(verbose=True)

    triage.issue = iw
    triage.issue.get_events()
    triage.issue.get_comments()

    # add additional mock data from fixture
    triage.force = True
    triage._now = im.ydata.get('_now', datetime.now())
    triage.number = im.ydata.get('number', 1)
    triage.github_repo = im.ydata.get('github_repo', 'core')
    triage.match = im.ydata.get('_match')
    triage.module_indexer.match = im.ydata.get('_match')
    if not im.ydata.get('_match'):
        triage.module_indexer.modules = {'xyz': SAMPLE_MODULE}
    else:
        triage.module_indexer.modules = {'NULL': triage.module_indexer.match}
    if im.ydata.get('_match'):
        triage._module = triage.match.get('name')
    else:
        triage._module = None
    triage._ansible_members = im.ydata.get('_ansible_members', [])
    triage._module_maintainers = im.ydata.get('_module_maintainers', [])

    return triage

