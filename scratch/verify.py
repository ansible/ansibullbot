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

    redirected = set()
    for number in numbers:
        fn = os.path.join(prefix, str(number), 'meta.json')
        fn = os.path.expanduser(fn)
        if not os.path.exists(fn):
            continue
        #print(fn)
        with open(fn, 'r') as f:
            meta = json.loads(f.read())
        ##pprint(meta)
        #print(meta['html_url'])
        newlabels = meta.get('actions', {}).get('newlabel', [])

        '''
        if len(newlabels) > 4:
            print('#######################')
            print('component: %s' % meta['template_data']['component_raw'])
            pprint(newlabels)
            pprint(meta['collection_filemap'])
            #import epdb; epdb.st()
        '''


        if 'needs_collection_redirect' in newlabels:
            print('\n#######################################################')
            print(fn)
            print(meta['html_url'])
            print('component: %s' % meta['template_data'].get('component_raw'))
            print('files: %s' % meta['filenames'])
            pprint(newlabels)
            pprint(meta['collection_filemap'])

            redirected.add(number)
            #import epdb; epdb.st()

    print('%s total tickets redirected' % len(list(redirected)))


if __name__ == "__main__":
    main()
