import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional, List, Dict

from ..constants import *
from .. import utils, device
from .xml import _ensure_params_or_fail

def _fh_loader_write_part(port, image_path, lun, start_sector, lang: Optional[Dict[str, str]] = None):
    lang = lang or {}
    if not FH_LOADER_EXE.exists():
        raise FileNotFoundError(lang.get("act_err_fh_exe_missing", "fh_loader.exe not found at {path}").format(path=FH_LOADER_EXE))
        
    port_str = f"\\\\.\\{port}"
    cmd = [
        str(FH_LOADER_EXE),
        f"--port={port_str}",
        f"--sendimage={image_path}",
        f"--lun={lun}",
        f"--start_sector={start_sector}",
        "--zlpawarehost=1",
        "--noprompt",
        "--memoryname=UFS"
    ]
    print(lang.get("act_flash_part", "[*] Flashing {name} to LUN:{lun} @ {start}...").format(name=image_path.name, lun=lun, start=start_sector))
    utils.run_command(cmd)

def read_edl(skip_adb: bool = False, skip_reset: bool = False, additional_targets: Optional[List[str]] = None, lang: Optional[Dict[str, str]] = None) -> None:
    lang = lang or {}
    print(lang.get("act_start_dump", "--- Starting Dump Process (fh_loader) ---"))
    
    dev = device.DeviceController(skip_adb=skip_adb, lang=lang)
    port = dev.setup_edl_connection()
    
    try:
        dev.load_firehose_programmer(EDL_LOADER_FILE, port)
        time.sleep(2)
    except Exception as e:
        print(lang.get("act_warn_prog_load", "[!] Warning: Programmer loading issue (might be already loaded): {e}").format(e=e))

    BACKUP_DIR.mkdir(exist_ok=True)
    
    targets = ["devinfo", "persist"]

    if additional_targets:
        targets.extend(additional_targets)
        print(lang.get("act_ext_dump_targets", "[*] Extended dump targets: {targets}").format(targets=', '.join(targets)))
    
    for target in targets:
        out_file = BACKUP_DIR / f"{target}.img"
        print(lang.get("act_prep_dump", "\n[*] Preparing to dump '{target}'...").format(target=target))
        
        try:
            params = _ensure_params_or_fail(target, lang=lang)
            print(lang.get("act_found_dump_info", "  > Found info in {xml}: LUN={lun}, Start={start}").format(xml=params['source_xml'], lun=params['lun'], start=params['start_sector']))
            
            dev.fh_loader_read_part(
                port=port,
                output_filename=str(out_file),
                lun=params['lun'],
                start_sector=params['start_sector'],
                num_sectors=params['num_sectors']
            )
            print(lang.get("act_dump_success", "[+] Successfully read '{target}' to '{file}'.").format(target=target, file=out_file.name))
            
        except (ValueError, FileNotFoundError) as e:
            print(lang.get("act_skip_dump", "[!] Skipping '{target}': {e}").format(target=target, e=e))
        except Exception as e:
            print(lang.get("act_err_dump", "[!] Failed to read '{target}': {e}").format(target=target, e=e), file=sys.stderr)

        print(lang.get("act_wait_stability", "[*] Waiting 5 seconds for stability..."))
        time.sleep(5)

    if not skip_reset:
        print(lang.get("act_reset_sys", "\n[*] Resetting device to system..."))
        dev.fh_loader_reset(port)
        print(lang.get("act_reset_sent", "[+] Reset command sent."))
        print(lang.get("act_wait_stability_long", "[*] Waiting 10 seconds for stability..."))
        time.sleep(10)
    else:
        print(lang.get("act_skip_reset", "\n[*] Skipping reset as requested (Device remains in EDL)."))

    print(lang.get("act_dump_finish", "\n--- Dump Process Finished ---"))
    print(lang.get("act_dump_saved", "[*] Files saved to: {dir}").format(dir=BACKUP_DIR.name))

def read_edl_fhloader(skip_adb: bool = False, skip_reset: bool = False, additional_targets: Optional[List[str]] = None, lang: Optional[Dict[str, str]] = None) -> None:
    return read_edl(skip_adb, skip_reset=skip_reset, additional_targets=additional_targets, lang=lang)

def write_edl(skip_reset: bool = False, skip_reset_edl: bool = False, lang: Optional[Dict[str, str]] = None) -> None:
    lang = lang or {}
    print(lang.get("act_start_write", "--- Starting Write Process (EDL) ---"))

    skip_adb_val = os.environ.get('SKIP_ADB') == '1'
    dev = device.DeviceController(skip_adb=skip_adb_val, lang=lang)

    if not OUTPUT_DP_DIR.exists():
        print(lang.get("act_err_dp_folder", "[!] Error: Patched images folder '{dir}' not found.").format(dir=OUTPUT_DP_DIR.name), file=sys.stderr)
        print(lang.get("act_err_run_patch_first", "[!] Please run 'Patch devinfo/persist' (Menu 3) first to generate the modified images."), file=sys.stderr)
        raise FileNotFoundError(lang.get("act_err_dp_folder_nf", "{dir} not found.").format(dir=OUTPUT_DP_DIR.name))
    print(lang.get("act_found_dp_folder", "[+] Found patched images folder: '{dir}'.").format(dir=OUTPUT_DP_DIR.name))

    port = dev.setup_edl_connection()

    try:
        dev.load_firehose_programmer(EDL_LOADER_FILE, port)
        time.sleep(2)
    except Exception as e:
        print(lang.get("act_warn_prog_load", "[!] Warning: Programmer loading issue: {e}").format(e=e))

    targets = ["devinfo", "persist"]

    for target in targets:
        image_path = OUTPUT_DP_DIR / f"{target}.img"

        if not image_path.exists():
            print(lang.get(f"act_skip_{target}", f"[*] '{target}.img' missing. Skipping."))
            continue

        print(f"[*] Flashing '{target}' via EDL...")

        try:
            params = _ensure_params_or_fail(target, lang=lang)
            print(lang.get("act_found_boot_info", "  > Found info: LUN={lun}, Start={start}").format(lun=params['lun'], start=params['start_sector']))
            
            dev.fh_loader_write_part(
                port=port,
                image_path=image_path,
                lun=params['lun'],
                start_sector=params['start_sector']
            )
            print(lang.get(f"act_flash_{target}_ok", f"[+] Successfully flashed '{target}'."))

        except (subprocess.CalledProcessError, FileNotFoundError, ValueError) as e:
            print(lang.get("act_err_edl_write", f"[!] An error occurred during the EDL write operation: {e}").format(e=e), file=sys.stderr)
            raise

    if not skip_reset:
        print(lang.get("act_reboot_device", "\n[*] Rebooting device..."))
        try:
            dev.fh_loader_reset(port)
        except Exception as e:
            print(lang.get("act_warn_reboot", "[!] Warning: Failed to reboot: {e}").format(e=e))
    else:
        print(lang.get("act_skip_reboot", "\n[*] Skipping reboot as requested."))

    print(lang.get("act_write_finish", "\n--- Write Process Finished ---"))

def write_anti_rollback(skip_reset: bool = False, lang: Optional[Dict[str, str]] = None) -> None:
    lang = lang or {}
    print(lang.get("act_start_arb_write", "--- Starting Anti-Rollback Write Process ---"))

    boot_img = OUTPUT_ANTI_ROLLBACK_DIR / "boot.img"
    vbmeta_img = OUTPUT_ANTI_ROLLBACK_DIR / "vbmeta_system.img"

    if not boot_img.exists() or not vbmeta_img.exists():
        print(lang.get("act_err_patched_missing", "[!] Error: Patched images not found in '{dir}'.").format(dir=OUTPUT_ANTI_ROLLBACK_DIR.name), file=sys.stderr)
        print(lang.get("act_err_run_patch_arb", "[!] Please run 'Patch Anti-Rollback' (Menu 7) first."), file=sys.stderr)
        raise FileNotFoundError(lang.get("act_err_patched_missing_exc", "Patched images not found in {dir}").format(dir=OUTPUT_ANTI_ROLLBACK_DIR.name))
    print(lang.get("act_found_arb_folder", "[+] Found patched images folder: '{dir}'.").format(dir=OUTPUT_ANTI_ROLLBACK_DIR.name))

    dev = device.DeviceController(skip_adb=True, lang=lang)
    
    print(lang.get("act_arb_write_step1", "\n--- [STEP 1] Detecting Active Slot via Fastboot ---"))
    print(lang.get("act_boot_fastboot", "[!] Please boot your device into FASTBOOT mode."))
    dev.wait_for_fastboot()

    active_slot = dev.get_active_slot_suffix_from_fastboot()
    if active_slot:
        print(lang.get("act_slot_confirmed", "[+] Active slot confirmed: {slot}").format(slot=active_slot))
    else:
        print(lang.get("act_warn_slot_fail", "[!] Warning: Active slot detection failed. Defaulting to no slot suffix."))
        active_slot = ""

    target_boot = f"boot{active_slot}"
    target_vbmeta = f"vbmeta_system{active_slot}"

    print(lang.get("act_arb_write_step2", "\n--- [STEP 2] Rebooting to EDL Mode ---"))
    print(lang.get("act_manual_edl_now", "[!] Please manually reboot your device to EDL mode now."))
    print(lang.get("act_manual_edl_hint", "(Use Key Combination or Fastboot menu if available)"))
    port = dev.wait_for_edl()
    
    try:
        dev.load_firehose_programmer(EDL_LOADER_FILE, port)
        time.sleep(2)

        print(lang.get("act_arb_write_step3", "\n--- [STEP 3] Flashing images to slot {slot} ---").format(slot=active_slot))

        print(lang.get("act_write_boot", "[*] Attempting to write '{target}' partition...").format(target=target_boot))
        params_boot = _ensure_params_or_fail(target_boot, lang=lang)
        print(lang.get("act_found_boot_info", "  > Found info: LUN={lun}, Start={start}").format(lun=params_boot['lun'], start=params_boot['start_sector']))
        dev.fh_loader_write_part(
            port=port,
            image_path=boot_img,
            lun=params_boot['lun'],
            start_sector=params_boot['start_sector']
        )
        print(lang.get("act_write_boot_ok", "[+] Successfully wrote '{target}'.").format(target=target_boot))

        print(lang.get("act_write_vbmeta", "[*] Attempting to write '{target}' partition...").format(target=target_vbmeta))
        params_vbmeta = _ensure_params_or_fail(target_vbmeta, lang=lang)
        print(lang.get("act_found_vbmeta_info", "  > Found info: LUN={lun}, Start={start}").format(lun=params_vbmeta['lun'], start=params_vbmeta['start_sector']))
        dev.fh_loader_write_part(
            port=port,
            image_path=vbmeta_img,
            lun=params_vbmeta['lun'],
            start_sector=params_vbmeta['start_sector']
        )
        print(lang.get("act_write_vbmeta_ok", "[+] Successfully wrote '{target}'.").format(target=target_vbmeta))

        if not skip_reset:
            print(lang.get("act_arb_reset", "\n[*] Operations complete. Resetting device..."))
            dev.fh_loader_reset(port)
            print(lang.get("act_reset_sent", "[+] Device reset command sent."))
        else:
            print(lang.get("act_arb_skip_reset", "\n[*] Operations complete. Skipping device reset as requested."))

    except (subprocess.CalledProcessError, FileNotFoundError, ValueError) as e:
        print(lang.get("act_err_edl_write", "[!] An error occurred during the EDL write operation: {e}").format(e=e), file=sys.stderr)
        raise
    
    print(lang.get("act_arb_write_finish", "\n--- Anti-Rollback Write Process Finished ---"))

def flash_edl(skip_reset: bool = False, skip_reset_edl: bool = False, skip_dp: bool = False, lang: Optional[Dict[str, str]] = None) -> None:
    lang = lang or {}
    print(lang.get("act_start_flash", "--- Starting Full EDL Flash Process ---"))

    skip_adb_val = os.environ.get('SKIP_ADB') == '1'
    dev = device.DeviceController(skip_adb=skip_adb_val, lang=lang)
    
    if not IMAGE_DIR.is_dir() or not any(IMAGE_DIR.iterdir()):
        print(lang.get("act_err_image_empty", "[!] Error: The '{dir}' folder is missing or empty.").format(dir=IMAGE_DIR.name))
        print(lang.get("act_err_run_xml_mod", "[!] Please run 'Modify XML for Update' (Menu 9) first."))
        raise FileNotFoundError(lang.get("act_err_image_empty_exc", "{dir} is missing or empty.").format(dir=IMAGE_DIR.name))
        
    loader_path = EDL_LOADER_FILE
    if not loader_path.exists():
        print(lang.get("act_err_loader_missing", "[!] Error: EDL Loader '{name}' not found in '{dir}' folder.").format(name=loader_path.name, dir=IMAGE_DIR.name))
        print(lang.get("act_err_copy_loader", "[!] Please copy it to the 'image' folder (from firmware)."))
        raise FileNotFoundError(lang.get("act_err_loader_missing_exc", "{name} not found in {dir}").format(name=loader_path.name, dir=IMAGE_DIR.name))

    if not skip_reset_edl:
        print("\n" + "="*61)
        print(lang.get("act_warn_overwrite_1", "  WARNING: PROCEEDING WILL OVERWRITE FILES IN YOUR 'image'"))
        print(lang.get("act_warn_overwrite_2", "           FOLDER WITH ANY PATCHED FILES YOU HAVE CREATED"))
        print(lang.get("act_warn_overwrite_3", "           (e.g., from Menu 1, 5, 7, or 9)."))
        print("="*61 + "\n")
        
        choice = ""
        while choice not in ['y', 'n']:
            choice = input(lang.get("act_ask_continue", "Are you sure you want to continue? (y/n): ")).lower().strip()

        if choice == 'n':
            print(lang.get("act_op_cancel", "[*] Operation cancelled."))
            return

    print(lang.get("act_copy_patched", "\n[*] Copying patched files to 'image' folder (overwriting)..."))
    output_folders_to_copy = [
        OUTPUT_DIR, 
        OUTPUT_ANTI_ROLLBACK_DIR,
        OUTPUT_XML_DIR
    ]
    
    copied_count = 0
    for folder in output_folders_to_copy:
        if folder.exists():
            try:
                shutil.copytree(folder, IMAGE_DIR, dirs_exist_ok=True)
                print(lang.get("act_copied_content", "  > Copied contents of '{src}' to '{dst}'.").format(src=folder.name, dst=IMAGE_DIR.name))
                copied_count += 1
            except Exception as e:
                print(lang.get("act_err_copy", "[!] Error copying files from {name}: {e}").format(name=folder.name, e=e), file=sys.stderr)
    
    if not skip_dp:
        if OUTPUT_DP_DIR.exists():
            try:
                shutil.copytree(OUTPUT_DP_DIR, IMAGE_DIR, dirs_exist_ok=True)
                print(lang.get("act_copied_dp", "  > Copied contents of '{src}' to '{dst}'.").format(src=OUTPUT_DP_DIR.name, dst=IMAGE_DIR.name))
                copied_count += 1
            except Exception as e:
                print(lang.get("act_err_copy_dp", "[!] Error copying files from {name}: {e}").format(name=OUTPUT_DP_DIR.name, e=e), file=sys.stderr)
        else:
            print(lang.get("act_skip_dp_copy", "[*] '{dir}' not found. Skipping devinfo/persist copy.").format(dir=OUTPUT_DP_DIR.name))
    else:
        print(lang.get("act_req_skip_dp", "[*] Skipping devinfo/persist copy as requested."))

    if copied_count == 0:
        print(lang.get("act_no_output_folders", "[*] No 'output*' folders found. Proceeding with files already in 'image' folder."))

    port = dev.setup_edl_connection()

    raw_xmls = [f for f in IMAGE_DIR.glob("rawprogram*.xml") if f.name != "rawprogram0.xml"]
    patch_xmls = list(IMAGE_DIR.glob("patch*.xml"))
    
    persist_write_xml = IMAGE_DIR / "rawprogram_write_persist_unsparse0.xml"
    persist_save_xml = IMAGE_DIR / "rawprogram_save_persist_unsparse0.xml"
    devinfo_write_xml = IMAGE_DIR / "rawprogram4_write_devinfo.xml"
    devinfo_original_xml = IMAGE_DIR / "rawprogram4.xml"

    has_patched_persist = (OUTPUT_DP_DIR / "persist.img").exists()
    has_patched_devinfo = (OUTPUT_DP_DIR / "devinfo.img").exists()

    if persist_write_xml.exists() and has_patched_persist and not skip_dp:
        print(lang.get("act_use_patched_persist", "[+] Using 'rawprogram_write_persist_unsparse0.xml' for persist flash (Patched)."))
        raw_xmls = [xml for xml in raw_xmls if xml.name != persist_save_xml.name]
    else:
        if persist_write_xml.exists() and any(xml.name == persist_write_xml.name for xml in raw_xmls):
             print(lang.get("act_skip_persist_flash", "[*] Skipping 'persist' flash (Not patched, preserving device data)."))
             raw_xmls = [xml for xml in raw_xmls if xml.name != persist_write_xml.name]

    if devinfo_write_xml.exists() and has_patched_devinfo and not skip_dp:
        print(lang.get("act_use_patched_devinfo", "[+] Using 'rawprogram4_write_devinfo.xml' for devinfo flash (Patched)."))
        raw_xmls = [xml for xml in raw_xmls if xml.name != devinfo_original_xml.name]
    else:
        if devinfo_write_xml.exists() and any(xml.name == devinfo_write_xml.name for xml in raw_xmls):
             print(lang.get("act_skip_devinfo_flash", "[*] Skipping 'devinfo' flash (Not patched, preserving device data)."))
             raw_xmls = [xml for xml in raw_xmls if xml.name != devinfo_write_xml.name]

    if not raw_xmls or not patch_xmls:
        print(lang.get("act_err_xml_missing", "[!] Error: 'rawprogram*.xml' (excluding rawprogram0.xml) or 'patch*.xml' files not found in '{dir}'.").format(dir=IMAGE_DIR.name))
        print(lang.get("act_err_flash_aborted", "[!] Cannot flash. Please run XML modification first."))
        raise FileNotFoundError(lang.get("act_err_xml_missing_exc", "Missing essential XML flash files in {dir}").format(dir=IMAGE_DIR.name))
        
    print(lang.get("act_flash_step1", "\n--- [STEP 1] Flashing all images via rawprogram (fh_loader) ---"))
    
    try:
        dev.edl_rawprogram(loader_path, "UFS", raw_xmls, patch_xmls, port)
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        print(lang.get("act_err_main_flash", "[!] An error occurred during main flash: {e}").format(e=e), file=sys.stderr)
        print(lang.get("act_warn_unstable", "[!] The device may be in an unstable state. Do not reboot manually."))
        raise
        
    print(lang.get("act_flash_step2", "\n--- [STEP 2] Cleaning up temporary images ---"))
    if not skip_dp:
        try:
            (IMAGE_DIR / "devinfo.img").unlink(missing_ok=True)
            (IMAGE_DIR / "persist.img").unlink(missing_ok=True)
            print(lang.get("act_removed_temp_imgs", "[+] Removed devinfo.img and persist.img from 'image' folder."))
        except OSError as e:
            print(lang.get("act_err_clean_imgs", "[!] Error cleaning up images: {e}").format(e=e), file=sys.stderr)

    if not skip_reset:
        print(lang.get("act_flash_step3", "\n--- [STEP 3] Final step: Resetting device to system ---"))
        try:
            print(lang.get("act_wait_stability", "[*] Waiting 5 seconds for stability..."))
            time.sleep(5)
            
            print(lang.get("act_reset_sys", "[*] Attempting to reset device via fh_loader..."))
            dev.fh_loader_reset(port)
            print(lang.get("act_reset_sent", "[+] Device reset command sent."))
        except (subprocess.CalledProcessError, FileNotFoundError, Exception) as e:
             print(lang.get("act_err_reset", "[!] Failed to reset device: {e}").format(e=e), file=sys.stderr)
    else:
        print(lang.get("act_skip_final_reset", "[*] Skipping final device reset as requested."))

    if not skip_reset:
        print(lang.get("act_flash_finish", "\n--- Full EDL Flash Process Finished ---"))