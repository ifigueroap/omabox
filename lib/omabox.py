#!/usr/bin/env python3
"""Omabox config, window class, and Omarchy integration.

The bash CLI in bin/omabox is what users run. This module owns TOML,
the Chromium window class, generated Hyprland Lua, and the optional
Omarchy menu entry so those pieces can be tested without a desktop.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tomllib
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PRESETS_FILE = ROOT / "presets" / "services.toml"
DEFAULT_UNREAD = r"^\((\d+)\)"
SERVICE_FIELDS = ("id", "name", "url", "icon", "profile", "key", "unread")
FLAG_FIELDS = ("sound", "badges")
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
KEY_RE = re.compile(r"^[1-9]$")
BEGIN = "-- BEGIN omabox"
END = "-- END omabox"
MENU_BEGIN = "// BEGIN omabox"
MENU_END = "// END omabox"

HYPR_BLOCK = """-- BEGIN omabox
-- Managed by `omabox setup` / `omabox uninstall`. Personal binds stay above.
require("hypr.omabox")
-- END omabox
"""

MENU_BLOCK = """  // BEGIN omabox
  "omabox": {"icon":"󰖟","label":"Omabox","action":"omabox toggle"},
  "omabox.dashboard": {"icon":"󰒓","label":"Omabox services","action":"omabox dashboard"},
  // END omabox"""


def home() -> Path:
    return Path(os.environ.get("HOME") or str(Path.home()))


def config_dir() -> Path:
    return home() / ".config" / "omabox"


def config_file() -> Path:
    return config_dir() / "services.toml"


DOCK_MODES = ("always", "special-only")
DOCK_EDGES = ("left", "right", "top", "bottom")
_SETTING_ORDER = ("dock", "edge", "pinned", "dnd")
_DND_KEYS = ("dnd", "do_not_disturb")


def settings_file() -> Path:
    return config_dir() / "config.toml"


def _read_settings_raw() -> dict:
    path = settings_file()
    if not path.is_file():
        return {}
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _read_dnd(source: dict) -> bool:
    """Global Do not disturb. `dnd` wins when both names are set."""
    if isinstance(source.get("dnd"), bool):
        return bool(source["dnd"])
    if isinstance(source.get("do_not_disturb"), bool):
        return bool(source["do_not_disturb"])
    return False


def normalized_settings(raw: dict | None = None) -> dict[str, object]:
    source = _read_settings_raw() if raw is None else raw
    dock = source.get("dock")
    edge = source.get("edge")
    pinned = source.get("pinned")
    return {
        "dock": dock if isinstance(dock, str) and dock in DOCK_MODES else "always",
        "edge": edge if isinstance(edge, str) and edge in DOCK_EDGES else "right",
        "pinned": pinned if isinstance(pinned, bool) else False,
        "dnd": _read_dnd(source),
    }


def load_dock_mode() -> str:
    return str(normalized_settings()["dock"])


def _toml_scalar(value: object) -> str | None:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    if isinstance(value, int):
        return str(value)
    return None


def _toml_key(key: str) -> bool:
    return re.fullmatch(r"[A-Za-z_][A-Za-z0-9_-]*", key) is not None


def save_settings(updates: dict) -> None:
    raw = _read_settings_raw()
    current = normalized_settings(raw)
    current.update(updates)
    raw["dock"] = current["dock"]
    raw["edge"] = current["edge"]
    raw["pinned"] = current["pinned"]
    raw["dnd"] = bool(current["dnd"])
    if "do_not_disturb" in raw:
        raw["do_not_disturb"] = raw["dnd"]
    lines: list[str] = []
    written: set[str] = set()
    for key in _SETTING_ORDER:
        rendered = _toml_scalar(raw.get(key))
        if rendered is None:
            continue
        lines.append(f"{key} = {rendered}")
        written.add(key)
    for key, value in raw.items():
        if not isinstance(key, str) or key in written or not _toml_key(key):
            continue
        rendered = _toml_scalar(value)
        if rendered is None:
            continue
        lines.append(f"{key} = {rendered}")
    path = settings_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def cmd_config(key: str = "", value: str = "") -> None:
    settings = normalized_settings()
    if not key:
        pinned = "true" if settings["pinned"] else "false"
        dnd = "true" if settings["dnd"] else "false"
        print(f"dock={settings['dock']}")
        print(f"edge={settings['edge']}")
        print(f"pinned={pinned}")
        print(f"dnd={dnd}")
        return
    if key == "dock":
        if not value:
            print(settings["dock"])
            return
        if value not in DOCK_MODES:
            die("dock must be 'always' or 'special-only'")
        save_settings({"dock": value})
        print(value)
        return
    if key == "edge":
        if not value:
            print(settings["edge"])
            return
        if value not in DOCK_EDGES:
            die("edge must be 'left', 'right', 'top', or 'bottom'")
        save_settings({"edge": value})
        print(value)
        return
    if key == "pinned":
        if not value:
            print("true" if settings["pinned"] else "false")
            return
        if value not in ("true", "false"):
            die("pinned must be 'true' or 'false'")
        save_settings({"pinned": value == "true"})
        print(value)
        return
    if key in _DND_KEYS:
        if not value:
            print("true" if settings["dnd"] else "false")
            return
        if value not in ("true", "false"):
            die("dnd must be 'true' or 'false'")
        save_settings({"dnd": value == "true"})
        apply_quiet()
        print(value)
        return
    die(f"unknown setting '{key}'")


def data_dir() -> Path:
    return home() / ".local" / "share" / "omabox"


def chromium_dir() -> Path:
    return data_dir() / "chromium"


def icon_cache_dir() -> Path:
    return data_dir() / "icons"


def hypr_dir() -> Path:
    # Omarchy's Lua package.path is $HOME/.config/?.lua (default/hypr/bootstrap.lua),
    # not $XDG_CONFIG_HOME.
    return home() / ".config" / "hypr"


def die(message: str, code: int = 1) -> None:
    print(f"omabox: {message}", file=sys.stderr)
    raise SystemExit(code)


def parse_http_url(url: str) -> tuple[str, str] | None:
    """Match bin/omarchy-webapp-window-class, restricted to http(s)."""
    raw = url.strip()
    match = re.match(r"^([a-zA-Z][a-zA-Z0-9+.-]*)://([^?#]*)", raw)
    if not match or match.group(1).lower() not in ("http", "https"):
        return None
    address = match.group(2)
    slash = address.find("/")
    if slash == -1:
        host, path = address, "/"
    else:
        host, path = address[:slash], address[slash:] or "/"
    if "@" in host:
        host = host.rsplit("@", 1)[1]
    if host.startswith("[") and "]" in host:
        host = host[: host.index("]") + 1]
    else:
        host = host.split(":", 1)[0]
    host = host.lower()
    if not host:
        return None
    return host, path


def window_class(url: str, profile: str) -> str:
    """Chromium Wayland app id for --app and --profile-directory.

    web_app::GenerateApplicationNameFromURL is host + "_" + path.
    GetShortcutFileName prefixes "chrome-" and the profile basename, then
    replaces illegal path characters and spaces with "_". For an https URL
    whose path is "/", that is chrome-<host>__-<profile>.
    """
    parsed = parse_http_url(url)
    name = profile or ""
    if not parsed or not name:
        return ""
    host, path = parsed
    return f"chrome-{host}_{path}-{name}".replace("/", "_").replace(" ", "_")


def class_regex(class_name: str) -> str:
    if not class_name:
        return ""
    return "^" + re.escape(class_name) + "$"


VISIBLE_WORKSPACE = "special:omabox"
HIDDEN_WORKSPACE = "special:omabox-hidden"
ADDRESS_RE = re.compile(r"^0x[0-9a-fA-F]+$")


def lua_quote(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def reported_class(client: dict) -> str:
    """Hyprland class, case-sensitive. Empty class falls back to initialClass."""
    value = client.get("class")
    if isinstance(value, str) and value:
        return value
    for key in ("initialClass", "initial_class"):
        value = client.get(key)
        if isinstance(value, str) and value:
            return value
    return ""


def client_address(client: dict) -> str:
    address = client.get("address") or ""
    if not isinstance(address, str):
        return ""
    return address if ADDRESS_RE.fullmatch(address) else ""


def workspace_name(client: dict) -> str:
    workspace = client.get("workspace")
    if isinstance(workspace, str):
        return workspace
    if isinstance(workspace, dict):
        name = workspace.get("name") or ""
        return name if isinstance(name, str) else ""
    return ""


def on_workspace(name: str, workspace: str) -> bool:
    bare = workspace.removeprefix("special:")
    return name == workspace or name == bare or name == f"special:{bare}"


def expr_move(workspace: str, selector: str) -> str:
    return (
        "hl.dsp.window.move({ workspace = "
        + lua_quote(workspace)
        + ", follow = false, window = "
        + lua_quote(selector)
        + " })"
    )


def expr_close(address: str) -> str:
    return "hl.dsp.window.close({ window = " + lua_quote(f"address:{address}") + " })"


def expr_focus(class_name: str) -> str:
    return "hl.dsp.focus({ window = " + lua_quote(f"class:{class_name}") + " })"


def build_focus_plan(clients: list, target_class: str, managed_classes: list[str]) -> dict:
    """One visible Omabox window: the target class on special:omabox.

    Other managed windows move to special:omabox-hidden. Extra windows of the
    target class are closed so a service keeps a single window. Class match
    is case-sensitive (WhatsApp is not Whatsapp).
    """
    managed = set(managed_classes)
    managed.add(target_class)
    targets: list[dict] = []
    others: list[dict] = []
    for client in clients:
        if not isinstance(client, dict):
            continue
        klass = reported_class(client)
        if klass == target_class:
            targets.append(client)
        elif klass in managed:
            others.append(client)
    if not targets:
        return {"found": False, "dispatch": [], "focus": "", "warnings": []}

    def rank(client: dict) -> tuple[int, int]:
        visible = 0 if on_workspace(workspace_name(client), VISIBLE_WORKSPACE) else 1
        return (visible, 0)

    keeper = sorted(enumerate(targets), key=lambda item: (rank(item[1]), item[0]))[0][1]
    keeper_address = client_address(keeper)
    dispatch: list[str] = []
    warnings: list[str] = []
    for client in others:
        if on_workspace(workspace_name(client), HIDDEN_WORKSPACE):
            continue
        address = client_address(client)
        if not address:
            warnings.append(f"no address for {reported_class(client)}; left it where it is")
            continue
        dispatch.append(expr_move(HIDDEN_WORKSPACE, f"address:{address}"))
    for client in targets:
        if client is keeper:
            continue
        address = client_address(client)
        if not address:
            warnings.append(f"duplicate {target_class} has no address; left it open")
            continue
        dispatch.append(expr_close(address))
    if keeper_address and not on_workspace(workspace_name(keeper), VISIBLE_WORKSPACE):
        dispatch.append(expr_move(VISIBLE_WORKSPACE, f"address:{keeper_address}"))
    elif not keeper_address:
        dispatch.append(expr_move(VISIBLE_WORKSPACE, f"class:{target_class}"))
    return {
        "found": True,
        "dispatch": dispatch,
        "focus": expr_focus(target_class),
        "warnings": warnings,
    }


def chromium_pids(user_data: str, proc_root: Path | None = None) -> list[str]:
    """PIDs whose cmdline contains this Chromium --user-data-dir.

    Omabox profiles share one user-data-dir, so these are every Omabox
    browser process, not a single profile. proc_root defaults to /proc and
    can be pointed at a fixture with OMABOX_PROC_ROOT.
    """
    needle = (user_data or "").encode()
    if not needle:
        return []
    root = proc_root
    if root is None:
        override = os.environ.get("OMABOX_PROC_ROOT")
        root = Path(override) if override else Path("/proc")
    if not root.is_dir():
        return []
    found: list[str] = []
    for entry in root.iterdir():
        if not entry.name.isdigit():
            continue
        try:
            raw = (entry / "cmdline").read_bytes()
        except OSError:
            continue
        argv = [part for part in raw.split(b"\0") if part]
        # Match the executable, not the --user-data-dir path (that path
        # itself contains "chromium").
        exe = argv[0].rsplit(b"/", 1)[-1].lower() if argv else b""
        if needle not in raw or b"chrom" not in exe:
            continue
        found.append(entry.name)
    return sorted(found, key=int)


def normalize_url(url: str, allow_empty: bool = False) -> str:
    text = (url or "").strip()
    if not text:
        if allow_empty:
            return ""
        die("URL is required")
    if re.search(r"\s", text):
        die("URL must not contain whitespace")
    if not re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", text):
        text = "https://" + text
    if not re.match(r"^https?://", text, re.IGNORECASE):
        die("URL must be http or https")
    if parse_http_url(text) is None:
        die(f"URL is not usable: {text}")
    return text


def check_unread(pattern: str) -> str:
    try:
        re.compile(pattern)
    except re.error as exc:
        die(f"unread regex is invalid: {exc}")
    return pattern


def check_profile(profile: str) -> str:
    text = profile.strip()
    if not text or text in (".", "..") or "/" in text or "\\" in text or "\x00" in text:
        die("profile must be a single directory name without slashes")
    if len(text) > 64:
        die("profile is too long")
    return text


def check_id(value: str) -> str:
    if not value or not ID_RE.match(value) or ".." in value:
        die(f"invalid service id '{value}'")
    return value


def check_key(value: str) -> str:
    if value and not KEY_RE.match(value):
        die("key must be empty or a digit 1-9")
    return value


def toml_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def service_flag(data: dict, field: str, default: bool = True) -> bool:
    """Missing sound/badges stay enabled so an old services.toml is unchanged in meaning."""
    if field not in data:
        return default
    value = data[field]
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in ("true", "1", "on", "yes"):
            return True
        if lowered in ("false", "0", "off", "no"):
            return False
    return default


def extra_fields(data: dict) -> dict:
    extra: dict = {}
    for key, value in data.items():
        if not isinstance(key, str) or key in SERVICE_FIELDS or key in FLAG_FIELDS:
            continue
        if not _toml_key(key) or _toml_scalar(value) is None:
            continue
        extra[key] = value
    return extra


def render_service(service: dict) -> str:
    lines = ["[[service]]"]
    for field in SERVICE_FIELDS:
        lines.append(f"{field} = {toml_string(str(service.get(field, '')))}")
    lines.append(f"sound = {'true' if service.get('sound', True) else 'false'}")
    lines.append(f"badges = {'true' if service.get('badges', True) else 'false'}")
    extra = service.get("_extra") or {}
    if isinstance(extra, dict):
        for key, value in extra.items():
            if not isinstance(key, str) or key in SERVICE_FIELDS or key in FLAG_FIELDS or not _toml_key(key):
                continue
            rendered = _toml_scalar(value)
            if rendered is None:
                continue
            lines.append(f"{key} = {rendered}")
    lines.append("")
    return "\n".join(lines)


def split_document(text: str) -> tuple[str, list[str]]:
    lines = text.splitlines(keepends=True)
    preamble: list[str] = []
    blocks: list[list[str]] = []
    current: list[str] | None = None
    for line in lines:
        if line.strip() == "[[service]]":
            if current is not None:
                blocks.append(current)
            current = [line]
        elif current is None:
            preamble.append(line)
        else:
            current.append(line)
    if current is not None:
        blocks.append(current)
    return "".join(preamble), ["".join(block) for block in blocks]


def parse_block(block: str) -> dict:
    data = tomllib.loads(block)
    # A block is one TOML array-of-tables entry: [[service]] fields live under
    # data["service"][0], not at the document root.
    rows = data.get("service") if isinstance(data, dict) else None
    if not isinstance(rows, list) or len(rows) != 1 or not isinstance(rows[0], dict) or "id" not in rows[0]:
        die("a [[service]] block is missing id")
    return normalize_service(rows[0])


def normalize_service(data: dict) -> dict:
    service = {field: "" if data.get(field) is None else str(data.get(field)) for field in SERVICE_FIELDS}
    service["id"] = check_id(service["id"].strip())
    service["name"] = service["name"].strip() or service["id"]
    service["url"] = normalize_url(service["url"], allow_empty=True) if service["url"].strip() else ""
    service["profile"] = check_profile(service["profile"] or service["name"])
    service["key"] = check_key(service["key"].strip())
    service["unread"] = check_unread(service["unread"] if service["unread"] != "" else DEFAULT_UNREAD)
    service["icon"] = service["icon"].strip()
    service["sound"] = service_flag(data, "sound")
    service["badges"] = service_flag(data, "badges")
    service["_extra"] = extra_fields(data)
    return service


def load_services(path: Path | None = None) -> list[dict]:
    target = path or config_file()
    if not target.is_file():
        return []
    _preamble, blocks = split_document(target.read_text(encoding="utf-8"))
    services = []
    seen = set()
    for block in blocks:
        service = parse_block(block)
        if service["id"] in seen:
            die(f"duplicate service id '{service['id']}' in {target}")
        seen.add(service["id"])
        services.append(service)
    return services


def write_services(services: list[dict], preamble: str | None = None, path: Path | None = None) -> None:
    target = path or config_file()
    if preamble is None:
        if target.is_file():
            preamble, _blocks = split_document(target.read_text(encoding="utf-8"))
        else:
            preamble = (
                "# Omabox services. One Chromium profile per [[service]].\n"
                "# `omabox add` / `omabox remove` rewrite service blocks and keep this header.\n\n"
            )
    if preamble and not preamble.endswith("\n"):
        preamble += "\n"
    body = "".join(render_service(service) for service in services)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(preamble + body, encoding="utf-8")


def load_presets() -> list[dict]:
    _preamble, blocks = split_document(PRESETS_FILE.read_text(encoding="utf-8"))
    return [parse_block(block) for block in blocks]


def bundled_icon(service_id: str) -> Path | None:
    candidate = ROOT / "icons" / f"{service_id}.svg"
    return candidate if candidate.is_file() else None


def cached_icon(service_id: str) -> Path | None:
    for suffix in (".png", ".svg", ".webp", ".ico"):
        candidate = icon_cache_dir() / f"{service_id}{suffix}"
        if candidate.is_file() and candidate.stat().st_size > 0:
            return candidate
    return None


def resolve_icon(service: dict) -> str:
    raw = service.get("icon") or ""
    if raw:
        path = Path(raw)
        if not path.is_absolute():
            path = config_dir() / raw
        if path.is_file():
            return str(path)
    bundled = bundled_icon(service["id"])
    if bundled:
        return str(bundled)
    cached = cached_icon(service["id"])
    return str(cached) if cached else ""


def public_service(service: dict, dnd: bool | None = None) -> dict:
    if dnd is None:
        dnd = bool(normalized_settings()["dnd"])
    sound = bool(service.get("sound", True))
    badges = bool(service.get("badges", True))
    cls = window_class(service["url"], service["profile"]) if service["url"] else ""
    return {
        "id": service["id"],
        "name": service["name"],
        "url": service["url"],
        "icon": resolve_icon(service),
        "profile": service["profile"],
        "key": service["key"],
        "unread": service["unread"],
        "class": cls,
        "classRegex": class_regex(cls),
        "ready": bool(service["url"]),
        "sound": sound,
        "badges": badges,
        "soundEffective": sound and not dnd,
        "badgesEffective": badges and not dnd,
    }


def slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug or "service"


def cmd_init(force: bool = False, announce: bool = True) -> None:
    target = config_file()
    if target.is_file() and not force:
        if announce:
            print(target)
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(PRESETS_FILE, target)
    if announce:
        print(target)


def cmd_list(as_json: bool) -> None:
    settings = normalized_settings()
    dnd = bool(settings["dnd"])
    services = [public_service(service, dnd=dnd) for service in load_services()]
    if as_json:
        json.dump(
            {
                "services": services,
                "dock": settings["dock"],
                "edge": settings["edge"],
                "pinned": settings["pinned"],
                "dnd": dnd,
            },
            sys.stdout,
        )
        sys.stdout.write("\n")
        return
    if not services:
        print(f"No services. Create {config_file()} with `omabox init`.")
        return
    for service in services:
        key = service["key"] or "-"
        url = service["url"] or "(set a URL)"
        print(f"{key:>2}  {service['id']:<16} {service['name']:<16} {url}")


def find_service(services: list[dict], ident: str) -> dict | None:
    for service in services:
        if service["id"] == ident:
            return service
    return None


def find_by_key(services: list[dict], key: str) -> dict | None:
    for service in services:
        if service["key"] == key:
            return service
    return None


def cmd_get(ident: str) -> None:
    services = load_services()
    if re.fullmatch(r"[1-9]", ident):
        found = find_by_key(services, ident) or find_service(services, ident)
    else:
        found = find_service(services, ident)
    if not found:
        die(f"no service '{ident}'")
    json.dump(public_service(found), sys.stdout)
    sys.stdout.write("\n")


def cmd_class(url: str, profile: str) -> None:
    print(window_class(url, profile))


def cmd_add(args: argparse.Namespace) -> None:
    if not config_file().is_file():
        cmd_init(announce=False)
    services = load_services()
    preset = None
    if args.preset:
        preset = find_service(load_presets(), args.preset)
        if not preset:
            die(f"unknown preset '{args.preset}'")
    overridden = any((
        args.id,
        args.name,
        args.url is not None,
        args.icon is not None,
        args.profile,
        args.key is not None,
        args.unread is not None,
    ))
    if preset and not overridden:
        incoming = dict(preset)
    else:
        base = dict(preset) if preset else {
            "id": "",
            "name": "",
            "url": "",
            "icon": "",
            "profile": "",
            "key": "",
            "unread": DEFAULT_UNREAD,
        }
        if args.id:
            base["id"] = args.id
        if args.name:
            base["name"] = args.name
        if args.url is not None:
            base["url"] = args.url
        if args.icon is not None:
            base["icon"] = args.icon
        if args.profile:
            base["profile"] = args.profile
        if args.key is not None:
            base["key"] = args.key
        if args.unread is not None:
            base["unread"] = args.unread
        if not base["id"]:
            base["id"] = slugify(base["name"] or base["profile"] or "service")
        if not base["name"]:
            base["name"] = base["id"]
        if not base["profile"]:
            base["profile"] = base["name"]
        incoming = normalize_service(base)
    incoming = normalize_service(incoming)
    existing = find_service(services, incoming["id"])
    if existing:
        # `omabox add --update` rewrites the block. Keep mute flags and any
        # extra flat keys so a URL change does not turn sound back on.
        incoming["sound"] = existing["sound"]
        incoming["badges"] = existing["badges"]
        incoming["_extra"] = dict(existing.get("_extra") or {})
    if existing and not args.update:
        if not overridden:
            json.dump(public_service(existing), sys.stdout)
            sys.stdout.write("\n")
            return
        die(f"service '{incoming['id']}' already exists (pass --update to replace it)")
    if incoming["key"]:
        other = find_by_key(services, incoming["key"])
        if other and other["id"] != incoming["id"]:
            print(f"omabox: key {incoming['key']} is already used by {other['id']}; SUPER+ALT+{incoming['key']} focuses that one", file=sys.stderr)
    replaced = False
    updated = []
    for service in services:
        if service["id"] == incoming["id"]:
            updated.append(incoming)
            replaced = True
        else:
            updated.append(service)
    if not replaced:
        updated.append(incoming)
    write_services(updated)
    refresh_rules_if_installed()
    json.dump(public_service(incoming), sys.stdout)
    sys.stdout.write("\n")


def cmd_remove(ident: str) -> None:
    services = load_services()
    if not find_service(services, ident):
        die(f"no service '{ident}'")
    write_services([service for service in services if service["id"] != ident])
    refresh_rules_if_installed()
    print(f"removed {ident}")


def render_lua(services: list[dict] | None = None) -> str:
    rows = services if services is not None else load_services()
    lines = [
        "-- Generated by omabox. `omabox setup`, `omabox add`, and `omabox remove` rewrite this file.",
        "-- Chromium Wayland app id (chrome/browser/web_applications/web_app_helpers.cc",
        "-- GenerateApplicationNameFromURL + os_integration/web_app_shortcut_linux.cc GetShortcutFileName):",
        "--   chrome-<host>_<path>-<profile>, then '/' and spaces become '_'.",
        "-- Omarchy's bin/omarchy-webapp-window-class is the profile=Default case.",
        "if type(o) ~= \"table\" or type(o.rebind) ~= \"function\" or type(o.window) ~= \"function\" then",
        "  return",
        "end",
        "",
        "-- Super+O is \"Pop window out\" (default/hypr/bindings/tiling.lua).",
        "-- Super+Shift+O is Obsidian while preinstalled binds are enabled",
        "-- (default/hypr/bindings/applications.lua). o.rebind replaces Obsidian.",
        "-- `omabox setup`, `omabox add`, and `omabox remove` rewrite this file.",
        "-- Then: hyprctl reload && hyprctl configerrors",
        'o.rebind("SUPER + SHIFT + O", "Omabox", "omabox toggle")',
        "for service = 1, 9 do",
        "  o.bind(",
        '    "SUPER + ALT + code:" .. tostring(service + 9),',
        '    "Omabox service " .. service,',
        '    "omabox focus " .. service',
        "  )",
        "end",
        "",
    ]
    for service in rows:
        cls = window_class(service["url"], service["profile"]) if service["url"] else ""
        if not cls:
            continue
        pattern = class_regex(cls).replace("\\", "\\\\").replace('"', '\\"')
        # Wiki window-rule effect `workspace` may be suffixed with " silent".
        # o.window() forwards that table to hl.window_rule (default/hypr/helpers.lua).
        lines.append(f'o.window("{pattern}", {{ workspace = "special:omabox silent" }})')
    lines.append("")
    return "\n".join(lines)


def rules_installed() -> bool:
    lua = hypr_dir() / "omabox.lua"
    bindings = hypr_dir() / "bindings.lua"
    if lua.is_file():
        return True
    if bindings.is_file() and BEGIN in bindings.read_text(encoding="utf-8"):
        return True
    return False


def refresh_rules_if_installed() -> None:
    if rules_installed():
        write_rules()


def write_rules() -> Path:
    target = hypr_dir() / "omabox.lua"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(render_lua(), encoding="utf-8")
    return target


def ensure_marked_block(path: Path, block: str, begin: str, end: str, created: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text(created, encoding="utf-8")
        return
    text = path.read_text(encoding="utf-8")
    pattern = re.compile(re.escape(begin) + r".*?" + re.escape(end) + r"\n?", re.DOTALL)
    if pattern.search(text):
        text = pattern.sub(block.rstrip() + "\n", text, count=1)
    else:
        if text and not text.endswith("\n"):
            text += "\n"
        text += "\n" + block.rstrip() + "\n"
    path.write_text(text, encoding="utf-8")


def remove_marked_block(path: Path, begin: str, end: str) -> None:
    if not path.is_file():
        return
    text = path.read_text(encoding="utf-8")
    pattern = re.compile(r"\n?" + re.escape(begin) + r".*?" + re.escape(end) + r"\n?", re.DOTALL)
    updated = pattern.sub("\n", text, count=1)
    path.write_text(updated, encoding="utf-8")


def bin_link() -> Path:
    return home() / ".local" / "bin" / "omabox"


def install_link() -> None:
    link = bin_link()
    link.parent.mkdir(parents=True, exist_ok=True)
    target = (ROOT / "bin" / "omabox").resolve()
    if link.is_symlink() and link.resolve() == target:
        return
    if link.exists() or link.is_symlink():
        print(f"omabox: left {link} alone; it does not point at {target}", file=sys.stderr)
        return
    link.symlink_to(target)


def remove_link() -> None:
    link = bin_link()
    target = (ROOT / "bin" / "omabox").resolve()
    if link.is_symlink() and link.resolve() == target:
        link.unlink()


def menu_file() -> Path:
    return home() / ".config" / "omarchy" / "extensions" / "omarchy-menu.jsonc"


def install_menu() -> None:
    path = menu_file()
    created = "{\n" + MENU_BLOCK + "\n}\n"
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(created, encoding="utf-8")
        return
    text = path.read_text(encoding="utf-8")
    pattern = re.compile(re.escape(MENU_BEGIN) + r".*?" + re.escape(MENU_END) + r"\n?", re.DOTALL)
    if pattern.search(text):
        text = pattern.sub(MENU_BLOCK + "\n", text, count=1)
        path.write_text(text, encoding="utf-8")
        return
    # Insert before the final closing brace so the file stays one JSON object.
    stripped = text.rstrip()
    idx = stripped.rfind("}")
    if idx == -1:
        path.write_text(created, encoding="utf-8")
        return
    prefix = stripped[:idx].rstrip()
    if prefix.endswith("{"):
        inserted = prefix + "\n" + MENU_BLOCK + "\n}\n"
    else:
        if not prefix.endswith(","):
            prefix += ","
        inserted = prefix + "\n" + MENU_BLOCK + "\n}\n"
    path.write_text(inserted, encoding="utf-8")


def remove_menu() -> None:
    path = menu_file()
    if not path.is_file():
        return
    text = path.read_text(encoding="utf-8")
    pattern = re.compile(r"\n?[ \t]*" + re.escape(MENU_BEGIN) + r".*?" + re.escape(MENU_END) + r",?\n?", re.DOTALL)
    path.write_text(pattern.sub("\n", text, count=1), encoding="utf-8")


BINDINGS_CREATED = """-- Personal keybindings. Omarchy loads this from hyprland.lua.
-- Omabox keeps its require inside the marked block below.

"""


def cmd_setup(menu: bool) -> None:
    cmd_init(announce=False)
    rules = write_rules()
    ensure_marked_block(hypr_dir() / "bindings.lua", HYPR_BLOCK, BEGIN, END, BINDINGS_CREATED + HYPR_BLOCK)
    install_link()
    if menu:
        install_menu()
    print(f"config: {config_file()}")
    print(f"rules:  {rules}")
    print(f"binds:  {hypr_dir() / 'bindings.lua'}")
    if menu:
        print(f"menu:   {menu_file()}")
    print("Reload Hyprland if it is already running (`hyprctl reload`).")
    print("Enable the shell plugin with: omarchy plugin enable omabox")


def cmd_uninstall(purge: bool) -> None:
    remove_marked_block(hypr_dir() / "bindings.lua", BEGIN, END)
    lua = hypr_dir() / "omabox.lua"
    if lua.is_file():
        lua.unlink()
    remove_menu()
    remove_link()
    if purge:
        shutil.rmtree(config_dir(), ignore_errors=True)
        shutil.rmtree(data_dir(), ignore_errors=True)
    print("Removed Omabox Hyprland binds, window rules, and menu rows.")
    if not purge:
        print(f"Kept {config_file()} and {data_dir()}. Pass --purge to delete them.")


def managed_classes() -> list[str]:
    classes: list[str] = []
    for service in load_services():
        if not service["url"]:
            continue
        klass = window_class(service["url"], service["profile"])
        if klass and klass not in classes:
            classes.append(klass)
    return classes


def cmd_focus_plan(target_class: str) -> None:
    raw = sys.stdin.read()
    if not raw.strip():
        print("omabox: hyprctl clients produced no output", file=sys.stderr)
        raise SystemExit(2)
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(f"omabox: could not parse hyprctl clients: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
    if isinstance(parsed, dict):
        parsed = parsed.get("clients") or parsed.get("windows") or []
    if not isinstance(parsed, list):
        print("omabox: hyprctl clients was not a list", file=sys.stderr)
        raise SystemExit(2)
    plan = build_focus_plan(parsed, target_class, managed_classes())
    json.dump(plan, sys.stdout)
    sys.stdout.write("\n")
    raise SystemExit(0 if plan["found"] else 1)


def cmd_chromium_pids(user_data: str) -> None:
    for pid in chromium_pids(user_data):
        print(pid)


def cmd_launch_spec(ident: str) -> None:
    services = load_services()
    if re.fullmatch(r"[1-9]", ident):
        found = find_by_key(services, ident) or find_service(services, ident)
    else:
        found = find_service(services, ident)
    if not found:
        die(f"no service '{ident}'")
    if not found["url"]:
        die(f"{found['name']} has no URL. Set one with: omabox add {found['id']} --url https://... --update")
    public = public_service(found)
    user_data = str(chromium_dir())
    args = [
        f"--user-data-dir={user_data}",
        f"--profile-directory={found['profile']}",
        f"--app={found['url']}",
        "--no-first-run",
        "--no-default-browser-check",
    ]
    # Profiles share one Chromium process, so --mute-audio would silence every
    # service. muteAudio tells the launcher to apply the per-stream policy
    # after the window exists.
    public["userDataDir"] = user_data
    public["args"] = args
    public["muteAudio"] = not bool(public["soundEffective"])
    json.dump(public, sys.stdout)
    sys.stdout.write("\n")


def cmd_service(ident: str, field: str, value: str) -> None:
    if field not in FLAG_FIELDS:
        die("service field must be 'sound' or 'badges'")
    services = load_services()
    if re.fullmatch(r"[1-9]", ident):
        found = find_by_key(services, ident) or find_service(services, ident)
    else:
        found = find_service(services, ident)
    if not found:
        die(f"no service '{ident}'")
    if not value:
        print("true" if found[field] else "false")
        return
    if value not in ("true", "false"):
        die(f"{field} must be 'true' or 'false'")
    found[field] = value == "true"
    write_services(services)
    apply_quiet()
    print(value)


def best_service_match(node: dict, services: list[dict]) -> dict | None:
    """Longest service name, profile, or id contained in the stream's media name."""
    media = str(node.get("media_name") or "").casefold()
    if not media:
        return None
    best: dict | None = None
    best_len = 0
    for service in services:
        for key in ("name", "profile", "id"):
            text = str(service.get(key) or "").strip()
            if len(text) < 3:
                continue
            needle = text.casefold()
            if needle in media and len(needle) > best_len:
                best = service
                best_len = len(needle)
    return best


def _output_stream(node: dict) -> bool:
    media_class = str(node.get("media_class") or "")
    if not media_class:
        return True
    return media_class.startswith("Stream/Output")


def plan_audio_actions(services: list[dict], dnd: bool, nodes: list, pids: list[str]) -> list[dict]:
    """Mute plan for Omabox Chromium streams.

    Only nodes whose process id is an Omabox browser pid are touched, so a
    normal Chromium window is left alone. Do not disturb mutes every such
    stream. Otherwise a stream follows the service whose name it matches,
    and an unmatched stream is unmuted so leaving Do not disturb is audible.
    """
    owned = {str(pid) for pid in pids if str(pid)}
    actions: list[dict] = []
    for node in nodes:
        if not isinstance(node, dict):
            continue
        pid = str(node.get("pid") or "")
        if pid not in owned or not _output_stream(node):
            continue
        node_id = str(node.get("id") or "")
        if not node_id:
            continue
        if dnd:
            mute = True
        else:
            matched = best_service_match(node, services)
            mute = False if matched is None else not bool(matched.get("sound", True))
        actions.append({
            "id": node_id,
            "pid": pid,
            "mute": mute,
            "backend": str(node.get("backend") or "pipewire"),
        })
    return actions


def parse_pw_dump(raw: str) -> list[dict]:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(payload, list):
        return []
    nodes: list[dict] = []
    for item in payload:
        if not isinstance(item, dict) or item.get("type") != "PipeWire:Interface:Node":
            continue
        info = item.get("info") if isinstance(item.get("info"), dict) else {}
        props = info.get("props") if isinstance(info.get("props"), dict) else {}
        if not props and isinstance(item.get("props"), dict):
            props = item["props"]
        if not isinstance(props, dict):
            continue
        node_id = item.get("id")
        if node_id is None:
            continue
        pid = props.get("application.process.id")
        nodes.append({
            "id": str(node_id),
            "pid": "" if pid is None else str(pid),
            "media_name": str(props.get("media.name") or ""),
            "app_name": str(props.get("application.name") or ""),
            "media_class": str(props.get("media.class") or ""),
            "backend": "pipewire",
        })
    return nodes


def parse_pactl_inputs(raw: str) -> list[dict]:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if isinstance(payload, dict):
        payload = payload.get("sink_inputs") or payload.get("sink-inputs") or []
    if not isinstance(payload, list):
        return []
    nodes: list[dict] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        props = item.get("properties") if isinstance(item.get("properties"), dict) else {}
        node_id = item.get("index")
        if node_id is None:
            node_id = item.get("id")
        if node_id is None:
            continue
        pid = props.get("application.process.id")
        nodes.append({
            "id": str(node_id),
            "pid": "" if pid is None else str(pid),
            "media_name": str(props.get("media.name") or ""),
            "app_name": str(props.get("application.name") or ""),
            "media_class": "",
            "backend": "pulse",
        })
    return nodes


def _command_stdout(argv: list[str]) -> str:
    try:
        completed = subprocess.run(
            argv,
            check=False,
            capture_output=True,
            text=True,
            timeout=3,
        )
    except (subprocess.SubprocessError, OSError):
        return ""
    if completed.returncode != 0:
        return ""
    return completed.stdout or ""


def pipewire_nodes() -> list[dict]:
    if "OMABOX_PW_DUMP_JSON" in os.environ:
        return parse_pw_dump(os.environ["OMABOX_PW_DUMP_JSON"])
    if "OMABOX_PACTL_JSON" in os.environ:
        return parse_pactl_inputs(os.environ["OMABOX_PACTL_JSON"])
    pw = shutil.which("pw-dump")
    if pw:
        raw = _command_stdout([pw])
        nodes = parse_pw_dump(raw) if raw else []
        if nodes:
            return nodes
    pactl = shutil.which("pactl")
    if pactl:
        raw = _command_stdout([pactl, "-f", "json", "list", "sink-inputs"])
        if raw:
            return parse_pactl_inputs(raw)
    return []


def perform_mute(action: dict) -> bool:
    log_path = os.environ.get("OMABOX_AUDIO_LOG")
    mute = "1" if action.get("mute") else "0"
    if log_path:
        try:
            with open(log_path, "a", encoding="utf-8") as handle:
                handle.write(f"{action.get('backend', 'pipewire')} {action.get('id')} {mute}\n")
        except OSError:
            return False
        return True
    backend = action.get("backend")
    if backend == "pulse":
        argv = ["pactl", "set-sink-input-mute", str(action.get("id")), mute]
    else:
        argv = ["wpctl", "set-mute", str(action.get("id")), mute]
    if shutil.which(argv[0]) is None:
        return False
    try:
        completed = subprocess.run(
            argv,
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=3,
        )
    except (subprocess.SubprocessError, OSError):
        return False
    return completed.returncode == 0


def profile_preferences_path(profile: str) -> Path | None:
    text = str(profile or "")
    if not text or text in (".", "..") or "/" in text or "\\" in text or "\x00" in text:
        return None
    return chromium_dir() / text / "Preferences"


def patch_notification_pref(path: Path | None, allow: bool) -> str:
    """Best-effort Chromium content setting. 1 allows notifications, 2 blocks them.

    A missing or unreadable Preferences file is left alone so the first launch
    can create a complete profile. The Omabox flag stays the source of truth.
    """
    if path is None or not path.is_file():
        return "missing"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeError):
        return "skipped"
    if not isinstance(data, dict):
        return "skipped"
    profile = data.get("profile")
    if profile is None:
        profile = {}
        data["profile"] = profile
    if not isinstance(profile, dict):
        return "skipped"
    defaults = profile.get("default_content_setting_values")
    if defaults is None:
        defaults = {}
        profile["default_content_setting_values"] = defaults
    if not isinstance(defaults, dict):
        return "skipped"
    desired = 1 if allow else 2
    if defaults.get("notifications") == desired:
        return "unchanged"
    defaults["notifications"] = desired
    temporary = path.with_name(path.name + ".omabox-tmp")
    try:
        temporary.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        temporary.replace(path)
    except OSError:
        try:
            temporary.unlink()
        except OSError:
            pass
        return "skipped"
    return "updated"


def apply_notification_flags(services: list[dict], dnd: bool) -> list[dict]:
    # Chromium rewrites Preferences on exit. Skip the file while that process
    # is running so a toggle cannot race it. The dock still hides badges.
    browser_running = bool(chromium_pids(str(chromium_dir())))
    results: list[dict] = []
    for service in services:
        allow = bool(service.get("badges", True)) and not dnd
        if browser_running:
            status = "browser-running"
        else:
            status = patch_notification_pref(profile_preferences_path(str(service.get("profile") or "")), allow)
        results.append({"id": service.get("id", ""), "allow": allow, "notifications": status})
    return results


def apply_audio(services: list[dict], dnd: bool) -> list[dict]:
    pids = chromium_pids(str(chromium_dir()))
    actions = plan_audio_actions(services, dnd, pipewire_nodes(), pids)
    applied: list[dict] = []
    for action in actions:
        applied.append({**action, "ok": perform_mute(action)})
    return applied


def apply_quiet() -> dict:
    services = load_services()
    dnd = bool(normalized_settings()["dnd"])
    return {
        "dnd": dnd,
        "audio": apply_audio(services, dnd),
        "notifications": apply_notification_flags(services, dnd),
    }


def cmd_apply_quiet() -> None:
    json.dump(apply_quiet(), sys.stdout)
    sys.stdout.write("\n")


def favicon_url(page_url: str) -> str:
    parsed = parse_http_url(page_url)
    if not parsed:
        return ""
    host = parsed[0]
    return f"https://www.google.com/s2/favicons?domain={host}&sz=128"


def cmd_fetch_icons() -> None:
    icon_cache_dir().mkdir(parents=True, exist_ok=True)
    for service in load_services():
        if bundled_icon(service["id"]) or not service["url"]:
            continue
        url = favicon_url(service["url"])
        dest = icon_cache_dir() / f"{service['id']}.png"
        try:
            with urllib.request.urlopen(url, timeout=10) as response:
                payload = response.read()
        except Exception as exc:  # noqa: BLE001 - best-effort favicon fetch
            print(f"omabox: icon for {service['id']} failed: {exc}", file=sys.stderr)
            continue
        if len(payload) < 16 or not payload.startswith(b"\x89PNG"):
            print(f"omabox: icon for {service['id']} was not a PNG", file=sys.stderr)
            continue
        dest.write_bytes(payload)
        print(dest)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="omabox")
    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init")
    init.add_argument("--force", action="store_true")

    listing = sub.add_parser("list")
    listing.add_argument("--json", action="store_true")

    config = sub.add_parser("config")
    config.add_argument("key", nargs="?", default="")
    config.add_argument("value", nargs="?", default="")

    get = sub.add_parser("get")
    get.add_argument("id")

    klass = sub.add_parser("class")
    klass.add_argument("url")
    klass.add_argument("profile")

    add = sub.add_parser("add")
    add.add_argument("preset", nargs="?", default="")
    add.add_argument("--id", default="")
    add.add_argument("--name", default="")
    add.add_argument("--url", default=None)
    add.add_argument("--icon", default=None)
    add.add_argument("--profile", default="")
    add.add_argument("--key", default=None)
    add.add_argument("--unread", default=None)
    add.add_argument("--update", action="store_true")

    remove = sub.add_parser("remove")
    remove.add_argument("id")

    service = sub.add_parser("service")
    service.add_argument("id")
    service.add_argument("field")
    service.add_argument("value", nargs="?", default="")

    sub.add_parser("apply-quiet")

    sub.add_parser("rules")

    setup = sub.add_parser("setup")
    setup.add_argument("--menu", action="store_true")

    uninstall = sub.add_parser("uninstall")
    uninstall.add_argument("--purge", action="store_true")

    spec = sub.add_parser("launch-spec")
    spec.add_argument("id")

    pids = sub.add_parser("chromium-pids")
    pids.add_argument("user_data")

    plan = sub.add_parser("focus-plan")
    plan.add_argument("class_name")

    sub.add_parser("fetch-icons")
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    if args.command == "init":
        cmd_init(force=args.force)
    elif args.command == "list":
        cmd_list(as_json=args.json)
    elif args.command == "config":
        cmd_config(args.key, args.value)
    elif args.command == "get":
        cmd_get(args.id)
    elif args.command == "class":
        cmd_class(args.url, args.profile)
    elif args.command == "add":
        cmd_add(args)
    elif args.command == "remove":
        cmd_remove(args.id)
    elif args.command == "service":
        cmd_service(args.id, args.field, args.value)
    elif args.command == "apply-quiet":
        cmd_apply_quiet()
    elif args.command == "rules":
        print(write_rules())
    elif args.command == "setup":
        cmd_setup(menu=args.menu)
    elif args.command == "uninstall":
        cmd_uninstall(purge=args.purge)
    elif args.command == "launch-spec":
        cmd_launch_spec(args.id)
    elif args.command == "chromium-pids":
        cmd_chromium_pids(args.user_data)
    elif args.command == "focus-plan":
        cmd_focus_plan(args.class_name)
    elif args.command == "fetch-icons":
        cmd_fetch_icons()
    else:
        die(f"unknown command {args.command}")


if __name__ == "__main__":
    main()
