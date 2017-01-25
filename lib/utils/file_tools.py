#!/usr/bin/env python

import os
from lib.utils.systemtools import *
from lib.utils.moduletools import ModuleIndexer

class FileIndexer(ModuleIndexer):

    def get_files(self):
        # manage the checkout
        if not os.path.isdir(self.checkoutdir):
            self.create_checkout()
        else:
            self.update_checkout()

        #cmd = 'find %s -type f' % self.checkoutdir
        cmd = 'find %s' % self.checkoutdir
        (rc, so, se) = run_command(cmd)
        files = so.split('\n')
        files = [x.strip() for x in files if x.strip()]
        files = [x.replace(self.checkoutdir + '/', '') for x in files]
        files = [x for x in files if not x.startswith('.git')]
        self.files = files


