
class PauseAtHeightforRepetier():

    @staticmethod
    def execute(data, parent_script):
        x = 0.
        y = 0.
        current_z = 0.
        pause_z = parent_script.getSettingValueByKey("pause_height")
        retraction_amount = parent_script.getSettingValueByKey("retraction_amount")
        extrude_amount = parent_script.getSettingValueByKey("extrude_amount")
        park_x = parent_script.getSettingValueByKey("head_park_x")
        park_y = parent_script.getSettingValueByKey("head_park_y")
        move_Z = parent_script.getSettingValueByKey("head_move_Z")
        layers_started = False
        redo_layers = parent_script.getSettingValueByKey("redo_layers")
        for layer in data:
            lines = layer.split("\n")
            for line in lines:
                if ";LAYER:0" in line:
                    layers_started = True
                    continue

                if not layers_started:
                    continue

                if parent_script.getValue(line, 'G') == 1 or parent_script.getValue(line, 'G') == 0:
                    current_z = parent_script.getValue(line, 'Z')
                    x = parent_script.getValue(line, 'X', x)
                    y = parent_script.getValue(line, 'Y', y)
                    if current_z != None:
                        if current_z >= pause_z:

                            index = data.index(layer)
                            prevLayer = data[index-1]
                            prevLines = prevLayer.split("\n")
                            current_e = 0.
                            for prevLine in reversed(prevLines):
                                current_e = parent_script.getValue(prevLine, 'E', -1)
                                if current_e >= 0:
                                    break

                            prepend_gcode = ";TYPE:CUSTOM\n"
                            prepend_gcode += ";added code by post processing\n"
                            prepend_gcode += ";script: PauseAtHeightforRepetier.py\n"
                            prepend_gcode += ";current z: %f \n" % (current_z)
                            prepend_gcode += ";current X: %f \n" % (x)
                            prepend_gcode += ";current Y: %f \n" % (y)

                            #Retraction
                            prepend_gcode += "M83\n"
                            if retraction_amount != 0:
                                prepend_gcode += "G1 E-%f F6000\n" % (retraction_amount)

                            #Move the head away
                            prepend_gcode += "G1 Z%f F300\n" % (1 + current_z)
                            prepend_gcode += "G1 X%f Y%f F9000\n" % (park_x, park_y)
                            if current_z < move_Z:
                                prepend_gcode += "G1 Z%f F300\n" % (current_z + move_Z)

                            #Disable the E steppers
                            prepend_gcode += "M84 E0\n"
                            #Wait till the user continues printing
                            prepend_gcode += "@pause now change filament and press continue printing ;Do the actual pause\n"

                            #Push the filament back,
                            if retraction_amount != 0:
                                prepend_gcode += "G1 E%f F6000\n" % (retraction_amount)

                            # Optionally extrude material
                            if extrude_amount != 0:
                                prepend_gcode += "G1 E%f F200\n" % (extrude_amount)
                                prepend_gcode += "@info wait for cleaning nozzle from previous filament\n"
                                prepend_gcode += "@pause  remove the waste filament from parking area and press continue printing\n"

                            # and retract again, the properly primes the nozzle when changing filament.
                            if retraction_amount != 0:
                                prepend_gcode += "G1 E-%f F6000\n" % (retraction_amount)

                            #Move the head back
                            prepend_gcode += "G1 Z%f F300\n" % (1 + current_z)
                            prepend_gcode +="G1 X%f Y%f F9000\n" % (x, y)
                            if retraction_amount != 0:
                                prepend_gcode +="G1 E%f F6000\n" % (retraction_amount)
                            prepend_gcode +="G1 F9000\n"
                            prepend_gcode +="M82\n"

                            # reset extrude value to pre pause value
                            prepend_gcode +="G92 E%f\n" % (current_e)

                            layer = prepend_gcode + layer

                            # include a number of previous layers
                            for i in range(1, redo_layers + 1):
                                prevLayer = data[index-i]
                                layer = prevLayer + layer

                            data[index] = layer #Override the data of this layer with the modified data
                            return data
                        break
        return data
