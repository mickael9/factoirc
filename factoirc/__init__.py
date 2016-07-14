#!/usr/bin/env python3

import sys
import re
import os
import asyncio
import logging

import irc3
import irc3.utils

from irc3.plugins.command import command

from .rcon import RconConnection

try:
    from systemd import journal
except ImportError:
    journal = None

ONLINE_RE = re.compile(r'\s*(.*?)\s+\(online\)')
LOG_PATTERN = r'\s*(?P<time>[\d.]+) (?P<level>Info|Verbose|Warning|Error) '
JOIN_PART_RE = re.compile(LOG_PATTERN + r'[^ ]+ MapTick\(\d+\) processed Player(?P<action>Leave|Join)Game peerID\((?P<peer_id>\d+)\).*')
USERNAME_RE = re.compile(LOG_PATTERN + r'[^ ]+ Received peer info for peer\((?P<peer_id>\d+)\) username\((?P<username>[^)]+)\).*')
CHAT_RE = re.compile(r'(?P<username>[^: ]+): (?P<message>.*)')


class SystemdJournalLogReader:
    def __init__(self, loop, callback, unit='factorio.service', **kwargs):
        if journal is None:
            raise ImportError('Please install the systemd python module')

        self.loop = loop
        self.callback = callback
        self.reader = journal.Reader()
        self.reader.add_match(_SYSTEMD_UNIT=unit)
        self.reader.seek_tail()

        # seek_tail() still leaves a few messages at the end
        # so we have to consume them first
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
        self.loop = loop
        self.callback = callback
        self.task = loop.create_task(self.log_read())

        # If stdin is a file, seek to its end
        if sys.stdin.seekable():
            sys.stdin.seek(0, os.SEEK_END)

    def __del__(self):
        self.task.cancel()

    async def log_read(self):
        while True:
            line = await self.loop.run_in_executor(
                None,
                sys.stdin.readline
            )
            if not line:  # EOF reached
                if not sys.stdin.seekable():
                    break
                await asyncio.sleep(0.2, loop=self.loop)
                continue
            line = line.strip('\n')
            self.callback(line)

READERS = {
    'stdin': StdinLogReader,
    'systemd': SystemdJournalLogReader,
}


@irc3.plugin
class FactoIRC:
    requires = ['irc3.plugins.command']

    def __init__(self, bot):
        self.bot = bot
        self.config = bot.config.get(self.__class__.__module__, {})
        self.log = logging.getLogger('irc3.%s' % __name__)
        autojoins = self.bot.config.get('autojoins')
        self.channels = irc3.utils.as_list(
            self.config.get('channels', autojoins)
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
        if data.startswith(self.bot.config.get('cmd', '!')):
            return

        await self.do_rcon('(irc) %s: %s' % (mask.nick, data))

    def broadcast(self, msg):
        self.log.debug('broadcast: %s', msg)

        for channel in self.channels:
            self.bot.privmsg(channel, '(factorio) %s' % msg)

    def log_line(self, line):
        self.log.debug('log line: %s', line)

        for pattern in (CHAT_RE, JOIN_PART_RE, USERNAME_RE):
            m = pattern.match(line)
            if not m:
                continue

            self.log.debug('regex match: %r', m.groupdict())

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
                self.broadcast('%s: %s' % (username, message))

    async def do_rcon(self, text):
        host = self.config.get('rcon_host', 'localhost')
        port = self.config.get('rcon_port', '27015')
        password = self.config.get('rcon_password', '')

        self.log.debug('RCON request: %s', text)

        conn = RconConnection(host, int(port), password, loop=self.bot.loop)
        result = (await conn.exec_command(text)).splitlines()

        self.log.debug('RCON response: %r', result)

        return result

    @command(permission='rcon')
    async def rcon(self, mask, target, args):
        '''
            Execute an RCON command

            %%rcon <command>...
        '''
        cmd = ' '.join(args['<command>'])
        result = await self.do_rcon(cmd)
        return result

    @command(permission='players')
    async def players(self, mask, target, args):
        '''
            Show connected players.

            %%players
        '''
        players = await self.do_rcon('/players')
        players = [m.group(1)
                   for m in map(ONLINE_RE.match, players)
                   if m]
        if players:
            return 'Connected players (%d): %s' % (
                    len(players), ', '.join(players))
        else:
            return 'No one is connected'
