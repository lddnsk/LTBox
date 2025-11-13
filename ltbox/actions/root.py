import os
import platform
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional, Dict

from ..constants import *
from .. import utils, device, imgpatch, downloader
from ..downloader import ensure_magiskboot
from .xml import _ensure_params_or_fail
from .system import detect_active_slot_robust
from .edl import _fh_loader_write_part

def root_boot_only(lang: Optional[Dict[str, str]] = None) -> None:
    lang = lang or {}
    print(lang.get("act_clean_root_out", "[*] Cleaning up old '{dir}' folder...").format(dir=OUTPUT_ROOT_DIR.name))
    if OUTPUT_ROOT_DIR.exists():
        shutil.rmtree(OUTPUT_ROOT_DIR)
    OUTPUT_ROOT_DIR.mkdir(exist_ok=True)
    print()
    
    utils.check_dependencies(lang=lang)
    magiskboot_exe = utils.get_platform_executable("magiskboot")
    ensure_magiskboot(lang=lang)

    if platform.system() != "Windows":
        os.chmod(magiskboot_exe, 0o755)

    print(lang.get("act_wait_boot", "--- Waiting for boot.img ---"))
    IMAGE_DIR.mkdir(exist_ok=True) 
    required_files = ["boot.img"]
    prompt = lang.get("act_prompt_boot",
        "[STEP 1] Place your stock 'boot.img' file\n"
        f"         (e.g., from your firmware) into the '{IMAGE_DIR.name}' folder."
    ).format(name=IMAGE_DIR.name)
    utils.wait_for_files(IMAGE_DIR, required_files, prompt, lang=lang)
    
    boot_img_src = IMAGE_DIR / "boot.img"
    boot_img = BASE_DIR / "boot.img" 
    
    try:
        shutil.copy(boot_img_src, boot_img)
        print(lang.get("act_copy_boot", "[+] Copied '{name}' to main directory for processing.").format(name=boot_img_src.name))
    except (IOError, OSError) as e:
        print(lang.get("act_err_copy_boot", "[!] Failed to copy '{name}': {e}").format(name=boot_img_src.name, e=e), file=sys.stderr)
        sys.exit(1)

    if not boot_img.exists():
        print(lang.get("act_err_boot_missing", "[!] 'boot.img' not found! Aborting."))
        sys.exit(1)

    shutil.copy(boot_img, BASE_DIR / "boot.bak.img")
    print(lang.get("act_backup_boot", "--- Backing up original boot.img ---"))

    with utils.temporary_workspace(WORK_DIR):
        shutil.copy(boot_img, WORK_DIR / "boot.img")
        boot_img.unlink()
        
        patched_boot_path = imgpatch.patch_boot_with_root_algo(WORK_DIR, magiskboot_exe, lang=lang)

        if patched_boot_path and patched_boot_path.exists():
            print(lang.get("act_finalize_root", "\n--- Finalizing ---"))
            final_boot_img = OUTPUT_ROOT_DIR / "boot.img"
            
            imgpatch.process_boot_image_avb(patched_boot_path, lang=lang)

            print(lang.get("act_move_root_final", "\n[*] Moving final image to '{dir}' folder...").format(dir=OUTPUT_ROOT_DIR.name))
            shutil.move(patched_boot_path, final_boot_img)

            print(lang.get("act_move_root_backup", "\n[*] Moving backup file to '{dir}' folder...").format(dir=BACKUP_DIR.name))
            BACKUP_DIR.mkdir(exist_ok=True)
            for bak_file in BASE_DIR.glob("boot.bak.img"):
                shutil.move(bak_file, BACKUP_DIR / bak_file.name)
            print()

            print("=" * 61)
            print(lang.get("act_success", "  SUCCESS!"))
            print(lang.get("act_root_saved", "  Patched boot.img has been saved to the '{dir}' folder.").format(dir=OUTPUT_ROOT_DIR.name))
            print("=" * 61)
        else:
            print(lang.get("act_err_root_fail", "[!] Patched boot image was not created. An error occurred during the process."), file=sys.stderr)

def root_device(skip_adb=False, lang: Optional[Dict[str, str]] = None) -> None:
    lang = lang or {}
    print(lang.get("act_start_root", "--- Starting Root Device Process (EDL Mode) ---"))
    
    if OUTPUT_ROOT_DIR.exists():
        shutil.rmtree(OUTPUT_ROOT_DIR)
    OUTPUT_ROOT_DIR.mkdir(exist_ok=True)
    BACKUP_BOOT_DIR.mkdir(exist_ok=True)

    utils.check_dependencies(lang=lang)
    
    magiskboot_exe = utils.get_platform_executable("magiskboot")
    ensure_magiskboot(lang=lang)

    dev = device.DeviceController(skip_adb=skip_adb, lang=lang)

    print(lang.get("act_root_step1", "\n--- [STEP 1/6] Waiting for ADB Connection & Slot Detection ---"))
    if not skip_adb:
        dev.wait_for_adb()

    active_slot = detect_active_slot_robust(dev, skip_adb, lang=lang)

    if active_slot:
        print(lang.get("act_slot_confirmed", "[+] Active slot confirmed: {slot}").format(slot=active_slot))
        target_partition = f"boot{active_slot}"
    else:
        print(lang.get("act_warn_root_slot", "[!] Warning: Active slot detection failed. Defaulting to 'boot' (System decides)."))
        target_partition = "boot"

    if not skip_adb:
        print(lang.get("act_check_ksu", "\n[*] Checking & Installing KernelSU Next (Spoofed) APK..."))
        downloader.download_ksu_apk(BASE_DIR, lang=lang)
        
        ksu_apks = list(BASE_DIR.glob("*spoofed*.apk"))
        if ksu_apks:
            apk_path = ksu_apks[0]
            print(lang.get("act_install_ksu", "[*] Installing {name} via ADB...").format(name=apk_path.name))
            try:
                utils.run_command([str(ADB_EXE), "install", "-r", str(apk_path)])
                print(lang.get("act_ksu_ok", "[+] APK installed successfully."))
            except Exception as e:
                print(lang.get("act_err_ksu", "[!] Failed to install APK: {e}").format(e=e))
                print(lang.get("act_root_anyway", "[!] Proceeding with root process anyway..."))
        else:
            print(lang.get("act_skip_ksu", "[!] Spoofed APK not found. Skipping installation."))
    
    print(lang.get("act_root_step2", "\n--- [STEP 2/6] Rebooting to EDL Mode ---"))
    port = dev.setup_edl_connection()
    
    try:
        dev.load_firehose_programmer(EDL_LOADER_FILE, port)
        time.sleep(2)
    except Exception as e:
        print(lang.get("act_warn_prog_load", "[!] Warning: Programmer loading issue: {e}").format(e=e))

    print(lang.get("act_root_step3", "\n--- [STEP 3/6] Dumping {part} partition ---").format(part=target_partition))
    
    params = None
    final_boot_img = OUTPUT_ROOT_DIR / "boot.img"
    
    with utils.temporary_workspace(WORKING_BOOT_DIR):
        dumped_boot_img = WORKING_BOOT_DIR / "boot.img"
        backup_boot_img = BACKUP_BOOT_DIR / "boot.img"
        base_boot_bak = BASE_DIR / "boot.bak.img"

        try:
            params = _ensure_params_or_fail(target_partition, lang=lang)
            print(lang.get("act_found_dump_info", "  > Found info in {xml}: LUN={lun}, Start={start}").format(xml=params['source_xml'], lun=params['lun'], start=params['start_sector']))
            dev.fh_loader_read_part(
                port=port,
                output_filename=str(dumped_boot_img),
                lun=params['lun'],
                start_sector=params['start_sector'],
                num_sectors=params['num_sectors']
            )
            print(lang.get("act_read_boot_ok", "[+] Successfully read '{part}' to '{file}'.").format(part=target_partition, file=dumped_boot_img))
        except (subprocess.CalledProcessError, FileNotFoundError, ValueError) as e:
            print(lang.get("act_err_dump", "[!] Failed to read '{part}': {e}").format(part=target_partition, e=e), file=sys.stderr)
            raise

        print(lang.get("act_backup_boot_root", "[*] Backing up original boot.img to '{dir}' folder...").format(dir=backup_boot_img.parent.name))
        shutil.copy(dumped_boot_img, backup_boot_img)
        print(lang.get("act_temp_backup_avb", "[*] Creating temporary backup for AVB processing..."))
        shutil.copy(dumped_boot_img, base_boot_bak)
        print(lang.get("act_backups_done", "[+] Backups complete."))

        print(lang.get("act_dump_reset", "\n[*] Dumping complete. Resetting to System to clear EDL state..."))
        dev.fh_loader_reset(port)
        
        print(lang.get("act_root_step4", "\n--- [STEP 4/6] Patching dumped boot.img ---"))
        patched_boot_path = imgpatch.patch_boot_with_root_algo(WORKING_BOOT_DIR, magiskboot_exe, lang=lang)

        if not (patched_boot_path and patched_boot_path.exists()):
            print(lang.get("act_err_root_fail", "[!] Patched boot image was not created. An error occurred."), file=sys.stderr)
            base_boot_bak.unlink(missing_ok=True)
            sys.exit(1)

        print(lang.get("act_root_step5", "\n--- [STEP 5/6] Processing AVB Footer ---"))
        try:
            imgpatch.process_boot_image_avb(patched_boot_path, lang=lang)
        except Exception as e:
            print(lang.get("act_err_avb_footer", "[!] Failed to process AVB footer: {e}").format(e=e), file=sys.stderr)
            base_boot_bak.unlink(missing_ok=True)
            raise

        shutil.move(patched_boot_path, final_boot_img)
        print(lang.get("act_patched_boot_saved", "[+] Patched boot image saved to '{dir}' folder.").format(dir=final_boot_img.parent.name))

        base_boot_bak.unlink(missing_ok=True)

    print(lang.get("act_root_step6", "\n--- [STEP 6/6] Flashing patched boot.img to {part} via EDL ---").format(part=target_partition))
    
    if not skip_adb:
        print(lang.get("act_wait_sys_adb", "[*] Waiting for device to boot to System (ADB) to ensure clean state..."))
        dev.wait_for_adb()
        print(lang.get("act_reboot_edl_flash", "[*] Rebooting to EDL for flashing..."))
        port = dev.setup_edl_connection()
    else:
        print(lang.get("act_skip_adb_on", "[!] Skip ADB is ON."))
        print(lang.get("act_manual_edl_now", "[!] Please manually reboot your device to EDL mode now."))
        port = dev.wait_for_edl()

    try:
        dev.load_firehose_programmer(EDL_LOADER_FILE, port)
        time.sleep(2)
    except Exception as e:
        print(lang.get("act_warn_prog_load", "[!] Warning: Programmer loading issue: {e}").format(e=e))

    if not params:
         params = _ensure_params_or_fail(target_partition, lang=lang)

    try:
        _fh_loader_write_part(
            port=port,
            image_path=final_boot_img,
            lun=params['lun'],
            start_sector=params['start_sector'],
            lang=lang
        )
        print(lang.get("act_flash_boot_ok", "[+] Successfully flashed 'boot.img' to {part} via EDL.").format(part=target_partition))
        
        print(lang.get("act_reset_sys", "[*] Resetting to system..."))
        dev.fh_loader_reset(port)
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        print(lang.get("act_err_edl_write", "[!] An error occurred during EDL flash: {e}").format(e=e), file=sys.stderr)
        raise

    print(lang.get("act_root_finish", "\n--- Root Device Process Finished ---"))

def unroot_device(skip_adb=False, lang: Optional[Dict[str, str]] = None) -> None:
    lang = lang or {}
    print(lang.get("act_start_unroot", "--- Starting Unroot Device Process (EDL Mode) ---"))
    
    backup_boot_file = BACKUP_BOOT_DIR / "boot.img"
    BACKUP_BOOT_DIR.mkdir(exist_ok=True)
    
    print(lang.get("act_unroot_step1", "\n--- [STEP 1/4] Checking Requirements ---"))
    if not list(IMAGE_DIR.glob("rawprogram*.xml")) and not list(IMAGE_DIR.glob("*.x")):
         print(lang.get("act_err_no_xmls", "[!] Error: No firmware XMLs found in '{dir}'.").format(dir=IMAGE_DIR.name))
         print(lang.get("act_unroot_req_xmls", "[!] Unroot via EDL requires partition information from firmware XMLs."))
         prompt = lang.get("act_prompt_image",
            "[STEP 1] Please copy the entire 'image' folder from your\n"
            "         unpacked Lenovo RSA firmware into the main directory."
         )
         utils.wait_for_directory(IMAGE_DIR, prompt, lang=lang)

    print(lang.get("act_unroot_step2", "\n--- [STEP 2/4] Checking for backup boot.img ---"))
    if not backup_boot_file.exists():
        prompt = lang.get("act_prompt_backup_boot",
            "[!] Backup file 'boot.img' not found.\n"
            f"    Please place your stock 'boot.img' (from your current firmware)\n"
            f"    into the '{BACKUP_BOOT_DIR.name}' folder."
        ).format(dir=BACKUP_BOOT_DIR.name)
        utils.wait_for_files(BACKUP_BOOT_DIR, ["boot.img"], prompt, lang=lang)
    
    print(lang.get("act_backup_boot_found", "[+] Stock backup 'boot.img' found."))

    dev = device.DeviceController(skip_adb=skip_adb, lang=lang)
    target_partition = "boot"

    print(lang.get("act_unroot_step3", "\n--- [STEP 3/4] Checking Device Slot & Connection ---"))
    if not skip_adb:
        dev.wait_for_adb()
    
    active_slot = detect_active_slot_robust(dev, skip_adb, lang=lang)
    
    if active_slot:
        print(lang.get("act_slot_confirmed", "[+] Active slot confirmed: {slot}").format(slot=active_slot))
        target_partition = f"boot{active_slot}"
    else:
        print(lang.get("act_warn_unroot_slot", "[!] Warning: Active slot detection failed. Defaulting to 'boot'."))

    port = dev.setup_edl_connection()

    try:
        dev.load_firehose_programmer(EDL_LOADER_FILE, port)
        time.sleep(2)
    except Exception as e:
        print(lang.get("act_warn_prog_load", "[!] Warning: Programmer loading issue: {e}").format(e=e))

    print(lang.get("act_unroot_step4", "\n--- [STEP 4/4] Flashing stock boot.img to {part} via EDL ---").format(part=target_partition))
    try:
        params = _ensure_params_or_fail(target_partition, lang=lang)
        print(lang.get("act_found_dump_info", "  > Found info in {xml}: LUN={lun}, Start={start}").format(xml=params['source_xml'], lun=params['lun'], start=params['start_sector']))
        
        _fh_loader_write_part(
            port=port,
            image_path=backup_boot_file,
            lun=params['lun'],
            start_sector=params['start_sector'],
            lang=lang
        )
        print(lang.get("act_flash_stock_boot_ok", "[+] Successfully flashed stock 'boot.img' to {part}.").format(part=target_partition))
        
        print(lang.get("act_reset_sys", "[*] Resetting to system..."))
        dev.fh_loader_reset(port)
        
    except (subprocess.CalledProcessError, FileNotFoundError, ValueError) as e:
        print(lang.get("act_err_edl_write", "[!] An error occurred during EDL flash: {e}").format(e=e), file=sys.stderr)
        raise

    print(lang.get("act_unroot_finish", "\n--- Unroot Device Process Finished ---"))