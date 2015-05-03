from __future__ import division, absolute_import, print_function, unicode_literals
#from .modules import services

import os
import sys
import json
import time
import socket
import datetime
import argparse

#import rethinkdb as rdb

import trollius as asyncio
from trollius import From, Return
import logging
logging.basicConfig()

timer = time.clock if sys.platform == 'win32' else time.time

class ConfigHandler(object):
    def __init__(self):
        pass

    def handleConfig(self, options, parser):
        if options.config == "":
            print("You have not defined a proper config, Please define a proper config to load from (-c /path/to/config.json)")
            exit()
        if os.path.isfile(options.config) == False:
            question = raw_input("The path you have specified for the config file does not exist, do you wish to create it? (y/n) ")
            if question.lower() == 'n':
                print("No config to load from! Exiting")
                exit()
            elif question.lower() == 'y':
                self.createConfig(options, options)
            else:
                print("Invalid response! Exiting")
                exit()
        return self.loadConfig(options, parser)
    
    def loadConfig(self, options, parser):
        try:
            self.config = json.load(open(options.config, 'r+'))
        except:
            print("There was an error loading the config! Perhaps it is malformed?")
            exit()
        for key, value in vars(options).items():
            if parser.get_default(key) != value:
                self.config[key] = value
        if options.boolnew == True:
            self.createConfig(options, options)
        if options.boolsave == True:
            self.createConfig(options, self.config)
        return self.config

    def openAndWrite(self, options, data):
        fp = open(options.config, 'w+')
        try:
            items = dict(vars(data))
        except: 
            items = dict(data)
        for item in ["config", "boolsave", "boolnew"]:
            items.pop(item, None)
        fp.seek(0)
        fp.write(json.dumps(items, sort_keys=True, indent=4))
        fp.truncate()
        fp.close()

    def createConfig(self, options, data):
        try: 
            self.openAndWrite(options, data)
            print("Config file updated successfully!")
        except Exception as e:
            print("Something went wrong! %s" % e)


class ClientHandler(object):
    def __init__(self):
        pass

class IdentHandler(object):
    clients = {}

    def ident_connection(self, message, host, port):
        print("Ident Task")
        task = asyncio.Task(self.handle_ident(message, host, port))
        self.clients[task] = (host, port)
        task.add_done_callback(self.ident_done)

    def ident_done(self, task):
        del self.clients[task]
        if len(self.clients) == 0:
            loop = asyncio.get_event_loop()
            #loop.stop()
     
    @asyncio.coroutine
    def handle_ident(self, message, host, port):
        try:
            client_reader, client_writer = yield From(asyncio.open_connection(host, port))
            request = "{}\r\n".format(message)
            client_writer.write(request.encode())
            data = yield From(asyncio.wait_for(client_reader.readline(), timeout=6.0))
            data = data.decode().rstrip()
            raise Return(data)
            print("Ident Lookup got '{}'".format(data))
        except:
            raise Return(None)


class MessageGenerator(object):
    def __init__(self):
        pass

    def normal_message(*a, **m):
        pass

    def raw_message(*a, **m):
        gen = "{}\r\n".format(m['message'])
        return gen.encode()

    def server_message(*a, **m):
        gen = ":{} {} {} :{}\r\n".format(m['leaf'], m['id'], m['name'], m['message'])
        return gen.encode()

    def notice_message(*a, **m):
        gen = ":{} NOTICE {} :{}\r\n".format(m['leaf'], m['name'], m['message'])
        return gen.encode()

    def inter_message(*a, **m):
        pass

    def channel_message(*a, **m):
        pass

    def private_message(*a, **m):
        pass

class KeepaliveHandler(object):
    def __init__(self, factory):
        self.check = {}

        self.peer = factory.peer

        self.timeout = 20
        self.timeout = (self.timeout / 2)

        self.transport = factory.transport
        self.MessageGenerator = MessageGenerator()

    def keepalive(self):
        loop = asyncio.get_event_loop()
        self.lastmessage = loop.time()
        checklist = dict(self.check)
        for key, value in checklist.items():
            if key < (loop.time() + (self.timeout * 2)):
                self.check[key][0].cancel()
                #print("Removing Keepalive for {} at {}".format(value[1], key))
                del self.check[key]
        if len(self.check) <= 0:
            self.generate_keepalive(loop)

    def generate_keepalive(self, loop):
        self.check[(loop.time() + self.timeout)] = [loop.call_later(self.timeout, self.ping_pong), self.peer]
        self.check[(loop.time() + (self.timeout * 2))] = [loop.call_later((self.timeout * 2), self.ping_pong), self.peer]

    def ping_pong(self):
        loop = asyncio.get_event_loop()
        peername = self.transport.get_extra_info('peername')
        if (loop.time() - self.lastmessage) > self.timeout:
            #print("Pinging")
            gen = self.MessageGenerator.raw_message(message="PING")
            self.transport.write(gen)
        if (loop.time() - self.lastmessage) > (self.timeout * 2):
            print("Connection to {} lost.".format(peername))
            self.transport.close()


class MessageHandler(object):
    def __init__(self, factory):
        self.nick  = None
        self.ident = None
        self.host  = None
        self.serv  = None
        self.real  = None
        self.addr  = factory.peer[0]
        self.check = {}
        self.tasks = {}
        
        self.prefix = None

        self.connected = False

        self.timeout = 20
        self.timeout = (self.timeout / 2) 

        self.network = factory.config['ircdname']
        self.leaflet = factory.config['ircdleafnick']

        self.peer = factory.peer
        self.transport = factory.transport
        self.factory = factory
        self.MessageGenerator = MessageGenerator()

    def handler(self, message):
        loop = asyncio.get_event_loop()
        block = message[0:4]
        after = message[5:]
        if block == "NICK":
            self.nick = after
            print("{} is identified as {}".format(self.peer, after))
            self.prefix = "~{}!{}@{}".format(self.nick, self.ident, self.addr)
            return
        if block == "USER":
            if self.connected == False:
                self.connected = True
                self.real = after.split(':')[1]
                data = after.split(':')[0].split()
                self.ident = data[0]
                self.host  = data[1]
                self.serv  = data[2]
                print("First Task")
                task = asyncio.Task(self.first_connection())
                self.tasks[task] = (self.peer, loop.time())
                task.add_done_callback(self.task_done)
            return
        if block == "PONG":
            print("Client {} PONG".format(self.peer))
            return
        if block != "PONG":
            print("Recieved '{}' from {} identified as {} - {}".format(repr(message), self.peer, self.nick, timer()))
            self.transport.write("{}\r\n".format(message).encode())
            print("Sent '{}' to {}".format(repr(message), self.peer))

    @asyncio.coroutine
    def first_connection(self):
        self.send_notice("*** Looking up your hostname...")
        self.send_notice("*** Checking Ident")
        loop = asyncio.get_event_loop()
        hosttask = loop.run_in_executor(None, socket.gethostbyaddr, self.addr)
        hostname = yield From(asyncio.wait(hosttask, timeout=5))
        print("Hostname was {}".format(hostname))

        lport = self.transport.get_extra_info('sockname')[1]
        rport = self.peer[1]
        request = "{}, {}".format(rport, lport)
        reply = IdentHandler().ident_connection(request, self.addr, 113)
        print("Ident Reply was {}".format(reply))
        if reply == None:
            self.send_notice("*** No Ident response")
            self.ident = "~{}".format(self.ident)
        self.prefix = "{}!{}@{}".format(self.nick, self.ident, self.addr)
        print("{} is now listed as {}".format(self.nick, self.prefix))

    def get_nick(self):
        return self.nick

    def send_notice(self, notice):
        notice = self.MessageGenerator.notice_message(leaf=self.leaflet, name='*', message=notice)
        self.transport.write(notice)

    def task_done(self, task):
        del self.tasks[task]
        if len(self.tasks) == 0:
            loop = asyncio.get_event_loop()

class Server(asyncio.Protocol):
    def __init__(self, config):
        self.config = config

    def connection_made(self, transport):
        self.transport = transport
        self.peer = self.transport.get_extra_info('peername')
        self.client = MessageHandler(self)
        self.keepalive = KeepaliveHandler(self)
        #print("New Connection")

    def data_received(self, indata):
        #print("Got Chatter")
        indata = indata.decode().rstrip()
        indata = indata.split('\r\n')
        for message in indata:
            self.client.handler(message)
            self.keepalive.keepalive()

class Core(object):
    def __init__(self, options, parser):
        self.config = ConfigHandler().handleConfig(options, parser)
        host = self.config['ircdhost'][0]
        port = int(self.config['ircdport'][0])
        loop = asyncio.get_event_loop()
        listener = loop.create_server(lambda: Server(self.config), host=host, port=port)
        server = loop.run_until_complete(listener)
        print('Opening listener on {}'.format(server.sockets[0].getsockname()))
        try:
            loop.run_forever()
        except KeyboardInterrupt:
            print("exit")
        finally:
            server.close()
            loop.close()


def run():
    parser = argparse.ArgumentParser(description='IRCPyd \r\n A simple Python based IRC Server by KsaRedFx')

    config = parser.add_argument_group("Configuration Settings", "Options that allow you to override configuration loading at runtime")
    config.add_argument("-c", "--config", dest="config", help="Location of the configuration file", default="")
    config.add_argument("-cs", "--configsave", dest="boolsave", help="Saves your overrides into the current config file", action='store_true')
    config.add_argument("-cn", "--confignew", dest="boolnew", help="Rewrites your config with the default settings", action='store_true')

    database = parser.add_argument_group("Database Settings", "Options that allow you to override database settings at runtime")
    database.add_argument("-dh", "--sqlhost", dest="sqlhost", help="Setting the host for the database storage", default="localhost")
    database.add_argument("-dp", "--sqlport", dest="sqlport", help="Setting the port for the database storage", default="28015")
    database.add_argument("-dn", "--sqlname", dest="sqlname", help="Setting the database name for the database storage", default="services")
    database.add_argument("-dk", "--sqlakey", dest="sqlakey", help="Setting the database auth key for the database storage", default="")

    ircd = parser.add_argument_group("IRCd Settings", "Options that llow you to override IRCd settings at runtime")
    ircd.add_argument("-i", "--ircdhost", nargs="+", dest="ircdhost", help="Host(s) the IRCd will bind to on startup", default=["127.0.0.1"])
    ircd.add_argument("-p", "--ircdport", nargs="+", dest="ircdport", help="Port(s) the IRCd will bind to on startup", default=["6667"])
    ircd.add_argument("-n", "--ircdname", dest="ircdname", help="Nickname you picked for your IRC Network", default="network")
    ircd.add_argument("-l", "--leafnick", dest="ircdleafnick", help="This particular IRCd's leaf nickname", default="leaflette")

    options = parser.parse_args()

    Core(options, parser)