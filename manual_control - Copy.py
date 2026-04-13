import time
import threading
import sys #safe input
from pynput import keyboard #capture key presses
import calibrate

import configlimits
PORT = configlimits.PORT
BAUD_RATE = configlimits.BAUD_RATE
LIMITS  = configlimits.LIMITS
SPEEDS = configlimits.SPEEDS
STEPS = configlimits.STEPS

import serialconnection
send_raw = serialconnection.send_raw
read_response = serialconnection.read_response

import locations
import commands

#joint state dictionary to keep track of live positions
state = {
    "X":           0.0,
    "Y":           0.0,
    "Z":           0.0,
    "T0_E":        0.0,
    "T1_E":        0.0,
    "active_tool": None,
    "servo":       "CLOSED",
    "mode":        "relative",
}

SLOW_DIVISOR = 5 #slow mode

state_lock = threading.Lock()
running = True
ctrl_held = False
typing_mode = False   # True = command input mode, keys ignored as robot commands

keys_down = set() #tracks pressed keys now
keys_fired = set() #triggered presses
keys_lock = threading.Lock()


def safe_input(prompt=""): #Handles non-UTF-8 bytes from Windows terminals
    try:
        if prompt:
            print(prompt, end="", flush=True)
        line = sys.stdin.buffer.readline()
        return line.decode("utf-8", errors="replace").strip()
    except Exception:
        return ""

def print_state(mode_tag=""):
    with state_lock:
        tool  = state["active_tool"] or "?"
        servo = state["servo"] or "?"
        slow  = " [SLOW MODE ON]" if ctrl_held else ""
        typing = " [TYPING MODE]" if typing_mode else ""
        print(
            f"\r  X:{state['X']:+.3f}  " #overwrites instead of new line
            f"Y:{state['Y']:+.3f}  "
            f"Z:{state['Z']:+.3f}  "
            f"T0:{state['T0_E']:+.3f}  "
            f"T1:{state['T1_E']:+.3f}  "
            f"Tool:{tool}  Servo:{servo}{slow}{typing}    ",
            end="", flush=True
        )

def print_full_state():
    with state_lock:
        tool  = state["active_tool"] or "?"
        servo = state["servo"] or "?"
        print(
            f"\n JOINT POSITIONS\n"
            f" X : {state['X']:+.3f} mm  (step: {STEPS['X']}mm)\n"
            f" Y : {state['Y']:+.3f} mm  (step: {STEPS['Y']}mm)\n"
            f" Z : {state['Z']:+.3f} mm  (step: {STEPS['Z']}mm)\n"
            f" T0 (E) : {state['T0_E']:+.3f} mm  (step: {STEPS['T0_E']}mm)\n"
            f" T1 (E) : {state['T1_E']:+.3f} mm  (step: {STEPS['T1_E']}mm)\n"
            f" Active tool : {tool}\n"
            f" Servo: {servo}\n"

        )

def would_exceed_limits(axis, delta): #limit checking, calculates position after movement, determines if within limits
    with state_lock:
        if axis in ("X", "Y", "Z"):
            new_val = state[axis] + delta
        elif axis == "T0_E":
            new_val = state["T0_E"] + delta
        elif axis == "T1_E":
            new_val = state["T1_E"] + delta
        else:
            return False
    lo, hi = LIMITS[axis]
    return new_val < lo or new_val > hi

def switch_tool(new_tool): #tool switching
    with state_lock:
        current = state["active_tool"]
    if new_tool == current:
        return #if already on correct tool.
    send_raw(new_tool) #switch extruder tool T0/T1
    #get correct e position for tool
    with state_lock:
        saved_e = state["T0_E"] if new_tool == "T0" else state["T1_E"]
    send_raw(f"G92 E{saved_e:.4f}")
    with state_lock:
        state["active_tool"] = new_tool #update tool state

def move_axis(axis, direction):
    divisor = SLOW_DIVISOR if ctrl_held else 1
    step    = round(STEPS[axis] / divisor * direction, 6)
    speed   = SPEEDS[axis]

    if would_exceed_limits(axis, step):
        lo, hi = LIMITS[axis]
        print(f"\n  WARNING:  {axis} limit reached [{lo:+.3f}, {hi:+.3f}]  ", flush=True)
        return False

    mode_tag = " [SLOW]" if ctrl_held else ""

    if axis in ("X", "Y", "Z"):
        send_raw(f"G1 {axis}{step} F{speed}")
        with state_lock:
            state[axis] += step #add delta update state

    elif axis in ("T0_E", "T1_E"):
        tool = "T0" if axis == "T0_E" else "T1"
        switch_tool(tool) #ensure correct tool active
        send_raw(f"G1 E{step} F{speed}")
        with state_lock:
            if axis == "T0_E":
                state["T0_E"] += step
            else:
                state["T1_E"] += step

    print_state(mode_tag) #update status
    return True

def toggle_servo(): #reads current state and sends opposite command to switch state
    with state_lock:
        current = state["servo"]
    if current == "OPEN":
        send_raw("M280 P0 S90")
        with state_lock:
            state["servo"] = "CLOSED"
        print(f"\nServo CLOSED", flush=True)
    else:
        send_raw("M280 P0 S0")
        with state_lock:
            state["servo"] = "OPEN"
        print(f"\nServo OPEN", flush=True)
    print_state()

saved_home = {
    "X": 0.0, "Y": 0.0, "Z": 0.0,
    "T0_E": 0.0, "T1_E": 0.0,
}

def mark_home():
    with state_lock:
        saved_home["X"]    = state["X"]
        saved_home["Y"]    = state["Y"]
        saved_home["Z"]    = state["Z"]
        saved_home["T0_E"] = state["T0_E"]
        saved_home["T1_E"] = state["T1_E"]
    print(
        f"\n Home saved: "
        f"X:{saved_home['X']:+.3f}  "
        f"Y:{saved_home['Y']:+.3f}  "
        f"Z:{saved_home['Z']:+.3f}  "
        f"T0:{saved_home['T0_E']:+.3f}  "
        f"T1:{saved_home['T1_E']:+.3f}",
        flush=True
    )
    print_state()

def go_home():
    #calculates delta for each axis
    #if delta is not 0 then sends the command to move
    print("\n\n *Returning to saved home")

    with state_lock:
        dx  = saved_home["X"]    - state["X"]
        dy  = saved_home["Y"]    - state["Y"]
        dz  = saved_home["Z"]    - state["Z"]
        dt0 = saved_home["T0_E"] - state["T0_E"]
        dt1 = saved_home["T1_E"] - state["T1_E"]

    if dx != 0.0:
        send_raw(f"G1 X{round(dx, 4)} F{SPEEDS['X']}")
        time.sleep(abs(dx) / 10 + 0.3)
    if dy != 0.0:
        send_raw(f"G1 Y{round(dy, 4)} F{SPEEDS['Y']}")
        time.sleep(abs(dy) / 200 + 0.3)
    if dz != 0.0:
        send_raw(f"G1 Z{round(dz, 4)} F{SPEEDS['Z']}")
        time.sleep(abs(dz) / 10 + 0.3)
    if dt0 != 0.0:
        switch_tool("T0")
        send_raw(f"G1 E{round(dt0, 4)} F{SPEEDS['T0_E']}")
        time.sleep(abs(dt0) / 5 + 0.3)
    if dt1 != 0.0:
        switch_tool("T1")
        send_raw(f"G1 E{round(dt1, 4)} F{SPEEDS['T1_E']}")
        time.sleep(abs(dt1) / 5 + 0.3)

    with state_lock:
        state["X"]    = saved_home["X"]
        state["Y"]    = saved_home["Y"]
        state["Z"]    = saved_home["Z"]
        state["T0_E"] = saved_home["T0_E"]
        state["T1_E"] = saved_home["T1_E"]

    print(" Arrived at saved home.")
    print_full_state()

def emergency_stop(): #emergency stop, F2, sends M410 stopping movement and clearing buffer
    serialconnection.send_raw("M410")
    print(
        "\n\n WARNING: EMERGENCY STOP (M410 sent. Robot halted)."
        "\n WARNING Physical position may be slightly behind software state / Recalibrate before continuing any precise movements."
        "\n Ready to continue with commands.\n",
        flush=True
    )
    print_full_state()

KEY_MAP = { #Key mapping - lowercase = + and uppercase = - direction.
    "x": ("X",    +1),
    "X": ("X",    -1),
    "y": ("Y",    +1),
    "Y": ("Y",    -1),
    "z": ("Z",    +1),
    "Z": ("Z",    -1),
    "0": ("T0_E", +1),
    ")": ("T0_E", -1),
    "1": ("T1_E", +1),
    "!": ("T1_E", -1),
}

SPECIAL_KEYS = {
    "o": "servo_toggle",
    "O": "servo_toggle",
}

def key_to_char(key): #catches and deals with special keys
    try:
        return key.char
    except AttributeError:
        return None

def on_press(key):
    global running, ctrl_held, typing_mode

    if key == keyboard.Key.f2: #F2 always ready to send no matter the mode
        emergency_stop()
        return

    if key == keyboard.Key.f12: #F12 to toggle typing mode also no mode check
        typing_mode = not typing_mode
        status = "TYPING ON (type commands, press F12 to exit)" if typing_mode else "TYPING OFF (keys active)"
        print(f"\n Typing mode {status}", flush=True)
        if not typing_mode:
            print_state()
        return

    if typing_mode: # If typing mode is on, ignore all keys being pressed
        return

    char = key_to_char(key)

    if key in (keyboard.Key.ctrl_l, keyboard.Key.ctrl_r): #Ctrl to toggle slow mode
        ctrl_held = not ctrl_held
        status = "ON slow" if ctrl_held else "OFF fast"
        print(f"\n Slow mode {status}", flush=True)
        print_state()
        return

    if key == keyboard.Key.esc: #esc to exit
        running = False
        return False

    if char is None: #special key
        return

    if char in SPECIAL_KEYS: #special key (servo toggle)
        with keys_lock:
            if char in keys_fired:
                return #ignore repeat press
            keys_fired.add(char)
            keys_down.add(char)
        action = SPECIAL_KEYS[char]
        if action == "servo_toggle":
            toggle_servo()
        return

    if char in KEY_MAP: #movement keys
        with keys_lock:
            if char in keys_fired:
                return
            keys_fired.add(char)
            keys_down.add(char)
        axis, direction = KEY_MAP[char]
        move_axis(axis, direction)

def on_release(key):
    char = key_to_char(key)
    if char:
        with keys_lock:
            keys_down.discard(char)
            keys_fired.discard(char)

def move_to_saved_location(name): #to move to a save locations position
    pos = locations.load_location(name)
    if pos is None:
        return

    print(f"\n Moving to '{name}'")

    axes = [("X", "X"), ("Y", "Y"), ("Z", "Z"), #go through all axis
            ("T0_E", "T0_E"), ("T1_E", "T1_E")]

    #calculate delta = target position - current position, skip if delta=0 and send command
    for state_key, limit_key in axes:
        with state_lock:
            current = state[state_key]
        target = pos[state_key]
        delta = round(target - current, 6)
        if delta == 0.0:
            continue
        speed = SPEEDS[limit_key]
        print(f"  ~ {state_key}: {current:+.3f} to {target:+.3f}  (Delta{delta:+.3f})  F{speed}")
        if state_key in ("X", "Y", "Z"):
            send_raw(f"G1 {state_key}{delta} F{speed}")
        else:
            tool = "T0" if state_key == "T0_E" else "T1"
            switch_tool(tool)
            send_raw(f"G1 E{delta} F{speed}")
        with state_lock:
            state[state_key] = target

    print(f" Arrived at '{name}'")
    print_full_state()

def command_thread(): #command input for when typing mode  on
    global running, typing_mode
    while running: #loops unless exited using esc
        raw = safe_input()
        if not raw:
            continue

        #Ignore and discard if typing mode is off
        if not typing_mode:
            continue

        cmd = raw.lower() # lowercase
        parts = raw.split(None, 1)
        cmd0 = parts[0].lower()

        if cmd == "home":
            threading.Thread(target=go_home, daemon=True).start()

        elif cmd == "save home":
            mark_home()

        elif cmd == "print":
            print_full_state()

        elif cmd0 == "save":
            print("\n Enter a name for this location: ", end="", flush=True)
            name = safe_input()
            if name:
                with state_lock:
                    current_state = dict(state)
                locations.save_location(name, current_state)
            else:
                print(" No name entered, location not saved.")

        elif cmd0 == "load":
            if len(parts) < 2:
                print(" Usage:  load <name>")
            else:
                move_to_saved_location(parts[1])

        elif cmd0 == "delete":
            if len(parts) < 2:
                print(" Usage:  delete <name>")
            else:
                locations.delete_location(parts[1])

        elif cmd in ("locations", "locs", "list"):
            locations.print_all()

        #limits runs the limits demonstration command
        elif cmd == "limits":
            threading.Thread(
                target=commands.run_command,
                args=("limits", state, state_lock),
                daemon=True #dies if program exits automatically
            ).start()

        # acknowledge
        elif cmd == "acknowledge":
            threading.Thread(
                target=commands.run_command,
                args=("acknowledge", state, state_lock),
                daemon=True
            ).start()

        #wave
        elif cmd == "wave":
            threading.Thread(
                target=commands.run_command,
                args=("wave", state, state_lock),
                daemon=True
            ).start()

        # drop
        elif cmd == "drop":
            threading.Thread(
                target=commands.run_command,
                args=("drop", state, state_lock),
                daemon=True
            ).start()

        # waterbottle_routine1
        elif cmd == "waterbottle_routine1":
            threading.Thread(
                target=commands.run_command,
                args=("waterbottle_routine1", state, state_lock),
                daemon=True
            ).start()

        # waterbottle_routine_reverse
        elif cmd in ("waterbottle_routine_reverse", "waterbottle_reverse"):
            threading.Thread(
                target=commands.run_command,
                args=("waterbottle_routine_reverse", state, state_lock),
                daemon=True
            ).start()

        # soap_routine1
        elif cmd == "soap_routine1":
            threading.Thread(
                target=commands.run_command,
                args=("soap_routine1", state, state_lock),
                daemon=True
            ).start()

        # soap_routine_reverse
        elif cmd in ("soap_routine_reverse", "soap_reverse"):
            threading.Thread(
                target=commands.run_command,
                args=("soap_routine_reverse", state, state_lock),
                daemon=True
            ).start()

        # bottle_routine1
        elif cmd == "bottle_routine1":
            threading.Thread(
                target=commands.run_command,
                args=("bottle_routine1", state, state_lock),
                daemon=True
            ).start()

        # box1_routine1
        elif cmd == "box1_routine1":
            threading.Thread(
                target=commands.run_command,
                args=("box1_routine1", state, state_lock),
                daemon=True
            ).start()

        # box2_routine1
        elif cmd == "box2_routine1":
            threading.Thread(
                target=commands.run_command,
                args=("box2_routine1", state, state_lock),
                daemon=True
            ).start()

        # box3_routine1
        elif cmd == "box3_routine1":
            threading.Thread(
                target=commands.run_command,
                args=("box3_routine1", state, state_lock),
                daemon=True
            ).start()

        elif cmd == "box1_routine_reverse":
            threading.Thread(
                target=commands.run_command,
                args=("box1_routine_reverse", state, state_lock),
                daemon=True
            ).start()

        elif cmd == "box2_routine_reverse":
            threading.Thread(
                target=commands.run_command,
                args=("box2_routine_reverse", state, state_lock),
                daemon=True
            ).start()

        elif cmd == "box3_routine_reverse":
            threading.Thread(
                target=commands.run_command,
                args=("box3_routine_reverse", state, state_lock),
                daemon=True
            ).start()

        elif cmd in ("commands", "cmds"): # commands : list all available commands
            commands.print_all()

        else:
            print(f" Unknown command '{raw}'.")
            print("  Commands: home | save home | print | save | load <n> | delete <n> | locations | run <n> | routine save/delete/list")


def run():
    global running, typing_mode

    running = True
    typing_mode = False

    #do not reset position, robot is still where left
    with state_lock:
        state["active_tool"] = state.get("active_tool") or "T1"
        state["servo"]       = state.get("servo") or "CLOSED"
        state["mode"]        = "relative"

    print(" Manual Keyboard Control")
    for axis, step in STEPS.items():
        lo, hi = LIMITS[axis]
        print(f"    {axis:<6} : {step} mm  (range {lo} to {hi})")
    print()

    print_full_state()
    print(" Ready, just press keys to move. Click Esc to return to menu.")
    print(" Press F12 to toggle typing mode for commands.\n")

    listener = keyboard.Listener(
        on_press=on_press,
        on_release=on_release
    )
    listener.start()

    cmd_thread = threading.Thread(target=command_thread, daemon=True)
    cmd_thread.start()

    try:
        while running:
            time.sleep(0.05)
    except KeyboardInterrupt:
        pass

    running = False
    listener.stop()
    print("\n\n  Returned to main menu. Final positions:")
    print_full_state()

def main():
    print(" Robot Manual Keyboard Controller (standalone)")

    serialconnection.connect()
    calibrate.run_calibration_prompt()
    run()
    serialconnection.disconnect()

if __name__ == "__main__":
    main()