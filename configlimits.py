# Import configlimits and use configlimits.LIMITS or SPEEDS or Steps["Y"]

PORT = "COM5" #Widows serial port that arduino is connected to
BAUD_RATE = 250000 # communication speed between python and arduino.
T1_BASE_OFFSET = -2.2    # T1 base zero offset, actual zero is -2.2 from where it thinks it is

# Joint limits / hard safety boundaries (minimum, maximum)
LIMITS = {
    "X":    (-6.2,   12.4),
    "Y":    (-720.0, 720.0),
    "Z":    (-22.0,  22.0),
    "T0_E": (-4.2,   4.2),
    "T1_E": (-5.2,   5.2),
}

# Speeds as F values for G1 move commands
SPEEDS = {
    "X":    100,
    "Y":    8000,
    "Z":    1000,
    "T0_E": 100,
    "T1_E": 100,
}

# Movement step sizes per keypress, calculated as (max-min limits)/20 i.e. 20 movements to go from min to max limit values
STEPS = {
    axis: round((hi - lo) / 20, 4)
    for axis, (lo, hi) in LIMITS.items()
}
