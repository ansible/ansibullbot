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

import requests
from jinja2 import Environment, FileSystemLoader

from ansibullbot import constants as C
from ansibullbot._text_compat import to_text
from ansibullbot.decorators.github import RateLimited
from ansibullbot.utils.gh_gql_client import GithubGraphQLClient
from ansibullbot.utils.git_tools import GitRepoWrapper
from ansibullbot.utils.iterators import RepoIssuesIterator
from ansibullbot.utils.logs import set_logger
from ansibullbot.utils.systemtools import run_command
from ansibullbot.utils.timetools import strip_time_safely
from ansibullbot.wrappers.ghapiwrapper import GithubWrapper

basepath = os.path.dirname(__file__).split('/')
libindex = basepath[::-1].index('ansibullbot')
libindex = (len(basepath) - 1) - libindex
basepath = '/'.join(basepath[0:libindex])
loader = FileSystemLoader(os.path.join(basepath, 'templates'))
environment = Environment(loader=loader, trim_blocks=True)


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

        logging.info('starting bot')
        self.set_logger()

        self.cachedir_base = os.path.expanduser(self.args.cachedir_base)
        self.issue_summaries = {}
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
        parser.add_argument("--logfile", type=str, default='/var/log/ansibullbot.log', help="Send logging to this file")
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

    def set_logger(self):
        set_logger(debug=self.args.debug, logfile=self.args.logfile)

    def start(self):
        if self.args.daemonize:
            logging.info('starting daemonize loop')
            self.loop()
        else:
            logging.info('starting single run')
            self.run()
        logging.info('stopping bot')

    def loop(self):
        """Call the run method in a defined interval"""
        while True:
            self.run()
            interval = self.args.daemonize_interval
            logging.info('sleep %ss (%sm)' % (interval, interval / 60))
            time.sleep(interval)

    @abc.abstractmethod
    def run(self):
        pass

    def render_boilerplate(self, tvars, boilerplate=None):
        template = environment.get_template('%s.j2' % boilerplate)
        comment = template.render(**tvars)
        return comment

    def apply_actions(self, iw, actions):
        action_meta = {'REDO': False}

        if actions.count() > 0:
            if self.args.dump_actions:
                self.dump_action_dict(iw, actions)

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
        '''Returns a dict with the last issue repo+number processed'''
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

    def get_stale_numbers(self, reponame):
        stale = []
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
                stale.append(number)
                continue

            try:
                with open(mfile, 'rb') as f:
                    meta = json.load(f)
            except ValueError as e:
                logging.error('failed to parse %s: %s' % (to_text(mfile), to_text(e)))
                os.remove(mfile)
                stale.append(number)
                continue

            delta = (datetime.datetime.now() - strip_time_safely(meta['time'])).days
            if delta > C.DEFAULT_STALE_WINDOW:
                stale.append(number)

        stale = sorted({int(x) for x in stale})
        if 10 >= len(stale) > 0:
            logging.info('stale: %s' % ','.join([to_text(x) for x in stale]))

        return stale

    @RateLimited
    def _collect_repo(self, repo, issuenums=None):
        '''Collect issues for an individual repo'''
        logging.info('getting repo obj for %s' % repo)
        if repo not in self.repos:
            gitrepo = GitRepoWrapper(
                cachedir=self.cachedir_base,
                repo=f'https://github.com/{repo}',
                commit=self.args.ansible_commit,
            )
            self.repos[repo] = {
                'repo': self.ghw.get_repo(repo),
                'issues': [],
                'processed': [],
                'since': None,
                'stale': [],
                'loopcount': 0,
                'labels': self.ghw.get_valid_labels(repo),
                'gitrepo': gitrepo,
            }
        else:
            # force a clean repo object to limit caching problems
            logging.info('updating repo')
            self.repos[repo]['repo'] = self.ghw.get_repo(repo)
            logging.info('updating checkout')
            self.repos[repo]['gitrepo'].update()

            # clear the issues
            self.repos[repo]['issues'] = {}
            # increment the loopcount
            self.repos[repo]['loopcount'] += 1

        logging.info('getting issue objs for %s' % repo)
        self.update_issue_summaries(repopath=repo, issuenums=issuenums)

        issuecache = {}
        numbers = self.issue_summaries[repo].keys()
        numbers = {int(x) for x in numbers}
        if issuenums:
            numbers.intersection_update(issuenums)
            numbers = list(numbers)
        logging.info('%s known numbers' % len(numbers))

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

        if self.args.start_at and self.repos[repo]['loopcount'] == 0:
            numbers = [x for x in numbers if x <= self.args.start_at]
            logging.info('%s numbers after start-at' % len(numbers))

        # Get stale numbers if not targeting
        if self.args.daemonize and self.repos[repo]['loopcount'] > 0:
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
        if not self.args.only_closed and not self.args.ignore_state:
            numbers = [
                x for x in numbers
                if (to_text(x) in self.issue_summaries[repo] and
                self.issue_summaries[repo][to_text(x)]['state'] == 'open')
            ]
            logging.info('%s numbers after checking state' % len(numbers))

        # filter by type
        if self.args.only_issues:
            numbers = [
                x for x in numbers
                if self.issue_summaries[repo][to_text(x)]['type'] == 'issue'
            ]
            logging.info('%s numbers after checking type' % len(numbers))
        elif self.args.only_prs:
            numbers = [
                x for x in numbers
                if self.issue_summaries[repo][to_text(x)]['type'] == 'pullrequest'
            ]
            logging.info('%s numbers after checking type' % len(numbers))

        numbers = sorted({int(x) for x in numbers})
        if self.args.sort == 'desc':
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

    def collect_repos(self):
        '''Populate the local cache of repos'''
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
