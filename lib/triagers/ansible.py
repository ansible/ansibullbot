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
import pytz
import re
import time

import lib.constants as C

from pprint import pprint
from lib.triagers.defaulttriager import DefaultTriager
from lib.wrappers.ghapiwrapper import GithubWrapper
from lib.wrappers.issuewrapper import IssueWrapper

from lib.utils.extractors import extract_pr_number_from_comment
from lib.utils.moduletools import ModuleIndexer
from lib.utils.version_tools import AnsibleVersionIndexer
from lib.utils.file_tools import FileIndexer
from lib.utils.webscraper import GithubWebScraper

from lib.decorators.github import RateLimited


BOTNAMES = ['ansibot', 'gregdek', 'robynbergeron']
REPOS = [
    'ansible/ansible',
    'ansible/ansible-modules-core',
    'ansible/ansible-modules-extras'
]
MREPOS = [x for x in REPOS if 'modules' in x]
REPOMERGEDATE = datetime.datetime(2016, 12, 6, 0, 0, 0)
MREPO_CLOSE_WINDOW = 60
MAINTAINERS_FILES = ['MAINTAINERS.txt']
FILEMAP_FILENAME = 'FILEMAP.json'

ERROR_CODES = {
    'shippable_failure': 1,
    'travis-ci': 2,
    'throttled': 3,
    'dirty': 4,
    'labeled': 5,
    'review': 6
}


class AnsibleTriage(DefaultTriager):

    EMPTY_ACTIONS = {
        'newlabel': [],
        'unlabel': [],
        'comments': [],
        'assign': [],
        'unassign': [],
        'close': False,
        'close_migrated': False,
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
        'owner_pr'
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
        'bot_status',
        'bot_broken',
        '!bot_broken',
        'bot_skip',
        '!bot_skip',
        'wontfix',
        'bug_resolved',
        'resolved_by_pr',
        'needs_contributor',
        '!needs_contributor',
        'needs_rebase',
        '!needs_rebase',
        'needs_revision',
        '!needs_revision',
        'shipit',
        '!shipit',
        'duplicate_of',
        'closeme'
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

        self.gh_pass = C.DEFAULT_GITHUB_PASSWORD
        self.github_pass = C.DEFAULT_GITHUB_PASSWORD
        self.gh_token = C.DEFAULT_GITHUB_TOKEN
        self.github_token = C.DEFAULT_GITHUB_TOKEN
        self.gh_user = C.DEFAULT_GITHUB_USERNAME
        self.github_user = C.DEFAULT_GITHUB_USERNAME

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

        # where to store junk
        self.cachedir = '~/.ansibullbot/cache'
        self.cachedir = os.path.expanduser(self.cachedir)
        self.cachedir_base = self.cachedir

        # repo objects
        self.repos = {}

        # scraped summaries for all issues
        self.issue_summaries = {}

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

        if hasattr(self.args, 'pause') and self.args.pause:
            self.always_pause = True

        # connect to github
        self.gh = self._connect()

        # wrap the connection
        self.ghw = GithubWrapper(self.gh)

        # create the scraper for www data
        self.gws = GithubWebScraper(cachedir=self.cachedir)
        #print(self.gws.get_last_number('ansible/ansible'))
        #sys.exit(1)
        #import epdb; epdb.st()

        # get the ansible members
        self.ansible_members = self.get_ansible_members()

        # get valid labels
        self.valid_labels = self.get_valid_labels('ansible/ansible')

        # extend managed labels
        self.MANAGED_LABELS += self.ISSUE_TYPES.values()

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

    def start(self):

        if hasattr(self.args, 'force_rate_limit') and \
                self.args.force_rate_limit:
            logging.warning('attempting to trigger rate limit')
            self.trigger_rate_limit()
            return

        if hasattr(self.args, 'daemonize') and self.args.daemonize:
            logging.info('starting daemonize loop')
            self.loop()
        else:
            logging.info('starting single run')
            self.run()
        logging.info('stopping bot')

    def set_logger(self):
        if hasattr(self.args, 'debug') and self.args.debug:
            logging.level = logging.DEBUG
        else:
            logging.level = logging.INFO
        logFormatter = \
            logging.Formatter("%(asctime)s %(levelname)s %(message)s")
        rootLogger = logging.getLogger()
        if hasattr(self.args, 'debug') and self.args.debug:
            rootLogger.setLevel(logging.DEBUG)
        else:
            rootLogger.setLevel(logging.INFO)

        if hasattr(self.args, 'logfile'):
            logfile = self.args.logfile
        else:
            logfile = '/tmp/ansibullbot.log'
        fileHandler = logging.FileHandler("{0}/{1}".format(
                os.path.dirname(logfile),
                os.path.basename(logfile))
        )
        fileHandler.setFormatter(logFormatter)
        rootLogger.addHandler(fileHandler)
        consoleHandler = logging.StreamHandler()
        consoleHandler.setFormatter(logFormatter)
        rootLogger.addHandler(consoleHandler)

    def get_rate_limit(self):
        return self.gh.get_rate_limit().raw_data

    def loop(self):
        '''Call the run method in a defined interval'''
        while True:
            self.run()
            interval = self.args.daemonize_interval
            logging.info('sleep %ss (%sm)' % (interval, interval / 60))
            time.sleep(interval)

    def run(self):
        '''Primary execution method'''

        # get all of the open issues [or just one]
        self.collect_repos()

        # stop here if we're just collecting issues to populate cache
        if self.args.collect_only:
            return

        # loop through each repo made by collect_repos
        for item in self.repos.items():
            repopath = item[0]
            repo = item[1]['repo']

            # skip repos based on args
            if self.skiprepo:
                if repopath in self.skiprepo:
                    continue
            if self.args.skip_module_repos and 'module' in repopath:
                continue
            if self.args.module_repos_only and 'module' not in repopath:
                continue

            # set the relative cachedir
            self.cachedir = os.path.join(self.cachedir_base, repopath)
            #import epdb; epdb.st()
            # this is where the issue history cache goes
            hcache = os.path.join(self.cachedir, repopath)
            # scrape all summaries from www for later opchecking
            self.update_issue_summaries(repopath=repopath)

            for issue in item[1]['issues']:

                iw = None
                self.issue = None
                self.meta = {}
                self.actions = {}
                number = issue.number
                self.number = number

                # keep track of known issues
                self.repos[repopath]['processed'].append(number)

                # skip issues based on args
                if self.args.start_at:
                    if number < self.args.start_at:
                        logging.info('(start_at) skip %s' % number)
                        redo = False
                        continue
                if self.args.start_at:
                    if number > self.start_at:
                        continue
                    else:
                        # unset for daemonize loops
                        self.args.start_at = None
                if issue.state == 'closed':
                    logging.info(str(number) + ' is closed, skipping')
                    redo = False
                    continue

                if self.args.only_prs and 'pull' not in issue.html_url:
                    logging.info(str(number) + ' is issue, skipping')
                    redo = False
                    continue
                if self.args.only_issues and 'pull' in issue.html_url:
                    logging.info(str(number) + ' is pullrequest, skipping')
                    redo = False
                    continue

                # users may want to re-run this issue after manual intervention
                redo = True

                # keep track of how many times this isssue has been re-done
                loopcount = 0

                while redo:

                    # use the loopcount to check new data
                    loopcount += 1

                    if loopcount <= 1:
                        logging.info('starting triage for %s' % issue.html_url)
                    else:
                        # if >1 get latest data
                        logging.info('restarting triage for %s' % number)
                        issue = repo.get_issue(number)

                    # clear redo
                    redo = False

                    # create the wrapper
                    iw = IssueWrapper(
                        repo=repo,
                        issue=issue,
                        cachedir=self.cachedir
                    )

                    if self.args.skip_no_update:
                        lmeta = self.load_meta(iw)
                        if lmeta:
                            if lmeta['updated_at'] == iw.updated_at.isoformat():
                                msg = 'skipping: no changes since last run'
                                logging.info(msg)
                                continue

                    # pre-processing for non-module repos
                    if iw.repo_full_name not in MREPOS:
                        # force an update on the PR data
                        iw.update_pullrequest()
                        # build the history
                        self.build_history(iw)

                    # set the global issue
                    self.issue = iw

                    if iw.repo_full_name not in MREPOS:
                        # basic processing for ansible/ansible
                        self.process(iw)
                    else:
                        # module repo processing ...
                        self.run_module_repo_issue(iw, hcache=hcache)
                        # do nothing else on these repos
                        redo = False
                        continue

                    # build up actions from the meta
                    self.create_actions()
                    #self.issue.meta = self.meta
                    self.save_meta(iw, self.meta)

                    # DEBUG!
                    logging.info('url: %s' % self.issue.html_url)
                    logging.info('title: %s' % self.issue.title)
                    logging.info(
                        'component: %s' %
                        self.template_data.get('component_raw')
                    )
                    if self.meta['is_needs_revision']:
                        logging.info('needs_revision')
                        for msg in self.meta['is_needs_revision_msgs']:
                            logging.info('needs_revision_msg: %s' % msg)
                    if self.meta['is_needs_rebase']:
                        logging.info('needs_rebase')
                        for msg in self.meta['is_needs_rebase_msgs']:
                            logging.info('needs_rebase_msg: %s' % msg)

                    # DEBUG!
                    #import epdb; epdb.st()
                    if self.meta.get('mergeable_state') == 'unknown' or \
                            'needs_rebase' in self.actions['newlabel'] or \
                            'needs_rebase' in self.actions['unlabel'] or \
                            'needs_revision' in self.actions['newlabel'] or \
                            'needs_revision' in self.actions['unlabel']:
                        rn = self.issue.repo_full_name
                        #import epdb; epdb.st()
                        summary = self.issue_summaries.get(rn, {}).\
                            get(self.issue.number, None)
                        if not summary:
                            summary = self.gws.get_single_issue_summary(
                                rn,
                                self.issue.number,
                                force=True
                            )
                        pprint(summary)

                        if self.meta.get('mergeable_state') == 'unknown':
                            pprint(self.actions)
                            import epdb; epdb.st()

                    pprint(self.actions)

                    # do the actions
                    action_meta = self.apply_actions()
                    if action_meta['REDO']:
                        redo = True

                logging.info('finished triage for %s' % str(iw))

    def update_issue_summaries(self, repopath=None):

        if repopath:
            repopaths = [repopath]
        else:
            repopaths = [x for x in REPOS]

        for rp in repopaths:

            # scrape all summaries rom www for later opchecking
            cachefile = os.path.join(
                self.cachedir,
                '%s__scraped_issues.json' % rp
            )
            self.issue_summaries[repopath] = self.gws.get_issue_summaries(
                'https://github.com/%s' % rp,
                cachefile=cachefile
            )

    def update_single_issue_summary(self, issuewrapper):
        '''Force scrape the summary for an issue'''
        number = issuewrapper.number
        rp = issuewrapper.repo_full_name
        self.issue_summaries[rp][number] = \
            self.gws.get_single_issue_summary(rp, number, force=True)

    @RateLimited
    def update_issue_object(self, issue):
        issue.update()
        return issue

    def save_meta(self, issuewrapper, meta):
        # save the meta+actions
        dmeta = meta.copy()
        dmeta['title'] = issuewrapper.title
        dmeta['html_url'] = issuewrapper.html_url
        dmeta['created_at'] = issuewrapper.created_at.isoformat()
        dmeta['updated_at'] = issuewrapper.updated_at.isoformat()
        dmeta['template_data'] = issuewrapper.template_data
        dmeta['actions'] = self.actions.copy()
        dmeta['labels'] = issuewrapper.labels
        dmeta['assigees'] = issuewrapper.assignees
        if issuewrapper.history:
            dmeta['history'] = issuewrapper.history.history
            for idx,x in enumerate(dmeta['history']):
                dmeta['history'][idx]['created_at'] = \
                    x['created_at'].isoformat()
        else:
            dmeta['history'] = []
        if issuewrapper.is_pullrequest():
            dmeta['pullrequest_status'] = issuewrapper.pullrequest_status
            dmeta['pullrequest_reviews'] = issuewrapper.reviews
        else:
            dmeta['pullrequest_status'] = []
            dmeta['pullrequest_reviews'] = []

        self.dump_meta(issuewrapper, dmeta)

    def run_module_repo_issue(self, iw, hcache=None):
        ''' Module Repos are dead!!! '''

        if iw.created_at >= REPOMERGEDATE:
            # close new module issues+prs immediately
            logging.info('module issue created -after- merge')
            self.close_module_issue_with_message(iw)
            self.save_meta(iw, {'updated_at': iw.updated_at.isoformat()})
            return
        else:
            # process history
            # - check if message was given, comment if not
            # - if X days after message, close PRs, move issues.
            logging.info('module issue created -before- merge')

            lc = iw.history.last_date_for_boilerplate('repomerge')
            if lc:
                # needs to be tz aware
                now = pytz.utc.localize(datetime.datetime.now())
                lcdelta = (now - lc).days
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
                    #kwargs['close'] = True
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
            self.save_meta(iw, {'updated_at': iw.updated_at.isoformat()})

    def load_meta(self, issuewrapper):
        mfile = os.path.join(
            issuewrapper.full_cachedir,
            'meta.json'
        )
        meta = {}
        if os.path.isfile(mfile):
            with open(mfile, 'rb') as f:
                meta = json.load(f)
        return meta

    def dump_meta(self, issuewrapper, meta):
        mfile = os.path.join(
            issuewrapper.full_cachedir,
            'meta.json'
        )
        meta['time'] = datetime.datetime.now().isoformat()
        logging.info('dump meta to %s' % mfile)
        with open(mfile, 'wb') as f:
            json.dump(meta, f, sort_keys=True, indent=2)
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
            if 'assign' not in v:
                jdata[k]['assign'] = []
            if 'notify' not in v:
                jdata[k]['notify'] = []
            if 'labels' not in v:
                jdata[k]['labels'] = []
        return jdata

    def create_actions(self):
        '''Parse facts and make actiosn from them'''

        if 'bot_broken' in self.meta['maintainer_commands'] or \
                'bot_broken' in self.meta['submitter_commands'] or \
                'bot_broken' in self.issue.labels:
            logging.warning('bot broken!')
            self.actions = copy.deepcopy(self.EMPTY_ACTIONS)
            if 'bot_broken' not in self.issue.labels:
                self.actions['newlabel'].append('bot_broken')
            return None

        elif 'bot_skip' in self.meta['maintainer_commands'] or \
                'bot_skip' in self.meta['submitter_commands']:
            self.actions = copy.deepcopy(self.EMPTY_ACTIONS)
            return None

        # UNKNOWN!!! ... sigh.
        if self.issue.is_pullrequest() and \
                self.meta['mergeable_state'] == 'unknown':
            msg = 'skipping %s because it has a' % self.issue.number
            msg += ' mergeable_state of unknown'
            logging.warning(msg)
            self.actions = copy.deepcopy(self.EMPTY_ACTIONS)
            return None

        # TRIAGE!!!
        if not self.issue.labels:
            self.actions['newlabel'].append('needs_triage')
        if 'triage' in self.issue.labels:
            if 'needs_triage' not in self.issue.labels:
                self.actions['newlabel'].append('needs_triage')
            self.actions['unlabel'].append('triage')

        # REVIEWS
        for rtype in ['core_review', 'committer_review', 'community_review']:
            if self.meta[rtype]:
                if rtype not in self.issue.labels:
                    self.actions['newlabel'].append(rtype)
            else:
                if rtype in self.issue.labels:
                    self.actions['unlabel'].append(rtype)

        # Ignore needs_revision if this is a work in progress
        if not self.issue.wip:

            # SHIPIT
            if self.meta['shipit'] and \
                    self.meta['mergeable'] and \
                    not self.meta['is_needs_revision'] and \
                    not self.meta['is_needs_rebase'] and \
                    not self.meta['is_needs_info']:

                logging.info('shipit')
                if self.meta['is_module'] and self.meta['module_match']:
                    if len(self.issue.files) == 1:
                        if not self.meta['is_new_module']:
                            metadata = self.meta['module_match']['metadata']
                            supported_by = metadata.get('supported_by')
                            if supported_by == 'community':
                                logging.info('auto-merge tests passed')
                                if 'automerge' not in self.issue.labels:
                                    self.actions['newlabel'].append('automerge')
                                self.actions['merge'] = True

                if 'shipit' not in self.issue.labels:
                    self.actions['newlabel'].append('shipit')
            else:
                if 'shipit' in self.issue.labels:
                    self.actions['unlabel'].append('shipit')
                if 'automerge' in self.issue.labels:
                    self.actions['unlabel'].append('automerge')

            # needs revision
            if self.meta['is_needs_revision'] or self.meta['is_bad_pr']:
                if 'needs_revision' not in self.issue.labels:
                    self.actions['newlabel'].append('needs_revision')
            else:
                if 'needs_revision' in self.issue.labels:
                    self.actions['unlabel'].append('needs_revision')

        else:
            if 'shipit' in self.issue.labels:
                self.actions['unlabel'].append('shipit')

        # owner PRs
        if self.meta['owner_pr']:
            if 'owner_pr' not in self.issue.labels:
                self.actions['newlabel'].append('owner_pr')
        else:
            if 'owner_pr' in self.issue.labels:
                self.actions['unlabel'].append('owner_pr')

        if self.meta['is_needs_rebase'] or self.meta['is_bad_pr']:
            if 'needs_rebase' not in self.issue.labels:
                    self.actions['newlabel'].append('needs_rebase')
        else:
            if 'needs_rebase' in self.issue.labels:
                    self.actions['unlabel'].append('needs_rebase')

        # travis-ci.org ...
        if self.meta['has_travis'] and not self.meta['has_travis_notification']:
            tvars = {'submitter': self.issue.submitter}
            comment = self.render_boilerplate(
                tvars,
                boilerplate='travis_notify'
            )
            if comment not in self.actions['comments']:
                self.actions['comments'].append(comment)

        if self.meta['is_new_module'] or self.meta['is_module']:
            # add topic labels
            for t in ['topic', 'subtopic']:
                label = self.meta['module_match'].get(t)
                if label in self.MODULE_NAMESPACE_LABELS:
                    label = self.MODULE_NAMESPACE_LABELS[label]

                if label and label in self.valid_labels and \
                        label not in self.issue.labels:
                    self.actions['newlabel'].append(label)

            # add namespace labels
            namespace = self.meta['module_match'].get('namespace')
            if namespace in self.MODULE_NAMESPACE_LABELS:
                label = self.MODULE_NAMESPACE_LABELS[namespace]
                if label not in self.issue.labels:
                    self.actions['newlabel'].append(label)

        if self.meta['is_new_module']:
            if 'new_module' not in self.issue.labels:
                self.actions['newlabel'].append('new_module')
        else:
            if 'new_module' in self.issue.labels:
                self.actions['unlabel'].append('new_module')

        if self.meta['is_module']:
            if 'module' not in self.issue.labels:
                # don't add manually removed label
                if not self.issue.history.was_unlabeled(
                    'module',
                    bots=BOTNAMES
                ):
                    self.actions['newlabel'].append('module')
        else:
            if 'module' in self.issue.labels:
                # don't remove manually added label
                if not self.issue.history.was_labeled(
                    'module',
                    bots=BOTNAMES
                ):
                    self.actions['unlabel'].append('module')

        # component labels
        if self.meta['component_labels']:
            for cl in self.meta['component_labels']:
                ul = self.issue.history.was_unlabeled(cl, bots=BOTNAMES)
                if not ul and \
                        cl not in self.issue.labels and \
                        cl not in self.actions['newlabel']:
                    self.actions['newlabel'].append(cl)

        if self.meta['ansible_label_version']:
            label = 'affects_%s' % self.meta['ansible_label_version']
            if label not in self.issue.labels:
                # do not re-add version labels
                if not self.issue.history.was_unlabeled(label):
                    self.actions['newlabel'].append(label)

        if self.meta['issue_type']:
            label = self.ISSUE_TYPES.get(self.meta['issue_type'])
            if label and label not in self.issue.labels:
                # do not re-add issue type labels
                if not self.issue.history.was_unlabeled(label):
                    self.actions['newlabel'].append(label)

        # use the filemap to add labels
        if self.issue.is_pullrequest():
            fmap_labels = self.get_filemap_labels_for_files(self.issue.files)
            for label in fmap_labels:
                if label in self.valid_labels and \
                        label not in self.issue.labels:
                    # do not re-add these labels
                    if not self.issue.history.was_unlabeled(label):
                        self.actions['newlabel'].append(label)

        # python3 ... obviously!
        if self.meta['is_py3']:
            if 'python3' not in self.issue.labels:
                # do not re-add py3
                if not self.issue.history.was_unlabeled(label):
                    self.actions['newlabel'].append('python3')

        # needs info?
        if self.meta['is_needs_info']:
            if 'needs_info' not in self.issue.labels:
                self.actions['newlabel'].append('needs_info')
        elif 'needs_info' in self.issue.labels:
            self.actions['unlabel'].append('needs_info')

        # assignees?
        if self.meta['to_assign']:
            for user in self.meta['to_assign']:
                # don't re-assign people
                if not self.issue.history.was_unassigned(user):
                    self.actions['assign'].append(user)

        # notify?
        if self.meta['to_notify']:
            tvars = {'notify': self.meta['to_notify']}
            comment = self.render_boilerplate(tvars, boilerplate='notify')
            if comment not in self.actions['comments']:
                self.actions['comments'].append(comment)

        # needs_contributor
        if 'needs_contributor' in self.meta['maintainer_commands']:
            if 'waiting_on_contributor' not in self.issue.labels:
                self.actions['newlabel'].append('waiting_on_contributor')
        elif 'waiting_on_contributor' in self.issue.labels:
                self.actions['unlabel'].append('waiting_on_contributor')

        # wontfix / notabug / bug_resolved / resolved_by_pr / duplicate_of
        if 'wontfix' in self.meta['maintainer_commands']:
            self.actions['close'] = True
        if 'notabug' in self.meta['maintainer_commands']:
            self.actions['close'] = True
        if 'bug_resolved' in self.meta['maintainer_commands']:
            self.actions['close'] = True
        if 'duplicate_of' in self.meta['maintainer_commands']:
            self.actions['close'] = True
        if 'resolved_by_pr' in self.meta['maintainer_commands']:
            # 'resolved_by_pr': {'merged': True, 'number': 19141},
            if self.meta['resolved_by_pr']['merged']:
                self.actions['close'] = True

        # migrated and source closed?
        if self.meta['is_migrated']:
            if self.meta['migrated_issue_state'] != 'closed':
                self.actions['close_migrated'] = True

        # bot_status
        if self.meta['needs_bot_status']:
            comment = self.render_boilerplate(
                self.meta,
                boilerplate='bot_status'
            )
            if comment not in self.actions['comments']:
                self.actions['comments'].append(comment)

        # label commands
        if self.meta['label_cmds']:
            if self.meta['label_cmds']['add']:
                for label in self.meta['label_cmds']['add']:
                    if label not in self.issue.labels:
                        self.actions['newlabel'].append(label)
                    if label in self.actions['unlabel']:
                        self.actions['unlabel'].remove(label)
            if self.meta['label_cmds']['del']:
                for label in self.meta['label_cmds']['del']:
                    if label in self.issue.labels:
                        self.actions['unlabel'].append(label)
                    if label in self.actions['newlabel']:
                        self.actions['newlabel'].remove(label)

        self.actions['newlabel'] = sorted(set(self.actions['newlabel']))
        self.actions['unlabel'] = sorted(set(self.actions['unlabel']))
        #import epdb; epdb.st()

    def check_safe_match(self):
        safe = True
        for k,v in self.actions.iteritems():
            if k == 'merge' and v:
                safe = False
                continue
            if k == 'newlabel' or k == 'unlabel':
                if 'needs_revision' in v or 'needs_rebase' in v:
                    safe = False
                else:
                    continue
            if k == 'comments' and len(v) == 0:
                continue
            if k == 'comments' and len(v) == 1:
                # notifying maintainer
                if v[0].startswith('cc '):
                    continue
            if k == 'assign':
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

    def get_filemap_users_for_files(self, files):
        '''Get expected notifiees from the filemap'''
        to_notify = []
        to_assign = []

        exclusive = False
        for f in files:

            # only one match
            if exclusive:
                continue

            for k,v in self.FILEMAP.iteritems():
                if not v['inclusive'] and v['regex'].match(f):
                    to_notify = v['notify']
                    to_assign = v['assign']
                    exclusive = True
                    break

                if 'notify' not in v and 'assign' not in v:
                    continue

                if v['regex'].match(f):
                    for user in v['notify']:
                        if user not in to_notify:
                            to_notify.append(user)
                    for user in v['assign']:
                        if user not in to_assign:
                            to_assign.append(user)

        return (to_notify, to_assign)

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

    def trigger_rate_limit(self):
        '''Repeatedly make calls to exhaust rate limit'''

        self.gh = self._connect()
        self.ghw = GithubWrapper(self.gh)

        while True:
            for repo in REPOS:
                cachedir = os.path.join(self.cachedir, repo)
                thisrepo = self.ghw.get_repo(repo, verbose=False)
                issues = thisrepo.repo.get_issues()
                rl = thisrepo.get_rate_limit()
                pprint(rl)

                for issue in issues:
                    iw = IssueWrapper(
                            repo=thisrepo,
                            issue=issue,
                            cachedir=cachedir
                    )
                    iw.history
                    rl = thisrepo.get_rate_limit()
                    pprint(rl)

    def collect_repos(self):
        '''Populate the local cache of repos'''
        # this should do a few things:
        logging.info('start collecting repos')

        logging.debug('creating github connection object')
        self.gh = self._connect()

        logging.info('creating github connection wrapper')
        self.ghw = GithubWrapper(self.gh)

        for repo in REPOS:

            # skip repos based on args
            if self.skiprepo:
                if repo in self.skiprepo:
                    continue
            if self.args.skip_module_repos and 'module' in repo:
                continue
            if self.args.module_repos_only and 'module' not in repo:
                continue

            logging.info('getting repo obj for %s' % repo)

            if repo not in self.repos:
                self.repos[repo] = {
                    'repo': self.ghw.get_repo(repo, verbose=False),
                    'issues': [],
                    'processed': [],
                    'since': None
                }
            else:
                # force a clean repo object to limit caching problems
                self.repos[repo]['repo'] = \
                    self.ghw.get_repo(repo, verbose=False)
                # clear the issues
                self.repos[repo]['issues'] = {}

            logging.info('getting issue objs for %s' % repo)
            if self.pr:
                logging.info('fetch %s' % self.pr)
                issue = self.repos[repo]['repo'].get_issue(self.pr)
                self.repos[repo]['issues'] = [issue]
            else:

                if not self.repos[repo]['since']:
                    # get all of them
                    issues = self.repos[repo]['repo'].get_issues()
                    self.repos[repo]['since'] = datetime.datetime.utcnow()
                else:
                    # get updated since last run + newly created
                    issues = self.repos[repo]['repo'].get_issues(
                        since=self.repos[repo]['since']
                    )
                    # reset the since marker
                    self.repos[repo]['since'] = datetime.datetime.utcnow()

                    # force pagination now
                    issues = [x for x in issues]

                    # get newly created issues
                    logging.info('getting last issue number for %s' % repo)
                    last_number = self.gws.get_last_number(repo)

                    since_numbers = [x.number for x in issues]
                    current_numbers = sorted(set(self.repos[repo]['processed']))
                    missing_numbers = xrange(current_numbers[-1], last_number)
                    missing_numbers = [x for x in missing_numbers
                                       if x not in current_numbers and
                                       x not in since_numbers]

                    logging.info(
                        'issue numbers not returned via "since": %s'
                        % ','.join([str(x) for x in missing_numbers])
                    )

                    for x in missing_numbers:
                        issue = None
                        try:
                            issue = self.repos[repo]['repo'].get_issue(x)
                        except Exception as e:
                            print(e)
                            import epdb; epdb.st()
                        if issue and \
                                issue.state == 'open' and \
                                issue not in issues:
                            issues.append(issue)

                self.repos[repo]['issues'] = issues

            logging.info('getting repo objs for %s complete' % repo)

        logging.info('finished collecting issues')

    def get_updated_issues(self, since=None):
        '''Get issues to work on'''
        # this should return a list of issueids that changed since the last run
        logging.info('start querying updated issues')

        # these need to be tuples (namespace, repo, number)
        issueids = []

        logging.info('finished querying updated issues')
        return issueids

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
        self.meta['is_migrated'] = False

        if iw.is_issue():
            if self.template_data.get('component name'):

                match = self.find_module_match(iw.title, self.template_data)
                if match:
                    self.meta['is_module'] = True
                    self.meta['is_plugin'] = True
                    self.meta['module_match'] = copy.deepcopy(match)
                    self.meta['component'] = match['name']

        elif len(iw.files) > 100:
            # das merge?
            self.meta['bad_pr'] = True

        else:
            # assume pullrequest
            for f in iw.files:

                if f.startswith('lib/ansible/modules/core') or \
                        f.startswith('lib/ansible/modules/extras'):
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

        # get labels for files ...
        if not iw.is_pullrequest():
            self.meta['is_issue'] = True
            self.meta['is_pullrequest'] = False
            self.meta['component_labels'] = []
        else:
            self.meta['is_issue'] = False
            self.meta['is_pullrequest'] = True
            self.meta['component_labels'] = self.get_component_labels(
                self.valid_labels,
                iw.files
            )

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

        # python3 ?
        self.meta['is_py3'] = self.is_python3()

        # shipit?
        self.meta.update(self.get_needs_revision_facts(iw, self.meta))
        self.meta.update(self.get_notification_facts(iw, self.meta))

        # needsinfo?
        self.meta['is_needs_info'] = self.is_needsinfo()
        self.meta.update(self.process_comment_commands(iw, self.meta))

        # shipit?
        self.meta.update(self.get_shipit_facts(iw, self.meta))
        self.meta.update(self.get_review_facts(iw, self.meta))

        # bot_status needed?
        self.meta.update(self.needs_bot_status(iw))

        # who is this waiting on?
        self.meta.update(self.waiting_on(iw, self.meta))

        # community triage
        self.meta.update(self.get_label_commands(iw, self.meta))

        if iw.migrated:
            miw = iw._migrated_issue
            self.meta['is_migrated'] = True
            self.meta['migrated_from'] = str(miw)
            self.meta['migrated_issue_repo_path'] = miw.repo.repo_path
            self.meta['migrated_issue_number'] = miw.number
            self.meta['migrated_issue_state'] = miw.state

    def find_module_match(self, title, template_data):

        match = None

        cname = template_data.get('component name')
        craw = template_data.get('component_raw')

        if self.module_indexer.find_match(cname, exact=True):
            match = self.module_indexer.find_match(cname, exact=True)
        elif template_data.get('component_raw') \
                and ('module' in title or
                     'module' in craw or
                     'action' in craw):
            # FUZZY MATCH?
            logging.info('fuzzy match module component')
            fm = self.module_indexer.fuzzy_match(
                title=title,
                component=craw
            )
            if fm:
                match = self.module_indexer.find_match(fm)
        else:
            pass

        return match

    def build_history(self, issuewrapper):
        '''Set the history and merge other event sources'''
        iw = issuewrapper
        iw._history = False
        iw.history

        if iw.migrated:
            mi = self.get_migrated_issue(iw.migrated_from)
            iw.history.merge_history(mi.history.history)
            iw._migrated_issue = mi

        if iw.is_pullrequest():
            iw.history.merge_reviews(iw.reviews)
            iw.history.merge_commits(iw.commits)

        return iw

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
        for label in issue.labels:
            if label not in self.MANAGED_LABELS:
                self.debug('keeping %s label' % label)
                self.issue.add_desired_label(name=label)

    def get_migrated_issue(self, migrated_issue):
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
        elif '/' in migrated_issue:
            miparts = migrated_issue.split('/')
            minumber = int(miparts[-1])
            mirepopath = '/'.join(miparts[0:2])
        else:
            print(migrated_issue)
            import epdb; epdb.st()

        mw = self.get_issue_by_repopath_and_number(
            mirepopath,
            minumber
        )

        return mw

    def get_issue_by_repopath_and_number(self, repo_path, number):

        # get the repo if not already fetched
        if repo_path not in self.repos:
            self.repos[repo_path] = {
                'repo': self.ghw.get_repo(repo_path, verbose=False),
                'issues': {}
            }

        mrepo = self.repos[repo_path]['repo']
        missue = mrepo.get_issue(number)
        mw = IssueWrapper(
            repo=mrepo,
            issue=missue,
            cachedir=os.path.join(self.cachedir, repo_path)
        )
        return mw

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
            'owner_pr': False,
            'shipit_ansible': False,
            'shipit_community': False,
            'shipit_count_community': False,
            'shipit_count_maintainer': False,
            'shipit_count_ansible': False,
        }

        if not iw.is_pullrequest():
            return nmeta
        if not meta['module_match']:
            return nmeta

        maintainers = meta['module_match']['maintainers']
        maintainers = \
            ModuleIndexer.replace_ansible(
                maintainers,
                self.ansible_members,
                bots=BOTNAMES
            )

        if not meta['is_new_module'] and iw.submitter in maintainers:
            nmeta['owner_pr'] = True

        # community is the other maintainers in the same namespace
        mnamespace = meta['module_match']['namespace']
        community = \
            self.module_indexer.get_maintainers_for_namespace(mnamespace)
        community = [x for x in community if x != 'ansible']

        # shipit tallies
        ansible_shipits = 0
        maintainer_shipits = 0
        community_shipits = 0
        shipit_actors = []

        for event in iw.history.history:

            if event['event'] not in ['commented', 'committed']:
                continue
            if event['actor'] in BOTNAMES:
                continue

            # commits reset the counters
            if event['event'] == 'committed':
                ansible_shipits = 0
                maintainer_shipits = 0
                community_shipits = 0
                shipit_actors = []
                continue

            actor = event['actor']
            body = event['body']

            # ansible shipits
            if actor in self.ansible_members:
                if 'shipit' in body or '+1' in body or 'LGTM' in body:
                    logging.info('%s shipit' % actor)
                    ansible_shipits += 1
                    if actor not in shipit_actors:
                        shipit_actors.append(actor)
                    continue

            # maintainer shipits
            if actor in maintainers:
                if 'shipit' in body or '+1' in body or 'LGTM' in body:
                    logging.info('%s shipit' % actor)
                    maintainer_shipits += 1
                    if actor not in shipit_actors:
                        shipit_actors.append(actor)
                    continue

            # community shipits
            if actor != iw.submitter and actor in community:
                if 'shipit' in body or '+1' in body or 'LGTM' in body:
                    logging.info('%s shipit' % actor)
                    community_shipits += 1
                    if actor not in shipit_actors:
                        shipit_actors.append(actor)
                    continue

        nmeta['shipit_count_community'] = community_shipits
        nmeta['shipit_count_maintainer'] = maintainer_shipits
        nmeta['shipit_count_ansible'] = ansible_shipits

        if (community_shipits + maintainer_shipits + ansible_shipits) > 1:
            nmeta['shipit'] = True

        logging.info(
            'total shipits: %s' %
            (community_shipits + maintainer_shipits + ansible_shipits)
        )

        return nmeta

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

        return mf

    def is_needsinfo(self):

        needs_info = False

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

        # a "dirty" mergeable_state can exist with "successfull" ci_state.

        committer_count = None
        needs_revision = False
        needs_revision_msgs = []
        merge_commits = False
        needs_rebase = False
        needs_rebase_msgs = []
        has_shippable = False
        has_travis = False
        has_travis_notification = False
        ci_state = None
        mstate = None
        change_requested = None
        #hreviews = None
        #reviews = None
        ready_for_review = None

        rmeta = {
            'committer_count': committer_count,
            'is_needs_revision': needs_revision,
            'is_needs_revision_msgs': needs_revision_msgs,
            'is_needs_rebase': needs_rebase,
            'is_needs_rebase_msgs': needs_rebase_msgs,
            'has_shippable': has_shippable,
            'has_travis': has_travis,
            'has_travis_notification': has_travis_notification,
            'merge_commits': merge_commits,
            'mergeable': None,
            'mergeable_state': mstate,
            'change_requested': change_requested,
            'ci_state': ci_state,
            'reviews': None,
            'www_reviews': None,
            'www_summary': None,
            'ready_for_review': ready_for_review
        }

        iw = issuewrapper
        if not iw.is_pullrequest():
            return rmeta

        maintainers = [x for x in self.ansible_members if x not in BOTNAMES]
        if self.meta.get('module_match'):
            maintainers += self.meta['module_match'].get('maintainers', [])

        # get the exact state from shippable ...
        #   success/pending/failure/... ?
        ci_status = iw.pullrequest_status
        ci_states = [x['state'] for x in ci_status]
        if not ci_states:
            ci_state = None
        else:
            ci_state = ci_states[0]
        logging.info('ci_state == %s' % ci_state)

        # clean/unstable/dirty/unknown
        mstate = iw.mergeable_state
        logging.info('mergeable_state == %s' % mstate)

        # clean/unstable/dirty/unknown
        if mstate != 'clean':

            if ci_state == 'failure':
                needs_revision = True
                needs_revision_msgs.append('ci failure')

            if mstate == 'dirty':
                needs_revision = True
                needs_rebase = True
                needs_revision_msgs.append('mergeable state is dirty')
                needs_rebase_msgs.append('mergeable state is dirty')

            elif mstate == 'unknown':
                # if tests are still running, this needs to be ignored.
                if ci_state not in ['pending']:
                    needs_revision = True
                    needs_revision_msgs.append('mergeable state is unknown')
                    needs_rebase = True
                    needs_rebase_msgs.append('mergeable state is unknown')

            elif mstate == 'unstable':
                # reduce the label churn
                if ci_state == 'pending' and 'needs_revision' in iw.labels:
                    needs_revision = True
                    needs_rebase_msgs.append('keep label till test finished')

        else:

            pending_reviews = []

            for event in iw.history.history:

                if event['actor'] in BOTNAMES:
                    continue

                if event['actor'] in maintainers and \
                        event['actor'] != iw.submitter:

                    if event['event'] == 'labeled':
                        if event['label'] == 'needs_revision':
                            needs_revision = True
                            needs_revision_msgs.append(
                                '[%s] labeled' % event['actor']
                            )
                            continue

                    if event['event'] == 'unlabeled':
                        if event['label'] == 'needs_revision':
                            needs_revision = False
                            needs_revision_msgs.append(
                                '[%s] unlabeled' % event['actor']
                            )
                            continue

                    if event['event'] == 'commented':
                        if '!needs_revision' in event['body']:
                            needs_revision = False
                            needs_revision_msgs.append(
                                '[%s] !needs_revision' % event['actor']
                            )
                            continue

                    if event['event'] == 'commented':
                        if 'needs_revision' in event['body'] and \
                                '!needs_revision' not in event['body']:
                            needs_revision = True
                            needs_revision_msgs.append(
                                '[%s] needs_revision' % event['actor']
                            )
                            continue

                if event['actor'] == iw.submitter:
                    if event['event'] == 'commented':
                        if 'ready_for_review' in event['body']:
                            ready_for_review = True
                            needs_revision = False
                            needs_revision_msgs.append(
                                '[%s] ready_for_review' % event['actor']
                            )
                            continue
                        if 'shipit' in event['body'].lower():
                            ready_for_review = True
                            needs_revision = False
                            needs_revision_msgs.append(
                                '[%s] shipit' % event['actor']
                            )
                            continue

                if event['event'].startswith('review_'):
                    if event['event'] == 'review_changes_requested':
                        pending_reviews.append(event['actor'])
                        needs_revision = True
                        needs_revision_msgs.append(
                            '[%s] changes requested' % event['actor']
                        )
                        continue

                    if event['event'] == 'review_approved':
                        if event['actor'] in pending_reviews:
                            pending_reviews.remove(event['actor'])
                        needs_revision = False
                        needs_revision_msgs.append(
                            '[%s] approved changes' % event['actor']
                        )
                        continue

                    if event['event'] == 'review_dismissed':
                        if event['actor'] in pending_reviews:
                            pending_reviews.remove(event['actor'])
                        needs_revision = False
                        needs_revision_msgs.append(
                            '[%s] dismissed review' % event['actor']
                        )
                        continue

            if pending_reviews:
                change_requested = pending_reviews
                needs_revision = True
                needs_revision_msgs.append(
                    'reviews pending: %s' % ','.join(pending_reviews)
                )

        # Merge commits are bad, force a rebase
        for mc in iw.merge_commits:
            merge_commits = True
            needs_rebase = True
            needs_rebase_msgs.append('merge commit %s' % mc.commit.sha)

        # Count committers
        committer_count = len(sorted(set(iw.committer_emails)))

        if ci_status:
            for x in ci_status:
                if 'travis-ci.org' in x['target_url']:
                    has_travis = True
                    continue
                if 'shippable.com' in x['target_url']:
                    has_shippable = True
                    continue

        if has_travis:
            needs_rebase = True
            needs_rebase_msgs.append('travis-ci found in status')

            # 'has_travis_notification': has_travis_notification,
            if 'travis_notify' in iw.history.get_boilerplate_comments():
                has_travis_notification = True
            else:
                has_travis_notification = False

        logging.info('mergeable_state is %s' % mstate)
        logging.info('needs_rebase is %s' % needs_rebase)
        logging.info('needs_revision is %s' % needs_revision)
        logging.info('ready_for_review is %s' % ready_for_review)

        # Scrape web data for debug purposes
        rfn = self.issue.repo_full_name
        www_summary = self.gws.get_single_issue_summary(rfn, self.issue.number)
        www_reviews = self.gws.scrape_pullrequest_review(rfn, self.issue.number)

        rmeta = {
            'committer_count': committer_count,
            'is_needs_revision': needs_revision,
            'is_needs_revision_msgs': needs_revision_msgs,
            'is_needs_rebase': needs_rebase,
            'is_needs_rebase_msgs': needs_rebase_msgs,
            'has_shippable': has_shippable,
            'has_travis': has_travis,
            'has_travis_notification': has_travis_notification,
            'merge_commits': merge_commits,
            'mergeable': self.issue.pullrequest.mergeable,
            'mergeable_state': mstate,
            'change_requested': change_requested,
            'ci_state': ci_state,
            'reviews': iw.reviews,
            'www_summary': www_summary,
            'www_reviews': www_reviews,
            'ready_for_review': ready_for_review
        }

        return rmeta

    def get_supported_by(self, issuewrapper, meta):

        # https://github.com/ansible/proposals/issues/30
        # core: maintained by the ansible core team.
        # community: This module is maintained by the community at large...
        # unmaintained: This module currently needs a new community contributor
        # committer: Committers to the ansible repository are the gatekeepers...

        supported_by = 'core'
        mmatch = meta.get('module_match')
        if mmatch:
            mmeta = mmatch.get('metadata', {})
            if mmeta:
                supported_by = mmeta.get('supported_by', 'core')
        if meta['is_new_module']:
            supported_by = 'community'
        return supported_by

    def get_review_facts(self, issuewrapper, meta):
        # Thanks @jpeck-resilient for this new module. When this module
        # receives 'shipit' comments from two community members and any
        # 'needs_revision' comments have been resolved, we will mark for
        # inclusion

        # pr is a module
        # pr owned by community or is new
        # pr owned by ansible

        rfacts = {
            'core_review': False,
            'community_review': False,
            'committer_review': False,
        }

        iw = issuewrapper
        if not iw.is_pullrequest():
            return rfacts
        if meta['shipit']:
            return rfacts
        if meta['is_needs_info']:
            return rfacts
        if meta['is_needs_revision']:
            return rfacts
        if meta['is_needs_rebase']:
            return rfacts
        if not meta['is_module']:
            return rfacts

        supported_by = self.get_supported_by(iw, meta)
        if supported_by == 'community':
            rfacts['community_review'] = True
        elif supported_by == 'core':
            rfacts['core_review'] = True
        elif supported_by == 'committer':
            rfacts['committer_review'] = True
        else:
            import epdb; epdb.st()

        return rfacts

    def get_notification_facts(self, issuewrapper, meta):
        '''Build facts about mentions/pings'''
        iw = issuewrapper
        if not iw.history:
            iw.history = self.get_history(
                iw,
                cachedir=self.cachedir,
                usecache=True
            )

        nfacts = {
            'to_notify': [],
            'to_assign': []
        }

        # who is assigned?
        current_assignees = iw.assignees

        # who can be assigned?
        valid_assignees = [x.login for x in iw.repo.assignees]

        # add people from filemap matches
        if iw.is_pullrequest():
            (fnotify, fassign) = self.get_filemap_users_for_files(iw.files)
            for user in fnotify:
                if user == iw.submitter:
                    continue
                if user not in nfacts['to_notify']:
                    if not iw.history.last_notified(user) and \
                            not iw.history.was_assigned(user) and \
                            not iw.history.was_subscribed(user) and \
                            not iw.history.last_comment(user):

                        nfacts['to_notify'].append(user)

            for user in fassign:
                if user == iw.submitter:
                    continue
                if user in nfacts['to_assign']:
                    continue
                if user not in current_assignees and user in valid_assignees:
                    nfacts['to_assign'].append(user)

        # add module maintainers
        if meta.get('module_match'):
            maintainers = meta.get('module_match', {}).get('maintainers', [])

            # do nothing if not maintained
            if maintainers:

                # don't ping us...
                if 'ansible' in maintainers:
                    maintainers.remove('ansible')

                for maintainer in maintainers:

                    # don't notify maintainers of their own issues ... duh
                    if maintainer == iw.submitter:
                        continue

                    if maintainer in valid_assignees and \
                            maintainer not in current_assignees:
                        nfacts['to_assign'].append(maintainer)

                    if maintainer in nfacts['to_notify']:
                        continue

                    if not iw.history.last_notified(maintainer) and \
                            not iw.history.was_assigned(maintainer) and \
                            not iw.history.was_subscribed(maintainer) and \
                            not iw.history.last_comment(maintainer):
                        nfacts['to_notify'].append(maintainer)

        #import epdb; epdb.st()
        return nfacts

    def process_comment_commands(self, issuewrapper, meta):

        vcommands = [x for x in self.VALID_COMMANDS]
        # these are handled by other fact gathering functions
        vcommands.remove('bot_status')
        vcommands.remove('needs_info')
        vcommands.remove('!needs_info')
        vcommands.remove('shipit')
        vcommands.remove('needs_rebase')
        vcommands.remove('!needs_rebase')
        vcommands.remove('needs_revision')
        vcommands.remove('!needs_revision')

        iw = issuewrapper

        maintainers = []
        if meta['module_match']:
            maintainers += meta.get('module_match', {}).get('maintainers', [])
            maintainers += meta.get('module_match', {}).get('authors', [])
        maintainers += [x.login for x in iw.repo.assignees]
        maintainers = sorted(set(maintainers))

        meta['maintainer_commands'] = iw.history.get_commands(
            maintainers,
            vcommands,
            uselabels=False,
        )
        meta['submitter_commands'] = iw.history.get_commands(
            iw.submitter,
            vcommands,
            uselabels=False,
        )

        negative_commands = \
            [x for x in self.VALID_COMMANDS if x.startswith('!')]
        negative_commands = [x.replace('!', '') for x in negative_commands]
        for x in negative_commands:
            meta['maintainer_commands'] = self.negate_command(
                x,
                meta['maintainer_commands']
            )
            meta['submitter_commands'] = self.negate_command(
                x,
                meta['submitter_commands']
            )

        # resolved_by_pr is special
        if 'resolved_by_pr' in meta['maintainer_commands']:
            # find the comment
            mc = iw.history.get_user_comments(maintainers)
            mc = [x for x in mc if 'resolved_by_pr' in x]
            # extract the PR
            pr_number = extract_pr_number_from_comment(mc[-1])
            # was it merged?
            merged = self.is_pr_merged(pr_number, repo=iw.repo)
            meta['resolved_by_pr'] = {
                'number': pr_number,
                'merged': merged
            }

        return meta

    def negate_command(self, command, commands):
        # negate bot_broken  ... bot_broken vs. !bot_broken
        positive = command
        negative = '!' + command

        bb = [x for x in commands if positive in x]
        if bb:
            for x in bb:
                if x == negative:
                    commands.remove(positive)
                    commands.remove(negative)

        return commands

    def get_component_labels(self, valid_labels, files):
        labels = [x for x in valid_labels if x.startswith('c:')]

        clabels = []
        for cl in labels:
            l = cl.replace('c:', '', 1)
            al = os.path.join('lib/ansible', l)
            for f in files:
                if f.startswith(l) or f.startswith(al):
                    clabels.append(cl)

        #import epdb; epdb.st()
        return clabels

    def needs_bot_status(self, issuewrapper):
        iw = issuewrapper
        bs = False
        for ev in iw.history.history:
            if ev['event'] != 'commented':
                continue
            if 'bot_status' in ev['body']:
                if ev['actor'] not in BOTNAMES:
                    if ev['actor'] in self.ansible_members or \
                            ev['actor'] in self.module_indexer.all_maintainers:
                        bs = True
                        continue
            # <!--- boilerplate: bot_status --->
            if bs:
                if ev['actor'] in BOTNAMES:
                    if 'boilerplate: bot_status' in ev['body']:
                        bs = False
                        continue
        return {'needs_bot_status': bs}

    def waiting_on(self, issuewrapper, meta):
        iw = issuewrapper
        wo = None
        if meta['is_issue']:
            if meta['is_needs_info']:
                wo = iw.submitter
            elif 'needs_contributor' in meta['maintainer_commands']:
                wo = 'contributor'
            else:
                wo = 'maintainer'
        else:
            if meta['is_needs_info']:
                wo = iw.submitter
            elif meta['is_needs_revision']:
                wo = iw.submitter
            elif meta['is_needs_rebase']:
                wo = iw.submitter
            else:
                if meta['is_core']:
                    wo = 'ansible'
                else:
                    wo = 'maintainer'

        return {'waiting_on': wo}

    def get_label_commands(self, issuewrapper, meta):
        add_labels = []
        del_labels = []

        wl = [
            'needs_triage',
            'test',
            'module',
            'cloud',
            'aws',
            'azure',
            'digital_ocean',
            'docker',
            'gce',
            'openstack',
            'vmware',
            'networking'
        ]
        wl += [x for x in self.valid_labels if x.startswith('affects_')]
        wl += [x for x in self.valid_labels if x.startswith('c:')]

        iw = issuewrapper
        maintainers = self.ansible_members
        maintainers += self.module_indexer.all_maintainers
        maintainers = sorted(set(maintainers))
        for ev in iw.history.history:
            if ev['actor'] in maintainers and ev['event'] == 'commented':
                if '+label' in ev['body'] or '-label' in ev['body']:
                    for line in ev['body'].split('\n'):
                        if 'label' not in line:
                            continue
                        words = line.split()

                        label = words[1]
                        action = words[0]
                        if action == '+label':
                            add_labels.append(label)
                            if label in del_labels:
                                del_labels.remove(label)
                        elif action == '-label':
                            del_labels.append(label)
                            if label in add_labels:
                                add_labels.remove(label)

        fact = {
            'label_cmds': {
                'add': add_labels,
                'del': del_labels
            }
        }

        return fact
