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

import xbmcgui
import xbmcplugin

import resources.lib.login as login
from resources.lib.utils import *
from resources.lib.dropbox_viewer import *


HANDLE = int(sys.argv[1])


class DropboxSearch(DropboxViewer):

    def __init__(self, params, account_settings):
        super().__init__(params, account_settings)
        self._search_text = params.get("search_text", "")

    def build_list(self):
        search_result = self._client.search(self._search_text, self._current_path)
        super().build_list(search_result)

    def show(self):

        if self._loader:
            super().show()
        else:
            xbmcgui.Dialog().ok(ADDON_NAME, LANGUAGE_STRING(30021))
            super().show(succeeded=False)

    def get_url(self, path, module=None):
        url = super().get_url(path, module)
        url += f"&search_text={self._search_text}"
        return url


def run(params):
    account_name = params.get("account", "")
    account_settings = login.get_account(account_name)

    if not account_settings:
        return

    search_text = params.get("search_text", "")

    if not search_text:
        keyboard = xbmc.Keyboard("", LANGUAGE_STRING(30018))
        keyboard.doModal()

        if not keyboard.isConfirmed():
            return

        search_text = keyboard.getText()
        params["search_text"] = search_text
        params["path"] = params.get("path", DROPBOX_SEP)

        if len(search_text) < 2:
            # Search text has to be at least 2 chars
            xbmcgui.Dialog().ok(ADDON_NAME, LANGUAGE_STRING(30019))
        else:
            search = DropboxSearch(params, account_settings)
            dialog = xbmcgui.DialogProgress()
            dialog.create(ADDON_NAME, f"{LANGUAGE_STRING(30020)} {search_text}")
            search.build_list()
            dialog.close()
            search.show()
