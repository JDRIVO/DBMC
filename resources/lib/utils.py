import os
import sys
import urllib.parse

import xbmc
import xbmcvfs
import xbmcaddon

from .constants import *


ADDON_ID        = "plugin.dbmc"
ADDON_URL       = f"plugin://{ADDON_ID}/"
ADDON           = xbmcaddon.Addon(ADDON_ID)
ADDON_SETTINGS  = ADDON.getSettings()
ADDON_NAME      = ADDON.getAddonInfo("name")
ADDON_PATH      = ADDON.getAddonInfo("path")
ADDON_ICON      = ADDON.getAddonInfo("icon")
LANGUAGE_STRING = ADDON.getLocalizedString
DATA_PATH       = xbmcvfs.translatePath(ADDON.getAddonInfo("profile"))
DROPBOX_SEP     = "/"


def log(txt):
    message = f"{ADDON_ID} {txt}"
    xbmc.log(msg=message, level=xbmc.LOGINFO)


def log_error(txt):
    message = f"{ADDON_ID} {txt}"
    xbmc.log(msg=message, level=xbmc.LOGERROR)


def log_debug(txt):
    message = f"{ADDON_ID} {txt}"
    xbmc.log(msg=message, level=xbmc.LOGDEBUG)


def parse_argv():
    params = {}
    param_string = sys.argv[2]

    if param_string:
        split_params = param_string.lstrip("?").split("&")

        for item in split_params:
            item = urllib.parse.unquote_plus(item)
            key_val = item.split("=")
            params[key_val[0]] = key_val[1]

    return params


def get_cache_path(account_name):
    data_path = ADDON.getSetting("cache_path")

    # Use user defined location?
    if not data_path:
        # Get the default path
        data_path = DATA_PATH

    return os.path.normpath(f"{data_path}/{account_name}")


def get_local_sync_path(local_sync_path, remote_sync_path, item_path):
    item_path = item_path.replace(remote_sync_path, "", 1)
    return os.path.normpath(local_sync_path + DROPBOX_SEP + item_path)


def replace_file_extension(path, file_extension):
    file_extension = "." + file_extension

    if file_extension in path[-len(file_extension):]:
        # File extension is ok, nothing to do
        return path
    else:
        new_path = path.rsplit(".", 1)[0]
        return new_path + file_extension


def identify_file_type(filename):
    file_extension = os.path.splitext(filename)[1][1:].lower()

    if file_extension in VIDEO_EXT:
        return "video"
    elif file_extension in AUDIO_EXT:
        return "audio"
    elif file_extension in IMAGE_EXT:
        return "image"
    else:
        return "other"


def escape_param(s):
    escaped = s.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def xor(w1, w2):
    from itertools import cycle
    # xor two strings together with the length of the first string limiting
    # Ensure w2 is bytes
    w2_bytes = w2.encode("utf-8")
    return bytes(c1 ^ c2 for c1, c2 in zip(w1, cycle(w2_bytes)))


def decode_key(word):
    from base64 import b64decode
    # Decode the word which was encoded with the given secret key
    base = xor(b64decode(word, "-_"), ADDON_NAME).decode("utf-8")
    return base[4:int(base[:3], 10) + 4]
