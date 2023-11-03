import os
import queue
import shutil
import datetime
import threading

try:
    import StorageServer
except:
    from . import storage_server_dummy as StorageServer

from dropbox.files import (
    DeletedMetadata,
    FileMetadata,
    FileSharingInfo,
    FolderMetadata,
    FolderSharingInfo,
    ListFolderResult,
)

from .utils import *
from .constants import *


class DropboxCache(StorageServer.StorageServer):

    def __init__(self, account_name):
        super().__init__(ADDON_NAME)
        self._cache_name = account_name
        cache_path = get_cache_path(account_name)
        self._shadow_path = f"{cache_path}/shadow/"
        self._thumb_path = f"{cache_path}/thumb/"
        self._data = None
        self._stop_event = threading.Event()

    def stop(self):
        self._stop_event.set()

    def stopped(self):
        return self._stop_event.is_set()

    def delete(self):
        super().delete(self._cache_name)

    def save(self, data=None):

        if data is None:
            data = self._data
        else:
            self._data = data

        super().set(self._cache_name, repr(data))

    def get(self):
        self._data = super().get(self._cache_name)

        if self._data:
            self._data = eval(self._data)
        else:
            self._data = {
                "links": {},
                "metadata": {},
            }

        return self._data

    @staticmethod
    def identify_file_type(metadata):
        filename = metadata.name
        file_extension = os.path.splitext(filename)[1][1:].lower()

        if file_extension in VIDEO_EXT:
            return "video"
        elif file_extension in AUDIO_EXT:
            return "audio"
        elif file_extension in IMAGE_EXT:
            return "image"
        else:
            return "other"

    def sort_metadata(self, entries, cached_metadata=None):

        if not cached_metadata:
            data = {
                "folders": {},
                "files": {
                    "video": {},
                    "audio": {},
                    "image": {},
                    "other": {},
                },
                "deleted": {
                    "folders": {},
                    "files": {},
                },
            }
        else:
            data = cached_metadata

        for metadata in entries:
            path = metadata.path_lower

            if isinstance(metadata, FolderMetadata):
                data["folders"][path] = metadata

                if path in data["deleted"]["folders"]:
                    del data["deleted"]["folders"][path]

            elif isinstance(metadata, FileMetadata):
                file_type = self.identify_file_type(metadata)
                data["files"][file_type][path] = metadata

                if path in data["deleted"]["files"]:
                    del data["deleted"]["files"][path]

            elif isinstance(metadata, DeletedMetadata) and cached_metadata:

                if path in data["folders"]:
                    data["deleted"]["folders"][path] = metadata
                    del data["folders"][path]
                else:

                    for file_type, metadata_ in data["files"].items():

                        if path in metadata_:
                            data["deleted"]["files"][path] = metadata
                            del metadata_[path]
                            break

        return data

    def process_deletions(self, path):

        if not self._data:
            return

        deleted_metadata = self._data["metadata"][path]["entries"]["deleted"]

        if not deleted_metadata:
            return

        for deletion_type in ("files", "folders"):

            for path in list(deleted_metadata[deletion_type]):

                if self.stopped():
                    return

                self.delete_cached_path(path, file=deletion_type == "files")
                del deleted_metadata[deletion_type][path]
                self.save()

    def delete_cached_path(self, path, file=True):
        thumb_path = os.path.normpath(self._thumb_path + path)
        shadow_path = os.path.normpath(self._shadow_path + path)

        if file:
            thumb_path = replace_file_extension(thumb_path, "jpg")
        else:
            thumb_path += os.sep
            shadow_path += os.sep

        for path in (shadow_path, thumb_path):

            if xbmcvfs.exists(path):

                if file:
                    log_debug(f"Removing cached file: {path}")
                    os.remove(path)
                else:
                    log_debug(f"Removing cached folder: {path}")
                    shutil.rmtree(path)


class FileLoader(threading.Thread):

    def __init__(self, client, module, account_name):
        super().__init__()
        self._client = client
        self._module = module
        cache_path = get_cache_path(account_name)
        self._shadow_path = f"{cache_path}/shadow/"
        self._thumb_path = f"{cache_path}/thumb/"
        self._thumb_list = queue.Queue() # Thread safe
        self._file_list = queue.Queue() # Thread safe
        self._stop_event = threading.Event()
        self._thumb_batch_total = 25
        self._file_batch_total = ADDON_SETTINGS.getInt("files_per_batch")

    def stop(self):
        self._stop_event.set()

    def stopped(self):
        return self._stop_event.is_set()

    def run(self):
        log_debug(f"FileLoader started for: {self._module}")
        tasks = []
        t = threading.Thread(target=self._thumb_batch_download)
        t.start()
        tasks.append(t)
        t = threading.Thread(target=self._file_batch_download)
        t.start()
        tasks.append(t)

        for task in tasks:
            task.join()

        if self.stopped():
            log_debug(f"FileLoader stopped (as requested) for: {self._module}")
        else:
            log_debug(f"FileLoader finished for: {self._module}")

    def _file_batch_download(self):

        while not self.stopped():
            tasks = []

            for _ in range(self._file_batch_total):

                try:
                    path = self._file_list.get(timeout=0.1)
                    location = self._get_shadow_location(path)

                    if not xbmcvfs.exists(location):
                        t = threading.Thread(target=self._client.save_file, args=(path, location))
                        t.start()
                        tasks.append(t)

                except queue.Empty:
                    break

            for task in tasks:
                task.join()

            xbmc.sleep(100)

    def _thumb_batch_download(self):

        while not self.stopped():
            batch = []
            locations = {}

            for _ in range(self._thumb_batch_total):

                try:
                    path = self._thumb_list.get(timeout=0.1)
                    location = self._get_thumb_Location(path)

                    if not xbmcvfs.exists(location):
                        batch.append(self._client.create_thumbnail_obj(path))
                        locations[path] = location

                except queue.Empty:
                    break

            if batch:
                self._client.save_thumbnails(batch, locations)

            xbmc.sleep(100)

    def _get_thumb_Location(self, path):
        location = replace_file_extension(path, "jpg")
        return os.path.normpath(self._thumb_path + location)

    def _get_shadow_location(self, path):
        return os.path.normpath(self._shadow_path + path)

    def get_thumbnail(self, path):
        self._thumb_list.put(path)
        return self._get_thumb_Location(path)

    def get_file(self, path):
        self._file_list.put(path)
        return self._get_shadow_location(path)
