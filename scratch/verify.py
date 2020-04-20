#!/usr/bin/env python3

import datetime
import glob
import json
import os

from pprint import pprint


def main():
    prefix = '~/.ansibullbot/cache/ansible/ansible/issues'
    directories = glob.glob('%s/*' % os.path.expanduser(prefix))
    numbers = [os.path.basename(x) for x in directories]
    numbers = [int(x) for x in numbers if x.isdigit()]
    numbers = sorted(numbers)

    for number in numbers:
        fn = os.path.join(prefix, str(number), 'meta.json')
        fn = os.path.expanduser(fn)
        if not os.path.exists(fn):
            continue
        print(fn)
        with open(fn, 'r') as f:
            meta = json.loads(f.read())
        #pprint(meta)
        newlabels = meta.get('actions', {}).get('newlabel', [])
        if len(newlabels) > 1:
            pprint(newlabels)
            import epdb; epdb.st()


if __name__ == "__main__":
    main()
