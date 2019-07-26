# Copyright (c) 2018 Ultimaker B.V.
# Cura is released under the terms of the LGPLv3 or higher.

from typing import Optional, Dict, cast, Any, Tuple

from .ContainerNode import ContainerNode
from .QualityChangesGroup import QualityChangesGroup

from cura.Machines.QualityGroup import DEFAULT_INTENT_CATEGORY

#
# QualityNode is used for BOTH quality and quality_changes containers.
#
class QualityNode(ContainerNode):

    def __init__(self, metadata: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(metadata = metadata)
        self.quality_type_map = {}  # type: Dict[str, QualityNode] # {kind}_type -> QualityNode for InstanceContainer

    def getChildNode(self, child_key: str) -> Optional["QualityNode"]:
        return self.children_map.get(child_key)

    def addQualityMetadata(self, quality_type: str, metadata: Dict[str, Any]):
        if quality_type not in self.quality_type_map:
            self.quality_type_map[quality_type] = QualityNode(metadata)

    def addIntentMetadata(self, quality_type: str, intent_category: str, metadata: Dict[str, Any]):
        if intent_category == DEFAULT_INTENT_CATEGORY:
            self.addQualityMetadata(quality_type, metadata)
            return

        if quality_type not in self.quality_type_map:
            self.quality_type_map[quality_type] = QualityNode()
        quality_type_node = self.quality_type_map[quality_type]

        if intent_category not in quality_type_node.quality_type_map:
            quality_type_node.quality_type_map[intent_category] = QualityNode(metadata)

    def getQualityNode(self, kind_id_name: str) -> Optional["QualityNode"]:
        return self.quality_type_map.get(kind_id_name)

    def addQualityChangesMetadata(self, quality_type: str, intent_category: str, metadata: Dict[str, Any]):
        if quality_type not in self.quality_type_map:
            self.quality_type_map[quality_type] = QualityNode()
        quality_node = self.quality_type_map[quality_type]
        if intent_category == DEFAULT_INTENT_CATEGORY:
            intent_node = quality_node
        else:
            if intent_category not in quality_node.quality_type_map:
                quality_node.quality_type_map[intent_category] = QualityNode()
            intent_node = self.quality_type_map[intent_category]

        name = metadata["name"]
        if name not in intent_node.children_map:
            intent_node.children_map[name] = QualityChangesGroup(name, (intent_category, quality_type))
        quality_changes_group = intent_node.children_map[name]
        cast(QualityChangesGroup, quality_changes_group).addNode(QualityNode(metadata))
