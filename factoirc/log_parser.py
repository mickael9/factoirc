import re

LOG_PATTERN = r'\s*(?P<time>[\d.]+) (?P<level>Info|Verbose|Warning|Error) '
JOIN_PART_RE = re.compile(
    LOG_PATTERN +
    r'[^ ]+ MapTick\(\d+\) processed Player(?P<action>Leave|Join)Game '
    r'peerID\((?P<peer_id>\d+)\).*'
)
USERNAME_RE = re.compile(
    LOG_PATTERN +
    r'[^ ]+ Received peer info for peer'
    r'\((?P<peer_id>\d+)\) username\((?P<username>[^)]+)\).*'
)

TIMESTAMP = r'(?P<date>\d+-\d+-\d+)\s+(?P<time>\d+:\d+:\d+)'

CHAT_RE = re.compile(
    r'(?:%s\s+\[CHAT\]\s+)?' % TIMESTAMP +  # prefix for Factorio >=0.13.10
    r'(?P<username>[^: ]+):\s+(?P<message>.*)',
    re.X
)

ACTION_RE = re.compile(
    TIMESTAMP + r'\s+' +
    r'''\[(?P<action>JOIN|LEAVE|KICK|BAN|COMMAND)]
        \s+
        (?P<username>[^\s]+)
        \s+
        (?P<message>.*)''',
    re.X
)

# Parse additional fields for those specific actions
ACTIONS_RE = dict(
    kick=r'was kicked by (?P<by>[^.\s]+)\. '
         r'Reason: (?:unspecified|(?P<reason>.*))\.',

    ban=r'was banned by (?P<by>[^.\s]+)\. '
        r'Reason: (?:unspecified|(?P<reason>.*))\.',

    command=r'\(command\):\s+(?P<command>.*)',
)
ACTIONS_RE = {k: re.compile(v) for k, v in ACTIONS_RE.items()}


class LogParser:
    def __init__(self, logger):
        self.logger = logger
        self.peer_names = {}

    def parse_line(self, line):
        for pattern in (CHAT_RE, ACTION_RE, JOIN_PART_RE, USERNAME_RE):
            m = pattern.match(line)
            if not m:
                continue

            result = m.groupdict()

            if result.get('action'):
                result['action'] = result['action'].lower()

            self.logger.debug('regex match: %r', result)

            if pattern == USERNAME_RE:
                peer_id = result['peer_id']
                username = result['username']
                self.peer_names[peer_id] = username
                return

            elif pattern == JOIN_PART_RE:
                action = result['action']
                peer_id = result['peer_id']
                try:
                    username = self.peer_names[peer_id]
                except KeyError:
                    continue

                result['username'] = username

                if action == 'Join':
                    result['message'] = 'joined the game'
                else:
                    result['message'] = 'left the game'

                return result

            elif pattern == CHAT_RE:
                username = result['username']
                if username == '<server>':
                    continue
                result['action'] = 'chat'
                return result

            elif pattern == ACTION_RE:
                action = result['action']
                message = result['message']

                if result['username'] == '<server>':
                    continue

                if action in ACTIONS_RE:
                    m = ACTIONS_RE[action].match(message)
                    if m:
                        result.update(m.groupdict())
                        self.logger.debug(
                            'additional regex match: %r' % m.groupdict())

                return result
