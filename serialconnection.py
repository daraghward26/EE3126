import serial #handles Windows serial port communication.
import time
import threading
import configlimits

# import serialconnection and use serialconnection.connect() or serialconnection.send_raw("G_ X_ F___")
_arduino   = None #connection object stored as private module level variable. Other files do not access directly but use send.raw()
_lock      = threading.Lock() #prevents keyboard listener and command input threads writing to serial port at same time.

# Connect calls and opens the serial port at startup, returns the arduino object so it can be referenced in other scripts.
def connect():
    global _arduino
    try:
        _arduino = serial.Serial(configlimits.PORT, configlimits.BAUD_RATE, timeout=1)
        time.sleep(2) #time for arduino to reset
        _arduino.reset_input_buffer()
        _arduino.reset_output_buffer() # clears previous left over data
        print(f" Successfully Connected to {configlimits.PORT} @ {configlimits.BAUD_RATE} baud")
    except Exception as e:
        print(f" WARNING: Could not open {configlimits.PORT}: {e}")
        print(" Running in DEMO MODE\n")
        _arduino = None
    return _arduino

# Disconnect is called on exit and closes the serial port cleanly releasing it.
def disconnect():
    global _arduino
    if _arduino:
        _arduino.close()
        _arduino = None
        print(" Serial connection closed.")

# Send takes the command, adds new line required, and writes it to arduino / prints to screen in demo mode
def send_raw(cmd):
    line = cmd.strip() + "\n"
    with _lock:
        if _arduino:
            try:
                _arduino.write(line.encode()) #sends bytes to serial port
                _arduino.flush()
            except Exception as e:
                print(f" WARNING: Serial error: {e}")
        else:
            print(f"  [DEMO] = {cmd.strip()}")

# Read and removes responses to prevent input buffer filling
def read_response(timeout=0.3):
    if not _arduino:
        return
    deadline = time.time() + timeout
    with _lock: #acquire lock
        while time.time() < deadline:
            if _arduino.in_waiting:
                _arduino.readline().decode(errors="replace").strip() #reads, replaces and removes to clear buffer
            else:
                time.sleep(0.01) #wait before rechecking