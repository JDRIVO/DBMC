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
from stat import *
from datetime import timezone
from dataclasses import dataclass

from ..utils import *


class SyncObject:
    OBJECT_IN_SYNC = 0
    OBJECT_TO_DOWNLOAD = 1
    OBJECT_TO_UPLOAD = 2
    OBJECT_TO_REMOVE = 3
    OBJECT_ADD_CHILD = 4
    OBJECT_REMOVED = 5
    OBJECT_SKIP = 6

    def __init__(self, path, client):
        self.path = path
        self._client = client
        self._name = None
        self._local_path = None
        self.is_dir = False
        self._failure = False
        self._remote_present = True
        self._local_timestamp = 0
        self._remote_timestamp = 0
        self._new_remote_timestamp = 0
        self._remote_client_modified_timestamp = 0
        self._state = self.OBJECT_IN_SYNC

    def set_item_info(self, metadata):
        log_debug(f"Set stored metadata: {self.path}")
        self._name = metadata.name
        self._remote_present = metadata.present
        self._remote_timestamp = metadata.server_modified
        self._new_remote_timestamp = self._remote_timestamp
        self._remote_client_modified_timestamp = metadata.client_modified

        if self.path != metadata.path:
            log_error(f"Stored metadata path ({metadata.path_display}) not equal to path {self.path}")

    def get_item_info(self):
        return Metadata(
            self.path,
            self._name,
            self.is_dir,
            self._remote_present,
            self._remote_timestamp,
            self._remote_client_modified_timestamp,
        )

    def update_remote_info(self, metadata):
        log_debug(f"Update remote metadata: {self.path}")

        if metadata.__class__.__name__ == "DeletedMetadata":
            self._remote_present = False
            log_debug(f"Item removed on remote: {self.path}")
            return
        elif metadata.__class__.__name__ == "FileMetadata":
            # Folder metadata doesn't contain timestamps
            # Convert to local time
            self._new_remote_timestamp = time.mktime(metadata.server_modified.replace(tzinfo=timezone.utc).astimezone(tz=None).timetuple())
            self._remote_client_modified_timestamp = time.mktime(metadata.client_modified.replace(tzinfo=timezone.utc).astimezone(tz=None).timetuple())

        self._remote_present = True
        self._name = metadata.name

    def update_timestamp(self):
        # local modified time = client_mtime
        st = os.stat(self._local_path)
        atime = st[ST_ATIME] # Access time
        mtime = st[ST_MTIME] # Modification time
        # Modify the file timestamp
        os.utime(self._local_path, (atime, int(self._remote_client_modified_timestamp)))
        # Read back and store the local timestamp value
        # this is used for comparison to the remote modified time
        st = os.stat(self._local_path)
        self._local_timestamp = st[ST_MTIME]
        self._remote_timestamp = self._new_remote_timestamp

    def update_local_path(self, parent_sync_path):

        if self._name:
            self._local_path = os.path.normpath(parent_sync_path + self._name)


@dataclass
class Metadata:
    path: str
    name: str
    is_dir: bool
    present: bool
    server_modified: float
    client_modified: float
