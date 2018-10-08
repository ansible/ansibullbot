#!/usr/bin/env python

import Levenshtein
import ast
import copy
import datetime
import fnmatch
import io
import logging
import os
import pickle
import re
import yaml

import six

from sqlalchemy import create_engine
from sqlalchemy import Column
from sqlalchemy import Integer
from sqlalchemy import String
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

from ansibullbot._text_compat import to_bytes, to_text
from ansibullbot.parsers.botmetadata import BotMetadataParser, BotYAMLLoader
from ansibullbot.utils.git_tools import GitRepoWrapper
from ansibullbot.utils.systemtools import run_command
from ansibullbot.utils.webscraper import GithubWebScraper

import ansibullbot.constants as C


Base = declarative_base()


class Blame(Base):
    __tablename__ = u'blames'
    id = Column(Integer(), primary_key=True)
    file_name = Column(String())
    file_commit = Column(String())
    author_commit = Column(String())
    author_login = Column(String())


class Email(Base):
    __tablename__ = u'email'
    id = Column(Integer())
    login = Column(String())
    email = Column(String(), primary_key=True)


class ModuleIndexer(object):

    EMPTY_MODULE = {
        u'authors': [],
        u'name': None,
        u'namespaced_module': None,
        u'namespace_maintainers': [],
        u'deprecated': False,
        u'deprecated_filename': None,
        u'dirpath': None,
        u'filename': None,
        u'filepath': None,
        u'fulltopic': None,
        u'maintainers': [],
        u'_maintainers': [],
        u'maintainers_keys': None,
        u'metadata': {},
        u'repo_filename': None,
        u'repository': u'ansible',
        u'subtopic': None,
        u'topic': None,
        u'imports': []
    }

    def __init__(self, commits=True, blames=True, botmetafile=None, maintainers=None, gh_client=None, cachedir=u'~/.ansibullbot/cache', gitrepo=None):
        '''
        Maintainers: defaultdict(dict) where keys are filepath and values are dict
        gh_client: GraphQL GitHub client
        '''
        self.get_commits = commits
        self.get_blames = blames
        self.botmetafile = botmetafile
        self.botmeta = {}  # BOTMETA.yml file with minor updates (macro rendered, empty default values fixed)
        self.modules = {}  # keys: paths of files belonging to the repository
        self.maintainers = maintainers or {}
        self.importmap = {}
        self.scraper_cache = os.path.join(cachedir, u'ansible.modules.scraper')
        self.scraper_cache = os.path.expanduser(self.scraper_cache)
        self.gws = GithubWebScraper(cachedir=self.scraper_cache)
        self.gqlc = gh_client
        self.files = []

        if gitrepo:
            self.gitrepo = gitrepo
        else:
            self.gitrepo = GitRepoWrapper(cachedir=cachedir, repo=u'https://github.com/ansible/ansible')

        # sqlalchemy
        unc = os.path.join(cachedir, u'ansible_module_indexer.db')
        unc = os.path.expanduser(unc)
        unc = u'sqlite:///' + unc

        self.engine = create_engine(unc)
        self.Session = sessionmaker(bind=self.engine)
        self.session = self.Session()

        Email.metadata.create_all(self.engine)
        Blame.metadata.create_all(self.engine)

        # committers by module
        self.committers = {}
        # commits by module
        self.commits = {}
        # map of email to github login
        self.emails_cache = {}

        # load the bot meta
        self.update(force=True)

    def update(self, force=False):
        '''Reload everything if there are new commits'''
        changed = self.gitrepo.manage_checkout()
        if changed or force:
            self.get_files()
            self.parse_metadata()

    def get_files(self):
        '''Cache a list of filenames in the checkout'''
        cmd = u'cd {}; git ls-files'.format(self.gitrepo.checkoutdir)
        (rc, so, se) = run_command(cmd)
        files = to_text(so).split(u'\n')
        files = [x.strip() for x in files if x.strip()]
        self.files = files

    def parse_metadata(self):

        if self.botmetafile is not None:
            with open(self.botmetafile, 'rb') as f:
                rdata = f.read()
        else:
            fp = u'.github/BOTMETA.yml'
            rdata = self.get_file_content(fp)
        self.botmeta = BotMetadataParser.parse_yaml(rdata)

        # load the modules
        logging.info(u'loading modules')
        self.get_ansible_modules()

    def _find_match(self, pattern, exact=False):

        logging.debug(u'exact:{} matching on {}'.format(exact, pattern))

        matches = []

        if isinstance(pattern, six.text_type):
            pattern = to_text(to_bytes(pattern,'ascii', 'ignore'), 'ascii')

        for k, v in six.iteritems(self.modules):
            if v[u'name'] == pattern:
                logging.debug(u'match {} on name: {}'.format(k, v[u'name']))
                matches = [v]
                break

        if not matches:
            # search by key ... aka the filepath
            for k, v in six.iteritems(self.modules):
                if k == pattern:
                    logging.debug(u'match {} on key: {}'.format(k, k))
                    matches = [v]
                    break

        if not matches and not exact:
            # search by properties
            for k, v in six.iteritems(self.modules):
                for subkey in v.keys():
                    if v[subkey] == pattern:
                        logging.debug(u'match {} on subkey: {}'.format(k, subkey))
                        matches.append(v)

        if not matches and not exact:
            # Levenshtein distance should workaround most typos
            distance_map = {}
            for k, v in six.iteritems(self.modules):
                mname = v.get(u'name')
                if not mname:
                    continue
                if isinstance(mname, six.text_type):
                    mname = to_text(to_bytes(mname, 'ascii', 'ignore'), 'ascii')
                try:
                    res = Levenshtein.distance(pattern, mname)
                except TypeError as e:
                    logging.error(e)
                    if C.DEFAULT_BREAKPOINTS:
                        logging.error(u'breakpoint!')
                        import epdb; epdb.st()
                distance_map[mname] = [res, k]
            res = sorted(distance_map.items(), key=lambda x: x[1], reverse=True)
            if len(pattern) > 3 > res[-1][1]:
                logging.debug(u'levenshtein ratio match: ({}) {} {}'.format(res[-1][-1], res[-1][0], pattern))
                matches = [self.modules[res[-1][-1]]]

        return matches

    def find_match(self, pattern, exact=False):
        '''Exact module name matching'''

        logging.debug(u'find_match for "{}"'.format(pattern))

        BLACKLIST = [
            u'module_utils',
            u'callback',
            u'network modules',
            u'networking modules'
            u'windows modules'
        ]

        if not pattern or pattern is None:
            return None

        if pattern.lower() == u'core':
            return None

        '''
        if 'docs.ansible.com' in pattern and '_module.html' in pattern:
            # http://docs.ansible.com/ansible/latest/copy_module.html
            # http://docs.ansible.com/ansible/latest/dev_guide/developing_modules.html
            # http://docs.ansible.com/ansible/latest/postgresql_db_module.html
            # [helm module](https//docs.ansible.com/ansible/2.4/helm_module.html)
            # Windows module: win_robocopy\nhttp://docs.ansible.com/ansible/latest/win_robocopy_module.html
            # Examples:\n* archive (https://docs.ansible.com/ansible/archive_module.html)\n* s3_sync (https://docs.ansible.com/ansible/s3_sync_module.html)
            urls = re.findall(
                'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\(\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+',
                pattern
            )
            #urls = [x for x in urls if '_module.html' in x]
            #if urls:
            #    import epdb; epdb.st()
            import epdb; epdb.st()
        '''

        # https://github.com/ansible/ansible/issues/19755
        if pattern == u'setup':
            pattern = u'system/setup.py'

        if u'/facts.py' in pattern or u' facts.py' in pattern:
            pattern = u'system/setup.py'

        # https://github.com/ansible/ansible/issues/18527
        #   docker-container -> docker_container
        if u'-' in pattern:
            pattern = pattern.replace(u'-', u'_')

        if u'module_utils' in pattern:
            # https://github.com/ansible/ansible/issues/20368
            return None
        elif u'callback' in pattern:
            return None
        elif u'lookup' in pattern:
            return None
        elif u'contrib' in pattern and u'inventory' in pattern:
            return None
        elif pattern.lower() in BLACKLIST:
            return None
        elif u'/' in pattern and not self._find_match(pattern, exact=True):
            # https://github.com/ansible/ansible/issues/20520
            if not pattern.startswith(u'lib/'):
                keys = self.modules.keys()
                for k in keys:
                    if pattern in k:
                        ppy = pattern + u'.py'
                        if k.endswith(pattern) or k.endswith(ppy):
                            return self.modules[k]
        elif pattern.endswith(u'.py') and self._find_match(pattern, exact=False):
            # https://github.com/ansible/ansible/issues/19889
            candidate = self._find_match(pattern, exact=False)

            if isinstance(candidate, list):
                if len(candidate) == 1:
                    candidate = candidate[0]

            if candidate[u'filename'] == pattern:
                return candidate

        match = self._find_match(pattern, exact=exact)
        if not match and not exact:
            # check for just the basename
            #   2617: ansible-s-extras/network/cloudflare_dns.py
            bname = os.path.basename(pattern)
            match = self._find_match(bname)

            if not match:
                # check for deprecated name
                #   _fireball -> fireball
                match = self._find_match(u'_' + bname)

        # unique the results
        if isinstance(match, list) and len(match) > 1:
            _match = []
            for m in match:
                if m not in _match:
                    _match.append(m)
            match = _match[:]

        return match

    def is_valid(self, mname):
        match = self.find_match(mname, exact=True)
        if match:
            return True
        else:
            return False

    def get_repository_for_module(self, mname):
        match = self.find_match(mname, exact=True)
        if match:
            return match[u'repository']
        else:
            return None

    def get_ansible_modules(self):
        """Make a list of known modules"""

        matches = []
        module_dir = os.path.join(self.gitrepo.checkoutdir, u'lib/ansible/modules')
        module_dir = os.path.expanduser(module_dir)
        for root, _, filenames in os.walk(module_dir):
            for filename in filenames:
                if u'lib/ansible/modules' in root and not filename == u'__init__.py':
                    matches.append(os.path.join(root, filename))

        matches = sorted(set(matches))

        self.populate_modules(matches)

        # custom fixes
        newitems = []
        for k, v in six.iteritems(self.modules):

            # include* is almost always an ansible/ansible issue
            # https://github.com/ansible/ansibullbot/issues/214
            if k.endswith(u'/include.py'):
                self.modules[k][u'repository'] = u'ansible'
            # https://github.com/ansible/ansibullbot/issues/214
            if k.endswith(u'/include_vars.py'):
                self.modules[k][u'repository'] = u'ansible'
            if k.endswith(u'/include_role.py'):
                self.modules[k][u'repository'] = u'ansible'

            # ansible maintains these
            if u'include' in k:
                self.modules[k][u'maintainers'] = [u'ansible']

            # deprecated modules are annoying
            if v[u'name'].startswith(u'_'):

                dkey = os.path.dirname(v[u'filepath'])
                dkey = os.path.join(dkey, v[u'filename'].replace(u'_', u'', 1))
                if dkey not in self.modules:
                    nd = v.copy()
                    nd[u'name'] = nd[u'name'].replace(u'_', u'', 1)
                    newitems.append((dkey, nd))

        for ni in newitems:
            self.modules[ni[0]] = ni[1]

        # parse metadata
        logging.debug(u'set module metadata')
        self.set_module_metadata()

        # parse imports
        logging.debug(u'set module imports')
        self.set_module_imports()

        # last modified
        if self.get_commits:
            logging.debug(u'set module commits')
            self.get_module_commits()

        # parse blame
        if self.get_blames and self.get_commits:
            logging.debug(u'set module blames')
            self.get_module_blames()

        # depends on metadata now ...
        logging.debug(u'set module maintainers')
        self.set_maintainers()

        return self.modules

    def populate_modules(self, matches):
        # figure out the names
        for match in matches:
            mdict = copy.deepcopy(self.EMPTY_MODULE)

            mdict[u'filename'] = os.path.basename(match)

            dirpath = os.path.dirname(match)
            dirpath = dirpath.replace(self.gitrepo.checkoutdir + u'/', u'')
            mdict[u'dirpath'] = dirpath

            filepath = match.replace(self.gitrepo.checkoutdir + u'/', u'')
            mdict[u'filepath'] = filepath

            mdict.update(
                self.split_topics_from_path(filepath)
            )

            mdict[u'repo_filename'] = mdict[u'filepath']\
                .replace(u'lib/ansible/modules/%s/' % mdict[u'repository'], u'')

            # clustering/consul
            mdict[u'namespaced_module'] = mdict[u'repo_filename']
            mdict[u'namespaced_module'] = \
                mdict[u'namespaced_module'].replace(u'.py', u'')
            mdict[u'namespaced_module'] = \
                mdict[u'namespaced_module'].replace(u'.ps1', u'')

            mname = os.path.basename(match)
            mname = mname.replace(u'.py', u'')
            mname = mname.replace(u'.ps1', u'')
            mdict[u'name'] = mname

            # deprecated modules
            if mname.startswith(u'_'):
                mdict[u'deprecated'] = True
                deprecated_filename = \
                    os.path.dirname(mdict[u'namespaced_module'])
                deprecated_filename = \
                    os.path.join(deprecated_filename, mname[1:] + u'.py')
                mdict[u'deprecated_filename'] = deprecated_filename
            else:
                mdict[u'deprecated_filename'] = mdict[u'repo_filename']

            self.modules[filepath] = mdict

        # meta is a special module
        self.modules[u'meta'] = copy.deepcopy(self.EMPTY_MODULE)
        self.modules[u'meta'][u'name'] = u'meta'
        self.modules[u'meta'][u'repo_filename'] = u'meta'

    def get_module_commits(self):
        keys = self.modules.keys()
        keys = sorted(keys)
        for k in keys:
            self.commits[k] = []
            cpath = os.path.join(self.gitrepo.checkoutdir, k)
            if not os.path.isfile(cpath):
                continue

            mtime = os.path.getmtime(cpath)
            refresh = False
            pfile = os.path.join(
                self.scraper_cache,
                k.replace(u'/', u'_') + u'.commits.pickle'
            )

            if not os.path.isfile(pfile):
                refresh = True
            else:
                pickle_kwargs = {'encoding': 'bytes'} if six.PY3 else {}
                print(pfile)
                with open(pfile, 'rb') as f:
                    pdata = pickle.load(f, **pickle_kwargs)
                if pdata[0] == mtime:
                    self.commits[k] = pdata[1]
                else:
                    refresh = True

            if refresh:
                logging.info(u'refresh commit cache for %s' % k)
                cmd = u'cd %s; git log --follow %s' % (self.gitrepo.checkoutdir, k)
                (rc, so, se) = run_command(cmd)
                for line in to_text(so).split(u'\n'):
                    if line.startswith(u'commit '):
                        commit = {
                            u'name': None,
                            u'email': None,
                            u'login': None,
                            u'hash': line.split()[-1],
                            u'date': None
                        }

                    # Author: Matt Clay <matt@mystile.com>
                    if line.startswith(u'Author: '):
                        line = line.replace(u'Author: ', u'')
                        line = line.replace(u'<', u'')
                        line = line.replace(u'>', u'')
                        lparts = line.split()

                        if u'@' in lparts[-1]:
                            commit[u'email'] = lparts[-1]
                            commit[u'name'] = u' '.join(lparts[:-1])
                        else:
                            pass

                        if commit[u'email'] and \
                                u'noreply.github.com' in commit[u'email']:
                            commit[u'login'] = commit[u'email'].split(u'@')[0]

                    # Date:   Sat Jan 28 23:28:53 2017 -0800
                    if line.startswith(u'Date:'):
                        dstr = line.split(u':', 1)[1].strip()
                        dstr = u' '.join(dstr.split(u' ')[:-1])
                        ds = datetime.datetime.strptime(
                            to_text(dstr),
                            u'%a %b %d %H:%M:%S %Y'
                        )
                        commit[u'date'] = ds
                        self.commits[k].append(commit)

                with open(pfile, 'wb') as f:
                    pickle.dump((mtime, self.commits[k]), f, protocol=0)

    def last_commit_for_file(self, filepath):
        if filepath in self.commits:
            return self.commits[filepath][0][u'hash']

        # git log --pretty=format:'%H' -1
        # lib/ansible/modules/cloud/amazon/ec2_metric_alarm.py
        cmd = u'cd %s; git log --pretty=format:\'%%H\' -1 %s' % \
            (self.gitrepo.checkoutdir, filepath)
        (rc, so, se) = run_command(cmd)
        return to_text(so).strip()

    def get_module_blames(self):

        logging.debug(u'build email cache')
        emails_cache = self.session.query(Email)
        emails_cache = [(x.email, x.login) for x in emails_cache]
        self.emails_cache = dict(emails_cache)

        logging.debug(u'build blame cache')
        blame_cache = self.session.query(Blame).all()
        blame_cache = [x.file_commit for x in blame_cache]
        blame_cache = sorted(set(blame_cache))

        logging.debug(u'eval module hashes')
        changed = False
        keys = sorted(self.modules.keys())
        for k in keys:
            if k not in self.files:
                self.committers[k] = {}
                continue

            ghash = self.last_commit_for_file(k)

            if ghash in blame_cache:
                continue

            logging.debug(u'checking hash for {}'.format(k))
            res = self.session.query(Blame).filter_by(file_name=k, file_commit=ghash).all()
            hashes = [x.file_commit for x in res]

            if ghash not in hashes:

                logging.debug(u'hash {} not found for {}, updating blames'.format(ghash, k))

                scraper_args = [u'ansible', u'ansible', u'devel', k]
                uns, emailmap = self.gqlc.get_usernames_from_filename_blame(*scraper_args)

                # check the emails
                for email, login in emailmap.items():
                    if email in self.emails_cache:
                        continue
                    exists = self.session.query(Email).filter_by(email=email).first()
                    if not exists:
                        logging.debug(u'insert {}:{}'.format(login, email))
                        _email = Email(email=email, login=login)
                        self.session.add(_email)
                        changed = True

                # check the blames
                for login, commits in uns.items():
                    for commit in commits:
                        kwargs = {
                            u'file_name': k,
                            u'file_commit': ghash,
                            u'author_commit': commit,
                            u'author_login': login
                        }
                        exists = self.session.query(Blame).filter_by(**kwargs).first()
                        if not exists:
                            logging.debug(u'insert {}:{}:{}'.format(k, commit, login))
                            _blame = Blame(**kwargs)
                            self.session.add(_blame)
                            changed = True

        if changed:
            self.session.commit()
            logging.debug(u're-build email cache')
            emails_cache = self.session.query(Email)
            emails_cache = [(x.email, x.login) for x in emails_cache]
            self.emails_cache = dict(emails_cache)

        # fill in what we can ...
        logging.debug(u'fill in commit logins')
        for k in keys:
            for idc, commit in enumerate(self.commits[k][:]):
                if not commit.get(u'login'):
                    continue
                login = self.emails_cache.get(commit[u'email'])
                if not login and u'@users.noreply.github.com' in commit[u'email']:
                    login = commit[u'email'].split(u'@')[0]
                    self.emails_cache[commit[u'email']] = login
                if not login:
                    print(u'unknown: {}'.format(commit[u'email']))
                self.commits[k][idc][u'login'] = self.emails_cache.get(login)

    def get_emails_by_login(self, login):
        res = self.session.query(Email).filter_by(login=login)
        emails = [x.email for x in res.values()]
        return emails

    def _get_module_blames(self):
        ''' Scrape the blame page for each module and store it '''

        keys = sorted(self.modules.keys())

        # scrape the data
        for k in keys:

            cpath = os.path.join(self.gitrepo.checkoutdir, k)
            if not os.path.isfile(cpath):
                self.committers[k] = {}
                continue

            ghash = self.last_commit_for_file(k)
            pfile = os.path.join(
                self.scraper_cache,
                k.replace(u'/', u'_') + u'.blame.pickle'
            )
            sargs = [u'ansible', u'ansible', u'devel', k]

            refresh = False
            if not os.path.isfile(pfile):
                refresh = True
            else:
                logging.debug(u'load {}'.format(pfile))
                with open(pfile, 'rb') as f:
                    pdata = pickle.load(f)
                if C.DEFAULT_BREAKPOINTS:
                    logging.error(u'breakpoint!')
                    import epdb; epdb.st()
                if pdata[0] == ghash:
                    self.committers[k] = pdata[1]
                    if len(pdata) == 3:
                        # use emailmap if available
                        emailmap = pdata[2]
                    else:
                        emailmap = {}
                else:
                    refresh = True

            if refresh:
                if self.gqlc:
                    logging.debug(u'graphql blame usernames {}'.format(pfile))
                    uns, emailmap = self.gqlc.get_usernames_from_filename_blame(*sargs)
                else:
                    emailmap = {}  # scrapping: emails not available
                    logging.debug(u'www blame usernames {}'.format(pfile))
                    uns = self.gws.get_usernames_from_filename_blame(*sargs)
                self.committers[k] = uns
                with open(pfile, 'wb') as f:
                    pickle.dump((ghash, uns, emailmap), f)

            for email, github_id in emailmap.items():
                if email not in self.emails_cache:
                    self.emails_cache[email] = github_id

        # add scraped logins to the map
        for k in keys:
            for idx, x in enumerate(self.commits[k]):
                if x[u'email'] in [u'@']:
                    continue
                if x[u'email'] not in self.emails_cache:
                    self.emails_cache[x[u'email']] = None
                if x[u'login']:
                    self.emails_cache[x[u'email']] = x[u'login']
                    continue

                xhash = x[u'hash']
                for ck, cv in six.iteritems(self.committers[k]):
                    if xhash in cv:
                        self.emails_cache[x[u'email']] = ck
                        break

        # fill in what we can ...
        for k in keys:
            for idx, x in enumerate(self.commits[k]):
                if not x[u'login']:
                    if x[u'email'] in [u'@']:
                        continue
                    if self.emails_cache[x[u'email']]:
                        login = self.emails_cache[x[u'email']]
                        xhash = x[u'hash']
                        self.commits[k][idx][u'login'] = login
                        if login not in self.committers[k]:
                            self.committers[k][login] = []
                        if xhash not in self.committers[k][login]:
                            self.committers[k][login].append(xhash)

    def set_maintainers(self):
        '''Define the maintainers for each module'''

        # grep the authors:
        for k, v in six.iteritems(self.modules):
            if v[u'filepath'] is None:
                continue
            mfile = os.path.join(self.gitrepo.checkoutdir, v[u'filepath'])
            authors = self.get_module_authors(mfile)
            self.modules[k][u'authors'] = authors

            # authors are maintainers by -default-
            self.modules[k][u'maintainers'] += authors
            self.modules[k][u'maintainers'] = \
                sorted(set(self.modules[k][u'maintainers']))

        metadata = self.botmeta[u'files'].keys()
        for k, v in six.iteritems(self.modules):
            if k == u'meta':
                continue

            if k in self.botmeta[u'files']:
                # There are metadata in .github/BOTMETA.yml for this file
                # copy maintainers_keys
                self.modules[k][u'maintainers_keys'] = self.botmeta[u'files'][k][u'maintainers_keys'][:]

                if self.botmeta[u'files'][k]:
                    maintainers = self.botmeta[u'files'][k].get(u'maintainers', [])

                    for maintainer in maintainers:
                        if maintainer not in self.modules[k][u'maintainers']:
                            self.modules[k][u'maintainers'].append(maintainer)

                    # remove the people who want to be ignored
                    if u'ignored' in self.botmeta[u'files'][k]:
                        ignored = self.botmeta[u'files'][k][u'ignored']
                        for x in ignored:
                            if x in self.modules[k][u'maintainers']:
                                self.modules[k][u'maintainers'].remove(x)

            else:
                # There isn't metadata in .github/BOTMETA.yml for this file
                best_match = None
                for mkey in metadata:
                    if v[u'filepath'].startswith(mkey):
                        if not best_match:
                            best_match = mkey
                            continue
                        if len(mkey) > len(best_match):
                            best_match = mkey
                if best_match:
                    self.modules[k][u'maintainers_keys'] = [best_match]
                    for maintainer in self.botmeta[u'files'][best_match].get(u'maintainers', []):
                        if maintainer not in self.modules[k][u'maintainers']:
                            self.modules[k][u'maintainers'].append(maintainer)

                    # remove the people who want to be ignored
                    for ignored in self.botmeta[u'files'][best_match].get(u'ignored', []):
                        if ignored in self.modules[k][u'maintainers']:
                            self.modules[k][u'maintainers'].remove(ignored)

            # save a pristine copy so that higher level code can still use it
            self.modules[k][u'maintainers'] = sorted(set(self.modules[k][u'maintainers']))
            self.modules[k][u'_maintainers'] = \
                [x for x in self.modules[k][u'maintainers']]

        # set the namespace maintainers ...
        for k, v in six.iteritems(self.modules):
            if u'namespace_maintainers' not in self.modules[k]:
                self.modules[k][u'namespace_maintainers'] = []
            if v.get(u'namespace'):
                ns = v.get(u'namespace')
                nms = self.get_maintainers_for_namespace(ns)
                self.modules[k][u'namespace_maintainers'] = nms

    def split_topics_from_path(self, module_file):
        subpath = module_file.replace(u'lib/ansible/modules/', u'')
        path_parts = subpath.split(u'/')
        topic = path_parts[0]

        if len(path_parts) > 2:
            subtopic = path_parts[1]
            fulltopic = u'/'.join(path_parts[0:2])
        else:
            subtopic = None
            fulltopic = path_parts[0]

        tdata = {
            u'fulltopic': fulltopic,
            u'namespace': fulltopic,
            u'topic': topic,
            u'subtopic': subtopic
        }

        return tdata

    def get_module_authors(self, module_file):
        """Grep the authors out of the module docstrings"""

        if not os.path.exists(module_file):
            return []

        documentation = b''
        inphase = False

        with io.open(module_file, 'rb') as f:
            for line in f:
                if b'DOCUMENTATION' in line:
                    inphase = True
                    continue
                if line.strip().endswith((b"'''", b'"""')):
                    break
                if inphase:
                    documentation += line

        if not documentation:
            return []

        # clean out any other yaml besides author to save time
        inphase = False
        author_lines = u''
        doc_lines = to_text(documentation).split(u'\n')
        for idx, x in enumerate(doc_lines):
            if x.startswith(u'author'):
                inphase = True
            if inphase and not x.strip().startswith((u'-', u'author')):
                inphase = False
                break
            if inphase:
                author_lines += x + u'\n'

        if not author_lines:
            return []

        ydata = {}
        try:
            ydata = yaml.load(author_lines, Loader=BotYAMLLoader)
        except Exception as e:
            print(e)
            return []

        # quit early if the yaml was not valid
        if not ydata:
            return []

        # sometimes the field is 'author', sometimes it is 'authors'
        if u'authors' in ydata:
            ydata[u'author'] = ydata[u'authors']

        # quit if the key was not found
        if u'author' not in ydata:
            return []

        if not isinstance(ydata[u'author'], list):
            ydata[u'author'] = [ydata[u'author']]

        authors = []
        for author in ydata[u'author']:
            github_ids = self.extract_github_id(author)
            if github_ids:
                authors.extend(github_ids)
        return authors

    def extract_github_id(self, author):
        authors = set()

        if u'ansible core team' in author.lower():
            authors.add(u'ansible')
        elif u'@' in author:
            # match github ids but not emails
            authors.update(re.findall(r'(?<!\w)@([\w-]+)(?![\w.])', author))
        elif u'github.com/' in author:
            # {'author': 'Henrique Rodrigues (github.com/Sodki)'}
            idx = author.find(u'github.com/')
            author = author[idx+11:]
            authors.add(author.replace(u')', u''))
        elif u'(' in author and len(author.split()) == 3:
            # Mathieu Bultel (matbu)
            idx = author.find(u'(')
            author = author[idx+1:]
            authors.add(author.replace(u')', u''))

        # search for emails
        for email in re.findall(r'[<(]([^@]+@[^)>]+)[)>]', author):
            github_id = self.emails_cache.get(email)
            if github_id:
                authors.add(github_id)

        return list(authors)

    def fuzzy_match(self, repo=None, title=None, component=None):
        '''Fuzzy matching for modules'''

        logging.debug(u'fuzzy match {}'.format(
            to_text(to_bytes(component, 'ascii', 'ignore'), 'ascii'))
        )

        if component.lower() == u'core':
            return None

        # https://github.com/ansible/ansible/issues/18179
        if u'validate-modules' in component:
            return None

        # https://github.com/ansible/ansible/issues/20368
        if u'module_utils' in component:
            return None

        if u'new module' in component:
            return None

        # authorized_keys vs. authorized_key
        if component and component.endswith(u's'):
            tm = self.find_match(component[:-1])
            if tm:
                if not isinstance(tm, list):
                    return tm[u'name']
                elif len(tm) == 1:
                    return tm[0][u'name']
                else:
                    if C.DEFAULT_BREAKPOINTS:
                        logging.error(u'breakpoint!')
                        import epdb; epdb.st()

        match = None
        known_modules = []

        for k, v in six.iteritems(self.modules):
            if v[u'name'] in [u'include']:
                continue
            known_modules.append(v[u'name'])

        title = title.lower()
        title = title.replace(u':', u'')
        title_matches = [x for x in known_modules if x + u' module' in title]

        if not title_matches:
            title_matches = [x for x in known_modules
                             if title.startswith(x + u' ')]
            if not title_matches:
                title_matches = \
                    [x for x in known_modules if u' ' + x + u' ' in title]

            if title_matches:
                title_matches = [x for x in title_matches if x != u'at']

        # don't do singular word matching in title for ansible/ansible
        cmatches = None
        if component:
            cmatches = [x for x in known_modules if x in component]
            cmatches = [x for x in cmatches if not u'_' + x in component]

        # globs
        if not cmatches and u'*' in component:
            fmatches = [x for x in known_modules if fnmatch.fnmatch(x, component)]
            if fmatches:
                cmatches = fmatches[:]

        if title_matches:
            # use title ... ?
            cmatches = [x for x in cmatches if x in title_matches and x not in [u'at']]

        if cmatches:
            if len(cmatches) >= 1 and (u'*' not in component and u'modules' not in component):
                match = cmatches[0]
            else:
                match = cmatches[:]
            if not match:
                if u'docs.ansible.com' in component:
                    pass
                else:
                    pass
            logging.debug("module - component matches: %s" % cmatches)

        if not match:
            if len(title_matches) == 1:
                match = title_matches[0]
            else:
                logging.debug("module - title matches: %s" % title_matches)

        return match

    def is_multi(self, rawtext):
        '''Is the string a list or a glob of modules?'''
        if rawtext:
            lines = rawtext.split(u'\n')

            # clean up lines
            lines = [x.strip() for x in lines if x.strip()]
            lines = [x for x in lines if len(x) > 2]

            if len(lines) > 1:
                return True

            if lines:
                if lines[0].strip().endswith(u'*'):
                    return True

        return False

    # https://github.com/ansible/ansible-modules-core/issues/3831
    def multi_match(self, rawtext):
        '''Return a list of matches for a given glob or list of names'''
        matches = []
        lines = rawtext.split(u'\n')
        lines = [x.strip() for x in lines if x.strip()]
        for line in lines:
            # is it an exact name, a path, a globbed name, a globbed path?
            if line.endswith(u'*'):
                thiskey = line.replace(u'*', u'')
                keymatches = []
                for k in self.modules.keys():
                    if thiskey in k:
                        keymatches.append(k)
                for k in keymatches:
                    matches.append(self.modules[k].copy())
            else:
                match = self.find_match(line)
                if match:
                    matches.append(match)

        # unique the list
        tmplist = []
        for x in matches:
            if x not in tmplist:
                tmplist.append(x)
        if matches != tmplist:
            matches = [x for x in tmplist]

        return matches

    def set_module_metadata(self):
        for k, v in six.iteritems(self.modules):
            if not v[u'filepath']:
                continue
            mfile = os.path.join(self.gitrepo.checkoutdir, v[u'filepath'])
            if not mfile.endswith(u'.py'):
                # metadata is only the .py files ...
                ext = mfile.split(u'.')[-1]
                mfile = mfile.replace(u'.' + ext, u'.py', 1)

            self.modules[k][u'metadata'].update(self.get_module_metadata(mfile))

    def get_module_metadata(self, module_file):
        meta = {}

        if not os.path.isfile(module_file):
            return meta

        rawmeta = u''
        inphase = False
        with io.open(module_file, 'r', encoding='utf-8') as f:
            for line in f:
                if line.startswith(u'ANSIBLE_METADATA'):
                    inphase = True
                if line.startswith(u'DOCUMENTATION'):
                    break
                if inphase:
                    rawmeta += line
        rawmeta = rawmeta.replace(u'ANSIBLE_METADATA =', u'', 1)
        rawmeta = rawmeta.strip()
        try:
            meta = ast.literal_eval(rawmeta)
            tmp_meta = {}
            for k, v in meta.items():
                if isinstance(k, six.binary_type):
                    k = to_text(k)
                if isinstance(v, six.binary_type):
                    v = to_text(v)
                if isinstance(v, list):
                    tmp_list = []
                    for i in v:
                        if isinstance(i, six.binary_type):
                            i = to_text(i)
                        tmp_list.append(i)
                    v = tmp_list
                    del tmp_list
                tmp_meta[k] = v
            meta = tmp_meta
            del tmp_meta
        except SyntaxError:
            pass

        return meta

    def set_module_imports(self):
        for k, v in six.iteritems(self.modules):
            if not v[u'filepath']:
                continue
            mfile = os.path.join(self.gitrepo.checkoutdir, v[u'filepath'])
            self.modules[k][u'imports'] = self.get_module_imports(mfile)

    def get_module_imports(self, module_file):
        mimports = []

        if not os.path.isfile(module_file):
            return mimports

        else:
            with open(module_file, 'rb') as f:
                for line in f:
                    line = line.strip()
                    line = line.replace(b',', b'')
                    if line.startswith(b'import') or \
                            (b'import' in line and b'from' in line):
                        lparts = line.split()
                        if line.startswith(b'import '):
                            mimports.append(lparts[1])
                        elif line.startswith(b'from '):
                            mpath = lparts[1] + b'.'
                            for spath in lparts[3:]:
                                mimports.append(mpath + spath)

            return [to_text(m) for m in mimports]

    @property
    def all_maintainers(self):
        maintainers = set()
        for path, metadata in self.botmeta[u'files'].items():
            maintainers.update(metadata.get(u'maintainers', []))
        return maintainers

    @property
    def all_authors(self):
        authors = set()
        for key, metadata in self.modules.items():
            authors.update(metadata.get(u'authors', []))
        return authors

    def get_maintainers_for_namespace(self, namespace):
        maintainers = []
        for k, v in self.modules.items():
            if u'namespace' not in v or u'maintainers' not in v:
                continue
            if v[u'namespace'] == namespace:
                for m in v[u'maintainers']:
                    if m not in maintainers:
                        maintainers.append(m)
        maintainers = [x for x in maintainers if x.strip()]
        return maintainers

    @staticmethod
    def replace_ansible(maintainers, ansible_members, bots=[]):
        '''Replace -ansible- with the -humans- in the org'''
        newlist = []
        for m in maintainers:
            if m != u'ansible':
                newlist.append(m)
            else:
                newlist += ansible_members
        newlist = sorted(set(newlist))
        newlist = [x for x in newlist if x not in bots]
        return newlist

    def get_file_content(self, filepath):
        fpath = os.path.join(self.gitrepo.checkoutdir, filepath)
        if not os.path.isfile(fpath):
            return None
        with io.open(fpath, 'r', encoding='utf-8') as f:
            data = f.read()
        return data
