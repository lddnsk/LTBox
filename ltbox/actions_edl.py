import os
import platform
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

from ltbox.constants import *
from ltbox import utils, edl, avb, device

def read_edl():
    print("--- Starting EDL Read Process ---")
    
    device.reboot_to_edl()
    print("[*] Waiting for 10 seconds for device to enter EDL mode...")
    time.sleep(10)
    
    BACKUP_DIR.mkdir(exist_ok=True)
    devinfo_out = BACKUP_DIR / "devinfo.img"
    persist_out = BACKUP_DIR / "persist.img"

    print(f"--- Waiting for EDL Loader File ---")
    required_files = [EDL_LOADER_FILENAME]
    prompt = (
        f"[STEP 1] Place the EDL loader file ('{EDL_LOADER_FILENAME}')\n"
        f"         into the '{IMAGE_DIR.name}' folder to proceed."
    )
    utils.wait_for_files(IMAGE_DIR, required_files, prompt)
    print(f"[+] Loader file '{EDL_LOADER_FILE.name}' found in '{IMAGE_DIR.name}'.")

    edl.wait_for_edl()
        
    print("\n[*] Attempting to read 'devinfo' partition...")
    try:
        edl.edl_read_part(EDL_LOADER_FILE, "devinfo", devinfo_out)
        print(f"[+] Successfully read 'devinfo' to '{devinfo_out}'.")
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        print(f"[!] Failed to read 'devinfo': {e}", file=sys.stderr)

    print("\n[*] Attempting to read 'persist' partition...")
    try:
        edl.edl_read_part(EDL_LOADER_FILE, "persist", persist_out)
        print(f"[+] Successfully read 'persist' to '{persist_out}'.")
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        print(f"[!] Failed to read 'persist': {e}", file=sys.stderr)

    print(f"\n--- EDL Read Process Finished ---")
    print(f"[*] Files have been saved to the '{BACKUP_DIR.name}' folder.")
    print(f"[*] You can now run 'Patch devinfo/persist' (Menu 3) to patch them.")


def write_edl(skip_reset=False, skip_reset_edl=False):
    print("--- Starting EDL Write Process ---")

    if not OUTPUT_DP_DIR.exists():
        print(f"[!] Error: Patched images folder '{OUTPUT_DP_DIR.name}' not found.", file=sys.stderr)
        print("[!] Please run 'Patch devinfo/persist' (Menu 3) first to generate the modified images.", file=sys.stderr)
        raise FileNotFoundError(f"{OUTPUT_DP_DIR.name} not found.")
    print(f"[+] Found patched images folder: '{OUTPUT_DP_DIR.name}'.")

    if not skip_reset_edl:
        print(f"--- Waiting for EDL Loader File ---")
        required_files = [EDL_LOADER_FILENAME]
        prompt = (
            f"[STEP 1] Place the EDL loader file ('{EDL_LOADER_FILENAME}')\n"
            f"         into the '{IMAGE_DIR.name}' folder to proceed."
        )
        IMAGE_DIR.mkdir(exist_ok=True) 
        utils.wait_for_files(IMAGE_DIR, required_files, prompt)
        print(f"[+] Loader file '{EDL_LOADER_FILE.name}' found in '{IMAGE_DIR.name}'.")

        edl.wait_for_edl()

    patched_devinfo = OUTPUT_DP_DIR / "devinfo.img"
    patched_persist = OUTPUT_DP_DIR / "persist.img"

    if not patched_devinfo.exists() and not patched_persist.exists():
         print(f"[!] Error: Neither 'devinfo.img' nor 'persist.img' found inside '{OUTPUT_DP_DIR.name}'.", file=sys.stderr)
         raise FileNotFoundError(f"No patched images found in {OUTPUT_DP_DIR.name}.")

    commands_executed = False
    
    try:
        if patched_devinfo.exists():
            print(f"\n[*] Attempting to write 'devinfo' partition with '{patched_devinfo.name}'...")
            edl.edl_write_part(EDL_LOADER_FILE, "devinfo", patched_devinfo)
            print("[+] Successfully wrote 'devinfo'.")
            commands_executed = True
        else:
            print(f"\n[*] 'devinfo.img' not found in '{OUTPUT_DP_DIR.name}'. Skipping write.")

        if patched_persist.exists():
            print(f"\n[*] Attempting to write 'persist' partition with '{patched_persist.name}'...")
            edl.edl_write_part(EDL_LOADER_FILE, "persist", patched_persist)
            print("[+] Successfully wrote 'persist'.")
            commands_executed = True
        else:
            print(f"\n[*] 'persist.img' not found in '{OUTPUT_DP_DIR.name}'. Skipping write.")

        if commands_executed and not skip_reset:
            print("\n[*] Operations complete. Resetting device...")
            edl.edl_reset(EDL_LOADER_FILE)
            print("[+] Device reset command sent.")
        elif skip_reset:
            print("\n[*] Operations complete. Skipping device reset as requested.")
        else:
            print("\n[!] No partitions were written. Skipping reset.")

    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        print(f"[!] An error occurred during the EDL write/reset operation: {e}", file=sys.stderr)
        raise

    if not skip_reset:
        print("\n" + "="*61)
        print("  FRIENDLY REMINDER:")
        print("  Please ensure you have a safe backup of your original")
        print("  'devinfo.img' and 'persist.img' files before proceeding")
        print("  with any manual flashing operations.")
        print("="*61)

    print("\n--- EDL Write Process Finished ---")

def _compare_rollback_indices():
    print("\n--- [STEP 1] Dumping Current Firmware via EDL ---")
    INPUT_CURRENT_DIR.mkdir(exist_ok=True)
    boot_out = INPUT_CURRENT_DIR / "boot.img"
    vbmeta_out = INPUT_CURRENT_DIR / "vbmeta_system.img"

    print(f"--- Waiting for EDL Loader File ---")
    required_loader = [EDL_LOADER_FILENAME]
    loader_prompt = (
        f"[REQUIRED] Place the EDL loader file ('{EDL_LOADER_FILENAME}')\n"
        f"         into the '{IMAGE_DIR.name}' folder to dump current firmware."
    )
    utils.wait_for_files(IMAGE_DIR, required_loader, loader_prompt)
    print(f"[+] Loader file '{EDL_LOADER_FILE.name}' found in '{IMAGE_DIR.name}'.")

    edl.wait_for_edl()
        
    print("\n[*] Attempting to read 'boot' partition...")
    try:
        edl.edl_read_part(EDL_LOADER_FILE, "boot", boot_out)
        print(f"[+] Successfully read 'boot' to '{boot_out}'.")
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        print(f"[!] Failed to read 'boot': {e}", file=sys.stderr)
        raise 

    print("\n[*] Attempting to read 'vbmeta_system' partition...")
    try:
        edl.edl_read_part(EDL_LOADER_FILE, "vbmeta_system", vbmeta_out)
        print(f"[+] Successfully read 'vbmeta_system' to '{vbmeta_out}'.")
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        print(f"[!] Failed to read 'vbmeta_system': {e}", file=sys.stderr)
        raise 
        
    print("\n--- [STEP 1] Dump complete ---")
    
    print("\n--- [STEP 2] Comparing Rollback Indices ---")
    print("\n[*] Extracting current ROM's rollback indices...")
    current_boot_rb = 0
    current_vbmeta_rb = 0
    try:
        current_boot_info = avb.extract_image_avb_info(INPUT_CURRENT_DIR / "boot.img")
        current_boot_rb = int(current_boot_info.get('rollback', '0'))
        
        current_vbmeta_info = avb.extract_image_avb_info(INPUT_CURRENT_DIR / "vbmeta_system.img")
        current_vbmeta_rb = int(current_vbmeta_info.get('rollback', '0'))
    except Exception as e:
        print(f"[!] Error reading current image info: {e}. Please check files.", file=sys.stderr)
        return 'ERROR', 0, 0

    print(f"  > Current ROM's Boot Index: {current_boot_rb}")
    print(f"  > Current ROM's VBMeta System Index: {current_vbmeta_rb}")

    print("\n[*] Extracting new ROM's rollback indices (from 'image' folder)...")
    new_boot_img = IMAGE_DIR / "boot.img"
    new_vbmeta_img = IMAGE_DIR / "vbmeta_system.img"

    if not new_boot_img.exists() or not new_vbmeta_img.exists():
        print(f"[!] Error: 'boot.img' or 'vbmeta_system.img' not found in '{IMAGE_DIR.name}' folder.")
        return 'MISSING_NEW', 0, 0
        
    new_boot_rb = 0
    new_vbmeta_rb = 0
    try:
        new_boot_info = avb.extract_image_avb_info(new_boot_img)
        new_boot_rb = int(new_boot_info.get('rollback', '0'))
        
        new_vbmeta_info = avb.extract_image_avb_info(new_vbmeta_img)
        new_vbmeta_rb = int(new_vbmeta_info.get('rollback', '0'))
    except Exception as e:
        print(f"[!] Error reading new image info: {e}. Please check files.", file=sys.stderr)
        return 'ERROR', 0, 0

    print(f"  > New ROM's Boot Index: {new_boot_rb}")
    print(f"  > New ROM's VBMeta System Index: {new_vbmeta_rb}")

    if new_boot_rb < current_boot_rb or new_vbmeta_rb < current_vbmeta_rb:
        print("\n[!] Downgrade detected! Anti-Rollback patching is REQUIRED.")
        return 'NEEDS_PATCH', current_boot_rb, current_vbmeta_rb
    else:
        print("\n[+] Indices are same or higher. No Anti-Rollback patch needed.")
        return 'MATCH', 0, 0

def read_anti_rollback():
    print("--- Anti-Rollback Status Check ---")
    utils.check_dependencies()
    
    try:
        status, _, _ = _compare_rollback_indices()
        print(f"\n--- Status Check Complete: {status} ---")
    except Exception as e:
        print(f"\n[!] An error occurred during status check: {e}", file=sys.stderr)

def patch_anti_rollback():
    print("--- Anti-Rollback Patcher ---")
    utils.check_dependencies()

    if OUTPUT_ANTI_ROLLBACK_DIR.exists():
        shutil.rmtree(OUTPUT_ANTI_ROLLBACK_DIR)
    OUTPUT_ANTI_ROLLBACK_DIR.mkdir(exist_ok=True)
    
    try:
        status, current_boot_rb, current_vbmeta_rb = _compare_rollback_indices()

        if status != 'NEEDS_PATCH':
            print("\n[!] No patching is required or files are missing. Aborting patch.")
            return

        print("\n--- [STEP 3] Patching New ROM ---")
        
        avb.patch_chained_image_rollback(
            image_name="boot.img",
            current_rb_index=current_boot_rb,
            new_image_path=(IMAGE_DIR / "boot.img"),
            patched_image_path=(OUTPUT_ANTI_ROLLBACK_DIR / "boot.img")
        )
        
        print("-" * 20)
        
        avb.patch_vbmeta_image_rollback(
            image_name="vbmeta_system.img",
            current_rb_index=current_vbmeta_rb,
            new_image_path=(IMAGE_DIR / "vbmeta_system.img"),
            patched_image_path=(OUTPUT_ANTI_ROLLBACK_DIR / "vbmeta_system.img")
        )

        print("\n" + "=" * 61)
        print("  SUCCESS!")
        print(f"  Anti-rollback patched images are in '{OUTPUT_ANTI_ROLLBACK_DIR.name}'.")
        print("  You can now run 'Write Anti-Rollback' (Menu 8).")
        print("=" * 61)

    except Exception as e:
        print(f"\n[!] An error occurred during patching: {e}", file=sys.stderr)
        shutil.rmtree(OUTPUT_ANTI_ROLLBACK_DIR) 

def write_anti_rollback(skip_reset=False):
    print("--- Starting Anti-Rollback Write Process ---")

    boot_img = OUTPUT_ANTI_ROLLBACK_DIR / "boot.img"
    vbmeta_img = OUTPUT_ANTI_ROLLBACK_DIR / "vbmeta_system.img"

    if not boot_img.exists() or not vbmeta_img.exists():
        print(f"[!] Error: Patched images not found in '{OUTPUT_ANTI_ROLLBACK_DIR.name}'.", file=sys.stderr)
        print("[!] Please run 'Patch Anti-Rollback' (Menu 7) first.", file=sys.stderr)
        raise FileNotFoundError(f"Patched images not found in {OUTPUT_ANTI_ROLLBACK_DIR.name}")
    print(f"[+] Found patched images folder: '{OUTPUT_ANTI_ROLLBACK_DIR.name}'.")

    if not skip_reset:
        print(f"--- Waiting for EDL Loader File ---")
        required_files = [EDL_LOADER_FILENAME]
        prompt = (
            f"[STEP 1] Place the EDL loader file ('{EDL_LOADER_FILENAME}')\n"
            f"         into the '{IMAGE_DIR.name}' folder to proceed."
        )
        IMAGE_DIR.mkdir(exist_ok=True) 
        utils.wait_for_files(IMAGE_DIR, required_files, prompt)
        print(f"[+] Loader file '{EDL_LOADER_FILE.name}' found in '{IMAGE_DIR.name}'.")

        edl.wait_for_edl()
    
    try:
        print(f"\n[*] Attempting to write 'boot' partition...")
        edl.edl_write_part(EDL_LOADER_FILE, "boot", boot_img)
        print("[+] Successfully wrote 'boot'.")

        print(f"\n[*] Attempting to write 'vbmeta_system' partition...")
        edl.edl_write_part(EDL_LOADER_FILE, "vbmeta_system", vbmeta_img)
        print("[+] Successfully wrote 'vbmeta_system'.")

        if not skip_reset:
            print("\n[*] Operations complete. Resetting device...")
            edl.edl_reset(EDL_LOADER_FILE)
            print("[+] Device reset command sent.")
        else:
            print("\n[*] Operations complete. Skipping device reset as requested.")

    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        print(f"[!] An error occurred during the EDL write operation: {e}", file=sys.stderr)
        raise
    
    print("\n--- Anti-Rollback Write Process Finished ---")

def flash_edl(skip_reset=False, skip_reset_edl=False):
    print("--- Starting Full EDL Flash Process ---")
    
    if not IMAGE_DIR.is_dir() or not any(IMAGE_DIR.iterdir()):
        print(f"[!] Error: The '{IMAGE_DIR.name}' folder is missing or empty.")
        print("[!] Please run 'Modify XML for Update' (Menu 9) first.")
        raise FileNotFoundError(f"{IMAGE_DIR.name} is missing or empty.")
        
    loader_path = EDL_LOADER_FILE_IMAGE
    if not loader_path.exists():
        print(f"[!] Error: EDL Loader '{loader_path.name}' not found in '{IMAGE_DIR.name}' folder.")
        print("[!] Please copy it to the 'image' folder (from firmware).")
        raise FileNotFoundError(f"{loader_path.name} not found in {IMAGE_DIR.name}")

    if not skip_reset_edl:
        print("\n" + "="*61)
        print("  WARNING: PROCEEDING WILL OVERWRITE FILES IN YOUR 'image'")
        print("           FOLDER WITH ANY PATCHED FILES YOU HAVE CREATED")
        print("           (e.g., from Menu 1, 5, 7, or 9).")
        print("="*61 + "\n")
        
        choice = ""
        while choice not in ['y', 'n']:
            choice = input("Are you sure you want to continue? (y/n): ").lower().strip()

        if choice == 'n':
            print("[*] Operation cancelled.")
            return

    print("\n[*] Copying patched files to 'image' folder (overwriting)...")
    output_folders_to_copy = [
        OUTPUT_DIR, 
        OUTPUT_ROOT_DIR, 
        OUTPUT_ANTI_ROLLBACK_DIR,
        OUTPUT_XML_DIR 
    ]
    
    copied_count = 0
    for folder in output_folders_to_copy:
        if folder.exists():
            try:
                shutil.copytree(folder, IMAGE_DIR, dirs_exist_ok=True)
                print(f"  > Copied contents of '{folder.name}' to '{IMAGE_DIR.name}'.")
                copied_count += 1
            except Exception as e:
                print(f"[!] Error copying files from {folder.name}: {e}", file=sys.stderr)
    
    if copied_count == 0:
        print("[*] No 'output*' folders found. Proceeding with files already in 'image' folder.")
    
    edl.wait_for_edl()
    
    print("\n--- [STEP 1] Flashing main firmware via rawprogram ---")
    raw_xmls = list(IMAGE_DIR.glob("rawprogram*.xml"))
    patch_xmls = list(IMAGE_DIR.glob("patch*.xml"))
    
    if not raw_xmls or not patch_xmls:
        print(f"[!] Error: 'rawprogram*.xml' or 'patch*.xml' files not found in '{IMAGE_DIR.name}'.")
        print(f"[!] Cannot flash. Please run XML modification first.")
        raise FileNotFoundError(f"Missing essential XML flash files in {IMAGE_DIR.name}")
        
    try:
        edl.edl_rawprogram(loader_path, "UFS", raw_xmls, patch_xmls)
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        print(f"[!] An error occurred during main flash: {e}", file=sys.stderr)
        print("[!] The device may be in an unstable state. Do not reboot manually.")
        raise
        
    print("\n--- [STEP 2] Flashing patched devinfo/persist ---")
    
    patched_devinfo = OUTPUT_DP_DIR / "devinfo.img"
    patched_persist = OUTPUT_DP_DIR / "persist.img"

    if not OUTPUT_DP_DIR.exists() or (not patched_devinfo.exists() and not patched_persist.exists()):
        print(f"[*] '{OUTPUT_DP_DIR.name}' not found or is empty. Skipping devinfo/persist flash.")
    else:
        print("[*] 'output_dp' folder found. Proceeding to flash devinfo/persist...")
        
        if not skip_reset_edl:
            print("\n[*] Resetting device back into EDL mode for devinfo/persist flash...")
            try:
                edl.edl_reset(loader_path, mode="edl")
                print("[+] Device reset-to-EDL command sent.")
            except Exception as e:
                 print(f"[!] Failed to reset device to EDL: {e}", file=sys.stderr)
                 print("[!] Please manually reboot to EDL mode.")
            
            edl.wait_for_edl() 
        
        write_edl(skip_reset=True, skip_reset_edl=True)

    print("\n--- [STEP 3] Flashing patched Anti-Rollback images ---")
    arb_boot = OUTPUT_ANTI_ROLLBACK_DIR / "boot.img"
    arb_vbmeta = OUTPUT_ANTI_ROLLBACK_DIR / "vbmeta_system.img"

    if not OUTPUT_ANTI_ROLLBACK_DIR.exists() or (not arb_boot.exists() and not arb_vbmeta.exists()):
        print(f"[*] '{OUTPUT_ANTI_ROLLBACK_DIR.name}' not found or is empty. Skipping Anti-Rollback flash.")
    else:
        print(f"[*] '{OUTPUT_ANTI_ROLLBACK_DIR.name}' found. Proceeding to flash Anti-Rollback images...")
        if skip_reset_edl:
             print("[*] Assuming device is still in EDL mode from previous step...")
        else:
            print("\n[!] CRITICAL: This flow is not intended to be run manually.")
            print("[!] Please use the 'Patch and Flash' (Menu 1) option.")
            
        write_anti_rollback(skip_reset=True)

    if not skip_reset:
        print("\n[*] Final step: Resetting device to system...")
        try:
            edl.edl_reset(loader_path)
            print("[+] Device reset command sent.")
        except Exception as e:
             print(f"[!] Failed to reset device: {e}", file=sys.stderr)
    else:
        print("[*] Skipping final device reset as requested.")

    if not skip_reset:
        print("\n--- Full EDL Flash Process Finished ---")