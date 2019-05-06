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
from cura.CuraApplication import CuraApplication
from PyQt5.QtNetwork import QNetworkRequest, QNetworkAccessManager
from PyQt5.QtCore import QUrl
from UM.Version import Version

catalog = i18nCatalog("cura")

class LocalDeviceManager():

    def __init__(self, plugin: "UltimakerOutputDevicePlugin"):
        self._plugin = plugin
        self._zeroconf_browser = None
        self._zeroconf = None
        self._last_zeroconf_event_time = time.time() #type: float

        # Time to wait after a zero-conf service change before allowing a zeroconf reset
        self._zeroconf_change_grace_period = 0.25 #type: float

        # Get list of manual instances from preferences
        self._preferences = CuraApplication.getInstance().getPreferences()
        self._preferences.addPreference("um3networkprinting/manual_instances", "")  # A comma-separated list of ip adresses or hostnames
        self._manual_addresses = self._preferences.getValue("um3networkprinting/manual_instances").split(",")

        self._api_version = "1"
        self._api_prefix = "/api/v" + self._api_version + "/"
        self._cluster_api_version = "1"
        self._cluster_api_prefix = "/cluster-api/v" + self._cluster_api_version + "/"
        self._network_manager = QNetworkAccessManager()
        self._network_manager.finished.connect(self._onNetworkRequestFinished)
        self._min_cluster_version = Version("4.0.0")
        self._min_cloud_version = Version("5.2.0")
    
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

            hostname = str(name).split(".")[0]
            if info:
                device_type = info.properties.get(b"type", None)
                if device_type:
                    if device_type == b"printer":
                        address = '.'.join(map(lambda n: str(n), info.address))
                        self._plugin.addDevice(hostname, "local", info.properties, address)
                    else:
                        Logger.log("w", "The type of the found device is '%s', not 'printer'! Ignoring..." % device_type)
        
        # For services that are removed:
        elif state_change == ServiceStateChange.Removed:
            Logger.log("d", "Zeroconf service removed: %s" % name)
            self._plugin.removeDevice(str(name), "local")

    def checkManuallyAddedDevice(self, address: str):
        if address not in self._manual_addresses:
            self._manual_addresses.append(address)
            self._preferences.setValue("um3networkprinting/manual_instances", ",".join(self._manual_addresses))

        url = QUrl("http://" + address + self._api_prefix + "system")
        name_request = QNetworkRequest(url)
        self._network_manager.get(name_request)

    def _onNetworkRequestFinished(self, reply: "QNetworkReply") -> None:
        reply_url = reply.url().toString()
        address = reply.url().host()
        properties = {}  # type: Dict[bytes, bytes]

        if reply.attribute(QNetworkRequest.HttpStatusCodeAttribute) != 200:
            # Either:
            #  - Something went wrong with checking the firmware version!
            #  - Something went wrong with checking the amount of printers the cluster has!
            #  - Couldn't find printer at the address when trying to add it manually.
            if address in self._manual_addresses:
                # TODO: Remove the printer
                return
            return

        if "system" in reply_url:
            try:
                system_info = json.loads(bytes(reply.readAll()).decode("utf-8"))
            except:
                Logger.log("e", "Something went wrong converting the JSON.")
                return

            properties = {
                b"name": system_info["name"].encode("utf-8"),
                b"address": address.encode("utf-8"),
                b"firmware_version": system_info["firmware"].encode("utf-8"),
                b"manual": b"true",
                b"machine": str(system_info['hardware']["typeid"]).encode("utf-8")
            }

            # Cluster needs an additional request, before it's completed.
            if Version(system_info["firmware"]) > self._min_cluster_version:
                properties[b"incomplete"] = b"true"     
                cluster_url = QUrl("http://" + address + self._cluster_api_prefix + "printers/")
                cluster_request = QNetworkRequest(cluster_url)
                self._network_manager.get(cluster_request)

            self._plugin.addDevice(system_info["hostname"], "local", properties, address)
        
        # This handles the cluster requests made above...
        elif "printers" in reply_url:
            # So we confirmed that the device is in fact a cluster printer, and we should now know how big it is.
            try:
                cluster_printers_list = json.loads(bytes(reply.readAll()).decode("utf-8"))
            except:
                Logger.log("e", "Something went wrong converting the JSON.")
                return
            hostname = cluster_printers_list[0]["unique_name"]
            discovered_devices = self._plugin.getDiscoveredDevices("local")
            if hostname in discovered_devices:
                device = discovered_devices[hostname]
                properties = device.getProperties().copy()
                if b"incomplete" in properties:
                    del properties[b"incomplete"]
                properties[b"cluster_size"] = str(len(cluster_printers_list)).encode("utf-8")

                # Remove the old version of the device and replace it with the updated one
                self._plugin.removeDevice(hostname, "local")
                self._plugin.addDevice(hostname, "local", properties, address)

        if address in self._manual_addresses:
            # TODO: Remove the printer
            return