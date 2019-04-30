# Copyright (c) 2019 Ultimaker B.V.
# Cura is released under the terms of the LGPLv3 or higher.

import json
import os
import time

from .CloudDeviceManager import CloudDeviceManager
from .LocalDeviceManager import LocalDeviceManager
from .UltimakerLocalOutputDevice import UltimakerLocalOutputDevice
from cura.CuraApplication import CuraApplication
from cura.MachineAction import MachineAction
from cura.PrinterOutput.PrinterOutputDevice import ConnectionType
from cura.Settings.CuraContainerRegistry import CuraContainerRegistry
from PyQt5.QtCore import QUrl, pyqtSignal
from PyQt5.QtGui import QDesktopServices
from PyQt5.QtNetwork import QNetworkRequest, QNetworkAccessManager
from typing import Optional, TYPE_CHECKING, Dict
from UM.i18n import i18nCatalog
from UM.Logger import Logger
from UM.OutputDevice.OutputDeviceManager import ManualDeviceAdditionAttempt
from UM.OutputDevice.OutputDevicePlugin import OutputDevicePlugin
from UM.Signal import Signal, signalemitter
from zeroconf import Zeroconf, ServiceBrowser, ServiceStateChange, ServiceInfo

catalog = i18nCatalog("cura")

##  In the future, extend this as required for more types of connections we might use such as third
#   party connections, Bluetooth, whatever.
class UltimakerOutputDevicePlugin(OutputDevicePlugin):

    deviceDiscovered = Signal()

    def __init__(self):
        super().__init__()
        self._local_device_manager = LocalDeviceManager(self)
        self._cloud_device_manager = CloudDeviceManager(self)
        self._discovered_devices = {
            "local": {},
            "cloud": {}
        }

    ##  Start looking for devices.
    def start(self) -> None:
        self._local_device_manager._startDiscovery()
        self._cloud_device_manager._startDiscovery()

    ## Stop looking for devices.
    def stop(self) -> None:
        self._local_device_manager._stopDiscovery()
        self._cloud_device_manager._stopDiscovery()

    def addDevice(self, hostname, connection_type, properties, address) -> None:
        if connection_type is "local":
            device = UltimakerLocalOutputDevice(hostname, address, properties)
        elif connection_type is "cloud":
            # TODO: Handle!
            device = None
        else:
            # TODO: Handle!
            return
        self._discovered_devices[connection_type][hostname] = device
        self.deviceDiscovered.emit()

    def removeDevice(self, hostname, connection_type) -> None:
        # Do nothing for now
        self.deviceDiscovered.emit()
        return None

    def getDiscoveredDevices(self) -> Dict:
        return self._discovered_devices
    
    def getDiscoveredCloudDevices(self) -> Dict:
        return self._discovered_devices["cloud"]

    def getDiscoveredLocalDevices(self) -> Dict:
        return self._discovered_devices["local"]

    # TODO: Replace with API calls, we should not be touching internal Cura data structures!
    # TODO: Only identify printers using host names, never network keys!
    def activeMachineNetworkKey(self) -> str:
        global_container_stack = CuraApplication.getInstance().getGlobalContainerStack()
        if global_container_stack:
            meta_data = global_container_stack.getMetaData()
            if "um_network_key" in meta_data:
                return global_container_stack.getMetaDataEntry("um_network_key")
        return ""

    def activeMachineHasNetworkKey(self, key: str) -> bool:
        metadata_filter = {"um_network_key": key}
        containers = CuraContainerRegistry.getInstance().findContainerStacks(type="machine", **metadata_filter)
        return bool(containers)

    ##  Find all container stacks that have the pair 'key = value' in its metadata and replaces the
    #   value with a new value.
    def _replaceContainersMetadata(self, key: str, value: str, new_value: str) -> None:
        machines = CuraContainerRegistry.getInstance().findContainerStacks(type="machine")
        for machine in machines:
            if machine.getMetaDataEntry(key) == value:
                machine.setMetaDataEntry(key, new_value)
    
    def setGroupName(self, group_name: str) -> None:
        Logger.log("d", "Attempting to set the group name of the active machine to %s", group_name)
        global_container_stack = CuraApplication.getInstance().getGlobalContainerStack()
        if global_container_stack:
            meta_data = global_container_stack.getMetaData()
            if "group_name" in meta_data:
                previous_connect_group_name = meta_data["group_name"]
                global_container_stack.setMetaDataEntry("group_name", group_name)
                # Find all the places where there is the same group name and change it accordingly
                self._replaceContainersMetadata(key = "group_name", value = previous_connect_group_name, new_value = group_name)
            else:
                global_container_stack.setMetaDataEntry("group_name", group_name)
            # Set the default value for "hidden", which is used when you have a group with multiple types of printers
            global_container_stack.setMetaDataEntry("hidden", False)

        # Ensure that the connection states are refreshed.
        self.refreshConnections()

    # TODO: What is this doing?
    # TODO: Replace with API calls, we should not be touching internal Cura data structures!
    def loadConfigurationFromPrinter(self) -> None:
        machine_manager = self._app.getMachineManager()
        hotend_ids = machine_manager.printerOutputDevices[0].hotendIds
        for index in range(len(hotend_ids)):
            machine_manager.printerOutputDevices[0].hotendIdChanged.emit(index, hotend_ids[index])
        material_ids = machine_manager.printerOutputDevices[0].materialIds
        for index in range(len(material_ids)):
            machine_manager.printerOutputDevices[0].materialIdChanged.emit(index, material_ids[index])

    def removeManualDevice(self, key: str, address: str):
        return None

    def resetLastManualDevice(self):
        self.deviceDiscovered.emit()
        return None

    def setManualDevice(self, key: str, address: str):
        if key != "":
            # This manual printer replaces a current manual printer
            self.removeManualDevice(key)
        if address != "":
            self.addManualDevice(address)