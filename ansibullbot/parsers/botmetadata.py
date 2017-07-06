#!/usr/bin/env python

import yaml
from string import Template


class BotMetadataParser(object):

    @staticmethod
    def parse_yaml(data):

        def clean_list_items(inlist):
            if isinstance(inlist, list):
                inlist = str(inlist)
            if '&' in inlist:
                import epdb; epdb.st()
            inlist = inlist.replace("[", '')
            inlist = inlist.replace("]", '')
            inlist = inlist.replace("'", '')
            inlist = inlist.replace(",", '')
            inlist = inlist.split()
            return inlist

        def fix_lists(data):
            for k,v in data['files'].items():
                for k2,v2 in v.items():
                    if isinstance(v2, str) and '$' in v2:
                        tmpl = Template(v2)
                        newv2 = tmpl.substitute(**data['macros'])
                        newv2 = clean_list_items(newv2)
                        data['files'][k][k2] = newv2

            return data

        def extend_labels(data):
            for k,v in data['files'].items():
                # labels from path(s)
                labels = v.get('labels', [])
                if isinstance(labels, str):
                    labels = labels.split()
                    labels = [x.strip() for x in labels if x.strip()]
                path_labels = [x.strip() for x in k.split('/') if x.strip()]
                for x in path_labels:
                    x = x.replace('.py', '')
                    x = x.replace('.ps1', '')
                    if x not in labels:
                        labels.append(x)
                data['files'][k]['labels'] = sorted(set(labels))

            return data

        ydata = yaml.load(data)

        # replace macros in files section
        ydata = fix_lists(ydata)

        # extend labels by filepath
        ydata = extend_labels(ydata)

        return ydata
