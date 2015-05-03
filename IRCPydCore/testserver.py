try:
    import asyncio
except ImportError:
    import trollius as asyncio
    from trollius import From
import logging
logging.basicConfig()


def readInput():
    try:
        new = raw_input("> ")
    except:
        new = input("> ")
    return new

class EchoClient(asyncio.Protocol):
    def connection_made(self, transport):
        self.transport = transport
        self.message = readInput()
        if len(self.message) != 0:
            transport.write(self.message.encode())

    def data_received(self, data):
        peername = self.transport.get_extra_info('sockname')
        print("Data '{}' received over {}".format(data.decode(), peername))
        if data.decode().upper() == "PING":
            self.transport.write("PONG".encode())

        self.connection_made(self.transport)

    def connection_lost(self, exc):
        print('Lost connection to server, message not sent.')
        asyncio.get_event_loop().stop()



loop = asyncio.get_event_loop()
while True:
    coro = loop.create_connection(EchoClient, '127.0.0.1', 6667)
    loop.run_until_complete(coro)
    loop.run_forever()
loop.close()
