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
import shutil
import traceback

import xbmcvfs

from ..utils import *
from .sync_file import SyncFile
from .sync_object import SyncObject


class SyncFolder(SyncObject):

    def __init__(self, path, client):
        log_debug(f"Create SyncFolder: {path}")
        super().__init__(path, client)
        self.is_dir = True
        self._children = {}

    def set_item_info(self, path, metadata):

        if path == self.path:
            super().set_item_info(metadata)
        elif path.find(self.path) != 0:
            log_error(f"set_item_info() Item({path}) isn't part of the remote sync path ({self.path})")
        else:
            child = self.get_item(path, metadata)
            child.set_item_info(path, metadata)

    def update_remote_info(self, path, metadata):

        if path == self.path:
            super().update_remote_info(metadata)
        elif path.find(self.path) != 0:
            log_error(f"update_remote_info() Item({path}) isn't part of the remote sync path ({self.path})")
        else:
            child = self.get_item(path, metadata)
            child.update_remote_info(path, metadata)

    def get_items_info(self):
        metadata_list = {}
        metadata_list[self.path] = self.get_item_info()

        for path, child in self._children.items():

            if child.is_dir:
                child_metadata = child.get_items_info()
                metadata_list.update(child_metadata)
            else:
                metadata_list[path] = child.get_item_info()

        return metadata_list

    def get_item(self, path, metadata):
        # Strip the child name, exclude its own path from the search for the first seperator
        end = path.find(DROPBOX_SEP, len(self.path) + 1)

        if end > 0:
            child_path = path[:end]
        else:
            child_path = path

        if not child_path in self._children:

            # Create the child
            if metadata.is_dir:
                child = SyncFolder(child_path, self._client)
            else:
                child = SyncFile(child_path, self._client)

            # Add the new created child to the childern's list
            self._children[child_path] = child

        return self._children[child_path]

    def in_sync(self):

        if self._state == self.OBJECT_SKIP:
            log_debug(f"Skipping folder: {self._local_path}")
            return self.OBJECT_IN_SYNC # Fake object in sync

        local_present = False

        if self._local_path:
            local_present = xbmcvfs.exists(self._local_path)
        elif self._remote_present:
            log_error(f"Has no local_path: {self.path}")

        # File present
        if not local_present and self._remote_present:
            return self.OBJECT_TO_DOWNLOAD

        if not self._remote_present:

            if local_present:
                # TODO: Check if local file is a newer one than the old remote file
                # if so, use the new local file
                return self.OBJECT_TO_REMOVE
            else:
                # File is completely removed, so can be removed from memory as well
                return self.OBJECT_REMOVED

        # TODO Check if files are present on disk but not in it's
        #  _childern's list
        # return self.OBJECT_ADD_CHILD
        return self.OBJECT_IN_SYNC

    def sync(self):

        if self._state == self.OBJECT_SKIP:
            return

        try:
            self._state = self.in_sync()

            if self._state == self.OBJECT_TO_DOWNLOAD:
                log_debug(f"Create folder: {self._local_path}")
                xbmcvfs.mkdirs(self._local_path)
            elif self._state == self.OBJECT_TO_UPLOAD:
                log_error(f"Can't upload folder: {self._local_path}")
                # TODO Add files if new files found local
                # TODO: Modify timestamp of dir
            elif self._state == self.OBJECT_TO_REMOVE:
                log_debug(f"Remove folder: {self._local_path}")
                shutil.rmtree(self._local_path)
            elif self._state == self.OBJECT_ADD_CHILD:
                # TODO
                pass
            elif self._state == self.OBJECT_IN_SYNC:
                pass
            else:
                log_error(f"Unknown folder status ({self._state}) for: {self.path}")

        except Exception as e:
            log_error(f"Exception occurred for folder {self._local_path}")
            log_error(traceback.format_exc())

            if self._failure:
                # Failure happened before so skip this item in all the next syncs
                self._state = self.OBJECT_SKIP
                log_error(f"Skipping folder in the next syncs: {self._local_path}")

            self._failure = True

    def get_items_to_sync(self):
        dirs_to_sync = []
        items_to_sync = []
        remove_list = {}

        for path, child in self._children.items():

            if child.is_dir:
                new_dirs, new_items = child.get_items_to_sync()
                dirs_to_sync += new_dirs
                items_to_sync += new_items

            child_sync_status = child.in_sync()

            if child_sync_status == child.OBJECT_REMOVED:
                # Remove child from list
                remove_list[path] = child
            elif child_sync_status != child.OBJECT_IN_SYNC:

                if child.is_dir:
                    dirs_to_sync.append(child)
                else:
                    items_to_sync.append(child)

        # Remove child's from list (this we can do now)
        if len(remove_list) > 0:
            # Sync this dir (dummy sync to remove the deleted child from storage)
            dirs_to_sync.append(self)

        for path in remove_list:
            child = self._children.pop(path)
            del child

        return dirs_to_sync, items_to_sync

    def set_client(self, client):
        self._client = client

        for child in self._children.values():
            child.set_client(client)

    def update_local_path(self, parent_sync_path):
        super().update_local_path(parent_sync_path)
        # _local_path can be None when the _name also is None
        # This can happen when the folder was deleted on dropbox
        # before it was ever on this system and dropbox doesn't update the metadata
        if self._local_path:
            # For folders add the os seperator (xbmcvfs.exists() needs it)
            self._local_path += os.sep

            for path, child in self._children.items():
                child.update_local_path(self._local_path)

    def update_local_root_path(self, sync_path):
        # Don't add the self._name to the sync_path for root
        self._local_path = os.path.normpath(sync_path)
        self._local_path += os.sep

        for path, child in self._children.items():
            child.update_local_path(self._local_path)
