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

from .utils import *


class DropboxFileBrowser(xbmcgui.WindowXMLDialog):
    """
    Dialog class that let's user select the a folder from Dropbox.
    """

    # FileBrowser IDs
    DIRECTORY_LIST = 450
    THUMB_LIST = 451
    HEADING_LABEL = 411
    PATH_LABEL = 412
    OK_BUTTON = 413
    CANCEL_BUTTON = 414
    CREATE_FOLDER = 415
    FLIP_IMAGE_HOR = 416
    # ACTION IDs
    ACTION_SELECT_ITEM = 7
    _heading = ""
    _current_path = ""
    selected_folder = None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._start_path = DROPBOX_SEP

    def set_db_client(self, client):
        self.client = client

    def set_heading(self, heading, path=None):
        self._heading = heading

        if path:
            self._start_path = path

        self._thumb_view = False

    def onInit(self):
        # super().onInit()
        # Some skins don't have the following items in the FileBrowser
        try:
            self.getControl(self.FLIP_IMAGE_HOR).setEnabled(False)
        except Exception as e:
            log_debug(f"DropboxFileBrowser Exception: {e!r}")

        try:
            self.getControl(self.THUMB_LIST).setVisible(False) # Bugy - check/change FileBrowser.xml file?
            self._thumb_view = True
        except Exception as e:
            log_debug(f"DropboxFileBrowser Exception: {e!r}")

        self.getControl(self.HEADING_LABEL).setLabel(self._heading)
        self.show_folders(self._start_path)

    def show_folders(self, path):
        log_debug(f"Selecting path: {path}")

        # Some skins don't have the following items in the FileBrowser
        try:
            self.getControl(self.PATH_LABEL).setLabel(path)
        except Exception as e:
            log_debug(f"DropboxFileBrowser Exception: {e!r}")

        list_view = self.getControl(self.DIRECTORY_LIST)

        if self._thumb_view:
            thumb_view = self.getControl(self.THUMB_LIST)

        list_view.reset()

        if self._thumb_view:
            thumb_view.reset()

        self._current_path = path
        entries = self.client.get_metadata(path, directory=True)

        if not entries:
            raise Exception(f"{ADDON_ID} No folders were retrieved")
        else:
            folders = entries["folders"]

        list_items = []

        if path != DROPBOX_SEP:
            back_path = os.path.dirname(path)
            list_item = xbmcgui.ListItem(label="..", label2=back_path)
            list_item.setArt({"icon": "DefaultFolderBack.png", "thumb": "DefaultFolderBack.png"})
            list_items.append(list_item)

        for path, metadata in folders.items():
            list_item = xbmcgui.ListItem(label=metadata.name, label2=path)
            list_item.setArt({"icon": "DefaultFolder.png", "thumb": "DefaultFolder.png"})
            list_items.append(list_item)

        list_view.addItems(list_items)

        if self._thumb_view:
            thumb_view.addItems(list_items) # Bugy - check/change FileBrowser.xml file?

        self.setFocusId(self.DIRECTORY_LIST)

    def onClick(self, controlId):

        if controlId == self.DIRECTORY_LIST:
            # Update with new selected path
            new_path = self.getControl(controlId).getSelectedItem().getLabel2()
            self.show_folders(new_path)
        elif controlId == self.OK_BUTTON:
            self.selected_folder = self._current_path
            self.close()
        elif controlId == self.CANCEL_BUTTON:
            self.close()
        elif controlId == self.CREATE_FOLDER:
            keyboard = xbmc.Keyboard("", LANGUAGE_STRING(30030))
            keyboard.doModal()

            if keyboard.isConfirmed():
                new_folder = self._current_path

                if self._current_path[-1:] != DROPBOX_SEP:
                    new_folder += DROPBOX_SEP

                new_folder += keyboard.getText()
                folder_created = self.client.create_folder(new_folder)

                if folder_created:
                    log(f"New folder created: {new_folder}")
                    # Update current list
                    self.show_folders(self._current_path)
                else:
                    log_error(f"Creating new folder failed: {new_folder}")

#     def onAction(self, action):

#         if action.getId() == self.ACTION_SELECT_ITEM:
#             controlId = self.getFocusId()

#             if controlId == self.DIRECTORY_LIST:
#                 # Update with new selected path
#                 new_path = self.getControl(controlId).getSelectedItem().getLabel2()
#                 self.show_folders(new_path)
#             elif controlId == self.OK_BUTTON:
#                 self.selected_folder = self._current_path
#                 self.close()
#             elif controlId == self.CANCEL_BUTTON:
#                 self.close()

#             # self.onClick(controlId)

#         else:
#             super().onAction(action)
