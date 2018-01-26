#!/usr/bin/env python


import json
import sys
from ansibullbot.utils.component_tools import AnsibleComponentMatcher


class EmailCache(object):

    def get(self, email):
        return None


def usage():
    print("PYTHONPATH=. scripts/render_botmeta.py <OUTFILE>")


def main():

    if len(sys.argv) != 2:
        usage()
        sys.exit(1)

    ec = EmailCache()
    cm = AnsibleComponentMatcher(
        botmetafile=None,
        cachedir='/tmp/botmeta_cache',
        email_cache=ec
    )
    cm.update()

    # This gets the rendered meta for just modules ...
    #meta = cm.BOTMETA
    #print(json.dumps(cm.BOTMETA, indent=2, sort_keys=True))

    # This is how the bot gets full meta for a file ...
    FULLMETA = {}
    for filen in cm.gitrepo.files:
        FULLMETA[filen] = cm.get_meta_for_file(filen)

    with open(sys.argv[1], 'w') as f:
        f.write(json.dumps(FULLMETA, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
