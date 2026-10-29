# -*- coding: utf-8 -*-
"""xbmc stub."""

LOGDEBUG = 10
LOGINFO = 20
LOGWARNING = 30
LOGERROR = 40

_lines = []


def log(message, level=LOGDEBUG):
    _lines.append((level, message))


def executebuiltin(command, wait=False):
    _lines.append((LOGINFO, "builtin: " + command))


def getCondVisibility(condition):
    return False


def sleep(milliseconds):
    pass
