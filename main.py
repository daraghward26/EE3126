import serialconnection
import calibrate
import manual_control
import voice_control
import gesture_control

def print_menu():
    print(
        "\n MAIN MENU \n"
        "  │    1. calibrate  = run calibration\n"
        "  │    2. manual     = manual keyboard control\n"
        "  │    3. voice      = voice control mode\n"
        "  │    4. gesture    = gesture control mode\n"
        "  │    5. exit       = disconnect and quit\n"
    )

def main():
    print(" Robot Arm Main Controller")

    serialconnection.connect()

    while True:
        print_menu() #always runs unless exited

        try:
            choice = input("  > ").strip().lower() #removes blank spaces
        except (EOFError, KeyboardInterrupt):
            break

        if choice in ("1", "calibrate"):
            completed = calibrate.run_calibration_prompt()
            if completed:
                with manual_control.state_lock: #accessed directly
                    manual_control.state.update({
                        "X":           0.0,
                        "Y":           0.0,
                        "Z":           0.0,
                        "T0_E":        0.0,
                        "T1_E":        0.0,
                        "active_tool": "T1",
                        "servo":       "CLOSED",
                        "mode":        "relative",
                    })
                print("Position state is now reset to zero after calibration.")

        elif choice in ("2", "manual"):
            manual_control.run()

        elif choice in ("3", "voice"):
            voice_control.run(manual_control.state, manual_control.state_lock)

        elif choice in ("4", "gesture"):
            gesture_control.run(manual_control.state, manual_control.state_lock)

        elif choice in ("5", "exit", "quit", "q"):
            break

        else:
            print("Please type 1, 2, 3, 4 or 5\n")

    serialconnection.disconnect()
    print("\n Goodbye.")

if __name__ == "__main__":
    main()
