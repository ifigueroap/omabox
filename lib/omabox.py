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
import sys
import tomllib
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PRESETS_FILE = ROOT / "presets" / "services.toml"
DEFAULT_UNREAD = r"^\((\d+)\)"
SERVICE_FIELDS = ("id", "name", "url", "icon", "profile", "key", "unread")
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


def render_service(service: dict) -> str:
    lines = ["[[service]]"]
    for field in SERVICE_FIELDS:
        lines.append(f"{field} = {toml_string(str(service.get(field, '')))}")
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
    if not isinstance(data, dict) or "id" not in data:
        die("a [[service]] block is missing id")
    return normalize_service(data)


def normalize_service(data: dict) -> dict:
    service = {field: "" if data.get(field) is None else str(data.get(field)) for field in SERVICE_FIELDS}
    service["id"] = check_id(service["id"].strip())
    service["name"] = service["name"].strip() or service["id"]
    service["url"] = normalize_url(service["url"], allow_empty=True) if service["url"].strip() else ""
    service["profile"] = check_profile(service["profile"] or service["name"])
    service["key"] = check_key(service["key"].strip())
    service["unread"] = check_unread(service["unread"] if service["unread"] != "" else DEFAULT_UNREAD)
    service["icon"] = service["icon"].strip()
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


def public_service(service: dict) -> dict:
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
    services = [public_service(service) for service in load_services()]
    if as_json:
        json.dump({"services": services}, sys.stdout)
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
        "if type(o) ~= \"table\" or type(o.bind) ~= \"function\" or type(o.window) ~= \"function\" then",
        "  return",
        "end",
        "",
        'o.bind("SUPER + O", "Omabox", "omabox toggle")',
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
    public["userDataDir"] = user_data
    public["args"] = args
    json.dump(public, sys.stdout)
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

    sub.add_parser("rules")

    setup = sub.add_parser("setup")
    setup.add_argument("--menu", action="store_true")

    uninstall = sub.add_parser("uninstall")
    uninstall.add_argument("--purge", action="store_true")

    spec = sub.add_parser("launch-spec")
    spec.add_argument("id")

    sub.add_parser("fetch-icons")
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    if args.command == "init":
        cmd_init(force=args.force)
    elif args.command == "list":
        cmd_list(as_json=args.json)
    elif args.command == "get":
        cmd_get(args.id)
    elif args.command == "class":
        cmd_class(args.url, args.profile)
    elif args.command == "add":
        cmd_add(args)
    elif args.command == "remove":
        cmd_remove(args.id)
    elif args.command == "rules":
        print(write_rules())
    elif args.command == "setup":
        cmd_setup(menu=args.menu)
    elif args.command == "uninstall":
        cmd_uninstall(purge=args.purge)
    elif args.command == "launch-spec":
        cmd_launch_spec(args.id)
    elif args.command == "fetch-icons":
        cmd_fetch_icons()
    else:
        die(f"unknown command {args.command}")


if __name__ == "__main__":
    main()
