import time
import configlimits
import serialconnection

T1_BASE_OFFSET = configlimits.T1_BASE_OFFSET
send_raw = serialconnection.send_raw
read_response = serialconnection.read_response

CALIBRATION_SEQUENCE = [ # calibration sent to give power to all joints/servos and determine home/zero position
    "G91",               #relative
    "G1 X2 Y2 Z2 F1000",
    "G1 X-2 Y-2 Z-2 F1000",
    "T0",
    "G1 E1 F100",
    "G1 E-1 F100",
    "T1",
    "G1 E1 F100",
    "G1 E-1 F100",
    "M280 P0 S0",
    "M280 P0 S90",
]

def run_base_calibration(): #performs cycling through calibration and printing positions
    print("\n Running calibration sequence: ")
    for cmd in CALIBRATION_SEQUENCE:
        print(f" = {cmd}")
        send_raw(cmd)
        time.sleep(0.5)
        read_response(timeout=0.3)
    print(" Base calibration complete.\n")

def calibrate_only(): # calibration modes #Standard base calibration
    run_base_calibration()
    print(" Done: current position is home (all joints are zero'd)")

def calibrate_with_zero(): #Base calibration + zero offset.
    run_base_calibration()

    print("Applying T1 base offset")
    print(f" Moving T1 to physical zero: G1 E{T1_BASE_OFFSET} F100")
    send_raw(f"G1 E{T1_BASE_OFFSET} F100")
    time.sleep(abs(T1_BASE_OFFSET) * 0.5 + 1.0)
    read_response(timeout=0.3)
    print("G92 E0  (declare as E=0)")
    send_raw("G92 E0")
    time.sleep(0.3)
    read_response(timeout=0.3)
    print(f" T1 zeroed : offset {T1_BASE_OFFSET} applied, now reading 0.\n")
    print(" Done : the current position is home (all joints = 0).")

def calibrate_fix(): #Base calibration +4.4 correction. Use when calibrate_zero was run by mistake at start.
    run_base_calibration()

    FIX_OFFSET = +4.4
    print(f" Applying T1 fix offset ({FIX_OFFSET:+.1f} mm)")
    print(f" Moving T1 by fix offset: G1 E{FIX_OFFSET} F100")
    send_raw(f"G1 E{FIX_OFFSET} F100")
    time.sleep(abs(FIX_OFFSET) * 0.5 + 1.0)
    read_response(timeout=0.3)
    print(" G92 E0  (declare as E=0)")
    send_raw("G92 E0")
    time.sleep(0.3)
    read_response(timeout=0.3)
    print(f" T1 fix applied {FIX_OFFSET:+.1f} mm offset, position is now corrected to 0.\n")
    print("Done : current position is home (all joints = 0).")

def run_calibration_prompt(): #calibration prompt menu
    print(
        "\n SELECT CALIBRATION TYPE \n"
        "  │    calibrate        -base calibration only end position is set as home\n"
        "  │\n"
        "  │    calibrate_zero   -base calibration + T1 offset moves T1 to physical zero\n"
        "  │\n"
        "  │    calibrate_fix    -base calibration + +4.4 correction reverses mistake and rezeroes T1\n"
    )

    while True: #waits for user input in loop
        try:
            choice = input("  > ").strip().lower() #convert to same case
        except (EOFError, KeyboardInterrupt):
            print("\n Calibration Aborted.")
            return False

        if choice == "calibrate":
            calibrate_only()
            return True
        elif choice in ("calibrate_zero", "calibrate-zero"):
            calibrate_with_zero()
            return True
        elif choice in ("calibrate_fix", "calibrate-fix"):
            calibrate_fix()
            return True
        else:
            print(" Select calibrate, calibrate_zero  or calibrate_fix\n")

#main for if running script directly
def main():
    print("Robot Arm Calibration")
    serialconnection.connect()
    run_calibration_prompt()
    serialconnection.disconnect()
    print("\nCalibration complete. You can close this window.")

if __name__ == "__main__":
    main()