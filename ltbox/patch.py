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
from ltbox import utils, downloader, avb, edit_images, get_kernel_ver, decrypt_x

# --- Core Functions ---
def patch_boot_with_root():
    print("--- Starting boot.img patching process ---")
    magiskboot_exe = utils.get_platform_executable("magiskboot")
    fetch_exe = utils.get_platform_executable("fetch")
    
    patched_boot_path = BASE_DIR / "boot.root.img"

    if not fetch_exe.exists():
         print(f"[!] '{fetch_exe.name}' not found. Please run install.bat")
         sys.exit(1)

    downloader._ensure_magiskboot(fetch_exe, magiskboot_exe)

    if platform.system() != "Windows":
        os.chmod(magiskboot_exe, 0o755)
        os.chmod(fetch_exe, 0o755)

    print("--- Waiting for boot.img ---") 
    IMAGE_DIR.mkdir(exist_ok=True) 
    required_files = ["boot.img"]
    prompt = (
        "[STEP 1] Place your stock 'boot.img' file\n"
        f"         (e.g., from your firmware) into the '{IMAGE_DIR.name}' folder."
    )
    utils.wait_for_files(IMAGE_DIR, required_files, prompt)
    
    boot_img_src = IMAGE_DIR / "boot.img"
    boot_img = BASE_DIR / "boot.img" 
    
    try:
        shutil.copy(boot_img_src, boot_img)
        print(f"[+] Copied '{boot_img_src.name}' to main directory for processing.")
    except (IOError, OSError) as e:
        print(f"[!] Failed to copy '{boot_img_src.name}': {e}", file=sys.stderr)
        sys.exit(1)

    if not boot_img.exists():
        print("[!] 'boot.img' not found! Aborting.")
        sys.exit(1)

    shutil.copy(boot_img, BASE_DIR / "boot.bak.img")
    print("--- Backing up original boot.img ---")

    if WORK_DIR.exists():
        shutil.rmtree(WORK_DIR)
    WORK_DIR.mkdir()

    original_cwd = Path.cwd()
    os.chdir(WORK_DIR)

    try:
        shutil.copy(boot_img, WORK_DIR)

        print("\n[1/8] Unpacking boot image...")
        utils.run_command([str(magiskboot_exe), "unpack", "boot.img"])
        if not (WORK_DIR / "kernel").exists():
            print("[!] Failed to unpack boot.img. The image might be invalid.")
            sys.exit(1)
        print("[+] Unpack successful.")

        print("\n[2/8] Verifying kernel version...")
        target_kernel_version = get_kernel_ver.get_kernel_version("kernel")

        if not target_kernel_version:
             print(f"[!] Failed to get kernel version from 'kernel' file.")
             sys.exit(1)

        if not re.match(r"\d+\.\d+\.\d+", target_kernel_version):
             print(f"[!] Invalid kernel version returned from script: '{target_kernel_version}'")
             sys.exit(1)
        
        print(f"[+] Target kernel version for download: {target_kernel_version}")

        kernel_image_path = downloader._get_gki_kernel(fetch_exe, target_kernel_version, WORK_DIR)

        print("\n[5/8] Replacing original kernel with the new one...")
        shutil.move(str(kernel_image_path), "kernel")
        print("[+] Kernel replaced.")

        print("\n[6/8] Repacking boot image...")
        utils.run_command([str(magiskboot_exe), "repack", "boot.img"])
        if not (WORK_DIR / "new-boot.img").exists():
            print("[!] Failed to repack the boot image.")
            sys.exit(1)
        shutil.move("new-boot.img", patched_boot_path)
        print("[+] Repack successful.")

        downloader._download_ksu_apk(fetch_exe, BASE_DIR)

    finally:
        os.chdir(original_cwd)
        if WORK_DIR.exists():
            shutil.rmtree(WORK_DIR)
        if boot_img.exists():
            boot_img.unlink()
        print("\n--- Cleaning up ---")

    if patched_boot_path.exists():
        return patched_boot_path
    return None

def convert_images(device_model=None):
    utils.check_dependencies()
    
    print("--- Starting vendor_boot & vbmeta conversion process ---") 

    print("[*] Cleaning up old folders...")
    if OUTPUT_DIR.exists():
        shutil.rmtree(OUTPUT_DIR)
    print()

    print("--- Waiting for vendor_boot.img and vbmeta.img ---") 
    IMAGE_DIR.mkdir(exist_ok=True)
    required_files = ["vendor_boot.img", "vbmeta.img"]
    prompt = (
        "[STEP 1] Place the required firmware files for conversion\n"
        f"         (e.g., from your PRC firmware) into the '{IMAGE_DIR.name}' folder."
    )
    utils.wait_for_files(IMAGE_DIR, required_files, prompt)
    
    vendor_boot_src = IMAGE_DIR / "vendor_boot.img"
    vbmeta_src = IMAGE_DIR / "vbmeta.img"

    print("--- Backing up original images ---")
    vendor_boot_bak = BASE_DIR / "vendor_boot.bak.img"
    vbmeta_bak = BASE_DIR / "vbmeta.bak.img"
    
    try:
        shutil.copy(vendor_boot_src, vendor_boot_bak)
        shutil.copy(vbmeta_src, vbmeta_bak)
        print("[+] Backup complete.\n")
    except (IOError, OSError) as e:
        print(f"[!] Failed to copy input files: {e}", file=sys.stderr)
        raise

    print("--- Starting PRC/ROW Conversion ---")
    edit_images.edit_vendor_boot(str(vendor_boot_bak))

    vendor_boot_prc = BASE_DIR / "vendor_boot_prc.img"
    print("\n[*] Verifying conversion result...")
    if not vendor_boot_prc.exists():
        print("[!] 'vendor_boot_prc.img' was not created. No changes made.")
        raise FileNotFoundError("vendor_boot_prc.img not created")
    print("[+] Conversion to PRC successful.\n")

    print("--- Extracting image information ---")
    vbmeta_info = avb.extract_image_avb_info(vbmeta_bak)
    vendor_boot_info = avb.extract_image_avb_info(vendor_boot_bak)
    print("[+] Information extracted.\n")

    if device_model:
        print(f"[*] Validating firmware against device model '{device_model}'...")
        fingerprint_key = "com.android.build.vendor_boot.fingerprint"
        if fingerprint_key in vendor_boot_info:
            fingerprint = vendor_boot_info[fingerprint_key]
            print(f"  > Found firmware fingerprint: {fingerprint}")
            if device_model in fingerprint:
                print(f"[+] Success: Device model '{device_model}' found in firmware fingerprint.")
            else:
                print(f"[!] ERROR: Device model '{device_model}' NOT found in firmware fingerprint.")
                print("[!] The provided ROM does not match your device model. Aborting.")
                raise SystemExit("Firmware model mismatch")
        else:
            print(f"[!] Warning: Could not find fingerprint property '{fingerprint_key}' in vendor_boot.")
            print("[!] Skipping model validation.")
    
    print("--- Adding Hash Footer to vendor_boot ---")
    
    for key in ['partition_size', 'name', 'rollback', 'salt']:
        if key not in vendor_boot_info:
            if key == 'partition_size' and 'data_size' in vendor_boot_info:
                 vendor_boot_info['partition_size'] = vendor_boot_info['data_size']
            else:
                raise KeyError(f"Could not find '{key}' in '{vendor_boot_bak.name}' AVB info.")

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
        print(f"[+] Restoring {len(vendor_boot_info['props_args']) // 2} properties for vendor_boot.")

    if 'flags' in vendor_boot_info:
        add_hash_footer_cmd.extend(["--flags", vendor_boot_info.get('flags', '0')])
        print(f"[+] Restoring flags for vendor_boot: {vendor_boot_info.get('flags', '0')}")

    utils.run_command(add_hash_footer_cmd)
    
    vbmeta_pubkey = vbmeta_info.get('pubkey_sha1')
    key_file = KEY_MAP.get(vbmeta_pubkey) 

    print(f"--- Remaking vbmeta.img ---")
    print("[*] Verifying vbmeta key...")
    if not key_file:
        print(f"[!] Public key SHA1 '{vbmeta_pubkey}' from vbmeta did not match known keys. Aborting.")
        raise KeyError(f"Unknown vbmeta public key: {vbmeta_pubkey}")
    print(f"[+] Matched {key_file.name}.\n")

    print("[*] Remaking 'vbmeta.img' using descriptors from backup...")
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

    finalize_images()

def finalize_images():
    print("--- Finalizing ---")
    print("[*] Renaming final images...")
    final_vendor_boot = BASE_DIR / "vendor_boot.img"
    shutil.move(BASE_DIR / "vendor_boot_prc.img", final_vendor_boot)

    final_images = [final_vendor_boot, BASE_DIR / "vbmeta.img"]

    print(f"\n[*] Moving final images to '{OUTPUT_DIR.name}' folder...")
    OUTPUT_DIR.mkdir(exist_ok=True)
    for img in final_images:
        if img.exists(): 
            shutil.move(img, OUTPUT_DIR / img.name)

    print(f"\n[*] Moving backup files to '{BACKUP_DIR.name}' folder...")
    BACKUP_DIR.mkdir(exist_ok=True)
    for bak_file in BASE_DIR.glob("*.bak.img"):
        shutil.move(bak_file, BACKUP_DIR / bak_file.name)
    print()

    print("=" * 61)
    print("  SUCCESS!")
    print(f"  Final images have been saved to the '{OUTPUT_DIR.name}' folder.")
    print("=" * 61)
    
def root_boot_only():
    print(f"[*] Cleaning up old '{OUTPUT_ROOT_DIR.name}' folder...")
    if OUTPUT_ROOT_DIR.exists():
        shutil.rmtree(OUTPUT_ROOT_DIR)
    OUTPUT_ROOT_DIR.mkdir(exist_ok=True)
    print()
    
    utils.check_dependencies()

    patched_boot_path = patch_boot_with_root()

    if patched_boot_path and patched_boot_path.exists():
        print("\n--- Finalizing ---")
        final_boot_img = OUTPUT_ROOT_DIR / "boot.img"
        
        avb.process_boot_image(patched_boot_path)

        print(f"\n[*] Moving final image to '{OUTPUT_ROOT_DIR.name}' folder...")
        shutil.move(patched_boot_path, final_boot_img)

        print(f"\n[*] Moving backup file to '{BACKUP_DIR.name}' folder...")
        BACKUP_DIR.mkdir(exist_ok=True)
        for bak_file in BASE_DIR.glob("boot.bak.img"):
            shutil.move(bak_file, BACKUP_DIR / bak_file.name)
        print()

        print("=" * 61)
        print("  SUCCESS!")
        print(f"  Patched boot.img has been saved to the '{OUTPUT_ROOT_DIR.name}' folder.")
        print("=" * 61)
    else:
        print("[!] Patched boot image was not created. An error occurred during the process.", file=sys.stderr)

def edit_devinfo_persist():
    print("--- Starting devinfo & persist patching process ---")
    
    print("--- Waiting for devinfo.img / persist.img ---") 
    BACKUP_DIR.mkdir(exist_ok=True) 

    devinfo_img_src = BACKUP_DIR / "devinfo.img"
    persist_img_src = BACKUP_DIR / "persist.img"
    
    devinfo_img = BASE_DIR / "devinfo.img"
    persist_img = BASE_DIR / "persist.img"

    if not devinfo_img_src.exists() and not persist_img_src.exists():
        prompt = (
            "[STEP 1] Place 'devinfo.img' and/or 'persist.img'\n"
            f"         (e.g., from 'Dump' menu) into the '{BACKUP_DIR.name}' folder."
        )
        while not devinfo_img_src.exists() and not persist_img_src.exists():
            if platform.system() == "Windows":
                os.system('cls')
            else:
                os.system('clear')
            print("--- WAITING FOR FILES ---")
            print(prompt)
            print(f"\nPlease place at least one file in the '{BACKUP_DIR.name}' folder:")
            print(" - devinfo.img")
            print(" - persist.img")
            print("\nPress Enter when ready...")
            try:
                input()
            except EOFError:
                sys.exit(1)

    if devinfo_img_src.exists():
        shutil.copy(devinfo_img_src, devinfo_img)
        print("[+] Copied 'devinfo.img' to main directory for processing.")
    if persist_img_src.exists():
        shutil.copy(persist_img_src, persist_img)
        print("[+] Copied 'persist.img' to main directory for processing.")

    if not devinfo_img.exists() and not persist_img.exists():
        print("[!] Error: 'devinfo.img' and 'persist.img' both not found in main directory. Aborting.")
        raise FileNotFoundError("devinfo.img or persist.img not found for patching.")
        
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_critical_dir = BASE_DIR / f"backup_critical_{timestamp}"
    backup_critical_dir.mkdir(exist_ok=True)
    
    print(f"[*] Backing up critical images to '{backup_critical_dir.name}'...")
    
    if devinfo_img.exists():
        shutil.copy(devinfo_img, backup_critical_dir)
        print(f"[+] Backed up '{devinfo_img.name}'.")
    if persist_img.exists():
        shutil.copy(persist_img, backup_critical_dir)
        print(f"[+] Backed up '{persist_img.name}'.")
    print("[+] Backup complete.\n")

    print(f"[*] Cleaning up old '{OUTPUT_DP_DIR.name}' folder...")
    if OUTPUT_DP_DIR.exists():
        shutil.rmtree(OUTPUT_DP_DIR)
    OUTPUT_DP_DIR.mkdir(exist_ok=True)

    print("[*] Running patch script...")
    edit_images.edit_devinfo_persist()

    modified_devinfo = BASE_DIR / "devinfo_modified.img"
    modified_persist = BASE_DIR / "persist_modified.img"
    
    if modified_devinfo.exists():
        shutil.move(modified_devinfo, OUTPUT_DP_DIR / "devinfo.img")
    if modified_persist.exists():
        shutil.move(modified_persist, OUTPUT_DP_DIR / "persist.img")
        
    print(f"\n[*] Final images have been moved to '{OUTPUT_DP_DIR.name}' folder.")
    
    print("[*] Cleaning up original image files...")
    devinfo_img.unlink(missing_ok=True)
    persist_img.unlink(missing_ok=True)
    
    print("\n" + "=" * 61)
    print("  SUCCESS!")
    print(f"  Modified images are ready in the '{OUTPUT_DP_DIR.name}' folder.")
    print("=" * 61)

def modify_xml(wipe=0):
    print("--- Starting XML Modification Process ---")
    
    print("--- Waiting for 'image' folder ---")
    prompt = (
        "[STEP 1] Please copy the entire 'image' folder from your\n"
        "         unpacked Lenovo RSA firmware into the main directory."
    )
    utils.wait_for_directory(IMAGE_DIR, prompt)

    if WORKING_DIR.exists():
        shutil.rmtree(WORKING_DIR)
    if OUTPUT_XML_DIR.exists():
        shutil.rmtree(OUTPUT_XML_DIR)
    
    WORKING_DIR.mkdir()
    print(f"\n[*] Created temporary '{WORKING_DIR.name}' folder.")

    print("[*] Decrypting *.x files and moving to 'working' folder...")
    xml_files = []
    for file in IMAGE_DIR.glob("*.x"):
        out_file = WORKING_DIR / file.with_suffix('.xml').name
        try:
            if decrypt_x.decrypt_file(str(file), str(out_file)):
                print(f"  > Decrypted: {file.name} -> {out_file.name}")
                xml_files.append(out_file)
            else:
                raise Exception(f"Decryption failed for {file.name}")
        except Exception as e:
            print(f"[!] Failed to decrypt {file.name}: {e}", file=sys.stderr)
            
    if not xml_files:
        print(f"[!] No '*.x' files found in '{IMAGE_DIR.name}'. Aborting.")
        shutil.rmtree(WORKING_DIR)
        raise FileNotFoundError(f"No *.x files found in {IMAGE_DIR.name}")

    contents_xml = WORKING_DIR / "contents.xml"
    if not contents_xml.exists():
        print(f"[!] Error: 'contents.xml' not found in '{WORKING_DIR.name}'.")
        print("[!] This file is essential for the flashing process. Aborting.")
        shutil.rmtree(WORKING_DIR)
        raise FileNotFoundError(f"contents.xml not found in {WORKING_DIR.name}")

    rawprogram4 = WORKING_DIR / "rawprogram4.xml"
    rawprogram_unsparse4 = WORKING_DIR / "rawprogram_unsparse4.xml"
    if not rawprogram4.exists() and rawprogram_unsparse4.exists():
        print(f"[*] 'rawprogram4.xml' not found. Copying 'rawprogram_unsparse4.xml'...")
        shutil.copy(rawprogram_unsparse4, rawprogram4)

    print("\n[*] Modifying 'rawprogram_save_persist_unsparse0.xml'...")
    rawprogram_save = WORKING_DIR / "rawprogram_save_persist_unsparse0.xml"
    if rawprogram_save.exists():
        try:
            with open(rawprogram_save, 'r', encoding='utf-8') as f:
                content = f.read()
            
            if wipe == 1:
                print(f"  > [WIPE] Removing metadata and userdata entries...")
                for i in range(1, 11):
                    content = content.replace(f'filename="metadata_{i}.img"', '')
                for i in range(1, 21):
                    content = content.replace(f'filename="userdata_{i}.img"', '')
            else:
                print(f"  > [NO WIPE] Skipping metadata and userdata removal.")
                
            with open(rawprogram_save, 'w', encoding='utf-8') as f:
                f.write(content)
            print("  > Patched 'rawprogram_save_persist_unsparse0.xml' successfully.")
        except Exception as e:
            print(f"[!] Error patching 'rawprogram_save_persist_unsparse0.xml': {e}", file=sys.stderr)
    else:
        print("  > 'rawprogram_save_persist_unsparse0.xml' not found. Skipping.")

    print("\n[*] Modifying 'rawprogram4.xml'...")
    if rawprogram4.exists():
        try:
            with open(rawprogram4, 'r', encoding='utf-8') as f:
                content = f.read()
            
            if not any(IMAGE_DIR.glob("vm-bootsys*.img")):
                print("  > 'vm-bootsys' image not found. Removing from XML...")
                content = content.replace('filename="vm-bootsys.img"', '')
            else:
                print("  > 'vm-bootsys' image found. Keeping in XML.")

            if not any(IMAGE_DIR.glob("vm-persist*.img")):
                print("  > 'vm-persist' image not found. Removing from XML...")
                content = content.replace('filename="vm-persist.img"', '')
            else:
                print("  > 'vm-persist' image found. Keeping in XML.")

            with open(rawprogram4, 'w', encoding='utf-8') as f:
                f.write(content)
            print("  > Patched 'rawprogram4.xml' successfully.")
        except Exception as e:
            print(f"[!] Error patching 'rawprogram4.xml': {e}", file=sys.stderr)
    else:
        print("  > 'rawprogram4.xml' not found. Skipping.")

    print("\n[*] Deleting unnecessary XML files...")
    files_to_delete = [
        WORKING_DIR / "rawprogram_unsparse0.xml",
        WORKING_DIR / "contents.xml",
        *WORKING_DIR.glob("*_WIPE_PARTITIONS.xml"),
        *WORKING_DIR.glob("*_BLANK_GPT.xml")
    ]
    for f in files_to_delete:
        if f.exists():
            f.unlink()
            print(f"  > Deleted: {f.name}")

    OUTPUT_XML_DIR.mkdir(exist_ok=True)
    print(f"\n[*] Moving modified XML files to '{OUTPUT_XML_DIR.name}'...")
    moved_count = 0
    for f in WORKING_DIR.glob("*.xml"):
        shutil.move(str(f), OUTPUT_XML_DIR / f.name)
        moved_count += 1
        
    print(f"[+] Moved {moved_count} modified XML file(s).")
    
    shutil.rmtree(WORKING_DIR)
    print(f"[*] Cleaned up temporary '{WORKING_DIR.name}' folder.")
    
    print("\n" + "=" * 61)
    print("  SUCCESS!")
    print(f"  Modified XML files are ready in the '{OUTPUT_XML_DIR.name}'.")
    print("  You can now run 'Flash EDL' (Menu 10).")
    print("=" * 61)