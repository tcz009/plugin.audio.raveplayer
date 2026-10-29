# -*- coding: utf-8 -*-
"""xbmc stub."""

LOGDEBUG = 10
LOGINFO = 20
LOGWARNING = 30
LOGERROR = 40

PLAYLIST_MUSIC = 0

_lines = []
PLAYED = []


def log(message, level=LOGDEBUG):
    _lines.append((level, message))


def executebuiltin(command, wait=False):
    _lines.append((LOGINFO, "builtin: " + command))


def getCondVisibility(condition):
    return False


def sleep(milliseconds):
    pass


class PlayList(object):
    def __init__(self, playlist_id=0):
        self.playlist_id = playlist_id
        self.items = []

    def clear(self):
        self.items = []

    def add(self, url, listitem=None, index=-1):
        if index < 0 or index >= len(self.items):
            self.items.append((url, listitem))
        else:
            self.items.insert(index, (url, listitem))
        return True

    def __len__(self):
        return len(self.items)


class Player(object):
    def play(self, item=None, listitem=None, windowed=False, startpos=-1):
        PLAYED.append(item)
        return True

    def isPlaying(self):
        return bool(PLAYED)
