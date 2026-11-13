NOTE: This is a first attempt at using a second hand kindle (£30 on ebay) as a smarthome surface. This might be a super stupid way of doing it, I couldn't ssh into the Kindle or get python on it, so this is very hacky! However this won't need charging for months, and functions as a way of having my raspberry pi serve me some data while I'm brushing my teeth, might adapt this to have it be a surface that lets me know if any agents did any work overnight....

# Kindle Bathroom Dashboard

Turns a jailbroken Kindle into a wall-mounted, always-on dashboard with a couple of tappable buttons for quick daily logging (built around weight + a 0.5–5 star mood rating, but adaptable to whatever stats you'd want to track). Built on a Kindle Paperwhite 3 (7th gen); the approach should generalize to other Kindles, but the exact jailbreak tool and a couple of settings-file details are firmware/model specific — see below.

**What it does:** a Flask server on your own always-on machine renders a
small landscape chart (weight trend + mood trend, last 4 weeks, plus a
"sleep debt" figure pulled from [intervals.icu](https://intervals.icu) if
you use it) and serves it over the internet via a token-protected URL. A
KOReader plugin on the Kindle shows that chart as its live background
with two corner buttons — tap one, log a value, and the chart (and the
Kindle's own screensaver) updates immediately. No periodic polling, no
background wake cycles — purely event-driven off you actually tapping a
button, which keeps battery use sane on a device you can't easily keep
plugged in.

## Before you start: jailbreak your Kindle

This repo doesn't jailbreak anything — that part is firmware-version
specific, well documented elsewhere, and changes faster than this README
would stay accurate. Use **[kindlemodding.org](https://kindlemodding.org/)**,
specifically:

1. **[The jailbreak wizard](https://kindlemodding.org/jailbreak-wizard.html)** —
   tells you which tool (WinterBreak, WinterBreak2, AdBreak, Nosebleed,
   SpringBreak, Sanctuary — they're all firmware-version gated, not
   model-gated) actually applies to your exact device. Don't guess from
   your Kindle's model name alone.
2. Once jailbroken, install **[KOReader](https://github.com/koreader/koreader)**
   via KPM (`;kpm update` then `;kpm install koreader` in the home-screen
   search bar) — this is the plugin platform the Kindle-side code here
   targets. The **[KPM docs](https://kindlemodding.org/kindle-dev/kpm/index.html)**
   and **["What's next" post-jailbreak guide](https://kindlemodding.org/jailbreaking/whats-next/index.html)**
   cover this well.
3. Optionally install `kterm` the same way, for an on-device terminal —
   useful for debugging, not required for normal operation.

A couple of things that genuinely tripped me up, documented in more
depth in [`NOTES_FOR_DEVELOPERS.md`](NOTES_FOR_DEVELOPERS.md): KUAL is
obsolete on the modern jailbreak stack, there's no Python available (this
is all Lua, via KOReader), and a plugin's `ButtonTable` should use a
single flat row of buttons rather than a nested multi-row layout, which
didn't render reliably in testing.

## Repo layout

```
server/
  app.py                          Flask routes (bearer-token protected)
  render.py                       Chart rendering (matplotlib)
  config.example.json             Copy to ~/.config/kindle_dashboard/config.json
  intervals-icu-config.example.json   Optional, only if you want the sleep-debt figure
koreader_plugin/
  bathdash.koplugin/main.lua      The Kindle-side plugin
```

## Setup

### 1. The server (on any always-on machine — a Raspberry Pi, a home server, etc.)

```bash
python3 -m venv venv && source venv/bin/activate
pip install flask matplotlib numpy requests
mkdir -p ~/.config/kindle_dashboard
cp server/config.example.json ~/.config/kindle_dashboard/config.json
# edit it: generate a real token with
#   python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

If you want the sleep-debt figure (optional — remove the relevant block
in `render.py` if you don't use intervals.icu):

```bash
mkdir -p ~/.config/intervals-icu
cp server/intervals-icu-config.example.json ~/.config/intervals-icu/config.json
# fill in your athlete_id and API key (intervals.icu -> Settings -> Developer Settings)
```

Run it:

```bash
python3 server/app.py
```

For anything beyond a quick test, run it as a systemd user service
(`Restart=always`) so it survives reboots.

### 2. Making the server reachable from the Kindle

The Kindle has no VPN client of its own, and your server's network/IP may
not be stable or on the same LAN as the Kindle. The clean fix here was
**[Tailscale](https://tailscale.com/) Funnel**: install Tailscale on the
server, then

```bash
tailscale funnel --bg 8765   # or whatever port your config.json uses
tailscale funnel status      # prints your public https://<name>.<tailnet>.ts.net URL
```

This exposes that port at a stable public HTTPS URL — the Kindle just
does a normal `curl`/`https.request()` to it, nothing Tailscale-specific
needed on the Kindle side. **Once you do this the URL itself is public**
(Funnel's TLS certs are logged in Certificate Transparency logs, so the
hostname isn't secret) — the bearer token in your config is the actual
security boundary, make it long and random.

### 3. The Kindle plugin

Copy `koreader_plugin/bathdash.koplugin/` to `/mnt/us/koreader/plugins/`
on the Kindle (it mounts as a plain USB drive). Edit the top of
`main.lua`:

```lua
local SERVER = "https://YOUR-DEVICE.YOUR-TAILNET.ts.net"
local TOKEN = "the same token you put in config.json"
local SCREENSAVER_PATH = "/mnt/us/screensaver_test/screensaver_test.png"
```

Then, **on the Kindle, in KOReader's Screensaver menu** (gear icon ->
Screensaver -> "Show custom image or cover on sleep screen"), point it at
that same path. Two more settings worth checking directly in
`/mnt/us/koreader/settings.reader.lua` if your screensaver ends up the
wrong orientation or has a "Sleeping" overlay you don't want:

- `screensaver_rotate_auto_for_best_fit` — set `true` if your rendered
  image doesn't match your panel's native orientation.
- `screensaver_show_message` — set `false` to remove the "Sleeping" text
  KOReader draws over every sleep screen by default, regardless of
  screensaver type.

Open the plugin from KOReader's menu -> "Bathroom Dashboard". It is
**deliberately not auto-launched on startup** — an earlier version of
this did that with no close button and genuinely trapped the device,
requiring a power cycle. If you re-add auto-launch, make sure a tested
close button exists first.

## Customizing

The two tracked things (weight + mood) are just an example. The real
reusable pieces are:
- the token-auth + Tailscale Funnel pattern for reaching a jailbroken
  device with no network of its own,
- the "render a PNG server-side, push it to both the KOReader screensaver
  and the live app background" trick, which sidesteps doing any heavy
  rendering (charts, images) on the Kindle itself,
- the fullscreen `ImageWidget` + corner-anchored `Button`s layout in
  `main.lua`, which is a reasonable starting point for any "background +
  a couple of buttons" KOReader app.

Swap `/weight` and `/mood` for whatever two things you actually want to
log, and adjust `render.py`'s chart accordingly.

## License

MIT — see [LICENSE](LICENSE).
