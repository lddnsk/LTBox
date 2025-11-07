import subprocess
import sys

from ltbox.constants import *
from ltbox import utils, device, patch, actions_edl

def patch_all(wipe=0):
    if wipe == 1:
        print("--- [WIPE MODE] Starting Automated Install & Flash ROW Firmware Process ---")
    else:
        print("--- [NO WIPE MODE] Starting Automated Update & Flash ROW Firmware Process ---")
    
    print("\n" + "="*61)
    print("  STEP 1/8: Waiting for ADB Connection")
    print("="*61)
    device.wait_for_adb()
    device_model = device.get_device_model()
    if not device_model:
        raise SystemExit("Failed to get device model via ADB.")
    print("\n--- [STEP 1/8] ADB Device Found SUCCESS ---")
    
    print("\n--- [STEP 2/8] Waiting for RSA Firmware 'image' folder ---")
    prompt = (
        "Please copy the entire 'image' folder from your\n"
        "         unpacked Lenovo RSA firmware into the main directory.\n"
        r"         (Typical Location: C:\ProgramData\RSA\Download\RomFiles\...)"
    )
    utils.wait_for_directory(IMAGE_DIR, prompt)
    print("[+] 'image' folder found.")
    
    try:
        print("\n" + "="*61)
        print("  STEP 3/8: Converting Firmware (PRC to ROW) & Validating Model")
        print("="*61)
        patch.convert_images(device_model=device_model)
        print("\n--- [STEP 3/8] Firmware Conversion & Validation SUCCESS ---")

        print("\n" + "="*61)
        print("  STEP 4/8: Modifying XML Files")
        print("="*61)
        patch.modify_xml(wipe=wipe)
        print("\n--- [STEP 4/8] XML Modification SUCCESS ---")
        
        print("\n" + "="*61)
        print("  STEP 5/8: Dumping devinfo/persist for patching")
        print("="*61)
        actions_edl.read_edl()
        print("\n--- [STEP 5/8] Dump SUCCESS ---")
        
        print("\n" + "="*61)
        print("  STEP 6/8: Patching devinfo/persist")
        print("="*61)
        patch.edit_devinfo_persist()
        print("\n--- [STEP 6/8] Patching SUCCESS ---")
        
        print("\n" + "="*61)
        print("  STEP 7/8: Checking and Patching Anti-Rollback")
        print("="*61)
        actions_edl.read_anti_rollback()
        actions_edl.patch_anti_rollback()
        print("\n--- [STEP 7/8] Anti-Rollback Check/Patch SUCCESS ---")
        
        print("\n" + "="*61)
        print("  [FINAL STEP 8/8] Flashing All Images via EDL")
        print("="*61)
        print("The device will now be flashed with all modified images.")
        actions_edl.flash_edl(skip_reset_edl=True) 
        
        print("\n" + "=" * 61)
        print("  FULL PROCESS COMPLETE!")
        print("  Your device should now reboot with a patched ROW firmware.")
        print("=" * 61)

    except (subprocess.CalledProcessError, FileNotFoundError, RuntimeError, KeyError) as e:
        print("\n" + "!" * 61)
        print("  AN ERROR OCCURRED: Process Halted.")
        print(f"  Error details: {e}")
        print("!" * 61)
        sys.exit(1)
    except SystemExit as e:
        print("\n" + "!" * 61)
        print(f"  PROCESS HALTED BY SCRIPT: {e}")
        print("!" * 61)
    except KeyboardInterrupt:
        print("\n" + "!" * 61)
        print("  PROCESS CANCELLED BY USER.")
        print("!" * 61)