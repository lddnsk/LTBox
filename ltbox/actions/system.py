import subprocess
from typing import Optional, Dict

from ..constants import *
from .. import utils, device

def detect_active_slot_robust(dev: device.DeviceController, skip_adb: bool, lang: Optional[Dict[str, str]] = None) -> Optional[str]:
    lang = lang or {}
    active_slot = None

    if not skip_adb:
        try:
            active_slot = dev.get_active_slot_suffix()
        except Exception:
            pass

    if not active_slot:
        print(lang.get("act_slot_adb_fail", "\n[!] Active slot not detected via ADB. Trying Fastboot..."))
        
        if not skip_adb:
            print(lang.get("act_reboot_bootloader", "[*] Rebooting to Bootloader..."))
            try:
                dev.reboot_to_bootloader()
            except Exception as e:
                print(lang.get("act_err_reboot_bl", "[!] Failed to reboot to bootloader: {e}").format(e=e))
        else:
            print("\n" + "="*60)
            print(lang.get("act_manual_fastboot", "  [ACTION REQUIRED] Please manually boot into FASTBOOT mode."))
            print("="*60 + "\n")

        dev.wait_for_fastboot()
        active_slot = dev.get_active_slot_suffix_from_fastboot()

        if not skip_adb:
            print(lang.get("act_slot_detected_sys", "[*] Slot detected. Rebooting to System to prepare for EDL..."))
            dev.fastboot_reboot_system()
            print(lang.get("act_wait_adb", "[*] Waiting for ADB connection..."))
            dev.wait_for_adb()
        else:
            print("\n" + "="*60)
            print(lang.get("act_detect_complete", "  [ACTION REQUIRED] Detection complete."))
            print(lang.get("act_manual_edl", "  [ACTION REQUIRED] Please manually boot your device into EDL mode."))
            print("="*60 + "\n")

    return active_slot

def disable_ota(skip_adb: bool = False, lang: Optional[Dict[str, str]] = None) -> None:
    lang = lang or {}
    dev = device.DeviceController(skip_adb=skip_adb, lang=lang)
    if dev.skip_adb:
        print(lang.get("act_ota_skip_adb", "[!] 'Disable OTA' was skipped as requested by Skip ADB setting."))
        return
    
    print(lang.get("act_start_ota", "--- Starting Disable OTA Process ---"))
    
    print("\n" + "="*61)
    print(lang.get("act_ota_step1", "  STEP 1/2: Waiting for ADB Connection"))
    print("="*61)
    try:
        dev.wait_for_adb()
        print(lang.get("act_adb_ok", "[+] ADB device connected."))
    except Exception as e:
        print(lang.get("act_err_wait_adb", "[!] Error waiting for ADB device: {e}").format(e=e), file=sys.stderr)
        raise

    print("\n" + "="*61)
    print(lang.get("act_ota_step2", "  STEP 2/2: Disabling Lenovo OTA Service"))
    print("="*61)
    
    command = [
        str(ADB_EXE), 
        "shell", "pm", "disable-user", "--user", "0", "com.lenovo.ota"
    ]
    
    print(lang.get("act_run_cmd", "[*] Running command: {cmd}").format(cmd=' '.join(command)))
    try:
        result = utils.run_command(command, capture=True)
        if "disabled" in result.stdout.lower() or "already disabled" in result.stdout.lower():
            print(lang.get("act_ota_disabled", "[+] Success: OTA service (com.lenovo.ota) is now disabled."))
            print(result.stdout.strip())
        else:
            print(lang.get("act_ota_unexpected", "[!] Command executed, but result was unexpected."))
            print(f"Stdout: {result.stdout.strip()}")
            if result.stderr:
                print(f"Stderr: {result.stderr.strip()}", file=sys.stderr)
    except Exception as e:
        print(lang.get("act_err_ota_cmd", "[!] An error occurred while running the command: {e}").format(e=e), file=sys.stderr)
        raise

    print(lang.get("act_ota_finished", "\n--- Disable OTA Process Finished ---"))