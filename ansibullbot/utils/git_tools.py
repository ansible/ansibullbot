#!/usr/bin/env python

import io
import logging
import os
import shutil

from ansibullbot._text_compat import to_text
from ansibullbot.utils.systemtools import run_command


class GitRepoWrapper(object):

    checkoutdir = None
    _files = []

    def __init__(self, cachedir, repo, commit=None, rebase=True):
        self._needs_rebase = rebase
        self.repo = repo
        self.commit = commit

        # allow for null repos
        if repo:
            urlparts = repo.split('/')
            urlparts = [x for x in urlparts if x and 'http' not in x]
            path_parts = list([cachedir] + urlparts)
            self.checkoutdir = os.path.join(*path_parts)
            parent = os.path.dirname(self.checkoutdir)
            if not os.path.exists(parent):
                os.makedirs(parent)

        '''
        self.checkoutdir = cachedir or u'~/.ansibullbot/cache'
        self.checkoutdir = os.path.join(cachedir, subdir)
        self.checkoutdir = os.path.expanduser(self.checkoutdir)
        '''

        self.commits_by_email = None
        self.files_by_commit = {}
        if repo:
            self.update(force=True)

    def exists(self, filename, loose=False):
        if self.checkoutdir is None:
            return False
        checkfile = os.path.join(self.checkoutdir, filename)
        if os.path.exists(checkfile):
            return True
        if not loose:
            return False

        for x in self._files:
            if x.endswith(filename):
                return True

        return False

    def isdir(self, filename):
        checkfile = os.path.join(self.checkoutdir, filename)
        return os.path.isdir(checkfile)

    def islink(self, filename):
        checkfile = os.path.join(self.checkoutdir, filename)
        return os.path.islink(checkfile)

    @property
    def files(self):
        self.get_files()
        return self._files

    @property
    def module_files(self):
        return [x for x in self._files if x.startswith(u'lib/ansible/modules')]

    def create_checkout(self):
        """checkout ansible"""
        # cleanup
        if os.path.isdir(self.checkoutdir):
            shutil.rmtree(self.checkoutdir)
        cmd = "git clone %s %s" \
            % (self.repo, self.checkoutdir)
        #if self.commit:
        #    import epdb; epdb.st()
        logging.debug(cmd)
        (rc, so, se) = run_command(cmd, env={'GIT_TERMINAL_PROMPT': 0, 'GIT_ASKPASS': '/bin/echo'})
        print(to_text(so) + to_text(se))

    def update(self, force=False):
        '''Reload everything if there are new commits'''
        changed = self.manage_checkout()
        if changed or force:
            self.get_files(force=True)
        self.commits_by_email = None

    def update_checkout(self):
        """rebase + pull + update the checkout"""

        changed = False

        # get a specific commit or do a rebase
        if self.commit:
            cmd = "cd %s; git log -1  | head -n1 | awk '{print $2}'" % self.checkoutdir
            (rc, so, se) = run_command(cmd)
            so = to_text(so).strip()

            if so != self.commit:
                cmd = "cd %s; git checkout %s" % (self.checkoutdir, self.commit)
                logging.debug(cmd)
                (rc, so, se) = run_command(cmd, env={'GIT_TERMINAL_PROMPT': 0, 'GIT_ASKPASS': '/bin/echo'})
                changed = True

            if rc != 0:
                self.create_checkout()
                changed = True

        else:
            changed = False

            cmd = "cd %s ; git pull --rebase" % self.checkoutdir
            logging.debug(cmd)
            (rc, so, se) = run_command(cmd, env={'GIT_TERMINAL_PROMPT': 0, 'GIT_ASKPASS': '/bin/echo'})
            so = to_text(so)
            print(so + to_text(se))

            # If rebase failed, recreate the checkout
            if rc != 0:
                self.create_checkout()
                return True
            else:
                if u'current branch devel is up to date.' not in so.lower():
                    changed = True

        self.commits_by_email = None

        return changed

    def manage_checkout(self):
        '''Check if there are any changes to the repo'''
        changed = False
        if not os.path.isdir(self.checkoutdir):
            self.create_checkout()
            changed = True
        elif self._needs_rebase:
            changed = self.update_checkout()
        return changed

    def get_files(self, force=False):
        '''Cache a list of filenames in the checkout'''
        if not self._files or force:
            cmd = u'cd {}; git ls-files'.format(self.checkoutdir)
            logging.debug(cmd)
            (rc, so, se) = run_command(cmd)
            files = to_text(so).split(u'\n')
            files = [x.strip() for x in files if x.strip()]
            self._files = files

    def get_files_by_commit(self, commit):

        if commit not in self.files_by_commit:
            cmd = u'cd {}; git show --pretty="" --name-only {}'.format(self.checkoutdir, commit)
            (rc, so, se) = run_command(cmd)
            filenames = [x.strip() for x in to_text(so).split(u'\n') if x.strip()]
            self.files_by_commit[commit] = filenames[:]
        else:
            filenames = self.files_by_commit[commit]

        return filenames

    def get_commits_by_email(self, email):
        '''Map an email(s) to a total num of commits and total by file'''
        if self.commits_by_email is None:
            commits = {}
            cmd = u'cd {}; git log --format="%h;%ae"'.format(self.checkoutdir)
            (rc, so, se) = run_command(cmd)
            lines = [x.strip() for x in to_text(so).split(u'\n') if x.strip()]
            for line in lines:
                parts = line.split(u';')
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
                    u'commit_count': 0,
                    u'commit_count_byfile': {}
                }

            if _email in self.commits_by_email:

                email_map[_email][u'commit_count'] = \
                    len(self.commits_by_email[_email])

                for _commit in self.commits_by_email[_email]:
                    filenames = self.get_files_by_commit(_commit)
                    for fn in filenames:
                        if fn not in email_map[_email][u'commit_count_byfile']:
                            email_map[_email][u'commit_count_byfile'][fn] = 0
                        email_map[_email][u'commit_count_byfile'][fn] += 1

        return email_map

    def existed(self, filepath):
        '''Did a file ever exist in this repo?'''

        cmd = 'cd %s; git rev-list --max-count=1 --all -- %s' % (self.checkoutdir, filepath)
        logging.info(cmd)
        (rc, so, se) = run_command(cmd)
        lrev = so.strip().decode('utf-8')

        if rc == 0 and lrev:
            return True

        return False

    def get_file_content(self, filepath, follow=False):

        fp = os.path.join(self.checkoutdir, filepath)
        if os.path.exists(fp):
            with io.open(fp, 'r', encoding='utf-8') as f:
                data = f.read()
            return data

        if not follow:
            return None

        # https://stackoverflow.com/a/1395463
        #cmd = 'cd %s; git show HEAD^:%s' % (self.checkoutdir, filepath)

        # https://stackoverflow.com/a/19727752
        cmd = 'cd %s; git rev-list --max-count=1 --all -- %s' % (self.checkoutdir, filepath)
        logging.info(cmd)
        (rc, so, se) = run_command(cmd)
        lrev = so.strip().decode('utf-8')
        cmd = 'cd %s; git show %s^:%s' % (self.checkoutdir, lrev, filepath)
        (rc, so, se) = run_command(cmd)
        logging.info(cmd)
        #so = so.decode('utf-8').strip()
        so = so.strip()
        if so.decode('utf-8').endswith('.py'):
            newpath = os.path.dirname(filepath)
            newpath = os.path.join(newpath, so.decode('utf-8'))

            cmd = 'cd %s; git rev-list --max-count=1 --all -- %s' % (self.checkoutdir, newpath)
            logging.info(cmd)
            (rc, so, se) = run_command(cmd)
            lrev = so.strip().decode('utf-8')
            cmd = 'cd %s; git show %s^:%s' % (self.checkoutdir, lrev, newpath)
            logging.info(cmd)
            (rc, so, se) = run_command(cmd)
            #so = so.decode('utf-8').strip()
            so = so.strip()

        return so
