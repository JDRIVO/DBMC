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

import json
import queue
import socket
import threading

from ..utils import *


HOST = "127.0.0.1" # Use 127.0.0.1 needed for windows
PORT = 0 # Let OS get a free port
SOCKET_BUFFER_SIZE = 1024
NOTIFY_SYNC_PATH = "sync_path"
NOTIFY_CHANGED_ACCOUNT = "account_settings_changed"
NOTIFY_ADDED_REMOVED_ACCOUNT = "account_added_removed"


class NotifySyncServer(threading.Thread):
    """
    The NotifySyncServer listens to a TCP port to check if a NotifySyncClient
    reported a change event. A change event can be sent by a client (DMBC plugin)
    when something changes on the synced folder.
    This NotifySyncServer is started by the DropboxSynchronizer. And DropboxSynchronizer
    will check the NotifySyncServer to see if it should perform a sync.
    """

    def __init__(self):
        super().__init__()
        self._socket = None
        self._used_port = 0
        self._notify_list = queue.Queue() # Thread safe
        self._stop_event = threading.Event()

    def stop(self):
        self._stop_event.set()

    def stopped(self):
        return self._stop_event.is_set()

    def setup_server(self):
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

        try:
            self._socket.bind((HOST, PORT))
            self._used_port = self._socket.getsockname()[1]
            self._socket.listen(1)
        except Exception as e:
            log_error(f"NotifySyncServer failed to bind to socket: {e!r}")
            self._socket.close()
            self._socket = None
            self._used_port = 0

        ADDON.setSettingInt("notify_server_port", self._used_port)

    def close_server(self):
        self.stop()
        s = None

        # Fake a notify to stop the thread
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.connect((HOST, self._used_port))
            s.sendall("".encode("utf-8"))
        except socket.error as e:
            log_error(f"NotifySyncServer Exception: {e!r}")
        finally:

            if s:
                s.close()

        # Wait for the thread
        self.join()

    def get_notification(self):
        """
        Returns one notification per call
        """

        account_name = None
        notification = None

        if not self._notify_list.empty():

            try:
                data = json.loads(self._notify_list.get())
                account_name = data[0]
                notification = data[1]
            except Exception as e:
                log_error("NotifySyncServer: failed to parse recieved data")

        return account_name, notification

    def run(self):
        self.setup_server()
        log_debug("NotifySyncServer started")

        while not self.stopped() and self._socket:
            client_socket = None

            # Check for new client connection
            try:
                client_socket, address = self._socket.accept()
            except socket.timeout as e:
                log_debug(f"NotifySyncServer Exception: {e!r}")
            except socket.error as e:
                log_error(f"NotifySyncServer Exception: {e!r}")
            except:
                log_error("NotifySyncServer Exception")

            if client_socket:
                # Check the socket for new notificatios from client(s))
                data = client_socket.recv(SOCKET_BUFFER_SIZE)
                log_debug(f"NotifySyncServer received data: {data!r}")
                self._notify_list.put(data)
                client_socket.close()

        if self._socket:
            self._socket.close()
            self._socket = None

        log_debug("NotifySyncServer stopped")


class NotifySyncClient:
    """
    NotifySyncClient is the client of NotifySyncServer and reports an event to
    NotifySyncServer by sending data over the TCP socket.
    """

    def send_notification(self, account_name, notification, data=None):
        s = None
        used_port = ADDON.getSettingInt("notify_server_port")

        if used_port > 0:

            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.connect((HOST, used_port))
                send_data = json.dumps([account_name, notification, data])
                s.sendall(send_data.encode("utf-8"))
                log_debug(f"NotifySyncClient send: {send_data!r}")
            except socket.error as e:
                log_error(f"NotifySyncClient Exception: {e!r}")
            finally:

                if s:
                    s.close()

        else:
            log_error("NotifySyncClient no port defined")

    def sync_path(self, account, path):
        # Check if synchronization is enabled and check if the path is somewhere
        # in the remote path
        if account.synchronisation and account.remote_path in path:
            # Ignore the path for now otherwise need to change receiving number of
            # SOCKET_BUFFER_SIZE according to the path string size
            self.send_notification(account.account_name, NOTIFY_SYNC_PATH)
        else:
            log_debug("NotifySyncClient Sync not enabled or path not part of remote sync path")

    def account_settings_changed(self, account):
        self.send_notification(account.account_name, NOTIFY_CHANGED_ACCOUNT)

    def account_added_removed(self):
        self.send_notification(None, NOTIFY_ADDED_REMOVED_ACCOUNT)
