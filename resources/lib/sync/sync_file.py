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
from stat import *

import xbmcvfs

from ..utils import *
from .sync_object import SyncObject


class SyncFile(SyncObject):

    def __init__( self, path, client):
        log_debug(f"Create SyncFile: {path}")
        super().__init__(path, client)
        self._file_type = None
        self.is_dir = False

    def in_sync(self):

        if self._state == self.OBJECT_SKIP:
            log_debug(f"Skipping file: {self._local_path}")
            return self.OBJECT_IN_SYNC # Fake object in sync

        local_present = False

        if self._local_path:
            local_present = xbmcvfs.exists(self._local_path)
        elif self._remote_present:
            log_error(f"Has no local_path: {self.path}")

        local_timestamp = 0

        if local_present:
            st = os.stat(self._local_path)
            local_timestamp = st[ST_MTIME]

        # File present
        if not local_present and self._remote_present:
            return self.OBJECT_TO_DOWNLOAD

        if not self._remote_present:

            if local_present:
                return self.OBJECT_TO_REMOVE
#                 # Check if local file is a newer one than the old remote file
#                 # if so, use the new local file
#                 if local_timestamp > self._local_timestamp:
#                     return self.OBJECT_TO_UPLOAD
#                 else:
#                     return self.OBJECT_TO_REMOVE
            else:
                # File is completely removed, so can be removed from memory as well
                return self.OBJECT_REMOVED

        # Compare timestamps
        if self._new_remote_timestamp > self._remote_timestamp:
            return self.OBJECT_TO_DOWNLOAD
#                 # Check if local file is a newer one than the new remote file
#                 # if so, use the new local file
#                 if local_timestamp > self._local_timestamp and local_timestamp > self._remote_timestamp:
#                     return self.OBJECT_TO_UPLOAD
#                 else:
#                     return self.OBJECT_TO_DOWNLOAD
#         if local_timestamp > self._local_timestamp:
#             return self.OBJECT_TO_UPLOAD

        return self.OBJECT_IN_SYNC

    def sync(self):
        succeeded = False

        if self._state == self.OBJECT_SKIP:
            return succeeded

        self._state = self.in_sync()

        if self._state == self.OBJECT_TO_DOWNLOAD:
            log_debug(f"Download file to: {self._local_path}")
            # succeeded = self._client.save_file(self.path, self._local_path)

            # if succeeded:
                # self.update_timestamp()

            # if self._file_type == "video":
            self._client.save_strm(self._id, self._local_path)
            self.update_timestamp()

        elif self._state == self.OBJECT_TO_UPLOAD:
            log_debug(f"Upload file: {self._local_path}")
            # Addon doesn't support 2 way sync
            # succeeded = self._client.upload(self._local_path, self.path)

            # if succeeded:
                # st = os.stat(self._local_path)
                # self._local_timestamp = st[ST_MTIME]

        elif self._state == self.OBJECT_TO_REMOVE:
            log_debug(f"Removing file: {self._local_path}")

            try:
                os.remove(self._local_path)
            except OSError as e:
                log_error(f"{self._local_path} doesn't exist locally")

            succeeded = True

        elif self._state == self.OBJECT_IN_SYNC or self._state == self.OBJECT_REMOVED:
            succeeded = True
        else:
            log_error(f"Unknown file status ({self._state}) for: {self.path}")
            return succeeded

        if not succeeded:

            if self._failure:
                # failure happened before so skip this item in all the next syncs
                self._state = self.OBJECT_SKIP
                log_error(f"Skipping file in the next syncs: {self._local_path}")

            self._failure = True

        return succeeded

    def set_item_info(self, path, metadata):
        self._file_type = identify_file_type(metadata.name)

        if path == self.path:
            super().set_item_info(metadata)
        else:
            log_error(f"set_item_info() item with wrong path: {path} should be: {self.path}")

    def update_remote_info(self, path, metadata):

        if path == self.path:
            super().update_remote_info(metadata)
        else:
            log_error(f"update_remote_info() item with wrong path: {path} should be: {self.path}")

    def set_client(self, client):
        self._client = client
