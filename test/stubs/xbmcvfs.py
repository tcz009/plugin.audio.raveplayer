# -*- coding: utf-8 -*-
"""xbmcvfs stub backed by the real filesystem (tests use temp dirs)."""

import os


def translatePath(path):
    return path


def exists(path):
    return os.path.exists(path)


def mkdirs(path):
    try:
        os.makedirs(path, exist_ok=True)
        return True
    except OSError:
        return False


def remove(path):
    try:
        os.remove(path)
        return True
    except OSError:
        return False


def rename(source, destination):
    try:
        os.replace(source, destination)
        return True
    except OSError:
        return False


class File(object):
    def __init__(self, path, mode="r"):
        self.path = path
        self.mode = mode
        self.handle = open(path, mode)

    def write(self, data):
        return self.handle.write(data)

    def read(self):
        return self.handle.read()

    def size(self):
        try:
            return os.path.getsize(self.path)
        except OSError:
            return 0

    def close(self):
        self.handle.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        self.close()
