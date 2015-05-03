from __future__ import division, absolute_import, print_function, unicode_literals
#from .modules import services
from string import whitespace, digits

import os
import sys
import json
import time
import socket
import base64
import datetime
import argparse

#import rethinkdb as rdb

import asyncio
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
        if not os.path.isfile(options.config):
            question = "The path you have specified for the config file does not exist, do you wish to create it? (y/n) "
            try:
                answer = raw_input(question)
            except:
                answer = input(question)
            if answer.lower() == 'n':
                print("No config to load from! Exiting")
                exit()
            elif answer.lower() == 'y':
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


class ConnectionHandler(object):
    connections = {}
    nicks = {}


class ChannelHandler(object):
    channels = {}


class IdentHandler(object):
    @asyncio.coroutine
    def handle_ident(self, message, host, port):
        try:
            client_reader, client_writer = yield from asyncio.open_connection(host, port)
            request = "{}\r\n".format(message)
            client_writer.write(request.encode())
            data = yield from asyncio.wait_for(client_reader.readline(), timeout=6.0)
            data = data.decode().rstrip()
            return data
            print("Ident Lookup got '{}'".format(data))
        except:
            return None


class MessageGenerator(object):
    def __init__(self, transport):
        self.pipe = transport
        
    def normal_message(self, pipe=None, *a, **m):
        pass

    def setup_message(self, pipe=None, *a, **m):
        if pipe == None:
            pipe = self.pipe
        gen = "{} :{}\r\n".format(m['type'].upper(), m['message'])
        pipe.write(gen.encode())

    def raw_message(self, pipe=None, *a, **m):
        if pipe == None:
            pipe = self.pipe
        gen = "{}\r\n".format(m['message'])
        pipe.write(gen.encode())

    def code_message(self, pipe=None, *a, **m):
        if pipe == None:
            pipe = self.pipe
        gen = ":{} {} {} :{}\r\n".format(m['leaf'], m['id'], m['name'], m['message'])
        pipe.write(gen.encode())

    def server_message(self, pipe=None, *a, **m):
        if pipe == None:
            pipe = self.pipe
        gen = ":{} {} :{}\r\n".format(m['leaf'], m['id'], m['message'])
        pipe.write(gen.encode())

    def inter_message(self, pipe=None, *a, **m):
        pass

    def channel_message(self, pipe=None, *a, **m):
        if pipe == None:
            pipe = self.pipe
        gen = ":{} {} {}\r\n".format(m['leaf'], m['id'], m['channel'])
        pipe.write(gen.encode())

    def private_message(self, pipe=None, *a, **m):
        pass

class KeepaliveHandler(object):
    def __init__(self, factory):
        self.check = {}

        self.peer = factory.peer
        self.leaf = factory.config['ircdleafnick']

        self.factory = factory

        self.timeout = 20
        self.timeout = (self.timeout / 2)

        self.transport = factory.transport
        self.MessageGenerator = MessageGenerator(self.transport)

    @asyncio.coroutine
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
            self.MessageGenerator.setup_message(type="PING", message=self.leaf)
        if (loop.time() - self.lastmessage) > (self.timeout * 2):
            #print("Connection to {} lost.".format(peername))
            self.transport.close()


class MessageHandler(object):
    def __init__(self, factory):
        self.nick  = None
        self.ident = None
        self.host  = None
        self.serv  = None
        self.real  = None
        self.addr  = factory.peer[0]
        self.uuid  = factory.uuid
        self.check = {}
        self.tasks = {}

        self.modes = 'iw'
        
        self.prefix = None

        self.ruser = False
        self.rnick = False
        self.connected = False
        self.disconnecting = False

        self.timeout = 20
        self.timeout = (self.timeout / 2) 

        self.ChanHan = factory.ChanHan
        self.ConnHan = factory.ConnHan
        self.IdentHandler = factory.IdentHandler

        self.keepalive = factory.keepalive

        self.network = factory.config['ircdname']
        self.leaflet = factory.config['ircdleafnick']

        self.peer = factory.peer
        self.transport = factory.transport
        self.factory = factory
        self.MessageGenerator = MessageGenerator(self.transport)

    def handler(self, message):
        loop = asyncio.get_event_loop()
        parse = message.split()
        block = parse[0]
        after = ' '.join(parse[1:])
        if block == "NICK":
            if after not in self.ConnHan.nicks:
                self.oldnick = self.nick
                self.nick = after
                self.rnick = True
            else:
                if self.nick == None:
                    nick = '*'
                else:
                    nick = self.nick
                self.MessageGenerator.code_message(leaf=self.leaflet, id='433', name="{} {}".format(nick, after), message='Nickname is already in use.')
                return
            print("{} is identified as {}".format(self.peer, after))
            if self.connected == True:
                del self.ConnHan.nicks[self.oldnick]
                for channel in self.ConnHan.connections[self.uuid]['channels']:
                    if self.ChanHan.channels[channel][first_joined] == self.oldnick:
                        self.ChanHan.channels[channel][first_joined] = self.nick
                    del self.ChanHan.channels[channel]['users'][self.oldnick]
                    self.ChanHan.channels[channel]['users'][self.nick] = ""
                self.MessageGenerator.server_message(leaf=self.prefix, id='NICK', message=self.nick)
            self.prefix = "~{}!{}@{}".format(self.nick, self.ident, self.addr)
            if self.nick is not None:
                self.ConnHan.connections[self.uuid]['nick'] = self.nick
                self.ConnHan.connections[self.uuid]['user'] = self.prefix
                self.ConnHan.nicks[self.nick] = self.uuid
            if self.ruser == True and self.rnick == True and self.connected == False:
                self.connected == True
                asyncio.Task(self.first_connection())
            return
        if block == "USER":
            if self.ruser == False:
                self.ruser = True
                self.real = after.split(':')[1]
                data = after.split(':')[0].split()
                self.ident = data[0]
                self.host  = data[1]
                self.serv  = data[2]
                if self.ruser == True and self.rnick == True and self.connected == False:
                    self.connected = True
                    asyncio.Task(self.first_connection())
                self.ConnHan.connections[self.uuid]['user'] = self.prefix
            return
        if block == "PONG":
            #print("Client {} PONG {}".format(self.peer, after))
            return
        if block == "MODE":
            asyncio.Task(self.set_modes(after))
            return
        if block == "JOIN":
            after = after.split(',')
            for channel in after:
                if channel not in self.ChanHan.channels:
                    self.create_channel(channel, self.nick)
                if channel not in self.ConnHan.connections[self.uuid]['channels']:
                    self.ConnHan.connections[self.uuid]['channels'].append(channel)
                else:
                    self.MessageGenerator.code_message(leaf=self.prefix, id='NOTICE', name=self.nick, message="You are already in {}".format(channel))
                self.ChanHan.channels[channel]['users'][self.nick] = ""
                asyncio.Task(self.message_channel(channel, "", mtype='JOIN'))
            return
        if block == "PART":
            after = after.split(':')
            try:
                message = after[1]
            except:
                message = ""
            after = after[0].rstrip().split(',')
            for channel in after:
                self.part_channel(channel, message)
            return
        if block == "PRIVMSG":
            after = after.split(':')
            target = after[0].rstrip()
            message = after[1]
            if '#' in target: 
                asyncio.Task(self.message_channel(target, message))
            else:
                try:
                    uuid = self.ConnHan.nicks[target]
                    pipe = self.ConnHan.connections[uuid]['pipe']
                    self.MessageGenerator.server_message(pipe=pipe, leaf=self.prefix, id='PRIVMSG {}'.format(target), message=message)
                except:
                    message = "User is currently offline"
                    self.MessageGenerator.server_message(leaf=self.prefix, id='PRIVMSG {}'.format(target), message=message)
            return
        if block == "QUIT":
            try:
                after = after.lstrip(':')
            except:
                pass
            self.disconnecting = True
            asyncio.Task(self.exit_server(after))
            return
        if block == "MYDATA":
            print("Mydata Requested")
            print("{} {} {}".format("-"*15, "Conn Conn", "-"*15))
            print(repr(self.ConnHan.connections))
            print("{} {} {}".format("-"*15, "Conn Nicks", "-"*15))
            print(json.dumps(self.ConnHan.nicks, sort_keys=True, indent=4))
            print("{} {} {}".format("-"*15, "Chan Chan", "-"*15))
            print(json.dumps(self.ChanHan.channels, sort_keys=True, indent=4))
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
        try:
            hostname = yield from asyncio.wait_for(hosttask, timeout=5)
            self.send_notice("*** Found your hostname")
        except:
            hostname = self.addr
            self.send_notice("*** Couldn't look up your hostname")
        self.addrhost = hostname[0]
        lport = self.transport.get_extra_info('sockname')[1]
        rport = self.peer[1]
        request = "{}, {}".format(rport, lport)
        reply = yield from asyncio.Task(self.IdentHandler.handle_ident(request, self.addr, 113))
        if reply == None:
            self.send_notice("*** No Ident response")
            self.ident = "~{}".format(self.ident)
        else:
            print("Ident Reply was {}".format(reply))
            self.send_notice("*** Got Ident response")
            self.ident = "{}".format(self.ident)
        self.prefix = "{}!{}@{}".format(self.nick, self.ident, self.addrhost)
        self.ConnHan.connections[self.uuid]['user'] = self.prefix
        yield from asyncio.wait_for(self.send_motd(), timeout=5)
        self.MessageGenerator.code_message(leaf=self.nick, id='MODE', name=self.nick, message="+{}".format(self.modes))

    @asyncio.coroutine
    def message_channel(self, channel, message, mtype='PRIVMSG'):
        if not len(message) > 0:
            if mtype == 'PRIVMSG':
                return
            message = ""
        if channel not in self.ChanHan.channels:
            message = "That channel does not exist"
            self.MessageGenerator.server_message(leaf=self.prefix, id='{} {}'.format(mtype, channel), message=message)
            return
        if self.nick not in self.ChanHan.channels[channel]['users']:
            message = "You must be in the channel to send a message to it"
            self.MessageGenerator.server_message(leaf=self.prefix, id='{} {}'.format(mtype, channel), message=message)
        else:
            for user in self.ChanHan.channels[channel]['users']:
                if mtype == "JOIN" or user != self.nick:
                    uuid = self.ConnHan.nicks[user]
                    pipe = self.ConnHan.connections[uuid]['pipe']
                    self.MessageGenerator.server_message(pipe=pipe, leaf=self.prefix, id='{} {}'.format(mtype, channel), message=message)
            if mtype == 'PART' or mtype == 'QUIT':
                try:
                    yield from asyncio.wait_for(self.remove_from_channel(channel), timeout=1)
                except:
                    pass

    @asyncio.coroutine
    def send_motd(self):
        motdgreet = "- {} Message of the Day -".format(self.leaflet)
        self.MessageGenerator.code_message(leaf=self.leaflet, id='375', name=self.nick, message=motdgreet)
        try:
            motdfile = self.factory.config['motd']
            motd = open(motdfile, 'r')
            for line in motd.readline().rstrip():
                line = "- {}".format(line)
                self.MessageGenerator.code_message(leaf=self.leaflet, id='372', name=self.nick, message=line)
        except:
            line = "- No MOTD was found for this server!"
            self.MessageGenerator.code_message(leaf=self.leaflet, id='372', name=self.nick, message=line)
        endmotd = "End of /MOTD command."
        self.MessageGenerator.code_message(leaf=self.leaflet, id='376', name=self.nick, message=endmotd)

    @asyncio.coroutine
    def set_modes(self, data):
        mode = None
        add = []
        remove = []
        removed = []
        data = data.split()
        if data[0] == self.nick:
            for x in data[1]:
                if x == '-':
                    mode = 'remove'
                elif x == '+':
                    mode = 'add'
                else:
                    if mode == 'add':
                        add.append(x)
                    elif mode == 'remove':
                        remove.append(x)
            add = ''.join(add)
            remove = ''.join(remove)
            for char in remove:
                if char in self.modes:
                    removed.append(char)
            self.modes = self.modes.translate({ord(i):None for i in remove})
            add = add.translate({ord(i):None for i in self.modes})
            self.modes = ''.join([self.modes, add])
            self.modes = ''.join([c for i, c in enumerate(self.modes) if c in whitespace+digits or not c in self.modes[:i]])
            removed = ''.join([c for i, c in enumerate(''.join(removed)) if c in whitespace+digits or not c in ''.join(removed)[:i]])
            if len(add) > 0:
                add = "+{}".format(add)
            if len(removed) > 0:
                removed = "-{}".format(removed)
            changes = "{}{}".format(add, removed)
            if len(changes) > 0:
                self.MessageGenerator.code_message(leaf=self.nick, id='MODE', name=self.nick, message=changes)

    @asyncio.coroutine
    def exit_server(self, message):
        for channel in self.ConnHan.connections[self.uuid]['channels']:
            #asyncio.Task(self.message_channel(channel, message, mtype='QUIT'))
            yield from asyncio.wait_for(self.remove_from_channel(channel), timeout=1)
        checklist = dict(self.keepalive.check)
        for key, check in checklist.items():
            check[0].cancel()
            del self.keepalive.check[key]
        del self.ConnHan.connections[self.uuid]
        del self.ConnHan.nicks[self.nick]
        self.transport.close()
        #print("Client {} disconnected with message '{}'".format(self.peer, message))
        del self

    def part_channel(self, channel, message):
        asyncio.Task(self.message_channel(channel, message, mtype='PART'))

    @asyncio.coroutine
    def remove_from_channel(self, channel):
        try:
            self.ConnHan.connections[self.uuid]['channels'].remove(channel)
        except:
            pass
        try:
            del self.ChanHan.channels[channel]['users'][self.nick]
        except:
            pass
        if len(self.ChanHan.channels[channel]['users']) == 0:
            del self.ChanHan.channels[channel]

    def create_channel(self, channel, user):
        loop = asyncio.get_event_loop()
        self.ChanHan.channels[channel] = dict(created=loop.time(), users={}, first_joined=user, topic=dict(time=0, text="", set_by=""), modes="")

    def get_nick(self):
        return self.nick

    def send_notice(self, notice):
        self.MessageGenerator.code_message(leaf=self.leaflet, id='NOTICE', name='*', message=notice)

    def task_done(self, task):
        del self.tasks[task]
        if len(self.tasks) == 0:
            loop = asyncio.get_event_loop()

class Server(asyncio.Protocol):
    def __init__(self, config, chan, conn, ident):
        self.config = config
        self.ChanHan = chan
        self.ConnHan = conn
        self.IdentHandler = ident

    def connection_made(self, transport):
        loop = asyncio.get_event_loop()
        self.transport = transport
        self.peer = self.transport.get_extra_info('peername')
        self.uuid = base64.b64encode("{} - {}".format(self.peer, loop.time()).encode())
        self.uuid = self.uuid.decode()
        self.keepalive = KeepaliveHandler(self)
        self.client = MessageHandler(self)
        self.ConnHan.connections[self.uuid] = dict(pipe=self.transport, server=self.config['ircdleafnick'], peer=self.peer, nick=None, user=None, channels=[])
        #print("New Connection")

    def data_received(self, indata):
        #print("Got Chatter")
        indata = indata.decode().rstrip()
        indata = indata.split('\r\n')
        for message in indata:
            self.client.handler(message)
            asyncio.Task(self.keepalive.keepalive())

    def connection_lost(self, exc):
        message = "Remote client closed the connection"
        if self.client.disconnecting != True:
            asyncio.Task(self.client.exit_server(message))
            del self.client

class Core(object):
    def __init__(self, options, parser):
        self.config = ConfigHandler().handleConfig(options, parser)
        host = self.config['ircdhost'][0]
        port = int(self.config['ircdport'][0])
        loop = asyncio.get_event_loop()
        chan = ChannelHandler()
        conn = ConnectionHandler()
        ident = IdentHandler()
        for host in self.config['ircdhost']:
            for port in self.config['ircdport']:
                listener = loop.create_server(lambda: Server(self.config, chan, conn, ident), host=host, port=port)
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