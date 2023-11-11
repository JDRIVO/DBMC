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
import socket

import xbmcgui
import xbmcvfs
import xbmcplugin

import resources.lib.login as login
from resources.lib.utils import *
from resources.lib.dropbox_client import KodiDropboxClient
from resources.lib.sync.notify_sync import NotifySyncClient
from resources.lib.dropbox_file_browser import DropboxFileBrowser


HANDLE = int(sys.argv[1])


class AccountBrowser:
    """
    Shows the list of accounts to the user and implements all the account features:
    - Showing the current accounts
    - add/remove/rename accounts
    """

    def __init__(self, params):
        self._content_type = params.get("content_type", "executable")
        self._accounts_dir = f"{DATA_PATH}/accounts/"

        if not xbmcvfs.exists(self._accounts_dir):
            xbmcvfs.mkdirs(self._accounts_dir)

    def build_list(self):
        account_names = os.listdir(self._accounts_dir)

        for account_name in account_names:
            self.add_account(account_name)

        self.add_action(LANGUAGE_STRING(30042), "add")

    def show(self):
        xbmcplugin.endOfDirectory(HANDLE, cacheToDisc=False)

    def add_account(self, account_name):
        icon_image = "DefaultFile.png"

        if self._content_type == "audio":
            icon_image = "DefaultAddonMusic.png"
        elif self._content_type == "video":
            icon_image = "DefaultAddonVideo.png"
        elif self._content_type == "image":
            icon_image = "DefaultAddonPicture.png"

        list_item = xbmcgui.ListItem(account_name)
        list_item.setArt({"icon": icon_image, "thumb": icon_image})
        url = f"{ADDON_URL}?content_type={self._content_type}&module=browse_folder&account={account_name}"
        context_menu_items = []
        context_menu_items.append((LANGUAGE_STRING(30044), self.get_context_url("remove", account_name)))
        context_menu_items.append((LANGUAGE_STRING(30012), self.get_context_url("change_passcode", account_name)))
        context_menu_items.append((LANGUAGE_STRING(30100), self.get_context_url("change_synchronization", account_name)))
        list_item.addContextMenuItems(context_menu_items)
        xbmcplugin.addDirectoryItem(HANDLE, url, list_item, isFolder=True)

    def add_action(self, account_name, action):
        list_item = xbmcgui.ListItem(account_name)
        list_item.setArt({"icon": "DefaultAddSource.png", "thumb": "DefaultAddSource.png"})
        url = f"{ADDON_URL}?content_type={self._content_type}&module=browse_account&action=add"
        context_menu_items = []
        list_item.addContextMenuItems(context_menu_items)
        xbmcplugin.addDirectoryItem(HANDLE, url, list_item, isFolder=True)

    def get_context_url(self, action, account_name):
        return f"RunPlugin({ADDON_URL}?action={action}&module=browse_account&account={account_name})"


def change_passcode(account_settings):
    account_name = account_settings.account_name
    log_debug(f"Changing passcode for account: {account_name}")
    enable_passcode = False
    dialog = xbmcgui.Dialog()

    if dialog.yesno(ADDON_NAME, f"{LANGUAGE_STRING(30011)} {account_name}?"):
         enable_passcode = True

    log_debug(f"Passcode enabled: {enable_passcode}")

    if not enable_passcode:
        account_settings.passcode = ""
        account_settings.save()
        login.clear_unlock(account_settings)
        return

    keyboard = xbmc.Keyboard("", LANGUAGE_STRING(30034))
    keyboard.setHiddenInput(True)
    keyboard.doModal()

    if keyboard.isConfirmed():
        account_settings.passcode = keyboard.getText()
        log_debug("Passcode set")
        login.clear_unlock(account_settings)
        valid_timeout = False

        while not valid_timeout:
            timeout_str = dialog.numeric(0, LANGUAGE_STRING(30015), str(account_settings.passcode_timeout))

            if not timeout_str:
                return

            timeout = int(timeout_str)

            if 1 <= timeout <= 120:
                account_settings.passcode_timeout = timeout
                log_debug(f"Passcode timeout set: {timeout}")
                valid_timeout = True
            else:
                log_debug("Wrong timeout value")
                dialog.ok(ADDON_NAME, LANGUAGE_STRING(30207))

        account_settings.save()


def change_synchronization(account_settings):
    account_name = account_settings.account_name
    log_debug(f"Changing synchronization for account: {account_name}")
    account_settings.synchronisation = False
    sync_settings_valid = False
    dialog = xbmcgui.Dialog()

    if dialog.yesno(ADDON_NAME, f"{LANGUAGE_STRING(30101)} {account_name}?"):
         account_settings.synchronisation = True

    log_debug(f"Synchronization enabled: {account_settings.synchronisation}")

    if not account_settings.synchronisation:
        sync_settings_valid = True
    else:
        # Select the local folder
        selected_folder = dialog.browse(3, LANGUAGE_STRING(30102), "files", mask="", treatAsFolder=True)
        log_debug(f"Selected local folder: {selected_folder}")

        if selected_folder:
            account_settings.sync_path = selected_folder
            # Select the remote folder
            dialog = DropboxFileBrowser("FileBrowser.xml", ADDON_PATH)
            client = KodiDropboxClient(
                account_settings.access_token,
                account_settings.refresh_token,
                account_settings.app_key,
                account_settings.app_secret,
                account_name=account_settings.account_name,
            )
            dialog.set_db_client(client)
            dialog.set_heading(LANGUAGE_STRING(30109), account_settings.remote_path)
            dialog.doModal()
            log_debug(f"Selected remote folder: {dialog.selected_folder}")

            if dialog.selected_folder:
                account_settings.remote_path = dialog.selected_folder
                dialog = xbmcgui.Dialog()
                valid_frequency = False

                while not valid_frequency:
                    frequency_str = dialog.numeric(0, LANGUAGE_STRING(30105), str(account_settings.sync_freq))

                    if not frequency_str:
                        return

                    frequency = int(frequency_str)

                    if 5 <= frequency <= 1440:
                        account_settings.sync_freq = frequency
                        log_debug(f"Synchronization frequency set: {frequency}")
                        valid_frequency = True
                    else:
                        log_debug("Wrong frequency value")
                        dialog.ok(ADDON_NAME, LANGUAGE_STRING(30208))

                sync_settings_valid = True

    if sync_settings_valid:
        account_settings.save()
        NotifySyncClient().account_settings_changed(account_settings)


def run(params):
    action = params.get("action", "")

    if action == "add":
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        address = s.getsockname()[0]
        s.close()
        selection = xbmcgui.Dialog().ok(
            ADDON_NAME,
            "{}\n\n[B][COLOR blue]http://{}:{}/register[/COLOR][/B]".format(
                LANGUAGE_STRING(30001),
                address,
                ADDON_SETTINGS.getInt("registration_server_port"),
            )
        )

    elif action == "remove":
        account_name = params.get("account", "")
        account_settings = login.get_account(account_name)

        if account_settings:

            if xbmcgui.Dialog().yesno(ADDON_NAME, f"{LANGUAGE_STRING(30045)} {account_name}"):

                try:
                    account_settings.remove()
                except Exception as e:
                    log_error(f"Failed to remove the account: {e}")
                else:
                    NotifySyncClient().account_added_removed()
                    xbmc.executebuiltin("Container.Refresh")

        else:
            log_error("Failed to remove the account")
            xbmcgui.Dialog().ok(ADDON_NAME, LANGUAGE_STRING(30203))

    elif action == "change_passcode":
        account_name = params.get("account", "")
        account_settings = login.get_account(account_name)

        if account_settings:
            change_passcode(account_settings)

    elif action == "change_synchronization":
        account_name = params.get("account", "")
        account_settings = login.get_account(account_name)

        if account_settings:
            change_synchronization(account_settings)

    else:
        browser = AccountBrowser(params)
        browser.build_list()
        browser.show()
