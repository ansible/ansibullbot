#!/usr/bin/env python

# This is a triager for the combined repos that should have happend in the 12-2016 timeframe.
#   https://groups.google.com/forum/#!topic/ansible-devel/mIxqxXRsmCI
#   https://groups.google.com/forum/#!topic/ansible-devel/iJouivmSSk4
#   https://github.com/ansible/proposals/issues/30

# Key features:
#   * daemonize mode that can continuously loop and process without needing wrapper scripts
#   * closed issues will also be processed (pygithub will kill ratelimits for this, so use a new caching+index tool)
#   * open issues in ansible-modules-[core|extras] will be closed with a note about pr|issue mover
#   * maintainers can be assigned to more than just the files in lib/ansible/modules 
#   * closed issues with active comments will be locked with msg about opening new
#   * closed issues where submitter issues "reopen" command will be reopened
#   * false positives on module issue detection can be corrected by a wide range of people
#   * more people (not just maintainers) should have access to a subset of bot commands
#   * a generic label add|remove command will allow the community to fill in where the bot can't
#   * different workflows should be a matter of enabling different plugins

import datetime
import logging
import os

from pprint import pprint
from lib.triagers.defaulttriager import DefaultTriager
from lib.wrappers.ghapiwrapper import GithubWrapper
from lib.wrappers.issuewrapper import IssueWrapper

#REPOS = ['ansible/ansible', 'ansible/ansible-modules-core', 'ansible/ansible-modules-extras']
#REPOS = ['ansible/ansible-modules-core', 'ansible/ansible-modules-extras']
REPOS = ['ansible/ansible-modules-extras']
MREPOS = [x for x in REPOS if 'modules' in x]
REPOMERGEDATE = datetime.datetime(2016, 12, 6, 0, 0, 0)

class TriageV3(DefaultTriager):

    def __init__(self, args):
        self.args = args
        self.last_run = None
        self.daemonize = None
        self.daemonize_interval = None
        self.dry_run = True
        self.force = False
        self.gh_pass = None
        self.github_pass = None
        self.gh_token = None
        self.github_token = None
        self.gh_user = None
        self.github_user = None
        self.logfile = None
        self.no_since = False
        self.only_closed = False
        self.only_issues = False
        self.only_open = False
        self.only_prs = False
        self.pause = False
        self.pr = False
        self.repo = None
        self.safe_force = False
        self.start_at = False
        self.verbose = False

        # where to store junk
        self.cachedir = '~/.ansibullbot/cache'
        self.cachedir = os.path.expanduser(self.cachedir)

        # repo objects
        self.repos = {}

        self.set_logger()
        logging.info('starting bot')

        logging.debug('setting bot attributes')
        attribs = dir(self.args)
        attribs = [x for x in attribs if not x.startswith('_')]
        for x in attribs:
            val = getattr(self, x)
            setattr(self, x, val)

        if self.args.daemonize:
            logging.info('starting daemonize loop')
            self.loop()
        else:
            logging.info('starting single run')
            self.run()
        logging.info('stopping bot')

    def set_logger(self):
        logging.level = logging.INFO
        logFormatter = logging.Formatter("%(asctime)s %(levelname)s  %(message)s")
        rootLogger = logging.getLogger()
        rootLogger.setLevel(logging.INFO)

        fileHandler = logging.FileHandler("{0}/{1}".format(
                os.path.dirname(self.args.logfile),
                os.path.basename(self.args.logfile))
        )
        fileHandler.setFormatter(logFormatter)
        rootLogger.addHandler(fileHandler)
        consoleHandler = logging.StreamHandler()
        consoleHandler.setFormatter(logFormatter)
        rootLogger.addHandler(consoleHandler)

    def loop(self):
        '''Call the run method in a defined interval'''
        pass

    def run(self):
        '''Primary execution method'''
        self.collect_issues()

        #if self.last_run:
        #    wissues = self.get_updated_issues(since=self.last_run)
        #else:
        #    wissues = self.get_updated_issues()

        for item in self.repos.items():
            repopath = item[0]
            repoobj = item[1]['repo']
            issues = item[1]['issues']
            for i_item in issues.items():
                ik = i_item[0]
                iw = i_item[1]
                logging.info(iw)

                if iw.state == 'closed':
                    logging.info(iw + ' is closed, skipping')
                    continue

                action_meta = None
                if iw.repo_full_name in MREPOS:
                    if iw.created_at >= REPOMERGEDATE:
                        action_meta = self.close_module_issue_with_message(iw)
                    else:
                        pass
                else:
                    pass

                pprint(action_meta)
                #import epdb; epdb.st()


    def close_module_issue_with_message(self, issue):
        '''After the repomerge, new issues+prs in the module repos should be closed'''
        self.actions = {}
        self.actions['close'] = True
        self.actions['comments'] = []
        self.actions['newlabel'] = []
        self.actions['unlabel'] = []

        # stubs for the comment templater
        self.module_maintainers = []
        self.module = None
        self.issue = issue
        self.template_data = {}
        self.github_repo = issue.repo_full_name
        self.match = {}

        issue.add_desired_comment('repomerge')
        comment = self.render_comment(boilerplate='repomerge')
        self.actions['comments'] = [comment]

        pprint(self.actions)
        action_meta = self.apply_actions()
        import epdb; epdb.st()
        return action_meta


    def collect_issues(self):
        '''Populate the local cache of issues'''
        # this should do a few things:
        #   1. collect all issues (open+closed) via a webcrawler
        #   2. index the issues into a sqllite database so we can query on update times
        #   3. set an abstracted object that takes in queries 
        logging.info('start collecting issues')
        logging.debug('creating github connection object')
        self.gh = self._connect()
        logging.info('creating github connection wrapper')
        self.ghw = GithubWrapper(self.gh)

        for repo in REPOS:
            logging.info('getting repo obj for %s' % repo)
            cachedir = os.path.join(self.cachedir, repo)
            self.repos[repo] = {}
            self.repos[repo]['repo'] = self.ghw.get_repo(repo, verbose=False)
            self.repos[repo]['issues'] = {}
            logging.info('getting issue objs for %s' % repo)
            issues = self.repos[repo]['repo'].get_issues()
            for issue in issues:
                iw = IssueWrapper(
                        repo=self.repos[repo]['repo'],
                        issue=issue,
                        cachedir=cachedir
                )
                self.repos[repo]['issues'][iw.number] = iw
            logging.info('getting issue objs for %s complete' % repo)

        logging.info('finished collecting issues')

    def get_updated_issues(self, since=None):
        '''Get issues to work on'''
        # this should return a list of issueids that have changed since the last run
        logging.info('start querying updated issues')

        # these need to be tuples (namespace, repo, number)
        issueids = []

        logging.info('finished querying updated issues')
        return issueids


