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
#     ansibullbot.ansible/modules
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

import ansibullbot.constants as C

from pprint import pprint
from ansibullbot.triagers.defaulttriager import DefaultTriager
from ansibullbot.wrappers.ghapiwrapper import GithubWrapper
from ansibullbot.wrappers.issuewrapper import IssueWrapper

from ansibullbot.utils.extractors import extract_pr_number_from_comment
from ansibullbot.utils.iterators import RepoIssuesIterator
from ansibullbot.utils.moduletools import ModuleIndexer
from ansibullbot.utils.version_tools import AnsibleVersionIndexer
from ansibullbot.utils.file_tools import FileIndexer
from ansibullbot.utils.shippable_api import ShippableRuns
from ansibullbot.utils.systemtools import run_command
from ansibullbot.utils.receiver_client import post_to_receiver
from ansibullbot.utils.webscraper import GithubWebScraper
from ansibullbot.utils.gh_gql_client import GithubGraphQLClient

from ansibullbot.decorators.github import RateLimited
from ansibullbot.errors import LabelWafflingError

from ansibullbot.triagers.plugins.backports import get_backport_facts
from ansibullbot.triagers.plugins.ci_rebuild import get_rebuild_facts
from ansibullbot.triagers.plugins.ci_rebuild import get_rebuild_merge_facts
from ansibullbot.triagers.plugins.filament import get_filament_facts
from ansibullbot.triagers.plugins.label_commands import get_label_command_facts
from ansibullbot.triagers.plugins.needs_info import is_needsinfo
from ansibullbot.triagers.plugins.needs_info import needs_info_template_facts
from ansibullbot.triagers.plugins.needs_info import needs_info_timeout_facts
from ansibullbot.triagers.plugins.needs_revision import get_needs_revision_facts
from ansibullbot.triagers.plugins.needs_revision import get_shippable_run_facts
from ansibullbot.triagers.plugins.shipit import automergeable
from ansibullbot.triagers.plugins.shipit import get_shipit_facts
from ansibullbot.triagers.plugins.shipit import needs_community_review


#BOTNAMES = ['ansibot', 'gregdek', 'robynbergeron']
REPOS = [
    'ansible/ansible',
    'ansible/ansible-modules-core',
    'ansible/ansible-modules-extras'
]
MREPOS = [x for x in REPOS if 'modules' in x]
REPOMERGEDATE = datetime.datetime(2016, 12, 6, 0, 0, 0)
MREPO_CLOSE_WINDOW = 60

ERROR_CODES = {
    'shippable_failure': 1,
    'travis-ci': 2,
    'throttled': 3,
    'dirty': 4,
    'labeled': 5,
    'review': 6
}


class AnsibleTriage(DefaultTriager):

    BOTNAMES = ['ansibot', 'gregdek', 'robynbergeron']

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
        'rebuild': False
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
        'close_me'
    ]

    ISSUE_REQUIRED_FIELDS = [
        'issue type',
        'component name',
        'ansible version',
        'summary'
    ]

    PULLREQUEST_REQUIRED_FIELDS = [
        'issue type',
    ]

    FILEMAP = {}

    def __init__(self, args):

        self._ansible_members = []
        self._ansible_core_team = []

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
        logging.info('creating api connection')
        self.gh = self._connect()

        # wrap the connection
        logging.info('creating api wrapper')
        self.ghw = GithubWrapper(self.gh)

        # create the scraper for www data
        logging.info('creating webscraper')
        self.gws = GithubWebScraper(cachedir=self.cachedir)
        if C.DEFAULT_GITHUB_TOKEN:
            self.gqlc = GithubGraphQLClient(C.DEFAULT_GITHUB_TOKEN)
        else:
            self.gqlc = None

        # get valid labels
        logging.info('getting labels')
        self.valid_labels = self.get_valid_labels('ansible/ansible')

        # extend managed labels
        self.MANAGED_LABELS += self.ISSUE_TYPES.values()

        '''
        # get the maintainers
        logging.info('getting maintainers mapping')
        self.module_maintainers = self.get_maintainers_mapping()
        '''

        '''
        # get the filemap
        logging.info('getting filemap')
        self.FILEMAP = self.get_filemap()
        '''

        # set the indexers
        logging.info('creating version indexer')
        self.version_indexer = AnsibleVersionIndexer()
        logging.info('creating file indexer')
        self.file_indexer = FileIndexer()
        '''
        self.file_indexer = FileIndexer(
            checkoutdir=os.path.expanduser(
                '~/.ansibullbot/cache/ansible.files.checkout'
            ),
            #cmap=COMPONENTMAP_FILENAME,
        )
        '''

        logging.info('creating module indexer')
        self.module_indexer = ModuleIndexer()

        # instantiate shippable api
        logging.info('creating shippable wrapper')
        spath = os.path.expanduser('~/.ansibullbot/cache/shippable.runs')
        self.SR = ShippableRuns(cachedir=spath, writecache=True)

    @property
    def ansible_members(self):
        if not self._ansible_members:
            self._ansible_members = self.get_ansible_members()
        return [x for x in self._ansible_members]

    @property
    def ansible_core_team(self):
        if not self._ansible_core_team:
            self._ansible_core_team = self.get_ansible_core_team()
        return [x for x in self._ansible_core_team if x not in self.BOTNAMES]

    def get_rate_limit(self):
        return self.gh.get_rate_limit().raw_data

    def run(self):
        '''Primary execution method'''

        # update on each run to pull in new data
        logging.info('updating module indexer')
        self.module_indexer.update()

        # update shippable run data
        self.SR.update()

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
            # this is where the issue history cache goes
            hcache = os.path.join(self.cachedir, repopath)

            '''
            # scrape all summaries from www for later opchecking
            self.update_issue_summaries(repopath=repopath)
            '''

            for issue in item[1]['issues']:

                if issue is None:
                    if C.DEFAULT_BREAKPOINTS:
                        logging.error('breakpoint!')
                        import epdb; epdb.st()
                    continue

                iw = None
                self.issue = None
                self.meta = {}
                self.actions = {}
                number = issue.number
                self.number = number

                # keep track of known issues
                self.repos[repopath]['processed'].append(number)

                if issue.state == 'closed' and not self.args.ignore_state:
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

                    # create the wrapper on each loop iteration
                    iw = IssueWrapper(
                        github=self.ghw,
                        repo=repo,
                        issue=issue,
                        cachedir=self.cachedir,
                        file_indexer=self.file_indexer
                    )

                    if self.args.skip_no_update:
                        lmeta = self.load_meta(iw)

                        if lmeta:

                            now = datetime.datetime.now()
                            mod_repo = (iw.repo_full_name in MREPOS)
                            skip = False

                            if lmeta['updated_at'] == iw.updated_at.isoformat():
                                skip = True

                            if skip and not mod_repo:
                                if iw.is_pullrequest():
                                    ua = iw.pullrequest.updated_at.isoformat()
                                    if lmeta['updated_at'] < ua:
                                        skip = False

                            if skip and not mod_repo:

                                # re-check ansible/ansible after
                                # a window of time since the last check.
                                lt = lmeta['time']
                                lt = datetime.datetime.strptime(
                                    lt,
                                    '%Y-%m-%dT%H:%M:%S.%f'
                                )
                                delta = (now - lt)
                                delta = delta.days
                                if delta > C.DEFAULT_STALE_WINDOW:
                                    msg = '!skipping: %s' % delta
                                    msg += ' days since last check'
                                    logging.info(msg)
                                    skip = False

                                # if last process time is older than
                                # last completion time on shippable, we need
                                # to reprocess because the ci status has
                                # probabaly changed.
                                if skip and iw.is_pullrequest():
                                    ua = iw.pullrequest.updated_at.isoformat()
                                    mua = datetime.datetime.strptime(
                                        lmeta['updated_at'],
                                        '%Y-%m-%dT%H:%M:%S'
                                    )
                                    lsr = self.SR.get_last_completion(iw.number)
                                    if (lsr and lsr > mua) or \
                                            ua > lmeta['updated_at']:
                                        skip = False

                            # was this in the stale list?
                            if skip and not mod_repo:
                                if iw.number in self.repos[repopath]['stale']:
                                    skip = False

                            # do a final check on the timestamp in meta
                            if skip and not mod_repo:
                                # 2017-04-12T11:05:08.980077
                                mts = datetime.datetime.strptime(
                                    lmeta['time'],
                                    '%Y-%m-%dT%H:%M:%S.%f'
                                )
                                delta = (now - mts).days
                                if delta > C.DEFAULT_STALE_WINDOW:
                                    skip = False

                            if skip:
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
                    self.save_meta(iw, self.meta)

                    # DEBUG!
                    logging.info('url: %s' % self.issue.html_url)
                    logging.info('title: %s' % self.issue.title)
                    logging.info(
                        'component: %s' %
                        self.template_data.get('component_raw')
                    )
                    if self.meta['template_missing_sections']:
                        logging.info(
                            'missing sections: ' +
                            ', '.join(self.meta['template_missing_sections'])
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
                    if self.meta.get('mergeable_state') == 'unknown' or \
                            'needs_rebase' in self.actions['newlabel'] or \
                            'needs_rebase' in self.actions['unlabel'] or \
                            'needs_revision' in self.actions['newlabel'] or \
                            'needs_revision' in self.actions['unlabel']:
                        rn = self.issue.repo_full_name
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
                            pass

                    pprint(self.actions)

                    # do the actions
                    action_meta = self.apply_actions(self.issue, self.actions)
                    if action_meta['REDO']:
                        redo = True

                logging.info('finished triage for %s' % str(iw))

    def update_issue_summaries(self, repopath=None):

        if repopath:
            repopaths = [repopath]
        else:
            repopaths = [x for x in REPOS]

        for rp in repopaths:

            # skip repos based on args
            if self.skiprepo:
                if repopath in self.skiprepo:
                    continue
            if self.args.skip_module_repos and 'module' in repopath:
                continue
            if self.args.module_repos_only and 'module' not in repopath:
                continue

            if self.gqlc:
                if self.pr:
                    self.issue_summaries[repopath] = {}
                    for pr in self.pr.split(','):
                        node = self.gqlc.get_summary(rp, 'pullRequest', pr)
                        if node is not None:
                            self.issue_summaries[repopath][pr] = node
                else:
                    self.issue_summaries[repopath] = self.gqlc.get_issue_summaries(rp)
            else:
                # scrape all summaries rom www for later opchecking

                if self.pr:
                    logging.warning("'pr' switch is used by but Github authentication token isn't set: all pull-requests will be scrapped")

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
        if self.gqlc:
            import epdb; epdb.st()
        else:
            self.issue_summaries[rp][number] = \
                self.gws.get_single_issue_summary(rp, number, force=True)

    @RateLimited
    def update_issue_object(self, issue):
        issue.update()
        return issue

    def save_meta(self, issuewrapper, meta):
        # save the meta+actions
        dmeta = meta.copy()
        dmeta['submitter'] = issuewrapper.submitter
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
        rfn = issuewrapper.repo_full_name
        rfn_parts = rfn.split('/', 1)
        namespace = rfn_parts[0]
        reponame = rfn_parts[1]
        post_to_receiver(
            'metadata',
            {'user': namespace, 'repo': reponame, 'number': issuewrapper.number},
            dmeta
        )

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

    def create_actions(self):
        '''Parse facts and make actions from them'''

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
        if self.issue.is_pullrequest():
            if self.meta['mergeable_state'] == 'unknown':
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

        # triage requirements met ...
        if self.meta['maintainer_triaged']:
            if 'needs_triage' in self.actions['newlabel']:
                self.actions['newlabel'].remove('needs_triage')
            if 'needs_triage' in self.issue.labels:
                if 'needs_triage' not in self.actions['unlabel']:
                    self.actions['unlabel'].append('needs_triage')

        # owner PRs
        if self.issue.is_pullrequest():
            if self.meta['owner_pr']:
                if 'owner_pr' not in self.issue.labels:
                    self.actions['newlabel'].append('owner_pr')
            else:
                if 'owner_pr' in self.issue.labels:
                    self.actions['unlabel'].append('owner_pr')

        # REVIEWS
        for rtype in ['core_review', 'committer_review', 'community_review']:
            if self.meta[rtype]:
                if rtype not in self.issue.labels:
                    self.actions['newlabel'].append(rtype)
            else:
                if rtype in self.issue.labels:
                    self.actions['unlabel'].append(rtype)

        # WIPs
        if self.issue.is_pullrequest():
            if self.issue.wip:
                if 'WIP' not in self.issue.labels:
                    self.actions['newlabel'].append('WIP')
                if 'shipit' in self.issue.labels:
                    self.actions['unlabel'].append('shipit')
            else:
                if 'WIP' in self.issue.labels:
                    self.actions['unlabel'].append('WIP')

        # MERGE COMMITS
        if self.issue.is_pullrequest():
            if self.meta['merge_commits']:
                if not self.meta['has_merge_commit_notification']:
                    comment = self.render_boilerplate(
                        self.meta,
                        boilerplate='merge_commit_notify'
                    )
                    self.actions['comments'].append(comment)
                    if 'merge_commit' not in self.issue.labels:
                        self.actions['newlabel'].append('merge_commit')
            else:
                if 'merge_commit' in self.issue.labels:
                    self.actions['unlabel'].append('merge_commit')

        # @YOU IN COMMIT MSGS
        if self.issue.is_pullrequest():
            if self.meta['has_commit_mention']:
                if not self.meta['has_commit_mention_notification']:

                    comment = self.render_boilerplate(
                        self.meta,
                        boilerplate='commit_msg_mentions'
                    )
                    self.actions['comments'].append(comment)

        # SHIPIT+AUTOMERGE
        if self.issue.is_pullrequest():
            if self.meta['shipit']:

                if 'shipit' not in self.issue.labels:
                    self.actions['newlabel'].append('shipit')

                if automergeable(self.meta, self.issue):
                    logging.info('auto-merge tests passed')
                    if 'automerge' not in self.issue.labels:
                        self.actions['newlabel'].append('automerge')
                    self.actions['merge'] = True
                else:
                    if 'automerge' in self.issue.labels:
                        self.actions['unlabel'].append('automerge')

            else:

                # not shipit and not automerge ...
                if 'shipit' in self.issue.labels:
                    self.actions['unlabel'].append('shipit')
                if 'automerge' in self.issue.labels:
                    self.actions['unlabel'].append('automerge')

        # NAMESPACE MAINTAINER NOTIFY
        if self.issue.is_pullrequest():
            if needs_community_review(self.meta, self.issue):

                comment = self.render_boilerplate(
                    self.meta,
                    boilerplate='community_shipit_notify'
                )

                if comment and comment not in self.actions['comments']:
                    self.actions['comments'].append(comment)

        # NEEDS REVISION
        if self.issue.is_pullrequest():
            if not self.issue.wip:
                if self.meta['is_needs_revision'] or self.meta['is_bad_pr']:
                    if 'needs_revision' not in self.issue.labels:
                        self.actions['newlabel'].append('needs_revision')
                else:
                    if 'needs_revision' in self.issue.labels:
                        self.actions['unlabel'].append('needs_revision')

        # NEEDS REBASE
        if self.issue.is_pullrequest():
            if self.meta['is_needs_rebase'] or self.meta['is_bad_pr']:
                if 'needs_rebase' not in self.issue.labels:
                    self.actions['newlabel'].append('needs_rebase')
            else:
                if 'needs_rebase' in self.issue.labels:
                    self.actions['unlabel'].append('needs_rebase')

        # travis-ci.org ...
        if self.issue.is_pullrequest():
            if self.meta['has_travis'] and \
                    not self.meta['has_travis_notification']:
                tvars = {'submitter': self.issue.submitter}
                comment = self.render_boilerplate(
                    tvars,
                    boilerplate='travis_notify'
                )
                if comment not in self.actions['comments']:
                    self.actions['comments'].append(comment)

        # shippable failures shippable_test_result
        if self.issue.is_pullrequest():
            if self.meta['ci_state'] == 'failure' and \
                    self.meta['needs_testresult_notification']:
                tvars = {
                    'submitter': self.issue.submitter,
                    'data': self.meta['shippable_test_results']
                }

                try:
                    comment = self.render_boilerplate(
                        tvars,
                        boilerplate='shippable_test_result'
                    )
                except Exception as e:
                    logging.debug(e)
                    if C.DEFAULT_BREAKPOINTS:
                        logging.debug('breakpoint!')
                        import epdb; epdb.st()
                    else:
                        raise Exception(str(e))

                # https://github.com/ansible/ansibullbot/issues/423
                if len(comment) < 65536:
                    if comment not in self.actions['comments']:
                        self.actions['comments'].append(comment)

        # https://github.com/ansible/ansibullbot/issues/293
        if self.issue.is_pullrequest():
            if not self.meta['has_shippable'] and not self.meta['has_travis']:
                if 'needs_ci' not in self.issue.labels:
                    self.actions['newlabel'].append('needs_ci')
            else:
                if 'needs_ci' in self.issue.labels:
                    self.actions['unlabel'].append('needs_ci')

        # MODULE CATEGORY LABELS
        if self.meta['is_new_module'] or self.meta['is_module']:
            # add topic labels
            for t in ['topic', 'subtopic']:
                label = self.meta['module_match'].get(t)
                if label in self.MODULE_NAMESPACE_LABELS:
                    label = self.MODULE_NAMESPACE_LABELS[label]

                if label and label in self.valid_labels and \
                        label not in self.issue.labels and \
                        not self.issue.history.was_unlabeled(label):
                    self.actions['newlabel'].append(label)

            # add namespace labels
            namespace = self.meta['module_match'].get('namespace')
            if namespace in self.MODULE_NAMESPACE_LABELS:
                label = self.MODULE_NAMESPACE_LABELS[namespace]
                if label not in self.issue.labels and \
                        not self.issue.history.was_unlabeled(label):
                    self.actions['newlabel'].append(label)

        # NEW MODULE
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
                    bots=self.BOTNAMES
                ):
                    self.actions['newlabel'].append('module')
        else:
            if 'module' in self.issue.labels:
                # don't remove manually added label
                if not self.issue.history.was_labeled(
                    'module',
                    bots=self.BOTNAMES
                ):
                    self.actions['unlabel'].append('module')

        # component labels
        if self.meta['component_labels'] and not self.meta['merge_commits']:

            # only add these labels to pullrequest or un-triaged issues
            if self.issue.is_pullrequest() or \
                    (self.issue.is_issue() and
                     (not self.issue.labels or
                      'needs_triage' in self.issue.labels)):

                # only add these if no c: labels have ever been changed by human
                clabels = self.issue.history.get_changed_labels(
                    prefix='c:',
                    bots=self.BOTNAMES
                )

                if not clabels:
                    for cl in self.meta['component_labels']:
                        ul = self.issue.history.was_unlabeled(
                            cl,
                            bots=self.BOTNAMES
                        )
                        if not ul and \
                                cl not in self.issue.labels and \
                                cl not in self.actions['newlabel']:
                            self.actions['newlabel'].append(cl)

        if self.meta['ansible_label_version']:
            vlabels = [x for x in self.issue.labels if x.startswith('affects_')]
            if not vlabels:
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
            fmap_labels = self.file_indexer.get_filemap_labels_for_files(self.issue.files)
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
                if not self.issue.history.was_unlabeled('python3'):
                    self.actions['newlabel'].append('python3')

        # needs info?
        if self.meta['is_needs_info']:
            if 'needs_info' not in self.issue.labels:
                self.actions['newlabel'].append('needs_info')

            # template data warning
            if self.meta['template_warning_required']:
                tvars = {
                    'submitter': self.issue.submitter,
                    'itype': self.issue.github_type,
                    'missing_sections': self.meta['template_missing_sections']
                }

                comment = self.render_boilerplate(
                    tvars,
                    boilerplate='issue_missing_data'
                )

                self.actions['comments'].append(comment)

            if self.meta['template_missing_sections']:
                if 'needs_template' not in self.issue.labels:
                    self.actions['newlabel'].append('needs_template')

        elif 'needs_info' in self.issue.labels:
            self.actions['unlabel'].append('needs_info')

        # clear the needs_template label
        if not self.meta['is_needs_info'] or \
                not self.meta['template_missing_sections']:
            if 'needs_template' in self.issue.labels:
                self.actions['unlabel'].append('needs_template')

        # needs_info warn/close?
        if self.meta['is_needs_info'] and self.meta['needs_info_action']:

            if self.meta['needs_info_action'] == 'close':
                self.actions['close'] = True

            tvars = {
                'submitter': self.issue.submitter,
                'action': self.meta['needs_info_action'],
                'itype': self.issue.github_type
            }

            comment = self.render_boilerplate(
                tvars,
                boilerplate='needs_info_base'
            )

            self.actions['comments'].append(comment)

        # assignees?
        '''
        # https://github.com/ansible/ansibullbot/issues/500
        if self.meta['to_assign']:
            for user in self.meta['to_assign']:
                # don't re-assign people
                if not self.issue.history.was_unassigned(user):
                    self.actions['assign'].append(user)
        '''

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
        if 'close_me' in self.meta['maintainer_commands']:
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

        if self.issue.is_pullrequest():

            # https://github.com/ansible/ansibullbot/issues/312
            # https://github.com/ansible/ansibullbot/issues/418
            if self.meta['ci_verified']:
                if 'ci_verified' not in self.issue.labels:
                    self.actions['newlabel'].append('ci_verified')
            else:
                if 'ci_verified' in self.issue.labels:
                    self.actions['unlabel'].append('ci_verified')

        # https://github.com/ansible/ansibullbot/issues/367
        if self.meta['is_backport']:
            if 'backport' not in self.issue.labels:
                self.actions['newlabel'].append('backport')

        # https://github.com/ansible/ansibullbot/issues/29
        if self.meta['is_module']:
            if self.meta['module_match']['deprecated']:
                if 'deprecated' not in self.issue.labels:
                    self.actions['newlabel'].append('deprecated')

        # https://github.com/ansible/ansibullbot/issues/406
        if self.issue.is_pullrequest():
            if not self.meta['has_shippable_yaml']:

                # no_shippable_yaml
                if not self.meta['has_shippable_yaml_notification']:
                    tvars = {'submitter': self.issue.submitter}
                    comment = self.render_boilerplate(
                        tvars,
                        boilerplate='no_shippable_yaml'
                    )
                    self.actions['comments'].append(comment)

                if 'needs_shippable' not in self.issue.labels:
                    self.actions['newlabel'].append('needs_shippable')

            else:
                if 'needs_shippable' in self.issue.labels:
                    self.actions['unlabel'].append('needs_shippable')

        # label PRs with missing repos
        if self.issue.is_pullrequest():
            if not self.meta['has_remote_repo']:
                if 'needs_repo' not in self.issue.labels:
                    self.actions['newlabel'].append('needs_repo')
            else:
                if 'needs_repo' in self.issue.labels:
                    self.actions['unlabel'].append('needs_repo')

        # https://github.com/ansible/ansibullbot/issues/458
        if self.issue.is_pullrequest():
            if self.meta['ci_stale']:
                if 'stale_ci' not in self.issue.labels:
                    self.actions['newlabel'].append('stale_ci')
            else:
                if 'stale_ci' in self.issue.labels:
                    self.actions['unlabel'].append('stale_ci')

        # https://github.com/ansible/ansibullbot/issues/589
        if self.meta['module_match'] and not self.meta['is_new_module']:
            if not self.meta['module_match']['maintainers']:
                # 'ansible' is cleared from the primary key, so we need
                # to check the original copy before deciding this isn't
                # being maintained.
                if not self.meta['module_match'].get('_maintainers'):
                    if 'needs_maintainer' not in self.issue.labels:
                        self.actions['newlabel'].append('needs_maintainer')
            else:
                if 'needs_maintainer' in self.issue.labels:
                    self.actions['unlabel'].append('needs_maintainer')

        # https://github.com/ansible/ansibullbot/issues/608
        cs_label = 'support:core'
        if self.meta['module_match']:
            mm = self.meta['module_match']
            sb = mm.get('metadata', {}).get('supported_by')
            if sb:
                cs_label = 'support:%s' % sb
        if cs_label not in self.issue.labels:
            self.actions['newlabel'].append(cs_label)

        if not self.meta['stale_reviews']:
            if 'stale_review' in self.issue.labels:
                self.actions['unlabel'].append('stale_review')
        else:
            if 'stale_review' not in self.issue.labels:
                self.actions['newlabel'].append('stale_review')

        # https://github.com/ansible/ansibullbot/issues/302
        if self.issue.is_pullrequest():
            if self.meta['needs_multiple_new_modules_notification']:
                tvars = {
                    'submitter': self.issue.submitter
                }
                comment = self.render_boilerplate(
                    tvars, boilerplate='multiple_module_notify'
                )
                if comment not in self.actions['comments']:
                    self.actions['comments'].append(comment)

        # https://github.com/ansible/ansible/pull/26921
        if self.meta['is_filament']:

            # no notifications on these
            if self.actions['comments']:
                remove = []
                for comment in self.actions['comments']:
                    if '@' in comment:
                        remove.append(comment)
                if remove:
                    for comment in remove:
                        self.actions['comments'].remove(comment)

            if'filament' not in self.issue.labels:
                self.actions['newlabel'].append('filament')
            if self.issue.age.days >= 5:
                self.actions['close'] = True

        # https://github.com/ansible/ansibullbot/pull/664
        if self.meta['needs_rebuild']:
            self.actions['rebuild'] = True
            if 'stale_ci' in self.actions['newlabel']:
                self.actions['newlabel'].remove('stale_ci')
            if 'stale_ci' in self.issue.labels:
                self.actions['unlabel'].append('stale_ci')

        # https://github.com/ansible/ansibullbot/issues/640
        if not self.meta['needs_rebuild'] and self.meta['admin_merge']:
            self.actions['merge'] = True

        self.actions['newlabel'] = sorted(set(self.actions['newlabel']))
        self.actions['unlabel'] = sorted(set(self.actions['unlabel']))

        # check for waffling
        labels = sorted(set(self.actions['newlabel'] + self.actions['unlabel']))
        for label in labels:
            if self.issue.history.label_is_waffling(label):
                if label in self.actions['newlabel'] or label in self.actions['unlabel']:
                    msg = '"{}" label is waffling on {}'.format(label, self.issue.html_url)
                    logging.error(msg)
                    if C.DEFAULT_BREAKPOINTS:
                        import epdb; epdb.st()
                    raise LabelWafflingError(msg)

    def check_safe_match(self):

        if hasattr(self, 'safe_force_script'):

            if self.safe_force_script:

                with open(self.safe_force_script, 'rb') as f:
                    fdata = f.read()
                res = eval(fdata)
                if res:
                    self.force = True
                else:
                    self.force = False
                return self.force

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
        action_meta = self.apply_actions(self.issue, self.actions)
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
        action_meta = self.apply_actions(self.issue, self.actions)
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
                            github=self.ghw,
                            repo=thisrepo,
                            issue=issue,
                            cachedir=cachedir
                    )
                    iw.history
                    rl = thisrepo.get_rate_limit()
                    pprint(rl)

    def get_stale_numbers(self, reponame):
        # https://github.com/ansible/ansibullbot/issues/458
        # def load_meta(self, issuewrapper):
        # cachedir = /home/jtanner/.ansibullbot/cache
        # idir = /home/jtanner/.ansibullbot/cache/ansible/ansible/issues/{NUM}

        stale = []
        reasons = {}

        for number,summary in self.issue_summaries[reponame].items():

            if number in stale:
                continue

            if summary['state'] == 'closed':
                continue

            number = int(number)
            mfile = os.path.join(
                self.cachedir_base,
                reponame,
                'issues',
                str(number),
                'meta.json'
            )

            if not os.path.isfile(mfile):
                reasons[number] = '%s missing' % mfile
                stale.append(number)
                continue

            with open(mfile, 'rb') as f:
                meta = json.load(f)

            ts = meta['time']
            ts = datetime.datetime.strptime(ts, '%Y-%m-%dT%H:%M:%S.%f')
            now = datetime.datetime.now()
            delta = (now - ts).days

            if delta > C.DEFAULT_STALE_WINDOW:
                reasons[number] = '%s delta' % delta
                stale.append(number)

        stale = sorted(set([int(x) for x in stale]))
        if len(stale) <= 10 and len(stale) > 0:
            logging.info('stale: %s' % ','.join([str(x) for x in stale]))

        return stale

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
            self._collect_repo(repo)

        logging.info('finished collecting issues')

    @RateLimited
    def _collect_repo(self, repo):
        '''Collect issues for an individual repo'''

        logging.info('getting repo obj for %s' % repo)
        if repo not in self.repos:
            self.repos[repo] = {
                'repo': self.ghw.get_repo(repo, verbose=False),
                'issues': [],
                'processed': [],
                'since': None,
                'stale': [],
                'loopcount': 0
            }
        else:
            # force a clean repo object to limit caching problems
            self.repos[repo]['repo'] = \
                self.ghw.get_repo(repo, verbose=False)
            # clear the issues
            self.repos[repo]['issues'] = {}
            # increment the loopcount
            self.repos[repo]['loopcount'] += 1

        # def __init__(self, repo, numbers, issuecache={})
        issuecache = {}

        logging.info('getting issue objs for %s' % repo)
        self.update_issue_summaries(repopath=repo)

        issuecache = {}
        numbers = self.issue_summaries[repo].keys()
        numbers = [int(x) for x in numbers]
        logging.info('%s known numbers' % len(numbers))

        if self.args.pr:
            if os.path.isfile(self.args.pr) and \
                    os.access(self.args.pr, os.X_OK):
                # allow for scripts when trying to target spec issues
                logging.info('executing %s' % self.args.pr)
                (rc, so, se) = run_command(self.args.pr)
                numbers = json.loads(so)
                numbers = [int(x) for x in numbers]
                logging.info(
                    '%s numbers after running script' % len(numbers)
                )
            else:
                # the issue id can be a list separated by commas
                if ',' in self.pr:
                    numbers = [int(x) for x in self.pr.split(',')]
                else:
                    numbers = [int(self.pr)]
            logging.info('%s numbers from --id/--pr' % len(numbers))

        if self.args.daemonize:

            if not self.repos[repo]['since']:
                ts = [
                    x[1]['updated_at'] for x in
                    self.issue_summaries[repo].items()
                    if x[1]['updated_at']
                ]
                ts += [
                    x[1]['created_at'] for x in
                    self.issue_summaries[repo].items()
                    if x[1]['created_at']
                ]
                ts = sorted(set(ts))
                self.repos[repo]['since'] = ts[-1]
            else:
                since = datetime.datetime.strptime(
                    self.repos[repo]['since'],
                    '%Y-%m-%dT%H:%M:%SZ'
                )
                api_since = self.repos[repo]['repo'].get_issues(
                    since=since
                )

                numbers = []
                for x in api_since:
                    number = x.number
                    numbers.append(number)
                    issuecache[number] = x

                numbers = sorted(set(numbers))
                logging.info(
                    '%s numbers after [api] since == %s' %
                    (len(numbers), since)
                )

                for k,v in self.issue_summaries[repo].items():
                    if v['created_at'] > self.repos[repo]['since']:
                        numbers.append(k)

                numbers = sorted(set(numbers))
                logging.info(
                    '%s numbers after [www] since == %s' %
                    (len(numbers), since)
                )

        if self.args.start_at and self.repos[repo]['loopcount'] == 0:
            numbers = [x for x in numbers if x <= self.args.start_at]
            logging.info('%s numbers after start-at' % len(numbers))

        # Get stale numbers if not targeting
        if repo not in MREPOS:
            if self.args.daemonize and self.repos[repo]['loopcount'] > 0:
                stale = self.get_stale_numbers(repo)
                self.repos[repo]['stale'] = [int(x) for x in stale]
                numbers += [int(x) for x in stale]
                numbers = sorted(set(numbers))
                logging.info('%s numbers after stale check' % len(numbers))

        ################################################################
        # PRE-FILTERING TO PREVENT EXCESSIVE API CALLS
        ################################################################

        # filter just the open numbers
        if not self.args.only_closed and not self.args.ignore_state:
            numbers = [
                x for x in numbers
                if str(x) in self.issue_summaries[repo] and
                self.issue_summaries[repo][str(x)]['state'] == 'open'
            ]
            logging.info('%s numbers after checking state' % len(numbers))

        # filter by type
        if self.args.only_issues:
            numbers = [
                x for x in numbers
                if self.issue_summaries[repo][str(x)]['type'].lower() == 'issue'
            ]
            logging.info('%s numbers after checking type' % len(numbers))
        elif self.args.only_prs:
            numbers = [
                x for x in numbers
                if self.issue_summaries[repo][str(x)]['type'].lower() ==
                'pullrequest'
            ]
            logging.info('%s numbers after checking type' % len(numbers))

        # Use iterator to avoid requesting all issues upfront
        numbers = sorted([int(x) for x in numbers])
        numbers = [x for x in reversed(numbers)]
        self.repos[repo]['issues'] = RepoIssuesIterator(
            self.repos[repo]['repo'],
            numbers,
            issuecache=issuecache
        )

        logging.info('getting repo objs for %s complete' % repo)

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

        self.meta['submitter'] = iw.submitter

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

        # https://github.com/ansible/ansible/issues/21207
        if not self.meta['ansible_version']:
            # fallback to version by date
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
        self.meta['is_new_directory'] = False
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

                # creating a new dir?
                if self.file_indexer.isnewdir(os.path.dirname(f)):
                    self.meta['is_new_directory'] = True

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

                    # keep track of namespace maintainers for new mods too
                    ns = match['namespace']
                    match['namespace_maintainers'] = \
                        self.module_indexer.get_maintainers_for_namespace(ns)

                    # these are "community" supported from the beginning?
                    match['metadata']['supported_by'] = 'community'

                    self.meta['module_match'] = copy.deepcopy(match)
                    self.meta['component'] = match['name']

                elif f.endswith('.md'):
                    # network/avi/README.md
                    continue
                else:
                    # FIXME - what do with these files?
                    logging.warning('unhandled filepath for matching: %s' % f)

        # get labels for files ...
        if not iw.is_pullrequest():
            self.meta['is_issue'] = True
            self.meta['is_pullrequest'] = False
            self.meta['component_labels'] = []

            if not self.meta['is_module'] and \
                    self.args.issue_component_matching:
                components = self.file_indexer.find_component_match(
                    iw.title,
                    iw.body,
                    iw.template_data
                )
                self.meta['guessed_components'] = components
                if components:
                    comp_labels = self.file_indexer.get_component_labels(
                        self.valid_labels,
                        components
                    )
                    self.meta['component_labels'] = comp_labels
                else:
                    self.meta['component_labels'] = []

        else:
            self.meta['is_issue'] = False
            self.meta['is_pullrequest'] = True
            self.meta['component_labels'] = \
                self.file_indexer.get_component_labels(
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

        # everything else is "core"
        if not self.meta['is_module']:
            self.meta['is_core'] = True

        # python3 ?
        self.meta['is_py3'] = self.is_python3()

        # backports
        self.meta.update(get_backport_facts(iw, self.meta))

        # shipit?
        self.meta.update(
            get_needs_revision_facts(
                self,
                iw,
                self.meta,
                #shippable=self.SR
            )
        )
        self.meta.update(self.get_notification_facts(iw, self.meta))

        # ci_verified and test results
        self.meta.update(
            get_shippable_run_facts(iw, self.meta, shippable=self.SR)
        )

        # needsinfo?
        #self.meta['is_needs_info'] = self.is_needsinfo()
        self.meta['is_needs_info'] = is_needsinfo(self)
        self.meta.update(self.process_comment_commands(iw, self.meta))
        self.meta.update(needs_info_template_facts(iw, self.meta))
        #self.meta.update(self.needs_info_timeout_facts(iw, self.meta))
        self.meta.update(needs_info_timeout_facts(iw, self.meta))

        # shipit?
        self.meta.update(
            get_shipit_facts(
                iw, self.meta, self.module_indexer,
                core_team=self.ansible_core_team, botnames=self.BOTNAMES
            )
        )
        self.meta.update(self.get_review_facts(iw, self.meta))

        # bot_status needed?
        self.meta.update(self.needs_bot_status(iw))

        # who is this waiting on?
        self.meta.update(self.waiting_on(iw, self.meta))

        # community label manipulation
        #self.meta.update(self.get_label_commands(iw, self.meta))
        self.meta.update(
            get_label_command_facts(
                iw,
                self.meta,
                self.module_indexer,
                core_team=self.ansible_core_team,
                valid_labels=self.valid_labels
            )
        )

        # triage from everyone else? ...
        self.meta.update(self.get_triage_facts(iw, self.meta))

        # filament
        self.meta.update(get_filament_facts(iw, self.meta))

        # ci rebuilds
        self.meta.update(get_rebuild_facts(iw, self.meta, self.SR))

        # ci rebuild + merge
        self.meta.update(
            get_rebuild_merge_facts(
                iw,
                self.meta,
                self.ansible_core_team
            )
        )

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
            if C.DEFAULT_BREAKPOINTS:
                logging.error('breakpoint!')
                import epdb; epdb.st()
            else:
                raise Exception('unknown url type for migrated issue')

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
            github=self.ghw,
            repo=mrepo,
            issue=missue,
            cachedir=os.path.join(self.cachedir_base, repo_path)
        )
        return mw

    def is_python3(self):
        '''Is the issue related to python3?'''
        ispy3 = False
        py3strings = ['python 3', 'python3', 'py3', 'py 3']

        for py3str in py3strings:

            if py3str in self.issue.title.lower():
                ispy3 = True
                break

            for k,v in self.template_data.iteritems():
                if not v:
                    continue
                if py3str in v.lower():
                    ispy3 = True
                    break

            if ispy3:
                break

        if ispy3:
            for comment in self.issue.comments:
                if '!python3' in comment.body:
                    logging.info('!python3 override in comments')
                    ispy3 = False
                    break

        return ispy3

    """
    def missing_fields(self):
        # start with missing template data
        if self.issue.is_issue():
            mf = self.ISSUE_REQUIRED_FIELDS
        else:
            mf = self.PULLREQUEST_REQUIRED_FIELDS

        if not self.issue.history:
            self.issue.history = self.get_history(
                self.issue,
                cachedir=self.cachedir_base,
                usecache=True
            )

        return mf
    """

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
        elif supported_by == 'curated':
            rfacts['committer_review'] = True
        else:
            if C.DEFAULT_BREAKPOINTS:
                logging.error('breakpoint!')
                import epdb; epdb.st()
            else:
                raise Exception('unknown supported_by type')

        return rfacts

    def get_notification_facts(self, issuewrapper, meta):
        '''Build facts about mentions/pings'''
        iw = issuewrapper
        """
        if not iw.history:
            import epdb; epdb.st()
            iw.history = self.get_history(
                iw,
                cachedir=self.cachedir_base,
                usecache=True
            )
        """

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
            (fnotify, fassign) = self.file_indexer.get_filemap_users_for_files(iw.files)
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
            botnames=self.BOTNAMES
        )
        meta['submitter_commands'] = iw.history.get_commands(
            iw.submitter,
            vcommands,
            uselabels=False,
            botnames=self.BOTNAMES
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
                    if positive in commands:
                        commands.remove(positive)
                    if negative in commands:
                        commands.remove(negative)

        return commands

    '''
    def get_component_labels(self, valid_labels, files):
        labels = [x for x in valid_labels if x.startswith('c:')]

        clabels = []
        for cl in labels:
            l = cl.replace('c:', '', 1)
            al = os.path.join('ansibullbot.ansible', l)
            for f in files:
                if f.startswith(l) or f.startswith(al):
                    clabels.append(cl)

        return clabels
    '''

    def needs_bot_status(self, issuewrapper):
        iw = issuewrapper
        bs = False
        for ev in iw.history.history:
            if ev['event'] != 'commented':
                continue
            if 'bot_status' in ev['body']:
                if ev['actor'] not in self.BOTNAMES:
                    if ev['actor'] in self.ansible_core_team or \
                            ev['actor'] == iw.submitter or \
                            ev['actor'] in self.module_indexer.all_maintainers:
                        bs = True
                        continue
            # <!--- boilerplate: bot_status --->
            if bs:
                if ev['actor'] in self.BOTNAMES:
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

    def get_triage_facts(self, issuewrapper, meta):
        tfacts = {
            'maintainer_triaged': False
        }

        if not meta['module_match']:
            return tfacts
        if not meta['module_match'].get('metadata'):
            return tfacts
        if not meta['module_match']['metadata'].get('supported_by'):
            return tfacts
        if not meta['module_match'].get('maintainers'):
            return tfacts

        iw = issuewrapper
        maintainers = [x for x in meta['module_match']['maintainers']]
        maintainers += [x for x in self.ansible_core_team]
        maintainers = [x for x in maintainers if x != iw.submitter]
        maintainers = sorted(set(maintainers))
        if iw.history.has_commented(maintainers):
            tfacts['maintainer_triaged'] = True
        elif iw.history.has_labeled(maintainers):
            tfacts['maintainer_triaged'] = True
        elif iw.history.has_unlabeled(maintainers):
            tfacts['maintainer_triaged'] = True
        elif iw.is_pullrequest() and iw.history.has_reviewed(maintainers):
            tfacts['maintainer_triaged'] = True

        return tfacts
