import asyncio
import logging

logging.basicConfig()
 
clients = {}  # task -> (reader, writer)
 
def make_connection(host, port, proccess):
    task = asyncio.Task(handle_client(host, port, proccess))
    clients[task] = (host, port)
 
    def client_done(task):
        del clients[task]
        if len(clients) == 0:
            loop = asyncio.get_event_loop()
            loop.stop()
 
    task.add_done_callback(client_done)
 
 
@asyncio.coroutine
def handle_client(host, port, proccess):
    client_reader, client_writer = yield from asyncio.open_connection(host, port)
    print("Connected to {}:{}".format(host, port))
    try:
        client_writer.write("WORLD - {}\r\n".format(proccess).encode())
        data = yield from client_reader.readline()
 
        sdata = data.decode().rstrip().upper()
        print("Received '{}'".format(sdata))
 
    finally:
        client_writer.close()
        print("Disconnected from {}:{} - {}".format(host, port, proccess))
 
def main():
    loop = asyncio.get_event_loop()
    for x in range(50):
        make_connection('127.0.0.1', 6667, x)
    loop.run_forever()
 
if __name__ == '__main__':
    main()