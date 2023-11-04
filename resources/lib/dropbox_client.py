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
import re
import queue
import base64
import shutil
import datetime
import threading
import traceback

import xbmc
import xbmcgui
import xbmcvfs

import dropbox.files
import dropbox.dropbox
import dropbox.exceptions

from .utils import *
from .dropbox_cache import DropboxCache


def command(silent=False, max_retries=3):
    """
    A decorator for handling authentication and exceptions
    """

    def decorate(f):

        def wrapper(self, *args, **keywords):
            retries = max_retries

            while retries > 0:

                try:
                    return f(self, *args, **keywords)
                except dropbox.exceptions.RateLimitError as e:

                    if e.backoff:
                        xbmc.sleep(e.backoff * 1000)
                    else:
                        xbmc.sleep(1000)

                except Exception as e:
                    error = traceback.format_exc()
                    log_error(f"{f.__name__} failed: {error}")

                    if not silent:
                        xbmcgui.Dialog().ok(ADDON_NAME, f"{LANGUAGE_STRING(30206)} {error}")

                    return

                retries -= 1

        wrapper.__doc__ = f.__doc__
        return wrapper

    return decorate


class KodiDropboxClient:
    """
    Provides a more 'general' interface to dropbox.
    Handles all dropbox API specifics
    """

    dropbox_api = None

    def __init__(self, access_token=None, refresh_token=None, app_key=None, app_secret=None, account_name=None, cache=None, auto_connect=True):
        self._access_token = access_token
        self._refresh_token = refresh_token
        self._app_key = app_key
        self._app_secret = app_secret

        if cache:
            self._cache = cache
        elif account_name:
            self._cache = DropboxCache(account_name)

        if auto_connect:
            connected, msg = self.connect()

            if not connected:
                xbmcgui.Dialog().ok(ADDON_NAME, f"{LANGUAGE_STRING(30205)} {msg}")

    def connect(self):
        msg = "No error"

        if not self._access_token:
            msg = "No token (access code)"

        if not self.dropbox_api and self._access_token:

            try:
                self.dropbox_api = dropbox.dropbox.Dropbox(
                    self._access_token,
                    oauth2_refresh_token=self._refresh_token,
                    app_key=self._app_key,
                    app_secret=self._app_secret,
                )
            except dropbox.exceptions.DropboxException as e:
                msg = str(e)
                self.dropbox_api = None

        return self.dropbox_api != None, msg

    def disconnect(self):
        self.dropbox_api = None

    @command()
    def get_metadata(self, path, directory=False):
        """
        The metadata of the directory is cached.
        The metadata of a file is retrieved from the directory metadata.
        For caching the metadata, the StorageServer
        (script.common.plugin.cache addon) is used.
        """

        path = path.lower()
        dir_name = path

        if not directory:
            dir_name = os.path.dirname(path)

        # Make the cache_name unique to the account (using the access_token).
        # To prevents that different accounts, which have the same directories, don't
        # use the same cache
        cached_data = self._cache.get()
        cached_metadata = cached_data["metadata"].get(path, {})

        if cached_metadata:
            cursor = cached_metadata["cursor"]
        else:
            cursor = None

        if directory or not cached_metadata:

            if cursor:

                try:
                    result = self.dropbox_api.files_list_folder_continue(cursor)
                except dropbox.exceptions.ApiError as e:
                    result = self.dropbox_api.files_list_folder("" if dir_name == "/" else dir_name)

                else:

                    if not result.entries and cached_metadata:
                        return cached_metadata["entries"]

            else:
                # Dropbox expects root path to be an empty string otherwise it will fail
                result = self.dropbox_api.files_list_folder("" if dir_name == "/" else dir_name)

            entries = result.entries
            metadata = self._cache.sort_metadata(entries, cached_metadata.get("entries"))
            cached_data["metadata"][dir_name] = {
                "cursor": result.cursor,
                "entries": metadata,
            }
            self._cache.save(cached_data)

        else:
            metadata = cached_metadata

        if not directory:

            for file_type, entries in metadata["files"].items():

                if path in entries:
                    return entries[path]

        return metadata

    @command()
    def get_media_url(self, path):
        """
        Cache this URL because it takes a lot of time requesting it
        If the media URL is still valid, within the margin, then don't
        request a new one yet.
        """

        link = None
        margin = 13800 # Seconds - link valid for 4 hours
        cached_data = self._cache.get()
        cached_links = cached_data["links"]
        cached_link = cached_links.get(path)

        if cached_link:

            if datetime.datetime.now() < cached_link["expires"]:
                link = cached_link["link"]
                log_debug("Media URL is using cached URL.")
            else:
                log_debug(f"Media URL expired. End time was: {cached_link['expires']}")

        if not link and self.dropbox_api:
            result = self.dropbox_api.files_get_temporary_link(path)
            link = result.link
            expiry = datetime.datetime.now() + datetime.timedelta(seconds=margin)
            cached_links[path] = {"link": link, "expires": expiry}
            log_debug("Media URL storing URL.")
            self._cache.save(cached_data)

        return link

    @command()
    def search(self, query, path):
        options = dropbox.files.SearchOptions(path=path)
        has_more = True
        cursor = False
        entries = []

        while has_more:

            if cursor:
                result = files_search_continue_v2(cursor)
            else:
                result = self.dropbox_api.files_search_v2(query, options=options)

            cursor = result.cursor
            has_more = result.has_more
            entries += [m.metadata.get_metadata() for m in result.matches if m.metadata.is_metadata()]

        return self._cache.sort_metadata(entries)

    @command()
    def delete(self, path):
        return self.dropbox_api.files_delete_v2(path)

    @command()
    def copy(self, from_path, to_path):
        return self.dropbox_api.files_copy_v2(from_path, to_path)

    @command()
    def move(self, from_path, to_path, autorename=False):
        return self.dropbox_api.files_move_v2(from_path, to_path, autorename=autorename)

    @command()
    def create_folder(self, path):
        return self.dropbox_api.files_create_folder_v2(path)

    @command()
    def upload(self, filename, path, dialog=False):
        size = os.stat(filename).st_size

        if size <= 0:
            log_error("File size of upload file <= 0")
            return

        file = open(filename, "rb")
        uploader = Uploader(self.dropbox_api, file, size)
        uploader.start()
        dialog = xbmcgui.DialogProgress()
        dialog.create(LANGUAGE_STRING(30033), filename)
        dialog.update(int((uploader.cursor.offset * 100) / uploader.target_length))

        while uploader.cursor.offset < uploader.target_length:

            if dialog.iscanceled():
                log("User canceled the upload")
                break

            uploader.upload_next()
            dialog.update(int((uploader.cursor.offset * 100) / uploader.target_length))

        dialog.close()

        if uploader.cursor.offset == uploader.target_length:
            path = re.sub(r"/+", "/", path + DROPBOX_SEP + os.path.basename(filename))

            if path == "/":
                path = ""
            else:
                path = "/" + path.strip("/")

            uploaded = uploader.finish(path)
            file.close()
            return uploaded

    @staticmethod
    def create_thumbnail_obj(path):
        format = dropbox.files.ThumbnailFormat("jpeg", None)
        size = dropbox.files.ThumbnailSize("w640h480", None)
        return dropbox.files.ThumbnailArg(path, format, size)

    @command(silent=True)
    def save_thumbnails(self, entries, locations):
        entries = self.dropbox_api.files_get_thumbnail_batch(entries).entries

        for result in entries:

            if result.is_success():
                data = result.get_success()
                metadata = data.metadata
                thumbnail = base64.decodebytes(data.thumbnail.encode())
                location = locations[metadata.path_lower]
                dir_name = os.path.dirname(location) + os.sep # Add os seperator because it is a dir

                if not xbmcvfs.exists(dir_name):
                    xbmcvfs.mkdirs(dir_name)

                with open(location, "wb") as cache_file: # 'b' option required for windows
                    cache_file.write(thumbnail)

                log_debug(f"Downloaded file to: {location}")

    @command(silent=True)
    def save_file(self, path, location):
        dir_name = os.path.dirname(location) + os.sep # Add os seperator because it is a dir

        if not xbmcvfs.exists(dir_name):
            xbmcvfs.mkdirs(dir_name)

        metadata, resp = self.dropbox_api.files_download(path)

        with open(location, "wb") as cache_file: # 'b' option required for windows
            shutil.copyfileobj(resp.raw, cache_file)

        log_debug(f"Downloaded file to: {location}")
        return True

    @command(silent=True)
    def get_remote_changes(self, cursor=None):

        if cursor:

            try:
                result = self.dropbox_api.files_list_folder_continue(cursor)
            except dropbox.exceptions.ApiError as e:
                result = self.dropbox_api.files_list_folder("", recursive=True)

        else:
            result = self.dropbox_api.files_list_folder("", recursive=True)

        return result.entries, result.cursor, result.has_more

    @command(silent=True)
    def get_account_info(self):
        return self.dropbox_api.users_get_current_account()


class ChunkedUploader:
    """Contains the logic around a chunked upload, which uploads a
    large file to Dropbox via the /chunked_upload endpoint.
    """

    def __init__(self, client, file_obj, length):
        self.client = client
        self.file_obj = file_obj
        self.target_length = length
        self.cursor = None

    def start(self):
        result = self.client.files_upload_session_start(self.file_obj.read(self.chunk_size))
        self.cursor = dropbox.files.UploadSessionCursor(result.session_id, self.file_obj.tell())

    def finish(self, path):
        commit = dropbox.files.CommitInfo(path=path)
        next_chunk_size = min(self.chunk_size, self.target_length - self.cursor.offset)
        return self.client.files_upload_session_finish(self.file_obj.read(next_chunk_size), self.cursor, commit)


class Uploader(ChunkedUploader):
    """
    Use the ChunkedUploader, but create a
    step() function to
    """

    def __init__(self, client, file_obj, length):
        super().__init__(client, file_obj, length)
        self.chunk_size = 1 * 1024 * 1024 # 1 MB sizes

    def upload_next(self):
        next_chunk_size = min(self.chunk_size, self.target_length - self.cursor.offset)
        self.client.files_upload_session_append_v2(self.file_obj.read(next_chunk_size), self.cursor)
        self.cursor.offset = self.file_obj.tell()


class Downloader(threading.Thread):
    _items_handled = 0
    _items_total = 0

    def __init__(self, client, path, location, is_dir):
        super().__init__()
        self._client = client
        self.path = path
        self.location = location
        self.is_dir = is_dir
        self.remote_base_path = os.path.dirname(path)
        self._file_list = queue.Queue() # Thread safe
        self.monitor = xbmc.Monitor()
        self._progress = xbmcgui.DialogProgress()
        self._progress.create(LANGUAGE_STRING(30039))
        self._progress.update(0)
        self.canceled = False
        self.error = False

    def run(self):
        log_debug(f"Downloader started for: {self.path}")

        # First get all the file-items in the path
        if not self.is_dir:
            # Download a single file
            entries = self._client.get_metadata(self.path)

            if not entries:
                raise Exception(f"{ADDON_ID} No metadata retrieved")

            self._file_list.put(entries)
        else:
            # Download a directory
            self.get_file_items(self.path)

        self._items_total = self._file_list.qsize()

        # Check if need to quit
        while not self._progress.iscanceled() and not self._file_list.empty() and not self.monitor.abortRequested():
            # Download the list of files/dirs
            item_to_retrieve = self._file_list.get()

            if item_to_retrieve:
                self._progress.update(int((self._items_handled * 100) / self._items_total), f"{LANGUAGE_STRING(30041)} {item_to_retrieve.path_display}")
                base_path = item_to_retrieve.path_display
                base_path = re.sub(self.remote_base_path, "", base_path, count=1, flags=re.IGNORECASE) # Remove the remote base path
                location = os.path.normpath(self.location + base_path)

                if isinstance(item_to_retrieve, dropbox.files.FolderMetadata):
                    location += os.sep # Add os seperator because it is a dir

                    if not xbmcvfs.exists(location):
                        xbmcvfs.mkdirs(location)

                else:

                    if not self._client.save_file(item_to_retrieve.path_display, location):
                        log_error(f"Downloader failed for: {item_to_retrieve.path_display}")
                        self._progress.close()
                        self.error = True

                        if xbmcvfs.exists(location):
                            os.remove(location)

                        return

                self._items_handled += 1

            xbmc.sleep(100)

        if self._progress.iscanceled():
            log_debug(f"Downloader stopped (as requested) for: {self.path}")
            self.canceled = True
        else:
            self._progress.update(100)
            log_debug(f"Downloader finished for: {self.path}")

        self._progress.close()
        del self._progress

    def get_file_items(self, path):
        entries = self._client.get_metadata(path, directory=True)

        if not entries:
            return

        files = entries["files"]
        folders = entries["folders"]

        for file_type, entries in files.items():

            for path, metadata in entries.items():
                self._file_list.put(metadata)

        for path in folders:
            self.get_file_items(path)
