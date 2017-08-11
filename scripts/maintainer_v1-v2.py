#!/usr/bin/env python

import json
import os
import pickle
import string
import subprocess
import sys
import requests
import requests_cache
import tempfile

from collections import OrderedDict
from pprint import pprint

from ansibullbot.triagers.ansible import AnsibleTriage
from ansibullbot.utils.file_tools import FileIndexer
from ansibullbot.utils.moduletools import ModuleIndexer

from ruamel.yaml import YAML as rYAML

requests_cache.install_cache('r_cache')

HEADER = """# BOTMETA V2.0
#
# Data used by ansibot to indentify who works on each file in the repo.
# If you have questions about this data format, please join #ansible-devel
# on irc.freenode and ping anyone who is op'ed.
#
# There are 2 primary sections of the data
#
#   macros
#       Macros are used to shorten and group some strings and lists.
#       Any macro with a prefix of "team_" is a maintainer group for
#       various files.
#
#   files
#       Each key represents a specific file in the repository.
#       If a module is not listed, it's maintainers default to the authors
#       If the file has no maintainers key, the value of the key is
#       presumed to be the maintainers.
#
#       Keys:
#           maintainers - these people can shipit and automerge
#           notified - these people are always subscribed to relevant issues
#           ignored - these people should never be notified
#           deprecated - this file is deprecated but probably not yet renamed
#           keywords - used to identify this file based on the issue description
#           support - used for files without internal metadata
#
"""

def get_maintainers_mapping():
    MAINTAINERS_FILES = ['MAINTAINERS.txt']
    maintainers = {}
    for fname in MAINTAINERS_FILES:
        if not os.path.isfile(fname):
            import ansibullbot.triagers.ansible as at
            basedir = os.path.dirname(at.__file__)
            basedir = os.path.dirname(basedir)
            basedir = os.path.dirname(basedir)
            fname = os.path.join(basedir, fname)
            if not os.path.isfile(fname):
                continue

        with open(fname, 'rb') as f:
            for line in f.readlines():
                #print(line)
                owner_space = (line.split(': ')[0]).strip()
                maintainers_string = (line.split(': ')[-1]).strip()
                maintainers[owner_space] = maintainers_string.split(' ')

    # meta is special
    maintainers['meta'] = ['ansible']
    return maintainers


def run_command(cmd):
    p = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    (so, se) = p.communicate()
    return (p.returncode, so, se)

def get_removed_maintainers():

    removed = {}

    cmd = 'git log --follow MAINTAINERS.txt'
    (rc, so, se) = run_command(cmd)
    commits = [x for x in so.split('\n') if x.startswith('commit ')]
    commits = [x.split()[-1] for x in commits]
    commits = commits[::-1]

    commits.remove('db17f02ec0ac7e3f6101bce609ea95b75684a673')
    commits.remove('967360e12292f5e1fe2179478b5dfeb51b81a718')


    for commit in commits:

        cmd = 'git log -1 -p %s' % commit
        (rc, so, se) = run_command(cmd)

        if 'maintainer' not in so.lower() and 'remove' in so.lower():
            continue

        lines = so.split('\n')
        inphase = False
        patchlines = []
        for idx,x in enumerate(lines):

            if x.startswith('diff --git'):
                if 'MAINTAINER' in x:
                    inphase = True
                else:
                    inphase = False


            if 'MAINTAINERS.txt' in x:
                continue
            if 'ansible_tower' in x or 'web_infrastructure' in x:
                continue
            if not inphase:
                continue

            patchlines.append(x)

            if x.startswith('---'):
                continue

            if x.startswith('-') and not x.strip().endswith('-'):
                if not lines[idx+1].startswith('+'):
                    """
                    nx = x.replace('-', '')
                    nx = nx.replace(':', '')
                    nx = nx.replace('@', '')
                    nx = nx.replace('DEPRECATED', '')
                    xp = [y.strip() for y in nx.split() if y.strip()]
                    if not xp:
                        continue
                    if len(xp) > 1:
                        bn = os.path.basename(xp[0])
                        if bn not in removed:
                            removed[bn] = []
                        removed[bn] += xp[1:]
                        #if xp[0] == 'web_infrastructure/ansible_tower/':
                        #    import epdb; epdb.st()

                        '''
                        pprint(patchlines)
                        print(bn)
                        pprint(xp[1:])
                        import epdb; epdb.st()
                        '''
                    """
                    pass
                else:

                    f1 = x.split(':')[0]
                    f1 = f1.replace('-', '')
                    f2 = lines[idx+1]
                    f2 = f2.split(':')[0]
                    f2 = f2.replace('+', '')

                    if f1 != f2:
                        continue

                    names1 = x.split(':')[1]
                    names1 = [y.strip() for y in names1.split() if y.strip()]
                    names2 = lines[idx+1].split(':')[1]
                    names2 = [y.strip() for y in names2.split() if y.strip()]

                    rx = []
                    for n1 in names1:
                        if n1 in ['NONE', 'DEPRECATED', 'ansible']:
                            continue
                        if n1 not in names2:
                            rx.append(n1)

                    if rx:
                        #pprint(patchlines)
                        if f1 not in removed:
                            removed[f1] = []
                        removed[f1] += rx
                        #import epdb; epdb.st()

    #import epdb; epdb.st()
    return removed


def main():
    pprint(sys.argv)
    dest = sys.argv[1]
    print('dest: %s' % dest)

    # get_valid_labels('ansible/ansible')
    # /home/jtanner/.ansibullbot/cache/ansible/ansible/labels.pickle

    with open(os.path.expanduser('~/.ansibullbot/cache/ansible/ansible/labels.pickle'), 'rb') as f:
        labels = pickle.load(f)
    valid_labels = [x.name for x in labels[1]]

    FILEMAP_FILENAME = 'FILEMAP.json'
    COMPONENTMAP_FILENAME = 'COMPONENTMAP.json'
    FI = FileIndexer(
        checkoutdir=os.path.expanduser(
            '~/.ansibullbot/cache/ansible.files.checkout'
        ),
        cmap=COMPONENTMAP_FILENAME,
    )

    module_cache_file = '/tmp/mi-modules.json'
    if not os.path.isfile(module_cache_file):
        module_maintainers = get_maintainers_mapping()
        MI = ModuleIndexer(maintainers=module_maintainers)
        MI.get_ansible_modules()
        with open(module_cache_file, 'wb') as f:
            f.write(json.dumps(MI.modules, sort_keys=True, indent=2))
        modules = MI.modules
    else:
        with open(module_cache_file, 'rb') as f:
            modules = json.loads(f.read())

    macro_teams = {
        'Qalthos,gundalow,privateip': 'openswitch',
        'Qalthos,ganeshrn,gundalow,privateip,rcarrillocruz,trishnaguha': 'networking',
        'GGabriele,jedelman8,mikewiebe,privateip,rahushen,rcarrillocruz,trishnaguha': 'nxos',
        'emonty,j2sol,juliakreger,rcarrillocruz,shrews,thingee': 'openstack',
        'chrishoffman,manuel-sousa,romanek-adam': 'rabbitmq',
        'alikins,barnabycourt,flossware,vritant': 'rhn',
        'Qalthos,amitsi,gundalow,privateip': 'netvisor',
        'haroldwongms,nitzmahone,tstringer': 'azure',
        'dagwieers,jborean93,jhawkesworth': 'windows',
        'dagwieers,dav1x,jctanner,nerzhul': 'vmware',
        'isharacomix,jrrivers,privateip': 'cumulus',
        'chiradeep,giorgos-nikolopoulos': 'netscaler',
        'ericsysmin,grastogi23,khaltore': 'avi',
        'ghjm,jlaska,matburt,wwitzel3': 'tower',
        'hulquest,lmprice: 'netapp',
    }

    usermap = {
        'mpdehaan': False
    }
    namemap = {
        'Shrews': 'shrews'
    }
    exclusions = {
        '*': ['chouseknecht', 'Java1Guy', 'franckcuny', 'mhite', 'bennojoy', 'risaacson', 'whenrik'],
        'network/wakeonlan': ['dagwiers'],
    }

    removed = get_removed_maintainers()

    teams = {}
    data = {}
    data['files'] = {}

    # merge the moduleindexer data
    for k,v in modules.items():
        fp = v.get('filepath')
        if not fp or not fp.startswith('lib/ansible'):
            continue
        data['files'][k] = {}
        if v['_maintainers']:
            data['files'][k]['maintainers'] = []
            data['files'][k]['maintainers'] = [x for x in v['_maintainers']]
        if v['authors']:
            if 'maintainers' not in data['files'][k]:
                data['files'][k]['maintainers'] = []
            data['files'][k]['maintainers'] += v['authors']
            data['files'][k]['maintainers'] = sorted(set(data['files'][k]['maintainers']))

        # validate each maintainer exists
        if 'maintainers' in data['files'][k]:
            maintainers = []
            for x in data['files'][k]['maintainers']:

                if x in exclusions['*']:
                    continue

                if x in namemap:
                    x = namemap[x]
                if x in usermap:
                    if usermap[x]:
                        maintainers.append(x)
                else:
                    if x == 'ansible':
                        usermap['ansible'] = True
                        maintainers.append(x)
                        continue
                    res = requests.get('https://github.com/%s' % x)
                    if res.status_code == 200:
                        usermap[x] = True
                        maintainers.append(x)
                    else:
                        usermap[x] = False
            data['files'][k]['maintainers'] = sorted(set(maintainers))
            if not data['files'][k]['maintainers']:
                data['files'][k].pop('maintainers', None)

    # merge the removed people
    for k,v in removed.items():
        k = os.path.join('lib/ansible/modules', k)
        v = sorted(set(v))
        if k in data['files']:
            if 'maintainers' in data['files'][k]:
                for vx in v:
                    if vx in data['files'][k]['maintainers']:
                        data['files'][k]['maintainers'].remove(vx)
                        if 'ignored' not in data['files'][k]:
                            data['files'][k]['ignored'] = []
                        data['files'][k]['ignored'].append(vx)
                if not data['files'][k]['maintainers']:
                    data['files'][k].pop('maintainers', None)
                    #import epdb; epdb.st()

    # merge the fileindexer data
    for k in FI.files:
        #if 'contrib/inventory' in k:
        #    import epdb; epdb.st()
        #print(k)
        try:
            klabels = FI.get_component_labels(valid_labels, [k])
            if klabels:
                klabels = [x for x in klabels if not x.startswith('c:')]
                if not klabels:
                    continue
                if k not in data['files']:
                    data['files'][k] = {}
                if 'labels' not in data['files'][k]:
                    data['files'][k]['labels'] = []
                data['files'][k]['labels'] += klabels
        except UnicodeDecodeError:
            continue

        keywords = FI.get_keywords_for_file(k)
        if keywords:
            if k not in data['files']:
                data['files'][k] = {}
            if 'keywords' not in data['files'][k]:
                data['files'][k]['keywords'] = []
            data['files'][k]['keywords'] += keywords
            #import epdb; epdb.st()

    '''
    # calculate all teams
    for k,v in data['files'].items():
        if not v.get('maintainers'):
            continue
        maintainers = sorted(set(v['maintainers']))
        key = ','.join(maintainers)
        if key not in teams:
            teams[key] = []
        teams[key].append(k)

    # rank and show
    steams = sorted(teams, key=len, reverse=True)
    for x in steams[0:15]:
        if x in macro_teams:
            continue
        pprint(teams[x])
        print(x)
        import epdb; epdb.st()
    import epdb; epdb.st()
    '''

    for k,v in data['files'].items():
        if not v.get('maintainers'):
            continue
        maintainers = v.get('maintainers')
        for idx,x in enumerate(maintainers):
            if x == 'ansible':
                maintainers[idx] = '$team_ansible'
        if maintainers == ['$team_ansible']:
            data['files'][k]['maintainers'] = ' '.join(maintainers)
            continue
        if len(maintainers) == 1:
            data['files'][k]['maintainers'] = ' '.join(maintainers)
            continue
        mkey = ','.join(sorted(set(maintainers)))
        if mkey in macro_teams:
            maintainers = ['$team_%s' % macro_teams[mkey]]
            data['files'][k]['maintainers'] = ' '.join(maintainers)
        else:
            # partial matching
            match = None
            subnames = sorted(set(maintainers))
            for sn in subnames:
                filtered = [x for x in subnames if x != sn]
                fkey = ','.join(filtered)
                if fkey in macro_teams:
                    match = fkey
            if match:
                to_clear = match.split(',')
                maintainers = [x for x in maintainers if x not in to_clear]
                data['files'][k]['maintainers'] = ' '.join(maintainers)

    # fix deprecations
    safe_names = [x for x in FI.files if all(c in string.printable for c in x)]
    remove = []
    for k,v in data['files'].items():
        maintainers = v.get('maintainers')
        if maintainers:
            if 'DEPRECATED' in data['files'][k]['maintainers']:
                data['files'][k].pop('maintainers', None)
                data['files'][k]['deprecated'] = True
        bn = os.path.basename(k)
        if bn.startswith('_') and bn != '__init__.py' and '/modules/' in k:
            '''
            data['files'][k]['deprecated'] = True
            if 'maintainers' in data['files'][k]:
                data['files'][k].pop('maintainers', None)
            '''
            remove.append(k)

        # get rid of files no longer in the repo
        if k not in safe_names:
            remove.append(k)

    for x in remove:
        data['files'].pop(x, None)


    # remove any keys where maintainers == authors
    remove = []
    for k,v in data['files'].items():
        if v.keys() != ['maintainers']:
            continue
        if v['maintainers'] != modules[k]['authors']:
            continue
        remove.append(k)
    for x in remove:
        data['files'].pop(x, None)

    #####################################
    # add special notifies
    #####################################
    data['files']['lib/ansible/modules/cloud/amazon/'] = {
        'notify': ['willthames']
    }

    #####################################
    # reduce to namespace maintainers
    #####################################
    groups = {}
    for k,v in data['files'].items():
        dn = os.path.dirname(k)
        if dn not in groups:
            groups[dn] = {
                'matches': [],
                'values': []
            }
        groups[dn]['matches'].append(k)
        if v not in groups[dn]['values']:
            groups[dn]['values'].append(v)
    for k,v in groups.items():
        if not len(v['values']) == 1:
            continue
        if len(v['matches']) == 1:
            continue
        #print(k)
        #pprint(v)

        newk = k + '/'
        data['files'][newk] = v['values'][0]
        for pf in v['matches']:
            data['files'].pop(pf, None)

        if newk in removed:
            import epdb; epdb.st()


    #####################################
    # make a sorted dict
    #####################################

    files = data['files']
    data['files'] = OrderedDict()
    fkeys = sorted(files.keys())
    fkeys = [x.replace('lib/ansible/modules', '$modules') for x in fkeys]
    fkeys = sorted(set(fkeys))
    for fkey in fkeys:
        if fkey.startswith('$modules'):
            mkey = fkey.replace('$modules', 'lib/ansible/modules')
            data['files'][fkey] = files[mkey]
        else:
            data['files'][fkey] = files[fkey]

    data['macros'] = OrderedDict()
    data['macros']['modules'] = 'lib/ansible/modules'
    macro_items = macro_teams.items()
    macro_items = [[x[1],x[0]] for x in macro_items]
    macro_dict ={}
    for x in macro_items:
        macro_dict[x[0]] = x[1]

    data['macros']['team_ansible'] = []
    keys = macro_dict.keys()
    for k in sorted(keys):
        team = macro_dict[k]
        team = team.split(',')
        if len(team) < 10:
            team = " ".join(team)
        data['macros']['team_%s' % k] = team

    # if maintainers is the only subkey, make the primary value a string
    for k,v in data['files'].items():
        keys = v.keys()
        if keys == ['maintainers']:
            if isinstance(v['maintainers'], list):
                data['files'][k] = " ".join(v['maintainers'])
            else:
                data['files'][k] = v['maintainers']
        for xk in ['ignored', 'notified', 'maintainers']:
            if xk in data['files'][k]:
                if not isinstance(data['files'][k][xk], (str, unicode)):
                    data['files'][k][xk] = " ".join(data['files'][k][xk])


    # write it once with ryaml to make it ordered
    ryaml = rYAML()
    (fo, fn) = tempfile.mkstemp()
    with open(fn, 'wb') as f:
        ryaml.dump(data, f)

    # read it back in
    with open(fn, 'rb') as f:
        ylines = f.readlines()

    phase = None
    for idx,x in enumerate(ylines):
        x = x.rstrip()
        x = x.replace('!!omap', '')
        if x.endswith(' {}'):
            x = x.replace(' {}', '')
        if x.startswith('-'):
            x = x.replace('-', ' ', 1)
        ylines[idx] = x


        if x.startswith(' ') and ':' not in x and '-' not in x:
            ylines[idx-1] += ' ' + x.strip()
            ylines[idx] = ''

    ylines = [x for x in ylines if x.strip()]
    ylines = [HEADER] + ylines

    with open(dest, 'wb') as f:
        f.write('\n'.join(ylines))

if __name__ == "__main__":
    main()
