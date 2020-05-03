#!/usr/bin/env python

import os

import yaml
import logzero
from logzero import logger
from pprint import pprint

from ansibullbot.parsers.botmetadata import BotMetadataParser
from ansibullbot.utils.git_tools import GitRepoWrapper
from ansibullbot.utils.galaxy import GalaxyQueryTool


def main():

    logzero.logfile('/tmp/routing_botmeta_migration_errors.log')

    gitrepo = GitRepoWrapper(cachedir='/tmp/ansible.checkout', repo='https://github.com/ansible/ansible')
    ansible29 = GitRepoWrapper(
        cachedir='/tmp/ansible.checkout.29',
        repo='https://github.com/ansible/ansible',
        commit='a76d78f6919f62698341be2f102297a2ce30897c',
    )

    GQT = GalaxyQueryTool(cachedir='/tmp/gqt.cache')
    GQT.BLACKLIST_FQCNS = []
    GQT.index_ecosystem()


    botmeta = BotMetadataParser.parse_yaml(gitrepo.get_file_content('.github/BOTMETA.yml'))
    botmeta_errors = []
    bmkeys = sorted(list(botmeta['files'].keys()))
    for k in bmkeys:
        if k.startswith('test/'):
            continue
        if os.path.basename(k) == "__init__.py":
            continue
        v = botmeta['files'][k]
        if 'migrated_to' in v or 'migrated' in v:
            mts = v['migrated_to']
            if not mts:
                continue
            gres = GQT.search_galaxy(k)
            if gres:
                fqcns = [x.split(':')[1] for x in gres]
                found = False
                for mt in mts:
                    if mt in fqcns:
                        found = True
                if not found and fqcns:
                    msg = 'BOTMETA: BE1 %s is not in %s but was found in %s' % (k, mts, fqcns)
                    logger.error(msg)
                    botmeta_errors.append(msg)
                elif not found:
                    msg = 'BOTMETA: BE2 %s is not in %s' % (k, mts)
                    logger.error(msg)
                    botmeta_errors.append(msg)
            else:

                fgres = GQT.fuzzy_search_galaxy(k)
                if fgres:
                    msg = 'BOTMETA: BE3 %s was not found in galaxy but looks similar to %s' % (k, fgres)
                else:
                    msg = 'BOTMETA: BE4 %s was not found in galaxy' % k
                logger.error(msg)
                botmeta_errors.append(msg)

    routing = gitrepo.get_file_content('lib/ansible/config/routing.yml')
    routing = yaml.load(routing)
    routing_errors = []
    for k,v in routing['plugin_routing'].items():
        if 'module' in k:
            dirname = os.path.join('lib', 'ansible', k)
        else:
            dirname = os.path.join('lib', 'ansible', 'plugins', k)
        if not gitrepo.isdir(dirname):
            logger.error(dirname)

        dirfiles = [x for x in ansible29.files if dirname in x]
        pnames = sorted(list(v.keys()))
        for pname in pnames:
            pdata = v[pname]
            routing_fqcp = pdata['redirect']

            pfiles = [x for x in dirfiles if '/' + pname + '.py' in x or '/' + '_' + pname + '.py' in x]
            if not pfiles:
                msg = 'ROUTING: RE1 can not find %s:%s in 2.9' % (dirname, pname)
                logger.error(msg)
                routing_errors.append(msg)
                continue

            if len(pfiles) > 1:
                msg = 'ROUTING: RE2 %s:%s has too many original matching files: %s' % (dirname, pname, len(pfiles))
                logger.error(msg)
                routing_errors.append(msg)
                continue

            pfile = pfiles[0]
            gres = GQT.search_galaxy(pfile)
            if not gres:
                fgres = GQT.fuzzy_search_galaxy(pfile)
                if fgres:
                    msg = "ROUTING: RE3 %s:%s is not in %s nor any other collections but looks similar to %s" % (k, pname, routing_fqcp, fgres)
                else:
                    msg = "ROUTING: RE3 %s:%s is not in %s nor any other collections" % (k, pname, routing_fqcp)
                logger.error(msg)
                routing_errors.append(msg)
                continue

            matched = False
            misses = []
            for res in gres:
                parts = res.split(':')
                fqcp = parts[1] + '.' + os.path.basename(parts[-1]).split('.')[0]
                if fqcp == routing_fqcp:
                    matched = True
                else:
                    misses.append(fqcp)

            if not matched and misses:
                msg = "ROUTING: RE4 %s:%s is not in %s but was found in %s" % (k, pname, routing_fqcp, misses)
                logger.error(msg)
                routing_errors.append(msg)


    print('DONE!')
    #import epdb; epdb.st()


if __name__ == "__main__":
    main()
