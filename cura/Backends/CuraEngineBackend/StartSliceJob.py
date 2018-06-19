# Copyright (c) 2017 Ultimaker B.V.
# Cura is released under the terms of the LGPLv3 or higher.

from enum import IntEnum
import re
from string import Formatter
import time
from typing import TYPE_CHECKING

import numpy

from UM.Logging.Logger import Logger
from UM.Scene.Iterator.DepthFirstIterator import DepthFirstIterator
from UM.Settings.Validator import ValidatorState
from UM.Settings.SettingRelation import RelationType

from cura.Scene.CuraSceneNode import CuraSceneNode
from cura.OneAtATimeIterator import OneAtATimeIterator

if TYPE_CHECKING:
    from cura.Machines.Machine import Machine


NON_PRINTING_MESH_SETTINGS = ["anti_overhang_mesh", "infill_mesh", "cutting_mesh"]


class StartJobResult(IntEnum):
    Finished = 1
    Error = 2
    SettingError = 3
    NothingToSlice = 4
    MaterialIncompatible = 5
    BuildPlateError = 6
    ObjectSettingError = 7 #When an error occurs in per-object settings.
    ObjectsWithDisabledExtruder = 8


##  Formatter class that handles token expansion in start/end gcod
class GcodeStartEndFormatter(Formatter):
    def get_value(self, key, args, kwargs):  # [CodeStyle: get_value is an overridden function from the Formatter class]
        # The kwargs dictionary contains a dictionary for each stack (with a string of the extruder_nr as their key),
        # and a default_extruder_nr to use when no extruder_nr is specified

        if isinstance(key, str):
            try:
                extruder_nr = kwargs["default_extruder_nr"]
            except ValueError:
                extruder_nr = -1

            key_fragments = [fragment.strip() for fragment in key.split(',')]
            if len(key_fragments) == 2:
                try:
                    extruder_nr = int(key_fragments[1])
                except ValueError:
                    try:
                        extruder_nr = int(kwargs["-1"][key_fragments[1]]) # get extruder_nr values from the global stack
                    except (KeyError, ValueError):
                        # either the key does not exist, or the value is not an int
                        Logger.log("w", "Unable to determine stack nr '%s' for key '%s' in start/end g-code, using global stack", key_fragments[1], key_fragments[0])
            elif len(key_fragments) != 1:
                Logger.log("w", "Incorrectly formatted placeholder '%s' in start/end g-code", key)
                return "{" + str(key) + "}"

            key = key_fragments[0]
            try:
                return kwargs[str(extruder_nr)][key]
            except KeyError:
                Logger.log("w", "Unable to replace '%s' placeholder in start/end g-code", key)
                return "{" + key + "}"
        else:
            Logger.log("w", "Incorrectly formatted placeholder '%s' in start/end g-code", key)
            return "{" + str(key) + "}"


class StartSliceJob:
    def __init__(self, application, slice_message):
        super().__init__()

        self._application = application
        self._scene = self._application.getController().getScene()

        self._slice_message = slice_message
        self._all_extruders_settings = None

        self._settings_dict = {"extruders": dict(),
                               }

    def getSliceMessage(self):
        return self._slice_message

    def _checkStackForErrors(self, stack):
        if stack is None:
            return False

        for key in stack.getAllKeys():
            validation_state = stack.getProperty(key, "validationState")
            if validation_state in (ValidatorState.Exception, ValidatorState.MaximumError, ValidatorState.MinimumError):
                Logger.log("w", "Setting %s is not valid, but %s. Aborting slicing.", key, validation_state)
                return True
        return False

    def has_objects_associated_with_disable_extruder(self, machine: "Machine", object_list: list) -> bool:
        """
        Checks if there are objects associated with disabled extruders with the given machine and object list.
        """
        extruders_enabled = machine.getEnabledExtruders()
        has_model_with_disabled_extruders = False
        for group in object_list:
            for node in group:
                extruder_position = node.callDecoration("getActiveExtruderPosition")
                if extruder_position not in extruders_enabled:
                    has_model_with_disabled_extruders = True
                    break
            if has_model_with_disabled_extruders:
                break
        return has_model_with_disabled_extruders

    ##  Runs the job that initiates the slicing.
    def run(self):
        active_machine = self._application.getMachineManager().getActiveMachine()
        if not active_machine:
            Logger.log("i", "No active machine, cannot slice")
            return False

        # Check the machine and its settings
        if not active_machine.isHardwareCompatible:
            Logger.log("i", "machine %s has hardware incompatible settings.", active_machine)
            return False
        if active_machine.checkHaveErrors():
            Logger.log("i", "machine %s has invalid settings.", active_machine)
            return False

        # Check build volume
        if self._application.getBuildVolume().hasErrors():
            return

        # Don't slice if there is a per object setting with an error value.
        for node in DepthFirstIterator(self._scene.getRoot()):
            if not isinstance(node, CuraSceneNode) or not node.isSelectable():
                continue

            if self._checkStackForErrors(node.callDecoration("getStack")):
                return

        # Remove old layer data.
        for node in DepthFirstIterator(self._scene.getRoot()):
            if node.callDecoration("getLayerData"):
                node.getParent().removeChild(node)
                break

        # Get the objects in their groups to print.
        object_groups = []
        if active_machine.global_stack.getProperty("print_sequence", "value") == "one_at_a_time":
            for node in OneAtATimeIterator(self._scene.getRoot()):
                temp_list = []

                # Node can't be printed, so don't bother sending it.
                if getattr(node, "_outside_buildarea", False):
                    continue

                children = node.getAllChildren()
                children.append(node)
                for child_node in children:
                    if child_node.getMeshData() and child_node.getMeshData().getVertices() is not None:
                        temp_list.append(child_node)

                if temp_list:
                    object_groups.append(temp_list)
            if len(object_groups) == 0:
                Logger.log("w", "No objects suitable for one at a time found, or no correct order found")
        else:
            temp_list = []
            has_printing_mesh = False
            for node in DepthFirstIterator(self._scene.getRoot()):
                if node.callDecoration("isSliceable") and node.getMeshData() and node.getMeshData().getVertices() is not None:
                    per_object_stack = node.callDecoration("getStack")
                    is_non_printing_mesh = False
                    if per_object_stack:
                        is_non_printing_mesh = any(per_object_stack.getProperty(key, "value") for key in NON_PRINTING_MESH_SETTINGS)

                    # Find a reason not to add the node
                    if getattr(node, "_outside_buildarea", False) and not is_non_printing_mesh:
                        continue

                    temp_list.append(node)
                    if not is_non_printing_mesh:
                        has_printing_mesh = True

            #If the list doesn't have any model with suitable settings then clean the list
            # otherwise CuraEngineBackend will crash
            if not has_printing_mesh:
                temp_list.clear()

            if temp_list:
                object_groups.append(temp_list)

        if self.has_objects_associated_with_disable_extruder(active_machine, object_groups):
            return False

        # All checks are done, create setting messages

        self._buildGlobalSettingsMessage(active_machine.global_stack)
        self._buildGlobalInheritsStackMessage(active_machine.global_stack)

        # Build messages for extruder stacks
        for extruder_stack in active_machine.global_stack.extruders.values():
            self._buildExtruderMessage(active_machine.global_stack, extruder_stack)

        for group in object_groups:
            group_message = self._slice_message.addRepeatedMessage("object_lists")
            if group[0].getParent() is not None and group[0].getParent().callDecoration("isGroup"):
                self._handlePerObjectSettings(group[0].getParent(), group_message)
            for object in group:
                mesh_data = object.getMeshData()
                rot_scale = object.getWorldTransformation().getTransposed().getData()[0:3, 0:3]
                translate = object.getWorldTransformation().getData()[:3, 3]

                # This effectively performs a limited form of MeshData.getTransformed that ignores normals.
                verts = mesh_data.getVertices()
                verts = verts.dot(rot_scale)
                verts += translate

                # Convert from Y up axes to Z up axes. Equals a 90 degree rotation.
                verts[:, [1, 2]] = verts[:, [2, 1]]
                verts[:, 1] *= -1

                obj = group_message.addRepeatedMessage("objects")
                obj.id = id(object)

                indices = mesh_data.getIndices()
                if indices is not None:
                    flat_verts = numpy.take(verts, indices.flatten(), axis=0)
                else:
                    flat_verts = numpy.array(verts)

                obj.vertices = flat_verts

                self._handlePerObjectSettings(object, obj)
        return True

    ##  Creates a dictionary of tokens to replace in g-code pieces.
    #
    #   This indicates what should be replaced in the start and end g-codes.
    #   \param stack The stack to get the settings from to replace the tokens
    #   with.
    #   \return A dictionary of replacement tokens to the values they should be
    #   replaced with.
    def _buildReplacementTokens(self, global_stack) -> dict:
        result = {}
        for key in global_stack.getAllKeys():
            value = global_stack.getProperty(key, "value")
            result[key] = value

        result["print_bed_temperature"] = result["material_bed_temperature"] # Renamed settings.
        result["print_temperature"] = result["material_print_temperature"]
        result["time"] = time.strftime("%H:%M:%S") #Some extra settings.
        result["date"] = time.strftime("%d-%m-%Y")
        result["day"] = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"][int(time.strftime("%w"))]

        initial_extruder_stack = self._application.getMachineManager().getUsedExtruderStacks()[0]
        initial_extruder_nr = initial_extruder_stack.getProperty("extruder_nr", "value")
        result["initial_extruder_nr"] = initial_extruder_nr

        return result

    ##  Replace setting tokens in a piece of g-code.
    #   \param value A piece of g-code to replace tokens in.
    #   \param default_extruder_nr Stack nr to use when no stack nr is specified, defaults to the global stack
    def _expandGcodeTokens(self, global_stack, value: str, default_extruder_nr: int = -1):
        if not self._all_extruders_settings:
            # NB: keys must be strings for the string formatter
            self._all_extruders_settings = {
                "-1": self._buildReplacementTokens(global_stack)
            }

            for extruder_stack in global_stack.extruders.values():
                extruder_nr = extruder_stack.getProperty("extruder_nr", "value")
                self._all_extruders_settings[str(extruder_nr)] = self._buildReplacementTokens(extruder_stack)

        try:
            # any setting can be used as a token
            fmt = GcodeStartEndFormatter()
            settings = self._all_extruders_settings.copy()
            settings["default_extruder_nr"] = default_extruder_nr
            return str(fmt.format(value, **settings))
        except:
            Logger.logException("w", "Unable to do token replacement on start/end g-code")
            return str(value)

    ##  Create extruder message from stack
    def _buildExtruderMessage(self, global_stack, extruder_stack):
        message = self._slice_message.addRepeatedMessage("extruders")
        message.id = int(extruder_stack.getMetaDataEntry("position"))

        settings = self._buildReplacementTokens(extruder_stack)

        # Also send the material GUID. This is a setting in fdmprinter, but we have no interface for it.
        settings["material_guid"] = extruder_stack.material.getMetaDataEntry("GUID", "")

        # Replace the setting tokens in start and end g-code.
        extruder_nr = extruder_stack.getProperty("extruder_nr", "value")
        settings["machine_extruder_start_code"] = self._expandGcodeTokens(global_stack, settings["machine_extruder_start_code"], extruder_nr)
        settings["machine_extruder_end_code"] = self._expandGcodeTokens(global_stack, settings["machine_extruder_end_code"], extruder_nr)

        position = str(extruder_stack.getMetaDataEntry("position"))
        self._settings_dict["extruders"][position] = dict()
        settings_dict = self._settings_dict["extruders"][position]

        settings_dict["enabled"] = extruder_stack.isEnabled()
        settings_dict["variant_name"] = extruder_stack.variant.getName()
        settings_dict["material"] = extruder_stack.material.getMetaDataEntry("base_file")
        settings_dict["settings"] = dict()

        for key, value in settings.items():
            # Do not send settings that are not settable_per_extruder.
            if not extruder_stack.getProperty(key, "settable_per_extruder"):
                continue
            setting = message.getMessage("settings").addRepeatedMessage("settings")
            setting.name = key
            setting.value = str(value).encode("utf-8")

            settings_dict["settings"][key] = {"value": str(value)}
            if extruder_stack.hasProperty(key, "limit_to_extruder"):
                settings_dict["settings"][key]["limit_to_extruder"] = str(extruder_stack.getProperty(key, "limit_to_extruder"))

    ##  Sends all global settings to the engine.
    #
    #   The settings are taken from the global stack. This does not include any
    #   per-extruder settings or per-object settings.
    def _buildGlobalSettingsMessage(self, global_stack):
        settings = self._buildReplacementTokens(global_stack)

        # Pre-compute material material_bed_temp_prepend and material_print_temp_prepend
        start_gcode = settings["machine_start_gcode"]
        bed_temperature_settings = ["material_bed_temperature", "material_bed_temperature_layer_0"]
        pattern = r"\{(%s)(,\s?\w+)?\}" % "|".join(bed_temperature_settings) # match {setting} as well as {setting, extruder_nr}
        settings["material_bed_temp_prepend"] = re.search(pattern, start_gcode) is None
        print_temperature_settings = ["material_print_temperature", "material_print_temperature_layer_0", "default_material_print_temperature", "material_initial_print_temperature", "material_final_print_temperature", "material_standby_temperature"]
        pattern = r"\{(%s)(,\s?\w+)?\}" % "|".join(print_temperature_settings) # match {setting} as well as {setting, extruder_nr}
        settings["material_print_temp_prepend"] = re.search(pattern, start_gcode) is None

        # Replace the setting tokens in start and end g-code.
        # Use values from the first used extruder by default so we get the expected temperatures
        initial_extruder_stack = self._application.getMachineManager().getUsedExtruderStacks()[0]
        initial_extruder_nr = initial_extruder_stack.getProperty("extruder_nr", "value")

        settings["machine_start_gcode"] = self._expandGcodeTokens(global_stack, settings["machine_start_gcode"], initial_extruder_nr)
        settings["machine_end_gcode"] = self._expandGcodeTokens(global_stack, settings["machine_end_gcode"], initial_extruder_nr)

        self._settings_dict["machine_type"] = global_stack.definition.getId()
        self._settings_dict["quality_type"] = global_stack.quality.getMetaDataEntry("quality_type")
        self._settings_dict["settings"] = dict()

        # Add all sub-messages for each individual setting.
        for key, value in settings.items():
            setting_message = self._slice_message.getMessage("global_settings").addRepeatedMessage("settings")
            setting_message.name = key
            setting_message.value = str(value).encode("utf-8")

            self._settings_dict["settings"][key] = {"value": str(value)}
            if global_stack.hasProperty(key, "limit_to_extruder"):
                self._settings_dict["settings"][key]["limit_to_extruder"] = str(global_stack.getProperty(key, "limit_to_extruder"))

    ##  Sends for some settings which extruder they should fallback to if not
    #   set.
    #
    #   This is only set for settings that have the limit_to_extruder
    #   property.
    #
    #   \param stack The global stack with all settings, from which to read the
    #   limit_to_extruder property.
    def _buildGlobalInheritsStackMessage(self, stack):
        for key in stack.getAllKeys():
            extruder_position = int(round(float(stack.getProperty(key, "limit_to_extruder"))))
            if extruder_position >= 0:  # Set to a specific extruder.
                setting_extruder = self._slice_message.addRepeatedMessage("limit_to_extruder")
                setting_extruder.name = key
                setting_extruder.extruder = extruder_position

    ##  Check if a node has per object settings and ensure that they are set correctly in the message
    #   \param node \type{SceneNode} Node to check.
    #   \param message object_lists message to put the per object settings in
    def _handlePerObjectSettings(self, node, message):
        stack = node.callDecoration("getStack")

        # Check if the node has a stack attached to it and the stack has any settings in the top container.
        if not stack:
            return

        # Check all settings for relations, so we can also calculate the correct values for dependent settings.
        top_of_stack = stack.getTop()  # Cache for efficiency.
        changed_setting_keys = set(top_of_stack.getAllKeys())

        # Add all relations to changed settings as well.
        for key in top_of_stack.getAllKeys():
            instance = top_of_stack.getInstance(key)
            self._addRelations(changed_setting_keys, instance.definition.relations)

        # Ensure that the engine is aware what the build extruder is.
        if stack.getProperty("machine_extruder_count", "value") > 1:
            changed_setting_keys.add("extruder_nr")

        # Get values for all changed settings
        for key in changed_setting_keys:
            setting = message.addRepeatedMessage("settings")
            setting.name = key
            extruder = int(round(float(stack.getProperty(key, "limit_to_extruder"))))

            # Check if limited to a specific extruder, but not overridden by per-object settings.
            if extruder >= 0 and key not in changed_setting_keys:
                limited_stack = self._application.getMachineManager().getActiveMachine().global_stack.extruders["0"]
            else:
                limited_stack = stack

            setting.value = str(limited_stack.getProperty(key, "value")).encode("utf-8")

    ##  Recursive function to put all settings that require each other for value changes in a list
    #   \param relations_set \type{set} Set of keys (strings) of settings that are influenced
    #   \param relations list of relation objects that need to be checked.
    def _addRelations(self, relations_set, relations):
        for relation in filter(lambda r: r.role == "value" or r.role == "limit_to_extruder", relations):
            if relation.type == RelationType.RequiresTarget:
                continue

            relations_set.add(relation.target.key)
            self._addRelations(relations_set, relation.target.relations)
