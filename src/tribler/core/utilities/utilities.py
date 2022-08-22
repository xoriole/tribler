"""
This module mainly provides validation and correction for urls. This class
provides a method for HTTP GET requests as well as a function to translate peers into health.
Author(s): Jie Yang
"""
import binascii
import itertools
import logging
import platform
import random
import re
import sys
from base64 import b32decode
from dataclasses import dataclass, field
from functools import wraps
from typing import Set, Tuple
from urllib.parse import parse_qsl, urlsplit

from tribler.core.components.libtorrent.utils.libtorrent_helper import libtorrent as lt
from tribler.core.utilities.sentinels import sentinel

logger = logging.getLogger(__name__)

# Sentinel representing that SQLite must create database in-memory with ":memory:" argument
MEMORY_DB = sentinel('MEMORY_DB')


# Decorator to prevent creating new object properties at runtime.
# Copy-pasted from SO post: https://stackoverflow.com/a/29368642
# (c) Yoann Quenach de Quivillic
def froze_it(cls):
    cls.__frozen = False

    def frozensetattr(self, key, value):
        if self.__frozen and not hasattr(self, key):
            exc_text = "Class {} is frozen. Cannot set {} = {}".format(cls.__name__, key, value)
            raise AttributeError(exc_text)
        else:
            object.__setattr__(self, key, value)

    def init_decorator(func):
        @wraps(func)
        def wrapper(self, *args, **kwargs):
            func(self, *args, **kwargs)
            self.__frozen = True

        return wrapper

    cls.__setattr__ = frozensetattr
    cls.__init__ = init_decorator(cls.__init__)

    return cls


def is_valid_url(url):
    """
    Checks whether the given URL is a valid URL.

    Both UDP and HTTP URLs will be validated correctly.

    :param url: an object representing the URL
    :return: Boolean specifying whether the URL is valid
    """
    if ' ' in url.strip():
        return
    if url.lower().startswith('udp'):
        url = url.lower().replace('udp', 'http', 1)
    split_url = urlsplit(url)

    return not (split_url[0] == '' or split_url[1] == '')


def parse_magnetlink(url):
    """
    Parses the magnet link provided by the given URL.

    The output of this file consists of:
        -   dn: The display name of the magnet link
        -   xt: The URI containing the file hash of the magnet link
        -   trs: The list of Tracker URLs
    :param url: the URL at which the magnet link can be found
    :return: (dn, xt, trs) tuple, which will be left (None, None, []) if the
    given URL does not lead to a magnet link
    """
    dn = None
    xt = None
    trs = []

    logger.debug("parse_magnetlink() %s", url)

    schema, netloc, path, query, fragment = urlsplit(url)
    if schema == "magnet":
        # magnet url's do not conform to regular url syntax (they
        # do not have a netloc.)  This causes path to contain the
        # query part.
        if "?" in path:
            pre, post = path.split("?", 1)
            if query:
                query = "&".join((post, query))
            else:
                query = post

        for key, value in parse_qsl(query):
            if key == "dn":
                # convert to Unicode
                dn = value.decode('utf-8') if not isinstance(value, str) else value

            elif key == "xt" and value.startswith("urn:btih:"):
                # vliegendhart: Adding support for base32 in magnet links (BEP 0009)
                encoded_infohash = value[9:49]
                if len(encoded_infohash) == 32:
                    xt = b32decode(encoded_infohash.upper())
                else:
                    xt = binascii.unhexlify(encoded_infohash)

            elif key == "tr":
                trs.append(value)

        logger.debug("parse_magnetlink() NAME: %s", dn)
        logger.debug("parse_magnetlink() HASH: %s", xt)
        logger.debug("parse_magnetlink() TRACS: %s", trs)

    return dn, xt, trs


def is_simple_match_query(query):
    """
    Check if the query is a simple match query with AND operators only.
    Supports unicode characters.
    """
    pattern = re.compile(r"\"[\\\w]+\"\*", flags=re.UNICODE)
    splits = pattern.split(query)
    for connector in splits:
        if connector and connector != " AND ":
            return False
    return True


def has_bep33_support():
    """
    Return whether our libtorrent version has support for BEP33 (DHT health lookups).
    Also see https://github.com/devos50/libtorrent/tree/bep33_support
    """
    return 'dht_pkt_alert' in dir(lt)


def is_infohash(infohash):
    return infohash and len(infohash) == 40 and is_hex_string(infohash)


def is_channel_public_key(key):
    return key and len(key) == 128 and is_hex_string(key)


def is_hex_string(text):
    try:
        int(text, 16)
        return True
    except ValueError:
        return False


def bdecode_compat(packet_buffer):
    """
    Utility method to make libtorrent bdecode() with Python3 in the existing Tribler codebase.
    We should change this when Libtorrent wrapper is refactored.
    """
    try:
        return lt.bdecode(packet_buffer)
    except RuntimeError:
        return None


def random_infohash(random_gen=None):
    r = random_gen or random
    return r.getrandbits(20 * 8).to_bytes(20, byteorder='big')


def is_frozen():
    """
    Return whether we are running in a frozen environment
    """
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        sys._MEIPASS  # pylint: disable=protected-access
    except Exception:  # pylint: disable=broad-except
        return False
    return True


fts_query_re = re.compile(r'\w+', re.UNICODE)
tags_re = re.compile(r'#[^\s^#]{3,50}(?=[#\s]|$)')


@dataclass
class Query:
    original_query: str
    tags: Set[str] = field(default_factory=set)
    fts_text: str = ''


def parse_query(query: str) -> Query:
    """
    The query structure:
        query = [tag1][tag2] text
                 ^           ^
                tags        fts query
    """
    if not query:
        return Query(original_query=query)

    tags, remaining_text = extract_tags(query)
    return Query(original_query=query, tags=tags, fts_text=remaining_text.strip())


def extract_tags(text: str) -> Tuple[Set[str], str]:
    if not text:
        return set(), ''

    tags = set()
    positions = [0]

    for m in tags_re.finditer(text):
        tag = m.group(0)[1:]
        tags.add(tag.lower())
        positions.extend(itertools.chain.from_iterable(m.regs))
    positions.append(len(text))

    remaining_text = ''.join(text[positions[i] : positions[i + 1]] for i in range(0, len(positions) - 1, 2))
    return tags, remaining_text


def to_fts_query(text):
    if not text:
        return None

    words = [f'"{w}"' for w in fts_query_re.findall(text) if w]
    if not words:
        return None

    return ' '.join(words) + '*'


def show_system_popup(title, text):
    """
    Create a native pop-up without any third party dependency.

    :param title: the pop-up title
    :param text: the pop-up body
    """
    sep = "*" * 80

    # pylint: disable=import-outside-toplevel, import-error, broad-except
    print('\n'.join([sep, title, sep, text, sep]), file=sys.stderr)  # noqa: T001
    system = platform.system()
    try:
        if system == 'Windows':
            import win32api

            win32api.MessageBox(0, text, title)
        elif system == 'Linux':
            import subprocess

            subprocess.Popen(['xmessage', '-center', text])
        elif system == 'Darwin':
            import subprocess

            subprocess.Popen(['/usr/bin/osascript', '-e', text])
        else:
            print(f'cannot create native pop-up for system {system}')  # noqa: T001
    except Exception as exception:
        # Use base Exception, because code above can raise many
        # non-obvious types of exceptions:
        # (SubprocessError, ImportError, win32api.error, FileNotFoundError)
        print(f'Error while showing a message box: {exception}')  # noqa: T001


def get_normally_distributed_number(mean=0, limit=100) -> float:
    """
    Returns a random floating point number based on normal distribution with default mean set as zero.
    This favors the lower value numbers to be selected more than the higher value numbers.
    """
    if limit <= 1:
        return 0

    while True:
        result = random.normalvariate(mean, limit / 3)
        if abs(result) < limit:
            return result
        return result


def get_normally_distributed_positive_integer(mean=0, limit=100) -> int:
    return abs(int(get_normally_distributed_number(mean=mean, limit=limit)))


def get_normally_distributed_positive_integers(size=1, limit=100) -> list:
    """
    Returns a list of non-repeated integer numbers based on normal distribution with mean value zero.
    """
    if size > limit:
        raise Exception("Cannot more numbers than the limit")

    numbers = []
    while len(numbers) < size:
        number = get_normally_distributed_positive_integer(mean=0, limit=limit)
        if number not in numbers:
            numbers.append(number)
    return numbers
