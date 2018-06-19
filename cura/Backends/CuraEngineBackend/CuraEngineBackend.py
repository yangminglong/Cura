# Copyright (c) 2018 Ultimaker B.V.
# Cura is released under the terms of the LGPLv3 or higher.

from collections import defaultdict
import os
import sys
import time
from typing import TYPE_CHECKING

import Arcus

from UM.Backend.Backend import Backend
from UM.Logging.Logger import Logger
from UM.Resources import Resources
from UM.OS import OS
from UM.Scene.Iterator.DepthFirstIterator import DepthFirstIterator
from UM.i18n import i18nCatalog

from . import StartSliceJob

if TYPE_CHECKING:
    from UM.Application import Application


catalog = i18nCatalog("cura")


def _findCuraEngine(install_path: str) -> str:
    # Find out where the engine is located, and how it is called.
    # This depends on how Cura is packaged and which OS we are running on.
    executable_name = "CuraEngine"
    if OS.isWindows():
        executable_name += ".exe"
    default_engine_location = executable_name
    if os.path.exists(os.path.join(install_path, "bin", executable_name)):
        default_engine_location = os.path.join(install_path, "bin", executable_name)
    if hasattr(sys, "frozen"):
        default_engine_location = os.path.join(os.path.dirname(os.path.abspath(sys.executable)), executable_name)
    if OS.isLinux() and not default_engine_location:
        if not os.getenv("PATH"):
            raise OSError("There is something wrong with your Linux installation.")
        for pathdir in os.getenv("PATH").split(os.pathsep):
            execpath = os.path.join(pathdir, executable_name)
            if os.path.exists(execpath):
                default_engine_location = execpath
                break
    return default_engine_location


class CuraEngineBackend(Backend):

    def __init__(self, application: "Application"):
        super().__init__(application)

        default_engine_location = _findCuraEngine(application.getInstallPrefix())
        default_engine_location = os.path.abspath(default_engine_location)
        Logger.log("i", "Found CuraEngineBackend at: %s", default_engine_location)
        self._application.getPreferences().addPreference("backend/location", default_engine_location)

        self._stored_layer_data = []
        self._stored_optimized_layer_data = {}

        self._scene = self._application.getController().getScene()

        # Listeners for receiving messages from the back-end.
        self._message_handlers["cura.proto.Layer"] = self._onLayerMessage
        self._message_handlers["cura.proto.LayerOptimized"] = self._onOptimizedLayerMessage
        self._message_handlers["cura.proto.Progress"] = self._onProgressMessage
        self._message_handlers["cura.proto.GCodeLayer"] = self._onGCodeLayerMessage
        self._message_handlers["cura.proto.GCodePrefix"] = self._onGCodePrefixMessage
        self._message_handlers["cura.proto.PrintTimeMaterialEstimates"] = self._onPrintTimeMaterialEstimates
        self._message_handlers["cura.proto.SlicingFinished"] = self._onSlicingFinishedMessage

        self._start_slice_job = None
        self._start_slice_job_build_plate = 0

        self._backend_log_max_lines = 20000  # Maximum number of lines to buffer
        self._last_num_objects = defaultdict(int)  # Count number of objects to see if there is something changed
        self._postponed_scene_change_sources = []  # scene change is postponed (by a tool)

        self._slice_start_time = None

    def close(self):
        self._terminate()

    def getEngineCommand(self):
        json_path = Resources.getPath(Resources.DefinitionContainers, "fdmprinter.def.json")
        return [self._application.getPreferences().getValue("backend/location"), "connect", "127.0.0.1:{0}".format(self._port), "-j", json_path, ""]

    ##  Perform a slice of the scene.
    def slice(self):
        Logger.log("d", "Starting to slice...")
        self._slice_start_time = time.time()

        if not hasattr(self._scene, "gcode_dict"):
            self._scene.gcode_dict = {}

        # see if we really have to slice
        build_plate_to_be_sliced = 0
        Logger.log("d", "Going to slice build plate [%s]!" % build_plate_to_be_sliced)

        self._stored_layer_data = []
        self._stored_optimized_layer_data[build_plate_to_be_sliced] = []

        self._scene.gcode_dict[build_plate_to_be_sliced] = []  #[] indexed by build plate number

        self._createSocket()
        self.startEngine()

        slice_message = self._socket.createMessage("cura.proto.Slice")
        self._start_slice_job = StartSliceJob.StartSliceJob(self._application, slice_message)
        if self._start_slice_job.run():
            Logger.log("i", "send message  !!!!!!!!!!")
            self._socket.sendMessage(slice_message)
            self._process.wait()
            Logger.log("i", "process done  !!!!!!!!!!!")
            self._socket.callback_thread.join()
            Logger.log("i", "callback thread done  !!!!!!!!!!!")
            self._socket.close()
        else:
            Logger.log("i", "start slice job failed!!!!!!!!!!")

    def getStartSliceJob(self):
        return self._start_slice_job

    ##  Terminate the engine process.
    #   Start the engine process by calling _createSocket()
    def _terminate(self):
        self._stored_layer_data = []
        self._stored_optimized_layer_data = []
        if self._start_slice_job is not None:
            self._start_slice_job.cancel()

        if self._process is not None:
            Logger.log("d", "Killing engine process")
            try:
                self._process.terminate()
                Logger.log("d", "Engine process is killed. Received return code %s", self._process.wait())
                self._process = None

            except Exception as e:  # terminating a process that is already terminating causes an exception, silently ignore this.
                Logger.log("d", "Exception occurred while trying to kill the engine %s", str(e))

    def _onSocketError(self, error):
        super()._onSocketError(error)
        if error.getErrorCode() == Arcus.ErrorCode.Debug:
            return

        if error.getErrorCode() not in [Arcus.ErrorCode.BindFailedError, Arcus.ErrorCode.ConnectionResetError, Arcus.ErrorCode.Debug]:
            Logger.log("w", "A socket error caused the connection to be reset")

    ##  Remove old layer data (if any)
    def _clearLayerData(self, build_plate_numbers = set()):
        for node in DepthFirstIterator(self._scene.getRoot()):
            if node.callDecoration("getLayerData"):
                if not build_plate_numbers or node.callDecoration("getBuildPlateNumber") in build_plate_numbers:
                    node.getParent().removeChild(node)

    ##  Called when a sliced layer data message is received from the engine.
    #
    #   \param message The protobuf message containing sliced layer data.
    def _onLayerMessage(self, message):
        #Logger.log("i", "!!!!!!!! on layer message")
        pass

    ##  Called when an optimized sliced layer data message is received from the engine.
    #
    #   \param message The protobuf message containing sliced layer data.
    def _onOptimizedLayerMessage(self, message):
        #Logger.log("i", "!!!!!!!! on optimized layer message")
        pass

    def _onProgressMessage(self, message):
        #print("!!!!!!!  [on progress]  ", message)
        pass

    ##  Called when the engine sends a message that slicing is finished.
    #
    #   \param message The protobuf message signalling that slicing is finished.
    def _onSlicingFinishedMessage(self, message):
        gcode_list = self._scene.gcode_dict[self._start_slice_job_build_plate]
        for index, line in enumerate(gcode_list):
            # TODO
            for token in ("{print_time}", "{filament_amount}", "{filament_weight}", "{filament_cost}", "{jobname}"):
                if token in line:
                    Logger.log("i", "------------    %s", line)
            #replaced = line.replace("{print_time}", str(self._application.getPrintInformation().currentPrintTime.getDisplayString()))
            #replaced = line.replace("{print_time}", str(self._application.getPrintInformation().currentPrintTime.getDisplayString(DurationFormat.Format.ISO8601)))
            #replaced = replaced.replace("{filament_amount}", str(self._application.getPrintInformation().materialLengths))
            #replaced = replaced.replace("{filament_weight}", str(self._application.getPrintInformation().materialWeights))
            #replaced = replaced.replace("{filament_cost}", str(self._application.getPrintInformation().materialCosts))
            #replaced = replaced.replace("{jobname}", str(self._application.getPrintInformation().jobName))

            #gcode_list[index] = replaced

        Logger.log("d", "Slicing took %s seconds", time.time() - self._slice_start_time)
        Logger.log("d", "See if there is more to slice...")
        self._socket.callback_thread.done()

    def _onGCodeLayerMessage(self, message):
        #Logger.log("i", "!!!!!! on gcode layer message")
        self._scene.gcode_dict[self._start_slice_job_build_plate].append(message.data.decode("utf-8", "replace"))

    def _onGCodePrefixMessage(self, message):
        #Logger.log("i", "!!!!!! on gcode prefix message")
        self._scene.gcode_dict[self._start_slice_job_build_plate].insert(0, message.data.decode("utf-8", "replace"))

    def _createSocket(self):
        proto_file_path = os.path.abspath(os.path.join("cura", "Backends", "CuraEngineBackend", "Cura.proto"))
        print("!!!!!!!!!!!!! proto file path = ", proto_file_path)
        super()._createSocket(proto_file_path)

    ##  Called when a print time message is received from the engine.
    #
    #   \param message The protobuf message containing the print time per feature and
    #   material amount per extruder
    def _onPrintTimeMaterialEstimates(self, message):
        material_amounts = []
        for index in range(message.repeatedMessageCount("materialEstimates")):
            material_amounts.append(message.getRepeatedMessage("materialEstimates", index).material_amount)

        times = self._parseMessagePrintTimes(message)

    ##  Called for parsing message to retrieve estimated time per feature
    #
    #   \param message The protobuf message containing the print time per feature
    def _parseMessagePrintTimes(self, message):
        result = {
            "inset_0": message.time_inset_0,
            "inset_x": message.time_inset_x,
            "skin": message.time_skin,
            "infill": message.time_infill,
            "support_infill": message.time_support_infill,
            "support_interface": message.time_support_interface,
            "support": message.time_support,
            "skirt": message.time_skirt,
            "travel": message.time_travel,
            "retract": message.time_retract,
            "none": message.time_none
        }
        return result
