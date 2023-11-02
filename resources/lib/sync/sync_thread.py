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

import time
import threading

import xbmc

from ..utils import *


class SynchronizeThread(threading.Thread):
    PROGRESS_TIMEOUT = 20.0

    def __init__(self, sync_account):
        super().__init__()
        self._sync_account = sync_account
        self._last_progress_update = 0.0
        self._stop_event = threading.Event()

    def stop(self):
        self._stop_event.set()

    def stopped(self):
        return self._stop_event.is_set()

    def run(self):
        log_debug(f"Start sync for account {self._sync_account.account_name}")
        self._sync_account.sync_semaphore.acquire()
        self._get_remote_changes()

        if not self.stopped():
            self._synchronize()

        self._sync_account.sync_semaphore.release()

        if self.stopped():
            log(f"DropboxSynchronizer: Sync aborted account {self._sync_account.account_name}")
        else:
            log_debug(f"Finished syncing account {self._sync_account.account_name}")

    def _get_remote_changes(self):
        has_more = True
        inital_sync = False
        client_cursor = self._sync_account.get_client_cursor()

        if not client_cursor:
            inital_sync = True
            log("Starting first sync")

        while has_more and not self.stopped():
            # Sync, get all metadata
            data = self._sync_account._client.get_remote_changes(client_cursor)

            if not data:
                return

            items, client_cursor, has_more = data

            # Prepare item list
            for metadata in items:
                path = metadata.path_lower

                if metadata.__class__.__name__ == "FolderMetadata":
                    metadata.is_dir = True
                else:
                    metadata.is_dir = False

                if not inital_sync:
                    log_debug(f"New item info received for {path}")

                if path.find(self._sync_account.root.path) == 0:
                    self._sync_account.root.update_remote_info(path, metadata)

            if len(items) > 0:
                self._sync_account.root.update_local_root_path(self._sync_account._sync_path)

            # Store new cursor + data
            self._sync_account.store_sync_data(client_cursor)

    def _synchronize(self):
        # Get the items to sync
        sync_dirs, sync_items = self._sync_account.root.get_items_to_sync()
        # Always first sync (create) dirs, so that they will have the correct timestamps

        if len(sync_items) > 0 or len(sync_dirs) > 0:

            for dir in sync_dirs:

                if self.stopped():
                    break

                dir.sync()

            items_total = len(sync_items)

            if items_total > 0 and not self.stopped():
                item_number = 0

                for item in sync_items:

                    if self.stopped():
                        break
                    else:
                        self.update_progress(item_number, items_total)
                        synced = item.sync()

                        if synced:
                            item_number += 1

                self.update_progress_finished(item_number, items_total)

            # Store the new data
            self._sync_account.store_sync_data()

    def update_progress(self, handled, total):
        now = time.time()

        if self._last_progress_update + self.PROGRESS_TIMEOUT < now:
            progress_text = f"{handled}/{total} ({self._sync_account.account_name})"
            log(f"Synchronizing number of items: {progress_text}")
            xbmc.executebuiltin(f"Notification({LANGUAGE_STRING(30114)},{progress_text},7000,{ADDON_ICON})")
            self._last_progress_update = now
            # Also store the new data (frequently)
            self._sync_account.store_sync_data()

    def update_progress_finished(self, handled, total):
        progress_text = f"{handled} ({self._sync_account.account_name})"
        log(f"Number of items synchronized: {progress_text}")
        xbmc.executebuiltin(f"Notification({LANGUAGE_STRING(30106)},{LANGUAGE_STRING(30107)}{progress_text},{10000},{ADDON_ICON})")
