# Copyright (c) 2019 Ultimaker B.V.
# Cura is released under the terms of the LGPLv3 or higher.

from .src import DiscoverMachineAction
from .src import UltimakerOutputDevicePlugin

# TODO: What is this?
def getMetaData():
    return {}

# TODO: Why are these here?
def register(app):
    return {
        "output_device": UltimakerOutputDevicePlugin.UltimakerOutputDevicePlugin()
        "machine_action": DiscoverMachineAction.DiscoverMachineAction()
    }
