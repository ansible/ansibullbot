#!/usr/bin/env python

import ast
import copy
import datetime
import logging
import os
import pickle
import re
import shutil
import yaml

from sqlalchemy import create_engine
from sqlalchemy import Column
from sqlalchemy import Integer
from sqlalchemy import String
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

from ansibullbot.parsers.botmetadata import BotMetadataParser
from ansibullbot.utils.systemtools import run_command
from ansibullbot.utils.webscraper import GithubWebScraper


Base = declarative_base()


class Blame(Base):
    __tablename__ = 'blames'
    id = Column(Integer(), primary_key=True)
    file_name = Column(String())
    file_commit = Column(String())
    author_commit = Column(String())
    author_login = Column(String())


class Email(Base):
    __tablename__ = 'email'
    id = Column(Integer())
    login = Column(String())
    email = Column(String(), primary_key=True)


class ModuleIndexer(object):

    EMPTY_MODULE = {
        'authors': [],
        'name': None,
        'namespaced_module': None,
        'namespace_maintainers': [],
        'deprecated': False,
        'deprecated_filename': None,
        'dirpath': None,
        'filename': None,
        'filepath': None,
        'fulltopic': None,
        'maintainers': [],
        '_maintainers': [],
        'maintainers_keys': None,
        'metadata': {},
        'repo_filename': None,
        'repository': 'ansible',
        'subtopic': None,
        'topic': None,
        'imports': []
    }

    REPO = "http://github.com/ansible/ansible"

    def __init__(self, maintainers=None, gh_client=None, cachedir='~/.ansibullbot/cache'):
        '''
        Maintainers: defaultdict(dict) where keys are filepath and values are dict
        gh_client: GraphQL GitHub client
        '''
        self.botmeta = {}  # BOTMETA.yml file with minor updates (macro rendered, empty default values fixed)
        self.modules = {}  # keys: paths of files belonging to the repository
        self.checkoutdir = '~/.ansibullbot/cache/ansible.modules.checkout'
        self.maintainers = maintainers or {}
        self.checkoutdir = os.path.join(cachedir, 'ansible.modules.checkout')
        self.checkoutdir = os.path.expanduser(self.checkoutdir)
        self.importmap = {}
        self.scraper_cache = '~/.ansibullbot/cache/ansible.modules.scraper'
        self.scraper_cache = os.path.expanduser(self.scraper_cache)
        self.gws = GithubWebScraper(cachedir=self.scraper_cache)
        self.gqlc = gh_client
        self.files = []

        # sqlalchemy
        unc = os.path.join(cachedir, 'ansible_module_indexer.db')
        unc = os.path.expanduser(unc)
        unc = 'sqlite:///' + unc

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
        changed = self.manage_checkout()
        if changed or force:
            self.get_files()
            self.parse_metadata()

    def manage_checkout(self):
        '''Check if there are any changes to the repo'''
        changed = False
        if not os.path.isdir(self.checkoutdir):
            self.create_checkout()
            changed = True
        else:
            changed = self.update_checkout()
        return changed

    def get_files(self):
        '''Cache a list of filenames in the checkout'''
        cmd = 'cd {}; git ls-files'.format(self.checkoutdir)
        (rc, so, se) = run_command(cmd)
        files = so.split('\n')
        files = [x.strip() for x in files if x.strip()]
        self.files = files

    def parse_metadata(self):

        fp = '.github/BOTMETA.yml'
        rdata = self.get_file_content(fp)
        self.botmeta = BotMetadataParser.parse_yaml(rdata)

        # load the modules
        logging.info('loading modules')
        self.get_ansible_modules()

    def create_checkout(self):
        """checkout ansible"""

        print('# creating checkout for module indexer')

        # cleanup
        if os.path.isdir(self.checkoutdir):
            shutil.rmtree(self.checkoutdir)

        #cmd = "git clone http://github.com/ansible/ansible --recursive %s" \
        cmd = "git clone %s %s" \
            % (self.REPO, self.checkoutdir)
        (rc, so, se) = run_command(cmd)
        print str(so) + str(se)

    def update_checkout(self):
        """rebase + pull + update the checkout"""

        changed = False

        cmd = "cd %s ; git pull --rebase" % self.checkoutdir
        (rc, so, se) = run_command(cmd)
        print str(so) + str(se)

        # If rebase failed, recreate the checkout
        if rc != 0:
            self.create_checkout()
            return True
        else:
            if 'current branch devel is up to date.' not in so.lower():
                changed = True

        return changed

    def _find_match(self, pattern, exact=False):

        match = None
        for k,v in self.modules.iteritems():
            if v['name'] == pattern:
                match = v
                break
        if not match:
            # search by key ... aka the filepath
            for k,v in self.modules.iteritems():
                if k == pattern:
                    match = v
                    break
        if not match and not exact:
            # search by properties
            for k,v in self.modules.iteritems():
                for subkey in v.keys():
                    if v[subkey] == pattern:
                        match = v
                        break
                if match:
                    break
        return match

    def find_match(self, pattern, exact=False):
        '''Exact module name matching'''
        if not pattern:
            return None

        # https://github.com/ansible/ansible/issues/19755
        if pattern == 'setup':
            pattern = 'system/setup.py'

        # https://github.com/ansible/ansible/issues/18527
        #   docker-container -> docker_container
        if '-' in pattern:
            pattern = pattern.replace('-', '_')

        if 'module_utils' in pattern:
            # https://github.com/ansible/ansible/issues/20368
            return None
        elif '/' in pattern and not self._find_match(pattern, exact=True):
            # https://github.com/ansible/ansible/issues/20520
            if not pattern.startswith('lib/'):
                keys = self.modules.keys()
                for k in keys:
                    if pattern in k:
                        ppy = pattern + '.py'
                        if k.endswith(pattern) or k.endswith(ppy):
                            return self.modules[k]
        elif pattern.endswith('.py') and self._find_match(pattern, exact=False):
            # https://github.com/ansible/ansible/issues/19889
            candidate = self._find_match(pattern, exact=False)
            if candidate['filename'] == pattern:
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
                match = self._find_match('_' + bname)

        return match

    def is_valid(self, mname):
        match = self.find_match(mname)
        if match:
            return True
        else:
            return False

    def get_repository_for_module(self, mname):
        match = self.find_match(mname)
        if match:
            return match['repository']
        else:
            return None

    def get_ansible_modules(self):
        """Make a list of known modules"""

        matches = []
        module_dir = os.path.join(self.checkoutdir, 'lib/ansible/modules')
        module_dir = os.path.expanduser(module_dir)
        for root, dirnames, filenames in os.walk(module_dir):
            for filename in filenames:
                if 'lib/ansible/modules' in root and \
                        not filename == '__init__.py' and \
                        (filename.endswith('.py') or filename.endswith('.ps1')):
                    matches.append(os.path.join(root, filename))

        matches = sorted(set(matches))

        # figure out the names
        for match in matches:
            mdict = copy.deepcopy(self.EMPTY_MODULE)

            mdict['filename'] = os.path.basename(match)

            dirpath = os.path.dirname(match)
            dirpath = dirpath.replace(self.checkoutdir + '/', '')
            mdict['dirpath'] = dirpath

            filepath = match.replace(self.checkoutdir + '/', '')
            mdict['filepath'] = filepath

            mdict.update(
                self.split_topics_from_path(filepath)
            )

            mdict['repo_filename'] = mdict['filepath']\
                .replace('lib/ansible/modules/%s/' % mdict['repository'], '')

            # clustering/consul
            mdict['namespaced_module'] = mdict['repo_filename']
            mdict['namespaced_module'] = \
                mdict['namespaced_module'].replace('.py', '')
            mdict['namespaced_module'] = \
                mdict['namespaced_module'].replace('.ps1', '')

            mname = os.path.basename(match)
            mname = mname.replace('.py', '')
            mname = mname.replace('.ps1', '')
            mdict['name'] = mname

            # deprecated modules
            if mname.startswith('_'):
                mdict['deprecated'] = True
                deprecated_filename = \
                    os.path.dirname(mdict['namespaced_module'])
                deprecated_filename = \
                    os.path.join(deprecated_filename, mname[1:] + '.py')
                mdict['deprecated_filename'] = deprecated_filename
            else:
                mdict['deprecated_filename'] = mdict['repo_filename']

            self.modules[filepath] = mdict

        # meta is a special module
        self.modules['meta'] = copy.deepcopy(self.EMPTY_MODULE)
        self.modules['meta']['name'] = 'meta'
        self.modules['meta']['repo_filename'] = 'meta'

        # custom fixes
        newitems = []
        for k,v in self.modules.iteritems():

            # include* is almost always an ansible/ansible issue
            # https://github.com/ansible/ansibullbot/issues/214
            if k.endswith('/include.py'):
                self.modules[k]['repository'] = 'ansible'
            # https://github.com/ansible/ansibullbot/issues/214
            if k.endswith('/include_vars.py'):
                self.modules[k]['repository'] = 'ansible'
            if k.endswith('/include_role.py'):
                self.modules[k]['repository'] = 'ansible'

            # ansible maintains these
            if 'include' in k:
                self.modules[k]['maintainers'] = ['ansible']

            # deprecated modules are annoying
            if v['name'].startswith('_'):

                dkey = os.path.dirname(v['filepath'])
                dkey = os.path.join(dkey, v['filename'].replace('_', '', 1))
                if dkey not in self.modules:
                    nd = v.copy()
                    nd['name'] = nd['name'].replace('_', '', 1)
                    newitems.append((dkey, nd))

        for ni in newitems:
            self.modules[ni[0]] = ni[1]

        # parse metadata
        logging.debug('set module metadata')
        self.set_module_metadata()

        # parse imports
        logging.debug('set module imports')
        self.set_module_imports()

        # last modified
        logging.debug('set module commits')
        self.get_module_commits()

        # parse blame
        logging.debug('set module blames')
        self.get_module_blames()

        # depends on metadata now ...
        logging.debug('set module maintainers')
        self.set_maintainers()

        return self.modules

    def get_module_commits(self):
        keys = self.modules.keys()
        keys = sorted(keys)
        for k in keys:
            #v = self.modules[k]
            self.commits[k] = []
            cpath = os.path.join(self.checkoutdir, k)
            if not os.path.isfile(cpath):
                continue

            mtime = os.path.getmtime(cpath)
            refresh = False
            pfile = os.path.join(
                self.scraper_cache,
                k.replace('/', '_') + '.commits.pickle'
            )

            if not os.path.isfile(pfile):
                refresh = True
            else:
                with open(pfile, 'rb') as f:
                    pdata = pickle.load(f)
                if pdata[0] == mtime:
                    self.commits[k] = pdata[1]
                else:
                    refresh = True

            if refresh:
                logging.info('refresh commit cache for %s' % k)
                cmd = 'cd %s; git log --follow %s' % (self.checkoutdir, k)
                (rc, so, se) = run_command(cmd)
                for line in so.split('\n'):
                    if line.startswith('commit '):
                        commit = {
                            'name': None,
                            'email': None,
                            'login': None,
                            'hash': line.split()[-1],
                            'date': None
                        }

                    # Author: Matt Clay <matt@mystile.com>
                    if line.startswith('Author: '):
                        line = line.replace('Author: ', '')
                        line = line.replace('<', '')
                        line = line.replace('>', '')
                        lparts = line.split()

                        if '@' in lparts[-1]:
                            commit['email'] = lparts[-1]
                            commit['name'] = ' '.join(lparts[:-1])
                        else:
                            pass

                        if commit['email'] and \
                                'noreply.github.com' in commit['email']:
                            commit['login'] = commit['email'].split('@')[0]

                    # Date:   Sat Jan 28 23:28:53 2017 -0800
                    if line.startswith('Date:'):
                        dstr = line.split(':', 1)[1].strip()
                        dstr = ' '.join(dstr.split(' ')[:-1])
                        ds = datetime.datetime.strptime(
                            dstr,
                            '%a %b %d %H:%M:%S %Y'
                        )
                        commit['date'] = ds
                        self.commits[k].append(commit)

                with open(pfile, 'wb') as f:
                    pickle.dump((mtime, self.commits[k]), f)

    def last_commit_for_file(self, filepath):
        if filepath in self.commits:
            return self.commits[filepath][0]['hash']

        # git log --pretty=format:'%H' -1
        # lib/ansible/modules/cloud/amazon/ec2_metric_alarm.py
        cmd = 'cd %s; git log --pretty=format:\'%%H\' -1 %s' % \
            (self.checkoutdir, filepath)
        (rc, so, se) = run_command(cmd)
        #import epdb; epdb.st()
        return so.strip()

    def get_module_blames(self):

        logging.debug('build email cache')
        emails_cache = self.session.query(Email)
        emails_cache = [(x.email,x.login) for x in emails_cache]
        self.emails_cache = dict(emails_cache)

        logging.debug('build blame cache')
        blame_cache = self.session.query(Blame).all()
        blame_cache = [x.file_commit for x in blame_cache]
        blame_cache = sorted(set(blame_cache))

        logging.debug('eval module hashes')
        changed = False
        keys = sorted(self.modules.keys())
        for k in keys:
            #logging.debug('eval {}'.format(k))

            if k not in self.files:
                self.committers[k] = {}
                continue

            #logging.debug('last commit {}'.format(k))
            ghash = self.last_commit_for_file(k)

            if ghash in blame_cache:
                continue

            logging.debug('checking hash for {}'.format(k))
            res = self.session.query(Blame).filter_by(file_name=k, file_commit=ghash).all()
            hashes = [x.file_commit for x in res]

            if ghash not in hashes:

                logging.debug('hash {} not found for {}, updating blames'.format(ghash, k))

                scraper_args = ['ansible', 'ansible', 'devel', k]
                uns, emailmap = self.gqlc.get_usernames_from_filename_blame(*scraper_args)

                # check the emails
                for email, login in emailmap.items():
                    if email in self.emails_cache:
                        continue
                    exists = self.session.query(Email).filter_by(email=email).first()
                    if not exists:
                        logging.debug('insert {}:{}'.format(login, email))
                        _email = Email(email=email, login=login)
                        self.session.add(_email)
                        changed = True

                # check the blames
                for login, commits in uns.items():
                    for commit in commits:
                        kwargs = {
                            'file_name': k,
                            'file_commit': ghash,
                            'author_commit': commit,
                            'author_login': login
                        }
                        exists = self.session.query(Blame).filter_by(**kwargs).first()
                        if not exists:
                            logging.debug('insert {}:{}:{}'.format(k, commit, login))
                            _blame = Blame(**kwargs)
                            self.session.add(_blame)
                            changed = True

        if changed:
            self.session.commit()
            logging.debug('re-build email cache')
            emails_cache = self.session.query(Email)
            emails_cache = [(x.email,x.login) for x in emails_cache]
            self.emails_cache = dict(emails_cache)

        # fill in what we can ...
        logging.debug('fill in commit logins')
        for k in keys:
            for idc,commit in enumerate(self.commits[k][:]):
                if not commit.get('login'):
                    continue
                login = self.emails_cache.get(commit['email'])
                if not login and '@users.noreply.github.com' in commit['email']:
                    login = commit['email'].split('@')[0]
                    self.emails_cache[commit['email']] = login
                if not login:
                    print('unknown: {}'.format(commit['email']))
                    #import epdb; epdb.st()
                self.commits[k][idc]['login'] = self.emails_cache.get(login)

    def _get_module_blames(self):
        ''' Scrape the blame page for each module and store it '''

        keys = sorted(self.modules.keys())

        # scrape the data
        #for k,v in self.modules.iteritems():
        for k in keys:

            #v = self.modules[k]
            cpath = os.path.join(self.checkoutdir, k)
            if not os.path.isfile(cpath):
                self.committers[k] = {}
                continue

            #mtime = os.path.getmtime(cpath)
            ghash = self.last_commit_for_file(k)
            pfile = os.path.join(
                self.scraper_cache,
                k.replace('/', '_') + '.blame.pickle'
            )
            sargs = ['ansible', 'ansible', 'devel', k]

            refresh = False
            if not os.path.isfile(pfile):
                refresh = True
            else:
                logging.debug('load {}'.format(pfile))
                with open(pfile, 'rb') as f:
                    pdata = pickle.load(f)
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
                    logging.debug('graphql blame usernames {}'.format(pfile))
                    uns, emailmap = self.gqlc.get_usernames_from_filename_blame(*sargs)
                else:
                    emailmap = {}  # scrapping: emails not available
                    logging.debug('www blame usernames {}'.format(pfile))
                    uns = self.gws.get_usernames_from_filename_blame(*sargs)
                self.committers[k] = uns
                with open(pfile, 'wb') as f:
                    pickle.dump((ghash, uns, emailmap), f)

            for email, github_id in emailmap.items():
                if email not in self.emails_cache:
                    self.emails_cache[email] = github_id

        # add scraped logins to the map
        #for k,v in self.modules.iteritems():
        for k in keys:
            #v = self.modules[k]
            for idx,x in enumerate(self.commits[k]):
                if x['email'] in ['@']:
                    continue
                if x['email'] not in self.emails_cache:
                    self.emails_cache[x['email']] = None
                if x['login']:
                    self.emails_cache[x['email']] = x['login']
                    continue

                xhash = x['hash']
                for ck,cv in self.committers[k].iteritems():
                    if xhash in cv:
                        self.emails_cache[x['email']] = ck
                        break

        # fill in what we can ...
        #for k,v in self.modules.iteritems():
        for k in keys:
            #v = self.modules[k]
            for idx,x in enumerate(self.commits[k]):
                if not x['login']:
                    if x['email'] in ['@']:
                        continue
                    if self.emails_cache[x['email']]:
                        login = self.emails_cache[x['email']]
                        xhash = x['hash']
                        self.commits[k][idx]['login'] = login
                        if login not in self.committers[k]:
                            self.committers[k][login] = []
                        if xhash not in self.committers[k][login]:
                            self.committers[k][login].append(xhash)

    def set_maintainers(self):
        '''Define the maintainers for each module'''

        # grep the authors:
        for k,v in self.modules.iteritems():
            if v['filepath'] is None:
                continue
            mfile = os.path.join(self.checkoutdir, v['filepath'])
            authors = self.get_module_authors(mfile)
            self.modules[k]['authors'] = authors

            # authors are maintainers by -default-
            self.modules[k]['maintainers'] += authors
            self.modules[k]['maintainers'] = \
                sorted(set(self.modules[k]['maintainers']))

        metadata = self.botmeta['files'].keys()
        for k,v in self.modules.iteritems():
            if k == 'meta':
                continue

            if k in self.botmeta['files']:
                # There are metadata in .github/BOTMETA.yml for this file
                # copy maintainers_keys
                self.modules[k]['maintainers_keys'] = self.botmeta['files'][k]['maintainers_keys'][:]

                if self.botmeta['files'][k]:
                    maintainers = self.botmeta['files'][k].get('maintainers', [])
                    for maintainer in maintainers:
                        if maintainer not in self.modules[k]['maintainers']:
                            self.modules[k]['maintainers'].append(maintainer)

                    # remove the people who want to be ignored
                    if 'ignored' in self.botmeta['files'][k]:
                        ignored = self.botmeta['files'][k]['ignored']
                        for x in ignored:
                            if x in self.modules[k]['maintainers']:
                                self.modules[k]['maintainers'].remove(x)

            else:
                # There isn't metadata in .github/BOTMETA.yml for this file
                best_match = None
                for mkey in metadata:
                    if v['filepath'].startswith(mkey):
                        if not best_match:
                            best_match = mkey
                            continue
                        if len(mkey) > len(best_match):
                            best_match = mkey
                if best_match:
                    self.modules[k]['maintainers_keys'] = [best_match]
                    for maintainer in self.botmeta['files'][best_match].get('maintainers', []):
                        if maintainer not in self.modules[k]['maintainers']:
                            self.modules[k]['maintainers'].append(maintainer)

                    # remove the people who want to be ignored
                    for ignored in self.botmeta['files'][best_match].get('ignored', []):
                        if ignored in self.modules[k]['maintainers']:
                            self.modules[k]['maintainers'].remove(ignored)

            # save a pristine copy so that higher level code can still use it
            self.modules[k]['maintainers'] = sorted(set(self.modules[k]['maintainers']))
            self.modules[k]['_maintainers'] = \
                [x for x in self.modules[k]['maintainers']]

        # set the namespace maintainers ...
        for k,v in self.modules.iteritems():
            if 'namespace_maintainers' not in self.modules[k]:
                self.modules[k]['namespace_maintainers'] = []
            if v.get('namespace'):
                ns = v.get('namespace')
                nms = self.get_maintainers_for_namespace(ns)
                self.modules[k]['namespace_maintainers'] = nms

    def split_topics_from_path(self, module_file):
        subpath = module_file.replace('lib/ansible/modules/', '')
        path_parts = subpath.split('/')
        topic = path_parts[0]

        if len(path_parts) > 2:
            subtopic = path_parts[1]
            fulltopic = '/'.join(path_parts[0:2])
        else:
            subtopic = None
            fulltopic = path_parts[0]

        tdata = {
            'fulltopic': fulltopic,
            'namespace': fulltopic,
            'topic': topic,
            'subtopic': subtopic
        }

        return tdata

    def get_module_authors(self, module_file):
        """Grep the authors out of the module docstrings"""

        if not os.path.exists(module_file):
            return []

        documentation = ''
        inphase = False

        with open(module_file, 'rb') as f:
            for line in f:
                if 'DOCUMENTATION' in line:
                    inphase = True
                    continue
                if line.strip().endswith("'''") or line.strip().endswith('"""'):
                    #phase = None
                    break
                if inphase:
                    documentation += line

        if not documentation:
            return []

        # clean out any other yaml besides author to save time
        inphase = False
        author_lines = ''
        doc_lines = documentation.split('\n')
        for idx,x in enumerate(doc_lines):
            if x.startswith('author'):
                #print("START ON %s" % x)
                inphase = True
                #continue
            if inphase and not x.strip().startswith('-') and \
                    not x.strip().startswith('author'):
                #print("BREAK ON %s" % x)
                inphase = False
                break
            if inphase:
                author_lines += x + '\n'

        if not author_lines:
            return []

        ydata = {}
        try:
            ydata = yaml.load(author_lines)
        except Exception as e:
            print e
            return []

        # quit early if the yaml was not valid
        if not ydata:
            return []

        # sometimes the field is 'author', sometimes it is 'authors'
        if 'authors' in ydata:
            ydata['author'] = ydata['authors']

        # quit if the key was not found
        if 'author' not in ydata:
            return []

        if type(ydata['author']) != list:
            ydata['author'] = [ydata['author']]

        authors = []
        for author in ydata['author']:
            github_ids = self.extract_github_id(author)
            if github_ids:
                authors.extend(github_ids)
        return authors

    def extract_github_id(self, author):
        authors = set()

        if 'ansible core team' in author.lower():
            authors.add('ansible')
        elif '@' in author:
            # match github ids but not emails
            authors.update(re.findall(r'(?<!\w)@([\w-]+)(?![\w.])', author))
        elif 'github.com/' in author:
            # {'author': 'Henrique Rodrigues (github.com/Sodki)'}
            idx = author.find('github.com/')
            author = author[idx+11:]
            authors.add(author.replace(')', ''))
        elif '(' in author and len(author.split()) == 3:
            # Mathieu Bultel (matbu)
            idx = author.find('(')
            author = author[idx+1:]
            authors.add(author.replace(')', ''))

        # search for emails
        for email in re.findall(r'[<(]([^@]+@[^)>]+)[)>]', author):
            github_id = self.emails_cache.get(email)
            if github_id:
                authors.add(github_id)

        return list(authors)

    def fuzzy_match(self, repo=None, title=None, component=None):
        '''Fuzzy matching for modules'''

        # https://github.com/ansible/ansible/issues/18179
        if 'validate-modules' in component:
            return None

        # https://github.com/ansible/ansible/issues/20368
        if 'module_utils' in component:
            return None

        # authorized_keys vs. authorized_key
        if component and component.endswith('s'):
            tm = self.find_match(component[:-1])
            if tm:
                return tm['name']

        match = None
        known_modules = []

        for k,v in self.modules.iteritems():
            known_modules.append(v['name'])

        title = title.lower()
        title = title.replace(':', '')
        title_matches = [x for x in known_modules if x + ' module' in title]

        if not title_matches:
            title_matches = [x for x in known_modules
                             if title.startswith(x + ' ')]
            if not title_matches:
                title_matches = \
                    [x for x in known_modules if ' ' + x + ' ' in title]

        # don't do singular word matching in title for ansible/ansible
        cmatches = None
        if component:
            cmatches = [x for x in known_modules if x in component]
            cmatches = [x for x in cmatches if not '_' + x in component]

            # use title ... ?
            if title_matches:
                cmatches = [x for x in cmatches if x in title_matches]

            if cmatches:
                if len(cmatches) >= 1:
                    match = cmatches[0]
                if not match:
                    if 'docs.ansible.com' in component:
                        pass
                    else:
                        pass
                print("module - component matches: %s" % cmatches)

        if not match:
            if len(title_matches) == 1:
                match = title_matches[0]
            else:
                print("module - title matches: %s" % title_matches)

        return match

    def is_multi(self, rawtext):
        '''Is the string a list or a glob of modules?'''
        if rawtext:
            lines = rawtext.split('\n')

            # clean up lines
            lines = [x.strip() for x in lines if x.strip()]
            lines = [x for x in lines if len(x) > 2]

            if len(lines) > 1:
                return True

            if lines:
                if lines[0].strip().endswith('*'):
                    return True

        return False

    # https://github.com/ansible/ansible-modules-core/issues/3831
    def multi_match(self, rawtext):
        '''Return a list of matches for a given glob or list of names'''
        matches = []
        lines = rawtext.split('\n')
        lines = [x.strip() for x in lines if x.strip()]
        for line in lines:
            # is it an exact name, a path, a globbed name, a globbed path?
            if line.endswith('*'):
                thiskey = line.replace('*', '')
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
        for k,v in self.modules.iteritems():
            if not v['filepath']:
                continue
            mfile = os.path.join(self.checkoutdir, v['filepath'])
            if not mfile.endswith('.py'):
                # metadata is only the .py files ...
                ext = mfile.split('.')[-1]
                mfile = mfile.replace('.' + ext, '.py', 1)

            self.modules[k]['metadata'].update(self.get_module_metadata(mfile))

    def get_module_metadata(self, module_file):
        meta = {}

        if not os.path.isfile(module_file):
            return meta

        rawmeta = ''
        inphase = False
        with open(module_file, 'rb') as f:
            for line in f:
                if line.startswith('ANSIBLE_METADATA'):
                    inphase = True
                    #continue
                if line.startswith('DOCUMENTATION'):
                    break
                if inphase:
                    rawmeta += line
        rawmeta = rawmeta.replace('ANSIBLE_METADATA =', '', 1)
        rawmeta = rawmeta.strip()
        try:
            meta = ast.literal_eval(rawmeta)
        except SyntaxError:
            pass

        return meta

    def set_module_imports(self):
        for k,v in self.modules.iteritems():
            if not v['filepath']:
                continue
            mfile = os.path.join(self.checkoutdir, v['filepath'])
            self.modules[k]['imports'] = self.get_module_imports(mfile)

    def get_module_imports(self, module_file):

        #import ansible.module_utils.nxos
        #from ansible.module_utils.netcfg import NetworkConfig, dumps
        #from ansible.module_utils.network import NetworkModule

        mimports = []

        if not os.path.isfile(module_file):
            return mimports

        else:
            with open(module_file, 'rb') as f:
                for line in f:
                    line = line.strip()
                    line = line.replace(',', '')
                    if line.startswith('import') or \
                            ('import' in line and 'from' in line):
                        lparts = line.split()
                        if line.startswith('import '):
                            mimports.append(lparts[1])
                        elif line.startswith('from '):
                            mpath = lparts[1] + '.'
                            for spath in lparts[3:]:
                                mimports.append(mpath + spath)

            return mimports

    @property
    def all_maintainers(self):
        maintainers = set()
        for path, metadata in self.botmeta['files'].items():
            maintainers.update(metadata.get('maintainers', []))
        return maintainers

    def get_maintainers_for_namespace(self, namespace):
        maintainers = []
        for k,v in self.modules.items():
            if 'namespace' not in v or 'maintainers' not in v:
                continue
            if v['namespace'] == namespace:
                for m in v['maintainers']:
                    if m not in maintainers:
                        maintainers.append(m)
        maintainers = [x for x in maintainers if x.strip()]
        return maintainers

    @staticmethod
    def replace_ansible(maintainers, ansible_members, bots=[]):
        '''Replace -ansible- with the -humans- in the org'''
        newlist = []
        for m in maintainers:
            if m != 'ansible':
                newlist.append(m)
            else:
                newlist += ansible_members
        newlist = sorted(set(newlist))
        newlist = [x for x in newlist if x not in bots]
        return newlist

    def get_file_content(self, filepath):
        fpath = os.path.join(self.checkoutdir, filepath)
        if not os.path.isfile(fpath):
            return None
        with open(fpath, 'rb') as f:
            data = f.read()
        return data
