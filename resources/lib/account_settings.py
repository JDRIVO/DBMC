#/*
# *      Copyright (C) 2013 Joost Kop
# *
# *
# *  This Program is free software; you can redistribute it and/or modify
# *  it under the terms of the GNU General Public License as published by
# *  the Free Software Foundation; either version 2, or (at your option)
# *  any later version.
# *
# *  This Program is distributed in the hope that it will be useful,
# *  but WITHOUT ANY WARRANTY; without even the implied warranty of
# *  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# *  GNU General Public License for more details.
# *
# *  You should have received a copy of the GNU General Public License
# *  along with this program; see the file COPYING.  If not, write to
# *  the Free Software Foundation, 675 Mass Ave, Cambridge, MA 02139, USA.
# *  http://www.gnu.org/copyleft/gpl.html
# *
# */

import os
import pickle
import shutil

import xbmcvfs

from .utils import *


class AccountSettings:
    """
    Class which loads and saves all the account settings,
    for easy access to the account settings
    """

    def __init__(self, account_name):
        self.account_name = account_name
        self.refresh_token = ""
        self.access_token = ""
        self.app_key = ""
        self.app_secret = ""
        self.remote_path = ""
        self.sync_path = ""
        self.passcode = ""
        self.passcode_timeout = 30
        self.sync_freq = 5
        self.synchronisation = False
        self.account_dir = os.path.normpath(f"{DATA_PATH}/accounts/{self.account_name}") + os.sep # Add os seperator because it is a dir

        if xbmcvfs.exists(self.account_dir):
            self.load()
            # Don't use the stored account_dir
            self.account_dir = os.path.normpath(f"{DATA_PATH}/accounts/{self.account_name}") + os.sep # Add os seperator because it is a dir
        else:
            log_debug(f"Account ({self.account_name}) doesn't exist yet")

    def load(self):
        log_debug(f"Loading account settings: {self.account_name}")
        settings_file = os.path.normpath(self.account_dir + "settings")

        try:

            with open(settings_file, "rb") as file_obj:
                tmp_dict = pickle.load(file_obj)

        except Exception as e:
            log_error(f"Failed to load the settings: {e}")
        else:
            self.__dict__.update(tmp_dict)

    def save(self):
        log_debug(f"Save account settings: {self.account_name}")

        if not xbmcvfs.exists(self.account_dir):
            xbmcvfs.mkdirs(self.account_dir)

        settings_file = os.path.normpath(self.account_dir + "settings")

        try:

            with open(settings_file, "wb") as file_obj:
                pickle.dump(self.__dict__, file_obj)

        except Exception as e:
            log_error(f"Failed saving the settings: {e}")

    def remove(self):
        log_debug(f"Remove account folder: {self.account_dir}")
        shutil.rmtree(self.account_dir)
        shutil.rmtree(get_cache_path(self.account_name))
        from .dropbox_cache import DropboxCache
        cache = DropboxCache(self.account_name)
        cache.delete()
        # Remove synced data is done in the DropboxSynchronizer
