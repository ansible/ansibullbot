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

import datetime
import json
import logging
import os

from copy import deepcopy
from distutils.version import LooseVersion
from pprint import pprint

import requests

from ansibullbot._text_compat import to_bytes, to_text

import ansibullbot.constants as C

from ansibullbot.triagers.defaulttriager import DefaultActions, DefaultTriager
from ansibullbot.wrappers.ghapiwrapper import GithubWrapper
from ansibullbot.wrappers.issuewrapper import IssueWrapper

from ansibullbot.parsers.botmetadata import BotMetadataParser

from ansibullbot.utils.component_tools import AnsibleComponentMatcher
from ansibullbot.utils.extractors import extract_pr_number_from_comment
from ansibullbot.utils.git_tools import GitRepoWrapper
from ansibullbot.utils.iterators import RepoIssuesIterator
from ansibullbot.utils.moduletools import ModuleIndexer
from ansibullbot.utils.timetools import strip_time_safely
from ansibullbot.utils.version_tools import AnsibleVersionIndexer
from ansibullbot.utils.systemtools import run_command
from ansibullbot.utils.receiver_client import post_to_receiver
from ansibullbot.utils.gh_gql_client import GithubGraphQLClient

from ansibullbot.decorators.github import RateLimited
from ansibullbot.errors import LabelWafflingError, NoCIError

from ansibullbot.triagers.plugins.backports import get_backport_facts
from ansibullbot.triagers.plugins.botstatus import get_bot_status_facts
from ansibullbot.triagers.plugins.ci_rebuild import get_ci_facts
from ansibullbot.triagers.plugins.ci_rebuild import get_rebuild_facts
from ansibullbot.triagers.plugins.ci_rebuild import get_rebuild_command_facts
from ansibullbot.triagers.plugins.ci_rebuild import get_rebuild_merge_facts
from ansibullbot.triagers.plugins.community_workgroups import get_community_workgroup_facts
from ansibullbot.triagers.plugins.component_matching import get_component_match_facts
from ansibullbot.triagers.plugins.collection_facts import get_collection_facts
from ansibullbot.triagers.plugins.cross_references import get_cross_reference_facts
from ansibullbot.triagers.plugins.filament import get_filament_facts
from ansibullbot.triagers.plugins.label_commands import get_label_command_facts
from ansibullbot.triagers.plugins.label_commands import get_waffling_overrides
from ansibullbot.triagers.plugins.needs_contributor import get_needs_contributor_facts
from ansibullbot.triagers.plugins.needs_info import is_needsinfo
from ansibullbot.triagers.plugins.needs_info import needs_info_template_facts
from ansibullbot.triagers.plugins.needs_info import needs_info_timeout_facts
from ansibullbot.triagers.plugins.needs_revision import get_needs_revision_facts
from ansibullbot.triagers.plugins.needs_revision import get_ci_run_facts
from ansibullbot.triagers.plugins.contributors import get_contributor_facts
from ansibullbot.triagers.plugins.notifications import get_notification_facts
from ansibullbot.triagers.plugins.performance import get_performance_facts
from ansibullbot.triagers.plugins.py3 import get_python3_facts
from ansibullbot.triagers.plugins.shipit import get_automerge_facts
from ansibullbot.triagers.plugins.shipit import get_review_facts
from ansibullbot.triagers.plugins.shipit import get_shipit_facts
from ansibullbot.triagers.plugins.shipit import get_submitter_facts
from ansibullbot.triagers.plugins.shipit import needs_community_review
from ansibullbot.triagers.plugins.small_patch import get_small_patch_facts
from ansibullbot.triagers.plugins.spam import get_spam_facts
from ansibullbot.triagers.plugins.test_support_plugins import get_test_support_plugins_facts
from ansibullbot.triagers.plugins.traceback import get_traceback_facts
from ansibullbot.triagers.plugins.deprecation import get_deprecation_facts
from ansibullbot.triagers.plugins.docs_info import get_docs_facts


VALID_CI_PROVIDERS = frozenset(('azp',))


# NOTE if we want to support more repos for the ansible triager
# using --repos and/or --skiprepo all occurrences of hardcoded
# "ansible/ansible" need to be fixed
REPOS = [
    'ansible/ansible',
]


def get_version_major_minor(vstring):
    '''Return an X.Y version'''
    lver = LooseVersion(vstring)
    rval = '.'.join([to_text(x) for x in lver.version[0:2]])
    return rval


class MetaDict(dict):
    def __setitem__(self, key, val):
        # https://github.com/ansible/ansible/issues/68640
        dict.__setitem__(self, key, val)
    def update(self, *args, **kwargs):
        for k, v in dict(*args, **kwargs).items():
            self[k] = v
            self.__setitem__(k, v)


class AnsibleActions(DefaultActions):
    def __init__(self):
        super().__init__()
        self.close_migrated = False
        self.rebuild = False
        self.rebuild_failed = False
        self.cancel_ci = False
        self.cancel_ci_branch = False


class AnsibleTriage(DefaultTriager):

    BOTNAMES = C.DEFAULT_BOT_NAMES

    CLOSING_LABELS = ['bot_closed']

    ISSUE_TYPES = {
        'bug report': 'bug',
        'bugfix pull request': 'bug',
        'feature idea': 'feature',
        'feature pull request': 'feature',
        'documentation report': 'docs',
        'docs pull request': 'docs',
        'new module pull request': 'new_plugin'
    }

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

    def __init__(self, args=None, update_checkouts=True):

        super().__init__()

        self._args = args

        parser = self.create_parser()
        args = parser.parse_args(self._args)
        self.args = args

        for x in vars(args):
            val = getattr(args, x)
            setattr(self, x, val)

        ci_provider = self.ci

        if ci_provider == 'azp':
            from ansibullbot.ci.azp import AzurePipelinesCI as ci_class
        else:
            raise ValueError(
                'Unknown CI provider specified in the config file: %s. Valid CI providers: %s' %
                (C.DEFAULT_CI_PROVIDER, ', '.join(VALID_CI_PROVIDERS))
            )

        self.ci = None
        self.ci_class = ci_class

        self.github_url = C.DEFAULT_GITHUB_URL
        self.github_user = C.DEFAULT_GITHUB_USERNAME
        self.github_pass = C.DEFAULT_GITHUB_PASSWORD
        self.github_token = C.DEFAULT_GITHUB_TOKEN

        # where to store junk
        self.cachedir_base = os.path.expanduser(self.cachedir_base)

        self.set_logger()
        logging.info('starting bot')

        # connect to github
        logging.info('creating api connection')
        self.gh = self._connect()

        # wrap the connection
        logging.info('creating api wrapper')
        self.ghw = GithubWrapper(self.gh, token=self.github_token, cachedir=self.cachedir_base)

        # get valid labels
        logging.info('getting labels')
        self.valid_labels = self.get_valid_labels("ansible/ansible")

        self._ansible_members = []
        self._ansible_core_team = None
        self.botmeta = {}
        self.automerge_on = False

        self.cachedir_base = os.path.expanduser(self.cachedir_base)

        # repo objects
        self.repos = {}

        # scraped summaries for all issues
        self.issue_summaries = {}

        logging.info('creating graphql client')
        self.gqlc = GithubGraphQLClient(
            C.DEFAULT_GITHUB_TOKEN,
            server=C.DEFAULT_GITHUB_URL
        )

        # clone ansible/ansible
        logging.info('creating gitrepowrapper')
        repo = 'https://github.com/ansible/ansible'
        self.gitrepo = GitRepoWrapper(cachedir=self.cachedir_base, repo=repo, commit=self.ansible_commit, rebase=update_checkouts)

        # load botmeta ... once!
        logging.info('ansible triager loading botmeta')
        self.load_botmeta()

        # set the indexers
        logging.info('creating version indexer')
        self.version_indexer = AnsibleVersionIndexer(checkoutdir=self.gitrepo.checkoutdir)

        logging.info('creating module indexer')
        self.module_indexer = ModuleIndexer(
            botmeta=self.botmeta,
            gh_client=self.gqlc,
            cachedir=self.cachedir_base,
            gitrepo=self.gitrepo,
            commits=not self.ignore_module_commits
        )

        logging.info('creating component matcher')
        self.component_matcher = AnsibleComponentMatcher(
            cachedir=self.cachedir_base,
            gitrepo=self.gitrepo,
            botmeta=self.botmeta,
            email_cache=self.module_indexer.emails_cache,
            usecache=True,
            use_galaxy=not self.args.ignore_galaxy
        )

        # resume is just an overload for the start-at argument
        resume = self.get_resume()
        if resume:
            if self.sort == 'desc':
                self.start_at = resume['number'] - 1
            else:
                self.start_at = resume['number'] + 1

    @property
    def ansible_members(self):
        if not self._ansible_members:
            self._ansible_members = self.get_members('ansible')
        return [x for x in self._ansible_members]

    @property
    def ansible_core_team(self):
        if self._ansible_core_team is None:
            teams = [
                'ansible-commit',
                'ansible-community',
            ]
            self._ansible_core_team = self.get_core_team('ansible', teams)
        return [x for x in self._ansible_core_team if x not in self.BOTNAMES]

    def load_botmeta(self):
        if self.botmetafile is not None:
            with open(self.botmetafile, 'rb') as f:
                rdata = f.read()
        else:
            rdata = self.gitrepo.get_file_content('.github/BOTMETA.yml')
        logging.info('ansible triager [re]loading botmeta')
        self.botmeta = BotMetadataParser.parse_yaml(rdata)

    def run(self):
        '''Primary execution method'''

        ts1 = datetime.datetime.now()
        icount = 0

        if self.ITERATION > 0:
            # update on each run to pull in new data
            logging.info('updating checkout')
            self.gitrepo.update()

            self.load_botmeta()

            logging.info('updating module indexer')
            self.module_indexer.update(botmeta=self.botmeta)

            logging.info('updating component matcher')
            self.component_matcher.update(
                email_cache=self.module_indexer.emails_cache,
                usecache=True,
                use_galaxy=not self.args.ignore_galaxy,
                botmeta=self.botmeta,
            )

        # is automerge allowed?
        self.automerge_on = False
        if self.botmeta.get('automerge'):
            if self.botmeta['automerge'] in ['Yes', 'yes', 'y', True, 1]:
                self.automerge_on = True

        # get all of the open issues [or just one]
        self.collect_repos()

        # stop here if we're just collecting issues to populate cache
        if self.collect_only:
            return

        for repopath, repodata in self.repos.copy().items():
            repo = repodata['repo']
            cachedir = os.path.join(self.cachedir_base, repopath)
            for issue in repodata['issues']:
                if issue is None:
                    continue

                icount += 1

                self.meta = {}
                self.processed_meta = {}
                number = issue.number
                self.set_resume(repopath, number)

                # keep track of known issues
                self.repos[repopath]['processed'].append(number)

                if issue.state == 'closed' and not self.ignore_state:
                    logging.info(to_text(number) + ' is closed, skipping')
                    redo = False
                    continue

                if self.only_prs and 'pull' not in issue.html_url:
                    logging.info(to_text(number) + ' is issue, skipping')
                    redo = False
                    continue

                if self.only_issues and 'pull' in issue.html_url:
                    logging.info(to_text(number) + ' is pullrequest, skipping')
                    redo = False
                    continue

                # users may want to re-run this issue after manual intervention
                redo = True

                # keep track of how many times this isssue has been re-done
                loopcount = 0

                # time each issue
                its1 = datetime.datetime.now()

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
                        cachedir=cachedir,
                        gitrepo=self.gitrepo,
                    )

                    if iw.is_pullrequest():
                        logging.info('creating CI wrapper')
                        self.ci = self.ci_class(self.cachedir_base, iw)
                    else:
                        self.ci = None

                    if self.skip_no_update:
                        lmeta = self.load_meta(iw)

                        if lmeta:

                            now = datetime.datetime.now()
                            skip = False

                            if lmeta['updated_at'] == to_text(iw.updated_at.isoformat()):
                                skip = True

                            if skip:
                                if iw.is_pullrequest():
                                    ua = to_text(iw.pullrequest.updated_at.isoformat())
                                    if lmeta['updated_at'] < ua:
                                        skip = False

                            if skip:
                                # re-check ansible/ansible after
                                # a window of time since the last check.
                                lt = lmeta['time']
                                lt = strip_time_safely(lt)
                                delta = (now - lt)
                                delta = delta.days
                                if delta > C.DEFAULT_STALE_WINDOW:
                                    msg = '!skipping: %s' % delta
                                    msg += ' days since last check'
                                    logging.info(msg)
                                    skip = False

                            if skip:
                                if iw.is_pullrequest():
                                    # if last process time is older than
                                    # last completion time on CI, we need
                                    # to reprocess because the CI status has
                                    # probabaly changed.
                                    if self.ci.updated_at and \
                                            self.ci.updated_at > strip_time_safely(lmeta['updated_at']):
                                        skip = False

                            # was this in the stale list?
                            if skip:
                                if iw.number in self.repos[repopath]['stale']:
                                    skip = False

                            # always poll rebuilds till they are merged
                            if lmeta.get('needs_rebuild') or lmeta.get('admin_merge'):
                                skip = False

                            # do a final check on the timestamp in meta
                            if skip:
                                mts = strip_time_safely(lmeta['time'])
                                delta = (now - mts).days
                                if delta > C.DEFAULT_STALE_WINDOW:
                                    skip = False

                            if skip:
                                msg = 'skipping: no changes since last run'
                                logging.info(msg)
                                continue

                    # force an update on the PR data
                    iw.update_pullrequest()
                    # build the history
                    self.build_history(iw)

                    actions = AnsibleActions()
                    self.process(iw)

                    # build up actions from the meta
                    self.create_actions(iw, actions)
                    self.save_meta(iw, self.meta, actions)

                    # DEBUG!
                    logging.info('url: %s' % iw.html_url)
                    logging.info('title: %s' % iw.title)
                    if iw.is_pullrequest():
                        for fn in iw.files:
                            logging.info('component[f]: %s' % fn)
                    else:
                        for line in iw.template_data.get('component_raw', '').split('\n'):
                            logging.info('component[t]: %s' % line)
                        for fn in self.meta['component_filenames']:
                            logging.info('component[m]: %s' % fn)

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

                    pprint(vars(actions))

                    # do the actions
                    action_meta = self.apply_actions(iw, actions)
                    if action_meta['REDO']:
                        redo = True

                its2 = datetime.datetime.now()
                td = (its2 - its1).total_seconds()
                logging.info('finished triage for %s in %ss' % (to_text(iw), td))

        ts2 = datetime.datetime.now()
        td = (ts2 - ts1).total_seconds()
        logging.info('triaged %s issues in %s seconds' % (icount, td))

    def eval_pr_param(self, pr):
        '''PR/ID can be a number, numberlist, script, jsonfile, or url'''

        if isinstance(pr, list):
            pass

        elif pr.isdigit():
            pr = int(pr)

        elif pr.startswith('http'):
            rr = requests.get(pr)
            numbers = rr.json()
            pr = numbers[:]

        elif os.path.isfile(pr) and not os.access(pr, os.X_OK):
            with open(pr) as f:
                numbers = json.loads(f.read())
            pr = numbers[:]

        elif os.path.isfile(pr) and os.access(pr, os.X_OK):
            # allow for scripts when trying to target spec issues
            logging.info('executing %s' % pr)
            (rc, so, se) = run_command(pr)
            numbers = json.loads(to_text(so))
            if numbers:
                if isinstance(numbers[0], dict) and 'number' in numbers[0]:
                    numbers = [x['number'] for x in numbers]
                else:
                    numbers = [int(x) for x in numbers]
            logging.info(
                '%s numbers after running script' % len(numbers)
            )
            pr = numbers[:]

        elif ',' in pr:
            numbers = [int(x) for x in pr.split(',')]
            pr = numbers[:]

        if not isinstance(pr, list):
            pr = [pr]

        return pr

    def update_issue_summaries(self, issuenums=None, repopath=None):

        if repopath:
            repopaths = [repopath]
        else:
            repopaths = [x for x in REPOS]

        for rp in repopaths:
            if issuenums and len(issuenums) <= 10:
                self.issue_summaries[repopath] = {}

                for num in issuenums:
                    # --pr is an alias to --id and can also be for issues
                    node = self.gqlc.get_summary(rp, 'pullRequest', num)
                    if node is None:
                        node = self.gqlc.get_summary(rp, 'issue', num)
                    if node is not None:
                        self.issue_summaries[repopath][to_text(num)] = node
            else:
                self.issue_summaries[repopath] = self.gqlc.get_issue_summaries(rp)


    def save_meta(self, issuewrapper, meta, actions):
        # save the meta+actions
        dmeta = meta.copy()
        dmeta['submitter'] = issuewrapper.submitter
        dmeta['number'] = issuewrapper.number
        dmeta['title'] = issuewrapper.title
        dmeta['body'] = issuewrapper.body
        dmeta['filenames'] = issuewrapper.files
        dmeta['renamed_filenames'] = issuewrapper.renamed_files
        dmeta['html_url'] = issuewrapper.html_url
        dmeta['created_at'] = to_text(issuewrapper.created_at.isoformat())
        dmeta['updated_at'] = to_text(issuewrapper.updated_at.isoformat())
        dmeta['template_data'] = issuewrapper.template_data
        if isinstance(actions, dict):
            dmeta['actions'] = actions.copy()
        else:
            if actions:
                dmeta['actions'] = vars(actions)
            else:
                dmeta['actions'] = {}
        dmeta['labels'] = issuewrapper.labels
        dmeta['assignees'] = issuewrapper.assignees
        if issuewrapper.history:
            dmeta['history'] = deepcopy(issuewrapper.history.history)
            for idx, x in enumerate(dmeta['history']):
                dmeta['history'][idx]['created_at'] = \
                    to_text(x['created_at'].isoformat())
        else:
            dmeta['history'] = []
        if issuewrapper.is_pullrequest():
            dmeta['pullrequest_status'] = issuewrapper.pullrequest_status
            dmeta['pullrequest_reviews'] = issuewrapper.reviews
        else:
            dmeta['pullrequest_status'] = []
            dmeta['pullrequest_reviews'] = []

        self.dump_meta(issuewrapper, dmeta)
        namespace, reponame = issuewrapper.repo_full_name.split('/', 1)

        # https://github.com/ansible/ansibullbot/issues/1355
        dmeta_copy = dmeta.copy()
        # These two might have dictionaries with keys that are considered
        # invalid in mongodb (like having '.') which would crash the receiver
        # and result in memory leaks.
        # FIXME figure out a way how to store these without keys being invalid
        dmeta_copy['collection_filemap'] = None
        dmeta_copy['collection_file_matches'] = None
        dmeta_copy['renamed_filenames'] = None
        dmeta_copy['test_support_plugins'] = None

        post_to_receiver(
            'metadata',
            {'user': namespace, 'repo': reponame, 'number': issuewrapper.number},
            dmeta_copy
        )
        self.processed_meta = dmeta_copy.copy()

    def load_meta(self, issuewrapper):
        mfile = os.path.join(
            issuewrapper.full_cachedir,
            'meta.json'
        )
        meta = {}
        if os.path.isfile(mfile):
            try:
                with open(mfile, 'rb') as f:
                    meta = json.load(f)
            except ValueError as e:
                logging.error("Could not load json from '%s' because: '%s'. Removing the file...", f.name, e)
                os.remove(mfile)
                return {}
        return meta

    def dump_meta(self, issuewrapper, meta):
        mfile = os.path.join(
            issuewrapper.full_cachedir,
            'meta.json'
        )
        meta['time'] = to_text(datetime.datetime.now().isoformat())
        logging.info('dump meta to %s' % mfile)

        with open(mfile, 'w', encoding='utf-8') as f:
            json.dump(meta, f)

    def create_actions(self, iw, actions):
        '''Parse facts and make actions from them'''
        # bot_broken + bot_skip bypass all actions
        if not self.ignore_bot_broken:
            bot_broken_commands = iw.history.get_commands(
                None,
                ['bot_broken', '!bot_broken'],
                timestamps=True
            )

            bot_broken_label = iw.history.label_last_applied('bot_broken')
            if bot_broken_label:
                bot_broken_commands.append((bot_broken_label, 'bot_broken'))

            bot_broken_unlabel = iw.history.label_last_removed('bot_broken')
            if bot_broken_unlabel:
                bot_broken_commands.append((bot_broken_label, '!bot_broken'))

            last_bot_broken = sorted(bot_broken_commands, key=lambda x: x[0])[-1:]
            if last_bot_broken and last_bot_broken[0][-1] == 'bot_broken':
                logging.warning('bot broken!')
                if 'bot_broken' not in iw.labels:
                    actions.newlabel.append('bot_broken')
                return
            else:
                if 'bot_broken' in iw.labels:
                    actions.unlabel.append('bot_broken')

            if 'bot_skip' in self.meta['maintainer_commands'] or \
                    'bot_skip' in self.meta['submitter_commands'] or \
                    '!bot_skip' in self.meta['maintainer_commands'] or \
                    '!bot_skip' in self.meta['submitter_commands']:
                bot_skip_users = [x.login for x in iw.repo.assignees]
                bot_skip_users.append(iw.submitter)
                bot_skip_commands = iw.history.get_commands(
                        bot_skip_users,
                        ['bot_skip', '!bot_skip'],
                        timestamps=True
                )
                last_bot_skip = sorted(bot_skip_commands, key=lambda x: x[0])[-1:]
                if last_bot_skip and last_bot_skip[0][-1] == 'bot_skip':
                    logging.warning('bot skip!')
                    return

        if iw.is_pullrequest():
            if not iw.incoming_repo_exists and C.features.is_enabled('close_missing_ref_prs'):
                type_to_branch_prefix = {
                    'bugfix pull request': 'bugfix',
                    'feature pull request': 'feature',
                    'documenation pull request': 'docs',
                    'test pull request': 'testing',
                    None: 'misc',
                }
                pr_number = iw.number
                pr_topic = iw.title.strip().replace(' ', '-').lower()
                pr_type = type_to_branch_prefix[
                    iw.template_data.get('issue type')
                ]
                pr_recovered_branch = (
                    'recovered-{pr_type}/{pr_number:d}-{pr_topic}'.
                    format(
                        pr_type=pr_type,
                        pr_number=pr_number,
                        pr_topic=pr_topic,
                    )
                )
                tvars = {
                    'pr_number': pr_number,
                    'pr_recovered_branch': pr_recovered_branch,
                    'pr_topic': pr_topic,
                    'pr_title_urlencoded': iw.title.replace(' ', '%20'),
                    'pr_type': pr_type,
                    'pr_submitter': iw.submitter,
                }
                comment = self.render_boilerplate(
                    tvars, boilerplate='incoming_ref_missing',
                )
                actions.comments.append(comment)
                if C.features.is_enabled('close_missing_ref_prs'):
                    actions.close = True
                actions.cancel_ci = True
                actions.cancel_ci_branch = True
                return

            if not iw.from_fork:
                tvars = {'submitter': iw.submitter}
                comment = self.render_boilerplate(tvars, boilerplate='fork')
                actions.comments.append(comment)
                actions.close = True
                actions.cancel_ci = True
                actions.cancel_ci_branch = True
                return

        # indicate what components were matched
        if not self.meta['is_bad_pr']:
            if iw.is_issue() and self.meta.get('needs_component_message'):
                tvars = {
                    'meta': self.meta
                }
                comment = self.render_boilerplate(
                    tvars, boilerplate='components_banner'
                )
                if comment not in actions.comments:
                    actions.comments.append(comment)

        # UNKNOWN!!! ... sigh.
        if iw.is_pullrequest():
            if self.meta['mergeable_state'] == 'unknown' and iw.state != 'closed':
                msg = 'skipping %s because it has a' % iw.number
                msg += ' mergeable_state of unknown'
                logging.warning(msg)
                return

        # TRIAGE!!!
        if 'needs_triage' not in iw.labels and not iw.history.was_unlabeled('needs_triage') and not iw.history.was_unlabeled('triage'):
            actions.newlabel.append('needs_triage')

        # legacy "triage" -> "needs_triage"
        if 'triage' in iw.labels:
            if 'needs_triage' not in iw.labels:
                actions.newlabel.append('needs_triage')
            actions.unlabel.append('triage')

        # owner PRs
        if iw.is_pullrequest():
            if self.meta['owner_pr']:
                if 'owner_pr' not in iw.labels:
                    actions.newlabel.append('owner_pr')
            else:
                if 'owner_pr' in iw.labels:
                    actions.unlabel.append('owner_pr')

        # REVIEWS
        for rtype in ['core_review', 'committer_review', 'community_review']:
            if self.meta[rtype]:
                if rtype not in iw.labels:
                    actions.newlabel.append(rtype)
            else:
                if rtype in iw.labels:
                    actions.unlabel.append(rtype)

        # WIPs
        if iw.is_pullrequest():
            if iw.wip:
                if 'WIP' not in iw.labels:
                    actions.newlabel.append('WIP')
                if 'shipit' in iw.labels:
                    actions.unlabel.append('shipit')
            else:
                if 'WIP' in iw.labels:
                    actions.unlabel.append('WIP')

        # MERGE COMMITS
        if iw.is_pullrequest():
            if self.meta['merge_commits']:
                if not self.meta['has_merge_commit_notification']:
                    comment = self.render_boilerplate(
                        self.meta,
                        boilerplate='merge_commit_notify'
                    )
                    actions.comments.append(comment)
                    if 'merge_commit' not in iw.labels:
                        actions.newlabel.append('merge_commit')
                if self.meta.get('has_ci'):
                    actions.cancel_ci = True
            else:
                if 'merge_commit' in iw.labels:
                    actions.unlabel.append('merge_commit')

        '''
        # BAD PR
        if iw.is_pullrequest() and self.meta['is_bad_pr']:
            actions.cancel_ci = True
        '''

        # @YOU IN COMMIT MSGS
        if iw.is_pullrequest():
            if self.meta['has_commit_mention']:
                if not self.meta['has_commit_mention_notification']:

                    comment = self.render_boilerplate(
                        self.meta,
                        boilerplate='commit_msg_mentions'
                    )
                    actions.comments.append(comment)

        # SHIPIT+AUTOMERGE
        if iw.is_pullrequest() and not self.meta['is_bad_pr']:
            if self.meta['shipit']:

                if 'shipit' not in iw.labels:
                    actions.newlabel.append('shipit')

                if self.meta['automerge']:
                    logging.info(self.meta['automerge_status'])
                    if 'automerge' not in iw.labels:
                        actions.newlabel.append('automerge')
                    if self.automerge_on:
                        actions.merge = True
                else:
                    logging.debug(self.meta['automerge_status'])
                    if 'automerge' in iw.labels:
                        actions.unlabel.append('automerge')

            else:

                # not shipit and not automerge ...
                if 'shipit' in iw.labels:
                    actions.unlabel.append('shipit')
                if 'automerge' in iw.labels:
                    actions.unlabel.append('automerge')

        # NAMESPACE MAINTAINER NOTIFY
        if iw.is_pullrequest() and not self.meta['is_bad_pr']:
            if needs_community_review(self.meta, iw):

                comment = self.render_boilerplate(
                    self.meta,
                    boilerplate='community_shipit_notify'
                )

                if comment and comment not in actions.comments:
                    actions.comments.append(comment)

        if iw.is_pullrequest() and self.meta['is_bad_pr']:
            if self.meta['is_bad_pr_reason']:
                last_comment_date = iw.history.last_date_for_boilerplate('bad_pr')

                if not last_comment_date:
                    comment = self.render_boilerplate(
                        tvars={'submitter': iw.submitter, 'is_bad_pr_reason': self.meta['is_bad_pr_reason']},
                        boilerplate='bad_pr'
                    )

                    if comment and comment not in actions.comments:
                        actions.comments.append(comment)

        # NEEDS REVISION
        if iw.is_pullrequest():
            if not iw.wip:
                if self.meta['is_needs_revision'] or self.meta['is_bad_pr']:
                    if 'needs_revision' not in iw.labels:
                        actions.newlabel.append('needs_revision')
                else:
                    if 'needs_revision' in iw.labels:
                        actions.unlabel.append('needs_revision')

        # NEEDS REBASE
        if iw.is_pullrequest():
            if self.meta['is_needs_rebase'] or self.meta['is_bad_pr']:
                if 'needs_rebase' not in iw.labels:
                    actions.newlabel.append('needs_rebase')
            else:
                if 'needs_rebase' in iw.labels:
                    actions.unlabel.append('needs_rebase')

        # comments with CI failures
        if iw.is_pullrequest() and not self.meta['is_bad_pr']:
            if self.meta['ci_state'] == 'failure' and \
                    self.meta['needs_testresult_notification']:
                tvars = {
                    'submitter': iw.submitter,
                    'data': self.meta['ci_test_results']
                }

                try:
                    comment = self.render_boilerplate(
                        tvars,
                        boilerplate='shippable_test_result'
                    )
                except Exception as e:
                    logging.debug(e)
                    raise

                # https://github.com/ansible/ansibullbot/issues/423
                if len(comment) < 65536:
                    if comment not in actions.comments:
                        actions.comments.append(comment)

        # https://github.com/ansible/ansibullbot/issues/293
        if iw.is_pullrequest():
            label = 'needs_ci'
            if not self.meta['has_ci']:
                if 'pre_azp' not in iw.labels:
                    if label not in iw.labels:
                        actions.newlabel.append(label)
            else:
                if label in iw.labels:
                    actions.unlabel.append(label)
                if 'pre_azp' in iw.labels:
                    actions.unlabel.append('pre_azp')

        # MODULE CATEGORY LABELS
        if not self.meta['is_bad_pr']:
            if self.meta['is_new_module'] or self.meta['is_module']:
                # add topic labels
                for t in ['topic', 'subtopic']:

                    mmatches = self.meta['module_match']
                    if not isinstance(mmatches, list):
                        mmatches = [mmatches]

                    for mmatch in mmatches:
                        label = mmatch.get(t)
                        if label in self.MODULE_NAMESPACE_LABELS:
                            label = self.MODULE_NAMESPACE_LABELS[label]

                        if label and label in self.valid_labels and \
                                label not in iw.labels and \
                                not iw.history.was_unlabeled(label):
                            actions.newlabel.append(label)

                        # add namespace labels
                        namespace = mmatch.get('namespace')
                        if namespace in self.MODULE_NAMESPACE_LABELS:
                            label = self.MODULE_NAMESPACE_LABELS[namespace]
                            if label not in iw.labels and \
                                    not iw.history.was_unlabeled(label):
                                actions.newlabel.append(label)

        # NEW MODULE
        if not self.meta['is_bad_pr']:
            if self.meta['is_new_module']:
                if 'new_module' not in iw.labels:
                    actions.newlabel.append('new_module')
            else:
                if 'new_module' in iw.labels:
                    actions.unlabel.append('new_module')

            if self.meta['is_module']:
                if 'module' not in iw.labels:
                    # don't add manually removed label
                    if not iw.history.was_unlabeled(
                        'module',
                        bots=self.BOTNAMES
                    ):
                        actions.newlabel.append('module')
            else:
                if 'module' in iw.labels:
                    # don't remove manually added label
                    if not iw.history.was_labeled(
                        'module',
                        bots=self.BOTNAMES
                    ):
                        actions.unlabel.append('module')

        # NEW PLUGIN
        if not self.meta['is_bad_pr']:
            label = 'new_plugin'
            if self.meta['is_new_plugin']:
                if label not in iw.labels and not iw.history.was_unlabeled(label):
                    actions.newlabel.append(label)
            else:
                if label in iw.labels and not iw.history.was_labeled(label):
                    actions.unlabel.append(label)

        # component labels
        if not self.meta['is_bad_pr']:
            if self.meta.get('component_labels') and not self.meta.get('merge_commits'):

                # only add these labels to pullrequest or un-triaged issues
                if iw.is_pullrequest() or \
                        (iw.is_issue() and
                        (not iw.labels or
                        'needs_triage' in iw.labels)):

                    # only add these if no c: labels have ever been changed by human
                    clabels = iw.history.get_changed_labels(
                        prefix='c:',
                        bots=self.BOTNAMES
                    )

                    if not clabels:
                        for cl in self.meta['component_labels']:
                            ul = iw.history.was_unlabeled(
                                cl,
                                bots=self.BOTNAMES
                            )
                            if not ul and \
                                    cl not in iw.labels and \
                                    cl not in actions.newlabel:
                                actions.newlabel.append(cl)

        if self.meta['is_pullrequest'] and self.meta['is_backport']:
            version = self.version_indexer.strip_ansible_version(self.meta['base_ref'])
            if version:
                for label in self.valid_labels:
                    if label.startswith('affects_'):
                        if label.endswith(version):
                            if label not in iw.labels:
                                actions.newlabel.append(label)
                        elif label in iw.labels:
                            actions.unlabel.append(label)
        elif self.meta['ansible_label_version']:
            vlabels = [x for x in iw.labels if x.startswith('affects_')]
            if not vlabels:
                label = 'affects_%s' % self.meta['ansible_label_version']
                if label not in iw.labels:
                    # do not re-add version labels
                    if not iw.history.was_unlabeled(label):
                        actions.newlabel.append(label)

        if self.meta['issue_type']:
            label = self.ISSUE_TYPES.get(self.meta['issue_type'])
            if label and label not in iw.labels:
                # do not re-add issue type labels
                if not iw.history.was_unlabeled(label):
                    actions.newlabel.append(label)

        # use the filemap to add labels
        if not self.meta['is_bad_pr']:
            if iw.is_pullrequest() and not self.meta.get('merge_commits'):
                fmap_labels = self.component_matcher.get_labels_for_files(iw.files)
                for label in fmap_labels:
                    if label in self.valid_labels and label not in iw.labels:
                        # do not re-add these labels
                        if not iw.history.was_unlabeled(label):
                            actions.newlabel.append(label)

        # python3 ... obviously!
        if not self.meta['is_bad_pr']:
            if self.meta['is_py3']:
                if 'python3' not in iw.labels:
                    # do not re-add py3
                    if not iw.history.was_unlabeled('python3'):
                        actions.newlabel.append('python3')

        # needs info?
        if self.meta['is_needs_info']:
            if 'needs_info' not in iw.labels:
                actions.newlabel.append('needs_info')

            # template data warning
            if self.meta['template_warning_required']:
                tvars = {
                    'submitter': iw.submitter,
                    'itype': iw.github_type,
                    'missing_sections': self.meta['template_missing_sections']
                }

                comment = self.render_boilerplate(
                    tvars,
                    boilerplate='issue_missing_data'
                )

                actions.comments.append(comment)

            if self.meta['template_missing_sections']:
                if 'needs_template' not in iw.labels:
                    actions.newlabel.append('needs_template')

        elif 'needs_info' in iw.labels:
            actions.unlabel.append('needs_info')

        # clear the needs_template label
        if not self.meta['is_needs_info'] or \
                not self.meta['template_missing_sections']:
            if 'needs_template' in iw.labels:
                actions.unlabel.append('needs_template')

        # needs_info warn/close?
        if self.meta['is_needs_info'] and self.meta['needs_info_action']:
            # FIXME the condition should be probably moved
            if not (self.meta['component_match_strategy'] == ['component_command'] and self.meta['template_missing_sections'] == ['component name']):
                if self.meta['needs_info_action'] == 'close':
                    actions.close = True

                tvars = {
                    'submitter': iw.submitter,
                    'action': self.meta['needs_info_action'],
                    'itype': iw.github_type
                }
                tvars.update(self.meta)

                comment = self.render_boilerplate(
                    tvars,
                    boilerplate='needs_info_base'
                )

                actions.comments.append(comment)

        # notify?
        if not self.meta['is_bad_pr']:
            if self.meta['to_notify']:
                tvars = {
                    'notify': self.meta['to_notify'],
                }
                comment = self.render_boilerplate(tvars, boilerplate='notify')
                if comment not in actions.comments:
                    actions.comments.append(comment)

        # needs_contributor
        if self.meta['is_needs_contributor']:
            if 'waiting_on_contributor' not in iw.labels:
                actions.newlabel.append('waiting_on_contributor')
        elif 'waiting_on_contributor' in iw.labels:
            actions.unlabel.append('waiting_on_contributor')

        # wontfix / notabug / bug_resolved / resolved_by_pr / duplicate_of
        if 'wontfix' in self.meta['maintainer_commands']:
            actions.close = True
        if 'notabug' in self.meta['maintainer_commands']:
            actions.close = True
        if 'bug_resolved' in self.meta['maintainer_commands']:
            actions.close = True
        if 'duplicate_of' in self.meta['maintainer_commands']:
            actions.close = True
        if 'close_me' in self.meta['maintainer_commands']:
            actions.close = True
        if 'resolved_by_pr' in self.meta['maintainer_commands']:
            # 'resolved_by_pr': {'merged': True, 'number': 19141},
            if self.meta['resolved_by_pr']['merged']:
                actions.close = True

        # migrated and source closed?
        if self.meta['is_migrated']:
            if 'github.com/ansible/ansible-' in self.meta['migrated_from']:
                if self.meta['migrated_issue_state'] != 'closed':
                    actions.close_migrated = True

        # bot_status
        if self.meta['needs_bot_status']:
            comment = self.render_boilerplate(
                self.meta,
                boilerplate='bot_status'
            )
            if comment not in actions.comments:
                actions.comments.append(comment)

        # performance issue/PR
        if self.meta['is_performance']:
            if 'performance' not in iw.labels:
                actions.newlabel.append('performance')

        # traceback
        if self.meta['has_traceback']:
            if 'traceback' not in iw.labels:
                actions.newlabel.append('traceback')

        # label commands
        if self.meta['label_cmds']:
            if self.meta['label_cmds']['add']:
                for label in self.meta['label_cmds']['add']:
                    if label not in iw.labels:
                        actions.newlabel.append(label)
                    if label in actions.unlabel:
                        actions.unlabel.remove(label)
            if self.meta['label_cmds']['del']:
                for label in self.meta['label_cmds']['del']:
                    if label in iw.labels:
                        actions.unlabel.append(label)
                    if label in actions.newlabel:
                        actions.newlabel.remove(label)

        # small patch?
        if iw.is_pullrequest():
            label_name = 'small_patch'
            if self.meta['is_small_patch']:
                if label_name not in iw.labels:
                    actions.newlabel.append(label_name)
            else:
                if label_name in iw.labels:
                    actions.unlabel.append(label_name)

        # docs_only?
        # https://github.com/ansible/ansibullbot/issues/1047
        if iw.is_pullrequest():
            label_name = 'docs_only'
            if self.meta['is_docs_only']:
                if label_name not in iw.labels:
                    actions.newlabel.append(label_name)
            else:
                if label_name in iw.labels:
                    actions.unlabel.append(label_name)

        if iw.is_pullrequest():

            # https://github.com/ansible/ansibullbot/issues/312
            # https://github.com/ansible/ansibullbot/issues/418
            if self.meta['ci_verified']:
                if 'ci_verified' not in iw.labels:
                    actions.newlabel.append('ci_verified')
            else:
                if 'ci_verified' in iw.labels:
                    actions.unlabel.append('ci_verified')

        # https://github.com/ansible/ansibullbot/issues/367
        if self.meta['is_backport']:
            if 'backport' not in iw.labels:
                actions.newlabel.append('backport')

        # https://github.com/ansible/ansibullbot/issues/29
        if self.meta['deprecated']:
            if 'deprecated' not in iw.labels:
                actions.newlabel.append('deprecated')
        else:
            if 'deprecated' in iw.labels:
                actions.unlabel.append('deprecated')

        # label PRs with missing repos
        if iw.is_pullrequest():
            if not self.meta['has_remote_repo']:
                if 'needs_repo' not in iw.labels:
                    actions.newlabel.append('needs_repo')
            else:
                if 'needs_repo' in iw.labels:
                    actions.unlabel.append('needs_repo')

        # https://github.com/ansible/ansibullbot/issues/458
        if not self.meta['is_bad_pr']:
            if iw.is_pullrequest():
                if self.meta['ci_stale']:
                    if 'stale_ci' not in iw.labels:
                        actions.newlabel.append('stale_ci')
                else:
                    if 'stale_ci' in iw.labels:
                        actions.unlabel.append('stale_ci')

        # https://github.com/ansible/ansibullbot/issues/589
        if not self.meta['is_bad_pr']:
            if self.meta['module_match'] and not self.meta['is_new_module']:
                mmatches = self.meta['module_match']
                if not isinstance(mmatches, list):
                    mmatches = [mmatches]
                needs_maintainer = False
                for mmatch in mmatches:
                    needs_maintainer = False
                    if not mmatch['maintainers'] and mmatch['support'] != 'core':
                        needs_maintainer = True
                        break
                if needs_maintainer:
                    if 'needs_maintainer' not in iw.labels:
                        actions.newlabel.append('needs_maintainer')
                else:
                    if 'needs_maintainer' in iw.labels:
                        actions.unlabel.append('needs_maintainer')

        # https://github.com/ansible/ansibullbot/issues/608
        if not self.meta['is_bad_pr']:
            if not self.meta.get('component_support'):
                cs_labels = ['support:core']
            else:
                cs_labels = []
                for sb in self.meta.get('component_support'):
                    if sb is None:
                        sb = 'core'
                    cs_label = 'support:%s' % sb
                    cs_labels.append(cs_label)
            for cs_label in cs_labels:
                if cs_label not in iw.labels:
                    actions.newlabel.append(cs_label)
            other_cs_labels = [x for x in iw.labels if x.startswith('support:')]
            for ocs_label in other_cs_labels:
                if ocs_label not in cs_labels:
                    actions.unlabel.append(ocs_label)

        if not self.meta['stale_reviews']:
            if 'stale_review' in iw.labels:
                actions.unlabel.append('stale_review')
        else:
            if 'stale_review' not in iw.labels:
                actions.newlabel.append('stale_review')

        # https://github.com/ansible/ansibullbot/issues/302
        if not self.meta['is_bad_pr']:
            if iw.is_pullrequest():
                if self.meta['needs_multiple_new_modules_notification']:
                    tvars = {
                        'submitter': iw.submitter
                    }
                    comment = self.render_boilerplate(
                        tvars, boilerplate='multiple_module_notify'
                    )
                    if comment not in actions.comments:
                        actions.comments.append(comment)

        # https://github.com/ansible/ansible/pull/26921
        if self.meta['is_filament']:

            # no notifications on these
            if actions.comments:
                remove = []
                for comment in actions.comments:
                    if '@' in comment:
                        remove.append(comment)
                if remove:
                    for comment in remove:
                        actions.comments.remove(comment)

            if 'filament' not in iw.labels:
                actions.newlabel.append('filament')
            if iw.age.days >= 5:
                actions.close = True

        # https://github.com/ansible/ansible/pull/68449
        if self.meta['test_support_plugins']:
            # should be fine to post just once, hopefully nobody will continue
            # with the PR after this comment...
            if not iw.history.last_date_for_boilerplate('test_support_plugins'):
                comment = self.render_boilerplate(
                    self.meta,
                    boilerplate='test_support_plugins'
                )
                if comment not in actions.comments:
                    actions.comments.append(comment)

        # https://github.com/ansible/ansibullbot/pull/664
        if self.meta['needs_rebuild_all']:
            actions.rebuild = True
            if 'stale_ci' in actions.newlabel:
                actions.newlabel.remove('stale_ci')
            if 'stale_ci' in iw.labels:
                actions.unlabel.append('stale_ci')
        elif self.meta['needs_rebuild_failed']:
            actions.rebuild_failed = True
            if 'stale_ci' in actions.newlabel:
                actions.newlabel.remove('stale_ci')
            if 'stale_ci' in iw.labels:
                actions.unlabel.append('stale_ci')

        # https://github.com/ansible/ansibullbot/issues/640
        if not self.meta['is_bad_pr']:
            if not self.meta['needs_rebuild'] and self.meta['admin_merge']:
                actions.merge = True

        # https://github.com/ansible/ansibullbot/issues/785
        if iw.is_pullrequest():
            if self.meta.get('new_contributor'):
                if 'new_contributor' not in iw.labels:
                    actions.newlabel.append('new_contributor')
            else:
                if 'new_contributor' in iw.labels:
                    actions.unlabel.append('new_contributor')

        # https://github.com/ansible/ansibullbot/issues/535
        if not self.meta['is_bad_pr']:
            for cm in self.meta['component_matches']:
                if cm.get('labels'):
                    for label in cm['labels']:
                        exists = label in iw.labels
                        unlabeled = iw.history.was_unlabeled(label)
                        valid = label in iw.repo.labels

                        # add it if a human did not remove it and is valid
                        if not exists and not unlabeled and valid:
                            actions.newlabel.append(label)

        # https://github.com/ansible/ansibullbot/issues/534
        if iw.is_pullrequest() and self.meta['is_empty_pr'] and not iw.wip:
            actions = AnsibleActions()
            actions.close = True

        # https://github.com/ansible/ansibullbot/issues/820
        if self.meta.get('wg', {}).get('needs_notification'):
            comment = self.render_boilerplate(
                self.meta,
                boilerplate='community_workgroups'
            )
            if comment not in actions.comments:
                actions.comments.append(comment)

        # https://github.com/ansible/ansibullbot/issues/924
        for key in ['has_pr', 'has_issue']:
            if self.meta['needs_' + key]:
                if key not in iw.labels:
                    actions.newlabel.append(key)

        # collections!!!
        if self.meta.get('is_collection'):
            clabels = ['collection']
            for fqcn in self.meta['collection_fqcns']:
                clabel = 'collection:%s' % fqcn
                clabels.append(clabel)
            for clabel in clabels:
                exists = clabel in iw.labels
                unlabeled = iw.history.was_unlabeled(clabel)

                # add it if a human did not remove it
                if not exists and not unlabeled:
                    actions.newlabel.append(clabel)

        # collections!!!
        if not self.meta.get('needs_collection_redirect') is True:
            if 'needs_collection_redirect' in iw.labels:
                actions.unlabel.append('needs_collection_redirect')
        else:
            if 'needs_collection_redirect' not in iw.labels:
                actions.newlabel.append('needs_collection_redirect')
            if self.botmeta['collection_redirect'] is True:
                actions.close = True
                actions.newlabel.append('bot_closed')
                if self.meta.get('needs_collection_redirect'):
                    comment = self.render_boilerplate(
                        self.meta,
                        boilerplate='collection_migration'
                    )
                    actions.comments.append(comment)

        # collections!!!
        if self.meta.get('collection_fqcn_label_remove'):
            for fqcn in self.meta['collection_fqcn_label_remove']:
                actions.unlabel.append('collection:%s'% fqcn)

        # spam!!!
        if self.meta.get('spam_comment_ids'):
            for commentid in self.meta['spam_comment_ids']:
                actions.uncomment.append(commentid)

        actions.newlabel = sorted({to_text(to_bytes(x, 'ascii'), 'ascii') for x in actions.newlabel})
        actions.unlabel = sorted({to_text(to_bytes(x, 'ascii'), 'ascii') for x in actions.unlabel})

        # check for waffling
        labels = sorted(set(actions.newlabel + actions.unlabel))
        for label in labels:
            if label in self.meta['label_waffling_overrides']:
                continue
            if iw.history.label_is_waffling(label):
                if label in actions.newlabel or label in actions.unlabel:
                    msg = f'"{label}" label is waffling on {iw.html_url}'
                    logging.error(msg)
                    raise LabelWafflingError(msg)
            elif label in actions.newlabel and label in actions.unlabel:
                msg = f'"{label}" label is waffling on {iw.html_url}'
                logging.error(msg)
                raise LabelWafflingError(msg)

    def post_actions_to_receiver(self, iw, actions, processed_meta):
        namespace, reponame = iw.repo_full_name.split('/', 1)
        processed_actions = {name: value for (name, value) in vars(actions).items() if value}
        data = processed_actions
        data['meta'] = processed_meta
        post_to_receiver(
            'actions',
            {'user': namespace, 'repo': reponame, 'number': iw.number},
            data,
        )

    def apply_actions(self, iw, actions):
        if self.safe_force:
            self.check_safe_match(iw, actions)
        return super().apply_actions(iw, actions)

    def check_safe_match(self, iw, actions):

        if self.safe_force_script:
            with open(self.safe_force_script, 'rb') as f:
                fdata = f.read()
            self.force = bool(eval(fdata))
            return self.force

        safe = True

        count = actions.count()
        if count:
            # all but needs_revision and needs_rebase labels are safe
            labels = set(actions.newlabel + actions.unlabel)
            if not labels.intersection(['needs_revision', 'needs_rebase']):
                count -= len(actions.newlabel) + len(actions.unlabel)

            # cc comment is safe
            if actions.comments:
                if len(actions.comments) == 1 and actions.comments[0].startswith('cc '):
                    count -= len(actions.comments)

            # assign is safe
            if actions.assign:
                count -= 1

            safe = bool(count)

        self.force = safe

        return safe

    def get_stale_numbers(self, reponame):
        # https://github.com/ansible/ansibullbot/issues/458

        stale = []
        reasons = {}

        for number, summary in self.issue_summaries[reponame].items():

            if number in stale:
                continue

            if summary['state'] == 'closed':
                continue

            number = int(number)
            mfile = os.path.join(
                self.cachedir_base,
                reponame,
                'issues',
                to_text(number),
                'meta.json'
            )

            if not os.path.isfile(mfile):
                reasons[number] = '%s missing' % mfile
                stale.append(number)
                continue

            try:
                with open(mfile, 'rb') as f:
                    meta = json.load(f)
            except ValueError as e:
                logging.error('failed to parse %s: %s' % (to_text(mfile), to_text(e)))
                os.remove(mfile)
                reasons[number] = '%s missing' % mfile
                stale.append(number)
                continue

            ts = meta['time']
            ts = strip_time_safely(ts)
            now = datetime.datetime.now()
            delta = (now - ts).days

            if delta > C.DEFAULT_STALE_WINDOW:
                reasons[number] = '%s delta' % delta
                stale.append(number)

        stale = sorted({int(x) for x in stale})
        if 10 >= len(stale) > 0:
            logging.info('stale: %s' % ','.join([to_text(x) for x in stale]))

        return stale

    def collect_repos(self):
        '''Populate the local cache of repos'''
        logging.info('start collecting repos')
        for repo in REPOS:
            # skip repos based on args
            if self.repo and self.repo != repo:
                continue
            if self.skiprepo:
                if repo in self.skiprepo:
                    continue

            if self.pr:
                numbers = self.eval_pr_param(self.pr)
                self._collect_repo(repo, issuenums=numbers)
            else:
                self._collect_repo(repo)
        logging.info('finished collecting issues')

    @RateLimited
    def _collect_repo(self, repo, issuenums=None):
        '''Collect issues for an individual repo'''

        logging.info('getting repo obj for %s' % repo)
        if repo not in self.repos:
            self.repos[repo] = {
                'repo': self.ghw.get_repo(repo),
                'issues': [],
                'processed': [],
                'since': None,
                'stale': [],
                'loopcount': 0
            }
        else:
            # force a clean repo object to limit caching problems
            self.repos[repo]['repo'] = \
                self.ghw.get_repo(repo)
            # clear the issues
            self.repos[repo]['issues'] = {}
            # increment the loopcount
            self.repos[repo]['loopcount'] += 1

        issuecache = {}

        logging.info('getting issue objs for %s' % repo)
        self.update_issue_summaries(repopath=repo, issuenums=issuenums)

        issuecache = {}
        numbers = self.issue_summaries[repo].keys()
        numbers = {int(x) for x in numbers}
        if issuenums:
            numbers.intersection_update(issuenums)
            numbers = list(numbers)
        logging.info('%s known numbers' % len(numbers))

        if self.daemonize:

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
                if ts:
                    self.repos[repo]['since'] = ts[-1]
            else:
                since = strip_time_safely(self.repos[repo]['since'])
                api_since = self.repos[repo]['repo'].get_issues(since=since)

                numbers = []
                for x in api_since:
                    number = x.number
                    numbers.append(number)
                    issuecache[number] = x

                numbers = sorted({int(n) for n in numbers})
                logging.info(
                    '%s numbers after [api] since == %s' %
                    (len(numbers), since)
                )

                for k, v in self.issue_summaries[repo].items():
                    if v['created_at'] is None:
                        # issue is closed and was never processed
                        continue

                    if v['created_at'] > self.repos[repo]['since']:
                        numbers.append(k)

                numbers = sorted({int(n) for n in numbers})
                logging.info(
                    '%s numbers after [www] since == %s' %
                    (len(numbers), since)
                )

        if self.start_at and self.repos[repo]['loopcount'] == 0:
            numbers = [x for x in numbers if x <= self.start_at]
            logging.info('%s numbers after start-at' % len(numbers))

        # Get stale numbers if not targeting
        if self.daemonize and self.repos[repo]['loopcount'] > 0:
            logging.info('checking for stale numbers')
            stale = self.get_stale_numbers(repo)
            self.repos[repo]['stale'] = [int(x) for x in stale]
            numbers += [int(x) for x in stale]
            numbers = sorted(set(numbers))
            logging.info('%s numbers after stale check' % len(numbers))

        ################################################################
        # PRE-FILTERING TO PREVENT EXCESSIVE API CALLS
        ################################################################

        # filter just the open numbers
        if not self.only_closed and not self.ignore_state:
            numbers = [
                x for x in numbers
                if (to_text(x) in self.issue_summaries[repo] and
                self.issue_summaries[repo][to_text(x)]['state'] == 'open')
            ]
            logging.info('%s numbers after checking state' % len(numbers))

        # filter by type
        if self.only_issues:
            numbers = [
                x for x in numbers
                if self.issue_summaries[repo][to_text(x)]['type'] == 'issue'
            ]
            logging.info('%s numbers after checking type' % len(numbers))
        elif self.only_prs:
            numbers = [
                x for x in numbers
                if self.issue_summaries[repo][to_text(x)]['type'] == 'pullrequest'
            ]
            logging.info('%s numbers after checking type' % len(numbers))

        numbers = sorted({int(x) for x in numbers})
        if self.sort == 'desc':
            numbers = [x for x in reversed(numbers)]

        if self.args.last and len(numbers) > self.args.last:
            numbers = numbers[0 - self.args.last:]

        # Use iterator to avoid requesting all issues upfront
        self.repos[repo]['issues'] = RepoIssuesIterator(
            self.repos[repo]['repo'],
            numbers,
            issuecache=issuecache
        )

        logging.info('getting repo objs for %s complete' % repo)

    def process(self, iw):
        '''Do initial processing of the issue'''

        # clear the actions+meta
        self.meta = MetaDict()

        self.meta['state'] = iw.state
        self.meta['submitter'] = iw.submitter

        # extract template data
        self.template_data = iw.template_data

        # set the issue type
        ITYPE = self.template_data.get('issue type')
        if ITYPE in self.ISSUE_TYPES:
            self.meta['issue_type'] = ITYPE
        else:
            # look for best match?
            self.meta['issue_type'] = self.guess_issue_type(iw)

        # needed for bot status
        if iw.is_issue():
            self.meta['is_issue'] = True
            self.meta['is_pullrequest'] = False
        else:
            self.meta['is_issue'] = False
            self.meta['is_pullrequest'] = True

        # get ansible version
        if iw.is_issue():
            self.meta['ansible_version'] = \
                self.get_ansible_version_by_issue(iw)
        else:
            # use the submit date's current version
            self.meta['ansible_version'] = \
                self.version_indexer.version_by_date(iw.created_at)

        # https://github.com/ansible/ansible/issues/21207
        if not self.meta['ansible_version']:
            # fallback to version by date
            self.meta['ansible_version'] = \
                self.version_indexer.version_by_date(iw.created_at)

        self.meta['ansible_label_version'] = \
            get_version_major_minor(self.meta['ansible_version'])
        logging.info('ansible version: %s' % self.meta['ansible_version'])

        # what is this?
        self.meta['is_migrated'] = False

        # what component(s) is this about?
        self.meta.update(
            get_component_match_facts(
                iw,
                self.component_matcher,
                self.valid_labels
            )
        )

        # collections?
        self.meta.update(
            get_collection_facts(
                iw,
                self.component_matcher,
                self.meta,
            )
        )

        # python3 ?
        self.meta.update(get_python3_facts(iw))

        # backports
        self.meta.update(get_backport_facts(iw, self.meta))

        # performance
        self.meta.update(get_performance_facts(iw, self.meta))

        # traceback
        self.meta.update(get_traceback_facts(iw))

        # small_patch
        self.meta.update(get_small_patch_facts(iw))

        # docs_only
        self.meta.update(get_docs_facts(iw))

        # shipit?
        self.meta.update(
            get_needs_revision_facts(
                self,
                iw,
                self.meta,
                self.ci
            )
        )

        # needs_contributor?
        self.meta.update(
            get_needs_contributor_facts(
                self,
                iw,
                self.meta,
            )
        )

        # who needs to be notified or assigned?
        self.meta.update(get_notification_facts(iw, self.meta, botmeta=self.botmeta))

        # ci_verified and test results
        self.meta.update(
            get_ci_run_facts(iw, self.meta, self.ci)
        )

        # needsinfo?
        self.meta['is_needs_info'] = is_needsinfo(self, iw)
        self.meta.update(self.process_comment_commands(iw, self.meta))
        self.meta.update(needs_info_template_facts(iw, self.meta))
        self.meta.update(needs_info_timeout_facts(iw, self.meta))

        # who is this person?
        self.meta.update(
            get_submitter_facts(
                iw,
                self.meta,
                self.module_indexer.emails_cache,
                self.component_matcher
            )
        )

        # shipit?
        self.meta.update(
            get_shipit_facts(
                iw, self.meta, self.botmeta['files'],
                core_team=self.ansible_core_team, botnames=self.BOTNAMES
            )
        )
        self.meta.update(get_review_facts(iw, self.meta))

        # bot_status needed?
        self.meta.update(get_bot_status_facts(iw, self.module_indexer.all_maintainers, core_team=self.ansible_core_team, bot_names=self.BOTNAMES))

        # who is this waiting on?
        self.meta.update(self.waiting_on(iw, self.meta))

        # community label manipulation
        self.meta.update(
            get_label_command_facts(
                iw,
                self.meta,
                self.module_indexer.all_maintainers,
                core_team=self.ansible_core_team,
                valid_labels=self.valid_labels
            )
        )

        # waffling overrides [label_waffling_overrides]
        self.meta.update(
            get_waffling_overrides(
                iw,
                self.meta,
                self.module_indexer.all_maintainers,
                core_team=self.ansible_core_team,
                valid_labels=self.valid_labels
            )
        )

        # filament
        self.meta.update(get_filament_facts(iw, self.meta))

        # test_support_plugins
        self.meta.update(
            get_test_support_plugins_facts(iw, self.component_matcher)
        )

        # ci
        self.meta.update(get_ci_facts(iw, self.ci))

        # ci rebuilds
        self.meta.update(get_rebuild_facts(iw, self.meta))

        # ci rebuild + merge
        self.meta.update(
            get_rebuild_merge_facts(
                iw,
                self.meta,
                self.ansible_core_team,
                self.ci,
            )
        )

        # ci rebuild requested?
        self.meta.update(
            get_rebuild_command_facts(
                iw,
                self.meta,
                self.ci,
            )
        )

        # first time contributor?
        self.meta.update(get_contributor_facts(iw))

        # is it deprecated?
        self.meta.update(get_deprecation_facts(iw, self.meta))

        # does it have a pr or does it have an issue?
        self.meta.update(get_cross_reference_facts(iw, self.meta))

        # need these keys to always exist
        if 'merge_commits' not in self.meta:
            self.meta['merge_commits'] = []
        if 'is_bad_pr' not in self.meta:
            self.meta['is_bad_pr'] = False

        if iw.migrated:
            miw = iw._migrated_issue
            self.meta['is_migrated'] = True
            self.meta['migrated_from'] = to_text(miw)
            try:
                self.meta['migrated_issue_repo_path'] = miw.repo_full_name
                self.meta['migrated_issue_number'] = miw.number
                self.meta['migrated_issue_state'] = miw.state
            except AttributeError:
                self.meta['migrated_issue_repo_path'] = None
                self.meta['migrated_issue_number'] = None
                self.meta['migrated_issue_state'] = None

        # spam!
        self.meta.update(get_spam_facts(iw, self.meta))

        # automerge
        self.meta.update(get_automerge_facts(iw, self.meta))

        # community working groups
        self.meta.update(get_community_workgroup_facts(iw, self.meta))

    def build_history(self, issuewrapper):
        '''Set the history and merge other event sources'''
        iw = issuewrapper
        iw._history = False
        iw.history

        if iw.migrated:
            mi = self.get_migrated_issue(iw.migrated_from)
            if mi:
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

        return None

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
            raise Exception('unknown url type for migrated issue')

        # https://github.com/ansible/ansibullbot/issues/1303
        try:
            mw = self.get_issue_by_repopath_and_number(
                mirepopath,
                minumber
            )
        except Exception as e:
            mw = None

        return mw

    def get_issue_by_repopath_and_number(self, repo_path, number):

        # get the repo if not already fetched
        if repo_path not in self.repos:
            self.repos[repo_path] = {
                'repo': self.ghw.get_repo(repo_path),
                'issues': {}
            }

        mrepo = self.repos[repo_path]['repo']
        missue = mrepo.get_issue(number)

        if not missue:
            return None

        mw = IssueWrapper(
            github=self.ghw,
            repo=mrepo,
            issue=missue,
            cachedir=os.path.join(self.cachedir_base, repo_path)
        )
        return mw

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
        vcommands.remove('needs_contributor')
        vcommands.remove('!needs_contributor')

        iw = issuewrapper

        maintainers = []

        maintainers += meta.get('component_authors', [])
        maintainers += meta.get('component_maintainers', [])
        maintainers += meta.get('component_notifiers', [])

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

        # JIMI_SKIP!!!
        if issuewrapper.submitter in ['jimi-c']:
            if 'bot_skip' not in meta['maintainer_commands']:
                meta['maintainer_commands'].append('bot_skip')
            if '!bot_skip' in meta['maintainer_commands']:
                meta['maintainer_commands'].remove('!bot_skip')
            if '!bot_skip' in meta['submitter_commands']:
                meta['submitter_commands'].remove('!bot_skip')

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
            if pr_number is None:
                # ignore resolved_by_pr command without actual number
                logging.warning("Invalid resolved_by_pr command in '%s'", mc[-1])
            else:
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

    def waiting_on(self, issuewrapper, meta):
        iw = issuewrapper
        wo = None
        if iw.is_issue():
            if meta['is_needs_info']:
                wo = iw.submitter
            elif meta['is_needs_contributor']:
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

    def get_ansible_version_by_issue(self, iw):
        aversion = None

        rawdata = iw.template_data.get('ansible version', '')
        if rawdata:
            aversion = self.version_indexer.strip_ansible_version(rawdata)

        if not aversion or aversion == 'devel':
            aversion = self.version_indexer.version_by_date(
                iw.instance.created_at
            )

        if aversion:
            if aversion.endswith('.'):
                aversion += '0'

        # re-run for versions ending with .x
        if aversion:
            if aversion.endswith('.x'):
                aversion = self.version_indexer.strip_ansible_version(aversion)

        if self.version_indexer.is_valid_version(aversion) and \
                aversion is not None:
            return aversion
        else:

            # try to go through the submitter's comments and look for the
            # first one that specifies a valid version
            cversion = None
            for comment in iw.comments:
                if comment['actor'] != iw.instance.user.login:
                    continue
                xver = self.version_indexer.strip_ansible_version(comment['body'])
                if self.version_indexer.is_valid_version(xver):
                    cversion = xver
                    break

            # use the comment version
            aversion = cversion

        return aversion

    def execute_actions(self, iw, actions):
        """Turns the actions into API calls"""

        self.post_actions_to_receiver(iw, actions, self.processed_meta)

        super().execute_actions(iw, actions)

        if actions.close_migrated:
            mi = self.get_issue_by_repopath_and_number(
                self.meta['migrated_issue_repo_path'],
                self.meta['migrated_issue_number']
            )
            logging.info('close migrated: %s' % mi.html_url)
            mi.instance.edit(state='closed')

        if actions.rebuild:
            runid = self.meta.get('ci_run_number')
            if runid:
                logging.info('Rebuilding CI %s for #%s' % (runid, iw.number))
                self.ci.rebuild(runid)
            else:
                logging.error(
                    f'rebuild: no CI runid for {iw.number}'
                )
        elif actions.rebuild_failed:
            runid = self.meta.get('ci_run_number')
            if runid:
                logging.info('Rebuilding CI %s for #%s' % (runid, iw.number))
                self.ci.rebuild_failed(runid)
            else:
                logging.error(
                    f'rebuild: no CI runid for {iw.number}'
                )

        if actions.cancel_ci:
            runid = self.meta.get('ci_run_number')
            if runid:
                logging.info('Cancelling CI %s for #%s' % (runid, iw.number))
                self.ci.cancel(runid)
            else:
                logging.error(
                    f'cancel: no CI runid for {iw.number}'
                )

        if actions.cancel_ci_branch:
            branch = iw.pullrequest.head.repo
            self.ci.cancel_on_branch(branch)

    @classmethod
    def create_parser(cls):

        parser = DefaultTriager.create_parser()

        parser.description = "Triage issue and pullrequest queues for Ansible.\n" \
                             " (NOTE: only useful if you have commit access to" \
                             " the repo in question.)"

        parser.add_argument("--repo", "-r", type=str, choices=REPOS,
                            help="Github repo to triage (defaults to all)")

        parser.add_argument("--skip_no_update", action="store_true",
                            help="skip processing if updated_at hasn't changed")

        parser.add_argument("--collect_only", action="store_true",
                            help="stop after caching issues")

        parser.add_argument("--sort", default='desc', choices=['asc', 'desc'],
                            help="Direction to sort issues [desc=9-0 asc=0-9]")

        parser.add_argument("--skiprepo", action='append',
                            help="Github repo to skip triaging")

        parser.add_argument("--only_prs", action="store_true",
                            help="Triage pullrequests only")
        parser.add_argument("--only_issues", action="store_true",
                            help="Triage issues only")

        parser.add_argument("--only_open", action="store_true",
                            help="Triage open issues|prs only")
        parser.add_argument("--only_closed", action="store_true",
                            help="Triage closed issues|prs only")

        parser.add_argument("--safe_force", action="store_true",
                            help="Prompt only on specific actions")
        parser.add_argument("--safe_force_script", type=str,
                            help="Script to check safe force")
        parser.add_argument("--ignore_state", action="store_true",
                            help="Do not skip processing closed issues")
        parser.add_argument("--ignore_bot_broken", action="store_true",
                            help="Do not skip processing bot_broken|bot_skip issues")

        parser.add_argument("--ignore_module_commits", action="store_true",
                            help="Do not enumerate module commit logs")

        parser.add_argument(
            "--pr", "--id", type=str,
            help="Triage only the specified pr|issue (separated by commas)"
        )

        parser.add_argument("--start-at", "--resume_id", type=int,
                            help="Start triage at the specified pr|issue")
        parser.add_argument("--resume", action="store_true", dest="resume_enabled",
                            help="pickup right after where the bot last stopped")
        parser.add_argument("--no_since", action="store_true",
                            help="Do not use the since keyword to fetch issues")
        parser.add_argument("--last", type=int,
                            help="triage the last N issues or PRs")

        parser.add_argument('--commit', dest='ansible_commit',
                            help="Use a specific commit for the indexers")

        parser.add_argument('--ignore_galaxy', action='store_true',
                            help='do not index or search for components in galaxy')

        parser.add_argument("--ci", type=str, choices=VALID_CI_PROVIDERS,
                            default=C.DEFAULT_CI_PROVIDER,
                            help="Specify a CI provider that repo uses")

        return parser

    def get_resume(self):
        '''Returns a dict with the last issue repo+number processed'''
        if self.pr or not self.resume_enabled:
            return

        resume_file = os.path.join(self.cachedir_base, 'resume.json')
        if not os.path.isfile(resume_file):
            logging.error('Resume: %r not found', resume_file)
            return None

        logging.debug('Resume: read %r', resume_file)
        with open(resume_file, 'r', encoding='utf-8') as f:
            data = json.loads(f.read())
        return data

    def set_resume(self, repo, number):
        if self.pr or not self.resume_enabled:
            return

        data = {
            'repo': repo,
            'number': number
        }
        resume_file = os.path.join(self.cachedir_base, 'resume.json')
        with open(resume_file, 'w', encoding='utf-8') as f:
            json.dump(data, f)
