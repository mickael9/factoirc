# -*- coding: utf-8 -*-
from irc3.plugins.command import command
from rcon import RconConnection
import irc3
import irc3.utils
import sys
import re

ONLINE_RE = re.compile(r'\s*(.*?)\s+\(online\)')


@irc3.plugin
class Plugin(object):
    def __init__(self, bot):
        self.bot = bot
        self.config = bot.config.get(self.__class__.__module__, {})
        self.channels = irc3.utils.as_list(self.bot.config.get('autojoins', []))
        self.bot.loop.create_task(self.log_read())
        self.log_format = re.compile(self.config['log_format'])

    @irc3.event(irc3.rfc.PRIVMSG)
    def on_privmsg(self, mask, target, data, **kwargs):
        if target not in self.channels:
            return
        if data[0:1] == '!':
            return

        self.do_rcon('(irc) %s: %s' % (mask.nick, data))

    async def log_read(self):
        while True:
            line = await self.bot.loop.run_in_executor(None, sys.stdin.readline)
            m = self.log_format.match(line)
            if m:
                username = m.group('username')
                if username == '<server>':
                    continue
                message = m.group('message')
                for channel in self.channels:
                    self.bot.privmsg(channel, '(factorio) %s: %s' % (username, message))

    def do_rcon(self, text):
        conn = RconConnection(self.config['rcon_host'],
                              int(self.config['rcon_port']),
                              self.config['rcon_password'])
        return conn.exec_command(text).splitlines()

    @command(permission='admin')
    def rcon(self, mask, target, args):
        """Execute an RCON command

            %%rcon <command>...
        """
        cmd = ' '.join(args['<command>'])
        result = self.do_rcon(cmd)
        yield from result

    @command(permission='view')
    def players(self, mask, target, args):
        """Show connected players.

            %%players
        """
        players = [m.group(1)
                   for m in map(ONLINE_RE.match, self.do_rcon('/players'))
                   if m]
        if players:
            return 'Connected players (%d): %s' % (len(players), ', '.join(players))
        else:
            return 'No one is connected'
