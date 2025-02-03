from kmk.keys import KC
from kmk.modules import Module
from kmk.utils import Debug
from analogio import AnalogIn
from supervisor import ticks_ms
debug = Debug(__name__)


DEFAULT_FILTER = lambda input: input >> 8
DEFAULT_SENSITIVITY = 256
#DEFAULT_SENSITIVITY = 150 #activates somtimes but not bad
def noop(*args):
    pass



class AnalogEvent:
    def __init__(self, on_change=noop, on_stop=noop, layer_change=noop):
        self._on_change = on_change
        self._on_stop = on_stop
        self._layer_change = layer_change

    def on_change(self, event, keyboard):
        self._on_change(self, event, keyboard)

    def on_stop(self, event, keyboard):
        self._on_stop(self, event, keyboard)

    def layer_change(self, keyboard):
        self._layer_change(self, keyboard)

class AnalogNoop:
    def on_change(*args):
        pass
    def on_stop(*args):
        pass
    def layer_change(*args):
        pass


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

    def layer_change(self, event, keyboard, ingress):
        if ingress:
            self.on_change(event, keyboard)
        else: #egress
            self.pressed = False
            keyboard.pre_process_key(self.key, False)

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
    event_map_layer = []
    for idx_event, event in enumerate(layer):
        if hasattr(event, "on_press"):
            if event == KC.NO:
                event_map_layer.append(AnalogNoop)
            
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
            if isinstance(event, type):
                event_map_layer.append(event())
            else:
                event_map_layer.append(event)
            
    return event_map_layer


def build_filter_layer(layer):
    filtermap = []
    for idx, event in enumerate(layer):
        if hasattr(event, 'filter'):
            filtermap.append(event.filter)
        else:
            filtermap.append(DEFAULT_FILTER)
    return filtermap


def invert_bool_fill(invertmap, filtermap):
    inverted_filters = []
    if invertmap == True:
        for idx, filter in enumerate(filtermap):
            filter_max = filter(65535)
            inverted_filters.append(lambda input: ((~filter(input)) + (filter_max + 1)))
    else:
        inverted_filters = filtermap
    return inverted_filters

def invert_filters(invertmap, filtermap, layer_num):
    inverted_filters = []
    if type(invertmap) == bool:
        inverted_filters = invert_bool_fill(invertmap, filtermap)
    elif type(invertmap) == list:
        invert_layer = invertmap[layer_num]
        if type(invert_layer) == bool:
            inverted_filters = invert_bool_fill(invert_layer, filtermap)
        elif type(invert_layer) == list:
            for idx_invert, invert in enumerate(invert_layer):
                if invert == True:
                    filter = filtermap[idx_invert]
                    filter_max = filter(65535)
                    inverted_filters.append(lambda input: ((~filter(input)) + (filter_max + 1)))
                else:
                    inverted_filters.append(filtermap[idx_invert])
    return inverted_filters



class AnalogHandler(Module):
    def __init__(self, evtmap, inputs, inputsmap = None, invertmap = None, filtermap = None, sensitivity = None):
        self.evtmap = evtmap
        self.invertmap = invertmap
        self.filtermap = filtermap
        self.sensitivity = sensitivity
        self.lastlayer = 0

        inputs_ordered = []
        if inputsmap != None: #process the order of the inputs if custom order applied
            inputs_ordered = []
            for idx, input_id in enumerate(inputsmap):
                inputs_ordered.append(self.inputs[input_id])
            if debug.enabled:
                debug("inputs reordered to: ", inputs_ordered)
        else:
            inputs_ordered = inputs
        
        ##test for and wrap inputs as needed in
        input_array = []
        for idx, input in enumerate(inputs_ordered):    
            if hasattr(input, 'value'):#found made analoginput
                input_array.append(AnalogInput(input))
            elif input.__class__.__name__ == "Pin":
                input_array.append(AnalogInput(AnalogIn(input)))

        self.inputs = input_array

    def on_runtime_enable(self, keyboard):
        return

    def on_runtime_disable(self, keyboard):
        return

    def during_bootup(self, keyboard):
        filtermap = []
        evtmap = self.evtmap
        for idx_layer, layer in enumerate(self.evtmap):
            
            if len(layer) == len(self.inputs):
                evtmap[idx_layer] = (convert_KC_keys(evtmap,idx_layer))
                
                if self.filtermap is None:
                    filtermap_layer = (build_filter_layer(evtmap[idx_layer]))
                else:
                    filtermap_layer = (self.filtermap[idx_layer])


                if self.invertmap != None:
                    print("inverting filters")
                    filtermap.append(invert_filters(self.invertmap, filtermap_layer, idx_layer))
                else:
                    filtermap.append(filtermap_layer)
                    
            else:
                if debug.enabled:
                    debug("failed to load evtmap layer ", idx_layer, "miss match found")
                    
        self.filtermap = filtermap
        self.evtmap = evtmap
        


    def before_matrix_scan(self, keyboard):
        keyboard_layer = keyboard.active_layers[0]
        
        if self.lastlayer != keyboard_layer:
            layer_changed = True
            #print("layer changed")
        else:
            layer_changed = False
        
        for idx, input in enumerate(self.inputs):
            
            if self.sensitivity != None:##add sensitivity filtering to boot :/
                sensitivity = self.sensitivity[keyboard_layer][idx]
            else:
                sensitivity = DEFAULT_SENSITIVITY

            
            current_value = input.value()
            last_value = input.last_value
            last_state = input.moving
            
            delta = last_value - current_value

            if delta not in range(-sensitivity, sensitivity + 1):
                input.last_value = current_value #catch slow movements by not updating until delta passed
                input.moving = True
            
            elif (delta in range(-sensitivity, sensitivity + 1) and
                  input.delta not in range(-sensitivity, sensitivity + 1)):
                input.last_value = current_value
                input.moving = False


            timedelta = (ticks_ms() - input.time)
            input.time = ticks_ms()
            input.delta = delta



            if layer_changed:
                event_func = self.evtmap[self.lastlayer][idx]
                event_filter = self.filtermap[self.lastlayer][idx]
                filtered_input = event_filter(current_value)
                filtered_delta = event_filter(last_value) - event_filter(current_value)
                event = EventWrapper(filtered_input, filtered_delta, timedelta)
                try:
                    event_func.layer_change(event, keyboard, False)
                except Exception as e:
                    if debug.enabled:
                        debug("idx", idx, "layer_change ingress: ", e)

            if input.moving or last_state or layer_changed:
                event_func = self.evtmap[keyboard_layer][idx]
                event_filter = self.filtermap[keyboard_layer][idx]
                filtered_input = event_filter(current_value)
                filtered_delta = event_filter(last_value) - event_filter(current_value)
                event = EventWrapper(filtered_input, filtered_delta, timedelta)

                if input.moving: #on change
                    try:
                        event_func.on_change(event, keyboard)
                    except Exception as e:
                        if debug.enabled:
                            debug("on_change: ", e)
                elif not input.moving and last_state: #on stop
                    try:
                        event_func.on_stop(event, keyboard)
                    except Exception as e:
                        if debug.enabled:
                            debug("on_stop: ", e)
                elif layer_changed:
                    try:
                        event_func.layer_change(event, keyboard, True)
                    except Exception as e:
                        if debug.enabled:
                            debug("idx", idx, "layer_change egress:", e)
            

        self.lastlayer = keyboard_layer

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
