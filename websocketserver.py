#!/usr/bin/python

# https://gist.github.com/jkp/3136208

import threading
import multiprocessing
import select
import struct
import SocketServer
from base64 import b64encode
from hashlib import sha1
from mimetools import Message
from StringIO import StringIO
 
import time;

class ThreadedWebSocketsHandler(SocketServer.StreamRequestHandler):
    magic = '258EAFA5-E914-47DA-95CA-C5AB0DC85B11'

    def setup(self):
        SocketServer.StreamRequestHandler.setup(self)
        self.thread = threading.currentThread()
        print "\r", self.thread.getName(), "connection established", self.client_address
        self.handshake_done = False
        self.active = True
        self.q = multiprocessing.Queue(1024)
        connections.append(self)

    def handle(self):
        while self.active:
            (input, [], []) = select.select([self.q._reader, self.rfile], [], [])
            for fd in input:
                if fd == self.q._reader:
                    if not self.handshake_done:
                        self.q.get()
                    else:
                        self.send_message(self.q.get())
                elif fd == self.rfile:
                    if not self.handshake_done:
                        self.handshake()
                    else:
                        self.read_next_message()
                else:
                    pass

    def read_next_message(self):
        b2 = self.rfile.read(2)
        # http://tools.ietf.org/html/rfc6455
        opcode = ord(b2[0]) & 15
        if opcode == 8:
            self.on_close()
            return
        length = ord(b2[1]) & 127
        if length == 126:
            length = struct.unpack(">H", self.rfile.read(2))[0]
        elif length == 127:
            length = struct.unpack(">Q", self.rfile.read(8))[0]
        masks = [ord(byte) for byte in self.rfile.read(4)]
        decoded = ""
        for char in self.rfile.read(length):
            decoded += chr(ord(char) ^ masks[len(decoded) % 4])
        self.on_message(decoded)

    def send_message(self, message):
        self.request.send(chr(129))
        length = len(message)
        if length <= 125:
            self.request.send(chr(length))
        elif length >= 126 and length <= 65535:
            self.request.send(126)
            self.request.send(struct.pack(">H", length))
        else:
            self.request.send(127)
            self.request.send(struct.pack(">Q", length))
        self.request.send(message)

    def handshake(self):
        data = self.request.recv(1024).strip()
        headers = Message(StringIO(data.split('\r\n', 1)[1]))
        if headers.get("Upgrade", None) != "websocket":
            return
        print "\r", self.thread.getName(), 'Handshaking'
        key = headers['Sec-WebSocket-Key']
        digest = b64encode(sha1(key + self.magic).hexdigest().decode('hex'))
        response = 'HTTP/1.1 101 Switching Protocols\r\n'
        response += 'Upgrade: websocket\r\n'
        response += 'Connection: Upgrade\r\n'
        response += 'Sec-WebSocket-Accept: %s\r\n\r\n' % digest
        self.handshake_done = self.request.send(response)

    def on_message(self, message):
        print "\r", self.thread.getName(), "READ:", message

    def on_close(self):
        self.active = False
        print "\r", self.thread.getName(), "closed"
        self.request.close()
        connections.remove(self)

# http://pymotw.com/2/SocketServer/
class ThreadedWebSocketsServer(SocketServer.ThreadingMixIn, SocketServer.TCPServer):
    pass

if __name__ == "__main__":
    import sys
    import tty, termios

    # http://code.activestate.com/recipes/577977-get-single-keypress/
    def getch():
        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            ch = sys.stdin.read(1)
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
        return ch

    def send_to_all(txt):
        for connection in connections:
            connection.q.put(txt)

    def close_all():
        for connection in connections:
            connection.on_close()

    import socket
    import threading

    connections = []

    SocketServer.TCPServer.allow_reuse_address = True
    server = ThreadedWebSocketsServer(
        ("0.0.0.0", 9999), ThreadedWebSocketsHandler)
    t = threading.Thread(target=server.serve_forever)
    t.setDaemon(True)
    t.start()
    print "\r", 'Server loop running in thread:', t.getName()

    try:
        txt = ''
        while True:
            c = getch()
            key = ord(c)
            if key == 27: #ESC
                break
            elif key == 127: #BS
                txt = txt[:-1]
            elif key == 13: #Enter
                txt = ''
            else:
                txt += c
            send_to_all(txt)
    except (KeyboardInterrupt, SystemExit):
        server.socket.close()
    close_all()
