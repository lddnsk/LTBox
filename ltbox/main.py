import argparse
import logging
import os
import platform
import subprocess
import sys
from contextlib import contextmanager
from pathlib import Path
from datetime import datetime
import json

APP_DIR = Path(__file__).parent.resolve()
LANG_DIR = APP_DIR / "lang"
BASE_DIR = APP_DIR.parent
PYTHON_EXE = BASE_DIR / "python3" / "python.exe"
DOWNLOADER_PY = APP_DIR / "downloader.py"

def select_language():
    os.system('cls' if os.name == 'nt' else 'clear')
    if not LANG_DIR.is_dir():
        print(f"[!] Critical Error: Language directory not found.", file=sys.stderr)
        print(f"[!] Expected path: {LANG_DIR}", file=sys.stderr)
        if platform.system() == "Windows":
            os.system("pause")
        sys.exit(1)

    lang_files = sorted(list(LANG_DIR.glob("*.json")))
    if not lang_files:
        print(f"[!] Critical Error: No language files (*.json) found in:", file=sys.stderr)
        print(f"[!] Path: {LANG_DIR}", file=sys.stderr)
        if platform.system() == "Windows":
            os.system("pause")
        sys.exit(1)

    available_languages = {}
    menu_options = []
    
    for i, f in enumerate(lang_files, 1):
        lang_code = f.stem
        available_languages[str(i)] = lang_code
        
        try:
            with open(f, 'r', encoding='utf-8') as lang_file:
                temp_lang = json.load(lang_file)
                lang_name = temp_lang.get("lang_native_name", lang_code)
        except Exception:
            lang_name = lang_code
        menu_options.append(f"     {i}. {lang_name}")

    print("\n  " + "=" * 58)
    print("     Select Language")
    print("  " + "=" * 58 + "\n")
    print("\n".join(menu_options))
    print("\n  " + "=" * 58 + "\n")

    choice = ""
    while choice not in available_languages:
        prompt = f"    Enter your choice (1-{len(available_languages)}): "
        choice = input(prompt).strip()
        if choice not in available_languages:
            print(f"    [!] Invalid choice. Please enter a number from 1 to {len(available_languages)}.")
    
    return available_languages[choice]

def setup_console():
    system = platform.system()
    if system == "Windows":
        try:
            import ctypes
            ctypes.windll.kernel32.SetConsoleTitleW(u"LTBox")
        except Exception as e:
            print(f"[!] Warning: Failed to set console title: {e}", file=sys.stderr)

setup_console()
lang_code = select_language()

sys.path.insert(0, str(Path(__file__).parent.parent.resolve()))

if platform.system() == "Windows":
    import ctypes

try:
    from ltbox import i18n
    i18n.load_lang(lang_code)
    from ltbox.i18n import get_string
except ImportError as e:
    print(f"[!] Error: Failed to import 'ltbox' package.", file=sys.stderr)
    print(f"[!] Details: {e}", file=sys.stderr)
    print(f"[!] Please ensure the 'ltbox' folder and its files are present.", file=sys.stderr)
    if platform.system() == "Windows":
        os.system("pause")
    sys.exit(1)

os.system('cls' if os.name == 'nt' else 'clear')
print(get_string("dl_base_installing"))
try:
    subprocess.run(
        [str(PYTHON_EXE), str(DOWNLOADER_PY), "install_base_tools", "--lang", lang_code],
        check=True,
        encoding='utf-8',
        errors='ignore'
    )
except (subprocess.CalledProcessError, FileNotFoundError) as e:
    print(f"[!] Critical Error: Failed to install base tools: {e}", file=sys.stderr)
    print("[!] Please run 'ltbox/install.bat' manually and try again.", file=sys.stderr)
    if platform.system() == "Windows":
        os.system("pause")
    sys.exit(1)

try:
    from ltbox import utils, actions, workflow
    from ltbox import constants
except ImportError as e:
    print(f"[!] Error: Failed to import 'ltbox' package.", file=sys.stderr)
    print(f"[!] Details: {e}", file=sys.stderr)
    print(f"[!] Please ensure the 'ltbox' folder and its files are present.", file=sys.stderr)
    if platform.system() == "Windows":
        os.system("pause")
    sys.exit(1)

COMMAND_MAP = {
    "convert": (actions.convert_images, {}),
    "root_device": (actions.root_device, {"skip_adb": True}),
    "root_boot_only": (actions.root_boot_only, {}),
    "unroot_device": (actions.unroot_device, {"skip_adb": True}),
    "disable_ota": (actions.disable_ota, {"skip_adb": True}),
    "edit_dp": (actions.edit_devinfo_persist, {}),
    "read_edl": (actions.read_edl, {"skip_adb": True}),
    "write_edl": (actions.write_edl, {}),
    "read_anti_rollback": (actions.read_anti_rollback, {}),
    "patch_anti_rollback": (actions.patch_anti_rollback, {}),
    "write_anti_rollback": (actions.write_anti_rollback, {}),
    "clean": (utils.clean_workspace, {}),
    "modify_xml": (actions.modify_xml, {"wipe": 0}),
    "modify_xml_wipe": (actions.modify_xml, {"wipe": 1}),
    "flash_edl": (actions.flash_edl, {}),
    "patch_all": (workflow.patch_all, {"wipe": 0, "skip_adb": True}),
    "patch_all_wipe": (workflow.patch_all, {"wipe": 1, "skip_adb": True}),
}

def check_path_encoding():
    current_path = str(Path(__file__).parent.parent.resolve())
    if not current_path.isascii():
        os.system('cls' if os.name == 'nt' else 'clear')
        print("\n" + "!" * 65)
        print(get_string("critical_error_path_encoding"))
        print("  " + "-" * 60)
        print(get_string("current_path").format(current_path=current_path))
        print("  " + "-" * 60)
        print(get_string("path_encoding_details_1"))
        print(get_string("path_encoding_details_2"))
        print("\n" + get_string("action_required"))
        print(get_string("action_required_details"))
        print(get_string("example_path"))
        print("!" * 65 + "\n")
        
        if platform.system() == "Windows":
            os.system("pause")
        else:
            input(get_string("press_enter_to_exit"))
        sys.exit(1)

@contextmanager
def capture_output_to_log(log_filename):
    logger = logging.getLogger("task_logger")
    logger.setLevel(logging.INFO)
    logger.handlers = [] 

    file_handler = logging.FileHandler(log_filename, encoding='utf-8')
    file_handler.setFormatter(logging.Formatter('%(message)s'))
    logger.addHandler(file_handler)

    class StreamLogger:
        def __init__(self, original_stream):
            self.original_stream = original_stream

        def write(self, message):
            self.original_stream.write(message)
            if message.strip():
                logger.info(message.rstrip())

        def flush(self):
            self.original_stream.flush()
            file_handler.flush()

    original_stdout = sys.stdout
    original_stderr = sys.stderr

    try:
        sys.stdout = StreamLogger(original_stdout)
        sys.stderr = StreamLogger(original_stderr)
        yield
    finally:
        sys.stdout = original_stdout
        sys.stderr = original_stderr
        logger.removeHandler(file_handler)
        file_handler.close()

def run_task(command, title, skip_adb):
    os.environ['SKIP_ADB'] = '1' if skip_adb else '0'
    
    os.system('cls' if os.name == 'nt' else 'clear')
    
    print("  " + "=" * 58)
    print(get_string("starting_task").format(title=title))
    print("  " + "=" * 58, "\n")

    needs_logging = command in ["patch_all", "patch_all_wipe"]
    log_context = None
    log_file = None

    if needs_logging:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_file = f"log_{timestamp}.txt"
        print(get_string("logging_enabled").format(log_file=log_file))
        print(get_string("logging_command").format(command=command))
        log_context = capture_output_to_log(log_file)
    else:
        @contextmanager
        def no_op(): yield
        log_context = no_op()

    try:
        with log_context:
            func_tuple = COMMAND_MAP.get(command)
            if not func_tuple:
                print(get_string("unknown_command").format(command=command), file=sys.stderr)
                return
            
            func, base_kwargs = func_tuple
            final_kwargs = base_kwargs.copy()
            if "skip_adb" in final_kwargs:
                final_kwargs["skip_adb"] = skip_adb
            
            func(**final_kwargs)

    except (subprocess.CalledProcessError, FileNotFoundError, RuntimeError, KeyError) as e:
        if not isinstance(e, SystemExit):
            print(get_string("unexpected_error").format(e=e), file=sys.stderr)
    except SystemExit:
        print(get_string("process_halted"), file=sys.stderr)
    except KeyboardInterrupt:
        print(get_string("process_cancelled"), file=sys.stderr)
    finally:
        print()
        if needs_logging and log_file:
            print(get_string("logging_finished").format(log_file=log_file))

        print("  " + "=" * 58)
        print(get_string("task_completed").format(title=title))
        print("  " + "=" * 58, "\n")
        
        if command == "clean":
            print(get_string("press_any_key_to_exit"))
        else:
            print(get_string("press_any_key_to_return"))

        if platform.system() == "Windows":
            os.system(f"pause > nul & echo {get_string('press_any_key')}...")
        else:
            input()

def run_info_scan(paths):
    print(get_string("scan_start"))
    
    PYTHON_EXE = constants.PYTHON_EXE
    AVBTOOL_PY = constants.AVBTOOL_PY
    BASE_DIR = constants.BASE_DIR

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_filename = BASE_DIR / f"image_info_{timestamp}.txt"
    
    files_to_scan = []
    for path_str in paths:
        p = Path(path_str)
        if p.is_dir():
            files_to_scan.extend(p.rglob("*.img"))
        elif p.is_file() and p.suffix.lower() == '.img':
            files_to_scan.append(p)
    
    if not files_to_scan:
        print(get_string("scan_no_files"), file=sys.stderr)
        return

    print(get_string("scan_found_files").format(count=len(files_to_scan)))
    
    logger = logging.getLogger("scan_logger")
    logger.setLevel(logging.INFO)
    fh = logging.FileHandler(log_filename, encoding='utf-8')
    fh.setFormatter(logging.Formatter('%(message)s'))
    logger.addHandler(fh)

    try:
        for f in files_to_scan:
            cmd = [str(PYTHON_EXE), str(AVBTOOL_PY), "info_image", "--image", str(f)]
            header = f"--- Info for: {f.resolve()} ---\n"
            logger.info(header)
            print(get_string("scan_scanning_file").format(filename=f.name))
            
            try:
                result = utils.run_command(cmd, capture=True, check=False)
                logger.info(result.stdout)
                logger.info(result.stderr)
                logger.info("\n" + "="*70 + "\n")
            except Exception as e:
                error_msg = get_string("scan_failed").format(filename=f.name, e=e)
                print(error_msg, file=sys.stderr)
                logger.info(error_msg)
    finally:
        logger.removeHandler(fh)
        fh.close()
    
    print(get_string("scan_complete"))
    print(get_string("scan_saved_to").format(filename=log_filename.name))

def print_main_menu(skip_adb):
    skip_adb_state = "ON" if skip_adb else "OFF"
    os.system('cls' if os.name == 'nt' else 'clear')
    print("\n  " + "=" * 58)
    print(get_string("menu_main_title"))
    print("  " + "=" * 58 + "\n")
    print(get_string("menu_main_1"))
    print(get_string("menu_main_2"))
    print(get_string("menu_main_3"))
    print(get_string("menu_main_4"))
    print(get_string("menu_main_5"))
    print(get_string("menu_main_6").format(skip_adb_state=skip_adb_state))
    print("\n" + get_string("menu_main_a"))
    print(get_string("menu_main_x"))
    print("\n  " + "=" * 58 + "\n")

def print_advanced_menu():
    os.system('cls' if os.name == 'nt' else 'clear')
    print("\n  " + "=" * 58)
    print(get_string("menu_adv_title"))
    print("  " + "=" * 58 + "\n")
    print(get_string("menu_adv_1"))
    print(get_string("menu_adv_2"))
    print(get_string("menu_adv_3"))
    print(get_string("menu_adv_4"))
    print(get_string("menu_adv_5"))
    print(get_string("menu_adv_6"))
    print(get_string("menu_adv_7"))
    print(get_string("menu_adv_8"))
    print(get_string("menu_adv_9"))
    print(get_string("menu_adv_10"))
    print("\n" + get_string("menu_adv_11"))
    print(get_string("menu_adv_m"))
    print("\n  " + "=" * 58 + "\n")

def advanced_menu(skip_adb):
    actions_map = {
        "1": ("convert", get_string("task_title_convert_rom")),
        "2": ("read_edl", get_string("task_title_dump_devinfo")),
        "3": ("edit_dp", get_string("task_title_patch_devinfo")),
        "4": ("write_edl", get_string("task_title_write_devinfo")),
        "5": ("read_anti_rollback", get_string("task_title_read_arb")),
        "6": ("patch_anti_rollback", get_string("task_title_patch_arb")),
        "7" : ("write_anti_rollback", get_string("task_title_write_arb")),
        "8": ("modify_xml_wipe", get_string("task_title_modify_xml_wipe")),
        "9": ("modify_xml", get_string("task_title_modify_xml_nowipe")),
        "10": ("flash_edl", get_string("task_title_flash_edl")),
        "11": ("clean", get_string("task_title_clean"))
    }

    while True:
        print_advanced_menu()
        choice = input(get_string("menu_adv_prompt")).strip().lower()

        if choice in actions_map:
            cmd, title = actions_map[choice]
            run_task(cmd, title, skip_adb)
            if choice == "11":
                sys.exit()
        elif choice == "m":
            return
        else:
            print(get_string("menu_adv_invalid"))
            if platform.system() == "Windows":
                os.system(f"pause > nul & echo {get_string('press_any_key')}...")
            else:
                input(get_string("press_enter_to_continue"))

def print_root_menu():
    os.system('cls' if os.name == 'nt' else 'clear')
    print("\n  " + "=" * 58)
    print(get_string("menu_root_title"))
    print("  " + "=" * 58 + "\n")
    print(get_string("menu_root_1"))
    print(get_string("menu_root_2"))
    print("\n" + get_string("menu_root_m"))
    print("\n  " + "=" * 58 + "\n")

def root_menu(skip_adb):
    actions_map = {
        "1": ("root_boot_only", get_string("task_title_root_file")),
        "2": ("root_device", get_string("task_title_root")),
    }

    while True:
        print_root_menu()
        choice = input(get_string("menu_root_prompt")).strip().lower()

        if choice in actions_map:
            cmd, title = actions_map[choice]
            run_task(cmd, title, skip_adb)
        elif choice == "m":
            return
        else:
            print(get_string("menu_root_invalid"))
            if platform.system() == "Windows":
                os.system(f"pause > nul & echo {get_string('press_any_key')}...")
            else:
                input(get_string("press_enter_to_continue"))

def main():
    skip_adb = False
    
    actions_map = {
        "1": ("patch_all_wipe", get_string("task_title_install_wipe")),
        "2": ("patch_all", get_string("task_title_install_nowipe")),
        "3": ("disable_ota", get_string("task_title_disable_ota")),
        "5": ("unroot_device", get_string("task_title_unroot")),
    }

    while True:
        print_main_menu(skip_adb)
        choice = input(get_string("menu_main_prompt")).strip().lower()

        if choice in actions_map:
            cmd, title = actions_map[choice]
            run_task(cmd, title, skip_adb)
        elif choice == "4":
            root_menu(skip_adb)
        elif choice == "6":
            skip_adb = not skip_adb
        elif choice == "a":
            advanced_menu(skip_adb)
        elif choice == "x":
            break
        else:
            print(get_string("menu_main_invalid"))
            if platform.system() == "Windows":
                os.system(f"pause > nul & echo {get_string('press_any_key')}...")
            else:
                input(get_string("press_enter_to_continue"))

if __name__ == "__main__":
    
    check_path_encoding()
    
    if len(sys.argv) > 1 and sys.argv[1].lower() == 'info':
        if len(sys.argv) > 2:
            run_info_scan(sys.argv[2:])
        else:
            print(get_string("info_no_files_dragged"), file=sys.stderr)
            print(get_string("info_drag_files_prompt"), file=sys.stderr)
        
        if platform.system() == "Windows":
            os.system("pause")
    else:
        main()