# Copyright (C) 2016 Mickaël Thomas
# Copyright (C) 2013 Peter Rowlands

# From pysrcds project: https://github.com/pmrowla/pysrcds
# Modified to work with python3 and the Factorio implementation of Source RCON

"""Source server RCON communications module"""

import struct
import socket
import itertools


# Packet types
SERVERDATA_AUTH = 3
SERVERDATA_AUTH_RESPONSE = 2
SERVERDATA_EXECCOMMAND = 2
SERVERDATA_RESPONSE_VALUE = 0


class RconPacket(object):

    """RCON packet"""

    _struct = struct.Struct('<3i')

    def __init__(self, pkt_id=0, pkt_type=-1, body=b''):
        self.pkt_id = pkt_id
        self.pkt_type = pkt_type
        self.body = body

    def __bytes__(self):
        """Return the body string"""
        return self.body

    def __repr__(self):
        return "RconPacket(pkt_id=%d, pkt_type=%d, body=%r)" % (
            self.pkt_id, self.pkt_type, self.body)

    def size(self):
        """Return the pkt_size field for this packet"""
        return len(self.body) + 10

    def pack(self):
        """Return the packed version of the packet"""
        header = self._struct.pack(self.size(), self.pkt_id, self.pkt_type)
        return b'%s%s\x00\x00' % (header, self.body)


class RconConnection(object):

    """RCON client to server connection"""

    def __init__(self, server, port=27015, password='', encoding='utf-8'):
        self.server = server
        self.port = port
        self.encoding = encoding
        self._sock = socket.create_connection((server, port))
        self._rfile = self._sock.makefile('rb')
        self.pkt_id = itertools.count(1)
        self._authenticate(password.encode(self.encoding))

    def _authenticate(self, password):
        """Authenticate with the server using the given password"""
        auth_pkt = RconPacket(next(self.pkt_id), SERVERDATA_AUTH, password)
        self._send_pkt(auth_pkt)
        auth_resp = self.read_response()

        if auth_resp.pkt_type != SERVERDATA_AUTH_RESPONSE:
            raise RconError('Received invalid auth response packet')
        if auth_resp.pkt_id == -1:
            raise RconAuthError('Bad password')

    def exec_command(self, command):
        """Execute the given RCON command
        Return the response body
        """
        cmd_pkt = RconPacket(next(self.pkt_id), SERVERDATA_EXECCOMMAND,
                             command.encode(self.encoding))
        self._send_pkt(cmd_pkt)
        resp = self.read_response(cmd_pkt)
        return resp.body.decode(self.encoding)

    def _send_pkt(self, pkt):
        """Send one RCON packet over the connection"""
        data = pkt.pack()
        self._sock.send(data)

    def _recv_pkt(self):
        """Read one RCON packet"""
        header = self._rfile.read(struct.calcsize('<3i'))
        (pkt_size, pkt_id, pkt_type) = struct.unpack('<3i', header)
        body = self._rfile.read(pkt_size - 8)
        # Strip the 2 trailing nulls from the body
        body = body.rstrip(b'\x00')
        return RconPacket(pkt_id, pkt_type, body)

    def read_response(self, request=None):
        """Return the next response packet"""
        if request and not isinstance(request, RconPacket):
            raise TypeError('Expected RconPacket type for request')
        response = self._recv_pkt()
        if (response.pkt_type != SERVERDATA_RESPONSE_VALUE and
                response.pkt_type != SERVERDATA_AUTH_RESPONSE):
            raise RconError('Recieved unexpected RCON packet type')
        if request and response.pkt_id != request.pkt_id:
            raise RconError('Response ID does not match request ID')
        return response


class RconError(Exception):
    """Generic RCON error"""
    pass


class RconAuthError(RconError):
    """Raised if an RCON Authentication error occurs"""


if __name__ == '__main__':
    import sys
    host, port, password, *cmd = sys.argv[1:]
    port = int(port)
    cmd = ' '.join(cmd)

    conn = RconConnection(host, port, password)
    print(repr(conn.exec_command(cmd)))
