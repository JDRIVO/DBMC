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
import time
import pickle
import shutil
import threading

import xbmcgui
import xbmcvfs

from ..utils import *
from .sync_folder import SyncFolder
from .sync_thread import SynchronizeThread
from ..account_settings import AccountSettings
from ..dropbox_client import KodiDropboxClient


class SyncAccount:
    """
    The SyncAccount is a class that executes the synchronization of a account.
    The DropboxSynchronizer tells the SyncAccount when a synchronisation needs to be
    done on user request or when settings of an account are changed.
    """

    def __init__(self, account_name):
        super().__init__()
        self.account_name = account_name
        self._refresh_token = ""
        self._access_token = ""
        self._app_key = ""
        self._app_secret = ""
        self._sync_path = ""
        self._remote_sync_path = "" # DROPBOX_SEP
        self._sync_freq = 0 # Minutes
        self._new_sync_time = 0
        self.root = None
        self._client = None
        self._sync_thread = None
        self._storage_file = None
        self._client_cursor = None
        self._enabled = False
        self.sync_semaphore = threading.Semaphore()
        self._sync_requests = []

    def init(self):
        # Get sync settings
        self._get_settings()

    def stop_sync(self):

        if self._sync_thread:
            self._sync_thread.stop()

    def sync_stopped(self):
        stopped = True

        if self._sync_thread:
            stopped = False

            if not self._sync_thread.is_alive():
                # Done syncing, destroy the thread
                del self._sync_thread
                self._sync_thread = None
                stopped = True

        return stopped

    def check_sync(self):
        """
        Check if it is time to sync according to the interval time.
        And do so when it is time to sync.
        """

        # Check if syncing is in progress
        if self._enabled and self.sync_stopped():
            now = time.time()

            # Did we get sync requests or is it time to sync?
            if len(self._sync_requests) > 0 or self._new_sync_time < now:
                self._sync_requests = []

                if self._new_sync_time < now:
                    # Update new sync time
                    self._update_sync_time()

                if self._get_client(reconnect=True):
                    self._start_sync()

    def notify_sync_request(self, path):

        if self._enabled:
            self._sync_requests.append(path)

    def notify_changed_settings(self):
        self._get_settings()

    def remove_sync_data(self):
        # Remove all sync data
        self.clear_sync_data()

        if xbmcvfs.exists(self._sync_path):
            shutil.rmtree(self._sync_path)

    def _start_sync(self):
        # Use a separate thread to do the syncing, so that the DropboxSynchronizer
        # can still handle other stuff (like changing settings) during syncing
        self._sync_thread = SynchronizeThread(self)
        self._sync_thread.start()

    def _get_settings(self):
        account = AccountSettings(self.account_name)
        self._storage_file = os.path.normpath(f"{account.account_dir}/sync_data.pik")
        got_semaphore = True
        enable = account.synchronisation
        temp_path = account.sync_path
        temp_remote_path = account.remote_path
        temp_freq = float(account.sync_freq)

        # The following settings can't be changed while syncing
        if not self.sync_semaphore.acquire(False):
            got_semaphore = False

            if enable != self._enabled or temp_path != self._sync_path or temp_remote_path != self._remote_sync_path:
                log(f"Can't change settings while synchronizing for {self.account_name}")
                dialog = xbmcgui.Dialog()
                stop_sync = dialog.yesno(ADDON_NAME, f"{LANGUAGE_STRING(30110)} {LANGUAGE_STRING(30113)}")

                if stop_sync:
                    # Stop the Synchronization
                    self.stop_sync()
                    log(f"Synchronizing stopped for {self.account_name}")
                    # Wait for the semaphore to be released
                    self.sync_semaphore.acquire()
                    got_semaphore = True
                else:
                    # Revert the changes
                    account.synchronisation = self._enabled
                    account.sync_path = self._sync_path
                    account.remote_path = self._remote_sync_path
                    account.save()
                    return

        # Enable?
        if enable and (not temp_path or not temp_remote_path):
            enable = False
            account.synchronisation = False
            account.save()
            log_error("Can't enable synchronization: sync_path or remote_path not set")
            dialog = xbmcgui.Dialog()
            dialog.ok(ADDON_NAME, LANGUAGE_STRING(30111))

        self._enabled = enable

        if not self._sync_path:
            # Get initial location
            self._sync_path = temp_path

        # Sync path changed?
        if self._sync_path != temp_path:

            if len(os.listdir(temp_path)) == 0:

                if xbmcvfs.exists(self._sync_path):
                    # Move the old sync path to the new one
                    log(f"Moving sync location for {self.account_name} from {self._sync_path} to {temp_path}")
                    names = os.listdir(self._sync_path)

                    for name in names:
                        src_name = os.path.join(self._sync_path, name)
                        shutil.move(src_name, temp_path)

                self._sync_path = temp_path

                if self.root:
                    self.root.update_local_root_path(self._sync_path)

                log(f"Sync_path updated for {self.account_name}")
                xbmc.executebuiltin(f"Notification({LANGUAGE_STRING(30103)},{temp_path},{7000},{ADDON_ICON})")

            else:
                log_error(f"New sync location is not empty: {temp_path}")
                dialog = xbmcgui.Dialog()
                dialog.ok(ADDON_NAME, f"{LANGUAGE_STRING(30104)} {temp_path}")
                # Restore the old location
                account.sync_path = self._sync_path
                account.save()

        if not self._remote_sync_path:
            # Get initial location
            self._remote_sync_path = temp_remote_path

        # Remote path changed?
        if temp_remote_path != self._remote_sync_path:
            self._remote_sync_path = temp_remote_path
            log(f"Changed remote path for {self.account_name} to {self._remote_sync_path}")

            if self.root:
                # Restart the synchronization
                # Remove all the files in current sync_path
                if xbmcvfs.exists(self._sync_path) and len(os.listdir(self._sync_path)) > 0:
                    shutil.rmtree(self._sync_path)

                # Reset the complete data on client side
                self.clear_sync_data()
                del self.root
                self.root = None
                # Start sync immediately
                self._new_sync_time = time.time()

        # Time interval changed?
        self._update_sync_time(temp_freq)
        # Reconnect to Dropbox (in case the token has changed)
        self._refresh_token = account.refresh_token
        self._access_token = account.access_token
        self._app_key = account.app_key
        self._app_secret = account.app_secret
        self._get_client(reconnect=True)

        if self._enabled and not self.root:
            log(f"Enabled synchronization for {self.account_name}")
            self._setup_sync_root()
        elif not self._enabled and self.root:
            log(f"Disabled synchronization for {self.account_name}")
            self._sync_freq = 0 # Trigger a sync next time it is enabled again
            self.stop_sync()
            del self.root
            self.root = None

        if got_semaphore:
            self.sync_semaphore.release()

    def _get_client(self, reconnect=False):

        if reconnect and self._client:
            self._client.disconnect()
            self._client = None

        if not self._client:
            self._client = KodiDropboxClient(
                self._access_token,
                self._refresh_token,
                self._app_key,
                self._app_secret,
                auto_connect=False,
            )
            connected, msg = self._client.connect()

            if not connected:
                log_error(f"DropboxSynchronizer could not connect to dropbox: {msg}")
                self._client = None

            # Update changed client to the root sync folder
            if self.root:
                self.root.set_client(self._client)

        return self._client

    def _update_sync_time(self, new_freq=None):

        if new_freq and self._sync_freq == 0:
            # Trigger initial sync after startup
            self._new_sync_time = time.time()
            self._sync_freq = new_freq
        else:
            update = False

            if not new_freq:
                update = True
            elif self._sync_freq != new_freq:
                self._sync_freq = new_freq
                update = True

            if update:
                freq_secs = self._sync_freq * 60
                self._new_sync_time = time.time() + freq_secs
                log_debug(f"New sync time: {time.strftime('%Y-%d-%mT%H:%M', time.localtime(self._new_sync_time))}")

    def _setup_sync_root(self):
        self.create_sync_root()
        # Update items which are in the cache
        client_cursor = self.get_client_cursor()

        if client_cursor:
            log_debug("Setup sync root with stored remote data")
            cursor, remote_data = self.get_sync_data()

            if remote_data:

                for path, metadata in remote_data.items():

                    if path.find(self.root.path) == 0:
                        self.root.set_item_info(path, metadata)

                self.root.update_local_root_path(self._sync_path)

            else:
                log_error("Remote cursor present, but no remote data")

    def create_sync_root(self):
        self.root = SyncFolder(self._remote_sync_path, self._client)

    def get_client_cursor(self):

        if not self._client_cursor:
            # Try to get the cursor from storage
            cursor, data = self.get_sync_data()

            if cursor:
                log_debug("Using stored remote cursor")
                self._client_cursor = cursor

        return self._client_cursor

    def store_sync_data(self, cursor=None):
        data = None

        if self.root:
            data = self.root.get_items_info()

        if cursor:
            self._client_cursor = cursor

        log_debug("Storing sync data")

        try:

            with open(self._storage_file, "wb") as f:
                pickle.dump([self._client_cursor, data], f, -1)

        except EnvironmentError as e:
            log_error(f"Storing storage_file Exception: {e!r}")

    def get_sync_data(self):
        data = None
        cursor = None

        try:

            with open(self._storage_file, "rb") as f:
                cursor, data = pickle.load(f)

        except EnvironmentError as e:
            log(f"Opening storage_file Exception: {e!r}")

        return cursor, data

    def clear_sync_data(self):
        self._client_cursor = None

        try:
            os.remove(self._storage_file)
        except OSError as e:
            log(f"Removing storage_file Exception: {e!r}")
