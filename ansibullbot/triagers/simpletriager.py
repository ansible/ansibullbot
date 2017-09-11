#!/usr/bin/env python

# This is a triager for the combined repos that should have happend
# in the 12-2016 timeframe.
#   https://groups.google.com/forum/#!topic/ansible-devel/mIxqxXRsmCI
#   https://groups.google.com/forum/#!topic/ansible-devel/iJouivmSSk4
#   https://github.com/ansible/proposals/issues/30

# Key features:
#   * daemonize mode that can continuously loop and process w/out scripts
#   * closed issues will also be processed (pygithub will kill ratelimits for
#     this, so use a new caching+index tool)
#   * open issues in ansible-modules-[core|extras] will be closed with a note
#     about pr|issue mover
#   * maintainers can be assigned to more than just the files in
#     lib/ansible/modules
#   * closed issues with active comments will be locked with msg about opening
#     new
#   * closed issues where submitter issues "reopen" command will be reopened
#   * false positives on module issue detection can be corrected by a wide range
#     of people
#   * more people (not just maintainers) should have access to a subset of bot
#     commands
#   * a generic label add|remove command will allow the community to fill in
#     where the bot can't
#   * different workflows should be a matter of enabling different plugins

import logging
import os

from pprint import pprint
from ansibullbot.triagers.defaulttriager import DefaultTriager, DefaultActions
from ansibullbot.utils.file_tools import FileIndexer
from ansibullbot.wrappers.issuewrapper import IssueWrapper
from github.GithubException import UnknownObjectException


class SimpleTriager(DefaultTriager):

    def __init__(self):
        super(SimpleTriager, self).__init__()
        # get valid labels
        logging.info('getting labels')
        self.valid_labels = self.get_valid_labels(self.repo)

    @classmethod
    def create_parser(cls):
        parser = DefaultTriager.create_parser()

        parser.description = "Triage issue and pullrequest queues for any github repo.\n" \
                             " (NOTE: only useful if you have commit access to" \
                             " the repo in question.)"

        parser.add_argument("--pr", "--id", type=str, dest="number",
                            help="Triage only the specified pr|issue (separated by commas)")
        parser.add_argument("--repo", "-r", type=str, required=True,
                    help="Github repo to triage (defaults to all)")
        return parser

    def run(self):

        # create the fileindexer
        fi_cache = '/tmp/ansibullbot/cache/{}.files.checkout'.format(self.repo)
        fi_cache = os.path.expanduser(fi_cache)
        self.file_indexer = FileIndexer(botmetafile=self.botmetafile, checkoutdir=fi_cache, repo=self.repo)
        self.file_indexer.update()

        # make a repo object for the github api
        repo = self.ghw.get_repo(self.repo)

        # map for issue type to label
        try:
            label_map = repo.get_label_map()
        except UnknownObjectException:
            label_map = {}

        # collect issues
        if not self.args.number:
            issues = repo.get_issues()
        else:
            issue = repo.get_issue(int(self.args.number))
            issues = [issue]

        # iterate through issues and apply actions
        for issue in issues:

            logging.info('triaging %s' % issue.html_url)
            actions = DefaultActions()

            # wrap the issue for extra magic
            cachedir = os.path.join(self.cachedir_base, self.repo)
            iw = IssueWrapper(github=self.ghw, repo=repo, issue=issue, cachedir=cachedir, file_indexer=self.file_indexer)

            # what did the submitter provide in the body?
            td = iw.template_data
            missing = iw.missing_template_sections
            if missing and 'needs_template' not in iw.labels:
                actions.newlabel.append('needs_template')

            # what type of issue is this?
            if 'issue type' in td:
                mapped_label = label_map.get(td['issue type'])
                if mapped_label:
                    if mapped_label not in iw.labels:
                        actions.newlabel.append(mapped_label)

            pprint(vars(actions))
            self.apply_actions(iw, actions)
