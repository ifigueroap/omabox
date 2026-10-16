# Omabox

Rambox-like web-app dock for [Omarchy](https://github.com/basecamp/omarchy) 4
("Quattro"). One Chromium process, one profile per service, every service
window on the Hyprland special workspace `omabox`.

Omarchy 4 runs the bar, launcher, notifications, OSDs, and lock screen as
plugins in one Quickshell process. Omabox is a third-party `panel` and
`bar-widget` plugin (`keepLoaded: true`) plus an `omabox` command.

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

The dock is a layer-shell panel, a pill of service icons plus a `+` button. The default edge is the right side, a vertical pill. `edge = "left"` stays vertical. `top` and `bottom` lay the icons in one horizontal row. It appears when the plugin is enabled and the shell has loaded `Panel.qml`. Theme colors come from `qs.Commons` `Color` and `Style`, which the shell updates when the theme changes (`docs/omarchy-shell.md`, `docs/theming.md`).

On a regular workspace the dock stays a short notch on that edge, drawn at 35% opacity until the pointer is over it. Moving the pointer onto the notch expands the full pill and brings it to full opacity; leaving it fades the dock and collapses the notch again after 400ms. On special workspace `omabox` the pill stays open, opaque, and reserves its thickness. `pinned = true` keeps that full opaque pill on regular workspaces too. It does not override `dock = "special-only"`, which still hides the dock everywhere except that workspace. The defaults are `dock = "always"`, `edge = "right"`, and `pinned = false`.

A bar button on the right of the Omarchy bar runs `omabox toggle`, the same action as `Super+Shift+O`. It is a `bar-widget` (`BarWidget.qml`, `defaultSection: "right"`), not a tray-drawer entry, so it stays visible without opening the tray (`docs/omarchy-shell.md`). The widget is a plain `Item` with `triggerPress`: `qs.Ui.BarWidget` and `qs.Ui.WidgetButton` are types the shell does not expose to `~/.config/omarchy/plugins/`.

Enabling a plugin that declares `bar-widget` writes a `bar.layout` entry and does not also append `plugins[]` (`shell/services/PluginRegistry.qml` `setEnabled`). A checkout that was enabled earlier already has `omabox` in `plugins[]`. `omarchy bar put` leaves that entry where it is and does not add a second one, so the button never appears. Disable and enable again after the shell has loaded this manifest:

```bash
omarchy plugin disable omabox
omarchy plugin enable omabox
```

That records `omabox` in `bar.layout.right`. The panel still loads, because `isEnabled` is true for either a bar slot or a `plugins[]` row.

After a later `git pull` in the plugin checkout, restart the shell so it loads new QML. Saving a file under `~/.config/omarchy/plugins/` also reloads plugin code; a type error on the previous load still needs a restart. Hyprland binds live in the generated file `~/.config/hypr/omabox.lua`, which a pull does not rewrite. Run `omabox setup` again after a pull that changes keybinds or window rules, then check the config:

```bash
git -C ~/.config/omarchy/plugins/omabox fetch origin
git -C ~/.config/omarchy/plugins/omabox checkout cursor/omabox-dock-layout-34c0
git -C ~/.config/omarchy/plugins/omabox pull origin cursor/omabox-dock-layout-34c0
~/.config/omarchy/plugins/omabox/bin/omabox setup
hyprctl configerrors
omarchy restart shell
omarchy plugin disable omabox
omarchy plugin enable omabox
omarchy-shell omabox dashboard
omabox config
```

`omabox dashboard` prints `ok` and opens the service dashboard when the panel is mounted. `Target not found.` means `Panel.qml` did not load, so no `omabox` IPC target was registered. `omarchy-restart-shell` is the same restart. A CLI-only change (launch, focus, toggle) is picked up through the `~/.local/bin/omabox` symlink without a shell restart. `omabox config` prints `dock=always`, `edge=right`, `pinned=false`, and `dnd=false` until you change them.

## Keys

| Keys | Action |
| --- | --- |
| `Super+Shift+O` | Toggle the `omabox` special workspace. This replaces Obsidian |
| `Super+Alt+1` … `9` | Focus the service whose `key` is that digit, or launch it |

`Super+O` is Omarchy's "Pop window out" bind (`default/hypr/bindings/tiling.lua`). `Super+Shift+O` launches Obsidian while preinstalled binds are enabled (`default/hypr/bindings/applications.lua`). The generated file uses `o.rebind`, so that chord toggles Omabox and no longer opens Obsidian. List binds with `omarchy menu keybindings --print`.

Those binds live in `~/.config/hypr/omabox.lua`, using the same `o.bind` helper as `~/.config/hypr/bindings.lua` (`code:10` is the key `1`). Digit keys follow the `key` field, not the order in the file. If two services share a key, the earlier one wins and `omabox add` says so.

To use a different toggle chord, edit the `o.rebind("SUPER + SHIFT + O", ...)` line in `~/.config/hypr/omabox.lua`. `o.rebind` removes the previous action first. A chord that is already bound, such as Obsidian on `Super+Shift+O`, has to use `o.rebind` rather than `o.bind`.

```lua
o.rebind("SUPER + ALT + O", "Omabox", "omabox toggle")
```

Then validate:

```bash
hyprctl reload
hyprctl configerrors
```

`omabox setup`, `omabox add`, and `omabox remove` rewrite `omabox.lua`, so put the custom chord back after those commands.

Right-click a service icon, or press and hold it, to open a small menu with **Sound** and **Badges**. Sound off mutes that service. Badges off hides its unread count and the urgent dot. The last control on the pill, after `+`, is **Do not disturb**. It turns sounds and badges off for every service, whatever each service has saved, until you turn it off. The dock stays the same edge pill; the menu opens inward from the icon.

Click a dock icon, or the bar button, to focus or launch that one service. The window rule parks new apps on special workspace `omabox` without showing it (`workspace` may end with ` silent` in the [Hyprland window rules](https://wiki.hypr.land/Configuring/Basics/Window-Rules/)). The click then leaves only that service on `special:omabox`: other Omabox windows move to `special:omabox-hidden`, a second window of the same class is closed, and the remaining window is focused with `hl.dsp.focus`. An empty special workspace does not stay open, which is why toggling it before Chromium maps looks like a click that did nothing. The `+` button opens the dashboard (also `omabox dashboard`, or the menu row "Omabox services").

If a window of that class is already mapped, `omabox focus` and `omabox launch` show it and do not start Chromium again. A second `--app` launch is what opens another WhatsApp window and the "open in another window" dialog. When none is mapped, Omabox launches once. A `hyprctl` client list that is empty or unreadable does not count as "no window": Omabox exits without launching, so a failed `hyprctl` cannot open another Chromium. The shared `--user-data-dir` is left running.

Quattro's `hyprctl dispatch` runs Lua, the same shape as Omarchy's scratchpad binds. Keyword dispatchers (`togglespecialworkspace`, `focuswindow`, `movetoworkspacesilent`) fail with `')' expected near 'omabox'`. Omabox calls:

```bash
hyprctl dispatch 'hl.dsp.workspace.toggle_special("omabox")'
hyprctl dispatch 'hl.dsp.window.move({ workspace = "special:omabox", follow = false, window = "class:chrome-web.whatsapp.com__-WhatsApp" })'
hyprctl dispatch 'hl.dsp.focus({ window = "class:chrome-web.whatsapp.com__-WhatsApp" })'
```

```bash
omabox launch whatsapp --print   # browser and flags, no window
omabox toggle --print            # Lua hyprctl dispatch
omabox focus whatsapp --print    # move, toggle, and focus commands
omabox launch whatsapp           # start it, or show it, on the omabox workspace
```

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
| `sound` | `true` (default) or `false`. `false` mutes that service. Omitted on older files, which stay unmuted |
| `badges` | `true` (default) or `false`. `false` hides the unread badge and urgent dot. Omitted on older files, which keep badges |

Presets: WhatsApp, Slack, Discord, Zulip (URL left blank), Telegram, Grok, ChatGPT, Claude, Grok Bot (`https://x.com/i/grok`).

```bash
omabox list
omabox add zulip --url https://your-org.zulipchat.com --update
omabox add --name "Work Slack" --url https://app.slack.com/ --profile "Work Slack" --key 2
omabox remove work-slack
omabox fetch-icons          # favicon cache for services without a bundled icon
```

`add` and `remove` rewrite `~/.config/hypr/omabox.lua` when setup has been run. Reload Hyprland (`hyprctl reload`) so new window rules load. `hypr.` modules are cleared on each config load (`default/hypr/bootstrap.lua`).

Dock visibility is a separate file, `~/.config/omabox/config.toml`, so rewriting `services.toml` does not drop it:

```toml
dock = "always"
edge = "right"
pinned = false
dnd = false
```

| Key | Values | Meaning |
| --- | --- | --- |
| `dock` | `always` (default), `special-only` | `always`: notch on regular workspaces, full pill on `special:omabox` and while the pointer is over the notch. `special-only`: full pill only while `special:omabox` is active |
| `edge` | `left`, `right` (default), `top`, `bottom` | Which screen edge holds the dock. Left and right are a vertical pill. Top and bottom are a horizontal row |
| `pinned` | `true`, `false` (default) | `true` keeps the pill fully open and opaque. `false` is the notch that expands on hover. Pin does not show the dock on other workspaces when `dock` is `special-only` |
| `dnd` | `true`, `false` (default) | Do not disturb. `true` turns sounds and badges off for every service. Per-service `sound` and `badges` stay as they are and apply again when this is `false`. `do_not_disturb` is accepted as the same setting |

While the pointer is off the dock, and the dock is neither pinned nor held open by `special:omabox`, the notch is drawn at 35% opacity using the same `Color` and `Style` values. Hover, pin, and that workspace use opacity 1.

```bash
omabox config                         # dock=always / edge=right / pinned=false / dnd=false
omabox config dock                    # always
omabox config dock special-only
omabox config edge bottom
omabox config pinned true
omabox config pinned false
omabox config dnd true
omabox service whatsapp sound false
omabox service whatsapp badges false
omabox service whatsapp sound         # prints true or false
```

`omabox list --json` includes `"dock"`, `"edge"`, `"pinned"`, and `"dnd"`. Each service includes `"sound"`, `"badges"`, `"soundEffective"`, and `"badgesEffective"`. The effective flags are false while Do not disturb is on. The dashboard chips call `omabox config dock`, `omabox config edge`, `omabox config pinned`, and `omabox config dnd`. Service rows call `omabox service <id> sound|badges true|false`. An unknown value is rejected. A missing or unreadable file uses the defaults above. Saving one key rewrites `config.toml` with `dock`, `edge`, `pinned`, and `dnd`, and keeps any other flat string, boolean, or integer keys already in the file. Changing Do not disturb does not rewrite `services.toml`. `omabox add --update` keeps a service's `sound`, `badges`, and any other flat keys on that block. `omabox init` still copies presets only when `services.toml` is missing, so an upgrade does not replace services you already have. `omabox uninstall --purge` deletes `~/.config/omabox`, including `config.toml`.

Sound and badges are best-effort on Wayland. Profiles share one Chromium process, so the launcher does not pass `--mute-audio` (that would silence every service). After a window is shown, and whenever a flag changes, Omabox asks PipeWire (`wpctl`) or Pulse (`pactl`) to mute output streams whose process is the Omabox Chromium and whose media name matches the service. Do not disturb mutes every stream from that process. Streams that are not Omabox are left alone. Notification badges in the dock follow `badges` and `dnd` immediately. Chromium's own notifications are a profile preference (`default_content_setting_values.notifications`) written only when that profile's `Preferences` file already exists, is valid JSON, and the Omabox Chromium is not running. Otherwise the file is left alone and the Omabox flag is still saved. The launcher applies that preference before it starts the browser.

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

Window rules use `o.window` with `workspace = "special:omabox silent"`. That helper sets `match.class` and passes the table to `hl.window_rule` (`default/hypr/helpers.lua`). The Hyprland wiki's `workspace` effect accepts a trailing ` silent`, the same form as Omarchy's screensaver rule in `default/hypr/apps/system.lua`, so a new service does not steal the current workspace. `omabox focus` moves the window onto that workspace with `hl.dsp.window.move`, shows it with `hl.dsp.workspace.toggle_special("omabox")`, and focuses it with `hl.dsp.focus`.

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
- Bar: `kinds` includes `bar-widget` with `entryPoints.barWidget` and `barWidget.defaultSection` `right` (`docs/omarchy-shell.md`, `bin/omarchy-plugin-validate`, `default/agents/skills/omarchy/plugins.md`). `tray` only draws inside the tray drawer. Third-party widgets receive `PluginBarApi` (`shell/Ui/PluginBarApi.qml`); `bar.run("omabox toggle")` is the click. `BarWidget` / `WidgetButton` in `qs.Ui` are types, same limit as `ShellIpc`, so the entry point does not instantiate them. The bar calls `triggerPress` on the widget item (`shell/Ui/Bar.qml`).
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
- The dashboard edits services by shelling out to `omabox`. It does not edit the TOML file from QML. Dock mode, edge, pin, Do not disturb, and per-service sound and badges use the same path (`omabox config …`, `omabox service …`).
- Per-service mute follows the Chromium stream's media name. A stream whose name does not contain the service name, profile, or id stays audible until Do not disturb mutes the whole Omabox browser. Turning Do not disturb off unmutes those streams again.
- Whether `special:omabox` is showing is read from `Hyprland.focusedWorkspace` and the focused monitor's `specialWorkspace` / `activeWorkspace` names. A compositor that reports the special workspace under a different field would leave the notch up while Omabox is open.
- `fetch-icons` uses Google's favicon service and accepts only a PNG response.

## What is not tested

This repo's CI runs shellcheck, qmllint (syntax only; Quickshell is not installed, so import and required-property checks are disabled), and unit tests for config, the window class (including a line-for-line check against Omarchy's `Default` formula), launch/focus command lines, and setup/uninstall file edits.

Not run, because there is no Omarchy desktop here:

- Quickshell loading the panel or the bar widget, live theme updates, layer-shell anchors on each edge, notch hover, idle opacity, or `ShellIpc`
- A real Chromium `--app` window and its Hyprland `class`
- `windowtitlev2` / `urgent` delivery into the badge
- `hyprctl dispatch` or `hyprctl reload` against a running compositor (tests check the Lua strings with a fake `hyprctl`)
- `omarchy plugin add` / `omarchy bar put` against a running shell (placement follows `PluginRegistry.setEnabled` in the quattro tree)
- The dashboard chips in a real shell (there is no browser UI to click; the chips call `omabox config` and `omabox service`)
- A live right-click or long-press on the dock (the menu items and the Do not disturb override are covered by `logic.js` and the Python flag tests; qmllint only checks syntax)
- `wpctl` / `pactl` against a running PipeWire session (tests feed fixture node lists and do not mute a real stream)
