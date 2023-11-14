import threading

from resources.lib.utils import *
from resources.lib.oauth.register import *
from resources.lib.sync.dropbox_sync import DropboxSynchronizer


if __name__ == "__main__":
    monitor = xbmc.Monitor()
    sync = DropboxSynchronizer()
    sync.start()
    port = ADDON.getSettingInt("registration_server_port")

    try:
        server = ThreadedHTTPServer(("", port), RequestHandler)
    except Exception as e:
        server = ThreadedHTTPServer(("", 0), RequestHandler)

    server_thread = threading.Thread(target=server.serve_forever)
    server_thread.start()

    while not monitor.abortRequested():

        if monitor.waitForAbort(1):
            break

    server.shutdown()
    server.server_close()
    server.socket.close()
