# Potentiometer

This module provides access to the values from analog pins and allows you to trigger functions based on the movement of the potentiometers.
## Usage
### 1. Import the module and declare your handler

from kmk.modules.potentiometer import PotentiometerHandler
potentiometer_handler = PotentiometerHandler()

keyboard.modules.append(potentiometer_handler)

### 2. Define your potentiometers, their corresponding functions, and an array to index the potentiometers

The format for each potentiometer is as follows:

    (Board pin, your function, boolean for defining min-max direction)

```python
potarray = []

potentiometer_handler.pins = [
    (board.A0, yourfunc.Handler(0, potarray), True),
    (board.A1, yourfunc.Handler(1, potarray), True),
    (board.A2, yourfunc.Handler(2, potarray), True),
    (board.A3, yourfunc.Handler(3, potarray), True)
]
potentiometer_handler.potentiometers = potarray
```

In the functions, the array is used to select the specific potentiometer to interact with. You can pass the potentiometer index as a number. However, if you don't need the index, you can directly reference the potentiometer using ```potarray[0]```.

### 3. Retrieve the potentiometer's position and direction of travel

To get the current position and direction of a potentiometer, use the following code:
```python
potpositionraw = (potarray[potnum].get_state()).position
potdirection = (potarray[potnum].get_state()).direction
```

## Working with the Output

If the "inverted" boolean is set, the potentiometer's range will be from -127 to 0. To normalize this range to 0 to 127, you can use the following code:

```python
if potpositionraw < 1 and potpositionraw != 0:
    potposition = potpositionraw + 127
elif potpositionraw == 0 and potdirection == 1:
    potposition = potpositionraw + 127
else:
    potposition = potpositionraw
```
