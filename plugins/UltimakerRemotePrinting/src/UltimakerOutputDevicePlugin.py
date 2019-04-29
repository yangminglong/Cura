# Copyright (c) 2019 Ultimaker B.V.
# Cura is released under the terms of the LGPLv3 or higher.

import json
import os
import time

from cura.CuraApplication import CuraApplication
from cura.MachineAction import MachineAction
from cura.PrinterOutput.PrinterOutputDevice import ConnectionType
from PyQt5.QtCore import QUrl, pyqtSignal
from PyQt5.QtGui import QDesktopServices
from PyQt5.QtNetwork import QNetworkRequest, QNetworkAccessManager
from UM.i18n import i18nCatalog
from UM.Logger import Logger
from UM.Signal import Signal, signalemitter
from UM.OutputDevice.OutputDeviceManager import ManualDeviceAdditionAttempt
from UM.OutputDevice.OutputDevicePlugin import OutputDevicePlugin
from zeroconf import Zeroconf, ServiceBrowser, ServiceStateChange, ServiceInfo

catalog = i18nCatalog("cura")

##  In the future, extend this as required for more types of connections we might use such as third
#   party connections, Bluetooth, whatever.
class UltimakerOutputDevicePlugin(OutputDevicePlugin):

    devicesDiscovered = Signal()

    def __init__(self):
        super().__init__()
        self._local_device_manager = LocalDeviceManager(self)
        self._cloud_device_manager = CloudDeviceManager(self)

    ##  Start looking for devices.
    def start(self) -> None:
        self._local_device_manager._startDiscovery()
        self._cloud_device_manager._startDiscovery()

    ## Stop looking for devices.
    def stop(self):
        self._local_device_manager._stopDiscovery()
        self._cloud_device_manager._stopDiscovery()

    def addDevice(self, hostname, address, properties) -> None:
        # Do nothing for now
        self.devicesDiscovered.emit()
        return None

    def removeDevice(self, hostname) -> None:
        # Do nothing for now
        self.devicesDiscovered.emit()
        return None



# TODO: There should be a device manager class which includes the following basic methods:
#   1. _startDiscovery
#   2. _stopDiscovery
#   3. _addDevice
#   4. _removeDevice
#   They should always have a _discovered_devices dict with NetworkOutputDevice instances
class DeviceManager():
    def __init__(self):
        return


class LocalDeviceManager():

    def __init__(self, plugin: UltimakerOutputDevicePlugin):
        self._plugin = plugin
        self._discovered_devices = {} # TODO: Typing!
        self._zero_conf_browser = None
        self._zero_conf = None
        self._last_zero_conf_event_time = time.time() #type: float

        # Time to wait after a zero-conf service change before allowing a zeroconf reset
        self._zero_conf_change_grace_period = 0.25 #type: float
    
    ##  Start searching for local printers (on LAN, with Zeroconf).
    def _startDiscovery(self) -> None:

        Logger.log("i", "Starting local (zeroconf) discovery.")

        # Ensure that there is a bit of time after a printer has been discovered. This is a work
        # around for an issue with Qt 5.5.1 up to Qt 5.7 which can segfault if we do this too often.
        # It's most likely that the QML engine is still creating delegates, where the python side
        # already deleted or garbage collected the data. Whatever the case, waiting a bit ensures
        # that it doesn't crash.
        if time.time() - self._last_zero_conf_event_time > self._zero_conf_change_grace_period:
            
            # Stop any previously running Zeroconf discovery and destroy existing browser.
            self._stopDiscovery()
            if self._zero_conf_browser:
                self._zero_conf_browser.cancel()
                self._zero_conf_browser = None

            # Remove any previously discovered devices from the discovered devices list.
            # for device in list(self._discovered_devices):
            #     self._removeDevice(device)

            # Create a new Zeroconf browser and start searching.
            self._zero_conf = Zeroconf()
            self._zero_conf_browser = ServiceBrowser(
                Zeroconf(),
                u'_ultimaker._tcp.local.',
                [self._onServiceChanged]
            )

    ##  Stop searching for local printers (on LAN, with Zeroconf).
    def _stopDiscovery(self) -> None:
        if self._zero_conf is not None:
            Logger.log("d", "Closing Zeroconf...")
            self._zero_conf.close()

        ##  Triggered when a zeroconf service is found
    def _onServiceChanged(self, zeroconf, service_type, name, state_change) -> None:

        # Reset the Zeroconf timer
        self._last_zero_conf_event_time = time.time()

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
                        self._plugin.addDevice(str(name), address, info.properties)
                    else:
                        Logger.log("w", "The type of the found device is '%s', not 'printer'! Ignoring.." % device_type)
        # For services that are removed:
        elif state_change == ServiceStateChange.Removed:
            Logger.log("d", "Zeroconf service removed: %s" % name)
            self._plugin.removeDevice(str(name))

class CloudDeviceManager():

    def __init__(self, plugin: UltimakerOutputDevicePlugin):
        self._discovered_devices = {} # TODO: Typing!

    ##  Start searching for printers associated with an Ultimaker Cloud account.
    def _startDiscovery(self) -> None:
        # Do nothing for now
        return None
    
    def _stopDiscovery(self) -> None:
        # Do nothing for now
        return None
