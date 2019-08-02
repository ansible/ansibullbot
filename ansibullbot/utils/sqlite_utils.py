#!/usr/bin/env python

import json
import os

from sqlalchemy import create_engine
from sqlalchemy import Column
from sqlalchemy import Integer
from sqlalchemy import String
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

import ansibullbot.constants as C


Base = declarative_base()


class Blame(Base):
    __tablename__ = u'blames'
    id = Column(Integer(), primary_key=True)
    file_name = Column(String())
    file_commit = Column(String())
    author_commit = Column(String())
    author_login = Column(String())


class Email(Base):
    __tablename__ = u'email'
    id = Column(Integer())
    login = Column(String())
    email = Column(String(), primary_key=True)


class RateLimit(Base):
    __tablename__ = u'rate_limit'
    id = Column(Integer(), primary_key=True)
    username = Column(String)
    token = Column(String)
    rawjson = Column(String)
    core_rate_limit = Column(Integer)
    core_rate_limit_remaining = Column(Integer)
    query_counter = Column(Integer)



class AnsibullbotDatabase(object):

    def __init__(self, cachedir='/tmp'):

        unc = C.DEFAULT_DATABASE_UNC
        if unc.startswith('sqlite:'):
            self.dbfile = unc.replace('sqlite:///', '')
            self.dbfile = os.path.expanduser(self.dbfile)
            self.dbfile = os.path.abspath(self.dbfile)
            dbfiledir = os.path.dirname(self.dbfile)
            if not os.path.exists(dbfiledir):
                os.makedirs(dbfiledir)
            unc = 'sqlite:///' + self.dbfile

        self.unc = unc

        self.engine = create_engine(self.unc)
        self.session_maker = sessionmaker(bind=self.engine)
        self.session = self.session_maker()

        Email.metadata.create_all(self.engine)
        Blame.metadata.create_all(self.engine)
        RateLimit.metadata.create_all(self.engine)

    def set_rate_limit(self, username=None, token=None, rawjson=None):

        '''Store the ratelimit json data by user/token'''

        kwargs = {
            'username': username,
            'token': token,
            'core_rate_limit': rawjson['resources']['core']['limit'],
            'core_rate_limit_remaining': rawjson['resources']['core']['remaining'],
            'rawjson': json.dumps(rawjson),
            'query_counter': 0
        }
        rl = RateLimit(**kwargs)
        self.session.merge(rl)
        self.session.flush()
        self.session.commit()

        self.reset_rate_limit_query_counter(username=username, token=token)

    def get_rate_limit_remaining(self, username=None, token=None):

        '''Get the core limit remaining by user/token'''

        rl = None
        rl = self.session.query(RateLimit).filter(RateLimit.token == token).first()
        if rl is None or not hasattr(rl, 'core_rate_limit_remaining'):
            return None
        remaining = rl.core_rate_limit_remaining

        if rl.query_counter is None:
            rl.query_counter = 0
        rl.query_counter += 1
        self.session.merge(rl)
        self.session.flush()
        self.session.commit()

        return remaining

    def get_rate_limit_rawjson(self, username=None, token=None):

        '''Get the ratelimit json by user/token'''

        rl = None
        rl = self.session.query(RateLimit).filter(RateLimit.token == token).first()
        if rl is None or not hasattr(rl, 'core_rate_limit_remaining'):
            return None

        data = None
        try:
            data = rl.rawjson
            data = json.loads(data)
        except Exception as e:
            pass

        # increment the counter to keep track of calls
        if rl.query_counter is None:
            rl.query_counter = 0
        rl.query_counter += 1
        self.session.merge(rl)
        self.session.flush()
        self.session.commit()

        return data

    def get_rate_limit_query_counter(self, username=None, token=None):
        counter = None
        try:
            counter = self.session.query(RateLimit).filter(RateLimit.token == token).first().query_counter
        except Exception as e:
            pass
        return counter

    def reset_rate_limit_query_counter(self, username=None, token=None):
        rl = None
        rl = self.session.query(RateLimit).filter(RateLimit.token == token).first()
        rl.query_counter = 0
        self.session.merge(rl)
        self.session.flush()
        self.session.commit()

    def debug(self):
        import epdb; epdb.st()     
