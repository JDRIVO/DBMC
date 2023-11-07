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

import resources.lib.login as login
from resources.lib.utils import *
from resources.lib.dropbox_viewer import *


HANDLE = int(sys.argv[1])


class FolderBrowser(DropboxViewer):

    def __init__(self, params, account_settings):
        super().__init__(params, account_settings)

    def build_list(self):
        super().build_list(self.get_metadata(self._current_path, directory=True))

    def show(self):
        super().show(cache_to_disc=False)

    def get_url(self, path, module=None):
        return super().get_url(path, module)


def run(params):
    # This is the entry point
    account_name = params.get("account", "")
    account_settings = login.get_account(account_name)

    if account_settings:
        browser = FolderBrowser(params, account_settings)
        browser.build_list()
        browser.show()
    else:
        xbmcplugin.endOfDirectory(HANDLE, succeeded=False)
