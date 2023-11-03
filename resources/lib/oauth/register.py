import os
import re
import urllib.parse
from socketserver import ThreadingMixIn
from http.server import BaseHTTPRequestHandler, HTTPServer

import xbmc

import dropbox.oauth
from ..utils import *
from ..account_settings import AccountSettings
from ..dropbox_client import KodiDropboxClient
from ..sync.notify_sync import NotifySyncClient


DIR_PATH = os.path.join(ADDON_PATH, "resources", "lib", "oauth")
FORM_PATH = os.path.join(DIR_PATH, "form.html")
FORM_SUCCESS_PATH = os.path.join(DIR_PATH, "form_success.html")
FORM_FAILURE_PATH = os.path.join(DIR_PATH, "form_failure.html")


class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True

    def __init__(self, *args, **kwargs):
        HTTPServer.__init__(self, *args, **kwargs)
        monitor = xbmc.Monitor()

        while ADDON_SETTINGS.getInt("registration_server_port") != self.server_port and not monitor.abortRequested():
            ADDON.setSettingInt("registration_server_port", self.server_port)
            xbmc.sleep(100)


class RequestHandler(BaseHTTPRequestHandler):

    def do_POST(self):

        if self.path == "/register":
            content_length = int(self.headers["Content-Length"])
            post_data = self.rfile.read(content_length).decode("utf-8")
            post_data = urllib.parse.unquote_plus(post_data)
            self.send_response(200)
            self.end_headers()

            try:
                app_key, app_secret, code = re.findall("key=(.*)&secret=(.*)&code=(.*)", post_data)[0]
                flow = dropbox.oauth.DropboxOAuth2FlowNoRedirect(app_key, app_secret, token_access_type="offline")
            except Exception as e:

                with open(FORM_FAILURE_PATH, "rb") as data:
                    self.wfile.write(data.read())

                log_error(f"Account registration failed: {e}")
                return

            flow_result = flow.finish(code)
            access_token = flow_result.access_token
            account_info = KodiDropboxClient(access_token=access_token).get_account_info()
            name_info = account_info.name
            account_name = "Account"

            if name_info:
                diplay_name = name_info.display_name

                if diplay_name:
                    account_name = diplay_name

            new_account = AccountSettings(account_name)
            account_present = new_account.app_key
            count = 1

            while account_present:
                new_account = AccountSettings(f"{account_name} ({count})")
                account_present = new_account.app_key
                count += 1

            new_account.refresh_token = flow_result.refresh_token
            new_account.access_token = access_token
            new_account.app_key = app_key
            new_account.app_secret = app_secret
            new_account.save()
            NotifySyncClient().account_added_removed()
            xbmc.executebuiltin("Container.Refresh")

            with open(FORM_SUCCESS_PATH, "rb") as data:
                self.wfile.write(data.read())

    def do_GET(self):

        if self.path == "/register":
            self.send_response(200)
            self.end_headers()

            with open(FORM_PATH, "rb") as data:
                self.wfile.write(data.read())
