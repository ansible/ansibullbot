#!/usr/bin/env python

import logging
import os
import shutil
from ansibullbot.utils.systemtools import run_command


class GitRepoWrapper(object):

    _files = []

    def __init__(self, cachedir, repo):
        self.repo = repo
        self.checkoutdir = cachedir or '~/.ansibullbot/cache'
        self.checkoutdir = os.path.join(cachedir, 'ansible.git.checkout')
        self.checkoutdir = os.path.expanduser(self.checkoutdir)
        self.commits_by_email = None
        self.files_by_commit = {}

    @property
    def files(self):
        self.get_files()
        return self._files

    @property
    def module_files(self):
        return [x for x in self._files if x.startswith('lib/ansible/modules')]

    def create_checkout(self):
        """checkout ansible"""
        # cleanup
        if os.path.isdir(self.checkoutdir):
            shutil.rmtree(self.checkoutdir)
        cmd = "git clone %s %s" \
            % (self.repo, self.checkoutdir)
        (rc, so, se) = run_command(cmd)
        print(str(so) + str(se))

    def update(self, force=False):
        '''Reload everything if there are new commits'''
        changed = self.manage_checkout()
        if changed or force:
            self.get_files(force=True)
        self.commits_by_email = None

    def update_checkout(self):
        """rebase + pull + update the checkout"""

        changed = False

        cmd = "cd %s ; git pull --rebase" % self.checkoutdir
        (rc, so, se) = run_command(cmd)
        print(str(so) + str(se))

        # If rebase failed, recreate the checkout
        if rc != 0:
            self.create_checkout()
            return True
        else:
            if 'current branch devel is up to date.' not in so.lower():
                changed = True

        self.commits_by_email = None

        return changed

    def manage_checkout(self):
        '''Check if there are any changes to the repo'''
        changed = False
        if not os.path.isdir(self.checkoutdir):
            self.create_checkout()
            changed = True
        else:
            changed = self.update_checkout()
        return changed

    def get_files(self, force=False):
        '''Cache a list of filenames in the checkout'''
        if not self._files or force:
            cmd = 'cd {}; git ls-files'.format(self.checkoutdir)
            logging.debug(cmd)
            (rc, so, se) = run_command(cmd)
            files = so.split('\n')
            files = [x.strip() for x in files if x.strip()]
            self._files = files

    def get_file_content(self, filepath):
        fpath = os.path.join(self.checkoutdir, filepath)
        if not os.path.isfile(fpath):
            return None
        with open(fpath, 'rb') as f:
            data = f.read()
        return data

    def get_files_by_commit(self, commit):

        if commit not in self.files_by_commit:
            cmd = 'cd {}; git show --pretty="" --name-only {}'.format(self.checkoutdir, commit)
            (rc, so, se) = run_command(cmd)
            filenames = [x.strip() for x in so.split('\n') if x.strip()]
            self.files_by_commit[commit] = filenames[:]
        else:
            filenames = self.files_by_commit[commit]

        return filenames

    def get_commits_by_email(self, email):
        '''Map an email(s) to a total num of commits and total by file'''
        if self.commits_by_email is None:
            commits = {}
            cmd = 'cd {}; git log --format="%h;%ae"'.format(self.checkoutdir)
            (rc, so, se) = run_command(cmd)
            lines = [x.strip() for x in so.split('\n') if x.strip()]
            for line in lines:
                parts = line.split(';')
                this_hash = parts[0]
                this_email = parts[1]
                if this_email not in commits:
                    commits[this_email] = set()
                commits[this_email].add(this_hash)
            self.commits_by_email = commits

        if not isinstance(email, (set, list)):
            emails = [email]
        else:
            emails = [x for x in email]

        email_map = {}

        for _email in emails:
            if _email not in email_map:
                email_map[_email] = {
                    'commit_count': 0,
                    'commit_count_byfile': {}
                }

            if _email in self.commits_by_email:

                email_map[_email]['commit_count'] = \
                    len(self.commits_by_email[_email])

                for _commit in self.commits_by_email[_email]:
                    filenames = self.get_files_by_commit(_commit)
                    for fn in filenames:
                        if fn not in email_map[_email]['commit_count_byfile']:
                            email_map[_email]['commit_count_byfile'][fn] = 0
                        email_map[_email]['commit_count_byfile'][fn] += 1

        return email_map
