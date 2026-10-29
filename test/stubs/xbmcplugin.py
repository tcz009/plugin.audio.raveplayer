# -*- coding: utf-8 -*-
"""xbmcplugin stub that records what the add-on emits."""

ITEMS = []
RESOLVED = []
CONTENT = []


def addDirectoryItem(handle, url, listitem, isFolder=True):
    ITEMS.append({"url": url, "label": listitem.label, "isFolder": isFolder,
                  "art": listitem.art, "info": listitem.info})
    return True


def addDirectoryItems(handle, items, totalItems=0):
    for url, listitem, is_folder in items:
        addDirectoryItem(handle, url, listitem, is_folder)
    return True


def setContent(handle, content):
    CONTENT.append(content)
    return True


def endOfDirectory(handle, succeeded=True, updateListing=False, cacheToDisc=True):
    return True


def setResolvedUrl(handle, succeeded, listitem):
    RESOLVED.append({"ok": succeeded, "path": listitem.path, "label": listitem.label})
    return True
