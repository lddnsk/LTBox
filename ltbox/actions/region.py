import os
import platform
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any

from ..constants import *
from .. import utils, device, imgpatch

def convert_images(device_model: Optional[str] = None, skip_adb: bool = False, lang: Optional[Dict[str, str]] = None) -> None:
    lang = lang or {}
    utils.check_dependencies(lang=lang)
    
    print(lang.get("act_conv_start", "--- Starting vendor_boot & vbmeta conversion process ---"))

    print(lang.get("act_clean_old", "[*] Cleaning up old folders..."))
    if OUTPUT_DIR.exists():
        shutil.rmtree(OUTPUT_DIR)
    print()

    print(lang.get("act_wait_vb_vbmeta", "--- Waiting for vendor_boot.img and vbmeta.img ---"))
    IMAGE_DIR.mkdir(exist_ok=True)
    required_files = ["vendor_boot.img", "vbmeta.img"]
    prompt = lang.get("act_prompt_vb_vbmeta", 
        "[STEP 1] Place the required firmware files for conversion\n"
        f"         (e.g., from your PRC firmware) into the '{IMAGE_DIR.name}' folder."
    ).format(name=IMAGE_DIR.name)
    utils.wait_for_files(IMAGE_DIR, required_files, prompt, lang=lang)
    
    vendor_boot_src = IMAGE_DIR / "vendor_boot.img"
    vbmeta_src = IMAGE_DIR / "vbmeta.img"

    print(lang.get("act_backup_orig", "--- Backing up original images ---"))
    vendor_boot_bak = BASE_DIR / "vendor_boot.bak.img"
    vbmeta_bak = BASE_DIR / "vbmeta.bak.img"
    
    try:
        shutil.copy(vendor_boot_src, vendor_boot_bak)
        shutil.copy(vbmeta_src, vbmeta_bak)
        print(lang.get("act_backup_complete", "[+] Backup complete.\n"))
    except (IOError, OSError) as e:
        print(lang.get("act_err_copy_input", "[!] Failed to copy input files: {e}").format(e=e), file=sys.stderr)
        raise

    print(lang.get("act_start_conv", "--- Starting PRC/ROW Conversion ---"))
    imgpatch.edit_vendor_boot(str(vendor_boot_bak), lang=lang)

    vendor_boot_prc = BASE_DIR / "vendor_boot_prc.img"
    print(lang.get("act_verify_conv", "\n[*] Verifying conversion result..."))
    if not vendor_boot_prc.exists():
        print(lang.get("act_err_vb_prc_missing", "[!] 'vendor_boot_prc.img' was not created. No changes made."))
        raise FileNotFoundError(lang.get("act_err_vb_prc_not_created", "vendor_boot_prc.img not created"))
    print(lang.get("act_conv_success", "[+] Conversion to PRC successful.\n"))

    print(lang.get("act_extract_info", "--- Extracting image information ---"))
    vbmeta_info = imgpatch.extract_image_avb_info(vbmeta_bak, lang=lang)
    vendor_boot_info = imgpatch.extract_image_avb_info(vendor_boot_bak, lang=lang)
    print(lang.get("act_info_extracted", "[+] Information extracted.\n"))

    if device_model and not skip_adb:
        print(lang.get("act_val_model", "[*] Validating firmware against device model '{model}'...").format(model=device_model))
        fingerprint_key = "com.android.build.vendor_boot.fingerprint"
        if fingerprint_key in vendor_boot_info:
            fingerprint = vendor_boot_info[fingerprint_key]
            print(lang.get("act_found_fp", "  > Found firmware fingerprint: {fp}").format(fp=fingerprint))
            if device_model in fingerprint:
                print(lang.get("act_model_match", "[+] Success: Device model '{model}' found in firmware fingerprint.").format(model=device_model))
            else:
                print(lang.get("act_model_mismatch", "[!] ERROR: Device model '{model}' NOT found in firmware fingerprint.").format(model=device_model))
                print(lang.get("act_rom_mismatch_abort", "[!] The provided ROM does not match your device model. Aborting."))
                raise SystemExit(lang.get("act_err_firmware_mismatch", "Firmware model mismatch"))
        else:
            print(lang.get("act_warn_fp_missing", "[!] Warning: Could not find fingerprint property '{key}' in vendor_boot.").format(key=fingerprint_key))
            print(lang.get("act_skip_val", "[!] Skipping model validation."))
    
    print(lang.get("act_add_footer_vb", "--- Adding Hash Footer to vendor_boot ---"))
    
    for key in ['partition_size', 'name', 'rollback', 'salt']:
        if key not in vendor_boot_info:
            if key == 'partition_size' and 'data_size' in vendor_boot_info:
                 vendor_boot_info['partition_size'] = vendor_boot_info['data_size']
            else:
                raise KeyError(lang.get("act_err_avb_key_missing", "Could not find '{key}' in '{name}' AVB info.").format(key=key, name=vendor_boot_bak.name))

    add_hash_footer_cmd = [
        str(PYTHON_EXE), str(AVBTOOL_PY), "add_hash_footer",
        "--image", str(vendor_boot_prc),
        "--partition_size", vendor_boot_info['partition_size'],
        "--partition_name", vendor_boot_info['name'],
        "--rollback_index", vendor_boot_info['rollback'],
        "--salt", vendor_boot_info['salt']
    ]
    
    if 'props_args' in vendor_boot_info:
        add_hash_footer_cmd.extend(vendor_boot_info['props_args'])
        print(lang.get("act_restore_props", "[+] Restoring {count} properties for vendor_boot.").format(count=len(vendor_boot_info['props_args']) // 2))

    if 'flags' in vendor_boot_info:
        add_hash_footer_cmd.extend(["--flags", vendor_boot_info.get('flags', '0')])
        print(lang.get("act_restore_flags", "[+] Restoring flags for vendor_boot: {flags}").format(flags=vendor_boot_info.get('flags', '0')))

    utils.run_command(add_hash_footer_cmd)
    
    vbmeta_pubkey = vbmeta_info.get('pubkey_sha1')
    key_file = KEY_MAP.get(vbmeta_pubkey) 

    print(lang.get("act_remake_vbmeta", "--- Remaking vbmeta.img ---"))
    print(lang.get("act_verify_vbmeta_key", "[*] Verifying vbmeta key..."))
    if not key_file:
        print(lang.get("act_err_vbmeta_key_mismatch", "[!] Public key SHA1 '{key}' from vbmeta did not match known keys. Aborting.").format(key=vbmeta_pubkey))
        raise KeyError(lang.get("act_err_unknown_key", "Unknown vbmeta public key: {key}").format(key=vbmeta_pubkey))
    print(lang.get("act_key_matched", "[+] Matched {name}.\n").format(name=key_file.name))

    print(lang.get("act_remaking_vbmeta", "[*] Remaking 'vbmeta.img' using descriptors from backup..."))
    vbmeta_img = BASE_DIR / "vbmeta.img"
    remake_cmd = [
        str(PYTHON_EXE), str(AVBTOOL_PY), "make_vbmeta_image",
        "--output", str(vbmeta_img),
        "--key", str(key_file),
        "--algorithm", vbmeta_info['algorithm'],
        "--padding_size", "8192",
        "--flags", vbmeta_info.get('flags', '0'),
        "--rollback_index", vbmeta_info.get('rollback', '0'),
        "--include_descriptors_from_image", str(vbmeta_bak),
        "--include_descriptors_from_image", str(vendor_boot_prc) 
    ]
        
    utils.run_command(remake_cmd)
    print()

    print(lang.get("act_finalize", "--- Finalizing ---"))
    print(lang.get("act_rename_final", "[*] Renaming final images..."))
    final_vendor_boot = BASE_DIR / "vendor_boot.img"
    shutil.move(BASE_DIR / "vendor_boot_prc.img", final_vendor_boot)

    final_images = [final_vendor_boot, BASE_DIR / "vbmeta.img"]

    print(lang.get("act_move_final", "\n[*] Moving final images to '{dir}' folder...").format(dir=OUTPUT_DIR.name))
    OUTPUT_DIR.mkdir(exist_ok=True)
    for img in final_images:
        if img.exists(): 
            shutil.move(img, OUTPUT_DIR / img.name)

    print(lang.get("act_move_backup", "\n[*] Moving backup files to '{dir}' folder...").format(dir=BACKUP_DIR.name))
    BACKUP_DIR.mkdir(exist_ok=True)
    for bak_file in BASE_DIR.glob("*.bak.img"):
        shutil.move(bak_file, BACKUP_DIR / bak_file.name)
    print()

    print("=" * 61)
    print(lang.get("act_success", "  SUCCESS!"))
    print(lang.get("act_final_saved", "  Final images have been saved to the '{dir}' folder.").format(dir=OUTPUT_DIR.name))
    print("=" * 61)

def select_country_code(prompt_message: str = "Please select a country from the list below:", lang: Optional[Dict[str, str]] = None) -> str:
    lang = lang or {}
    print(lang.get("act_prompt_msg", "\n--- {msg} ---").format(msg=prompt_message.upper()))

    if not COUNTRY_CODES:
        print(lang.get("act_err_codes_missing", "[!] Error: COUNTRY_CODES not found in constants.py. Aborting."), file=sys.stderr)
        raise ImportError(lang.get("act_err_codes_missing_exc", "COUNTRY_CODES missing from constants.py"))

    sorted_countries = sorted(COUNTRY_CODES.items(), key=lambda item: item[1])
    
    num_cols = 3
    col_width = 38 
    
    line_width = col_width * num_cols
    print("-" * line_width)
    
    for i in range(0, len(sorted_countries), num_cols):
        line = []
        for j in range(num_cols):
            idx = i + j
            if idx < len(sorted_countries):
                code, name = sorted_countries[idx]
                line.append(f"{idx+1:3d}. {name} ({code})".ljust(col_width))
        print("".join(line))
    print("-" * line_width)

    while True:
        try:
            choice = input(lang.get("act_enter_num", "Enter the number (1-{len}): ").format(len=len(sorted_countries)))
            choice_idx = int(choice) - 1
            if 0 <= choice_idx < len(sorted_countries):
                selected_code = sorted_countries[choice_idx][0]
                selected_name = sorted_countries[choice_idx][1]
                print(lang.get("act_selected", "[+] You selected: {name} ({code})").format(name=selected_name, code=selected_code))
                return selected_code
            else:
                print(lang.get("act_invalid_num", "[!] Invalid number. Please enter a number within the range."))
        except ValueError:
            print(lang.get("act_invalid_input", "[!] Invalid input. Please enter a number."))
        except (KeyboardInterrupt, EOFError):
            print(lang.get("act_select_cancel", "\n[!] Selection cancelled by user. Exiting."))
            sys.exit(1)

def edit_devinfo_persist(lang: Optional[Dict[str, str]] = None) -> None:
    lang = lang or {}
    print(lang.get("act_start_dp_patch", "--- Starting devinfo & persist patching process ---"))
    
    print(lang.get("act_wait_dp", "--- Waiting for devinfo.img / persist.img ---"))
    BACKUP_DIR.mkdir(exist_ok=True) 

    devinfo_img_src = BACKUP_DIR / "devinfo.img"
    persist_img_src = BACKUP_DIR / "persist.img"
    
    devinfo_img = BASE_DIR / "devinfo.img"
    persist_img = BASE_DIR / "persist.img"

    if not devinfo_img_src.exists() and not persist_img_src.exists():
        prompt = lang.get("act_prompt_dp", 
            "[STEP 1] Place 'devinfo.img' and/or 'persist.img'\n"
            f"         (e.g., from 'Dump' menu) into the '{BACKUP_DIR.name}' folder."
        ).format(dir=BACKUP_DIR.name)
        while not devinfo_img_src.exists() and not persist_img_src.exists():
            if platform.system() == "Windows":
                os.system('cls')
            else:
                os.system('clear')
            print(lang.get("act_wait_files_title", "--- WAITING FOR FILES ---"))
            print(prompt)
            print(lang.get("act_place_one_file", "\nPlease place at least one file in the '{dir}' folder:").format(dir=BACKUP_DIR.name))
            print(" - devinfo.img")
            print(" - persist.img")
            print(lang.get("act_press_enter", "\nPress Enter when ready..."))
            try:
                input()
            except EOFError:
                sys.exit(1)

    if devinfo_img_src.exists():
        shutil.copy(devinfo_img_src, devinfo_img)
    if persist_img_src.exists():
        shutil.copy(persist_img_src, persist_img)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_critical_dir = BASE_DIR / f"backup_critical_{timestamp}"
    backup_critical_dir.mkdir(exist_ok=True)
    
    if devinfo_img.exists():
        shutil.copy(devinfo_img, backup_critical_dir)
    if persist_img.exists():
        shutil.copy(persist_img, backup_critical_dir)
    print(lang.get("act_files_backed_up", "[+] Files copied and backed up to '{dir}'.\n").format(dir=backup_critical_dir.name))

    print(lang.get("act_clean_dp_out", "[*] Cleaning up old '{dir}' folder...").format(dir=OUTPUT_DP_DIR.name))
    if OUTPUT_DP_DIR.exists():
        shutil.rmtree(OUTPUT_DP_DIR)
    OUTPUT_DP_DIR.mkdir(exist_ok=True)

    print(lang.get("act_detect_codes", "[*] Detecting current region codes in images..."))
    detected_codes = imgpatch.detect_region_codes(lang=lang)
    
    status_messages = []
    files_found = 0
    
    display_order = ["persist.img", "devinfo.img"]
    
    for fname in display_order:
        if fname in detected_codes:
            code = detected_codes[fname]
            display_name = Path(fname).stem 
            
            if code:
                status_messages.append(f"{display_name}: {code}XX")
                files_found += 1
            else:
                status_messages.append(f"{display_name}: null")
    
    print(lang.get("act_detect_result", "\n[+] Detection Result:  {res}").format(res=', '.join(status_messages)))
    
    if files_found == 0:
        print(lang.get("act_no_codes_skip", "[!] No region codes detected. Patching skipped."))
        devinfo_img.unlink(missing_ok=True)
        persist_img.unlink(missing_ok=True)
        return

    print(lang.get("act_ask_change_code", "\nDo you want to change the region code? (y/n)"))
    choice = ""
    while choice not in ['y', 'n']:
        choice = input(lang.get("act_enter_yn", "Enter choice (y/n): ")).lower().strip()

    if choice == 'n':
        print(lang.get("act_op_cancel", "[*] Operation cancelled. No changes made."))
        
        devinfo_img.unlink(missing_ok=True)
        persist_img.unlink(missing_ok=True)
        
        print(lang.get("act_safety_remove", "[*] Safety: Removing stock devinfo.img/persist.img from 'image' folder to prevent accidental flash."))
        (IMAGE_DIR / "devinfo.img").unlink(missing_ok=True)
        (IMAGE_DIR / "persist.img").unlink(missing_ok=True)
        return

    if choice == 'y':
        target_map = detected_codes.copy()
        replacement_code = select_country_code(lang.get("act_select_new_code", "SELECT NEW REGION CODE"), lang=lang)
        imgpatch.patch_region_codes(replacement_code, target_map, lang=lang)

        modified_devinfo = BASE_DIR / "devinfo_modified.img"
        modified_persist = BASE_DIR / "persist_modified.img"
        
        if modified_devinfo.exists():
            shutil.move(modified_devinfo, OUTPUT_DP_DIR / "devinfo.img")
        if modified_persist.exists():
            shutil.move(modified_persist, OUTPUT_DP_DIR / "persist.img")
            
        print(lang.get("act_dp_moved", "\n[*] Final images have been moved to '{dir}' folder.").format(dir=OUTPUT_DP_DIR.name))
        
        devinfo_img.unlink(missing_ok=True)
        persist_img.unlink(missing_ok=True)
        
        print("\n" + "=" * 61)
        print(lang.get("act_success", "  SUCCESS!"))
        print(lang.get("act_dp_ready", "  Modified images are ready in the '{dir}' folder.").format(dir=OUTPUT_DP_DIR.name))
        print("=" * 61)