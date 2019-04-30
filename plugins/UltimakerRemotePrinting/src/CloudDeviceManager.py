# Copyright (c) 2019 Ultimaker B.V.
# Cura is released under the terms of the LGPLv3 or higher.

from UM.i18n import i18nCatalog
from UM.Logger import Logger
from typing import Optional, TYPE_CHECKING, Dict

catalog = i18nCatalog("cura")

class CloudDeviceManager():

    def __init__(self, plugin: "UltimakerOutputDevicePlugin"):
        self._discovered_devices = {} # TODO: Typing!

    ##  Start searching for printers associated with an Ultimaker Cloud account.
    def _startDiscovery(self) -> None:
        # Do nothing for now
        return None
    
    def _stopDiscovery(self) -> None:
        # Do nothing for now
        return None
