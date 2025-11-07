import platform
import sys
import os
import time

from ltbox.constants import *
from ltbox import utils

# --- ADB Device Handling ---
def wait_for_adb():
    print("\n--- WAITING FOR ADB DEVICE ---")
    print("[!] Please enable USB Debugging on your device, connect it via USB.")
    print("[!] A 'Allow USB debugging?' prompt will appear on your device.")
    print("[!] Please check 'Always allow from this computer' and tap 'OK'.")
    try:
        utils.run_command([str(ADB_EXE), "wait-for-device"])
        print("[+] ADB device connected.")
    except Exception as e:
        print(f"[!] Error waiting for ADB device: {e}", file=sys.stderr)
        raise

def get_device_model():
    print("[*] Getting device model via ADB...")
    try:
        result = utils.run_command([str(ADB_EXE), "shell", "getprop", "ro.product.model"], capture=True)
        model = result.stdout.strip()
        if not model:
            print("[!] Could not get device model. Is the device authorized?")
            return None
        print(f"[+] Found device model: {model}")
        return model
    except Exception as e:
        print(f"[!] Error getting device model: {e}", file=sys.stderr)
        print("[!] Please ensure the device is connected and authorized.")
        return None

def reboot_to_edl():
    print("[*] Attempting to reboot device to EDL mode via ADB...")
    try:
        utils.run_command([str(ADB_EXE), "reboot", "edl"])
        print("[+] Reboot command sent. Please wait for the device to enter EDL mode.")
    except Exception as e:
        print(f"[!] Failed to send reboot command: {e}", file=sys.stderr)
        print("[!] Please reboot to EDL manually if it fails.")