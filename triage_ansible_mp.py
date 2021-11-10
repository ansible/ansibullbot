#!/usr/bin/env python
#
# This file is part of Ansible
#
# Ansible is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Ansible is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Ansible. If not, see <http://www.gnu.org/licenses/>.

from __future__ import print_function

import datetime
import json
import os
import sys
import tempfile

from itertools import zip_longest
from multiprocessing import Process

from logzero import logger
from ansibullbot.ansibletriager import AnsibleTriager


def run_triage_worker(numbers):
    thispid = os.getpid()
    logger.info('%s started with %s numbers' % (str(thispid), len(numbers)))
    tfh,tfn = tempfile.mkstemp(suffix='.json')
    #logger.info('%s %s' % (thispid, tfh))
    logger.info('%s %s' % (thispid, tfn))

    with open(tfn, 'w') as f:
        f.write(json.dumps(numbers))

    args = sys.argv[1:]
    args.append('--id=%s' % tfn)
    logger.info(args)

    triager = AnsibleTriager(args=args, update_checkouts=False)
    triager.run()

    os.remove(tfn)
    return (tfn)


def grouper(n, iterable, padvalue=None):
    return zip_longest(*[iter(iterable)]*n, fillvalue=padvalue)


def main():

    workercount = 8

    ts1 = datetime.datetime.now()

    # Run the triager ...
    #AnsibleTriage(args=sys.argv[1:]).start()

    # init just creates all the tools ...
    parent = AnsibleTriager(args=sys.argv[1:])

    # collect_repos() gets all the issues to be triaged ...
    parent.collect_repos()

    # get the issue numbers
    numbers = parent.repos['ansible/ansible']['issues'].numbers[:]

    # make a range of numbers for each worker
    chunks = grouper(int(len(numbers) / (workercount - 1)), numbers)
    chunks = list(chunks)

    # start each worker with it's numbers
    pids = []
    for chunk in chunks:
        p = Process(target=run_triage_worker, args=(chunk,))
        pids.append(p)
    [x.start() for x in pids]
    [x.join() for x in pids]

    ts2 = datetime.datetime.now()
    td = (ts2 - ts1).total_seconds()
    logger.info('COMPLETED MP TRIAGE IN %s SECONDS' % td)


if __name__ == "__main__":
    main()
