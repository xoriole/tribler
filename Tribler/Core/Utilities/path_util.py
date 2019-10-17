from __future__ import absolute_import

import os
import pathlib
from shutil import rmtree

from six import text_type


class Path(pathlib.Path):

    def __new__(cls, *args, **kwargs):
        if cls is Path:
            cls = WindowsPath if os.name == 'nt' else PosixPath
        self = cls._from_parts(args, init=False)
        if not self._flavour.is_supported:
            raise NotImplementedError("cannot instantiate %r on your system"
                                      % (cls.__name__,))
        self._init()
        return self

    def rmtree(self, ignore_errors=False, onerror=None):
        """
        Delete the entire directory even if it contains directories / files.
        """
        rmtree(text_type(self), ignore_errors, onerror)

    def startswith(self, text):
        return self.match("%s*" % text)

    def endswith(self, text):
        return self.match("*%s" % text)

    def to_text(self):
        return text_type(self)


class PosixPath(Path, pathlib.PurePosixPath):
    __slots__ = ()


class WindowsPath(Path, pathlib.PureWindowsPath):
    __slots__ = ()


def ensure_path(path):
    return path if isinstance(path, Path) else Path(path)


def abspath(path, optional_prefix=None):
    path = ensure_path(path)
    return path if path.is_absolute() else Path(optional_prefix, path) if optional_prefix else path.absolute()


def norm_path(base_path, path):
    base_path = ensure_path(base_path)
    path = ensure_path(path)
    if path.is_absolute():
        if base_path in list(path.parents):
            return path.relative_to(base_path)
    return path

def normpath(base_path, path):
    return norm_path(base_path, path)


def join(*path):
    return Path(*path)


def exists(path):
    return Path(path).exists()


def makedirs(directory):
    Path(directory).mkdir(parents=True)


def isdir(directory):
    return Path(directory).is_dir()

def isfile(input):
    return Path(input).is_file()

def isabs(input):
    return Path(input).is_absolute()

def dirname(input):
    return Path(input).parent

def issubfolder(base_path, path):
    return base_path in list(path.parents)
