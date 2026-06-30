import ttkbootstrap as tb
from ttkbootstrap.constants import *
from tkcalendar import DateEntry
import tkinter as tk
from tkinter import messagebox
from urllib.parse import urlparse

from datetime import datetime, timedelta
import threading, json, os, sys, time
import webbrowser

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.keys import Keys
from selenium.common.exceptions import WebDriverException
from selenium.common.exceptions import InvalidSessionIdException

# ================= GLOBAL =================
is_paused = False
stop_execution = False


def get_runtime_base_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def get_config_file_path():
    return os.path.join(get_runtime_base_dir(), "config.json")


def create_chrome_driver():
    runtime_dir = get_runtime_base_dir()
    profile_dir = os.path.join(runtime_dir, "chrome-profile")
    os.makedirs(profile_dir, exist_ok=True)

    options = webdriver.ChromeOptions()
    options.add_argument(f"--user-data-dir={profile_dir}")
    options.add_argument("--profile-directory=Default")

    search_paths = [
        os.path.join(runtime_dir, "chromedriver.exe"),
        os.path.join(getattr(sys, "_MEIPASS", runtime_dir), "chromedriver.exe"),
    ]

    for driver_path in search_paths:
        if os.path.exists(driver_path):
            return webdriver.Chrome(service=Service(driver_path), options=options)

    # Fallback for environments where Selenium Manager can resolve the driver.
    return webdriver.Chrome(options=options)

# ================= CONFIG =================
def load_config():
    config_path = get_config_file_path()
    if os.path.exists(config_path):
        with open(config_path) as f:
            return json.load(f)
    return {}

def save_config(data):
    with open(get_config_file_path(), "w") as f:
        json.dump(data, f, indent=4)

def wait_if_paused():
    global is_paused
    while is_paused:
        time.sleep(0.5)


def focus_form_context(driver, log_callback=None):
    """Switch driver context to where the shift form is present (main doc or iframe)."""
    probe_script = """
        function collectRoots(startRoot) {
            const roots = [];
            const stack = [startRoot];
            while (stack.length) {
                const root = stack.pop();
                if (!root) continue;
                roots.push(root);

                let nodes = [];
                try {
                    nodes = root.querySelectorAll('*');
                } catch (_) {
                    nodes = [];
                }

                for (const el of nodes) {
                    if (el && el.shadowRoot) stack.push(el.shadowRoot);
                }
            }
            return roots;
        }

        const roots = collectRoots(document);
        const info = {
            headers: 0,
            datepickers: 0,
            timepickers: 0,
            shiftDropdowns: 0,
            forms: 0,
            modals: 0,
            titleHits: 0,
            titleTexts: []
        };

        const titleNeedles = [
            'shift/on-call support allowance',
            'shift allowance',
            'on-call support allowance',
            'initiate flow'
        ];

        for (const root of roots) {
            info.headers += root.querySelectorAll('div.section-header, [class*="section-header"]').length;
            info.datepickers += root.querySelectorAll('dbx-ds-datepicker').length;
            info.timepickers += root.querySelectorAll('dbx-ds-timepicker').length;
            info.shiftDropdowns += root.querySelectorAll('dbx-ds-dropdown, dbx-internal-dropdown').length;
            info.forms += root.querySelectorAll('db-form, dbx-form').length;
            info.modals += root.querySelectorAll('dbx-ds-modal, ds-modal, [part*="modal"], [class*="modal"]').length;

            const maybeTitleNodes = root.querySelectorAll('h1, h2, h3, [class*="title"], [part*="title"], .top-bar, .db-modal-header');
            for (const node of maybeTitleNodes) {
                const text = (node.innerText || node.textContent || '').trim();
                if (!text) continue;
                const low = text.toLowerCase();
                if (titleNeedles.some(n => low.includes(n))) {
                    info.titleHits += 1;
                    if (info.titleTexts.length < 3) info.titleTexts.push(text.slice(0, 140));
                }
            }
        }

        info.contextFound = (
            (info.headers > 0 && (info.datepickers > 0 || info.timepickers > 0 || info.shiftDropdowns > 0)) ||
            (info.forms > 0 && (info.datepickers > 0 || info.timepickers > 0)) ||
            (info.modals > 0 && info.titleHits > 0)
        );

        return info;
    """

    has_form_script = """
        function collectRoots(startRoot) {
            const roots = [];
            const stack = [startRoot];
            while (stack.length) {
                const root = stack.pop();
                if (!root) continue;
                roots.push(root);

                let nodes = [];
                try {
                    nodes = root.querySelectorAll('*');
                } catch (_) {
                    nodes = [];
                }

                for (const el of nodes) {
                    if (el && el.shadowRoot) {
                        stack.push(el.shadowRoot);
                    }
                }
            }
            return roots;
        }

        const roots = collectRoots(document);
        for (const root of roots) {
            const headers = root.querySelectorAll('div.section-header, [class*="section-header"]');
            const datepickers = root.querySelectorAll('dbx-ds-datepicker');
            const timepickers = root.querySelectorAll('dbx-ds-timepicker');
            const dropdowns = root.querySelectorAll('dbx-ds-dropdown, dbx-internal-dropdown');
            const forms = root.querySelectorAll('db-form, dbx-form');
            const modals = root.querySelectorAll('dbx-ds-modal, ds-modal, [part*="modal"], [class*="modal"]');

            let titleHit = false;
            const titleNeedles = [
                'shift/on-call support allowance',
                'shift allowance',
                'on-call support allowance',
                'initiate flow'
            ];
            const titleNodes = root.querySelectorAll('h1, h2, h3, [class*="title"], [part*="title"], .top-bar, .db-modal-header');
            for (const n of titleNodes) {
                const txt = (n.innerText || n.textContent || '').toLowerCase();
                if (titleNeedles.some(needle => txt.includes(needle))) {
                    titleHit = true;
                    break;
                }
            }

            if (
                (headers.length > 0 && (datepickers.length > 0 || timepickers.length > 0 || dropdowns.length > 0)) ||
                (forms.length > 0 && (datepickers.length > 0 || timepickers.length > 0)) ||
                (modals.length > 0 && titleHit)
            ) {
                return true;
            }
        }
        return false;
    """

    def search_frames_recursively(depth=0, max_depth=5):
        if depth > max_depth:
            return False

        if log_callback and depth == 0:
            try:
                info = driver.execute_script(probe_script)
                if info:
                    titles = " | ".join(info.get("titleTexts", [])) if isinstance(info, dict) else ""
                    log_callback(
                        "Form probe: "
                        f"headers={info.get('headers', 0)}, "
                        f"datepickers={info.get('datepickers', 0)}, "
                        f"timepickers={info.get('timepickers', 0)}, "
                        f"dropdowns={info.get('shiftDropdowns', 0)}, "
                        f"forms={info.get('forms', 0)}, "
                        f"modals={info.get('modals', 0)}, "
                        f"titleHits={info.get('titleHits', 0)}"
                    )
                    if titles:
                        log_callback(f"Title probe match: {titles}")
            except Exception:
                pass

        try:
            if driver.execute_script(has_form_script):
                return True
        except Exception:
            pass

        try:
            frames = driver.find_elements("tag name", "iframe")
        except Exception:
            frames = []

        for idx, frame in enumerate(frames):
            try:
                driver.switch_to.frame(frame)
                if search_frames_recursively(depth + 1, max_depth=max_depth):
                    if log_callback:
                        log_callback(f"Shift form found inside iframe depth {depth + 1}, index {idx}.")
                    return True
                driver.switch_to.parent_frame()
            except Exception:
                try:
                    driver.switch_to.parent_frame()
                except Exception:
                    pass
                continue

        return False

    try:
        driver.switch_to.default_content()
    except Exception:
        return False

    found = search_frames_recursively(depth=0, max_depth=5)
    if found:
        return True

    try:
        driver.switch_to.default_content()
    except Exception:
        pass
    return False


def wait_for_form_context(driver, timeout=60, log_callback=None):
    """Wait until shift form context is available in main page or iframe."""
    end_time = time.time() + timeout
    attempt = 0

    while time.time() < end_time:
        attempt += 1
        if focus_form_context(driver, log_callback=log_callback):
            if log_callback:
                log_callback(f"Form context detected after {attempt} check(s).")
            return True

        if log_callback and attempt % 5 == 0:
            seconds_left = max(0, int(end_time - time.time()))
            log_callback(f"Waiting for form context... ({seconds_left}s remaining)")

        time.sleep(1)

    if log_callback:
        try:
            current_url = driver.current_url
        except Exception:
            current_url = "unavailable"
        log_callback(f"Timed out waiting for form context (timeout={timeout}s, url={current_url}).")

    return False


def wait_for_form_ready(driver, timeout=90, log_callback=None):
    end_time = time.time() + timeout
    attempt = 0
    while time.time() < end_time:
        attempt += 1
        try:
            ready = focus_form_context(driver, log_callback=log_callback)
            if ready:
                if log_callback:
                    log_callback(f"Shift form ready detected after {attempt} check(s).")
                return True
        except WebDriverException:
            pass
        if log_callback and attempt % 5 == 0:
            seconds_left = max(0, int(end_time - time.time()))
            log_callback(f"Waiting for shift form to load... ({seconds_left}s remaining)")
        time.sleep(1)

    if log_callback:
        try:
            current_url = driver.current_url
        except Exception:
            current_url = "unavailable"
        log_callback(f"Timed out waiting for shift form (timeout={timeout}s, url={current_url}).")
    return False


def wait_for_form_controls(driver, timeout=60, log_callback=None):
    """Wait for actionable controls after modal/form shell appears."""
    end_time = time.time() + timeout
    attempt = 0
    script = """
        function collectRoots(startRoot) {
            const roots = [];
            const stack = [startRoot];
            while (stack.length) {
                const root = stack.pop();
                if (!root) continue;
                roots.push(root);
                let nodes = [];
                try { nodes = root.querySelectorAll('*'); } catch (_) { nodes = []; }
                for (const el of nodes) {
                    if (el && el.shadowRoot) stack.push(el.shadowRoot);
                }
            }
            return roots;
        }

        const roots = collectRoots(document);
        let datepickers = 0;
        let timepickers = 0;
        let dropdowns = 0;
        for (const root of roots) {
            datepickers += root.querySelectorAll('dbx-ds-datepicker').length;
            timepickers += root.querySelectorAll('dbx-ds-timepicker').length;
            dropdowns += root.querySelectorAll('dbx-ds-dropdown, dbx-internal-dropdown').length;
        }
        return {
            ready: datepickers > 0 && (timepickers > 0 || dropdowns > 0),
            datepickers,
            timepickers,
            dropdowns
        };
    """

    while time.time() < end_time:
        attempt += 1
        try:
            info = driver.execute_script(script)
            if info and info.get("ready"):
                if log_callback:
                    log_callback(
                        "Actionable controls detected: "
                        f"datepickers={info.get('datepickers', 0)}, "
                        f"timepickers={info.get('timepickers', 0)}, "
                        f"dropdowns={info.get('dropdowns', 0)}"
                    )
                return True
            if log_callback and attempt % 5 == 0:
                seconds_left = max(0, int(end_time - time.time()))
                if info:
                    log_callback(
                        "Waiting for actionable controls... "
                        f"datepickers={info.get('datepickers', 0)}, "
                        f"timepickers={info.get('timepickers', 0)}, "
                        f"dropdowns={info.get('dropdowns', 0)} "
                        f"({seconds_left}s remaining)"
                    )
                else:
                    log_callback(f"Waiting for actionable controls... ({seconds_left}s remaining)")
        except Exception:
            pass
        time.sleep(1)

    return False

def execute_script_with_retry(driver, script, args=(), retries=10, delay=0.5):
    """Run JS until it returns truthy or retries are exhausted."""
    for _ in range(retries):
        try:
            if driver.execute_script(script, *args):
                return True
        except:
            pass
        time.sleep(delay)
    return False


def switch_to_next_form_context(driver, known_handles):
    """Switch to a newly opened tab/window if available; otherwise use the latest handle."""
    try:
        current_handles = driver.window_handles
        if not current_handles:
            return False

        new_handles = [h for h in current_handles if h not in known_handles]
        if new_handles:
            driver.switch_to.window(new_handles[-1])
            return True

        # Fallback: stay with the most recent handle when no new handle is detected.
        driver.switch_to.window(current_handles[-1])
        return True
    except Exception:
        return False

def is_valid_shift_url(url):
    try:
        parsed = urlparse(url.strip())
        return parsed.scheme in ("http", "https") and bool(parsed.netloc)
    except Exception:
        return False

# ✅ LOGIN WAIT POPUP (THREAD-SAFE)
def wait_after_login(root):
    proceed_event = threading.Event()

    def show_popup():
        popup = tk.Toplevel(root)
        popup.title("Login Required")
        popup.geometry("300x120")
        popup.transient(root)

        def continue_after_login():
            if popup.winfo_exists():
                popup.destroy()
            proceed_event.set()

        tk.Label(popup, text="Login in browser,\nthen click Continue").pack(pady=20)
        tk.Button(popup, text="Continue", command=continue_after_login).pack()

        popup.protocol("WM_DELETE_WINDOW", continue_after_login)
        popup.grab_set()

    # Tk widgets must be created on the main/UI thread.
    root.after(0, show_popup)
    proceed_event.wait()

# ✅ HANDLE PROCEED BUTTON
def handle_post_login(driver, shift_url):

    for _ in range(30):

        time.sleep(1)

        try:
            clicked = driver.execute_script("""
                function deepFind(root){
                    if(!root) return null;
                    let els = root.querySelectorAll("button, span, div");

                    for(let e of els){
                        let t=(e.innerText||"").toLowerCase();
                        if(t.includes("proceed")||t.includes("continue")) return e;
                    }

                    for(let e of els){
                        if(e.shadowRoot){
                            let r=deepFind(e.shadowRoot);
                            if(r) return r;
                        }
                    }
                    return null;
                }

                let btn=deepFind(document);
                if(btn){btn.click(); return true;}
                return false;
            """)

            if clicked:
                time.sleep(3)

            driver.get(shift_url)
            return

        except:
            pass

    driver.get(shift_url)

def open_time_dropdown(driver, day_index, timepicker_index, dropdown_index):
    return driver.execute_script("""
        function findDayBlocks(root) {
            const all = Array.from(root.querySelectorAll('*'));
            const qualifies = (el) => {
                try {
                    const dps = el.querySelectorAll('dbx-ds-datepicker').length;
                    const tps = el.querySelectorAll('dbx-ds-timepicker').length;
                    const dds = el.querySelectorAll('dbx-ds-dropdown, dbx-internal-dropdown').length;
                    return dps >= 2 && tps >= 2 && dds >= 1;
                } catch (_) {
                    return false;
                }
            };
            const candidates = all.filter(qualifies);
            return candidates.filter(el => !candidates.some(other => other !== el && el.contains(other)));
        }

        function findFormRoot() {
            const candidates = [];
            const stack = [document];
            while (stack.length) {
                const root = stack.pop();
                if (!root) continue;
                let nodes = [];
                try { nodes = root.querySelectorAll('*'); } catch (_) { nodes = []; }
                for (const el of nodes) {
                    const tag = (el.tagName || '').toLowerCase();
                    if (tag === 'db-form' || tag === 'dbx-form') {
                        candidates.push(el.shadowRoot || el);
                    }
                    if (el.shadowRoot) stack.push(el.shadowRoot);
                }
            }
            for (const c of candidates) {
                const headers = c.querySelectorAll('div.section-header, [class*="section-header"]');
                const tps = c.querySelectorAll('dbx-ds-timepicker');
                const blocks = findDayBlocks(c);
                if ((headers.length > 0 || blocks.length > 0) && tps.length > 0) return c;
            }
            return candidates[0] || null;
        }

        const root = findFormRoot();
        if (!root) return null;

        const headers = root.querySelectorAll('div.section-header, [class*="section-header"]');
        const header = headers[arguments[0]];

        let day = null;
        if (header) {
            day = header;
            for (let i = 0; i < 8 && day; i++) {
                if (day.querySelector('dbx-ds-timepicker')) break;
                day = day.parentElement;
            }
        }

        if (!day) {
            const blocks = findDayBlocks(root);
            day = blocks[arguments[0]] || null;
        }
        if (!day) return null;

        const timepickers = day.querySelectorAll('dbx-ds-timepicker');
        const tp = timepickers[arguments[1]];
        if (!tp || !tp.shadowRoot) return null;

        const dropdowns = tp.shadowRoot.querySelectorAll('dbx-internal-dropdown');
        const dropdown = dropdowns[arguments[2]];
        if (!dropdown || !dropdown.shadowRoot) return null;

        const head = dropdown.shadowRoot
            .querySelector('dbx-dropdown-head')
            ?.shadowRoot
            ?.querySelector('#main-wrapper');

        if (!head) return null;
        head.scrollIntoView({ block: 'center', inline: 'nearest' });
        head.click();
        return dropdown;
    """, day_index, timepicker_index, dropdown_index)

def keyboard_select_from_top(driver, option_index):
    actions = ActionChains(driver)
    for _ in range(30):
        actions.send_keys(Keys.ARROW_UP)
    for _ in range(option_index):
        actions.send_keys(Keys.ARROW_DOWN)
    actions.send_keys(Keys.ENTER).perform()
    time.sleep(0.4)

def keyboard_select_time_value(driver, val):
    keyboard_select_from_top(driver, int(val) + 1)


def set_time_direct(driver, day_index, timepicker_index, hour, minute):
    """Set HH/MM directly inside timepicker inputs for accordion-based Darwinbox layouts."""
    return driver.execute_script("""
        const dayIndex = arguments[0];
        const tpIndex = arguments[1];
        const hh = String(arguments[2]).padStart(2, '0');
        const mm = String(arguments[3]).padStart(2, '0');

        function findDayBlocks(root) {
            const all = Array.from(root.querySelectorAll('*'));
            const qualifies = (el) => {
                try {
                    const dps = el.querySelectorAll('dbx-ds-datepicker').length;
                    const tps = el.querySelectorAll('dbx-ds-timepicker').length;
                    const dds = el.querySelectorAll('dbx-ds-dropdown, dbx-internal-dropdown').length;
                    return dps >= 2 && tps >= 2 && dds >= 1;
                } catch (_) {
                    return false;
                }
            };
            const candidates = all.filter(qualifies);
            return candidates.filter(el => !candidates.some(other => other !== el && el.contains(other)));
        }

        function findFormRoot() {
            const candidates = [];
            const stack = [document];
            while (stack.length) {
                const root = stack.pop();
                if (!root) continue;
                let nodes = [];
                try { nodes = root.querySelectorAll('*'); } catch (_) { nodes = []; }
                for (const el of nodes) {
                    const tag = (el.tagName || '').toLowerCase();
                    if (tag === 'db-form' || tag === 'dbx-form') {
                        candidates.push(el.shadowRoot || el);
                    }
                    if (el.shadowRoot) stack.push(el.shadowRoot);
                }
            }
            return candidates[0] || null;
        }

        function setInputValue(input, value) {
            if (!input) return false;
            input.focus();
            input.value = '';
            input.dispatchEvent(new Event('input', { bubbles: true }));
            input.value = value;
            input.dispatchEvent(new Event('input', { bubbles: true }));
            input.dispatchEvent(new Event('change', { bubbles: true }));
            input.dispatchEvent(new Event('blur', { bubbles: true }));
            return true;
        }

        const root = findFormRoot();
        if (!root) return false;

        const headers = root.querySelectorAll('div.section-header, [class*="section-header"]');
        let day = null;
        if (headers[dayIndex]) {
            day = headers[dayIndex];
            for (let i = 0; i < 8 && day; i++) {
                if (day.querySelector('dbx-ds-timepicker')) break;
                day = day.parentElement;
            }
        }
        if (!day) {
            const blocks = findDayBlocks(root);
            day = blocks[dayIndex] || null;
        }
        if (!day) return false;

        const timepickers = day.querySelectorAll('dbx-ds-timepicker');
        const tp = timepickers[tpIndex];
        if (!tp || !tp.shadowRoot) return false;

        const inputs = Array.from(tp.shadowRoot.querySelectorAll('input'));
        if (inputs.length >= 2) {
            const ok1 = setInputValue(inputs[0], hh);
            const ok2 = setInputValue(inputs[1], mm);
            return !!(ok1 && ok2);
        }

        const internalDropdowns = tp.shadowRoot.querySelectorAll('dbx-internal-dropdown');
        if (internalDropdowns.length >= 2) {
            const setByDropdownInput = (dd, value) => {
                if (!dd || !dd.shadowRoot) return false;
                const inp = dd.shadowRoot.querySelector('input');
                return setInputValue(inp, value);
            };
            const ok1 = setByDropdownInput(internalDropdowns[0], hh);
            const ok2 = setByDropdownInput(internalDropdowns[1], mm);
            return !!(ok1 && ok2);
        }

        return false;
    """, day_index, timepicker_index, hour, minute)

def pick_time(driver, day_index, timepicker_index, hour, minute):
    hour_dropdown = open_time_dropdown(driver, day_index, timepicker_index, 0)
    if hour_dropdown:
        time.sleep(0.4)
        keyboard_select_time_value(driver, hour)

        minute_dropdown = open_time_dropdown(driver, day_index, timepicker_index, 1)
        if minute_dropdown:
            time.sleep(0.4)
            keyboard_select_time_value(driver, minute)
            return True

    # Fallback for newer accordion-based layouts with direct HH/MM fields.
    return bool(set_time_direct(driver, day_index, timepicker_index, hour, minute))

def open_shift_dropdown(driver, day_index):
    return driver.execute_script("""
        function findDayBlocks(root) {
            const all = Array.from(root.querySelectorAll('*'));
            const qualifies = (el) => {
                try {
                    const dps = el.querySelectorAll('dbx-ds-datepicker').length;
                    const tps = el.querySelectorAll('dbx-ds-timepicker').length;
                    const dds = el.querySelectorAll('dbx-ds-dropdown, dbx-internal-dropdown').length;
                    return dps >= 2 && tps >= 2 && dds >= 1;
                } catch (_) {
                    return false;
                }
            };
            const candidates = all.filter(qualifies);
            return candidates.filter(el => !candidates.some(other => other !== el && el.contains(other)));
        }

        function findFormRoot() {
            const candidates = [];
            const stack = [document];
            while (stack.length) {
                const root = stack.pop();
                if (!root) continue;
                let nodes = [];
                try { nodes = root.querySelectorAll('*'); } catch (_) { nodes = []; }
                for (const el of nodes) {
                    const tag = (el.tagName || '').toLowerCase();
                    if (tag === 'db-form' || tag === 'dbx-form') {
                        candidates.push(el.shadowRoot || el);
                    }
                    if (el.shadowRoot) stack.push(el.shadowRoot);
                }
            }
            for (const c of candidates) {
                const headers = c.querySelectorAll('div.section-header, [class*="section-header"]');
                const dds = c.querySelectorAll('dbx-ds-dropdown, dbx-internal-dropdown');
                const blocks = findDayBlocks(c);
                if ((headers.length > 0 || blocks.length > 0) && dds.length > 0) return c;
            }
            return candidates[0] || null;
        }

        const root = findFormRoot();
        if (!root) return null;

        const headers = root.querySelectorAll('div.section-header, [class*="section-header"]');
        const header = headers[arguments[0]];

        let day = null;
        if (header) {
            day = header;
            for (let i = 0; i < 8 && day; i++) {
                if (day.querySelector('dbx-ds-dropdown')) break;
                day = day.parentElement;
            }
        }

        if (!day) {
            const blocks = findDayBlocks(root);
            day = blocks[arguments[0]] || null;
        }
        if (!day) return null;

        const dd = day.querySelector('dbx-ds-dropdown');
        if (!dd || !dd.shadowRoot) return null;

        const dropdown = dd.shadowRoot.querySelector('dbx-internal-dropdown');
        if (!dropdown || !dropdown.shadowRoot) return null;

        const head = dropdown.shadowRoot
            .querySelector('dbx-dropdown-head')
            ?.shadowRoot
            ?.querySelector('#main-wrapper');

        if (!head) return null;
        head.scrollIntoView({ block: 'center', inline: 'nearest' });
        head.click();
        return dropdown;
    """, day_index)

def pick_shift(driver, day_index, shift_name):
    dropdown = open_shift_dropdown(driver, day_index)
    if not dropdown:
        return False
    time.sleep(0.4)
    ActionChains(driver) \
        .send_keys(shift_name) \
        .send_keys(Keys.ARROW_DOWN) \
        .send_keys(Keys.ENTER) \
        .perform()
    time.sleep(0.4)
    return True

# ================= APP =================
class App:

    def __init__(self):

        self.saved = load_config()
        self.next_form_event = threading.Event()
        self.driver = None
        self.login_completed = False
        self.is_running = False

        self.root = tb.Window(themename="litera")
        self.root.title("Shift Entry Bot")
        self.root.geometry("1100x1000")
        self.root.state("zoomed")
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        self.build_ui()
        self.root.mainloop()

    # ---------- LOG ----------
    def log(self, msg):
        if msg.startswith((
            "Form probe:",
            "Title probe match:",
            "Form diagnostics:",
            "Shift form found inside iframe",
            "Actionable controls detected:",
            "Waiting for actionable controls... datepickers=",
            "Opening day section index",
            "Opened day section index",
            "Accordion state[",
            "Setting date values for index",
            "Date values set for index",
            "Selecting IN time for index",
            "IN time set for index",
            "Selecting OUT time for index",
            "OUT time set for index",
            "Selecting shift name for index",
            "Shift name set for index",
        )):
            return
        self.logs.insert(tk.END, msg + "\n")
        self.logs.see(tk.END)

    def error(self, msg):
        self.errors.insert(tk.END, "❌ " + msg + "\n")
        self.errors.see(tk.END)

    # ================= UI =================
    def build_ui(self):

        self.root.columnconfigure(1, weight=1)
        self.root.rowconfigure(0, weight=1)

        sidebar = tb.Frame(self.root, width=320, padding=10)
        sidebar.grid(row=0, column=0, sticky="ns")
        sidebar.grid_propagate(False)

        # tb.Label(sidebar, text="Shift Tool", font=("Segoe UI", 16, "bold")).pack(anchor="w", pady=(0, 10))

        date_section = tb.Labelframe(sidebar, text="Date Range", padding=6)
        date_section.pack(fill=X, pady=(0, 6))

        self.start_date = DateEntry(date_section, date_pattern="dd-mm-yyyy", width=18)
        self.end_date = DateEntry(date_section, date_pattern="dd-mm-yyyy", width=18)
        self.start_date.pack(fill=X, pady=(0, 4))
        self.end_date.pack(fill=X)

        mode_section = tb.Labelframe(sidebar, text="Shift Type", padding=6)
        mode_section.pack(fill=X, pady=(0, 6))
        self.shift_type = tb.Combobox(mode_section, values=["Day", "Night"], state="readonly")
        self.shift_type.set("Day")
        self.shift_type.pack(fill=X)

        url_section = tb.Labelframe(sidebar, text="Shift URL", padding=6)
        url_section.pack(fill=X, pady=(0, 6))

        self.url = tb.Entry(url_section)
        self.url.pack(fill=X)
        saved_url = self.saved.get("shift_url", "")
        if saved_url:
            self.url.insert(0, saved_url)

        holiday_section = tb.Labelframe(sidebar, text="Leave/Holiday", padding=6)
        holiday_section.pack(fill=X, pady=(0, 6))

        self.h_picker = DateEntry(holiday_section, date_pattern="dd-mm-yyyy", width=18)
        self.h_picker.pack(fill=X, pady=(0, 4))

        self.h_list = tk.Listbox(holiday_section, height=4)
        self.h_list.pack(fill=X)

        def add_h():
            d = self.h_picker.get()
            if d not in self.h_list.get(0, tk.END):
                self.h_list.insert(tk.END, d)

        def rem_h():
            for i in reversed(self.h_list.curselection()):
                self.h_list.delete(i)

        tb.Button(holiday_section, text="Add", command=add_h).pack(fill=X, pady=(4, 2))
        tb.Button(holiday_section, text="Remove", command=rem_h).pack(fill=X)

        shift_section = tb.Labelframe(sidebar, text="Shift Details", padding=6)
        shift_section.pack(fill=X, pady=(0, 6))
        shift_section.columnconfigure(1, weight=1)
        shift_section.columnconfigure(2, weight=1)

        tb.Label(shift_section, text="").grid(row=0, column=0, sticky="w")
        tb.Label(shift_section, text="Hour").grid(row=0, column=1, sticky="w", padx=(0, 6))
        tb.Label(shift_section, text="Minute").grid(row=0, column=2, sticky="w")

        self.in_h = tb.Combobox(shift_section, values=[f"{i:02}" for i in range(24)], width=8, state="readonly")
        self.in_m = tb.Combobox(shift_section, values=["00", "15", "30", "45"], width=8, state="readonly")
        self.out_h = tb.Combobox(shift_section, values=[f"{i:02}" for i in range(24)], width=8, state="readonly")
        self.out_m = tb.Combobox(shift_section, values=["00", "15", "30", "45"], width=8, state="readonly")

        self.in_h.set("14")
        self.in_m.set("00")
        self.out_h.set("22")
        self.out_m.set("00")

        tb.Label(shift_section, text="In").grid(row=1, column=0, sticky="w", pady=(2, 6), padx=(0, 8))
        self.in_h.grid(row=1, column=1, sticky="ew", pady=(1, 4), padx=(0, 6))
        self.in_m.grid(row=1, column=2, sticky="ew", pady=(1, 4))

        tb.Label(shift_section, text="Out").grid(row=2, column=0, sticky="w", pady=(0, 8), padx=(0, 8))
        self.out_h.grid(row=2, column=1, sticky="ew", pady=(0, 5), padx=(0, 6))
        self.out_m.grid(row=2, column=2, sticky="ew", pady=(0, 5))

        tb.Label(shift_section, text="Shift Name").grid(row=3, column=0, columnspan=3, sticky="w", pady=(0, 4))
        self.shift_name = tb.Combobox(
            shift_section,
            values=["First Shift", "Second Shift", "Night Shift", "On-Call Support"],
            state="readonly"
        )
        self.shift_name.set("Second Shift")
        self.shift_name.grid(row=4, column=0, columnspan=3, sticky="ew")

        button_section = tb.Frame(sidebar)
        button_section.pack(fill=X, pady=(2, 0))
        tb.Button(button_section, text="Start", bootstyle="success", command=self.start).pack(fill=X, pady=(0, 4))
        self.next_form_btn = tb.Button(
            button_section,
            text="Continue Next Form",
            bootstyle="info",
            command=self.continue_next_form,
            state="disabled"
        )
        self.next_form_btn.pack(fill=X, pady=(0, 4))
        tb.Button(button_section, text="Pause", command=self.pause).pack(fill=X, pady=(0, 4))
        tb.Button(button_section, text="Stop", bootstyle="danger", command=self.stop).pack(fill=X)
        author_link = tb.Label(
            sidebar,
            text="Author - Naveenkumar Angamuthu",
            font=("Segoe UI", 7, "underline"),
            foreground="#0a66c2",
            cursor="hand2"
        )
        author_link.pack(fill="x", pady=(6, 2))
        author_link.bind(
            "<Button-1>",
            lambda _event: webbrowser.open_new_tab("https://www.linkedin.com/in/naveenkumar-angamuthu-b16ba5190/")
        )

        # MAIN
        main = tb.Frame(self.root)
        main.grid(row=0, column=1, sticky="nsew")

        self.logs = tk.Text(main, height=20)
        self.logs.pack(fill=BOTH, expand=YES)

        self.errors = tk.Text(main, height=8, bg="#fff5f5")
        self.errors.pack(fill=BOTH)

    # ================= CONTROL =================
    def pause(self):
        global is_paused
        is_paused = not is_paused
        self.log("Paused" if is_paused else "Resumed")

    def stop(self):
        global stop_execution
        stop_execution = True
        self.log("Stopping...")

    def on_close(self):
        try:
            if self.driver:
                self.driver.quit()
        except Exception:
            pass
        self.driver = None
        self.root.destroy()

    def start(self):
        if self.is_running:
            self.log("Flow already running. Please wait or click Stop.")
            return

        shift_url = self.url.get().strip()
        if not shift_url:
            messagebox.showerror("Invalid Shift URL", "Please enter the shift URL before starting.")
            return

        if not is_valid_shift_url(shift_url):
            messagebox.showerror("Invalid Shift URL", "Please enter a valid URL (http:// or https://).")
            return

        self.saved["shift_url"] = shift_url
        save_config(self.saved)
        self.log(f"Validated shift URL: {shift_url}")
        self.log("Saved shift URL to config.json")

        self.log("Starting automation...")
        self.is_running = True
        threading.Thread(target=self.run, daemon=True).start()

    def continue_next_form(self):
        self.next_form_event.set()
        self.log("Continue requested. Resuming in current session...")

    def wait_for_next_form(self):
        global stop_execution

        self.next_form_event.clear()

        def enable_button_and_prompt():
            self.next_form_btn.configure(state="normal")
            messagebox.showinfo(
                "Open Next Form",
                "Filled 18 entries in this form.\n\n"
                "Open the next shift form in the same browser session, then click 'Continue Next Form'."
            )

        self.root.after(0, enable_button_and_prompt)
        self.log("Waiting for next form. Open it in browser and click 'Continue Next Form'.")

        while not self.next_form_event.is_set():
            if stop_execution:
                self.log("Stop requested while waiting for next form.")
                self.root.after(0, lambda: self.next_form_btn.configure(state="disabled"))
                return False
            time.sleep(0.3)

        self.log("Continue signal received for next form.")
        self.root.after(0, lambda: self.next_form_btn.configure(state="disabled"))
        return True

    def fill_form_batch(
        self,
        driver,
        start_date,
        end_date,
        holidays,
        shift,
        selected_shift_name,
        is_cross_midnight,
        max_entries=18
    ):
        global stop_execution

        self.log("Locating form context (main page/iframe)...")
        if not wait_for_form_context(driver, timeout=90, log_callback=self.log):
            self.error("Unable to find shift form in page or iframe.")
            return start_date, 0

        self.log("Waiting for shift form readiness check...")
        if not wait_for_form_ready(driver, timeout=90, log_callback=self.log):
            self.error("Shift form did not load. Open the correct form and try Continue Next Form.")
            return start_date, 0
        self.log("Shift form is ready.")

        self.log("Waiting for date/time controls to become actionable...")
        if not wait_for_form_controls(driver, timeout=75, log_callback=self.log):
            self.error("Form shell detected, but date/time controls did not become ready.")
            return start_date, 0

        day_count = driver.execute_script("""
        function findDayBlocks(root) {
            const all = Array.from(root.querySelectorAll('*'));
            const qualifies = (el) => {
                try {
                    const dps = el.querySelectorAll('dbx-ds-datepicker').length;
                    const tps = el.querySelectorAll('dbx-ds-timepicker').length;
                    const dds = el.querySelectorAll('dbx-ds-dropdown, dbx-internal-dropdown').length;
                    return dps >= 2 && tps >= 2 && dds >= 1;
                } catch (_) {
                    return false;
                }
            };
            const candidates = all.filter(qualifies);
            return candidates.filter(el => !candidates.some(other => other !== el && el.contains(other)));
        }

        function findFormRoot() {
            const candidates = [];
            const stack = [document];
            while (stack.length) {
                const root = stack.pop();
                if (!root) continue;
                let nodes = [];
                try { nodes = root.querySelectorAll('*'); } catch (_) { nodes = []; }
                for (const el of nodes) {
                    const tag = (el.tagName || '').toLowerCase();
                    if (tag === 'db-form' || tag === 'dbx-form') {
                        candidates.push(el.shadowRoot || el);
                    }
                    if (el.shadowRoot) stack.push(el.shadowRoot);
                }
            }
            for (const c of candidates) {
                const headers = c.querySelectorAll('div.section-header, [class*="section-header"]');
                if (headers.length > 0) return c;
            }
            return candidates[0] || null;
        }
        const root = findFormRoot();
        if (!root) return 0;
        const headers = root.querySelectorAll('div.section-header, [class*="section-header"]');
        if (headers.length > 0) return headers.length;
        const blocks = findDayBlocks(root);
        return blocks.length;
        """)
        self.log(f"Detected {day_count} day section(s) in current form.")

        if day_count <= 0:
            debug_counts = driver.execute_script("""
                function findFormRoot() {
                    const candidates = [];
                    const stack = [document];
                    while (stack.length) {
                        const root = stack.pop();
                        if (!root) continue;
                        let nodes = [];
                        try { nodes = root.querySelectorAll('*'); } catch (_) { nodes = []; }
                        for (const el of nodes) {
                            const tag = (el.tagName || '').toLowerCase();
                            if (tag === 'db-form' || tag === 'dbx-form') {
                                candidates.push(el.shadowRoot || el);
                            }
                            if (el.shadowRoot) stack.push(el.shadowRoot);
                        }
                    }
                    for (const c of candidates) {
                        const headers = c.querySelectorAll('div.section-header, [class*="section-header"]');
                        if (headers.length > 0) return c;
                    }
                    return candidates[0] || null;
                }
                const root = findFormRoot();
                if (!root) return 'form-host=0, section-header=0, datepicker=0, timepicker=0';
                const headers = root.querySelectorAll('div.section-header, [class*="section-header"]').length;
                const dps = root.querySelectorAll('dbx-ds-datepicker').length;
                const tps = root.querySelectorAll('dbx-ds-timepicker').length;
                return `form-host=1, section-header=${headers}, datepicker=${dps}, timepicker=${tps}`;
            """)
            self.log(f"Form diagnostics: {debug_counts}")
            self.error("No day sections found in shift form.")
            return start_date, 0

        current_date = start_date
        entries_filled = 0
        batch_limit = min(day_count, max_entries)
        self.log(f"Starting batch with limit {batch_limit} entries.")

        for i in range(batch_limit):

            if stop_execution:
                self.log("Stop flag detected. Ending current batch.")
                break

            wait_if_paused()

            while current_date.weekday() >= 5 or current_date.date() in holidays:
                self.log(f"Skip {current_date}")
                current_date += timedelta(days=1)

            if current_date > end_date:
                self.log("Reached end date for this run.")
                break

            check_in_date = current_date
            check_out_date = current_date + timedelta(days=1) if is_cross_midnight else current_date

            check_in_date_str = check_in_date.strftime("%d-%m-%Y")
            check_out_date_str = check_out_date.strftime("%d-%m-%Y")

            self.log(
                f"➡ IN: {check_in_date_str} | OUT: {check_out_date_str} "
                f"({shift['type']}) | SHIFT: {selected_shift_name}"
            )

            try:
                self.log(f"Opening day section index {i}.")
                clicked = execute_script_with_retry(driver, """
                    const idx = arguments[0];
                    function findDayBlocks(root) {
                        const all = Array.from(root.querySelectorAll('*'));
                        const qualifies = (el) => {
                            try {
                                const dps = el.querySelectorAll('dbx-ds-datepicker').length;
                                const tps = el.querySelectorAll('dbx-ds-timepicker').length;
                                const dds = el.querySelectorAll('dbx-ds-dropdown, dbx-internal-dropdown').length;
                                return dps >= 2 && tps >= 2 && dds >= 1;
                            } catch (_) {
                                return false;
                            }
                        };
                        const candidates = all.filter(qualifies);
                        return candidates.filter(el => !candidates.some(other => other !== el && el.contains(other)));
                    }

                    function findFormRoot() {
                        const candidates = [];
                        const stack = [document];
                        while (stack.length) {
                            const root = stack.pop();
                            if (!root) continue;
                            let nodes = [];
                            try { nodes = root.querySelectorAll('*'); } catch (_) { nodes = []; }
                            for (const el of nodes) {
                                const tag = (el.tagName || '').toLowerCase();
                                if (tag === 'db-form' || tag === 'dbx-form') {
                                    candidates.push(el.shadowRoot || el);
                                }
                                if (el.shadowRoot) stack.push(el.shadowRoot);
                            }
                        }
                        for (const c of candidates) {
                            const headers = c.querySelectorAll('div.section-header, [class*="section-header"]');
                            if (headers.length > 0) return c;
                        }
                        return candidates[0] || null;
                    }

                    const root = findFormRoot();
                    if (!root) return false;

                    const deepQueryAll = (startRoot, selector) => {
                        const out = [];
                        const stack = [startRoot];
                        while (stack.length) {
                            const r = stack.pop();
                            if (!r) continue;
                            let found = [];
                            let nodes = [];
                            try { found = Array.from(r.querySelectorAll(selector)); } catch (_) { found = []; }
                            try { nodes = Array.from(r.querySelectorAll('*')); } catch (_) { nodes = []; }
                            out.push(...found);
                            for (const n of nodes) {
                                if (n && n.shadowRoot) stack.push(n.shadowRoot);
                            }
                        }
                        return out;
                    };

                    const getDayAccordions = () => {
                        const all = deepQueryAll(root, 'dbx-ds-accordion');
                        const tagged = all.filter(acc => {
                            try {
                                if (!acc.shadowRoot) return false;
                                const txt = (acc.shadowRoot.innerText || '').toLowerCase();
                                return txt.includes('day ') || txt.includes('date - check in');
                            } catch (_) {
                                return false;
                            }
                        });
                        return tagged.length > 0 ? tagged : all;
                    };

                    const accordionState = (acc) => {
                        if (!acc || !acc.shadowRoot) return { open: false, contentExpanded: false };
                        const main = acc.shadowRoot.querySelector('[part="main-wrapper"], .main-wrapper');
                        const content = acc.shadowRoot.querySelector('[part="content-wrapper"], .content-wrapper');

                        const cls = ((main && main.className) || '').toString().toLowerCase();
                        const open = cls.includes('is-open') || cls.includes('open');

                        let contentExpanded = false;
                        if (content) {
                            const h = (content.style && content.style.height) ? content.style.height.toLowerCase() : '';
                            const overflow = (content.style && content.style.overflow) ? content.style.overflow.toLowerCase() : '';
                            const rect = content.getBoundingClientRect();
                            contentExpanded = (
                                h === 'auto' ||
                                h === '' ||
                                (!h.includes('0px') && rect.height > 4) ||
                                overflow === 'visible'
                            );
                        }

                        return { open, contentExpanded };
                    };

                    const forceOpenAccordion = (acc) => {
                        if (!acc || !acc.shadowRoot) return false;

                        const isOpenByMainWrapper = () => {
                            const main = acc.shadowRoot.querySelector('[part="main-wrapper"], .main-wrapper');
                            const cls = ((main && main.className) || '').toString();
                            return cls.includes('is-open');
                        };

                        if (isOpenByMainWrapper()) return true;

                        const walkRoots = (root, visitor) => {
                            const stack = [root];
                            while (stack.length) {
                                const r = stack.pop();
                                if (!r) continue;

                                let nodes = [];
                                try { nodes = Array.from(r.querySelectorAll('*')); } catch (_) { nodes = []; }
                                for (const n of nodes) {
                                    try { visitor(n); } catch (_) {}

                                    if (n && n.shadowRoot) {
                                        stack.push(n.shadowRoot);
                                    }

                                    let assigned = [];
                                    try {
                                        if (typeof n.assignedElements === 'function') {
                                            assigned = n.assignedElements({ flatten: true }) || [];
                                        }
                                    } catch (_) {
                                        assigned = [];
                                    }

                                    for (const a of assigned) {
                                        if (a && a.shadowRoot) stack.push(a.shadowRoot);
                                        try { visitor(a); } catch (_) {}
                                    }
                                }
                            }
                        };

                        const findTitleCandidates = () => {
                            const exact = [];
                            const dayLike = [];

                            const pushIfVisible = (arr, el) => {
                                if (!el) return;
                                if (arr.includes(el)) return;
                                const rect = (typeof el.getBoundingClientRect === 'function') ? el.getBoundingClientRect() : null;
                                if (!rect || (rect.width <= 0 && rect.height <= 0)) return;
                                arr.push(el);
                            };

                            const checkNode = (el) => {
                                const cls = ((el.className || '') + '').toLowerCase();
                                const part = ((el.getAttribute && el.getAttribute('part')) || '').toLowerCase();
                                const text = ((el.innerText || el.textContent || '') + '').trim();
                                const low = text.toLowerCase();

                                if (cls.includes('title-wrapper') || part.includes('title-wrapper')) {
                                    pushIfVisible(exact, el);
                                    return;
                                }

                                if ((cls.includes('title') || part.includes('title')) && /^day\s+\d+/.test(low)) {
                                    pushIfVisible(dayLike, el);
                                    return;
                                }

                                if (/^day\s+\d+/.test(low)) {
                                    pushIfVisible(dayLike, el);
                                }
                            };

                            walkRoots(acc.shadowRoot, checkNode);
                            walkRoots(acc, checkNode);
                            return exact.length > 0 ? exact : dayLike;
                        };

                        const clickNode = (el) => {
                            try { el.scrollIntoView({ block: 'center', inline: 'nearest' }); } catch (_) {}
                            try {
                                el.click();
                            } catch (_) {
                                try {
                                    el.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, composed: true }));
                                } catch (_) {}
                            }
                        };

                        for (let attempt = 0; attempt < 8; attempt++) {
                            if (isOpenByMainWrapper()) return true;

                            const titleCandidates = findTitleCandidates();
                            for (const el of titleCandidates) {
                                clickNode(el);
                                if (isOpenByMainWrapper()) return true;
                            }

                            // Final fallback in each attempt.
                            const header = acc.shadowRoot.querySelector('[part="header-wrapper"], .header-wrapper, .header-content-wrapper, .header-content');
                            if (header) {
                                clickNode(header);
                                if (isOpenByMainWrapper()) return true;
                            }
                        }

                        const s = accordionState(acc);
                        return !!(isOpenByMainWrapper() || (s.open && s.contentExpanded));
                    };

                    const dayAccordions = getDayAccordions();
                    const acc = dayAccordions[idx];
                    if (!acc) return false;
                    return forceOpenAccordion(acc);
                    """, args=(i,), retries=20, delay=0.4)

                if not clicked:
                    raise Exception(f"Unable to open day section index {i}: accordion open failed")
                self.log(f"Opened day section index {i}.")

                open_state = driver.execute_script("""
                    const idx = arguments[0];
                    const deepQueryAll = (startRoot, selector) => {
                        const out = [];
                        const stack = [startRoot];
                        while (stack.length) {
                            const r = stack.pop();
                            if (!r) continue;
                            let found = [];
                            let nodes = [];
                            try { found = Array.from(r.querySelectorAll(selector)); } catch (_) { found = []; }
                            try { nodes = Array.from(r.querySelectorAll('*')); } catch (_) { nodes = []; }
                            out.push(...found);
                            for (const n of nodes) {
                                if (n && n.shadowRoot) stack.push(n.shadowRoot);
                            }
                        }
                        return out;
                    };

                    const accs = deepQueryAll(document, 'dbx-ds-accordion').filter(acc => {
                        try {
                            const txt = (acc.shadowRoot && acc.shadowRoot.innerText || '').toLowerCase();
                            return txt.includes('day ') || txt.includes('date - check in');
                        } catch (_) {
                            return false;
                        }
                    });
                    const acc = accs[idx] || null;
                    if (!acc || !acc.shadowRoot) return 'accordion-not-found';
                    const main = acc.shadowRoot.querySelector('[part="main-wrapper"], .main-wrapper');
                    const content = acc.shadowRoot.querySelector('[part="content-wrapper"], .content-wrapper');
                    const cls = ((main && main.className) || '').toString();
                    const h = (content && content.style && content.style.height) ? content.style.height : '';
                    const ov = (content && content.style && content.style.overflow) ? content.style.overflow : '';
                    return `mainClass=${cls} | contentHeight=${h} | contentOverflow=${ov}`;
                """, i)
                self.log(f"Accordion state[{i}]: {open_state}")

                self.log(f"Setting date values for index {i}.")
                filled = execute_script_with_retry(driver, """
                    const idx = arguments[0];
                    const inDate = arguments[1];
                    const outDate = arguments[2];

                    function findDayBlocks(root) {
                        const all = Array.from(root.querySelectorAll('*'));
                        const qualifies = (el) => {
                            try {
                                const dps = el.querySelectorAll('dbx-ds-datepicker').length;
                                const tps = el.querySelectorAll('dbx-ds-timepicker').length;
                                const dds = el.querySelectorAll('dbx-ds-dropdown, dbx-internal-dropdown').length;
                                return dps >= 2 && tps >= 2 && dds >= 1;
                            } catch (_) {
                                return false;
                            }
                        };
                        const candidates = all.filter(qualifies);
                        return candidates.filter(el => !candidates.some(other => other !== el && el.contains(other)));
                    }

                    function findFormRoot() {
                        const candidates = [];
                        const stack = [document];
                        while (stack.length) {
                            const root = stack.pop();
                            if (!root) continue;
                            let nodes = [];
                            try { nodes = root.querySelectorAll('*'); } catch (_) { nodes = []; }
                            for (const el of nodes) {
                                const tag = (el.tagName || '').toLowerCase();
                                if (tag === 'db-form' || tag === 'dbx-form') {
                                    candidates.push(el.shadowRoot || el);
                                }
                                if (el.shadowRoot) stack.push(el.shadowRoot);
                            }
                        }
                        for (const c of candidates) {
                            const headers = c.querySelectorAll('div.section-header, [class*="section-header"]');
                            if (headers.length > 0) return c;
                        }
                        return candidates[0] || null;
                    }

                    const root = findFormRoot();
                    if (!root) return false;

                    const headers = root.querySelectorAll('div.section-header, [class*="section-header"]');
                    const header = headers[idx];
                    let day = null;

                    if (header) {
                        day = header;
                        for (let i = 0; i < 8 && day; i++) {
                            if (day.querySelector('dbx-ds-datepicker')) break;
                            day = day.parentElement;
                        }
                    }

                    if (!day) {
                        const blocks = findDayBlocks(root);
                        day = blocks[idx] || null;
                    }
                    if (!day) return false;

                    const datepickers = day.querySelectorAll('dbx-ds-datepicker');
                    if (!datepickers || datepickers.length === 0) return false;

                    const setDate = (dp, value) => {
                        if (!dp || !dp.shadowRoot) return false;
                        const input = dp.shadowRoot.querySelector('input');
                        if (!input) return false;
                        input.value = value;
                        input.dispatchEvent(new Event('input', { bubbles: true }));
                        return true;
                    };

                    let setAny = false;
                    setAny = setDate(datepickers[0], inDate) || setAny;

                    if (datepickers.length > 1) {
                        setAny = setDate(datepickers[1], outDate) || setAny;
                    } else {
                        setAny = setDate(datepickers[0], outDate) || setAny;
                    }

                    return setAny;
                    """, args=(i, check_in_date_str, check_out_date_str))

                if not filled:
                    raise Exception(f"Unable to set date for day index {i}: datepicker shadow DOM not ready")
                self.log(f"Date values set for index {i}.")

                execute_script_with_retry(driver, """
                    const idx = arguments[0];
                    function findDayBlocks(root) {
                        const all = Array.from(root.querySelectorAll('*'));
                        const qualifies = (el) => {
                            try {
                                const dps = el.querySelectorAll('dbx-ds-datepicker').length;
                                const tps = el.querySelectorAll('dbx-ds-timepicker').length;
                                const dds = el.querySelectorAll('dbx-ds-dropdown, dbx-internal-dropdown').length;
                                return dps >= 2 && tps >= 2 && dds >= 1;
                            } catch (_) {
                                return false;
                            }
                        };
                        const candidates = all.filter(qualifies);
                        return candidates.filter(el => !candidates.some(other => other !== el && el.contains(other)));
                    }
                    const blocks = findDayBlocks(document);
                    const day = blocks[idx];
                    if (!day) return false;
                    day.scrollIntoView({ block: 'center', inline: 'nearest' });
                    return true;
                """, args=(i,), retries=6, delay=0.2)

                self.log(f"Selecting IN time for index {i}: {shift['in'][0]}:{shift['in'][1]}")
                in_ok = pick_time(driver, i, 0, shift["in"][0], shift["in"][1])
                if not in_ok:
                    raise Exception(f"Unable to set IN time for day index {i}")
                self.log(f"IN time set for index {i}.")

                self.log(f"Selecting OUT time for index {i}: {shift['out'][0]}:{shift['out'][1]}")
                out_ok = pick_time(driver, i, 1, shift["out"][0], shift["out"][1])
                if not out_ok:
                    raise Exception(f"Unable to set OUT time for day index {i}")
                self.log(f"OUT time set for index {i}.")

                self.log(f"Selecting shift name for index {i}: {selected_shift_name}")
                shift_ok = pick_shift(driver, i, selected_shift_name)
                if not shift_ok:
                    raise Exception(f"Unable to select shift for day index {i}")
                self.log(f"Shift name set for index {i}.")

            except Exception as e:
                self.error(str(e))

            entries_filled += 1
            self.log(f"Completed entry {entries_filled} in this batch.")
            current_date += timedelta(days=1)

        self.log(f"Batch completed. Entries filled: {entries_filled}.")
        return current_date, entries_filled

    # ================= AUTOMATION =================
    def run(self):

        global stop_execution
        stop_execution = False
        self.log("Run started.")

        start_date = datetime.strptime(self.start_date.get(), "%d-%m-%Y")
        end_date = datetime.strptime(self.end_date.get(), "%d-%m-%Y")
        self.log(f"Date range selected: {start_date.strftime('%d-%m-%Y')} to {end_date.strftime('%d-%m-%Y')}")

        holidays = {
            datetime.strptime(d, "%d-%m-%Y").date()
            for d in self.h_list.get(0, tk.END)
        }
        self.log(f"Loaded {len(holidays)} holiday/leave date(s).")

        shift_url = self.url.get()
        self.log(f"Target shift form URL: {shift_url}")

        shift = {
            "in": (self.in_h.get(), self.in_m.get()),
            "out": (self.out_h.get(), self.out_m.get()),
            "name": self.shift_name.get(),
            "type": self.shift_type.get()
        }

        selected_shift_name = shift["name"]

        in_minutes = int(shift["in"][0]) * 60 + int(shift["in"][1])
        out_minutes = int(shift["out"][0]) * 60 + int(shift["out"][1])
        is_cross_midnight = shift["type"].lower() == "night" and out_minutes <= in_minutes
        self.log(
            f"Shift details: type={shift['type']}, name={shift['name']}, "
            f"in={shift['in'][0]}:{shift['in'][1]}, out={shift['out'][0]}:{shift['out'][1]}, "
            f"cross_midnight={is_cross_midnight}"
        )

        try:
            # Reuse one browser session for all starts until app/browser is closed.
            if self.driver is not None:
                self.log("Checking existing browser session...")
                try:
                    _ = self.driver.current_url
                    self.log("Existing browser session is active.")
                except (WebDriverException, InvalidSessionIdException):
                    self.log("Existing browser session is not valid. Creating a new one.")
                    self.driver = None
                    self.login_completed = False

            if self.driver is None:
                self.log("Launching Chrome browser...")
                self.driver = create_chrome_driver()
                self.driver.maximize_window()
                self.log("Chrome launched and window maximized.")

            driver = self.driver

            if not self.login_completed:
                self.log("Opening login page...")
                driver.get("https://tavant-peoplehub.darwinbox.com")

                already_logged_in = False
                try:
                    already_logged_in = driver.execute_script("""
                        const t = (document.body && document.body.innerText || '').toLowerCase();
                        return !(t.includes('sign in') || t.includes('login'));
                    """)
                except Exception:
                    already_logged_in = False

                if already_logged_in:
                    self.log("Existing login session detected from saved Chrome profile.")
                    self.login_completed = True
                else:
                    self.log("Waiting for manual login confirmation...")
                    wait_after_login(self.root)
                    self.login_completed = True
                    self.log("Manual login confirmed.")
            else:
                self.log("Login already completed in this browser session.")

            self.log("Navigating to shift form and handling post-login state...")
            handle_post_login(driver, shift_url)
            self.log("Shift form navigation completed.")
        except Exception as e:
            self.error(f"Failed to launch/reuse Chrome session: {e}")
            self.error("Install Google Chrome and keep chromedriver.exe next to the EXE, or ensure internet access for Selenium Manager.")
            self.driver = None
            self.login_completed = False
            self.is_running = False
            return

        current_date = start_date
        aborted = False
        processed_any_batch = False
        self.log("Entering batch processing loop.")

        while current_date <= end_date and not stop_execution:
            self.log(f"Processing form batch starting from {current_date.strftime('%d-%m-%Y')}.")
            current_date, entries_filled = self.fill_form_batch(
                driver=driver,
                start_date=current_date,
                end_date=end_date,
                holidays=holidays,
                shift=shift,
                selected_shift_name=selected_shift_name,
                is_cross_midnight=is_cross_midnight,
                max_entries=18
            )
            processed_any_batch = True

            if stop_execution or current_date > end_date:
                break

            if entries_filled <= 0:
                self.error("No entries were filled in this form. Stopping to avoid loop.")
                self.log("Stopping run because no entries were filled in the current batch.")
                aborted = True
                break

            try:
                known_handles = list(driver.window_handles)
                self.log(f"Captured {len(known_handles)} existing browser tab/window handle(s).")
            except Exception:
                known_handles = []
                self.log("Unable to capture existing tab/window handles. Will still attempt switch.")

            if not self.wait_for_next_form():
                break

            self.log("Attempting to switch to next form tab/window...")
            switched = switch_to_next_form_context(driver, known_handles)
            if switched:
                try:
                    self.log(f"Using browser tab: {driver.current_url}")
                except Exception:
                    self.log("Switched browser tab/window for next form.")
            else:
                self.error("Could not switch to next form tab/window. Open it and try Continue Next Form again.")
                aborted = True
                break

        if stop_execution:
            self.log("⏹ Flow stopped")
            self.is_running = False
            return

        if aborted or (not processed_any_batch) or current_date <= end_date:
            self.log("Flow ended before completion. Resolve the above error and run again.")
            self.is_running = False
            return

        self.log("✅ DONE")
        self.root.after(0, lambda: messagebox.showinfo("Flow Completed", "Shift entry flow is done."))
        self.is_running = False

# ================= RUN =================
App()
