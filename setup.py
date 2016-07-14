from setuptools import setup, find_packages

with open('README.rst', 'r', encoding='utf-8') as f:
    long_description = f.read()

setup(
    name='factoirc',

    version='0.2',

    description='Bidirectional IRC bridge for Factorio',
    long_description=long_description,

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
