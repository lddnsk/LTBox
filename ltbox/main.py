import argparse
import os
import platform
import subprocess
import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent.resolve()))

if platform.system() == "Windows":
    import ctypes

try:
    from ltbox import utils, actions, workflow
except ImportError as e:
    print(f"[!] Error: Failed to import 'ltbox' package.", file=sys.stderr)
    print(f"[!] Details: {e}", file=sys.stderr)
    print(f"[!] Please ensure the 'ltbox' folder and its files are present.", file=sys.stderr)
    if platform.system() == "Windows":
        os.system("pause")
    sys.exit(1)

class Tee:
    def __init__(self, original_stream, log_file):
        self.original_stream = original_stream
        self.log_file = log_file

    def write(self, message):
        try:
            self.original_stream.write(message)
            self.log_file.write(message)
        except Exception as e:
            self.original_stream.write(f"\n[!] Logging Error: {e}\n")

    def flush(self):
        try:
            self.original_stream.flush()
            self.log_file.flush()
        except Exception:
            pass

def setup_console():
    system = platform.system()
    if system == "Windows":
        try:
            ctypes.windll.kernel32.SetConsoleTitleW(u"LTBox")
        except Exception as e:
            print(f"[!] Warning: Failed to set console title: {e}", file=sys.stderr)

def run_task(command, title, skip_adb=False):
    log_file_handle = None
    original_stdout = sys.stdout
    original_stderr = sys.stderr

    if command in ["patch_all", "patch_all_wipe"]:
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            log_filename = f"log_{timestamp}.txt"
            
            log_file_handle = open(log_filename, 'w', encoding='utf-8')
            
            sys.stdout = Tee(original_stdout, log_file_handle)
            sys.stderr = Tee(original_stderr, log_file_handle)
            
            print(f"--- Logging enabled. Output will be saved to {log_filename} ---")
            print(f"--- Command: {command} ---")
        except Exception as e:
            sys.stdout = original_stdout
            sys.stderr = original_stderr
            if log_file_handle:
                log_file_handle.close()
            print(f"[!] Failed to initialize logger: {e}", file=sys.stderr)
            log_file_handle = None
    
    os.environ['SKIP_ADB'] = '1' if skip_adb else '0'

    os.system('cls' if os.name == 'nt' else 'clear')
    print("  " + "=" * 58)
    print(f"    Starting Task: [{title}]...")
    print("  " + "=" * 58, "\n")

    try:
        if command == "convert":
            actions.convert_images()
        elif command == "root_device":
            actions.root_device(skip_adb=skip_adb)
        elif command == "unroot_device":
            actions.unroot_device(skip_adb=skip_adb)
        elif command == "disable_ota":
            actions.disable_ota(skip_adb=skip_adb)
        elif command == "edit_dp":
            actions.edit_devinfo_persist()
        elif command == "read_edl":
            actions.read_edl(skip_adb=skip_adb)
        elif command == "write_edl":
            actions.write_edl()
        elif command == "read_anti_rollback":
            actions.read_anti_rollback()
        elif command == "patch_anti_rollback":
            actions.patch_anti_rollback()
        elif command == "write_anti_rollback":
            actions.write_anti_rollback()
        elif command == "clean":
            utils.clean_workspace()
        elif command == "modify_xml":
            actions.modify_xml(wipe=0)
        elif command == "modify_xml_wipe":
            actions.modify_xml(wipe=1)
        elif command == "flash_edl":
            actions.flash_edl()
        elif command == "patch_all":
            workflow.patch_all(wipe=0, skip_adb=skip_adb)
        elif command == "patch_all_wipe":
            workflow.patch_all(wipe=1, skip_adb=skip_adb)
            
    except (subprocess.CalledProcessError, FileNotFoundError, RuntimeError, KeyError) as e:
        if not isinstance(e, SystemExit):
            print(f"\nAn unexpected error occurred: {e}", file=sys.stderr)
    except SystemExit:
        print("\nProcess halted by script (e.g., file not found).", file=sys.stderr)
    except KeyboardInterrupt:
        print("\nProcess cancelled by user.", file=sys.stderr)

    finally:
        print()
        
        if log_file_handle:
            print(f"--- Logging finished. Output saved to {log_file_handle.name} ---")
            sys.stdout = original_stdout
            sys.stderr = original_stderr
            log_file_handle.close()

        print("  " + "=" * 58)
        print(f"    Task [{title}] has completed.")
        print("  " + "=" * 58, "\n")
        
        if command == "clean":
            print("Press any key to exit...")
        else:
            print("Press any key to return...")

        if platform.system() == "Windows":
            os.system("pause > nul")
        else:
            input()

def advanced_menu(skip_adb):
    while True:
        os.system('cls' if os.name == 'nt' else 'clear')
        print("\n  " + "=" * 58)
        print("     LTBox - Advanced")
        print("  " + "=" * 58 + "\n")
        print("     1. Convert PRC to ROW in ROM")
        print("     2. Dump devinfo/persist from device")
        print("     3. Patch devinfo/persist to change region code")
        print("     4. Write devinfo/persist to device")
        print("     5. Detect Anti-Rollback from device")
        print("     6. Patch rollback indices in ROM")
        print("     7. Write Anti-Anti-Rollback to device")
        print("     8. Convert x files to xml (WIPE DATA)")
        print("     9. Convert x files to xml & Modify (NO WIPE)")
        print("    10. Flash firmware to device")
        print("\n    11. Clean workspace")
        print("     m. Back to Main")
        print("\n  " + "=" * 58 + "\n")
        
        choice = input("    Enter your choice (1-11, m): ").strip().lower()

        if choice == "1":
            run_task("convert", "Convert PRC to ROW in ROM", skip_adb)
        elif choice == "2":
            run_task("read_edl", "Dump devinfo/persist from device", skip_adb)
        elif choice == "3":
            run_task("edit_dp", "Patch devinfo/persist to change region code", skip_adb)
        elif choice == "4":
            run_task("write_edl", "Write devinfo/persist to device", skip_adb)
        elif choice == "5":
            run_task("read_anti_rollback", "Detect Anti-Rollback from device", skip_adb)
        elif choice == "6":
            run_task("patch_anti_rollback", "Patch rollback indices in ROM", skip_adb)
        elif choice == "7":
            run_task("write_anti_rollback", "Write Anti-Anti-Rollback to device", skip_adb)
        elif choice == "8":
            run_task("modify_xml_wipe", "Convert x files to xml (WIPE DATA)", skip_adb)
        elif choice == "9":
            run_task("modify_xml", "Convert & Modify x files to xml (NO WIPE)", skip_adb)
        elif choice == "10":
            run_task("flash_edl", "Flash firmware to device", skip_adb)
        elif choice == "11":
            run_task("clean", "Workspace Cleanup", skip_adb)
            sys.exit()
        elif choice == "m":
            return
        else:
            print("\n    [!] Invalid choice. Please enter a number from 1-11, or m.")
            if platform.system() == "Windows":
                os.system("pause > nul")
            else:
                input("Press Enter to continue...")


def main():
    skip_adb = False
    
    while True:
        skip_adb_state = "ON" if skip_adb else "OFF"
        os.system('cls' if os.name == 'nt' else 'clear')
        print("\n  " + "=" * 58)
        print("     LTBox - Main")
        print("  " + "=" * 58 + "\n")
        print(f"     1. Install ROW firmware to PRC device (WIPE DATA)")
        print(f"     2. Update ROW firmware on PRC device (NO WIPE)")
        print(f"     3. Disable OTA")
        print(f"     4. Root device")
        print(f"     5. Unroot device")
        print(f"     6. Skip ADB [{skip_adb_state}]")
        print("\n     a. Advanced")
        print("     x. Exit")
        print("\n  " + "=" * 58 + "\n")
        
        choice = input("    Enter your choice: ").strip().lower()

        if choice == "1":
            run_task("patch_all_wipe", "Install ROW firmware (WIPE DATA)", skip_adb)
        elif choice == "2":
            run_task("patch_all", "Update ROW firmware (NO WIPE)", skip_adb)
        elif choice == "3":
            run_task("disable_ota", "Disable OTA", skip_adb)
        elif choice == "4":
            run_task("root_device", "Root device", skip_adb)
        elif choice == "5":
            run_task("unroot_device", "Unroot device", skip_adb)
        elif choice == "6":
            skip_adb = not skip_adb
        elif choice == "a":
            advanced_menu(skip_adb)
        elif choice == "x":
            break
        else:
            print("\n    [!] Invalid choice.")
            if platform.system() == "Windows":
                os.system("pause > nul")
            else:
                input("Press Enter to continue...")

if __name__ == "__main__":
    setup_console()
    main()