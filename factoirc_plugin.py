# -*- coding: utf-8 -*-
from irc3.plugins.command import command
from rcon import RconConnection
import irc3
import irc3.utils
import sys
import re

try:
    from systemd import journal
except ImportError:
    journal = None

ONLINE_RE = re.compile(r'\s*(.*?)\s+\(online\)')
LOG_PATTERN = r'\s*(?P<time>[\d.]+) (?P<level>Info|Verbose|Warning|Error) '
JOIN_PART_RE = re.compile(LOG_PATTERN + r'[^ ]+ MapTick\(\d+\) processed Player(?P<action>Leave|Join)Game peerID\((?P<peer_id>\d+)\).*')
USERNAME_RE = re.compile(LOG_PATTERN + r'[^ ]+ Received peer info for peer\((?P<peer_id>\d+)\) username\((?P<username>mickael9)\).*')
CHAT_RE = re.compile(r'(?P<username>[^: ]+): (?P<message>.*)')


class SystemdJournalLogReader:
    def __init__(self, loop, callback, unit, **kwargs):
        print('Using systemd log reader: unit=%s' % unit)
        if journal is None:
            raise ImportError("Please install the systemd python module")
        self.loop = loop
        self.callback = callback
        self.reader = journal.Reader()
        self.reader.add_match(_SYSTEMD_UNIT=unit)
        self.reader.seek_tail()
        # seek_tail() doesn't seem to work as expected and leaves a
        # few messages at the end so make sure we consume them first
        list(self.reader)
        self.fd = self.reader.fileno()
        self.loop.add_reader(self.fd, self.on_fd_ready)

    def __del__(self):
        self.loop.remove_reader(self.fd)

    def on_fd_ready(self):
        for entry in self.reader:
            if not entry:  # empty dict = no more entries
                break
            self.callback(entry['MESSAGE'])


class StdinLogReader:
    def __init__(self, loop, callback, **kwargs):
        print('Using stdin log reader')
        self.loop = loop
        self.callback = callback
        self.task = loop.create_task(self.log_read())

    def __del__(self):
        self.task.cancel()

    async def log_read(self):
        while True:
            line = await self.loop.run_in_executor(
                None,
                sys.stdin.readline
            )
            if not line:  # stdin closed...
                break
            self.callback(line.strip('\n'))

READERS = {
    'stdin': StdinLogReader,
    'systemd': SystemdJournalLogReader,
}


@irc3.plugin
class Plugin(object):
    def __init__(self, bot):
        self.bot = bot
        self.config = bot.config.get(self.__class__.__module__, {})
        self.channels = irc3.utils.as_list(
            self.bot.config.get('autojoins', [])
        )

        self.reader = None
        self.peer_names = {}

    @irc3.event(irc3.rfc.JOIN)
    def on_join(self, mask, channel, **kwargs):
        if mask.nick == self.bot.nick:
            reader_class = READERS[self.config.get('method', 'stdin')]
            self.reader = reader_class(self.bot.loop,
                                       self.log_line,
                                       **self.config)

    @irc3.event(irc3.rfc.PRIVMSG)
    async def on_privmsg(self, mask, target, data, **kwargs):
        if target not in self.channels:
            return
        if data[0:1] == '!':
            return

        await self.do_rcon('(irc) %s: %s' % (mask.nick, data))

    def broadcast(self, msg):
        for channel in self.channels:
            self.bot.privmsg(channel, "(factorio) %s" % msg)

    def log_line(self, line):
        print('Got log line: %r' % line)
        for pattern in (CHAT_RE, JOIN_PART_RE, USERNAME_RE):
            m = pattern.match(line)
            if not m:
                continue

            if pattern == USERNAME_RE:
                peer_id = m.group('peer_id')
                username = m.group('username')
                self.peer_names[peer_id] = username

            elif pattern == JOIN_PART_RE:
                action = m.group('action')
                peer_id = m.group('peer_id')
                try:
                    username = self.peer_names[peer_id]
                except KeyError:
                    continue

                if action == 'Join':
                    msg = '%s joined the game'
                elif action == 'Leave':
                    msg = '%s left the game'

                self.broadcast(msg % username)

            elif pattern == CHAT_RE:
                username = m.group('username')
                if username == '<server>':
                    continue
                message = m.group('message')
                self.broadcast("%s: %s" % (username, message))

    async def do_rcon(self, text):
        def rcon():
            host = self.config.get('rcon_host', 'localhost')
            port = self.config.get('rcon_port', '27015')
            password = self.config.get('rcon_password', '')

            conn = RconConnection(host, int(port), password)
            result = conn.exec_command(text).splitlines()
            return result
        result = await self.bot.loop.run_in_executor(None, rcon)
        return result

    @command(permission='admin')
    async def rcon(self, mask, target, args):
        """Execute an RCON command

            %%rcon <command>...
        """
        cmd = ' '.join(args['<command>'])
        result = await self.do_rcon(cmd)
        return result

    @command(permission='view')
    async def players(self, mask, target, args):
        """Show connected players.

            %%players
        """
        players = await self.do_rcon('/players')
        players = [m.group(1)
                   for m in map(ONLINE_RE.match, players)
                   if m]
        if players:
            return 'Connected players (%d): %s' % (
                    len(players), ', '.join(players))
        else:
            return 'No one is connected'
