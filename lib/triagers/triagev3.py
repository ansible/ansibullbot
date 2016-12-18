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

import copy
import datetime
import json
import logging
import os
import re
import time

from pprint import pprint
from lib.triagers.defaulttriager import DefaultTriager
from lib.wrappers.ghapiwrapper import GithubWrapper
from lib.wrappers.historywrapper import HistoryWrapper
from lib.wrappers.issuewrapper import IssueWrapper

from lib.utils.moduletools import ModuleIndexer
from lib.utils.version_tools import AnsibleVersionIndexer
from lib.utils.file_tools import FileIndexer


BOTNAMES = ['ansibot', 'gregdek']
REPOS = [
    'ansible/ansible',
    'ansible/ansible-modules-core',
    'ansible/ansible-modules-extras'
]
MREPOS = [x for x in REPOS if 'modules' in x]
REPOMERGEDATE = datetime.datetime(2016, 12, 6, 0, 0, 0)
MREPO_CLOSE_WINDOW = 30
MAINTAINERS_FILES = ['MAINTAINERS-CORE.txt', 'MAINTAINERS-EXTRAS.txt']
FILEMAP_FILENAME = 'FILEMAP.json'


class TriageV3(DefaultTriager):

    EMPTY_ACTIONS = {
        'newlabel': [],
        'unlabel': [],
        'comments': [],
        'close': False,
        'open': False,
        'merge': False,
    }

    EMPTY_META = {
    }

    ISSUE_TYPES = {
        'bug report': 'bug_report',
        'bugfix pull request': 'bugfix_pull_request',
        'feature idea': 'feature_idea',
        'feature pull request': 'feature_pull_request',
        'documentation report': 'docs_report',
        'docs pull request': 'docs_pull_request',
        'new module pull request': 'new_plugin'
    }

    MANAGED_LABELS = [
        'bot_broken',
        'needs_info',
        'needs_rebase',
        'needs_revision',
        'shipit',
        'shipit_owner_pr'
    ]

    # modules having files starting like the key, will get the value label
    MODULE_NAMESPACE_LABELS = {
        'cloud': "cloud",
        'cloud/google': "gce",
        'cloud/amazon': "aws",
        'cloud/azure': "azure",
        'cloud/openstack': "openstack",
        'cloud/digital_ocean': "digital_ocean",
        'windows': "windows",
        'network': "networking"
    }

    VALID_COMMANDS = [
        'needs_info',
        '!needs_info',
        'notabug',
        'bot_broken',
        'bot_skip',
        'wontfix',
        'bug_resolved',
        'resolved_pr_pr',
        'needs_contributor',
        'needs_rebase',
        'needs_revision',
        'shipit',
        'duplicate_of'
    ]

    ISSUE_REQUIRED_FIELDS = [
        'issue type',
        'component name',
        'ansible version',
        'summary'
    ]

    PULLREQUEST_REQUIRED_FIELDS = [
    ]

    FILEMAP = {}

    def __init__(self, args):
        self.args = args
        self.last_run = None
        self.daemonize = None
        self.daemonize_interval = None
        self.dry_run = False
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
        self.always_pause = False
        self.pr = False
        self.repo = None
        self.safe_force = False
        self.skiprepo = []
        self.start_at = False
        self.verbose = False

        # extend managed labels
        self.MANAGED_LABELS += self.ISSUE_TYPES.values()

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
            val = getattr(self.args, x)
            if x.startswith('gh_'):
                setattr(self, x.replace('gh_', 'github_'), val)
            else:
                setattr(self, x, val)

        if self.args.pause:
            self.always_pause = True

        if self.args.daemonize:
            logging.info('starting daemonize loop')
            self.loop()
        else:
            logging.info('starting single run')
            self.run()
        logging.info('stopping bot')

    def set_logger(self):
        if self.args.debug:
            logging.level = logging.DEBUG
        else:
            logging.level = logging.INFO
        logFormatter = \
            logging.Formatter("%(asctime)s %(levelname)s  %(message)s")
        rootLogger = logging.getLogger()
        if self.args.debug:
            rootLogger.setLevel(logging.DEBUG)
        else:
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
        while True:
            self.run()
            interval = self.args.daemonize_interval
            logging.info('sleep %ss (%sm)' % (interval, interval / 60))
            time.sleep(interval)

    def run(self):
        '''Primary execution method'''

        # get the issues
        self.collect_issues()

        # get the maintainers
        self.module_maintainers = self.get_maintainers_mapping()

        # get the filemap
        self.FILEMAP = self.get_filemap()

        # set the indexers
        self.version_indexer = AnsibleVersionIndexer()
        self.file_indexer = FileIndexer()
        self.module_indexer = ModuleIndexer(maintainers=self.module_maintainers)
        self.module_indexer.get_ansible_modules()

        # get the ansible members
        self.ansible_members = self.get_ansible_members()

        # get valid labels
        self.valid_labels = self.get_valid_labels('ansible/ansible')

        #if self.last_run:
        #    wissues = self.get_updated_issues(since=self.last_run)
        #else:
        #    wissues = self.get_updated_issues()

        for item in self.repos.items():
            repopath = item[0]

            if repopath in self.skiprepo:
                continue

            issues = item[1]['issues']
            numbers = sorted(issues.keys())
            numbers.reverse()
            for number in numbers:

                iw = issues[number]

                if self.args.start_at:
                    if number < self.args.start_at:
                        logging.info('skip %s' % number)
                        continue

                self.issue = iw
                logging.info(iw)

                if iw.state == 'closed':
                    logging.info(iw + ' is closed, skipping')
                    continue

                hcache = os.path.join(self.cachedir, iw.repo_full_name)
                #action_meta = None

                if iw.repo_full_name not in MREPOS:
                    # ansible/ansible triage

                    # basic processing
                    self.process(iw)
                    self.meta.update(self.get_facts(iw))

                    # history+comment processing
                    #self.process_history()

                    # issue
                    #import epdb; epdb.st()
                    pass

                else:
                    if iw.created_at >= REPOMERGEDATE:
                        # close new module issues+prs immediately
                        logging.info('module issue created -after- merge')
                        self.close_module_issue_with_message(iw)
                        continue
                    else:
                        # process history
                        # - check if message was given, comment if not
                        # - if X days after message, close PRs, move issues.
                        logging.info('module issue created -before- merge')

                        logging.info('build history')
                        hw = self.get_history(
                            iw,
                            usecache=True,
                            cachedir=hcache
                        )
                        logging.info('history built')
                        lc = hw.last_date_for_boilerplate('repomerge')
                        if lc:
                            lcdelta = (datetime.datetime.now() - lc).days
                        else:
                            lcdelta = None

                        kwargs = {}
                        # missing the comment?
                        if lc:
                            kwargs['bp'] = 'repomerge'
                        else:
                            kwargs['bp'] = None

                        # should it be closed or not?
                        if iw.is_pullrequest():
                            if lc and lcdelta > MREPO_CLOSE_WINDOW:
                                kwargs['close'] = True
                                self.close_module_issue_with_message(
                                    iw,
                                    **kwargs
                                )
                            elif not lc:
                                # add the comment
                                self.add_repomerge_comment(iw)
                            else:
                                # do nothing
                                pass
                        else:
                            kwargs['close'] = False
                            if lc and lcdelta > MREPO_CLOSE_WINDOW:
                                # move it for them
                                self.move_issue(iw)
                            elif not lc:
                                # add the comment
                                self.add_repomerge_comment(iw)
                            else:
                                # do nothing
                                pass
                        # do nothing else on these repos
                        continue

                self.create_actions()
                logging.info('url: %s' % self.issue.html_url)
                logging.info('title: %s' % self.issue.title)
                logging.info('component: %s'
                             % self.template_data.get('component_raw'))
                pprint(self.actions)
                self.apply_actions()
                logging.info('finished triage for %s' % iw.number)
                #import epdb; epdb.st()

    def get_filemap(self):
        '''Read filemap and make re matchers'''
        with open(FILEMAP_FILENAME, 'rb') as f:
            jdata = json.loads(f.read())
        for k,v in jdata.iteritems():
            reg = k
            if reg.endswith('/'):
                reg += '*'
            jdata[k]['regex'] = re.compile(reg)

            if 'inclusive' not in v:
                jdata[k]['inclusive'] = True
            if 'notify' not in v:
                jdata[k]['notify'] = []
            if 'labels' not in v:
                jdata[k]['labels'] = []
        return jdata

    def create_actions(self):
        '''Parse facts and make actiosn from them'''
        if self.meta['bot_broken']:
            logging.warning('bot broken!')
            self.actions = copy.deepcopy(self.EMPTY_ACTIONS)
            if 'bot_broken' not in self.issue.labels:
                self.actions['newlabel'].append('bot_broken')
            return None

        elif self.meta['bot_skip']:
            logging.info('bot skip')
            self.actions = copy.deepcopy(self.EMPTY_ACTIONS)
            return None

        elif self.meta['bot_spam']:
            logging.warning('bot spam!')
            self.actions = copy.deepcopy(self.EMPTY_ACTIONS)
            return None

        elif self.meta['is_bad_pr']:
            # FIXME - do something!
            self.actions = copy.deepcopy(self.EMPTY_ACTIONS)
            return None

        ## TRIAGE!!!
        if not self.issue.labels:
            self.actions['newlabel'].append('triage')

        if self.meta['shipit'] and not self.meta['is_needs_revision']:
            logging.info('shipit')
            if self.meta['shipit_owner_pr'] \
                    and 'shipit_owner_pr' not in self.issue.labels:
                self.actions['newlabel'].append('shipit')
                self.actions['newlabel'].append('shipit_owner_pr')
            elif not self.meta['shipit_owner_pr'] \
                    and self.meta['shipit'] \
                    and 'shipit' not in self.issue.labels \
                    and 'shipit' not in self.actions['newlabel']:
                self.actions['newlabel'].append('shipit')
        else:
            if 'shipit' in self.issue.labels:
                self.actions['unlabel'].append('shipit')
            if 'shipit_owner_pr' in self.issue.labels:
                self.actions['unlabel'].append('shipit_owner_pr')
            if self.meta['is_needs_revision']:
                if 'needs_revision' not in self.issue.labels:
                    self.actions['newlabel'].append('needs_revision')
            else:
                if 'needs_revision' in self.issue.labels:
                    self.actions['unlabel'].append('needs_revision')

        if self.meta['is_needs_rebase']:
            if 'needs_rebase' not in self.issue.labels:
                    self.actions['newlabel'].append('needs_rebase')
        else:
            if 'needs_rebase' in self.issue.labels:
                    self.actions['unlabel'].append('needs_rebase')
        #import epdb; epdb.st()

        if self.meta['is_new_module'] or self.meta['is_module']:
            # add topic labels
            for t in ['topic', 'subtopic']:
                label = self.meta['module_match'].get(t)
                if label in self.MODULE_NAMESPACE_LABELS:
                    label = self.MODULE_NAMESPACE_LABELS[label]

                if label and label in self.valid_labels and \
                        label not in self.issue.current_labels:
                    self.actions['newlabel'].append(label)

            # add namespace labels
            namespace = self.meta['module_match'].get('namespace')
            if namespace in self.MODULE_NAMESPACE_LABELS:
                label = self.MODULE_NAMESPACE_LABELS[namespace]
                if label not in self.issue.current_labels:
                    self.actions['newlabel'].append(label)
            #import epdb; epdb.st()

        if self.meta['is_new_module'] or self.meta['is_new_plugin']:
            if 'new_plugin' not in self.issue.labels:
                self.actions['newlabel'].append('new_plugin')

        if self.meta['is_module']:
            if 'module' not in self.issue.labels:
                self.actions['newlabel'].append('module')
        else:
            if 'module' in self.issue.labels:
                self.actions['unlabel'].append('module')

        if self.meta['is_module_util']:
            if 'module_util' not in self.issue.labels:
                self.actions['newlabel'].append('module_util')

        if self.meta['is_plugin']:
            if 'plugin' not in self.issue.labels:
                self.actions['newlabel'].append('plugin')
        else:
            if 'plugin' in self.issue.labels:
                self.actions['unlabel'].append('plugin')

        if self.meta['ansible_label_version']:
            label = 'affects_%s' % self.meta['ansible_label_version']
            if label not in self.issue.labels:
                self.actions['newlabel'].append(label)

        if self.meta['issue_type']:
            label = self.ISSUE_TYPES.get(self.meta['issue_type'])
            if label and label not in self.issue.labels:
                self.actions['newlabel'].append(label)

        # use the filemap to add labels
        if self.issue.is_pullrequest():
            fmap_labels = self.get_filemap_labels_for_files(self.issue.files)
            for label in fmap_labels:
                if label in self.valid_labels and \
                        label not in self.issue.labels:
                    self.actions['newlabel'].append(label)

        # python3 ... obviously!
        if self.meta['is_py3']:
            if 'python3' not in self.issue.labels:
                self.actions['newlabel'].append('python3')

        # needs info?
        if self.meta['is_needs_info']:
            if 'needs_info' not in self.issue.labels:
                self.actions['newlabel'].append('needs_info')
        elif 'needs_info' in self.issue.labels:
            self.actions['unlabel'].append('needs_info')

        self.actions['newlabel'] = sorted(set(self.actions['newlabel']))
        self.actions['unlabel'] = sorted(set(self.actions['unlabel']))

        # maintainer commands
        # needs info

        #if not self.empty_actions:
        #    pprint(self.actions)
        #    import epdb; epdb.st()
        #import epdb; epdb.st()

    def check_safe_match(self):
        safe = True
        for k,v in self.actions.iteritems():
            if k == 'newlabel' or k == 'unlabel':
                continue
            if v:
                safe = False
        if safe:
            self.force = True
        else:
            self.force = False
        return safe

    def get_filemap_labels_for_files(self, files):
        '''Get expected labels from the filemap'''
        labels = []

        exclusive = False
        for f in files:

            # only one match
            if exclusive:
                continue

            for k,v in self.FILEMAP.iteritems():
                if not v['inclusive'] and v['regex'].match(f):
                    labels = v['labels']
                    exclusive = True
                    break

                if 'labels' not in v:
                    continue
                if v['regex'].match(f):
                    for label in v['labels']:
                        if label not in labels:
                            labels.append(label)

        return labels

    def empty_actions(self):
        empty = True
        for k,v in self.actions.iteritems():
            if v:
                empty = False
                break
        return empty

    def move_issue(self, issue):
        '''Move an issue to ansible/ansible'''
        # this should only happen >30 days -after- the repomerge
        pass

    def add_repomerge_comment(self, issue, bp='repomerge'):
        '''Add the comment without closing'''

        self.actions = copy.deepcopy(self.EMPTY_ACTIONS)

        # stubs for the comment templater
        self.module_maintainers = []
        self.module = None
        self.issue = issue
        self.template_data = {}
        self.github_repo = issue.repo_full_name
        self.match = {}

        comment = self.render_comment(boilerplate=bp)
        self.actions['comments'] = [comment]

        logging.info('url: %s' % self.issue.html_url)
        logging.info('title: %s' % self.issue.title)
        logging.info('component: %s' % self.template_data.get('component_raw'))
        pprint(self.actions)
        action_meta = self.apply_actions()
        return action_meta

    def close_module_issue_with_message(self, issue, bp='repomerge_new'):
        '''After repomerge, new issues+prs in the mod repos should be closed'''
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

        comment = self.render_comment(boilerplate=bp)
        self.actions['comments'] = [comment]

        logging.info('url: %s' % self.issue.html_url)
        logging.info('title: %s' % self.issue.title)
        logging.info('component: %s' % self.template_data.get('component_raw'))
        pprint(self.actions)
        action_meta = self.apply_actions()
        return action_meta

    def collect_issues(self):
        '''Populate the local cache of issues'''
        # this should do a few things:
        #   1. collect all issues (open+closed) via a webcrawler
        #   2. index the issues into a rdmbs so we can query on update times(?)
        #   3. set an abstracted object that takes in queries
        logging.info('start collecting issues')
        logging.debug('creating github connection object')
        self.gh = self._connect()
        logging.info('creating github connection wrapper')
        self.ghw = GithubWrapper(self.gh)

        for repo in REPOS:

            if repo in self.skiprepo:
                continue
            #import epdb; epdb.st()

            logging.info('getting repo obj for %s' % repo)
            cachedir = os.path.join(self.cachedir, repo)
            self.repos[repo] = {
                'repo': self.ghw.get_repo(repo, verbose=False),
                'issues': {}
            }

            logging.info('getting issue objs for %s' % repo)
            if self.pr:
                logging.info('fetch %s' % self.pr)
                issue = self.repos[repo]['repo'].get_issue(self.pr)
                iw = IssueWrapper(
                        repo=self.repos[repo]['repo'],
                        issue=issue,
                        cachedir=cachedir
                )
                self.repos[repo]['issues'][iw.number] = iw
            else:
                issues = self.repos[repo]['repo'].get_issues()
                for issue in issues:

                    if self.args.start_at:
                        if issue.number < self.args.start_at:
                            continue

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
        # this should return a list of issueids that changed since the last run
        logging.info('start querying updated issues')

        # these need to be tuples (namespace, repo, number)
        issueids = []

        logging.info('finished querying updated issues')
        return issueids

    def get_history(self, issue, usecache=True, cachedir=None):
        history = HistoryWrapper(issue, usecache=usecache, cachedir=cachedir)
        return history

    def process(self, issuewrapper):
        '''Do initial processing of the issue'''
        iw = issuewrapper

        # clear the actions+meta
        self.actions = copy.deepcopy(self.EMPTY_ACTIONS)
        self.meta = copy.deepcopy(self.EMPTY_META)

        # clear maintainers
        self.maintainers = []

        # extract template data
        self.template_data = iw.get_template_data()

        # set the issue type
        ITYPE = self.template_data.get('issue type')
        if ITYPE in self.ISSUE_TYPES:
            self.meta['issue_type'] = ITYPE
        else:
            # look for best match?
            self.meta['issue_type'] = self.guess_issue_type(iw)

        # get ansible version
        if iw.is_issue():
            self.meta['ansible_version'] = \
                self.get_ansible_version_by_issue(iw)
        else:
            # use the submit date's current version
            self.meta['ansible_version'] = \
                self.version_indexer.ansible_version_by_date(iw.created_at)
        self.meta['ansible_label_version'] = \
            self.get_ansible_version_major_minor(
                version=self.meta['ansible_version']
            )
        logging.info('ansible version: %s' % self.meta['ansible_version'])

        # what is this?
        self.meta['is_bad_pr'] = False
        self.meta['is_module'] = False
        self.meta['is_action_plugin'] = False
        self.meta['is_new_module'] = False
        self.meta['is_module_util'] = False
        self.meta['is_plugin'] = False
        self.meta['is_new_plugin'] = False
        self.meta['is_core'] = False
        self.meta['is_multi_module'] = False
        self.meta['module_match'] = None
        self.meta['component'] = None

        if iw.is_issue():
            if self.template_data.get('component name'):
                cname = self.template_data.get('component name')
                craw = self.template_data.get('component_raw')
                if self.module_indexer.find_match(cname):
                    match = self.module_indexer.find_match(cname)
                    self.meta['is_module'] = True
                    self.meta['is_plugin'] = True
                    self.meta['module_match'] = copy.deepcopy(match)
                    self.meta['component'] = match['name']
                elif self.template_data.get('component_raw') \
                        and ('module' in iw.title or
                             'module' in craw or
                             'action' in craw):
                    # FUZZY MATCH?
                    logging.info('fuzzy match module component')
                    fm = self.module_indexer.fuzzy_match(
                        title=iw.title,
                        component=self.template_data['component_raw']
                    )
                    if fm:
                        match = self.module_indexer.find_match(fm)
                        self.meta['is_module'] = True
                        self.meta['is_plugin'] = True
                        self.meta['module_match'] = copy.deepcopy(match)
                        self.meta['component'] = match['name']
                else:
                    pass

        elif len(iw.files) > 100:
            # das merge?
            self.meta['bad_pr'] = True
        else:
            # assume pullrequest
            for f in iw.files:

                if f.startswith('lib/ansible/modules/core') or \
                        f.startswith('lib/ansible/modules/core'):
                    self.meta['is_bad_pr'] = True
                    continue

                if f.startswith('lib/ansible/module_utils'):
                    self.meta['is_module_util'] = True
                    continue

                if f.startswith('lib/ansible/plugins/action'):
                    self.meta['is_action_plugin'] = True

                if f.startswith('lib/ansible') \
                        and not f.startswith('lib/ansible/modules'):
                    self.meta['is_core'] = True

                if not f.startswith('lib/ansible/modules') and \
                        not f.startswith('lib/ansible/plugins/actions'):
                    continue

                # duplicates?
                if self.meta['module_match']:
                    # same maintainer?
                    nm = self.module_indexer.find_match(f)
                    if nm:
                        self.meta['is_multi_module'] = True
                        if nm['maintainers'] == \
                                self.meta['module_match']['maintainers']:
                            continue
                        else:
                            # >1 set of maintainers
                            logging.info('multiple modules referenced')
                            #import epdb; epdb.st()
                            pass

                if self.module_indexer.find_match(f):
                    match = self.module_indexer.find_match(f)
                    self.meta['is_module'] = True
                    self.meta['is_plugin'] = True
                    self.meta['module_match'] = copy.deepcopy(match)
                    self.meta['component'] = match['name']
                elif f.startswith('lib/ansible/modules') \
                        and (f.endswith('.py') or f.endswith('.ps1')):
                    self.meta['is_new_module'] = True
                    self.meta['is_module'] = True
                    self.meta['is_plugin'] = True
                    match = copy.deepcopy(self.module_indexer.EMPTY_MODULE)
                    match['name'] = os.path.basename(f).replace('.py', '')
                    match['filepath'] = f
                    match.update(
                        self.module_indexer.split_topics_from_path(f)
                    )
                    #import epdb; epdb.st()
                    self.meta['module_match'] = copy.deepcopy(match)
                    self.meta['component'] = match['name']
                elif f.endswith('.md'):
                    # network/avi/README.md
                    continue
                else:
                    # FIXME - what do with these files?
                    print(f)
                    #import epdb; epdb.st()

        # who owns this?
        self.meta['owner'] = 'ansible'
        if self.meta['module_match']:
            print(self.meta['module_match'])
            maintainers = self.meta['module_match']['maintainers']
            if maintainers:
                self.meta['owner'] = maintainers
            elif self.meta['is_new_module']:
                self.meta['owner'] = ['ansible']
            else:
                logging.error('NO MAINTAINER LISTED FOR %s'
                              % self.meta['module_match']['name'])
                #import epdb; epdb.st()

        # everything else is "core"
        if not self.meta['is_module']:
            self.meta['is_core'] = True
            #import epdb; epdb.st()

        # shipit?
        self.meta.update(self.get_shipit_facts(iw, self.meta))
        self.meta.update(self.get_needs_revision_facts(iw, self.meta))
        self.meta.update(self.get_community_review_facts(iw, self.meta))

        # python3 ?
        self.meta['is_py3'] = self.is_python3()

        # needsinfo?
        self.meta['is_needs_info'] = self.is_needsinfo()

    def guess_issue_type(self, issuewrapper):
        iw = issuewrapper

        # body contains any known types?
        body = iw.body
        for key in self.ISSUE_TYPES.keys():
            if body and key in body.lower():
                return key

        if iw.is_issue():
            pass
        elif iw.is_pullrequest():
            pass

        return None

    def get_maintainers_mapping(self):
        maintainers = {}
        for fname in MAINTAINERS_FILES:
            with open(fname, 'rb') as f:
                for line in f.readlines():
                    #print(line)
                    owner_space = (line.split(': ')[0]).strip()
                    maintainers_string = (line.split(': ')[-1]).strip()
                    maintainers[owner_space] = maintainers_string.split(' ')
                    #import epdb; epdb.st()

        # meta is special
        maintainers['meta'] = ['ansible']
        return maintainers

    def keep_unmanaged_labels(self, issue):
        '''Persists labels that were added manually and not bot managed'''
        for label in issue.current_labels:
            if label not in self.MANAGED_LABELS:
                self.debug('keeping %s label' % label)
                self.issue.add_desired_label(name=label)

    def get_shipit_facts(self, issuewrapper, meta):
        # shipit/+1/LGTM in comment.body from maintainer

        # AUTOMERGE
        # * New module, existing namespace: require a "shipit" from some
        #   other maintainer in the namespace. (Ideally, identify a maintainer
        #   for the entire namespace.)
        # * New module, new namespace: require discussion with the creator
        #   of the namespace, which will likely be a vendor.
        # * And all new modules, of course, go in as "preview" mode.

        iw = issuewrapper
        nmeta = {
            'shipit': False,
            'shipit_owner_pr': False,
            'shipit_ansible': False,
            'shipit_community': False
        }

        if not iw.is_pullrequest():
            return nmeta
        if not meta['module_match']:
            return nmeta

        ansible_shipits = 0
        shipits = 0
        migrated_issue = None

        maintainers = [x for x in self.ansible_members if x not in BOTNAMES]
        maintainers += meta['module_match']['maintainers']

        for comment in iw.comments:
            body = comment.body

            # ansible shipits
            if comment.user.login in self.ansible_members and \
                    comment.user.login not in BOTNAMES:
                if 'shipit' in body or '+1' in body or 'LGTM' in body:
                    ansible_shipits += 1

            # community shipits
            if comment.user.login != iw.submitter:
                if 'shipit' in body or '+1' in body or 'LGTM' in body:
                    shipits += 1

            # Migrated from ansible/ansible-modules-extras#3662
            # u'Migrated from
            #   https://github.com/ansible/ansible-modules-extras/pull/2979 by
            #   tintoy (not original author)'
            if comment.user.login == iw.submitter and \
                    body.lower().startswith('migrated from'):
                bparts = body.split()
                migrated_issue = bparts[2]
                #import epdb; epdb.st()

            if comment.user.login in maintainers:
                if 'shipit' in body or '+1' in body or 'LGTM' in body:
                    nmeta['shipit'] = True
                    if comment.user.login == iw.submitter:
                        nmeta['shipit_owner_pr'] = True
                    break

        # prmover doesn't copy comments, so they have to
        # be scraped from the old pullrequest
        if migrated_issue and not nmeta['shipit']:

            if migrated_issue.startswith('https://'):
                miparts = migrated_issue.split('/')
                minumber = int(miparts[-1])
                minamespace = miparts[-4]
                mirepo = miparts[-3]
                mirepopath = minamespace + '/' + mirepo
            elif '#' in migrated_issue:
                miparts = migrated_issue.split('#')
                minumber = int(miparts[-1])
                mirepopath = miparts[0]
            else:
                print(migrated_issue)
                import epdb; epdb.st()

            if mirepopath not in self.repos:
                self.repos[mirepopath] = {
                    'repo': self.ghw.get_repo(mirepopath, verbose=False),
                    'issues': {}
                }
            mrepo = self.repos[mirepopath]['repo']
            missue = mrepo.get_issue(minumber)
            mw = IssueWrapper(
                repo=mrepo,
                issue=missue,
                cachedir=os.path.join(self.cachedir, mirepopath)
            )

            for comment in mw.comments:

                # ansible shipits
                if comment.user.login in self.ansible_members and \
                        comment.user.login not in BOTNAMES:
                    if 'shipit' in body or '+1' in body or 'LGTM' in body:
                        ansible_shipits += 1

                # community shipits
                if comment.user.login != iw.submitter:
                    if 'shipit' in body or '+1' in body or 'LGTM' in body:
                        shipits += 1

                if comment.user.login in maintainers:
                    if 'shipit' in body or '+1' in body or 'LGTM' in body:
                        nmeta['shipit'] = True
                        if comment.user.login == iw.submitter:
                            nmeta['shipit_owner_pr'] = True
                        break

        # https://github.com/ansible/ansible-modules-extras/pull/1749
        # Thanks again to @dinoocch for this PR. This PR was reviewed by an
        # Ansible member. Marking for inclusion.
        if not nmeta['shipit'] and ansible_shipits > 0:
            nmeta['shipit'] = True
            nmeta['shipit_ansible'] = True

        # community voted shipits
        if not nmeta['shipit'] and shipits > 1 and \
                (self.meta['is_module'] and self.meta['is_new_module']):
            #import epdb; epdb.st()
            nmeta['shipit'] = True
            nmeta['shipit_community'] = True
            #import epdb; epdb.st()

        return nmeta

    def get_facts(self, issuewrapper):
        facts = {}
        facts['bot_broken'] = False
        facts['bot_skip'] = False
        facts['bot_spam'] = False
        return facts

    def is_python3(self):
        '''Is the issue related to python3?'''
        ispy3 = False
        py3strings = ['python 3', 'python3', 'py3', 'py 3']

        for py3str in py3strings:

            if py3str in self.issue.title.lower():
                ispy3 = True
                break

            if py3str in self.template_data.get('component_raw', ''):
                ispy3 = True
                break

            if py3str in self.template_data.get('component name', ''):
                ispy3 = True
                break

            if py3str in self.template_data.get('summary', ''):
                ispy3 = True
                break

        if ispy3:
            for comment in self.issue.comments:
                if '!python3' in comment.body:
                    logging.info('!python3 override in comments')
                    ispy3 = False
                    break

        return ispy3

    def missing_fields(self):
        # start with missing template data
        if self.issue.is_issue():
            mf = self.ISSUE_REQUIRED_FIELDS
        else:
            mf = self.PULLREQUEST_REQUIRED_FIELDS

        if not self.issue.history:
            self.issue.history = self.get_history(
                self.issue,
                cachedir=self.cachedir,
                usecache=True
            )

        #import epdb; epdb.st()

    def is_needsinfo(self):

        needs_info = False
        if not self.issue.history:
            self.issue.history = self.get_history(
                self.issue,
                cachedir=self.cachedir,
                usecache=True
            )

        maintainers = [x for x in self.ansible_members if x not in BOTNAMES]
        if self.meta.get('module_match'):
            maintainers += self.meta['module_match'].get('maintainers', [])

        for event in self.issue.history.history:

            if needs_info and event['actor'] == self.issue.submitter:
                needs_info = False

            if event['actor'] in BOTNAMES:
                continue
            if event['actor'] not in maintainers:
                continue

            if event['event'] == 'labeled':
                if event['label'] == 'needs_info':
                    needs_info = True
                    continue
            if event['event'] == 'unlabeled':
                if event['label'] == 'needs_info':
                    needs_info = False
                    continue
            if event['event'] == 'commented':
                if '!needs_info' in event['body']:
                    needs_info = False
                elif 'needs_info' in event['body']:
                    needs_info = True

        #import epdb; epdb.st()
        return needs_info

    def get_needs_revision_facts(self, issuewrapper, meta):
        # Thanks @adityacs for this PR. This PR requires revisions, either
        # because it fails to build or by reviewer request. Please make the
        # suggested revisions. When you are done, please comment with text
        # 'ready_for_review' and we will put this PR back into review.

        needs_revision = False
        needs_rebase = False

        iw = issuewrapper
        if not iw.is_pullrequest():
            return {'is_needs_revision': needs_revision,
                    'is_needs_rebase': needs_rebase}

        #if not meta['is_new_module']:
        #    return {'is_needs_revision': needs_revision}

        if not iw.history:
            iw.history = self.get_history(
                iw,
                cachedir=self.cachedir,
                usecache=True
            )

        maintainers = [x for x in self.ansible_members if x not in BOTNAMES]
        if self.meta.get('module_match'):
            maintainers += self.meta['module_match'].get('maintainers', [])

        if iw.pullrequest.mergeable_state != 'clean':
            needs_revision = True
            if iw.pullrequest.mergeable_state == 'unstable':
                pass
            else:
                needs_rebase = True
        else:
            for event in iw.history.history:
                if event['actor'] in maintainers:
                    if event['event'] == 'labeled':
                        if event['label'] == 'needs_revision':
                            needs_revision = True
                    if event['event'] == 'unlabeled':
                        if event['label'] == 'needs_revision':
                            needs_revision = False
                if needs_revision and event['actor'] == iw.submitter:
                    if event['event'] == 'commented':
                        if 'ready_for_review' in event['body']:
                            needs_revision = False

        #if needs_revision and not needs_rebase:
        #    print(iw.html_url)
        #    import epdb; epdb.st()

        return {'is_needs_revision': needs_revision,
                'is_needs_rebase': needs_rebase}


    def get_community_review_facts(self, issuewrapper, meta):
        # Thanks @jpeck-resilient for this new module. When this module
        # receives 'shipit' comments from two community members and any
        # 'needs_revision' comments have been resolved, we will mark for
        # inclusion

        community_review = False

        iw = issuewrapper
        if not iw.is_pullrequest():
            return {'is_community_review': community_review}
        if not meta['is_new_module']:
            return {'is_community_review': community_review}

        if not ['shipit'] and not meta['is_needs_revision']:
            community_review = True

        return {'is_community_review': community_review}
