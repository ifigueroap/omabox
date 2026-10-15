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
        omabox.cmd_config("dock", "special-only")
        self.assertEqual(omabox.settings_file().read_text(encoding="utf-8").strip(), 'dock = "special-only"')
        self.assertEqual(omabox.load_dock_mode(), "special-only")
        listed = json.loads(subprocess.check_output(
            [sys.executable, str(ROOT / "lib" / "omabox.py"), "list", "--json"],
            text=True,
        ))
        self.assertEqual(listed["dock"], "special-only")
        with self.assertRaises(SystemExit):
            omabox.cmd_config("dock", "sometimes")
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
