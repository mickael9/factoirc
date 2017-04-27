#!/usr/bin/env python3

__version__ = '0.6'

import re
import asyncio
import logging

import irc3

from irc3.utils import as_list, as_channel
from irc3.plugins.command import command

from . import readers
from .utils import catch
from .rcon import RconConnection
from .irc_colors import IRCColors
from .log_parser import LogParser


ONLINE_RE = re.compile(r'\s*(.*?)\s+\(online\)')

DEFAULT_CONFIG = dict(
    method='stdin',
    file='console.log',
    unit='factorio.service',
    rcon_timeout=5,
    rcon_host='localhost',
    rcon_port=27015,
    rcon_password='password',
)

DEFAULT_FORWARDING = dict(
    irc=dict(
        actions='all',
        prefix='(irc)',
        chat='{nick}: {message}',
        join='{nick} joined {channel}.',
        leave='{nick} left {channel} ({reason}).',
        kick='{nick} was kicked off {channel} by {by} ({reason})',
        quit='{nick} quit {channel} ({reason}).',
        newnick='{nick} renamed to {newnick}',
        default_reason='unspecified',
    ),
    game=dict(
        actions='all',
        prefix='(factorio)',
        chat='{username}: {message}',
        default='{username} {message}',
        default_reason='unspecified',
    )
)


@irc3.plugin
class FactoIRC:
    requires = ['irc3.plugins.command', 'irc3.plugins.userlist']

    FORMAT_ALIASES = dict(
        B=IRCColors.bold,
        I=IRCColors.italic,
        U=IRCColors.underline,
        V=IRCColors.reverse,
        R=IRCColors.reset,
        C=IRCColors.color,
    )

    def __init__(self, bot):
        self.bot = bot
        self.reader = None

        self.log = logging.getLogger('irc3.%s' % __name__)
        self.log_parser = LogParser(self.log)

        self.config = dict(DEFAULT_CONFIG)
        self.config.update(bot.config.get(self.__class__.__module__, {}))
        self.log.debug('config: %r', self.config)

        autojoins = self.bot.config.get('autojoins')
        self.channels = [
            as_channel(c)
            for c in as_list(
                self.config.get('channels', autojoins)
            )
        ]

        self.actions = {}

        for act_type in DEFAULT_FORWARDING:
            config = dict(DEFAULT_FORWARDING[act_type])
            config.update(self.bot.config.get(
                '%s.%s-forwarding' % (self.__class__.__module__, act_type)))
            self.actions[act_type] = config

        self.log.debug('actions: %r', self.actions)

        # on_quit needs to be executed before the userlist plugin sees
        # the QUIT event so that we can check which channels the user
        # was in
        self.bot.attach_events(
            irc3.event(irc3.rfc.QUIT, self.on_quit),
            insert=True
        )
        self.log.info('FactoIRC %s loaded.' % __version__)

    def format_action(self, act_type, action, **kwargs):
        config = self.actions[act_type]
        actions = set(as_list(config['actions']))

        if not {action, 'all'} & actions:
            return

        values = {k[8:]: v
                  for k, v in config.items()
                  if k.startswith('default_')}

        values.update({k: v
                       for k, v in kwargs.items()
                       if k not in values or v})

        fmt = config.get(action, config.get('default', ''))
        if not fmt:
            raise ValueError('Undefined action: %s' % action)
        if config.get('prefix'):
            fmt = config['prefix'] + ' ' + fmt

        return fmt.format(**values)

    async def irc_action(self, action, channel, simulate=False, **kwargs):
        if channel not in self.channels:
            return
        msg = self.format_action('irc', action, channel=channel, **kwargs)
        if simulate:
            return msg
        if msg:
            await self.do_rcon(msg)

    async def game_action(self, action, simulate=False, **kwargs):
        msg = self.format_action(
            'game', action, c=IRCColors, **self.FORMAT_ALIASES, **kwargs)
        if msg.strip().startswith('/'):
            raise ValueError("Formatted message can't begin with /")
        if simulate:
            return msg
        if msg:
            self.broadcast(msg)

    @irc3.event(irc3.rfc.JOIN)
    async def on_join(self, mask, channel, **kwargs):
        if not self.actions['irc'] or self.actions['irc'] == {'none'}:
            # Nothing to forward, don't bother to create a reader
            return

        if mask.nick == self.bot.nick:
            if not self.reader:
                self.reader = readers.new(
                    self.config['method'], self.bot.loop,
                    self.log_line, **self.config)
            return

        await self.irc_action('join', channel=channel, nick=mask.nick)

    @irc3.event(irc3.rfc.PART)
    async def on_part(self, mask, channel, data, **kwargs):
        await self.irc_action(
            'leave', channel=channel, nick=mask.nick,
            reason=data
        )

    @irc3.event(irc3.rfc.KICK)
    async def on_kick(self, mask, channel, target, data, **kwargs):
        await self.irc_action(
            'kick', channel=channel, nick=target, by=mask.nick,
            reason=data
        )

    def on_quit(self, mask, data, **kwargs):
        for channel in self.channels:
            if mask.nick in self.bot.channels.get(channel, []):
                self.bot.loop.create_task(self.irc_action(
                    'quit', channel=channel, nick=mask.nick,
                    reason=data
                ))
                return

    @irc3.event(irc3.rfc.NEW_NICK)
    async def on_nick(self, nick, new_nick, **kwargs):
        for channel in self.channels:
            if new_nick in self.bot.channels.get(channel, []):
                await self.irc_action(
                    'newnick', channel=channel, nick=nick.nick,
                    newnick=new_nick
                )
                return

    @irc3.event(irc3.rfc.PRIVMSG)
    async def on_privmsg(self, mask, target, data, **kwargs):
        if not target.is_channel:
            return
        if data.startswith(self.bot.config.get('cmd', '!')):
            return

        await self.irc_action(
            'chat', channel=target, nick=mask.nick, message=data)

    def broadcast(self, msg):
        self.log.debug('broadcast: %s', msg)

        for channel in self.channels:
            self.bot.privmsg(channel, msg)

    async def log_line(self, line):
        self.log.debug('log line: %s', line)
        result = self.log_parser.parse_line(line)
        if not result:
            return
        self.log.debug('log parsed: %r', result)
        await self.game_action(**result)

    async def do_rcon(self, text):
        host = self.config['rcon_host']
        port = self.config['rcon_port']
        password = self.config['rcon_password']

        self.log.debug('RCON request: %s', text)

        conn = RconConnection(host, int(port), password, loop=self.bot.loop)
        try:
            result = (await asyncio.wait_for(
                conn.exec_command(text),
                timeout=float(self.config['rcon_timeout']),
                loop=self.bot.loop,
            )).splitlines()
        finally:
            conn.close()

        self.log.debug('RCON response: %r', result)

        return result

    @command(permission='rcon', use_shlex=False)
    @catch
    async def rcon(self, mask, target, args):
        '''
            Execute an RCON command

            %%rcon <command>...
        '''
        cmd = ' '.join(args['<command>'])
        return await self.do_rcon(cmd)

    @command(permission='players')
    @catch
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

    @command(permissions='admin')
    @catch
    async def test_action(self, mask, target, args):
        '''
            Simulate actions (mostly for testing messages format), eg:
            !test_action game kick username=foo by=bar reason=baz

            %%test_action (irc | game) <action> <name>=<value>...
        '''

        values = dict(simulate=True)
        if target.is_channel:
            values['channel'] = target

        values.update(arg.split('=', 2) for arg in args['<name>=<value>'])

        if args['irc']:
            res = await self.irc_action(args['<action>'], **values)
        else:
            res = await self.game_action(args['<action>'], **values)

        if values.get('simulate'):
            return res
