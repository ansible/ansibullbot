#!/usr/bin/python
#
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

from __future__ import print_function

import ConfigParser
import abc
import json
import logging
import os
import sys
import time
import pickle
from datetime import datetime

# remember to pip install PyGithub, kids!
from github import Github

from jinja2 import Environment, FileSystemLoader

from ansibullbot.decorators.github import RateLimited
from ansibullbot.wrappers.ghapiwrapper import GithubWrapper
from ansibullbot.wrappers.issuewrapper import IssueWrapper
from ansibullbot.utils.descriptionfixer import DescriptionFixer

basepath = os.path.dirname(__file__).split('/')
libindex = basepath[::-1].index('ansibullbot')
libindex = (len(basepath) - 1) - libindex
basepath = '/'.join(basepath[0:libindex])
loader = FileSystemLoader(os.path.join(basepath, 'templates'))
environment = Environment(loader=loader, trim_blocks=True)

BOTLIST = None


class DefaultActions(object):
    def __init__(self):
        self.newlabel = []
        self.unlabel = []
        self.comments = []
        self.assign = []
        self.unassign = []
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


class DefaultTriager(object):

    ITERATION = 0

    def __init__(self, args):

        self.args = args
        self.last_run = None
        self.daemonize = None
        self.daemonize_interval = None
        self.dry_run = False
        self.force = False

        self.configfile = self.args.configfile
        self.config = ConfigParser.ConfigParser()
        self.config.read([self.configfile])

        try:
            self.github_user = self.config.get('defaults', 'github_username')
        except:
            self.github_user = None

        try:
            self.github_pass = self.config.get('defaults', 'github_password')
        except:
            self.github_pass = None

        try:
            self.github_token = self.config.get('defaults', 'github_token')
        except:
            self.github_token = None

        self.repopath = self.args.repo
        self.logfile = self.args.logfile

        # where to store junk
        self.cachedir = self.args.cachedir
        self.cachedir = os.path.expanduser(self.cachedir)
        self.cachedir_base = self.cachedir

        self.set_logger()
        logging.info('starting bot')

        logging.debug('setting bot attributes')
        for x in vars(self.args):
            val = getattr(self.args, x)
            setattr(self, x, val)

        if hasattr(self.args, 'pause') and self.args.pause:
            self.always_pause = True

        # connect to github
        logging.info('creating api connection')
        self.gh = self._connect()

        # wrap the connection
        logging.info('creating api wrapper')
        self.ghw = GithubWrapper(self.gh, cachedir=self.cachedir)

        # get valid labels
        logging.info('getting labels')
        self.valid_labels = self.get_valid_labels(self.repopath)

    @property
    def resume(self):
        '''Returns a dict with the last issue repo+number processed'''
        if not hasattr(self, 'args'):
            return None
        if hasattr(self.args, 'pr') and self.args.pr:
            return None
        if not hasattr(self.args, 'resume'):
            return None
        if not self.args.resume:
            return None

        if hasattr(self, 'cachedir_base'):
            resume_file = os.path.join(self.cachedir_base, 'resume.json')
        else:
            resume_file = os.path.join(self.cachedir, 'resume.json')
        if not os.path.isfile(resume_file):
            return None

        with open(resume_file, 'rb') as f:
            data = json.loads(f.read())
        return data

    def set_resume(self, repo, number):
        if not hasattr(self, 'args'):
            return None
        if hasattr(self.args, 'pr') and self.args.pr:
            return None
        if not hasattr(self.args, 'resume'):
            return None
        if not self.args.resume:
            return None

        data = {
            'repo': repo,
            'number': number
        }
        if hasattr(self, 'cachedir_base'):
            resume_file = os.path.join(self.cachedir_base, 'resume.json')
        else:
            resume_file = os.path.join(self.cachedir, 'resume.json')
        with open(resume_file, 'wb') as f:
            f.write(json.dumps(data, indent=2))

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

        logdir = os.path.dirname(logfile)
        if logdir and not os.path.isdir(logdir):
            os.makedirs(logdir)

        fileHandler = logging.FileHandler(logfile)
        fileHandler.setFormatter(logFormatter)
        rootLogger.addHandler(fileHandler)
        consoleHandler = logging.StreamHandler()
        consoleHandler.setFormatter(logFormatter)
        rootLogger.addHandler(consoleHandler)

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

    @RateLimited
    def _connect(self):
        """Connects to GitHub's API"""
        if self.github_token:
            return Github(login_or_token=self.github_token)
        else:
            return Github(
                login_or_token=self.github_user,
                password=self.github_pass
            )

    @abc.abstractmethod
    def _get_repo_path(self):
        pass

    def is_pr(self, issue):
        if '/pull/' in issue.html_url:
            return True
        else:
            return False

    def is_issue(self, issue):
        return not self.is_pr(issue)

    @RateLimited
    def get_members(self, organization):
        """Get members of an organization

        Args:
            organization: name of the organization

        Returns:
            A list of GitHub login belonging to the organization
        """
        members = []
        update = False
        write_cache = False
        now = self.get_current_time()
        gh_org = self._connect().get_organization(organization)

        cachedir = self.cachedir
        if cachedir.endswith('/issues'):
            cachedir = os.path.dirname(cachedir)
        cachefile = os.path.join(cachedir, 'members.pickle')

        if not os.path.isdir(cachedir):
            os.makedirs(cachedir)

        if os.path.isfile(cachefile):
            with open(cachefile, 'rb') as f:
                mdata = pickle.load(f)
            members = mdata[1]
            if mdata[0] < gh_org.updated_at:
                update = True
        else:
            update = True
            write_cache = True

        if update:
            members = gh_org.get_members()
            members = [x.login for x in members]

        # save the data
        if write_cache:
            mdata = [now, members]
            with open(cachefile, 'wb') as f:
                pickle.dump(mdata, f)

        return members

    @RateLimited
    def get_core_team(self, organization, teams):
        """Get members of the core team

        Args:
            organization: name of the teams' organization
            teams: list of teams that compose the project core team

        Returns:
            A list of GitHub login belonging to teams
        """
        members = set()

        conn = self._connect()
        gh_org = conn.get_organization(organization)
        for team in gh_org.get_teams():
            if team.name in teams:
                for member in team.get_members():
                    members.add(member.login)

        return sorted(members)

    #@RateLimited
    def get_valid_labels(self, repo=None):

        # use the repo wrapper to enable caching+updating
        if not self.ghw:
            self.gh = self._connect()
            self.ghw = GithubWrapper(self.gh)

        if not repo:
            # OLD workflow
            self.repo = self.ghw.get_repo(self._get_repo_path())
            vlabels = []
            for vl in self.repo.get_labels():
                vlabels.append(vl.name)
        else:
            # v3 workflow
            rw = self.ghw.get_repo(repo)
            vlabels = []
            for vl in rw.get_labels():
                vlabels.append(vl.name)

        return vlabels

    def debug(self, msg=""):
        """Prints debug message if verbosity is given"""
        if self.verbose:
            print("Debug: " + msg)

    def loop(self):
        '''Call the run method in a defined interval'''
        while True:
            self.run()
            self.ITERATION += 1
            interval = self.args.daemonize_interval
            logging.info('sleep %ss (%sm)' % (interval, interval / 60))
            time.sleep(interval)

    @abc.abstractmethod
    def run(self):
        pass

    def get_current_time(self):
        return datetime.utcnow()

    def render_boilerplate(self, tvars, boilerplate=None):
        template = environment.get_template('%s.j2' % boilerplate)
        comment = template.render(**tvars)
        return comment

    def check_safe_match(self, iw, actions):
        """ Turn force on or off depending on match characteristics """
        safe_match = False

        if actions.count() == 0:
            safe_match = True

        elif not actions.close and not actions.unlabel:
            if len(actions.newlabel) == 1:
                if actions.newlabel[0].startswith('affects_'):
                    safe_match = True

        else:
            safe_match = False
            if self.module:
                if self.module in iw.instance.title.lower():
                    safe_match = True

        # be more lenient on re-notifications
        if not safe_match:
            if not actions.close and \
                    not actions.unlabel and \
                    not actions.newlabel:

                if len(actions.comments) == 1:
                    if 'still waiting' in actions.comments[0]:
                        safe_match = True

        if safe_match:
            self.force = True
        else:
            self.force = False

    def apply_actions(self, iw, actions):

        action_meta = {'REDO': False}

        if hasattr(self, 'safe_force') and self.safe_force:
            self.check_safe_match(iw, actions)

        if actions.count() > 0:

            if hasattr(self, 'args'):
                if hasattr(self.args, 'dump_actions'):
                    if self.args.dump_actions:
                        self.dump_action_dict(iw, actions)

            if self.dry_run:
                print("Dry-run specified, skipping execution of actions")
            else:
                if self.force:
                    print("Running actions non-interactive as you forced.")
                    self.execute_actions(iw, actions)
                    return action_meta
                cont = raw_input("Take recommended actions (y/N/a/R/T/DEBUG)? ")
                if cont in ('a', 'A'):
                    sys.exit(0)
                if cont in ('Y', 'y'):
                    self.execute_actions(iw, actions)
                if cont == 'T':
                    self.template_wizard(iw)
                    action_meta['REDO'] = True
                if cont == 'r' or cont == 'R':
                    action_meta['REDO'] = True
                if cont == 'DEBUG':
                    # put the user into a breakpoint to do live debug
                    action_meta['REDO'] = True
                    import epdb; epdb.st()
        elif self.always_pause:
            print("Skipping, but pause.")
            cont = raw_input("Continue (Y/n/a/R/T/DEBUG)? ")
            if cont in ('a', 'A', 'n', 'N'):
                sys.exit(0)
            if cont == 'T':
                self.template_wizard(iw)
                action_meta['REDO'] = True
            elif cont == 'REDO':
                action_meta['REDO'] = True
            elif cont == 'DEBUG':
                # put the user into a breakpoint to do live debug
                import epdb; epdb.st()
                action_meta['REDO'] = True
        elif hasattr(self, 'force_description_fixer') and self.args.force_description_fixer:
            if iw.html_url not in self.FIXED_ISSUES:
                if self.meta['template_missing_sections']:
                    changed = self.template_wizard(iw)
                    if changed:
                        action_meta['REDO'] = True
                self.FIXED_ISSUES.append(iw.html_url)
        else:
            print("Skipping.")

        # let the upper level code redo this issue
        return action_meta

    def template_wizard(self, iw):

        DF = DescriptionFixer(iw, self.meta)

        old = iw.body
        old_lines = old.split('\n')
        new = DF.new_description
        new_lines = new.split('\n')

        total_lines = len(new_lines)
        if len(old_lines) > total_lines:
            total_lines = len(old_lines)

        if len(new_lines) < total_lines:
            delta = total_lines - len(new_lines)
            for x in xrange(0, delta):
                new_lines.append('')

        if len(old_lines) < total_lines:
            delta = total_lines - len(old_lines)
            for x in xrange(0, delta):
                old_lines.append('')

        line = '--------------------------------------------------------'
        padding = 100
        print("%s|%s" % (line.ljust(padding), line))
        for c1, c2 in zip(old_lines, new_lines):
            if len(c1) > padding:
                c1 = c1[:padding-4]
            if len(c2) > padding:
                c2 = c2[:padding-4]
            print("%s|%s" % (c1.rstrip().ljust(padding), c2.rstrip()))
        print("%s|%s" % (line.rstrip().ljust(padding), line))

        print('# ' + iw.html_url)
        cont = raw_input("Apply this new description? (Y/N) ")
        if cont == 'Y':
            iw.set_description(DF.new_description)
            return True
        else:
            return False

    def execute_actions(self, iw, actions):
        """Turns the actions into API calls"""

        for comment in actions.comments:
            logging.info("acton: comment - " + comment)
            iw.add_comment(comment=comment)
        if actions.close:
            # https://github.com/PyGithub/PyGithub/blob/master/github/Issue.py#L263
            logging.info('action: close')
            iw.instance.edit(state='closed')
            return

        if actions.close_migrated:
            mi = self.get_issue_by_repopath_and_number(
                self.meta['migrated_issue_repo_path'],
                self.meta['migrated_issue_number']
            )
            logging.info('close migrated: %s' % mi.html_url)
            mi.instance.edit(state='closed')

        for unlabel in actions.unlabel:
            logging.info('action: unlabel - ' + unlabel)
            iw.remove_label(label=unlabel)
        for newlabel in actions.newlabel:
            logging.info('action: label - ' + newlabel)
            iw.add_label(label=newlabel)

        if 'assign' in actions:
            for user in actions.assign:
                logging.info('action: assign - ' + user)
                iw.assign_user(user)
        if 'unassign' in actions:
            for user in actions.unassign:
                logging.info('action: unassign - ' + user)
                iw.unassign_user(user)

        if 'merge' in actions:
            if actions.merge:
                iw.merge()

        if 'rebuild' in actions:
            if actions.rebuild:
                runid = self.meta.get('rebuild_run_number')
                if runid:
                    self.SR.rebuild(runid)
                else:
                    logging.error(
                        'no shippable runid for {}'.format(iw.number)
                    )

    @RateLimited
    def is_pr_merged(self, number, repo=None):
        '''Check if a PR# has been merged or not'''
        merged = False
        pr = None
        try:
            if not repo:
                pr = self.repo.get_pullrequest(number)
            else:
                pr = repo.get_pullrequest(number)
        except Exception as e:
            print(e)
        if pr:
            merged = pr.merged
        return merged

    def wrap_issue(self, github, repo, issue, header=None):
        iw = IssueWrapper(
            github=github,
            repo=repo,
            issue=issue,
            cachedir=self.cachedir
        )
        if header:
            iw.TEMPLATE_HEADER=header
        if self.file_indexer:
            iw.file_indexer = self.file_indexer
        return iw

    def dump_action_dict(self, issue, actions):
        '''Serialize the action dict to disk for quick(er) debugging'''
        fn = os.path.join('/tmp', 'actions', issue.repo_full_name, str(issue.number) + '.json')
        dn = os.path.dirname(fn)
        if not os.path.isdir(dn):
            os.makedirs(dn)

        logging.info('dumping {}'.format(fn))
        with open(fn, 'wb') as f:
            f.write(json.dumps(actions, indent=2, sort_keys=True))
