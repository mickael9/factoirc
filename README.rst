========
FactoIRC
========

FactoIRC is a bidirectional IRC bridge between Factorio and IRC.
It comes as a plugin for the irc3_ python module.

It can join one or more channels and forward messages back and forth between IRC and Factorio.

Some IRC commands are also provided :

- **!rcon**: Execute an RCON command and return the result.
- **!players**: Get the list of the currently online players.

FactoIRC uses the RCON protocol introduced in Factorio 0.13 to forward messages from IRC to Factorio.

Forwarding Factorio chat messages to IRC requires access to the Factorio server output which can be done with two methods depending on your setup.

Installation
------------

You'll need to have Python 3.5 (or later) which can be obtained through your distribution's package manager
or downloaded from https://www.python.org/ (for Windows users).

Once Python 3.5 is installed, FactoIRC can be installed using

.. code:: bash

    $ pip3 install factoirc

Configuration
-------------

Configuration is done using the `config.ini` file. A config.example.ini_ file is provided as an example.

Depending on your setup, you will have to use either the `stdin` or the `systemd` method.

Using `stdin` method
~~~~~~~~~~~~~~~~~~~~

Unless you're running your Factorio server on a Linux machine using `systemd`, this is the method you'll use.

You will need to connect the factorio server output to the FactoIRC bot.

This can be achieved using a command such as:

.. code:: bash
   
    $ factorio --rcon-port=27015 --rcon-password=password --start-server=save.zip | irc3 config.ini


Alternatively, you might want to separate execution of Factorio and the bot using an intermediate log file:

.. code:: bash

    $ factorio ... > log.txt
    $ irc3 config.ini < log.txt

**Warning:** do NOT use the `factorio-current.log` file created by Factorio, as it does not contain the chat log.

Using `systemd` method
~~~~~~~~~~~~~~~~~~~~~~

If your Factorio server runs under systemd (only for Linux machines), FactoIRC can directly access the logs from the systemd journal.
You'll need the following options in your configuration file:

.. code:: ini

    [factoirc]
    method = systemd
    unit = factorio.service


For this method to work, the `python-systemd` module is required and can be installed via pip:

.. code:: bash

    $ pip3 install python-systemd

.. _irc3: https://irc3.readthedocs.io/
.. _config.example.ini: config.example.ini
