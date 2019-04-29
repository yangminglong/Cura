# Copyright (c) 2019 Ultimaker B.V.
# Cura is released under the terms of the LGPLv3 or higher.

import os.path

from cura.CuraApplication import CuraApplication
from cura.MachineAction import MachineAction
from PyQt5.QtCore import pyqtSignal, pyqtProperty, pyqtSlot, QObject
from UM.i18n import i18nCatalog
from UM.Logger import Logger
from UM.PluginRegistry import PluginRegistry
from typing import Optional, TYPE_CHECKING

catalog = i18nCatalog("cura")

# This class is responsible for creating the discovery pop up, but does no actual logic itself.
# It's just for exposing stuff to QML
# TODO: What is a machine action?
class DiscoverMachineAction(MachineAction):

    def __init__(self) -> None:
        super().__init__("DiscoverMachineAction", catalog.i18nc("@action","Connect via Network"))
        self._qml_url = "resources/qml/DiscoverUM3Action.qml"
        self._plugin = None #type: Optional[UM3OutputDevicePlugin]
        self.__additional_components_view = None #type: Optional[QObject]
        self._app = CuraApplication.getInstance()

        # Wait for Cura's QML engine to be ready, then create UI components.
        self._app.engineCreatedSignal.connect(self._createUIComponents)

    ##  This is an internal-only signal which is emitted when the main plugin discovers devices.
    #   Its only purpose is to update properties exposed to QML. Do not connect it anywhere else!
    discoveredDevicesChanged = pyqtSignal()

    ##  Emit the discoveredDevicesChanged signal when the main plugin discovers devices.
    def _onDevicesDiscovered(self) -> None:
        self.discoveredDevicesChanged.emit()

    ##  Create UI components for machine discovery.
    def _createUIComponents(self) -> None:
        Logger.log("d", "Creating additional ui components for UM3.")

        # Create networking dialog
        plugin_path = PluginRegistry.getInstance().getPluginPath("UltimakerRemotePrinting")
        if not plugin_path:
            return
        qml_path = os.path.join(plugin_path, "resources/qml/UM3InfoComponents.qml")
        self.__additional_components_view = self._app.createQmlComponent(qml_path, {
            "manager": self
        })
        if not self.__additional_components_view:
            Logger.log("w", "Could not create ui components for UM3.")
            return



    # QML Slots & Properties
    # ==============================================================================================

    ##  Trigger the plugin's startDiscovery method from QML.
    @pyqtSlot()
    def startDiscovery(self) -> None:
        Logger.log("d", "Starting device discovery.")
        
        if not self._network_plugin:
            self._plugin = self._app.getOutputDeviceManager().getOutputDevicePlugin("UltimakerRemotePrinting")
            self._plugin.devicesDiscovered.connect(self._onDevicesDiscovered)
        
        self._plugin.startDiscovery()

    # TODO: From here on down, everything is just a wrapper for the main plugin, needlessly adding
    # complexity. The plugin itself should be able to expose these things to QML without using these
    # wrapper functions.

    ##  Associate the currently active machine with the given printer device. The network connection
    #   information will be stored into the metadata of the currently active machine.
    #   TODO: This should be an API call
    @pyqtSlot(QObject)
    def associateActiveMachineWithPrinterDevice(self, printer_device: Optional["PrinterOutputDevice"]) -> None:
        if self._network_plugin:
            self._network_plugin.associateActiveMachineWithPrinterDevice(printer_device)

    @pyqtSlot(result = str)
    def getLastManualEntryKey(self) -> str:
        if self._network_plugin:
            return self._network_plugin.getLastManualDevice()
        return ""
    
    ##  List of discovered devices.
    @pyqtProperty("QVariantList", notify = discoveredDevicesChanged)
    def discoveredDevices(self): # TODO: Typing!
        if self._plugin:
            devices = list(self._plugin.getDiscoveredDevices().values())
            devices.sort(key = lambda k: k.name)
            return devices
        else:
            return []

    ##  Re-filters the list of devices.
    @pyqtSlot()
    def reset(self):
        Logger.log("d", "Reset the list of found devices.")
        if self._network_plugin:
            self._network_plugin.resetLastManualDevice()
        self.discoveredDevicesChanged.emit()

    @pyqtSlot(str, str)
    def removeManualDevice(self, key, address):
        if not self._network_plugin:
            return

        self._network_plugin.removeManualDevice(key, address)

    @pyqtSlot(str, str)
    def setManualDevice(self, key, address):
        if key != "":
            # This manual printer replaces a current manual printer
            self._network_plugin.removeManualDevice(key)

        if address != "":
            self._network_plugin.addManualDevice(address)

    @pyqtSlot()
    def loadConfigurationFromPrinter(self) -> None:
        machine_manager = self._app.getMachineManager()
        hotend_ids = machine_manager.printerOutputDevices[0].hotendIds
        for index in range(len(hotend_ids)):
            machine_manager.printerOutputDevices[0].hotendIdChanged.emit(index, hotend_ids[index])
        material_ids = machine_manager.printerOutputDevices[0].materialIds
        for index in range(len(material_ids)):
            machine_manager.printerOutputDevices[0].materialIdChanged.emit(index, material_ids[index])
    