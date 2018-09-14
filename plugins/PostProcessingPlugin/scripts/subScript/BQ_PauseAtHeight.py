
class BQ_PauseAtHeight():

    @staticmethod
    def execute(data, parent_script):
        x = 0.
        y = 0.
        current_z = 0.
        pause_z = parent_script.getSettingValueByKey("pause_height")
        for layer in data: 
            lines = layer.split("\n")
            for line in lines:
                if parent_script.getValue(line, 'G') == 1 or parent_script.getValue(line, 'G') == 0:
                    current_z = parent_script.getValue(line, 'Z')
                    if current_z != None:
                        if current_z >= pause_z:
                            prepend_gcode = ";TYPE:CUSTOM\n"
                            prepend_gcode += "; -- Pause at height (%.2f mm) --\n" % pause_z

                            # Insert Pause gcode
                            prepend_gcode += "M25        ; Pauses the print and waits for the user to resume it\n"
                            
                            index = data.index(layer) 
                            layer = prepend_gcode + layer
                            data[index] = layer # Override the data of this layer with the modified data
                            return data
                        break
        return data
