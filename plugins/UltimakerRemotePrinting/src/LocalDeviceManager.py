# Copyright (c) 2019 Ultimaker B.V.
# Cura is released under the terms of the LGPLv3 or higher.

import json
import os
import time

from .UltimakerLocalOutputDevice import UltimakerLocalOutputDevice
from typing import Optional, TYPE_CHECKING, Dict
from UM.i18n import i18nCatalog
from UM.Logger import Logger
from zeroconf import Zeroconf, ServiceBrowser, ServiceStateChange, ServiceInfo

catalog = i18nCatalog("cura")

class LocalDeviceManager():

    def __init__(self, plugin: "UltimakerOutputDevicePlugin"):
        self._plugin = plugin
        self._discovered_devices = {} # TODO: Typing!
        self._zeroconf_browser = None
        self._zeroconf = None
        self._last_zeroconf_event_time = time.time() #type: float

        # Time to wait after a zero-conf service change before allowing a zeroconf reset
        self._zeroconf_change_grace_period = 0.25 #type: float
    
    ##  Start searching for local printers (on LAN, with Zeroconf).
    def _startDiscovery(self) -> None:
        
        # Ensure that there is a bit of time after a printer has been discovered. This is a work
        # around for an issue with Qt 5.5.1 up to Qt 5.7 which can segfault if we do this too often.
        # It's most likely that the QML engine is still creating delegates, where the python side
        # already deleted or garbage collected the data. Whatever the case, waiting a bit ensures
        # that it doesn't crash.
        if time.time() - self._last_zeroconf_event_time > self._zeroconf_change_grace_period:
            
            # Start fresh...
            self._stopDiscovery()

            Logger.log("i", "Starting local (zeroconf) discovery.")

            # Create a new Zeroconf browser and start searching.
            if not self._zeroconf:
                self._zeroconf = Zeroconf()

            if not self._zeroconf_browser:
                self._zeroconf_browser = ServiceBrowser(
                    Zeroconf(),
                    u'_ultimaker._tcp.local.',
                    [self._onServiceChanged]
            )

    ##  Stop any previously running Zeroconf discovery and destroy existing browser.
    def _stopDiscovery(self) -> None:

        # Cancel the browser if it exists.
        if self._zeroconf_browser:
            self._zeroconf_browser.cancel()
            self._zeroconf_browser = None

        # Close Zeroconf if it exists
        if self._zeroconf:
            Logger.log("d", "Closing Zeroconf...")
            self._zeroconf.close()
            self._zeroconf = None

        ##  Triggered when a zeroconf service is found
    def _onServiceChanged(self, zeroconf, service_type, name, state_change) -> None:

        # Reset the Zeroconf timer
        self._last_zeroconf_event_time = time.time()

        # For services that are added:
        if state_change == ServiceStateChange.Added:
            info = zeroconf.get_service_info(service_type, name)

            # An example of what the info will typically look like:
            # -----------------------------------------------------
            #   type = "_ultimaker._tcp.local.",
            #   name = "ultimakersystem-ccbdd300203a._ultimaker._tcp.local.",
            #   address = b"\n\xb7\x01\x8d",
            #   port = 80,
            #   weight = 0,
            #   priority = 0,
            #   server = "ultimakersystem-ccbdd300203a.local.",
            #   properties = {
            #       b"hotend_serial_0": b"8b6bc3170000",
            #       b"hotend_type_0": b"AA 0.4",
            #       b"type": b"printer",
            #       b"cluster_size": b"0",
            #       b"hotend_serial_1": b"ff5327210000",
            #       b"hotend_type_1": b"BB 0.4",
            #       b"name": b"BusdevP6",
            #       b"firmware_version": b"5.2.8.20190320",
            #       b"machine": b"9066.0"
            #   }
            if info:
                device_type = info.properties.get(b"type", None)
                if device_type:
                    if device_type == b"printer":
                        address = '.'.join(map(lambda n: str(n), info.address))
                        print("ADDING DEVICE", str(name))
                        self._plugin.addDevice(str(name), "local", info.properties, address)
                    else:
                        Logger.log("w", "The type of the found device is '%s', not 'printer'! Ignoring..." % device_type)
        
        # For services that are removed:
        elif state_change == ServiceStateChange.Removed:
            Logger.log("d", "Zeroconf service removed: %s" % name)
            self._plugin.removeDevice(str(name), "local")