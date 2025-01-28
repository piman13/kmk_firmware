from kmk.keys import KC
from kmk.modules import Module
from kmk.utils import Debug
from analogio import AnalogIn
from supervisor import ticks_ms
debug = Debug(__name__)


DEFAULT_FILTER = lambda input, offset: input >> offset
DEFAULT_SENSITIVITY = 1

def noop(*args):
    pass



class AnalogEvent:
    def __init__(self, on_change=noop, on_stop=noop):
        self._on_change = on_change
        self._on_stop = on_stop

    def on_change(self, event, keyboard):
        self._on_change(self, event, keyboard)

    def on_stop(self, event, keyboard):
        self._on_stop(self, event, keyboard)


class AnalogKey(AnalogEvent):
    def __init__(self, key, threshold=127, filter = DEFAULT_FILTER):
        self.key = key
        self.threshold = threshold
        self.pressed = False
        self.filter = filter


    def on_change(self, event, keyboard):
        if event.value >= self.threshold and not self.pressed:
            self.pressed = True
            keyboard.pre_process_key(self.key, True)

        elif event.value < self.threshold and self.pressed:
            self.pressed = False
            keyboard.pre_process_key(self.key, False)

    def on_stop(self, event, keyboard):
        pass


class AnalogInput:
    def __init__(self, input):
        self.value = lambda: input.value
        self.last_value = 0
        self.delta = 0
        self.moving = False
        self.time = ticks_ms()

class EventWrapper:
    def __init__(self, value, delta, timedelta):
        self.value = value
        self.delta = delta
        self.timedelta = timedelta
    


def convert_KC_keys(evtmap, layer_num):
    layer = evtmap[layer_num]
    event_map = []
    for idx_event, event in enumerate(layer):
        if hasattr(event, "on_press"):
            if event == KC.NO:
                event_map.append(AnalogEvent)
            
            elif event == KC.TRANSPARENT or event == KC.TRNS:
                if layer_num > 0:
                    x = layer_num
                    while x >= 0:
                        if not(evtmap[x][idx_event] == KC.TRNS or evtmap[x][idx_event] == KC.TRANSPARENT):
                            event_map_layer.append(evtmap[x][idx_event])#in theory lower layer is done already
                        x -= 1
            else:
                event_map_layer.append(AnalogKey(event))
        else:
            event_map_layer.append(event)
    return event_map_layer


def build_filter_layer(layer):
    for idx, event in enumerate(layer):
        filtermap = []
        if hasattr(event, 'filter'):
            filtermap.append(event.filter)
        else:
            filtermap.append(DEFAULT_FILTER)


def invert_bool_fill(invertmap, filtermap):
    inverted_filters = []
    if invertmap == True:
        for idx, filter in enumerate(filtermap):
            filter_max = filter(65535)
            inverted_filters.append(lambda input: ((~filter(input)) + filter_max))
    else:
        inverted_filters = filtermap
    return inverted_filters

def invert_filters(invertmap, filtermap, layer_num):
    inverted_filters = []
    if type(invertmap) == bool:
        inverted_filters = invert_bool_fill(invertmap, filtermap)
    elif type(invertmap) == list:
        invert_layer = self.invertmap[layer_num]
        if type(invert_layer) == bool:
            inverted_filters = invert_bool_fill(invert_layer, filtermap)
        elif type(invert_layer) == list:
            for idx_invert, invert in enumerate(invert_layer):
                if invert == True:
                    filter = filtermap[idx_invert]
                    filter_max = filter(65535)
                    inverted_filters.append(lambda input: ((~filter(input)) + filter_max))
                else:
                    inverted_filters.append(filtermap[idx_invert])
    return inverted_filters



class AnalogHandler(Module):
    def __init__(self, evtmap, inputs, inputsmap = None, invertmap = None, filtermap = None, sensitivity = None):
        self.evtmap = evtmap
        self.invertmap = invertmap
        self.filtermap = filtermap
        self.sensitivity = sensitivity

        if inputsmap != None: #process the order of the inputs if custom order applied
            inputs_ordered = []
            for idx, input_id in enumerate(inputsmap):
                inputs_ordered.append(self.inputs[input_id])

            if debug.enabled:
                debug("inputs reordered to: ", inputs_ordered)
            self.inputs = inputs_ordered

        ##test for and wrap inputs as needed in
        for idx, input in enumerate(inputs):
            input_array = []
            print(dir(input.__class__.__name__))
            if hasattr(input, 'value'):#found made analoginput
                input_array.append(AnalogInput(input))
            elif input.__class__.__name__ == "Pin":
                input_array.append(AnalogInput(AnalogIn(input)))
                print("pin")
        
        self.inputs = input_array

    def on_runtime_enable(self, keyboard):
        return

    def on_runtime_disable(self, keyboard):
        return

    def during_bootup(self, keyboard):
        filtermap = []
        evtmap = []
        for idx_layer, layer in enumerate(self.evtmap):
            if len(layer) == len(self.inputs):
                evtmap.append(convert_KC_keys(self.evtmap,idx_layer))
                
                if self.filtermap is None:
                    filtermap_layer(build_filter_layer(evtmap[idx_layer]))

                if self.invertmap != None:
                    filtermap.append(invert_filters(self.invertmap, filtermap_layer, idx_layer))
                else:
                    filtermap.append(filtermap_layer)
            else:
                print("failed to load evtmap layer x miss match found")
                break

        self.filtermap = filtermap
        self.evtmap = evtmap
        


    def before_matrix_scan(self, keyboard):
        for idx, input in enumerate(self.inputs):
            keyboard_layer = keyboard.active_layers[0]
            
            if self.sensitivity != None:##add sensitivity filtering to boot :/
                sensitivity = self.sensitivity[keyboard_layer][idx]
            else:
                sensitivity = DEFAULT_SENSITIVITY

            print("MARK 1")

            #print(dir(input))
            
            current_value = input.value()
            last_value = input.last_value
            last_state = input.moving
            
            delta = last_value - current_value

            print("MARK 2")
            
            if delta not in range(-sensitivity, sensitivity + 1):
                input.last_value = current_value #catch slow movements by not updating until delta passed
                input.moving = True
            
            elif (delta in range(-sensitivity, sensitivity + 1) and
                  input.delta not in range(-sensitivity, sensitivity + 1)):
                input.last_value = current_value
                input.moving = False


            print("MARK 3")

            timedelta = (ticks_ms() - input.time)
            input.time = ticks_ms()
            input.delta = delta
            
            if input.moving: #on change
                print("MARK 4")
                event_func = self.evtmap[keyboard_layer][idx]
                event_filter = self.filtermap[keyboard_layer][idx]
                filtered_input = event_filter(current_value)
                filtered_delta = event_filter(last_value) - event_filter(current_value)

                event = EventWrapper(filtered_input, filtered_delta, timedelta)

                event_func.on_change(event, keyboard)
            elif not analog.state and old_state: #on stop
                print("MARK 5")
                event_func = self.evtmap[keyboard_layer][idx]
                event_filter = self.filtermap[keyboard_layer][idx]
                filtered_input = event_filter(current_value)
                filtered_delta = event_filter(delta)

                event = EventWrapper(filtered_input, filtered_delta, timedelta)

                event_func.on_stop(event, keyboard)

            print("MARK 6")
            

    def after_matrix_scan(self, keyboard):
        return

    def before_hid_send(self, keyboard):
        return

    def after_hid_send(self, keyboard):
        return

    def on_powersave_enable(self, keyboard):
        return

    def on_powersave_disable(self, keyboard):
        return
