#!/usr/bin/env python

import logging


def get_contributor_facts(issuewrapper):

    # https://github.com/blog/2397-making-it-easier-to-grow-communities-on-github
    # NONE - new contributor
    # MEMBER - member of a team
    # CONTRIBUTOR - made previous commits

    cfacts = {
        'new_contributor': False
    }

    iw = issuewrapper

    # ignore issues
    if iw.is_issue():
        return cfacts

    association = iw.pull_raw.get('author_association')
    logging.info('{} {} association: {}'.format(iw.html_url, iw.submitter, association))

    if association == 'NONE':
        cfacts['new_contributor'] = True

    return cfacts
