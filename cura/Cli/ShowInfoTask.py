import sys
from typing import TYPE_CHECKING

from cura.Machines.VariantManager import VariantType

if TYPE_CHECKING:
    from UM.Application import Application


class ShowInfoTask:

    def __init__(self, application: "Application",
                 show_all_machine_ids: bool = False,
                 show_all_configurations_for_machine_id: str = "") -> None:
        self._application = application

        self.show_all_machine_ids = show_all_machine_ids
        self.show_all_configurations_for_machine_id = show_all_configurations_for_machine_id

    def start(self) -> None:
        if self.show_all_machine_ids:
            self._showAllMachineIds()
        elif self.show_all_configurations_for_machine_id:
            self._showAllConfigurationsForMachineID(self.show_all_configurations_for_machine_id)

    def _showAllMachineIds(self) -> None:
        machine_manager = self._application.getMachineManager()
        machine_type_list = machine_manager.getAllMachineTypes()
        machine_type_list = sorted(machine_type_list)

        for machine_type in machine_type_list:
            print("[machine_type] %s" % machine_type)

    def _showAllConfigurationsForMachineID(self, machine_id: str) -> None:
        machine_manager = self._application.getMachineManager()
        all_machine_type_list = machine_manager.getAllMachineTypes()
        if machine_id not in all_machine_type_list:
            print("Machine ID [%s] is not available." % machine_id)
            sys.exit(1)

        machine_manager.createMachine("tmp", machine_id)
        machine = machine_manager.getMachine("tmp")
        machine_manager._active_machine = machine

        variant_manager = self._application.getVariantManager()
        material_manager = self._application.getMaterialManager()
        quality_manager = self._application.getQualityManager()

        all_variant_node_dict = variant_manager.getVariantNodes(machine.global_stack, VariantType.NOZZLE)
        all_material_id_list = material_manager.getAvailableMaterialIdsForMachine(machine.global_stack)

        for varaint_name in sorted(all_variant_node_dict):
            print("[variant] %s" % varaint_name)
        for material_id in sorted(all_material_id_list):
            print("[material] %s" % material_id)
        #for quality_type in sorted(all_quality_type_list):
        #    print("[quality_type] %s" % quality_type)
