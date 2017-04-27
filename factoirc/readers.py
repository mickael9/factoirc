import os
import sys
import asyncio

try:
    from systemd import journal
except ImportError:
    journal = None


class StreamLogReader:
    task = None

    def __init__(self, stream, loop, callback, **kwargs):
        self.stream = stream
        self.loop = loop
        self.callback = callback
        self.task = loop.create_task(self.log_read())

        # If the stream is a file, seek to its end
        if self.stream.seekable():
            self.stream.seek(0, os.SEEK_END)

    def __del__(self):
        if self.task:
            self.task.cancel()

    async def log_read(self):
        while True:
            line = await self.loop.run_in_executor(
                None,
                self.stream.readline
            )
            if not line:  # EOF reached
                if not self.stream.seekable():
                    break
                await asyncio.sleep(0.2, loop=self.loop)
                continue
            line = line.strip('\n')
            self.loop.create_task(self.callback(line))


class StdinLogReader(StreamLogReader):
    def __init__(self, loop, callback, **kwargs):
        super().__init__(sys.stdin, loop, callback, **kwargs)


class FileLogReader(StreamLogReader):
    def __init__(self, loop, callback, file, **kwargs):
        stream = open(file, encoding='utf-8')
        super().__init__(stream, loop, callback, **kwargs)


class SystemdJournalLogReader:
    def __init__(self, loop, callback, unit, **kwargs):
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
            self.loop.create_task(self.callback(entry['MESSAGE']))
        self.reader.process()


READERS = dict(
    file=FileLogReader,
    stdin=StdinLogReader,
    systemd=SystemdJournalLogReader,
)


def new(name, loop, callback, **kwargs):
    try:
        reader_class = READERS[name]
    except KeyError:
        raise ValueError("Unknown reader name: %s" % name)

    return reader_class(loop, callback, **kwargs)
