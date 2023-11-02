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

import time

import xbmcgui

from .utils import *
from .account_settings import AccountSettings


def unlock(account_settings):
    unlocked = True
    win = xbmcgui.Window(xbmcgui.getCurrentWindowId())

    if account_settings.passcode:
        win_prop_name = account_settings.account_name + "Unlocked"
        unlock_timeout = account_settings.passcode_timeout * 60 # to minutes

        try:
            unlocked_time = float(win.getProperty(win_prop_name))
        except ValueError:
            unlocked_time = 0.0

        unlocked = time.time() < unlocked_time + unlock_timeout

        if not unlocked:
            log("Unlock with passcode required")
            keyboard = xbmc.Keyboard("", LANGUAGE_STRING(30013))
            keyboard.setHiddenInput(True)
            keyboard.doModal()

            if keyboard.isConfirmed():

                if keyboard.getText() == account_settings.passcode:
                    unlocked = True
                else:
                    xbmcgui.Dialog().ok(ADDON_NAME, LANGUAGE_STRING(30014))

        if unlocked:
            win.setProperty(win_prop_name, str(time.time()))

    return unlocked


def clear_unlock(account_settings):
    win_prop_name = account_settings.account_name + "Unlocked"
    win = xbmcgui.Window(xbmcgui.getCurrentWindowId())
    win.clearProperty(win_prop_name)


def get_account(account_name):

    if not account_name:
        return

    account_settings = AccountSettings(account_name)

    if not account_settings.access_token:
        return

    if unlock(account_settings):
        return account_settings
