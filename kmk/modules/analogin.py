from kmk.keys import KC
from kmk.modules import Module
from kmk.utils import Debug
from supervisor import ticks_ms
from analogio import AnalogIn

debug = Debug(__name__)


DEFAULT_FILTER = [
    lambda input, offset: input >> offset,
    lambda input, offset: ~(input >> offset) + (65536 >> offset)
]


VEL_MAX_TIME = 100 #this might fall behind with more scans (aim to make scans take less time) default


#thinking notes for mux
#muxing uses dio pins for ch select. while if you have multiple muxers they should all use the same ch select
#some might not follow this. the option should be provided to map seperate pins for each adc
#while there should not be a max to the number of channels there might be a true scanning max before delay holds
#other systems to fault (not sure if this could be threaded or if kmk uses threding to help but if you need
#32 switches on per adc you have a big board or... a big midi pad...)

#notes for midi https://www.youtube.com/watch?v=2BccxWkUgaU
#ya it don't belong in here but whatever

def noop(*args):
    pass


## invert the filter by changing the outputed value to a negitive then adding back to positive
## and getting max val from the filter so even very custom filters can work
def eval_filter(filter):
    filter_max = filter(65535) + 1 #eval filter max to not run every time
    filter_inverted = lambda input: ((~filter(input)) + filter_max)
    return filter_inverted, filter_max



#class to provide on_change and on_stop if not
#found diverts to noop
class AnalogEvent:
    def __init__(self, on_change=noop, on_stop=noop):
        self._on_change = on_change
        self._on_stop = on_stop

    def on_change(self, event, keyboard):
        self._on_change(self, event, keyboard)

    def on_stop(self, event, keyboard):
        self._on_stop(self, event, keyboard)


class AnalogNoop(AnalogEvent):
    def on_change(*args):
        pass
    def on_stop(*args):
        pass

#simple adjustable key
#possable upgrade could be to have a velocity
#to deside multiple functions depending on speed of press?
class AnalogKey(AnalogEvent):
    def __init__(self, key, threshold=127):
        self.key = key
        self.threshold = threshold
        self.pressed = False

    #the threshold is setup so 0 is at the top of switch
    #this is mainly to match the normal bool state of switches
    #with 0 being off and 1 being being pressed 
    def on_change(self, keyboard, analog):
        debug(analog.value)
        if analog.value >= self.threshold and not self.pressed:
            self.pressed = True
            keyboard.pre_process_key(self.key, True)

        elif analog.value < self.threshold and self.pressed:
            self.pressed = False
            keyboard.pre_process_key(self.key, False)

    def on_stop(self, event, keyboard):
        pass





#AnalogInput only handles the updating of the input
#and gets it filters from elseware to allow for on the fly layer swaping
#as well as not storeing to much big or duped info in many places
class AnalogInput(AnalogEvent):
    def __init__(self, input):
        self.input = lambda: input.value
        self.value = 0
        self.delta = 0
        self.state = False
        self.time = ticks_ms()

    #calculate velocity upon call, this is kept serpate
    #so as to not waste time with an unnecessary calc unless needed
    #other expressions that could be common usecases could be added
    #in a simalar vein to this however I can't think of anything that a
    #external function could not do on it's own with the info provided
    #VEL_MAX_TIME might need to be calibraded per keyboard config
    #this mainly depends on the micro-controler and loaded modules
    #more testing needed
    @property ## NEEDS REWORK FOR NEW STORAGE OF VALS
    def velocity(self):
        #this exprestion should allow for velocity to be from
        #0 to the max val of the filter (then we clamp it)
        #this should give a good representation of the velocity
        #but scaled to somthing that would be more useful to a function
        velocity = min(
            max(0,
                int(
                    self.delta / (ticks_ms() - self.time)* self.filtermax / VEL_MAX_TIME
                    )
                ),
            self.filtermax
            )
        return velocity


    #does what it says on the tin and updates the state of
    #value. time, delta, state
    #time is not used in this but it is used in velocity and
    #could be used in other functions (not sure for what but it's there)
    def update_state(self, filter, sensitivity):
        value = filter(self.input())
        delta = value - self.value

        #randomly takes ~27ms (likely due to the garbage colector or other threads)
        if delta not in range(-sensitivity, sensitivity + 1):
            self.value = value #catch slow movements by not updating until delta passed
            self.state = True
            
            
        elif (delta in range(-sensitivity, sensitivity + 1) and
              self.delta not in range(-sensitivity, sensitivity + 1)):
            self.value = value
            self.state = False
        
        
        self.delta = delta
        self.time = ticks_ms()


    #WIP
class MuxedAnlogInput:
     def __init__(self,idx):
         print("tmp")

#looks like a jumble :/
#but a lot of it is safety testing for later and
#to run with less checks in main
def AnalogHandlerEvtMaping(self):
    event_map = [] #fix maping of KC keys in evtmap
    for layer_x, layer in enumerate(self.evtmap):
        event_map_layer = []
        for idx, event in enumerate(layer):
            if hasattr(event, "on_press"):
                if event == KC.NO:
                    event_map_layer.append(AnalogNoop)
                elif event == KC.TRANSPARENT or event == KC.TRNS:
                    if layer_x > 0:
                        x = layer_x
                        while x >= 0:
                            if not(self.evtmap[x][idx] == KC.TRNS or self.evtmap[x][idx] == KC.TRANSPARENT):
                                event_map_layer.append(AnalogKey(self.evtmap[x][idx]))
                            x -= 1
                else:
                    event_map_layer.append(AnalogKey(event))
            else:
                print("saving event")
                event_map_layer.append(event)
        event_map.append(event_map_layer)

    print(event_map)
    for layer_x, layer in enumerate(event_map):
        for idx, event in enumerate(layer):
            if event == None:
                event_map[layer_x][idx] = AnalogNoop
            

    self.evtmap = event_map
    sensitivity_map = [[]]
    #fill out filtermap and sensitivity map if not provided
    if self.filtermap == [[]]:
        if debug.enabled:
            debug("filtermap not filled")
        filter_map = []
        sensitivity_map = []
        if len(self.evtmap) > 0:
            for layer_x, layer in enumerate(self.evtmap):
                filtermap_layer = []
                sensitivity_layer = []
                for idx, event in enumerate(layer):
                    if hasattr(event, 'properties'):
                        filtermap_layer.append(event.properties.filter)
                        sensitivity_layer.append(event.properties.sensitivity)
                    else:
                        if debug.enabled:
                            debug("class with no properties found defaulting to base filter")
                        filtermap_layer.append(8)
                        sensitivity_layer.append(1)
                        
                filter_map.append(filtermap_layer)
                sensitivity_map.append(sensitivity_layer)
                
            self.filtermap = filter_map
            
    if self.sensitivitymap == [[]]:
        self.sensitivitymap = sensitivity_map
    else:
        self.sensitivitymap = [[]]
    
#Main interface for the user 
#arrays like filtermap, invertmap, and sensitivitymap auto fill if they only have one entry
#I don't like how big invert map could be for what it is so perhaps it could be a true bitmap
#but I also need to add perlayer functionaltiy to the 3 maps and AnalogInput so perhaps it
#might be worth it.
#I broke out the state var so it could be used as an event trigger to allow for
#the rest of kmk to run mor async but don't know how best to do this efficiently or
#within the kmk scope
#biggest problem is duplicated information that is only used once in the handler
#not sure what the best way to deal with this is other than passing it from handler live
#that could work for anything that needs layermaping I guess but I also don't want the user to
#have to make masive arrays just to use invert differently on one layer
#perhaps a more complex parcer is needed during bootup
#need to add catches for no event, a KC on it's own


class AnalogHandler(Module):
    def __init__(self):
        self.analogs = []                 #array of analogs to call during runtime
        self.apins = None                 #analog pins (required)
        self.evtmap = None                #event map of inputs (required) (2d array like a keymap)
        self.mpins = None                 #muxing  pins (optional)
        self.disabledmuxs = None          #list of disabled mux keys
                                          #(so you don't have a bunch of floating or grounded keys)
                                          #list of indexs to skip during boot (might need a better solution)
        self.filtermap = [[]] #list to contain custom filters to the inputs
        self.invertmap = [[]]          #list to set inputs to be inverted or all
        self.sensitivitymap = [[]]         #set the sensitivity of each input
        
    def on_runtime_enable(self, keyboard):
        return

    def on_runtime_disable(self, keyboard):
        return


    #look into getting filters from event func and passing those at runtime
    #so filters can be per layer
    def during_bootup(self, keyboard):
        if self.apins and self.evtmap:

            if self.mpins is not None:
                #pass to mux handler?
                print("not implemented yet")
            else:
                if debug.enabled:
                    debug('analog mode: direct pin mode')

                for idx, pin in enumerate(self.apins):
                    self.analogs.append(AnalogInput(AnalogIn(pin)))      
                print("analogs: " + str(self.analogs))

            AnalogHandlerEvtMaping(self)           
        elif debug.enabled:
            debug('missing event map or analog pins')
        return


    #perhaps for update_state it could takeing the filter from the external list
    #honisly should look into running the external func to get it's info
    #like filters during boot up
    
    def before_matrix_scan(self, keyboard):
        for idx, analog in enumerate(self.analogs):
            keyboard_layer = keyboard.active_layers[0]

            #load in maps and catch other cases
            if len(self.filtermap[0]) > 0:
                try:
                    filter_id = self.filtermap[keyboard_layer][idx]
                except:
##                    if debug.enabled:#bad to print crap in main loop
##                        debug("error in filtermap. defaulting to 0-255")
                    filter_id = 8
            else: #this should never happen fool make boot code for building from evtmap
                filter_id = 8
                
            ######################
            if type(self.invertmap) is bool :
                invert = self.invertmap
            else:
                try:
                    invert = self.invertmap[keyboard_layer][idx]
                except:
                    invert = False
                    if debug.enabled:
                        debug("invertmap format error at layer:", keyboard_layer, " event: ", idx)

            ######################
            try:
                sensitivity = self.sensitivitymap[keyboard_layer][idx]
            except:
                sensitivity = 1
            ######################

            if type(filter_id) is int:
                filter_direction = DEFAULT_FILTER[invert]
                filter = lambda input : filter_direction(input, filter_id)
            ######################
                
            old_state = analog.state

            analog.update_state(filter, sensitivity)
         
            event_func = self.evtmap[keyboard_layer][idx]

            if analog.state: #on change
                event_func.on_change(keyboard, analog)
            elif not analog.state and old_state: #on stop
                event_func.on_stop(keyboard, analog)
            #else: it hasen't moved so no reason to do anything
        return keyboard
        

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
