#!/usr/bin/env python

import logging


def get_contributor_facts(issuewrapper):

    # https://github.com/blog/2397-making-it-easier-to-grow-communities-on-github
    # NONE - new contributor
    # MEMBER - member of a team
    # CONTRIBUTOR - made previous commits

    cfacts = {
        u'new_contributor': False
    }

    iw = issuewrapper

    # ignore issues
    if iw.is_issue():
        return cfacts

    association = iw.pull_raw.get(u'author_association').upper()
    logging.info(u'{} {} association: {}'.format(iw.html_url, iw.submitter, association))

    if association in [u'NONE', u'FIRST_TIME_CONTRIBUTOR']:
        cfacts[u'new_contributor'] = True

    return cfacts
