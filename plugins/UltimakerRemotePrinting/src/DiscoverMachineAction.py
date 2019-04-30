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
from .UltimakerOutputDevicePlugin import UltimakerOutputDevicePlugin

catalog = i18nCatalog("cura")

# This class is responsible for creating the discovery pop up, but does no actual logic itself.
# It's just for exposing stuff to QML
# TODO: What is a machine action?
class DiscoverUM3Action(MachineAction):

    def __init__(self) -> None:
        super().__init__("DiscoverUM3Action", catalog.i18nc("@action","Connect via Network"))
        self._qml_url = "resources/qml/DiscoverMachineAction.qml"
        self._plugin = None #type: Optional[UltimakerOutputDevicePlugin]
        self._app = CuraApplication.getInstance()
        self._devices = []
        self._additional_ui_components = None #type: Optional[QObject]

        self._app.engineCreatedSignal.connect(self._createAdditionalUIComponents)

    ##  This is an internal-only signal which is emitted when the main plugin discovers devices.
    #   Its only purpose is to update properties exposed to QML. Do not connect it anywhere else!
    discoveredDevicesChanged = pyqtSignal()

    ##  Emit the discoveredDevicesChanged signal when the main plugin discovers devices.
    def _onDeviceDiscovered(self) -> None:
        self.discoveredDevicesChanged.emit()

    ##  Get the UltimakerRemotePrinting plugin from the OutputDeviceManager.
    def _getPlugin(self) -> UltimakerOutputDevicePlugin:
        return self._app.getOutputDeviceManager().getOutputDevicePlugin("UltimakerRemotePrinting")

    ##  Create additional UI components such as the "Send Print Job" button.
    def _createAdditionalUIComponents(self) -> None:
        Logger.log("d", "Creating additional UI components for Ultimaker Remote Printing.")

        # Create networking dialog.
        plugin_path = PluginRegistry.getInstance().getPluginPath("UltimakerRemotePrinting")
        if not plugin_path:
            return
        path = os.path.join(plugin_path, "resources/qml/UM3InfoComponents.qml")
        self._additional_ui_components = CuraApplication.getInstance().createQmlComponent(path, {
            "manager": self
        })
        if not self._additional_ui_components:
            Logger.log("w", "Could not create UI components for Ultimaker Remote Printing.")
            return

        # Create extra components.
        self._app.addAdditionalComponent("monitorButtons", self._additional_ui_components.findChild(QObject, "networkPrinterConnectButton"))

    ##  Override parent method in MachineAction.
    #   This requires not attention from the user (any more), so we don't need to show any 'upgrade
    #   screens'.
    def needsUserInteraction(self) -> bool:
        return False
    
    # QML Slots & Properties
    # ==============================================================================================
    # TODO: From here on down, everything is just a wrapper for the main plugin, needlessly adding
    # complexity. The plugin itself should be able to expose these things to QML without using these
    # wrapper functions.

    ##  Trigger the plugin's startDiscovery method from QML.
    @pyqtSlot()
    def performDiscovery(self) -> None:
        if not self._plugin:
            self._plugin = self._getPlugin()
        self._plugin.deviceDiscovered.connect(self._onDeviceDiscovered)
        self._plugin.start()

    ##  Associate the currently active machine with the given printer device. The network connection
    #   information will be stored into the metadata of the currently active machine.
    #   TODO: This should be an API call
    @pyqtSlot(QObject)
    def associateActiveMachineWithPrinterDevice(self, printer_device: Optional["PrinterOutputDevice"]) -> None:
        if not self._plugin:
            self._plugin = self._getPlugin()
        self._plugin.associateActiveMachineWithPrinterDevice(printer_device)

    @pyqtSlot(result = str)
    def getLastManualEntryKey(self) -> str:
        if not self._plugin:
            self._plugin = self._getPlugin()
        return self._plugin.getLastManualDevice()
    
    ##  List of discovered devices.
    @pyqtProperty("QVariantList", notify = discoveredDevicesChanged)
    def discoveredDevices(self): # TODO: Typing!
        if not self._plugin:
            self._plugin = self._getPlugin()
        devices = list(self._plugin.getDiscoveredLocalDevices().values())
        devices.sort(key = lambda k: k.name)
        return devices

    ##  Pass-through. See UltimakerOutputDevicePlugin.resetLastManualDevice().
    # TODO: was formerly called "reset"
    @pyqtSlot()
    def resetLastManualDevice(self):
        if not self._plugin:
            self._plugin = self._getPlugin()
        self._plugin.resetLastManualDevice()

    ##  Pass-through. See UltimakerOutputDevicePlugin.activeMachineNetworkKey().
    @pyqtSlot(result = str)
    def activeMachineNetworkKey(self) -> str:
        if not self._plugin:
            self._plugin = self._getPlugin()
        return self._plugin.activeMachineNetworkKey()
    
    ##  Pass-through. See UltimakerOutputDevicePlugin.activeMachineHasNetworkKey().
    @pyqtSlot(str, result = bool)
    def activeMachineHasNetworkKey(self, key: str) -> bool:
        if not self._plugin:
            self._plugin = self._getPlugin()
        return self._plugin.activeMachineHasNetworkKey()
    
    ##  Pass-through. See UltimakerOutputDevicePlugin.setGroupName().
    @pyqtSlot(str)
    def setGroupName(self, group_name: str) -> None:
        if not self._plugin:
            self._plugin = self._getPlugin()
        return self._plugin.setGroupName()

    ##  Pass-through. See UltimakerOutputDevicePlugin.removeManualDevice().
    @pyqtSlot(str, str)
    def removeManualDevice(self, key: str, address: str) -> None:
        if not self._plugin:
            self._plugin = self._getPlugin()
        return self._plugin.removeManualDevice(key, address)

    ##  Pass-through. See UltimakerOutputDevicePlugin.setManualDevice().
    @pyqtSlot(str, str)
    def setManualDevice(self, key: str, address: str) -> None:
        if not self._plugin:
            self._plugin = self._getPlugin()
        return self._plugin.setManualDevice(key, address)

    ##  Pass-through. See UltimakerOutputDevicePlugin.loadConfigurationFromPrinter().
    @pyqtSlot()
    def loadConfigurationFromPrinter(self) -> None:
        if not self._plugin:
            self._plugin = self._getPlugin()
        return self._plugin.loadConfigurationFromPrinter()