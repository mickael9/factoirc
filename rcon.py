# Copyright (C) 2016 Mickaël Thomas
# Copyright (C) 2013 Peter Rowlands

# From pysrcds project: https://github.com/pmrowla/pysrcds
# Converted to python3 and asyncio.
# Made compatible to the Factorio RCON implementation.

"""Source server RCON communications module"""

import struct
import itertools
import asyncio


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

    def __init__(self, server, port=27015, password='', loop=None,
                 encoding='utf-8'):
        self.server = server
        self.port = port
        self.encoding = encoding
        self.password = password
        self.loop = loop
        self.authenticated = False
        self.pkt_id = itertools.count(1)

    async def authenticate(self, password=None):
        """Authenticate with the server using the given password"""

        if password is None:
            password = self.password
        password = password.encode(self.encoding)

        self.rd, self.wr = await asyncio.open_connection(
            self.server, self.port, loop=self.loop
        )

        auth_pkt = RconPacket(next(self.pkt_id), SERVERDATA_AUTH, password)
        await self._send_pkt(auth_pkt)

        auth_resp = await self.read_response()

        if auth_resp.pkt_type != SERVERDATA_AUTH_RESPONSE:
            raise RconError('Received invalid auth response packet')

        if auth_resp.pkt_id == -1:
            raise RconAuthError('Bad password')

        self.authenticated = True

    async def exec_command(self, command, read_response=True):
        """
        Execute the given RCON command
        Return the response body
        """

        if not self.authenticated:
            await self.authenticate()

        cmd_pkt = RconPacket(next(self.pkt_id), SERVERDATA_EXECCOMMAND,
                             command.encode(self.encoding))

        await self._send_pkt(cmd_pkt)
        if read_response:
            resp = await self.read_response(cmd_pkt)
            return resp.body.decode(self.encoding)
        else:
            return cmd_pkt

    async def _send_pkt(self, pkt):
        """Send one RCON packet over the connection"""

        data = pkt.pack()
        self.wr.write(data)
        await self.wr.drain()

    async def _recv_pkt(self):
        """Read one RCON packet"""

        header = await self.rd.readexactly(struct.calcsize('<3i'))
        (pkt_size, pkt_id, pkt_type) = struct.unpack('<3i', header)
        body = await self.rd.readexactly(pkt_size - 8)

        # Strip the 2 trailing nulls from the body
        body = body.rstrip(b'\x00')

        return RconPacket(pkt_id, pkt_type, body)

    async def read_response(self, request=None):
        """Return the next response packet"""

        if request and not isinstance(request, RconPacket):
            raise TypeError('Expected RconPacket type for request')

        response = await self._recv_pkt()

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


def main():
    import sys

    if len(sys.argv) < 5:
        print('Usage: %s <host> <port> <password> <command>...' % sys.argv[0])
        sys.exit(1)

    host, port, password, *cmd = sys.argv[1:]
    port = int(port)
    cmd = ' '.join(cmd)

    loop = asyncio.get_event_loop()
    conn = RconConnection(host, port, password)
    resp = loop.run_until_complete(conn.exec_command(cmd))
    print(resp, end='')

if __name__ == '__main__':
    main()
