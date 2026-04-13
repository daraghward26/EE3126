import json            # Used to save and to load positions of robot to/from locations.json
import os               #Locations store location name as string, X, Y, Z, T0 and T1 positions

LOCATIONS_FILE = os.path.join(os.path.dirname(__file__), "locations.json")

def _load_all(): # load all saved locations
    if not os.path.exists(LOCATIONS_FILE):
        return {}
    try:
        with open(LOCATIONS_FILE, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        print(f" Warning: Could not read locations file:{e}")
        return {}

def _save_all(locations): #Takes full location dictionary and writes it back to JSON file
    try:
        with open(LOCATIONS_FILE, "w") as f:
            json.dump(locations, f, indent=4)
    except IOError as e:
        print(f"WARNING: Could not write locations file: {e}")

def save_location(name, state):  #Save current positions under a name and overwrite if it already exists

    locations = _load_all()
    locations[name] = {
        "X":  state["X"],
        "Y":  state["Y"],
        "Z":   state["Z"],
        "T0_E": state["T0_E"],
        "T1_E": state["T1_E"],
    }
    _save_all(locations)
    print(
        f"\n Location '{name}' saved "
        f"  X:{state['X']:+.3f}  "
        f"Y:{state['Y']:+.3f}  "
        f"Z:{state['Z']:+.3f}  "
        f"T0:{state['T0_E']:+.3f}  "
        f"T1:{state['T1_E']:+.3f}"
    )

def load_location(name): #returns saved position dictionary for name

    locations = _load_all()
    if name in locations:
        return locations[name]
    print(f" No location named '{name}' was found.")
    print_all()
    return None

def delete_location(name): # delete saved locations
    locations = _load_all()
    if name in locations:
        del locations[name]
        _save_all(locations)
        print(f" Location '{name}' was deleted.")
    else:
        print(f" No location named '{name}' found.")
        print_all()

def print_all(): # print all the saved locations

    locations = _load_all()
    if not locations:
        print("\n No saved locations\n")
        return
    print(f"\nSAVED LOCATIONS")
    for name, pos in locations.items():
        print(
         f" {name:<20}"
        f"X:{pos['X']:+.3f} "
        f"Y:{pos['Y']:+.3f}  "
        f"Z:{pos['Z']:+.3f}"
        f"T0:{pos['T0_E']:+.3f}  "
        f"T1:{pos['T1_E']:+.3f}"
        )