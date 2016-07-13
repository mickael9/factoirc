from setuptools import setup, find_packages
setup(
    name='factoirc',

    version='0.1',

    description='Bidirectional IRC bridge for Factorio',

    url='https://github.com/mickael9/factoirc',

    author='Mickaël Thomas',
    author_email='mickael9@gmail.com',

    license='MIT',

    classifiers=[
        'Development Status :: 3 - Alpha',

        'License :: OSI Approved :: MIT License',

        'Programming Language :: Python :: 3.5',

        'Topic :: Communications :: Chat :: Internet Relay Chat',
        'Topic :: Games/Entertainment',
    ],

    keywords='factorio irc',

    packages=find_packages(),

    install_requires=['irc3'],

    extras_require={
        'systemd': ['python-systemd'],
    },
)
