# This file is part of Ansible
#
# Ansible is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Ansible is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Ansible. If not, see <http://www.gnu.org/licenses/>.


import abc
import argparse
import datetime
import json
import logging
import os
import sys
import time
import typing as t

import requests
from jinja2 import Environment, FileSystemLoader

from ansibullbot import constants as C
from ansibullbot.utils.github import RateLimited
from ansibullbot.utils.gh_gql_client import GithubGraphQLClient
from ansibullbot.utils.git_tools import GitRepoWrapper
from ansibullbot.utils.logs import set_logger
from ansibullbot.utils.systemtools import run_command
from ansibullbot.utils.timetools import strip_time_safely
from ansibullbot.ghapiwrapper import GithubWrapper, RepoWrapper


basepath = os.path.dirname(__file__).split('/')
libindex = basepath[::-1].index('ansibullbot')
libindex = (len(basepath) - 1) - libindex
basepath = '/'.join(basepath[0:libindex])

_environment = Environment(
    loader=FileSystemLoader(os.path.join(basepath, 'templates')),
    trim_blocks=True
)


class DefaultActions:
    def __init__(self):
        self.newlabel = []
        self.unlabel = []
        self.comments = []
        self.uncomment = []
        self.close = False
        self.open = False
        self.merge = False

    def count(self):
        """ Return the number of actions that are to be performed """
        count = 0
        for value in vars(self).values():
            if value:
                if isinstance(value, bool):
                    count += 1
                else:
                    count += len(value)

        return count


def render_boilerplate(tvars: t.Dict[str, t.Any], boilerplate: str) -> str:
    return _environment.get_template(f'{boilerplate}.j2').render(**tvars)


class DefaultTriager:
    """
    How to use:
    1. Create a new class which inherits from DefaultTriager
    2. Implement 'Triager.run(self)' method:
        - iterate over issues/pull requests
        - for each issue
        1. create 'actions = DefaultActions()'
        2. define which action(s) should be done updating 'actions' instance
        3. call parent 'apply_actions' methods: 'DefaultTriager.apply_actions(iw, actions)'
    3. Run:
    def main():
        Triager().start()
    """
    CLOSING_LABELS = []

    def __init__(self, args=None):
        parser = self.create_parser()
        self.args = parser.parse_args(args)

        set_logger(debug=self.args.debug, logfile=self.args.logfile)
        logging.info('starting bot')

        self.cachedir_base = os.path.expanduser(self.args.cachedir_base)
        self.repos = {}

        # resume is just an overload for the start-at argument
        resume = self.get_resume()
        if resume:
            if self.args.sort == 'desc':
                self.args.start_at = resume['number'] - 1
            else:
                self.args.start_at = resume['number'] + 1

        logging.info('creating api wrapper')
        self.ghw = GithubWrapper(
            url=C.DEFAULT_GITHUB_URL,
            user=C.DEFAULT_GITHUB_USERNAME,
            passw=C.DEFAULT_GITHUB_PASSWORD,
            token=C.DEFAULT_GITHUB_TOKEN,
            cachedir=self.cachedir_base
        )

        logging.info('creating graphql client')
        self.gqlc = GithubGraphQLClient(
            C.DEFAULT_GITHUB_TOKEN,
            server=C.DEFAULT_GITHUB_URL
        )

        self._maintainer_team = None

    @property
    def maintainer_team(self):
        # Note: this assumes that the token used by the bot has access to check
        # team privileges across potentially more than one organization
        if self._maintainer_team is None:
            self._maintainer_team = []
            teams = C.DEFAULT_GITHUB_MAINTAINERS
            for team in teams:
                _org, _team = team.split('/')
                self._maintainer_team.extend(self.gqlc.get_members(_org, _team))
        return sorted(set(self._maintainer_team).difference(C.DEFAULT_BOT_NAMES))

    @classmethod
    def create_parser(cls):
        parser = argparse.ArgumentParser()
        parser.add_argument("--botmetafile", type=str, default=None, help="Use this filepath for botmeta instead of from the repo")
        parser.add_argument("--cachedir", type=str, dest='cachedir_base', default='~/.ansibullbot/cache')
        parser.add_argument("--daemonize", action="store_true", help="run in a continuos loop")
        parser.add_argument("--daemonize_interval", type=int, default=(30 * 60), help="seconds to sleep between loop iterations")
        parser.add_argument("--debug", "-d", action="store_true", help="Debug output")
        parser.add_argument("--dry-run", "-n", action="store_true", help="Don't make any changes")
        parser.add_argument("--dump_actions", action="store_true", help="serialize the actions to disk [/tmp/actions]")
        parser.add_argument("--force", "-f", action="store_true", help="Do not ask questions")
        parser.add_argument("--logfile", type=str, help="Send logging to this file")
        parser.add_argument("--ignore_state", action="store_true", help="Do not skip processing closed issues")
        parser.add_argument("--last", type=int, help="triage the last N issues or PRs")
        parser.add_argument("--only_closed", action="store_true", help="Triage closed issues|prs only")
        parser.add_argument("--only_issues", action="store_true", help="Triage issues only")
        parser.add_argument("--only_prs", action="store_true", help="Triage pullrequests only")
        parser.add_argument("--pause", "-p", action="store_true", dest="always_pause", help="Always pause between prs|issues")
        parser.add_argument("--pr", "--id", type=str, help="Triage only the specified pr|issue (separated by commas)")
        parser.add_argument("--resume", action="store_true", dest="resume_enabled", help="pickup right after where the bot last stopped")
        parser.add_argument("--repo", "-r", type=str, help="Github repo to triage (defaults to all)")
        parser.add_argument("--skiprepo", action='append', help="Github repo to skip triaging")
        parser.add_argument("--start-at", type=int, help="Start triage at the specified pr|issue")
        parser.add_argument("--sort", default='desc', choices=['asc', 'desc'], help="Direction to sort issues [desc=9-0 asc=0-9]")
        return parser

    def start(self):
        if self.args.daemonize:
            logging.info('starting daemonize loop')
            while True:
                self.run()
                interval = self.args.daemonize_interval
                logging.info('sleep %ss (%sm)' % (interval, interval / 60))
                time.sleep(interval)
        else:
            logging.info('starting single run')
            self.run()
        logging.info('stopping bot')

    @abc.abstractmethod
    def run(self):
        pass

    def apply_actions(self, iw, actions):
        action_meta = {'REDO': False}

        if actions.count() > 0:
            if self.args.dump_actions:
                self.dump_action_dict(iw, actions.__dict__)

            if self.args.dry_run:
                print("Dry-run specified, skipping execution of actions")
            else:
                if self.args.force:
                    print("Running actions non-interactive as you forced.")
                    self.execute_actions(iw, actions)
                    return action_meta
                cont = input("Take recommended actions (y/N/a/R/DEBUG)? ")
                if cont in ('a', 'A'):
                    sys.exit(0)
                if cont in ('Y', 'y'):
                    self.execute_actions(iw, actions)
                if cont in ('r', 'R'):
                    action_meta['REDO'] = True
                if cont == 'DEBUG':
                    # put the user into a breakpoint to do live debug
                    action_meta['REDO'] = True
                    import epdb; epdb.st()
        elif self.args.always_pause:
            print("Skipping, but pause.")
            cont = input("Continue (Y/n/a/R/DEBUG)? ")
            if cont in ('a', 'A', 'n', 'N'):
                sys.exit(0)
            elif cont in ('r', 'R'):
                action_meta['REDO'] = True
            elif cont == 'DEBUG':
                # put the user into a breakpoint to do live debug
                import epdb; epdb.st()
                action_meta['REDO'] = True
        else:
            print("Skipping.")

        # let the upper level code redo this issue
        return action_meta

    def execute_actions(self, iw, actions):
        """Turns the actions into API calls"""
        for commentid in actions.uncomment:
            iw.remove_comment_by_id(commentid)

        for comment in actions.comments:
            logging.info("acton: comment - " + comment)
            iw.add_comment(comment=comment)

        if actions.close:
            for newlabel in actions.newlabel:
                if newlabel in self.CLOSING_LABELS:
                    logging.info('action: label - ' + newlabel)
                    iw.add_label(label=newlabel)

            for unlabel in actions.unlabel:
                logging.info('action: unlabel - ' + unlabel)
                iw.remove_label(label=unlabel)

            logging.info('action: close')
            iw.instance.edit(state='closed')

        else:
            for unlabel in actions.unlabel:
                logging.info('action: unlabel - ' + unlabel)
                iw.remove_label(label=unlabel)
            for newlabel in actions.newlabel:
                logging.info('action: label - ' + newlabel)
                iw.add_label(label=newlabel)

            if actions.merge:
                iw.merge()

    def dump_action_dict(self, issue, actions):
        """Serialize the action dict to disk for quick(er) debugging"""
        fn = os.path.join('/tmp', 'actions', issue.repo_full_name, str(issue.number) + '.json')
        dn = os.path.dirname(fn)
        if not os.path.isdir(dn):
            os.makedirs(dn)

        logging.info(f'dumping {fn}')
        with open(fn, 'w') as f:
            f.write(json.dumps(actions, indent=2, sort_keys=True))

    def get_resume(self):
        """Returns a dict with the last issue repo+number processed"""
        if self.args.pr or not self.args.resume_enabled:
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
        if self.args.pr or not self.args.resume_enabled:
            return

        data = {
            'repo': repo,
            'number': number
        }
        resume_file = os.path.join(self.cachedir_base, 'resume.json')
        with open(resume_file, 'w', encoding='utf-8') as f:
            json.dump(data, f)

    def eval_pr_param(self, pr):
        """PR/ID can be a number, numberlist, script, jsonfile, or url"""
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
            numbers = json.loads(str(so))
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

    def load_meta(self, reponame: str, number: str) -> t.Dict[str, t.Any]:
        mfile = os.path.join(
            self.cachedir_base,
            reponame,
            'issues',
            number,
            'meta.json'
        )
        meta = {}
        try:
            with open(mfile, 'rb') as f:
                meta = json.load(f)
        except ValueError as e:
            logging.error("Could not load json from '%s' because: '%s'. Removing the file...", mfile, e)
            os.remove(mfile)
        except OSError:
            pass
        return meta

    def get_stale_numbers(self, reponame: str, issue_summaries: t.Dict[str, t.Dict[str, t.Any]]) -> t.List[int]:
        stale = []
        for summary in issue_summaries.values():
            number = summary['number']
            if number in stale:
                continue
            if summary['state'] == 'closed':
                continue

            if not (meta := self.load_meta(reponame, str(number))):
                stale.append(number)
                continue

            days_stale = (datetime.datetime.now() - strip_time_safely(meta['time'])).days
            if days_stale > C.DEFAULT_STALE_WINDOW:
                stale.append(number)

        stale = sorted(stale)
        if 10 >= len(stale) > 0:
            logging.info('stale: %s' % stale)

        return stale

    @RateLimited
    def _collect_repo(self, repo, issuenums=None):
        """Collect issues for an individual repo"""
        logging.info('getting repo obj for %s' % repo)
        repo_obj = RepoWrapper(self.ghw.gh, repo, cachedir=self.cachedir_base)

        if repo not in self.repos:
            gitrepo = GitRepoWrapper(
                cachedir=self.cachedir_base,
                repo=f'https://github.com/{repo}',
                commit=self.args.ansible_commit,
            )
            self.repos[repo] = {
                'repo': repo_obj,
                'issues': [],
                'since': None,
                'stale': [],
                'loopcount': 0,
                'labels': [l.name for l in repo_obj.labels],
                'gitrepo': gitrepo,
            }
        else:
            # force a clean repo object to limit caching problems
            logging.info('updating repo')
            self.repos[repo]['repo'] = repo_obj

            logging.info('updating checkout')
            self.repos[repo]['gitrepo'].update()

            # clear the issues
            self.repos[repo]['issues'] = {}
            # increment the loopcount
            self.repos[repo]['loopcount'] += 1

        logging.info('getting issue objs for %s' % repo)
        issue_summaries = {}
        if issuenums and len(issuenums) <= 10:
            for num in issuenums:
                for object_type in ('pullRequest', 'issue'):
                    node = self.gqlc.get_summary(repo, object_type, num)
                    if node is not None:
                        issue_summaries[str(num)] = node
                        break
        else:
            issue_summaries = self.gqlc.get_issue_summaries(repo)

        issuecache = {}
        numbers = [int(x) for x in issue_summaries.keys()]
        if issuenums:
            numbers = set(numbers)
            numbers.intersection_update(issuenums)
            numbers = list(numbers)
        logging.info('%s known numbers' % len(numbers))

        if self.args.daemonize:
            if not self.repos[repo]['since']:
                ts = [
                    x[1]['updated_at'] for x in
                    issue_summaries.items()
                    if x[1]['updated_at']
                ]
                ts += [
                    x[1]['created_at'] for x in
                    issue_summaries.items()
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
                    numbers.append(x.number)
                    issuecache[x.number] = x

                numbers = sorted({int(n) for n in numbers})
                logging.info(
                    '%s numbers after [api] since == %s' %
                    (len(numbers), since)
                )

                for k, v in issue_summaries.items():
                    if v['updated_at'] is None:
                        # issue is closed and was never processed
                        continue

                    if v['updated_at'] > self.repos[repo]['since']:
                        numbers.append(k)

                numbers = sorted({int(n) for n in numbers})
                logging.info(
                    '%s numbers after [www] since == %s' %
                    (len(numbers), since)
                )

        if self.args.start_at and self.repos[repo]['loopcount'] == 0:
            numbers = [x for x in numbers if x <= self.args.start_at]
            logging.info('%s numbers after start-at' % len(numbers))

        # Get stale numbers if not targeting
        if self.args.daemonize and self.repos[repo]['loopcount'] > 0:
            logging.info('checking for stale numbers')
            self.repos[repo]['stale'] = self.get_stale_numbers(repo, issue_summaries)
            numbers.extend(self.repos[repo]['stale'])
            numbers = sorted(set(numbers))
            logging.info('%s numbers after stale check' % len(numbers))

        ################################################################
        # PRE-FILTERING TO PREVENT EXCESSIVE API CALLS
        ################################################################

        if not self.args.ignore_state:
            issues_state = 'closed' if self.args.only_closed else 'open'
            numbers = [
                x for x in numbers
                if issue_summaries.get(str(x), {}).get('state') == issues_state
            ]
            logging.info('%s numbers after checking state' % len(numbers))

        if self.args.only_issues:
            numbers = [
                x for x in numbers
                if issue_summaries[str(x)]['type'] == 'issue'
            ]
            logging.info('%s numbers after checking type' % len(numbers))
        elif self.args.only_prs:
            numbers = [
                x for x in numbers
                if issue_summaries[str(x)]['type'] == 'pullrequest'
            ]
            logging.info('%s numbers after checking type' % len(numbers))

        numbers = sorted({int(x) for x in numbers})
        if self.args.sort == 'desc':
            numbers = [x for x in reversed(numbers)]

        if self.args.last and len(numbers) > self.args.last:
            numbers = numbers[0 - self.args.last:]

        self.repos[repo]['numbers'] = numbers
        self.repos[repo]['issuecache'] = issuecache
        self.repos[repo]['summaries'] = issue_summaries

        logging.info('getting repo objs for %s complete' % repo)

    def collect_repos(self):
        """Populate the local cache of repos"""
        logging.info('start collecting repos')
        for repo in C.DEFAULT_GITHUB_REPOS:
            # skip repos based on args
            if self.args.repo and self.args.repo != repo:
                continue
            if self.args.skiprepo:
                if repo in self.args.skiprepo:
                    continue

            if self.args.pr:
                numbers = self.eval_pr_param(self.args.pr)
                self._collect_repo(repo, issuenums=numbers)
            else:
                self._collect_repo(repo)
        logging.info('finished collecting issues')
