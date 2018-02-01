#!/usr/bin/env python

import datetime
from distutils.version import LooseVersion


def get_deprecation_facts(issuewrapper, meta, versionindexer):

	# https://github.com/ansible/ansible/blob/devel/lib/ansible/modules/cloud/docker/_docker.py#L21-L24
    #deprecated:
    #   removed_in: "2.4"
    #   why: Replaced by dedicated modules.
    #   alternative: Use M(docker_container) and M(docker_image) instead.

    dmeta = {
        'is_deprecated': False,
        'deprecation_action': None
    }

    iw = issuewrapper

    if len(meta['component_matches']) != 1:
        return dmeta

    cm = meta['component_matches'][0]
    if cm.get('deprecated'):
        dmeta['is_deprecated'] = True

        if 'removed_in' not in cm['deprecation_info']:
            return dmeta

        if not versionindexer.is_valid_version(cm['deprecation_info']['removed_in']):
            return dmeta

        dversion = LooseVersion(cm['deprecation_info']['removed_in'])
        dversion = [int(x) for x in dversion.version]
        current = LooseVersion(versionindexer.version_by_date(datetime.datetime.now()))
        current = [int(x) for x in current.version]

        if len(dversion) == 2:
            dversion.append(0)
        if len(current) == 2:
            current.append(0)

        df_bpd = iw.history.last_date_for_boilerplate('needs_info_base')

    #import epdb; epdb.st()
    return dmeta
