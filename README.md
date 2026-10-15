# Omabox

Rambox-like web-app dock for [Omarchy](https://github.com/basecamp/omarchy) 4
("Quattro"). One Chromium process, one profile per service, every service
window on the Hyprland special workspace `omabox`.

Omarchy 4 runs the bar, launcher, notifications, OSDs, and lock screen as
plugins in one Quickshell process. Omabox is a third-party `panel` plugin
(`keepLoaded: true`) plus a `omabox` command.

## Install

`omarchy plugin add` only clones and validates. It never runs plugin code
(`bin/omarchy-plugin-add` in Omarchy). Keybindings are a second step, because
Hyprland config is your `~/.config/hypr` and Omarchy will not edit it for a
plugin.

```bash
omarchy plugin add https://github.com/ifigueroap/omabox --enable --yes
~/.config/omarchy/plugins/omabox/bin/omabox setup --menu
```

`setup` is idempotent. It:

- copies `presets/services.toml` to `~/.config/omabox/services.toml` if you do not have one yet
- writes `~/.config/hypr/omabox.lua` (`o.bind` / `o.window`) and a marked `require("hypr.omabox")` in `~/.config/hypr/bindings.lua`
- symlinks `~/.local/bin/omabox` (this is on PATH for a normal Omarchy login)
- with `--menu`, adds an `omabox` row to `~/.config/omarchy/extensions/omarchy-menu.jsonc`
- reloads Hyprland when `hyprctl` is available

Skip the menu row with `omabox setup` and no `--menu`. Enable the plugin later with `omarchy plugin enable omabox`.

The dock is a layer-shell panel on the right edge of the screen, a vertical pill of service icons plus a `+` button. It appears when the plugin is enabled and the shell has loaded `Panel.qml`. Theme colors come from `qs.Commons` `Color` and `Style`, which the shell updates when the theme changes (`docs/omarchy-shell.md`, `docs/theming.md`).

After a later `git pull` in the plugin checkout, restart the shell so it loads the new QML. Saving a file under `~/.config/omarchy/plugins/` also reloads plugin code; a type error on the previous load still needs a restart:

```bash
git -C ~/.config/omarchy/plugins/omabox pull
omarchy restart shell
omarchy-shell omabox dashboard
```

`omabox dashboard` prints `ok` and opens the service dashboard when the panel is mounted. `Target not found.` means `Panel.qml` did not load, so no `omabox` IPC target was registered. `omarchy-restart-shell` is the same restart.

## Keys

| Keys | Action |
| --- | --- |
| `Super+O` | Toggle the `omabox` special workspace |
| `Super+Alt+1` … `9` | Focus the service whose `key` is that digit, or launch it |

Those binds live in the generated Lua, using the same `o.bind` helper as `~/.config/hypr/bindings.lua` and `default/hypr/bindings/tiling.lua` (`code:10` is the key `1`). Digit keys follow the `key` field, not the order in the file. If two services share a key, the earlier one wins and `omabox add` says so.

Click a dock icon to focus or launch. The `+` button opens the dashboard (also `omabox dashboard`, or the menu row "Omabox services").

## Config

`~/.config/omabox/services.toml`:

```toml
[[service]]
id = "whatsapp"
name = "WhatsApp"
url = "https://web.whatsapp.com/"
icon = ""
profile = "WhatsApp"
key = "1"
unread = "^\\((\\d+)\\)"
```

| Field | Meaning |
| --- | --- |
| `id` | Stable id (`omabox focus whatsapp`) |
| `name` | Label in the dock |
| `url` | `http` or `https` page opened with `--app`. Zulip ships with an empty URL until you set yours |
| `icon` | Optional file. Empty uses `icons/<id>.svg`, then a cached favicon |
| `profile` | Chromium `--profile-directory` (no slashes). Spaces are allowed |
| `key` | `1`–`9` for `Super+Alt+<key>`, or empty |
| `unread` | JavaScript/Python regex. The first capture group is the badge count. Default `^\((\d+)\)` matches titles like `(3) WhatsApp` |

Presets: WhatsApp, Slack, Discord, Zulip (URL left blank), Telegram, Grok, ChatGPT, Claude, Grok Bot (`https://x.com/i/grok`).

```bash
omabox list
omabox add zulip --url https://your-org.zulipchat.com --update
omabox add --name "Work Slack" --url https://app.slack.com/ --profile "Work Slack" --key 2
omabox remove work-slack
omabox fetch-icons          # favicon cache for services without a bundled icon
```

`add` and `remove` rewrite `~/.config/hypr/omabox.lua` when setup has been run. Reload Hyprland (`hyprctl reload`) so new window rules load. `hypr.` modules are cleared on each config load (`default/hypr/bootstrap.lua`).

## How windows are launched and matched

Every service uses one shared data directory and its own profile:

```text
chromium --user-data-dir=$HOME/.local/share/omabox/chromium \
  --profile-directory=<profile> --app=<url>
```

The browser binary is chosen the same way as `bin/omarchy-launch-webapp` (default Chromium-family desktop, otherwise `chromium`). Launch goes through `uwsm-app` when that exists, else `setsid`. Omabox does **not** call `omarchy-cmd-browser-handoff`, because that would open the URL in the default profile.

Chromium's Wayland app id (what Hyprland reports as `class`) is:

```text
chrome-<host>_<path>-<profile>
```

with `/` and spaces replaced by `_`. For a path of `/` that is `chrome-<host>__-<profile>`.

That is `web_app::GenerateApplicationNameFromURL` (`host + "_" + path`) plus `GetShortcutFileName` (`chrome-` + that name + `-` + profile basename) in Chromium. Omarchy already special-cases profile `Default` in `bin/omarchy-webapp-window-class`. `omabox class` matches that script for `Default` and uses the profile name otherwise. A space in `--profile-directory=Profile 1` stays a space in the flag and becomes `Profile_1` in the class.

Window rules use `o.window` with `workspace = "special:omabox silent"`, so a new service does not steal the current workspace. `omabox focus` moves the window onto that workspace, shows it, and focuses it.

Unread badges read Hyprland `windowtitlev2` titles (`(3) …`). An `urgent` event with no parsed count draws a dot instead, cleared on `activewindowv2`.

## Uninstall

```bash
omabox uninstall          # binds, rules, menu rows, ~/.local/bin/omabox
omabox uninstall --purge  # also ~/.config/omabox and ~/.local/share/omabox (profiles)
omarchy plugin remove omabox --yes
```

Run `omabox uninstall` before `omarchy plugin remove`. Plugin remove deletes the checkout and does not run an uninstall hook.

## Plugin API this follows

Checked against `basecamp/omarchy` branch `quattro` (the default branch):

- Manifest: `docs/omarchy-shell.md`, `manual/32-shell-plugins.md`, `bin/omarchy-plugin-validate`, `shell/services/PluginRegistry.qml`
- Enablement: third-party plugins turn on by appearing in `plugins[]` (`omarchy plugin enable`). `shell.json` has no per-plugin config object
- Loading: `keepLoaded` panels mount at startup in `shell/shell.qml`; entry points are `Item`s and receive `omarchyPath`, `shell`, `manifest`
- IPC: target `omabox` (`dashboard`, `reload`). First-party code uses the `ShellIpc` type from `shell/Commons/ShellIpc.qml`. That type is not visible to a file loaded from `~/.config/omarchy/plugins/`, so Omabox uses `IpcHandler` (`Quickshell.Io`) plus the `IpcRegistry` singleton, which is what `ShellIpc.qml` does internally. `Style`, `Util`, and `Color` are singletons and stay available.
- Colors: `import qs.Commons as Commons` and `Commons.Color` / `Style` (`docs/omarchy-shell.md`, `shell/Commons/Color.qml`, `docs/theming.md`)
- Menu rows: `docs/menu.md`, `~/.config/omarchy/extensions/omarchy-menu.jsonc`
- Hyprland: `o.bind` / `o.window` from `default/hypr/helpers.lua`, user binds in `~/.config/hypr/bindings.lua`, module path in `default/hypr/bootstrap.lua`

## Icons

WhatsApp, Discord, Zulip, Telegram, Claude, and the X mark used for Grok Bot are from [Simple Icons](https://github.com/simple-icons/simple-icons) (CC0). Slack, ChatGPT, and Grok are original monograms. See `icons/NOTICE.md`.

## Limitations

- Profiles share one Chromium process. Cookies are per profile; a browser bug in that process is shared. This is not an OS sandbox per service.
- Wayland ignores Chromium's `--class`. The class above is the one Hyprland actually sees. X11 is not the Omarchy session.
- A URL whose path is not `/` does not get a double underscore. Discord is `chrome-discord.com__app-Discord`. The dock computes the class from the URL; it does not assume every service is `__`.
- Zulip does nothing until it has an `https` URL.
- `unread` only sees titles Chromium puts on the window. Sites that show a count only inside the page stay at the urgent-dot fallback.
- The dashboard edits services by shelling out to `omabox`. It does not edit the TOML file from QML.
- `fetch-icons` uses Google's favicon service and accepts only a PNG response.

## What is not tested

This repo's CI runs shellcheck, qmllint (syntax only; Quickshell is not installed, so import and required-property checks are disabled), and unit tests for config, the window class (including a line-for-line check against Omarchy's `Default` formula), launch/focus command lines, and setup/uninstall file edits.

Not run, because there is no Omarchy desktop here:

- Quickshell loading the panel, live theme updates, layer-shell anchors, or `ShellIpc`
- A real Chromium `--app` window and its Hyprland `class`
- `windowtitlev2` / `urgent` delivery into the badge
- `uwsm-app`, `hyprctl dispatch`, or `hyprctl reload` against a compositor
- `omarchy plugin add` itself (the manifest is checked against the same rules as `omarchy-plugin-validate`)
