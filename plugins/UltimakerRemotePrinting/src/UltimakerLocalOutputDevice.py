# Copyright (c) 2019 Ultimaker B.V.
# Cura is released under the terms of the LGPLv3 or higher.

from typing import Any, cast, Tuple, Union, Optional, Dict, List
from time import time

import io  # To create the correct buffers for sending data to the printer.
import json
import os

from UM.FileHandler.FileHandler import FileHandler
from UM.FileHandler.WriteFileJob import WriteFileJob  # To call the file writer asynchronously.
from UM.i18n import i18nCatalog
from UM.Logger import Logger
from UM.Message import Message
from UM.PluginRegistry import PluginRegistry
from UM.Qt.Duration import Duration, DurationFormat
from UM.Scene.SceneNode import SceneNode  # For typing.
from UM.Settings.ContainerRegistry import ContainerRegistry

from cura.CuraApplication import CuraApplication
from cura.PrinterOutput.Models.PrinterConfigurationModel import PrinterConfigurationModel
from cura.PrinterOutput.Models.ExtruderConfigurationModel import ExtruderConfigurationModel
from cura.PrinterOutput.NetworkedPrinterOutputDevice import AuthState, NetworkedPrinterOutputDevice
from cura.PrinterOutput.Models.PrinterOutputModel import PrinterOutputModel
from cura.PrinterOutput.Models.MaterialOutputModel import MaterialOutputModel
from cura.PrinterOutput.PrinterOutputDevice import ConnectionType

from PyQt5.QtNetwork import QNetworkRequest, QNetworkReply
from PyQt5.QtGui import QDesktopServices, QImage
from PyQt5.QtCore import pyqtSlot, QUrl, pyqtSignal, pyqtProperty, QObject

i18n_catalog = i18nCatalog("cura")


class UltimakerLocalOutputDevice(NetworkedPrinterOutputDevice):

    def __init__(self, device_id, address, properties, parent = None) -> None:
        super().__init__(device_id = device_id, address = address, properties=properties, connection_type = ConnectionType.NetworkConnection, parent = parent)
        self._api_prefix = "/cluster-api/v1/"

        self._application = CuraApplication.getInstance()

        self._number_of_extruders = 2

        self._dummy_lambdas = (
            "", {}, io.BytesIO()
        )  # type: Tuple[Optional[str], Dict[str, Union[str, int, bool]], Union[io.StringIO, io.BytesIO]]

        self._print_jobs = [] # type: List[UM3PrintJobOutputModel]
        self._received_print_jobs = False # type: bool

        if PluginRegistry.getInstance() is not None:
            plugin_path = PluginRegistry.getInstance().getPluginPath("UltimakerRemotePrinting")
            if plugin_path is None:
                Logger.log("e", "Cloud not find plugin path for plugin UM3NetworkPrnting")
                raise RuntimeError("Cloud not find plugin path for plugin UM3NetworkPrnting")
            self._monitor_view_qml_path = os.path.join(plugin_path, "resources", "qml", "MonitorStage.qml")

        self._accepts_commands = True  # type: bool

        # Cluster does not have authentication, so default to authenticated
        self._authentication_state = AuthState.Authenticated

        self._error_message = None  # type: Optional[Message]
        self._write_job_progress_message = None  # type: Optional[Message]
        self._progress_message = None  # type: Optional[Message]

        self._active_printer = None  # type: Optional[PrinterOutputModel]

        self._printer_selection_dialog = None  # type: QObject

        self.setPriority(3)  # Make sure the output device gets selected above local file output
        self.setName(self._id)
        self.setShortDescription(i18n_catalog.i18nc("@action:button Preceded by 'Ready to'.", "Print over network"))
        self.setDescription(i18n_catalog.i18nc("@properties:tooltip", "Print over network"))

        self.setConnectionText(i18n_catalog.i18nc("@info:status", "Connected over the network"))

        self._printer_uuid_to_unique_name_mapping = {}  # type: Dict[str, str]

        self._finished_jobs = []  # type: List[UM3PrintJobOutputModel]

        self._cluster_size = int(properties.get(b"cluster_size", 0))  # type: int

        self._latest_reply_handler = None  # type: Optional[QNetworkReply]
        self._sending_job = None

        self._active_camera_url = QUrl()  # type: QUrl