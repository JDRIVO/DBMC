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

import uuid
import threading

import xbmc
import xbmcgui
import xbmcplugin

from .utils import *
from .constants import *
from .dropbox_cache import *
from .dropbox_client import KodiDropboxClient


HANDLE = int(sys.argv[1])


class DropboxViewer:
    """
    Handles the Kodi GUI/View behaviour and takes care of caching the files
    """

    _use_steaming_urls = False
    _filter_files = False
    _loader = None
    _session = ""

    def __init__(self, params, account_settings):
        self._account_settings = account_settings
        self._account_name = self._account_settings.account_name
        self._cache = DropboxCache(self._account_name)
        self._client = KodiDropboxClient(
            self._account_settings.access_token,
            self._account_settings.refresh_token,
            self._account_settings.app_key,
            self._account_settings.app_secret,
            self._account_name,
            self._cache,
        )
        self._filter_files = ADDON.getSettingBool("file_filter")
        self._use_steaming_urls = ADDON.getSettingBool("stream_media")
        self._enabled_sync = self._account_settings.synchronisation
        self._local_sync_path = self._account_settings.sync_path
        self._remote_sync_path = self._account_settings.remote_path
        self._current_path = params.get("path", DROPBOX_SEP)
        self._module = params.get("module", "")
        self._content_type = params.get("content_type", "executable")
        # Set/change 'session_id' to let the other FolderBrowser know that it has to quit
        self._session = str(uuid.uuid4())
        self.win = xbmcgui.Window(xbmcgui.getCurrentWindowId())
        self.win.setProperty("session_id", self._session)
        self.monitor = xbmc.Monitor()
        self.add_sort_methods()

    def must_stop(self):
        """
        When Kodi quits or the plugin(visible menu) is changed, stop this thread
        """

        # win = xbmcgui.Window(xbmcgui.getCurrentWindowId())
        session = self.win.getProperty("session_id")

        if session != self._session:
            log_debug("session_id changed")
            return True
        elif self.monitor.abortRequested():
            log_debug("xbmc.abortRequested")
            return True

    def add_sort_methods(self):
        sort_methods = (
            xbmcplugin.SORT_METHOD_UNSORTED,
            xbmcplugin.SORT_METHOD_LABEL,
            xbmcplugin.SORT_METHOD_DATE,
            xbmcplugin.SORT_METHOD_SIZE,
        )
        [xbmcplugin.addSortMethod(HANDLE, sort_method) for sort_method in sort_methods]

    def get_metadata(self, path, directory=False):
        entries = self._client.get_metadata(path, directory)

        if not entries:
            raise Exception(f"{ADDON_ID} No metadata retrieved")

        return entries

    def show(self, cache_to_disc=True, succeeded=True):
        xbmcplugin.endOfDirectory(HANDLE, succeeded=succeeded, cacheToDisc=cache_to_disc)

        if self._loader:
            delete_thread = threading.Thread(target=self._cache.process_deletions, args=(self._current_path,))
            delete_thread.start()
            self._loader.start()
            # Now wait for the FileLoader
            # We cannot run the FileLoader standalone without this plugin.
            # For that we would need to use the xbmc.abortRequested, which becomes
            # true as soon as we exit this plugin

            while self._loader.is_alive() or delete_thread.is_alive():

                if self.must_stop():
                    # Force the thread to stop
                    self._loader.stop()
                    self._cache.stop()
                    # Wait for the thread
                    delete_thread.join(1)
                    self._loader.join(4) # After 5 seconds it will be killed any way by Kodi
                    break

                xbmc.sleep(100)

    def build_list(self, items):
        # Create and start the thread that will download the files
        self._loader = FileLoader(self._client, self._module, self._account_name)
        self.process_folders(items["folders"])

        if not self._filter_files or self._content_type == "executable":
            [self.process_files(file_type, entries) for file_type, entries in items["files"].items()]
        else:
            self.process_files(self._content_type, items["files"][self._content_type])

    def process_folders(self, folders):
        [self.add_folder(metadata.name, path) for path, metadata in folders.items()]

    def process_files(self, content_type, entries):
        [self.add_file(path, metadata, content_type) for path, metadata in entries.items()]

    def add_folder(self, name, path):
        list_item = xbmcgui.ListItem(name)
        list_item.setArt({"icon": "DefaultFolder.png", "thumb": "DefaultFolder.png"})
        url = self.get_url(path, module="browse_folder")
        context_menu_items = []
        search_url = self.get_url(path, module="search_dropbox")
        context_menu_items.append((LANGUAGE_STRING(30017), f"RunPlugin({search_url})"))
        context_menu_items.append((LANGUAGE_STRING(30022), self.get_context_url(path, "delete")))
        context_menu_items.append((LANGUAGE_STRING(30002), self.get_context_url(path, "rename")))
        context_menu_items.append((LANGUAGE_STRING(30027), self.get_context_url(path, "move")))
        context_menu_items.append((LANGUAGE_STRING(30024), self.get_context_url(path, "copy")))
        context_menu_items.append((LANGUAGE_STRING(30029), self.get_context_url(path, "create_folder")))
        context_menu_items.append((LANGUAGE_STRING(30031), self.get_context_url(path, "upload")))
        context_menu_items.append((LANGUAGE_STRING(30037), self.get_context_url(path, "download", extra="is_dir=True")))

        if self._enabled_sync and self._remote_sync_path in path:
            context_menu_items.append((LANGUAGE_STRING(30112), self.get_context_url(path, "sync_now")))

        list_item.addContextMenuItems(context_menu_items)
        # No useful metadata of folder
        xbmcplugin.addDirectoryItem(HANDLE, url, list_item, isFolder=True)

    def add_file(self, path, metadata, media_type):
        filename = metadata.name
        list_item = xbmcgui.ListItem(filename)
        list_item.setArt({"icon": ICONS[media_type]})
        list_item.setDateTime(metadata.server_modified.strftime("%Y-%m-%d %H:%M:%S"))
        list_item.setInfo(TYPES[media_type], {"size": metadata.size})

        if media_type in ("image", "video", "audio"):
            list_item.setArt({"thumb": self._loader.get_thumbnail(path)})

            if self._use_steaming_urls and media_type in ("video", "audio"):
                # This doesn't work for pictures
                list_item.setProperty("IsPlayable", "true")
                url = f"{ADDON_URL}?action=play&path={path}&filename={filename}&account={self._account_name}"
            else:
                url = self._loader.get_file(path)
                # url = self.get_media_url(path)

        else:
            list_item.setProperty("IsPlayable", "false")
            url = "No action"

        context_menu_items = []
        search_url = self.get_url(self._current_path, module="search_dropbox")
        context_menu_items.append((LANGUAGE_STRING(30017), f"RunPlugin({search_url})"))
        context_menu_items.append((LANGUAGE_STRING(30022), self.get_context_url(path, "delete")))
        context_menu_items.append((LANGUAGE_STRING(30002), self.get_context_url(path, "rename")))
        context_menu_items.append((LANGUAGE_STRING(30027), self.get_context_url(path, "move")))
        context_menu_items.append((LANGUAGE_STRING(30024), self.get_context_url(path, "copy")))
        context_menu_items.append((LANGUAGE_STRING(30029), self.get_context_url(self._current_path, "create_folder")))
        context_menu_items.append((LANGUAGE_STRING(30031), self.get_context_url(self._current_path, "upload")))
        context_menu_items.append((LANGUAGE_STRING(30037), self.get_context_url(path, "download", extra="is_dir=False")))

        if self._enabled_sync and self._remote_sync_path in path:
            context_menu_items.append((LANGUAGE_STRING(30112), self.get_context_url(self._current_path, "sync_now")))

        list_item.addContextMenuItems(context_menu_items)
        xbmcplugin.addDirectoryItem(HANDLE, url, list_item, isFolder=False)

    def get_url(self, path, module=None):
        url = f"{ADDON_URL}?content_type={self._content_type}&account={self._account_name}&path={path}"

        if module:
            url += f"&module={module}"
        else:
            url += f"&module={self._module}"

        return url

    def get_context_url(self, path, action, extra=None):
        url = f"RunPlugin({ADDON_URL}?action={action}&account={self._account_name}"

        if action == "upload":
            url += f"&to_path={path}"
        else:
            url += f"&path={path}"

        if extra:
            url += f"&{extra}"

        return url + ")"
