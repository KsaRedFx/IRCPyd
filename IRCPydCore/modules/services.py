from __future__ import division, absolute_import, print_function, unicode_literals

import os
import sys
import json
import time
import socket
import datetime

import rethinkdb as rdb

timer = time.clock if sys.platform == 'win32' else time.time

class ChanServ(object):
    def __init__(self, options):
        pass

class NickServ(object):
    def __init__(self, options):
        pass

class OperServ(object):
    def __init__(self, options):
        pass