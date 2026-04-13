import speech_recognition as sr
import threading
import commands

def _load_triggers(): #loads voice command dictionary from JSON
    all_cmds = commands._load_all()
    triggers = all_cmds.get("voice_triggers", {}) #gets triggers section
    return dict(sorted(triggers.items(), key=lambda x: len(x[0]), reverse=True))   #Sorted by length so longer phrases match first

def _match_trigger(text, triggers): #return command name for trigger word if heard
    for phrase, cmd_name in triggers.items():
        if phrase in text: #checks if trigger word is in text
            return cmd_name, phrase #returns command name and match word
    return None, None #if non returns none

def run(state, state_lock):
    recognizer = sr.Recognizer() #recognition engine
    triggers = _load_triggers() #loads trigger map at startup
    running = True

    print("Voice Control Mode")
    print("\n Trigger words:")
    for phrase, cmd in triggers.items():
        print(f" '{phrase}' = {cmd}")
    print("\nSay 'quit' or 'exit' to go to main menu.")
    print(" Listening pauses while a command is running.\n")

    active_command = threading.Event()   # set while a command is running

    def execute(cmd_name):
        active_command.set() #marks running command
        try:
            commands.run_command(cmd_name, state, state_lock)
        finally:
            active_command.clear() #marks command as finished

    while running: #dont listen if command is running
        if active_command.is_set(): # checks if command is currently running
            import time
            time.sleep(0.1)
            continue

        try:
            with sr.Microphone() as mic:
                print(" Listening")
                recognizer.adjust_for_ambient_noise(mic, duration=0.5)
                audio = recognizer.listen(mic, timeout=5, phrase_time_limit=10)

            text = recognizer.recognize_google(audio).lower() #sends audio to google server and receives back text
            print(f" Heard: '{text}'")

            # Check for exit first
            if "quit" in text or "exit" in text:
                print(" Exiting voice control")
                running = False
                break

            # Match trigger phrase
            cmd_name, matched = _match_trigger(text, triggers)
            if cmd_name:
                print(f" Trigger: '{matched}' =  {cmd_name}")
                threading.Thread(
                    target=execute,
                    args=(cmd_name,),
                    daemon=True
                ).start()
            else:
                print("No trigger word recognised.")

        except sr.WaitTimeoutError:
            print("No speech detected, still listening")
        except sr.UnknownValueError:
            print("Could not understand audio pleasetry again.")
        except sr.RequestError:
            print("Google Speech Recognition is not available.")
        except KeyboardInterrupt:
            print("\nInterrupted.")
            break
        except Exception as e:
            print(f"Error: {e}")

    print("\n  Returned to main menu.\n")
