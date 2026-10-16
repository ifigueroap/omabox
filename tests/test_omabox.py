#!/usr/bin/env python3
"""Headless tests for Omabox config, window class, and install files."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "lib"))

import omabox  # noqa: E402


CLASSES = Path(__file__).with_name("classes.tsv")
OMARCHY_CLASS = r"""
url=$1
address=${url#*://}
address=${address%%[?#]*}
host=${address%%/*}
path=${address:${#host}}
host=${host##*@}
host=${host%%:*}
printf 'chrome-%s_%s-Default\n' "${host,,}" "${path:-/}" | sed 's|/|_|g'
"""


class FocusPlanTests(unittest.TestCase):
    def test_one_visible_window_and_exact_class(self) -> None:
        target = "chrome-web.whatsapp.com__-WhatsApp"
        slack = "chrome-app.slack.com__-Slack"
        clients = [
            {"address": "0xaaa", "class": target, "workspace": {"name": "special:omabox"}},
            {"address": "0xbbb", "class": target, "workspace": {"name": "special:omabox"}},
            {"address": "0xccc", "class": slack, "workspace": {"name": "special:omabox"}},
            {"address": "0xddd", "class": "chrome-web.whatsapp.com__-Whatsapp", "workspace": {"name": "special:omabox"}},
        ]
        plan = omabox.build_focus_plan(clients, target, [target, slack])
        self.assertTrue(plan["found"])
        self.assertEqual(plan["focus"], 'hl.dsp.focus({ window = "class:chrome-web.whatsapp.com__-WhatsApp" })')
        joined = "\n".join(plan["dispatch"])
        self.assertIn('hl.dsp.window.move({ workspace = "special:omabox-hidden", follow = false, window = "address:0xccc" })', joined)
        self.assertIn('hl.dsp.window.close({ window = "address:0xbbb" })', joined)
        self.assertNotIn("0xaaa", joined)
        self.assertNotIn("0xddd", joined)
        self.assertNotIn("Whatsapp", plan["focus"])

        missed = omabox.build_focus_plan(clients, "chrome-web.whatsapp.com__-Whatsapp", [target])
        self.assertTrue(missed["found"])
        self.assertIn("Whatsapp", missed["focus"])
        hidden = omabox.build_focus_plan(
            [{"address": "0xaaa", "class": target, "workspace": {"name": "special:omabox-hidden"}}],
            target,
            [target],
        )
        self.assertIn('workspace = "special:omabox"', "\n".join(hidden["dispatch"]))


class IpcTests(unittest.TestCase):
    def test_panel_registers_quickshell_ipc_handler(self) -> None:
        source = (ROOT / "Panel.qml").read_text(encoding="utf-8")
        # ShellIpc is a qs.Commons component type. A third-party document
        # outside the shell tree cannot name it ("ShellIpc is not a type"),
        # and the panel then never mounts. IpcHandler plus the IpcRegistry
        # singleton is the body of shell/Commons/ShellIpc.qml.
        self.assertNotIn("ShellIpc {", source)
        self.assertIn("IpcHandler {", source)
        self.assertIn('target: "omabox"', source)
        self.assertIn("Commons.IpcRegistry.register(ipc)", source)
        self.assertIn("function dashboard(): string", source)
        self.assertIn("function reload(): string", source)


class ClassTests(unittest.TestCase):
    def test_golden_classes(self) -> None:
        for line in CLASSES.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            url, profile, expected = line.split("\t")
            self.assertEqual(omabox.window_class(url, profile), expected, url)

    def test_matches_omarchy_default_profile(self) -> None:
        urls = [
            "https://web.whatsapp.com/",
            "https://discord.com/app",
            "https://web.telegram.org/a/",
            "https://example.com:8443/foo/bar?q=1#x",
            "https://user:pass@app.slack.com/client",
        ]
        for url in urls:
            got = subprocess.check_output(["bash", "-c", OMARCHY_CLASS, "class", url], text=True).strip()
            self.assertEqual(omabox.window_class(url, "Default"), got, url)

    def test_empty_without_url_or_profile(self) -> None:
        self.assertEqual(omabox.window_class("", "WhatsApp"), "")
        self.assertEqual(omabox.window_class("notaurl", "WhatsApp"), "")
        self.assertEqual(omabox.favicon_url("https://web.whatsapp.com/"), "https://www.google.com/s2/favicons?domain=web.whatsapp.com&sz=128")


class ConfigTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name)
        self._old_home = os.environ.get("HOME")
        os.environ["HOME"] = str(self.home)

    def tearDown(self) -> None:
        if self._old_home is None:
            os.environ.pop("HOME", None)
        else:
            os.environ["HOME"] = self._old_home
        self.tmp.cleanup()

    def test_init_add_remove_roundtrip(self) -> None:
        omabox.cmd_init()
        services = omabox.load_services()
        self.assertEqual(
            [service["id"] for service in services],
            ["whatsapp", "slack", "discord", "zulip", "telegram", "grok", "chatgpt", "claude", "grok-bot"],
        )
        zulip = next(service for service in services if service["id"] == "zulip")
        self.assertEqual(zulip["url"], "")
        self.assertEqual(omabox.window_class(zulip["url"], zulip["profile"]), "")

        omabox.main(["add", "--name", "My App", "--url", "example.com/app", "--profile", "My App", "--key", "2"])
        added = next(service for service in omabox.load_services() if service["id"] == "my-app")
        self.assertEqual(added["url"], "https://example.com/app")
        self.assertEqual(added["profile"], "My App")
        self.assertEqual(omabox.window_class(added["url"], added["profile"]), "chrome-example.com__app-My_App")
        header = omabox.config_file().read_text(encoding="utf-8")
        self.assertIn("Zulip has no public URL", header)

        with self.assertRaises(SystemExit):
            omabox.main(["add", "--name", "My App", "--url", "https://example.com/other"])

        omabox.main(["add", "zulip", "--url", "https://chat.example.com/", "--update"])
        zulip = next(service for service in omabox.load_services() if service["id"] == "zulip")
        self.assertEqual(zulip["url"], "https://chat.example.com/")
        self.assertEqual(omabox.public_service(zulip)["class"], "chrome-chat.example.com__-Zulip")

        omabox.main(["remove", "my-app"])
        self.assertIsNone(omabox.find_service(omabox.load_services(), "my-app"))

    def test_rejects_bad_url_and_profile(self) -> None:
        omabox.cmd_init()
        with self.assertRaises(SystemExit):
            omabox.main(["add", "--name", "Bad", "--url", "javascript:alert(1)"])
        with self.assertRaises(SystemExit):
            omabox.main(["add", "--name", "Bad", "--url", "https://example.com/a b"])
        with self.assertRaises(SystemExit):
            omabox.main(["add", "--name", "Bad", "--url", "https://example.com/", "--profile", "../escape"])

    def test_unread_regex_roundtrip(self) -> None:
        omabox.cmd_init()
        whatsapp = omabox.find_service(omabox.load_services(), "whatsapp")
        assert whatsapp is not None
        self.assertEqual(whatsapp["unread"], r"^\((\d+)\)")

    def test_list_json_icons_are_bundled(self) -> None:
        omabox.cmd_init()
        raw = subprocess.check_output([sys.executable, str(ROOT / "lib" / "omabox.py"), "list", "--json"], text=True)
        payload = json.loads(raw)
        icons = {row["id"]: row["icon"] for row in payload["services"]}
        self.assertTrue(icons["whatsapp"].endswith("/icons/whatsapp.svg"))
        self.assertTrue(Path(icons["whatsapp"]).is_file())
        self.assertTrue(icons["grok-bot"].endswith("/icons/grok-bot.svg"))
        zulip = next(row for row in payload["services"] if row["id"] == "zulip")
        self.assertEqual(zulip["class"], "")
        self.assertFalse(zulip["ready"])
        self.assertEqual(payload["dock"], "always")
        self.assertEqual(payload["edge"], "right")
        self.assertIs(payload["pinned"], False)
        self.assertIs(payload["dnd"], False)
        self.assertIs(next(row for row in payload["services"] if row["id"] == "whatsapp")["sound"], True)
        self.assertIs(next(row for row in payload["services"] if row["id"] == "whatsapp")["badges"], True)

    def test_launch_spec(self) -> None:
        omabox.cmd_init()
        spec = json.loads(subprocess.check_output([sys.executable, str(ROOT / "lib" / "omabox.py"), "launch-spec", "1"], text=True))
        self.assertEqual(spec["id"], "whatsapp")
        self.assertIn(f"--user-data-dir={self.home / '.local' / 'share' / 'omabox' / 'chromium'}", spec["args"])
        self.assertIn("--profile-directory=WhatsApp", spec["args"])
        self.assertIn("--app=https://web.whatsapp.com/", spec["args"])
        self.assertEqual(spec["class"], "chrome-web.whatsapp.com__-WhatsApp")
        with self.assertRaises(subprocess.CalledProcessError):
            subprocess.check_output([sys.executable, str(ROOT / "lib" / "omabox.py"), "launch-spec", "zulip"], stderr=subprocess.STDOUT)

    def test_lua_rules_and_setup_roundtrip(self) -> None:
        omabox.cmd_setup(menu=True)
        lua = (self.home / ".config" / "hypr" / "omabox.lua").read_text(encoding="utf-8")
        self.assertIn('o.rebind("SUPER + SHIFT + O", "Omabox", "omabox toggle")', lua)
        self.assertNotIn('o.bind("SUPER + O", "Omabox", "omabox toggle")', lua)
        self.assertIn("Obsidian", lua)
        self.assertIn("SUPER + ALT + code:", lua)
        self.assertIn("special:omabox silent", lua)
        self.assertIn(r"^chrome\\-web\\.whatsapp\\.com__\\-WhatsApp$", lua)
        self.assertNotIn("Zulip", lua)
        bindings = (self.home / ".config" / "hypr" / "bindings.lua").read_text(encoding="utf-8")
        self.assertEqual(bindings.count('require("hypr.omabox")'), 1)
        menu = (self.home / ".config" / "omarchy" / "extensions" / "omarchy-menu.jsonc").read_text(encoding="utf-8")
        self.assertIn('"omabox"', menu)
        self.assertIn("omabox dashboard", menu)
        link = self.home / ".local" / "bin" / "omabox"
        self.assertTrue(link.is_symlink())
        self.assertEqual(link.resolve(), (ROOT / "bin" / "omabox").resolve())

        omabox.main(["add", "zulip", "--url", "https://chat.example.org/", "--update"])
        lua = (self.home / ".config" / "hypr" / "omabox.lua").read_text(encoding="utf-8")
        self.assertIn(r"chat\\.example\\.org", lua)

        omabox.cmd_setup(menu=True)
        bindings = (self.home / ".config" / "hypr" / "bindings.lua").read_text(encoding="utf-8")
        self.assertEqual(bindings.count('require("hypr.omabox")'), 1)

        omabox.cmd_uninstall(purge=False)
        self.assertFalse((self.home / ".config" / "hypr" / "omabox.lua").exists())
        self.assertNotIn("omabox", (self.home / ".config" / "hypr" / "bindings.lua").read_text(encoding="utf-8"))
        self.assertTrue(omabox.config_file().is_file())
        self.assertFalse(link.exists())
        omabox.cmd_uninstall(purge=True)
        self.assertFalse(omabox.config_dir().exists())

    def test_dock_mode_roundtrip(self) -> None:
        self.assertEqual(omabox.load_dock_mode(), "always")
        self.assertEqual(omabox.normalized_settings()["edge"], "right")
        self.assertIs(omabox.normalized_settings()["pinned"], False)
        omabox.cmd_config("dock", "special-only")
        text = omabox.settings_file().read_text(encoding="utf-8")
        self.assertIn('dock = "special-only"', text)
        self.assertIn('edge = "right"', text)
        self.assertIn("pinned = false", text)
        self.assertEqual(omabox.load_dock_mode(), "special-only")
        omabox.cmd_config("edge", "top")
        omabox.cmd_config("pinned", "true")
        omabox.cmd_config("dock", "always")
        text = omabox.settings_file().read_text(encoding="utf-8")
        self.assertIn('dock = "always"', text)
        self.assertIn('edge = "top"', text)
        self.assertIn("pinned = true", text)
        self.assertEqual(omabox.normalized_settings()["edge"], "top")
        self.assertIs(omabox.normalized_settings()["pinned"], True)
        listed = json.loads(subprocess.check_output(
            [sys.executable, str(ROOT / "lib" / "omabox.py"), "list", "--json"],
            text=True,
        ))
        self.assertEqual(listed["dock"], "always")
        self.assertEqual(listed["edge"], "top")
        self.assertIs(listed["pinned"], True)
        shown = subprocess.check_output(
            [sys.executable, str(ROOT / "lib" / "omabox.py"), "config"],
            text=True,
        )
        self.assertIn("dock=always", shown)
        self.assertIn("edge=top", shown)
        self.assertIn("pinned=true", shown)
        omabox.settings_file().write_text('dock = "special-only"\nnote = "keep"\n', encoding="utf-8")
        omabox.cmd_config("edge", "bottom")
        kept = omabox.settings_file().read_text(encoding="utf-8")
        self.assertIn('dock = "special-only"', kept)
        self.assertIn('edge = "bottom"', kept)
        self.assertIn('note = "keep"', kept)
        with self.assertRaises(SystemExit):
            omabox.cmd_config("dock", "sometimes")
        with self.assertRaises(SystemExit):
            omabox.cmd_config("edge", "middle")
        with self.assertRaises(SystemExit):
            omabox.cmd_config("pinned", "yes")
        with self.assertRaises(SystemExit):
            omabox.cmd_config("theme", "dark")

    def test_menu_insert_keeps_existing_entries(self) -> None:
        menu = self.home / ".config" / "omarchy" / "extensions" / "omarchy-menu.jsonc"
        menu.parent.mkdir(parents=True)
        menu.write_text('{\n  // comment\n  "personal": {"label":"Personal"}\n}\n', encoding="utf-8")
        omabox.install_menu()
        text = menu.read_text(encoding="utf-8")
        self.assertIn('"personal"', text)
        self.assertEqual(text.count("BEGIN omabox"), 1)
        omabox.install_menu()
        self.assertEqual(menu.read_text(encoding="utf-8").count("BEGIN omabox"), 1)
        omabox.remove_menu()
        cleaned = menu.read_text(encoding="utf-8")
        self.assertNotIn("BEGIN omabox", cleaned)
        self.assertIn('"personal"', cleaned)


class QuietTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name)
        self._old_home = os.environ.get("HOME")
        self._old_env = {
            key: os.environ.get(key)
            for key in ("OMABOX_PW_DUMP_JSON", "OMABOX_PACTL_JSON", "OMABOX_AUDIO_LOG", "OMABOX_PROC_ROOT")
        }
        os.environ["HOME"] = str(self.home)
        os.environ["OMABOX_PW_DUMP_JSON"] = "[]"
        os.environ.pop("OMABOX_PACTL_JSON", None)
        os.environ.pop("OMABOX_AUDIO_LOG", None)
        os.environ.pop("OMABOX_PROC_ROOT", None)

    def tearDown(self) -> None:
        if self._old_home is None:
            os.environ.pop("HOME", None)
        else:
            os.environ["HOME"] = self._old_home
        for key, value in self._old_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self.tmp.cleanup()

    def test_defaults_and_dnd_do_not_rewrite_services(self) -> None:
        omabox.cmd_init()
        services_before = omabox.config_file().read_text(encoding="utf-8")
        self.assertNotIn("sound =", services_before)
        whatsapp = omabox.find_service(omabox.load_services(), "whatsapp")
        assert whatsapp is not None
        self.assertTrue(whatsapp["sound"])
        self.assertTrue(whatsapp["badges"])
        self.assertIs(omabox.normalized_settings()["dnd"], False)
        omabox.cmd_config("dnd", "true")
        self.assertEqual(omabox.config_file().read_text(encoding="utf-8"), services_before)
        self.assertIn("dnd = true", omabox.settings_file().read_text(encoding="utf-8"))
        self.assertIs(omabox.normalized_settings()["dnd"], True)
        listed = json.loads(subprocess.check_output(
            [sys.executable, str(ROOT / "lib" / "omabox.py"), "list", "--json"],
            text=True,
        ))
        self.assertIs(listed["dnd"], True)
        row = next(item for item in listed["services"] if item["id"] == "slack")
        self.assertIs(row["sound"], True)
        self.assertIs(row["soundEffective"], False)
        self.assertIs(row["badgesEffective"], False)
        omabox.cmd_config("do_not_disturb", "false")
        self.assertIs(omabox.normalized_settings()["dnd"], False)
        with self.assertRaises(SystemExit):
            omabox.cmd_config("dnd", "maybe")

    def test_service_flags_survive_update_and_keep_other_services(self) -> None:
        omabox.cmd_init()
        original = omabox.config_file().read_text(encoding="utf-8")
        original = original.replace('id = "whatsapp"\n', 'id = "whatsapp"\ncustom = "kept"\n', 1)
        omabox.config_file().write_text(original, encoding="utf-8")
        ids_before = [service["id"] for service in omabox.load_services()]
        omabox.main(["service", "whatsapp", "sound", "false"])
        text = omabox.config_file().read_text(encoding="utf-8")
        self.assertIn("Zulip has no public URL", text)
        self.assertIn('custom = "kept"', text)
        self.assertIn("sound = false", text)
        services = omabox.load_services()
        self.assertEqual([service["id"] for service in services], ids_before)
        whatsapp = omabox.find_service(services, "whatsapp")
        slack = omabox.find_service(services, "slack")
        assert whatsapp is not None and slack is not None
        self.assertFalse(whatsapp["sound"])
        self.assertTrue(whatsapp["badges"])
        self.assertEqual(whatsapp["_extra"].get("custom"), "kept")
        self.assertTrue(slack["sound"])
        self.assertTrue(slack["badges"])
        omabox.main(["add", "whatsapp", "--url", "https://web.whatsapp.com/", "--update"])
        whatsapp = omabox.find_service(omabox.load_services(), "whatsapp")
        assert whatsapp is not None
        self.assertFalse(whatsapp["sound"])
        self.assertEqual(whatsapp["url"], "https://web.whatsapp.com/")
        self.assertEqual(whatsapp["_extra"].get("custom"), "kept")
        omabox.main(["service", "2", "badges", "false"])
        slack = omabox.find_service(omabox.load_services(), "slack")
        assert slack is not None
        self.assertFalse(slack["badges"])
        self.assertTrue(slack["sound"])
        shown = subprocess.check_output(
            [sys.executable, str(ROOT / "lib" / "omabox.py"), "service", "whatsapp", "sound"],
            text=True,
        )
        self.assertEqual(shown.strip(), "false")
        with self.assertRaises(SystemExit):
            omabox.main(["service", "whatsapp", "theme", "false"])
        with self.assertRaises(SystemExit):
            omabox.main(["service", "whatsapp", "sound", "maybe"])

    def test_legacy_do_not_disturb_key_is_kept(self) -> None:
        omabox.settings_file().parent.mkdir(parents=True, exist_ok=True)
        omabox.settings_file().write_text('do_not_disturb = true\nnote = "keep"\n', encoding="utf-8")
        self.assertIs(omabox.normalized_settings()["dnd"], True)
        omabox.cmd_config("edge", "left")
        text = omabox.settings_file().read_text(encoding="utf-8")
        self.assertIn("dnd = true", text)
        self.assertIn("do_not_disturb = true", text)
        self.assertIn('note = "keep"', text)
        self.assertIn('edge = "left"', text)

    def test_audio_plan_and_notification_pref(self) -> None:
        services = [
            {"id": "whatsapp", "name": "WhatsApp", "profile": "WhatsApp", "sound": False, "badges": True},
            {"id": "slack", "name": "Slack", "profile": "Slack", "sound": True, "badges": False},
            {"id": "work-slack", "name": "Work Slack", "profile": "Work Slack", "sound": False, "badges": True},
        ]
        nodes = [
            {"id": "10", "pid": "42", "media_name": "WhatsApp", "media_class": "Stream/Output/Audio", "backend": "pipewire"},
            {"id": "11", "pid": "42", "media_name": "Slack call", "media_class": "Stream/Output/Audio", "backend": "pipewire"},
            {"id": "12", "pid": "42", "media_name": "Other tab", "media_class": "Stream/Output/Audio", "backend": "pipewire"},
            {"id": "13", "pid": "99", "media_name": "WhatsApp", "media_class": "Stream/Output/Audio", "backend": "pipewire"},
            {"id": "14", "pid": "42", "media_name": "Mic", "media_class": "Stream/Input/Audio", "backend": "pipewire"},
            {"id": "15", "pid": "42", "media_name": "Work Slack", "media_class": "Stream/Output/Audio", "backend": "pipewire"},
        ]
        muted = {item["id"]: item["mute"] for item in omabox.plan_audio_actions(services, False, nodes, ["42"])}
        self.assertTrue(muted["10"])
        self.assertFalse(muted["11"])
        self.assertFalse(muted["12"])
        self.assertNotIn("13", muted)
        self.assertNotIn("14", muted)
        self.assertTrue(muted["15"])
        dnd = {item["id"]: item["mute"] for item in omabox.plan_audio_actions(services, True, nodes, ["42"])}
        self.assertTrue(dnd["10"])
        self.assertTrue(dnd["11"])
        self.assertTrue(dnd["12"])
        self.assertNotIn("13", dnd)

        raw = json.dumps([
            {
                "id": 10,
                "type": "PipeWire:Interface:Node",
                "info": {"props": {
                    "application.process.id": 42,
                    "media.name": "WhatsApp",
                    "media.class": "Stream/Output/Audio",
                    "application.name": "Chromium",
                }},
            },
            {"id": 3, "type": "PipeWire:Interface:Client"},
        ])
        parsed = omabox.parse_pw_dump(raw)
        self.assertEqual(parsed[0]["pid"], "42")
        self.assertEqual(parsed[0]["media_name"], "WhatsApp")
        self.assertEqual(omabox.parse_pw_dump("not-json"), [])
        pulse = omabox.parse_pactl_inputs(json.dumps([
            {"index": 7, "properties": {"application.process.id": "42", "media.name": "Slack"}},
        ]))
        self.assertEqual(pulse[0]["backend"], "pulse")
        self.assertEqual(pulse[0]["id"], "7")

        omabox.cmd_init()
        prefs = omabox.profile_preferences_path("WhatsApp")
        assert prefs is not None
        prefs.parent.mkdir(parents=True)
        prefs.write_text(json.dumps({
            "other": 1,
            "profile": {"name": "WhatsApp", "default_content_setting_values": {"popups": 1}},
        }), encoding="utf-8")
        broken = omabox.profile_preferences_path("Slack")
        assert broken is not None
        broken.parent.mkdir(parents=True)
        broken.write_text("{", encoding="utf-8")
        results = {row["id"]: row for row in omabox.apply_notification_flags(omabox.load_services(), False)}
        self.assertEqual(results["whatsapp"]["notifications"], "updated")
        self.assertTrue(results["whatsapp"]["allow"])
        self.assertEqual(results["zulip"]["notifications"], "missing")
        saved = json.loads(prefs.read_text(encoding="utf-8"))
        self.assertEqual(saved["other"], 1)
        self.assertEqual(saved["profile"]["default_content_setting_values"]["popups"], 1)
        self.assertEqual(saved["profile"]["default_content_setting_values"]["notifications"], 1)
        self.assertEqual(broken.read_text(encoding="utf-8"), "{")
        omabox.main(["service", "whatsapp", "badges", "false"])
        saved = json.loads(prefs.read_text(encoding="utf-8"))
        self.assertEqual(saved["profile"]["default_content_setting_values"]["notifications"], 2)
        self.assertEqual(omabox.patch_notification_pref(prefs, False), "unchanged")
        omabox.cmd_config("dnd", "true")
        blocked = {row["id"]: row for row in omabox.apply_notification_flags(omabox.load_services(), True)}
        self.assertFalse(blocked["slack"]["allow"])

        proc = self.home / "proc" / "42"
        proc.mkdir(parents=True)
        user_data = str(self.home / ".local" / "share" / "omabox" / "chromium")
        (proc / "cmdline").write_bytes(f"chromium\0--user-data-dir={user_data}\0".encode())
        os.environ["OMABOX_PROC_ROOT"] = str(self.home / "proc")
        os.environ["OMABOX_PW_DUMP_JSON"] = raw
        log = self.home / "audio.log"
        os.environ["OMABOX_AUDIO_LOG"] = str(log)
        omabox.cmd_config("dnd", "false")
        omabox.main(["service", "whatsapp", "sound", "false"])
        logged = log.read_text(encoding="utf-8").strip().splitlines()
        self.assertIn("pipewire 10 1", logged)
        saved = json.loads(prefs.read_text(encoding="utf-8"))
        saved["profile"]["default_content_setting_values"]["notifications"] = 1
        prefs.write_text(json.dumps(saved), encoding="utf-8")
        skipped = omabox.apply_notification_flags(omabox.load_services(), True)
        self.assertEqual(skipped[0]["id"], "whatsapp")
        self.assertEqual(skipped[0]["notifications"], "browser-running")
        self.assertEqual(
            json.loads(prefs.read_text(encoding="utf-8"))["profile"]["default_content_setting_values"]["notifications"],
            1,
        )

    def test_launch_spec_mute_flag(self) -> None:
        omabox.cmd_init()
        omabox.main(["service", "whatsapp", "sound", "false"])
        spec = json.loads(subprocess.check_output(
            [sys.executable, str(ROOT / "lib" / "omabox.py"), "launch-spec", "whatsapp"],
            text=True,
        ))
        self.assertIs(spec["muteAudio"], True)
        self.assertNotIn("--mute-audio", spec["args"])
        omabox.main(["service", "whatsapp", "sound", "true"])
        spec = json.loads(subprocess.check_output(
            [sys.executable, str(ROOT / "lib" / "omabox.py"), "launch-spec", "whatsapp"],
            text=True,
        ))
        self.assertIs(spec["muteAudio"], False)

    def test_dock_menu_is_wired(self) -> None:
        dock = (ROOT / "DockWindow.qml").read_text(encoding="utf-8")
        self.assertIn("Qt.RightButton", dock)
        self.assertIn("onPressAndHold", dock)
        self.assertIn("suppressHold", dock)
        self.assertIn("serviceMenuItems", dock)
        self.assertIn("openMenu", dock)
        self.assertIn('["service", window.menuServiceId, modelData.field, modelData.next]', dock)
        self.assertIn('["config", "dnd", window.host.doNotDisturb ? "false" : "true"]', dock)
        self.assertIn("Do not disturb", dock)
        self.assertIn("allowsBadges", dock)
        self.assertIn("allowsSound", dock)
        panel = (ROOT / "Panel.qml").read_text(encoding="utf-8")
        self.assertIn("doNotDisturb", panel)
        self.assertIn('root.lastArgs[0] === "service"', panel)
        dashboard = (ROOT / "DashboardWindow.qml").read_text(encoding="utf-8")
        self.assertIn("Do not disturb", dashboard)
        self.assertIn('["config", "dnd", modelData.value]', dashboard)
        self.assertIn('["service", modelData.id, "sound"', dashboard)
        self.assertIn('["service", modelData.id, "badges"', dashboard)


class CliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name)
        self.env = os.environ.copy()
        self.env["HOME"] = str(self.home)
        self.env["PATH"] = "/usr/bin:/bin"
        subprocess.check_call([str(ROOT / "bin" / "omabox"), "init"], env=self.env)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def run_cli(self, *args: str) -> str:
        return subprocess.check_output([str(ROOT / "bin" / "omabox"), *args], env=self.env, text=True)

    def test_launch_toggle_focus_print(self) -> None:
        launch = self.run_cli("launch", "whatsapp", "--print")
        self.assertIn("wrapper direct", launch)
        self.assertIn("--user-data-dir=", launch)
        self.assertIn("--profile-directory=WhatsApp", launch)
        self.assertIn("--app=https://web.whatsapp.com/", launch)
        self.assertIn("--no-first-run", launch)
        self.assertNotIn("uwsm-app", launch)
        self.assertEqual(
            self.run_cli("toggle", "--print").strip(),
            'hyprctl dispatch \'hl.dsp.workspace.toggle_special("omabox")\'',
        )
        focus = self.run_cli("focus", "1", "--print")
        self.assertIn("class chrome-web.whatsapp.com__-WhatsApp", focus)
        self.assertIn("single-window special:omabox", focus)
        self.assertIn('workspace = "special:omabox-hidden"', focus)
        self.assertIn(
            'hyprctl dispatch \'hl.dsp.focus({ window = "class:chrome-web.whatsapp.com__-WhatsApp" })\'',
            focus,
        )
        self.assertIn('hyprctl dispatch \'hl.dsp.workspace.toggle_special("omabox")\'', focus)
        self.assertNotIn("togglespecialworkspace", focus)
        self.assertNotIn("focuswindow", focus)
        self.assertNotIn("movetoworkspace", focus)

    def test_launch_shows_workspace_after_window_exists(self) -> None:
        bindir = self.home / "bin"
        bindir.mkdir()
        hypr_log = self.home / "hypr.log"
        launch_log = self.home / "launch.log"
        (bindir / "hyprctl").write_text(
            "#!/bin/bash\n"
            'printf "%s\\n" "$*" >> "$OMABOX_HYPR_LOG"\n'
            'if [[ $1 == -j && $2 == clients ]]; then\n'
            "  lines=0\n"
            '  if [[ -f $OMABOX_LAUNCH_LOG ]]; then\n'
            '    lines=$(grep -c . "$OMABOX_LAUNCH_LOG" || true)\n'
            "  fi\n"
            '  if [[ ${lines:-0} -ge 1 ]]; then\n'
            '    printf "%s\\n" \'[{"class":"chrome-web.whatsapp.com__-WhatsApp"}]\'\n'
            "  else\n"
            "    printf '%s\\n' '[]'\n"
            "  fi\n"
            'elif [[ $1 == -j && $2 == monitors ]]; then\n'
            '  printf "%s\\n" \'[{"specialWorkspace":{"name":""}}]\'\n'
            "fi\n"
            "exit 0\n",
            encoding="utf-8",
        )
        (bindir / "uwsm-app").write_text(
            "#!/bin/bash\n"
            'printf "%s\\n" "$*" >> "$OMABOX_LAUNCH_LOG"\n'
            "exit 0\n",
            encoding="utf-8",
        )
        (bindir / "chromium").write_text("#!/bin/bash\nexit 0\n", encoding="utf-8")
        for name in ("hyprctl", "uwsm-app", "chromium"):
            (bindir / name).chmod(0o755)
        env = self.env.copy()
        env["PATH"] = f"{bindir}:/usr/bin:/bin"
        env["OMABOX_HYPR_LOG"] = str(hypr_log)
        env["OMABOX_LAUNCH_LOG"] = str(launch_log)
        subprocess.check_call([str(ROOT / "bin" / "omabox"), "launch", "whatsapp"], env=env)
        launched = launch_log.read_text(encoding="utf-8")
        self.assertIn("--user-data-dir=", launched)
        self.assertIn("--profile-directory=WhatsApp", launched)
        self.assertIn("--app=https://web.whatsapp.com/", launched)
        hypr = hypr_log.read_text(encoding="utf-8")
        self.assertLess(hypr.index("-j clients"), hypr.index('dispatch hl.dsp.workspace.toggle_special("omabox")'))
        self.assertIn(
            'dispatch hl.dsp.window.move({ workspace = "special:omabox", follow = false, window = "class:chrome-web.whatsapp.com__-WhatsApp" })',
            hypr,
        )
        self.assertIn('dispatch hl.dsp.focus({ window = "class:chrome-web.whatsapp.com__-WhatsApp" })', hypr)
        self.assertNotIn("togglespecialworkspace", hypr)
        self.assertNotIn("focuswindow", hypr)

    def test_focus_reveals_existing_window_without_launch(self) -> None:
        bindir = self.home / "bin"
        bindir.mkdir()
        hypr_log = self.home / "hypr.log"
        launch_log = self.home / "launch.log"
        (bindir / "hyprctl").write_text(
            "#!/bin/bash\n"
            'printf "%s\\n" "$*" >> "$OMABOX_HYPR_LOG"\n'
            'if [[ $1 == -j && $2 == clients ]]; then\n'
            '  printf "%s\\n" \'[{"class":"chrome-web.whatsapp.com__-WhatsApp"}]\'\n'
            'elif [[ $1 == -j && $2 == monitors ]]; then\n'
            '  printf "%s\\n" \'[{"specialWorkspace":{"name":""}}]\'\n'
            "fi\n"
            "exit 0\n",
            encoding="utf-8",
        )
        (bindir / "uwsm-app").write_text("#!/bin/bash\nprintf '%s\\n' \"$*\" >> \"$OMABOX_LAUNCH_LOG\"\nexit 0\n", encoding="utf-8")
        (bindir / "chromium").write_text("#!/bin/bash\nexit 0\n", encoding="utf-8")
        for name in ("hyprctl", "uwsm-app", "chromium"):
            (bindir / name).chmod(0o755)
        env = self.env.copy()
        env["PATH"] = f"{bindir}:/usr/bin:/bin"
        env["OMABOX_HYPR_LOG"] = str(hypr_log)
        env["OMABOX_LAUNCH_LOG"] = str(launch_log)
        subprocess.check_call([str(ROOT / "bin" / "omabox"), "focus", "whatsapp"], env=env)
        self.assertFalse(launch_log.exists())
        hypr = hypr_log.read_text(encoding="utf-8")
        self.assertIn('dispatch hl.dsp.workspace.toggle_special("omabox")', hypr)
        self.assertIn('dispatch hl.dsp.focus({ window = "class:chrome-web.whatsapp.com__-WhatsApp" })', hypr)

    def test_focus_parks_other_services_and_closes_duplicates(self) -> None:
        bindir = self.home / "bin"
        bindir.mkdir()
        hypr_log = self.home / "hypr.log"
        launch_log = self.home / "launch.log"
        whatsapp = "chrome-web.whatsapp.com__-WhatsApp"
        slack = omabox.window_class("https://app.slack.com/", "Slack")
        clients = json.dumps(
            [
                {"address": "0xaaa", "class": whatsapp, "workspace": {"name": "special:omabox"}},
                {"address": "0xbbb", "class": whatsapp, "workspace": {"name": "special:omabox"}},
                {"address": "0xccc", "class": slack, "workspace": {"name": "special:omabox"}},
            ]
        )
        (bindir / "hyprctl").write_text(
            "#!/bin/bash\n"
            'printf "%s\\n" "$*" >> "$OMABOX_HYPR_LOG"\n'
            'if [[ $1 == -j && $2 == clients ]]; then\n'
            f"  printf '%s\\n' {clients!r}\n"
            'elif [[ $1 == -j && $2 == monitors ]]; then\n'
            '  printf "%s\\n" \'[{"specialWorkspace":{"name":""}}]\'\n'
            "fi\n"
            "exit 0\n",
            encoding="utf-8",
        )
        (bindir / "uwsm-app").write_text("#!/bin/bash\nprintf '%s\\n' \"$*\" >> \"$OMABOX_LAUNCH_LOG\"\nexit 0\n", encoding="utf-8")
        (bindir / "chromium").write_text("#!/bin/bash\nexit 0\n", encoding="utf-8")
        for name in ("hyprctl", "uwsm-app", "chromium"):
            (bindir / name).chmod(0o755)
        env = self.env.copy()
        env["PATH"] = f"{bindir}:/usr/bin:/bin"
        env["OMABOX_HYPR_LOG"] = str(hypr_log)
        env["OMABOX_LAUNCH_LOG"] = str(launch_log)
        subprocess.check_call([str(ROOT / "bin" / "omabox"), "focus", "whatsapp"], env=env)
        self.assertFalse(launch_log.exists())
        hypr = hypr_log.read_text(encoding="utf-8")
        self.assertLess(
            hypr.index('dispatch hl.dsp.window.move({ workspace = "special:omabox-hidden", follow = false, window = "address:0xccc" })'),
            hypr.index('dispatch hl.dsp.focus({ window = "class:chrome-web.whatsapp.com__-WhatsApp" })'),
        )
        self.assertIn('dispatch hl.dsp.window.close({ window = "address:0xbbb" })', hypr)
        self.assertNotIn("address:0xaaa", hypr)

    def test_launch_runs_once_when_no_window_exists(self) -> None:
        bindir = self.home / "bin"
        bindir.mkdir()
        hypr_log = self.home / "hypr.log"
        launch_log = self.home / "launch.log"
        user_data = self.home / ".local" / "share" / "omabox" / "chromium"
        proc = self.home / "proc" / "424242"
        proc.mkdir(parents=True)
        (proc / "cmdline").write_bytes(b"chromium\0--user-data-dir=" + str(user_data).encode() + b"\0")
        (bindir / "hyprctl").write_text(
            "#!/bin/bash\n"
            'printf "%s\\n" "$*" >> "$OMABOX_HYPR_LOG"\n'
            'if [[ $1 == -j && $2 == clients ]]; then\n'
            "  lines=0\n"
            '  if [[ -f $OMABOX_LAUNCH_LOG ]]; then lines=$(grep -c . "$OMABOX_LAUNCH_LOG" || true); fi\n'
            '  if [[ ${lines:-0} -ge 2 ]]; then\n'
            '    printf "%s\\n" \'[{"class":"chrome-web.whatsapp.com__-WhatsApp"}]\'\n'
            "  else\n"
            "    printf '%s\\n' '[]'\n"
            "  fi\n"
            'elif [[ $1 == -j && $2 == monitors ]]; then\n'
            '  printf "%s\\n" \'[{"specialWorkspace":{"name":""}}]\'\n'
            "fi\n"
            "exit 0\n",
            encoding="utf-8",
        )
        (bindir / "uwsm-app").write_text("#!/bin/bash\nprintf '%s\\n' \"$*\" >> \"$OMABOX_LAUNCH_LOG\"\nexit 0\n", encoding="utf-8")
        (bindir / "chromium").write_text("#!/bin/bash\nexit 0\n", encoding="utf-8")
        for name in ("hyprctl", "uwsm-app", "chromium"):
            (bindir / name).chmod(0o755)
        env = self.env.copy()
        env["PATH"] = f"{bindir}:/usr/bin:/bin"
        env["OMABOX_HYPR_LOG"] = str(hypr_log)
        env["OMABOX_LAUNCH_LOG"] = str(launch_log)
        env["OMABOX_PROC_ROOT"] = str(self.home / "proc")
        env["OMABOX_WINDOW_WAIT_TICKS"] = "1"
        result = subprocess.run(
            [str(ROOT / "bin" / "omabox"), "focus", "whatsapp"],
            env=env,
            check=False,
            stderr=subprocess.PIPE,
            text=True,
        )
        self.assertEqual(result.returncode, 1)
        self.assertNotIn("launching whatsapp again", result.stderr)
        launched = launch_log.read_text(encoding="utf-8").strip().splitlines()
        self.assertEqual(len(launched), 1)

    def test_chromium_pids_match_the_shared_browser_only(self) -> None:
        proc = self.home / "proc"
        data = str(self.home / ".local" / "share" / "omabox" / "chromium")
        (proc / "42").mkdir(parents=True)
        (proc / "42" / "cmdline").write_bytes(f"chromium\0--user-data-dir={data}\0".encode())
        (proc / "7").mkdir()
        (proc / "7" / "cmdline").write_bytes(f"bash\0--user-data-dir={data}\0".encode())
        (proc / "9").mkdir()
        (proc / "9" / "cmdline").write_bytes(b"chromium\0--user-data-dir=/tmp/other\0")
        self.assertEqual(omabox.chromium_pids(data, proc), ["42"])

    def test_service_dnd_commands(self) -> None:
        services_before = (self.home / ".config" / "omabox" / "services.toml").read_text(encoding="utf-8")
        self.assertEqual(self.run_cli("service", "whatsapp", "sound", "false").strip(), "false")
        listed = json.loads(self.run_cli("list", "--json"))
        whatsapp = next(row for row in listed["services"] if row["id"] == "whatsapp")
        slack = next(row for row in listed["services"] if row["id"] == "slack")
        self.assertIs(whatsapp["sound"], False)
        self.assertIs(whatsapp["badges"], True)
        self.assertIs(whatsapp["soundEffective"], False)
        self.assertIs(slack["sound"], True)
        self.assertIs(listed["dnd"], False)
        self.assertIn("whatsapp", services_before)
        rewritten = (self.home / ".config" / "omabox" / "services.toml").read_text(encoding="utf-8")
        self.assertIn('id = "slack"', rewritten)
        self.assertIn('id = "zulip"', rewritten)
        self.assertIn("Zulip has no public URL", rewritten)
        self.assertEqual(self.run_cli("config", "dnd", "true").strip(), "true")
        self.assertIn("dnd=true", self.run_cli("config"))
        listed = json.loads(self.run_cli("list", "--json"))
        self.assertIs(listed["dnd"], True)
        slack = next(row for row in listed["services"] if row["id"] == "slack")
        self.assertIs(slack["sound"], True)
        self.assertIs(slack["soundEffective"], False)
        self.assertIs(slack["badgesEffective"], False)

    def test_list_and_class(self) -> None:
        listed = self.run_cli("list")
        self.assertIn("whatsapp", listed)
        self.assertIn("Zulip", listed)
        self.assertEqual(
            self.run_cli("class", "https://web.whatsapp.com/", "WhatsApp").strip(),
            "chrome-web.whatsapp.com__-WhatsApp",
        )


if __name__ == "__main__":
    unittest.main()
