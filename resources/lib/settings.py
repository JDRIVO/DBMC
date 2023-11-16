class Settings:

    def __init__(self, addon):
        self._addon = addon

    def _getSetting(self, id):
        return self._addon.getSetting(id)

    def getString(self, id, default=None):
        value = self._getSetting(id)

        if value:
            return value
        else:
            return default

    def getBool(self, id, default=None):
        value = self._getSetting(id)

        if value:
            return value == "true"
        else:
            return default

    def getInt(self, id, default=None):

        try:
            return int(self._getSetting(id))
        except ValueError:
            return default
