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

import xbmcgui
import xbmcplugin

import resources.lib.login as login
from resources.lib.utils import *
from resources.lib.sync.notify_sync import NotifySyncClient
from resources.lib.dropbox_file_browser import DropboxFileBrowser
from resources.lib.dropbox_client import KodiDropboxClient, Downloader


HANDLE = int(sys.argv[1])
PARAMS = sys.argv[2]


def run():
    log_debug(f"Argument List: {sys.argv}")
    params = parse_argv()

    if HANDLE < 0:

        # Handle action of a file
        if "module" in params:
            # Plugin (module) to run
            path = ADDON_URL + PARAMS
            xbmc.executebuiltin(f"Container.Update({path})")
            return

        account_name = params.get("account", "")
        account_settings = login.get_account(account_name)

        if not account_settings:
            xbmcgui.Dialog().ok(ADDON_NAME, LANGUAGE_STRING(30203))
            return

        # All actions below require a KodiDropboxClient
        client = KodiDropboxClient(
            account_settings.access_token,
            account_settings.refresh_token,
            account_settings.app_key,
            account_settings.app_secret,
            account_settings.account_name,
        )
        action = params.get("action", "")

        if action == "delete":

            if "path" in params:
                path = params["path"]

                if xbmcgui.Dialog().yesno(ADDON_NAME, f"{LANGUAGE_STRING(30023)} {path}"):
                    deleted = client.delete(path)

                    if deleted:
                        log(f"File deleted: {path}")
                        xbmc.executebuiltin("Container.Refresh")
                        NotifySyncClient().sync_path(account_settings, path)
                    else:
                        log_error(f"File delete failed: {path}")

        elif action == "rename":

            if "path" in params:
                path = params["path"]
                keyboard = xbmc.Keyboard("", LANGUAGE_STRING(30003))
                keyboard.doModal()

                if keyboard.isConfirmed():
                    input = keyboard.getText()

                    if not input:
                        return

                    # Dropbox path -> don't use os.path.join()
                    to_path = os.path.dirname(path)

                    if to_path[-1:] != DROPBOX_SEP:
                        to_path += DROPBOX_SEP

                    file_extension = os.path.splitext(os.path.basename(path))[1]
                    to_path += keyboard.getText() + file_extension
                    renamed = client.move(path, to_path, autorename=True)

                    if renamed:
                        log(f"File renamed: from {path} to {renamed.metadata.path_display}")
                        xbmc.executebuiltin("Container.Refresh")
                        NotifySyncClient().sync_path(account_settings, path)
                    else:
                        log_error(f"File rename failed: from {path} to {to_path}")

        elif action == "move":

            if "path" in params:
                path = params["path"]
                dialog = DropboxFileBrowser("FileBrowser.xml", ADDON_PATH)
                dialog.set_db_client(client)
                dialog.set_heading(LANGUAGE_STRING(30025) + LANGUAGE_STRING(30028))
                dialog.doModal()

                if dialog.selected_folder:
                    # Dropbox path -> don't use os.path.join()
                    to_path = dialog.selected_folder

                    if dialog.selected_folder[-1:] != DROPBOX_SEP:
                        to_path += DROPBOX_SEP

                    to_path += os.path.basename(path)
                    moved = client.move(path, to_path)

                    if moved:
                        log(f"File moved: from {path} to {to_path}")
                        xbmc.executebuiltin("Container.Refresh")
                        NotifySyncClient().sync_path(account_settings, path)
                        NotifySyncClient().sync_path(account_settings, to_path)
                    else:
                        log_error(f"File move failed: from {path} to {to_path}")

                del dialog

        elif action == "copy":

            if "path" in params:
                path = params["path"]
                dialog = DropboxFileBrowser("FileBrowser.xml", ADDON_PATH)
                dialog.set_db_client(client)
                dialog.set_heading(LANGUAGE_STRING(30025) + LANGUAGE_STRING(30026))
                dialog.doModal()

                if dialog.selected_folder:
                    # Dropbox path -> don't use os.path.join()
                    to_path = dialog.selected_folder

                    if dialog.selected_folder[-1:] != DROPBOX_SEP:
                        to_path += DROPBOX_SEP

                    to_path += os.path.basename(path)
                    copied = client.copy(path, to_path)

                    if copied:
                        log(f"File copied: {path} to {to_path}")
                        NotifySyncClient().sync_path(account_settings, to_path)
                    else:
                        log_error(f"File copy failed: {path} to {to_path}")

                del dialog

        elif action == "create_folder":

            if "path" in params:
                path = params["path"]
                keyboard = xbmc.Keyboard("", LANGUAGE_STRING(30030))
                keyboard.doModal()

                if keyboard.isConfirmed():
                    new_folder = path

                    if path[-1:] != DROPBOX_SEP:
                        new_folder += DROPBOX_SEP

                    new_folder += keyboard.getText()
                    folder_created = client.create_folder(new_folder)

                    if folder_created:
                        log(f"New folder created: {new_folder}")
                        xbmc.executebuiltin("Container.Refresh")
                        NotifySyncClient().sync_path(account_settings, new_folder)
                    else:
                        log_error(f"Creating new folder failed: {new_folder}")

        elif action == "upload":

            if "to_path" in params:
                to_path = params["to_path"]
                filename = xbmcgui.Dialog().browse(1, LANGUAGE_STRING(30032), "files")

                if filename:
                    uploaded = client.upload(filename, to_path, dialog=True)

                    if uploaded:
                        log(f"File uploaded: {filename} to {to_path}")
                        xbmc.executebuiltin("Container.Refresh")
                        NotifySyncClient().sync_path(account_settings, to_path)
                    else:
                        log_error(f"File upload failed: {filename} to {to_path}")

        elif action == "download":

            if "path" in params:
                path = params["path"]
                is_dir = "true" == params["is_dir"].lower()
                dialog = xbmcgui.Dialog()
                destination = dialog.browse(3, LANGUAGE_STRING(30025) + LANGUAGE_STRING(30038), "files")

                if destination:
                    downloader = Downloader(client, path, destination, is_dir)
                    downloader.start()

                    while downloader.is_alive():
                        xbmc.sleep(100)

                    # Wait for the thread
                    downloader.join()

                    if downloader.canceled:
                        log("Downloading canceled")
                    elif downloader.error:
                        dialog.ok(ADDON_NAME, LANGUAGE_STRING(30204))
                    else:
                        log("Downloading finished")
                        dialog.ok(ADDON_NAME, f"{LANGUAGE_STRING(30040)} {destination}")

        elif action == "sync_now":
            path = params["path"]
            NotifySyncClient().sync_path(account_settings, path)
        else:
            log_error(f"Unknown action received: {action}")

    elif "module" in params:
        # Module chosen, load and execute module
        module = params["module"]
        __import__(module)
        current_module = sys.modules[module]
        current_module.run(params)

    elif "action" in params and params["action"] == "play":
        account_name = params.get("account", "")
        account_settings = login.get_account(account_name)

        if account_settings:
            client = KodiDropboxClient(
                account_settings.access_token,
                account_settings.refresh_token,
                account_settings.app_key,
                account_settings.app_secret,
                account_settings.account_name,
            )
            path = params["path"]
            url = client.get_media_url(path)
            log_debug(f"Media URL: {url}")
            list_item = xbmcgui.ListItem()
            list_item.select(True)
            list_item.setPath(url)
            filename = params.get("filename")

            if filename:
                video_info = list_item.getVideoInfoTag()
                video_info.setTitle(filename)

            xbmcplugin.setResolvedUrl(HANDLE, True, list_item)
        else:
            log_error("Action play: no account name provided")

    else:
        # No module chosen
        # Run the browse_account module
        module = "browse_account"
        params["module"] = module
        __import__(module)
        current_module = sys.modules[module]
        current_module.run(params)


if __name__ == "__main__":
    run()
