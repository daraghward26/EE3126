import json
import os
import time
import serialconnection
import configlimits

COMMANDS_FILE = os.path.join(os.path.dirname(__file__), "commands.json")
SPEEDS = configlimits.SPEEDS
LIMITS = configlimits.LIMITS

AXIS_MAP = { # Lookup table mapping axis name to state, gcode and speed.
    "X":    {"state_key": "X",   "gcode": "X", "speed_key": "X"},
    "Y":    {"state_key": "Y",    "gcode": "Y", "speed_key": "Y"},
    "Z":    {"state_key": "Z",    "gcode": "Z", "speed_key": "Z"},
    "T0_E": {"state_key": "T0_E", "gcode": "E", "speed_key": "T0_E"},
    "T1_E": {"state_key": "T1_E", "gcode": "E", "speed_key": "T1_E"},
}

def _load_all(): #reads JSON, returns empty if missing
    if not os.path.exists(COMMANDS_FILE):
        return {}
    try:
        with open(COMMANDS_FILE, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        print(f" WARNING: Could not read commands file: {e}")
        return {}

def print_all():
    cmds = _load_all()
    if not cmds:
        print("\n No saved commands yet.\n")
        return
    print(f"\n AVAILABLE COMMANDS")
    for name in cmds:
        print(f" {name}")

def _send(cmd): #to send gcode command to terminal keeping updated
    print(f" {cmd}")
    serialconnection.send_raw(cmd)

def _wait_for_move(speed_key, delta): #approximately calculate time to complete movement
    secs = abs(delta) / (SPEEDS[speed_key] / 60.0) + 0.3
    time.sleep(secs)

def _switch_tool(axis, state, state_lock):
    #reads currently known e position from state dictionary, sends command to switch tool, G92 current position and updates the active tool in state dictionary.
    if axis == "T0_E":
        with state_lock:
            current_e = state["T0_E"]
        _send("T0")
        _send(f"G92 E{current_e:.4f}")
        with state_lock:
            state["active_tool"] = "T0"
    elif axis == "T1_E":
        with state_lock:
            current_e = state["T1_E"]
        _send("T1")
        _send(f"G92 E{current_e:.4f}")
        with state_lock:
            state["active_tool"] = "T1"

def _move_to_absolute(axis, target_val, state, state_lock):
    #moves axis to absolute value by calculating delta (relative)
    info = AXIS_MAP[axis]
    state_key = info["state_key"]
    speed_key = info["speed_key"]
    gcode = info["gcode"]

    with state_lock:
        current = state[state_key]

    delta = round(target_val - current, 4)
    if delta == 0.0:
        return 0.0

    if axis in ("T0_E", "T1_E"):
        _switch_tool(axis, state, state_lock)
        _send(f"G1 E{delta} F{SPEEDS[speed_key]}")
    else:
        _send(f"G1 {gcode}{delta} F{SPEEDS[speed_key]}")

    with state_lock:
        state[state_key] = target_val

    _wait_for_move(speed_key, delta)
    return delta

def _go_home(state, state_lock):
    print(" Going to absolute zero.")
    for axis in ("Z", "Y", "X", "T0_E", "T1_E"):
        _move_to_absolute(axis, 0.0, state, state_lock)
    print(" At absolute zero.")

def _go_to_absolute_position(pos, state, state_lock): #moves all axis to absolute position.
    order = []
    # Z axis moves first if going up but last if going down to prevent flopping of unpowered joints.
    with state_lock:
        current_z = state["Z"]
    target_z = pos.get("Z", current_z)
    if target_z >= current_z:
        order = ["Z", "Y", "X", "T0_E", "T1_E"]
    else:
        order = ["Y", "X", "T0_E", "T1_E", "Z"]

    for axis in order:
        key = axis if axis in ("X","Y","Z") else axis
        if key in pos:
            _move_to_absolute(axis, pos[key], state, state_lock)
        elif axis == "T0_E" and "T0_E" in pos:
            _move_to_absolute("T0_E", pos["T0_E"], state, state_lock)
        elif axis == "T1_E" and "T1_E" in pos:
            _move_to_absolute("T1_E", pos["T1_E"], state, state_lock)

def _servo(value, state, state_lock, wait=0.5):
    label = "OPEN" if value == 0 else ("HALF" if value == 45 else "CLOSED")
    print(f"Servo: S{value} ({label}) ")
    _send(f"M280 P0 S{value}")
    with state_lock:
        state["servo"] = label
    time.sleep(wait)

def _run_step(step, state, state_lock):
    t = step["type"]

    if t == "home":
        _go_home(state, state_lock)
        time.sleep(step.get("wait", 1.0))

    elif t == "move":
        axis = step["axis"]
        target = step["target"]
        ret_zero = step.get("return_zero", True)
        wait = step.get("wait", 1.0)
        lo, hi = LIMITS[axis]

        # Min
        print(f" {axis} = min ({lo:+.3f}) ")
        _move_to_absolute(axis, lo, state, state_lock)
        time.sleep(wait)

        # Max
        print(f"  {axis} = max ({hi:+.3f})")
        _move_to_absolute(axis, hi, state, state_lock)
        time.sleep(wait)

        # Return to zero
        if ret_zero:
            print(f" {axis} to 0")
            _move_to_absolute(axis, 0.0, state, state_lock)
            time.sleep(wait)

    elif t == "servo":
        _servo(step["value"], state, state_lock, step.get("wait", 0.5))

    elif t == "raw":
        _send(step["cmd"])
        time.sleep(step.get("wait", 0.3))

    elif t == "absolute":
        print(f" Moving to absolute position")
        pos = {k: v for k, v in step.items() if k not in ("type", "wait")}
        _go_to_absolute_position(pos, state, state_lock)
        time.sleep(step.get("wait", 0.5))

    elif t == "move_joint":
 # Move a single joint to an absolute target position and wait.
        axis = step["axis"]
        target = step["target"]
        wait    = step.get("wait", 0.0)
        _move_to_absolute(axis, target, state, state_lock)
        if wait > 0:
            print(f"Waiting {wait}s")
            time.sleep(wait)

def run_command(name, state, state_lock): #loads command file, finds name command, loops through command steps.Updates position tracking.
    cmds = _load_all()
    if name not in cmds:
        print(f" No command '{name}' found")
        print_all()
        return

    labels = {
        "limits":      "Showing all joint limits",
        "acknowledge": "Acknowledging",
        "wave":        "Waving",
        "drop":        "Dropping the object",
    }
    print(f"\nRUNNING: {name}")
    print(f" {labels.get(name, name)}")

    steps = cmds[name]["steps"]
    for i, step in enumerate(steps, 1):
        _run_step(step, state, state_lock)

    print(f"\n  Done: '{name}' complete\n")