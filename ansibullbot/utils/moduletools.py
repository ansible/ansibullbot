import copy
import logging
import os
import pickle

from sqlalchemy import create_engine
from sqlalchemy import Column
from sqlalchemy import Integer
from sqlalchemy import String
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

from ansibullbot._text_compat import to_text
from ansibullbot.utils.extractors import ModuleExtractor
from ansibullbot.utils.systemtools import run_command
from ansibullbot.utils.timetools import strip_time_safely


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


class ModuleIndexer:

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

    def __init__(self, commits=True, blames=True, botmeta=None, gh_client=None, cachedir='~/.ansibullbot/cache', gitrepo=None):
        self.get_commits = commits
        self.get_blames = blames
        botmeta = botmeta if botmeta else {}
        self.gqlc = gh_client
        self.scraper_cache = os.path.expanduser(os.path.join(cachedir, 'ansible.modules.scraper'))
        self.gitrepo = gitrepo

        self.modules = {}  # keys: paths of files belonging to the repository

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

        self.update(botmeta)

    def update(self, botmeta=None):
        if botmeta is not None:
            self.botmeta = botmeta
        self.get_ansible_modules()

    def get_ansible_modules(self):
        """Make a list of known modules"""

        matches = []
        module_dir = os.path.join(self.gitrepo.checkoutdir, 'lib/ansible/modules')
        module_dir = os.path.expanduser(module_dir)
        for root, _, filenames in os.walk(module_dir):
            for filename in filenames:
                if 'lib/ansible/modules' in root and not filename == '__init__.py':
                    matches.append(os.path.join(root, filename))

        matches = sorted(set(matches))

        self.populate_modules(matches)

        # custom fixes
        newitems = []
        for k, v in self.modules.items():

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

        # parse imports
        logging.debug('set module imports')
        self.set_module_imports()

        # last modified
        if self.get_commits:
            logging.debug('set module commits')
            self.get_module_commits()

        # parse blame
        if self.get_blames and self.get_commits:
            logging.debug('set module blames')
            self.get_module_blames()

        # depends on metadata now ...
        logging.debug('set module maintainers')
        self.set_maintainers()

        return self.modules

    def populate_modules(self, matches):
        # figure out the names
        for match in matches:
            mdict = copy.deepcopy(self.EMPTY_MODULE)

            mdict['filename'] = os.path.basename(match)

            dirpath = os.path.dirname(match)
            dirpath = dirpath.replace(self.gitrepo.checkoutdir + '/', '')
            mdict['dirpath'] = dirpath

            filepath = match.replace(self.gitrepo.checkoutdir + '/', '')
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
                k.replace('/', '_') + '.commits.pickle'
            )

            if not os.path.isfile(pfile):
                refresh = True
            else:
                logging.debug(pfile)
                with open(pfile, 'rb') as f:
                    pdata = pickle.load(f)
                if pdata[0] == mtime:
                    self.commits[k] = pdata[1]
                else:
                    refresh = True

            if refresh:
                logging.info('refresh commit cache for %s' % k)
                cmd = 'cd %s; git log --follow %s' % (self.gitrepo.checkoutdir, k)
                (rc, so, se) = run_command(cmd)
                for line in to_text(so).split('\n'):
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
                        commit['date'] = strip_time_safely(to_text(dstr))
                        self.commits[k].append(commit)

                with open(pfile, 'wb') as f:
                    pickle.dump((mtime, self.commits[k]), f)

    def last_commit_for_file(self, filepath):
        if filepath in self.commits and 'hash' in self.commits[filepath][0]:
            return self.commits[filepath][0]['hash']

        # git log --pretty=format:'%H' -1
        # lib/ansible/modules/cloud/amazon/ec2_metric_alarm.py
        cmd = 'cd %s; git log --pretty=format:\'%%H\' -1 %s' % \
            (self.gitrepo.checkoutdir, filepath)
        (rc, so, se) = run_command(cmd)
        return to_text(so).strip()

    def get_module_blames(self):

        logging.debug('build email cache')
        emails_cache = self.session.query(Email)
        emails_cache = [(x.email, x.login) for x in emails_cache]
        self.emails_cache = dict(emails_cache)

        logging.debug('build blame cache')
        blame_cache = self.session.query(Blame).all()
        blame_cache = [x.file_commit for x in blame_cache]
        blame_cache = sorted(set(blame_cache))

        logging.debug('eval module hashes')
        changed = False
        keys = sorted(self.modules.keys())
        for k in keys:
            if k not in self.gitrepo.files:
                self.committers[k] = {}
                continue

            ghash = self.last_commit_for_file(k)

            if ghash in blame_cache:
                continue

            logging.debug(f'checking hash for {k}')
            res = self.session.query(Blame).filter_by(file_name=k, file_commit=ghash).all()
            hashes = [x.file_commit for x in res]

            if ghash not in hashes:

                logging.debug(f'hash {ghash} not found for {k}, updating blames')

                scraper_args = ['ansible', 'ansible', 'devel', k]
                uns, emailmap = self.gqlc.get_usernames_from_filename_blame(*scraper_args)

                # check the emails
                for email, login in emailmap.items():
                    if email in self.emails_cache:
                        continue
                    exists = self.session.query(Email).filter_by(email=email).first()
                    if not exists:
                        logging.debug(f'insert {login}:{email}')
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
                            logging.debug(f'insert {k}:{commit}:{login}')
                            _blame = Blame(**kwargs)
                            self.session.add(_blame)
                            changed = True

        if changed:
            self.session.commit()
            logging.debug('re-build email cache')
            emails_cache = self.session.query(Email)
            emails_cache = [(x.email, x.login) for x in emails_cache]
            self.emails_cache = dict(emails_cache)

        # fill in what we can ...
        logging.debug('fill in commit logins')
        for k in keys:
            for idc, commit in enumerate(self.commits[k][:]):
                if not commit.get('login'):
                    continue
                login = self.emails_cache.get(commit['email'])
                if not login and '@users.noreply.github.com' in commit['email']:
                    login = commit['email'].split('@')[0]
                    self.emails_cache[commit['email']] = login
                if not login:
                    logging.debug('unknown: {}'.format(commit['email']))
                self.commits[k][idc]['login'] = self.emails_cache.get(login)

    def set_maintainers(self):
        '''Define the maintainers for each module'''

        # grep the authors:
        for k, v in self.modules.items():
            if v['filepath'] is None:
                continue
            mfile = os.path.join(self.gitrepo.checkoutdir, v['filepath'])
            authors = ModuleExtractor(mfile, email_cache=self.emails_cache).get_module_authors()
            self.modules[k]['authors'] = authors

            # authors are maintainers by -default-
            self.modules[k]['maintainers'] += authors
            self.modules[k]['maintainers'] = \
                sorted(set(self.modules[k]['maintainers']))

        metadata = self.botmeta['files'].keys()
        for k, v in self.modules.items():
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
        for k, v in self.modules.items():
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

    def set_module_imports(self):
        for k, v in self.modules.items():
            if not v['filepath']:
                continue
            mfile = os.path.join(self.gitrepo.checkoutdir, v['filepath'])
            self.modules[k]['imports'] = self.get_module_imports(mfile)

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
        for path, metadata in self.botmeta['files'].items():
            maintainers.update(metadata.get('maintainers', []))
        return maintainers

    def get_maintainers_for_namespace(self, namespace):
        maintainers = []
        for k, v in self.modules.items():
            if 'namespace' not in v or 'maintainers' not in v:
                continue
            if v['namespace'] == namespace:
                for m in v['maintainers']:
                    if m not in maintainers:
                        maintainers.append(m)
        maintainers = [x for x in maintainers if x.strip()]
        return maintainers
