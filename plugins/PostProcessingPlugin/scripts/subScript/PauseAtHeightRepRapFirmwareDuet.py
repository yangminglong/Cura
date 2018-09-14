
class PauseAtHeightRepRapFirmwareDuet():

    @staticmethod
    def execute(data, parent_script):
        current_z = 0.
        pause_z = parent_script.getSettingValueByKey("pause_height")

        layers_started = False
        for layer_number, layer in enumerate(data):
            lines = layer.split("\n")
            for line in lines:
                if ";LAYER:0" in line:
                    layers_started = True
                    continue

                if not layers_started:
                    continue

                if parent_script.getValue(line, 'G') == 1 or parent_script.getValue(line, 'G') == 0:
                    current_z = parent_script.getValue(line, 'Z')
                    if current_z != None:
                        if current_z >= pause_z:
                            prepend_gcode = ";TYPE:CUSTOM\n"
                            prepend_gcode += "; -- Pause at height (%.2f mm) --\n" % pause_z
                            prepend_gcode += parent_script.putValue(M = 226) + "\n"
                            layer = prepend_gcode + layer

                            data[layer_number] = layer # Override the data of this layer with the modified data
                            return data
                        break
        return data
