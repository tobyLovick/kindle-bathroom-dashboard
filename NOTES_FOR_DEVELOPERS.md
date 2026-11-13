# Notes on jailbroken-Kindle app development

Lessons from building the bathroom dashboard (`kindle_bathroom_dashboard/`) — generalizable to any future Kindle-jailbreak project, not specific to that one.

## Jailbreaking itself

- **The jailbreak method is gated by firmware version, not model name.** "Paperwhite 3" doesn't tell you which tool applies — different firmware ranges on the *same* model need different tools (WinterBreak / WinterBreak2 / AdBreak / Nosebleed / SpringBreak / Sanctuary as of late 2026). Use kindlemodding.org's jailbreak wizard (needs serial + firmware version) rather than guessing from docs — it got this right when a documentation-based guess would have picked the wrong tool.
- Newest devices (Scribe 3rd gen, Colorsoft, as of this writing) may have **no public jailbreak at all** — check before assuming any Kindle is jailbreakable.
- A jailbreak payload that's "just a webpage" (e.g. WinterBreak2's `dialoger.html`) works by calling the Kindle's internal `nativeBridge` JS API from the Experimental Browser — worth actually reading a small payload before trusting it, which is easy since these are typically a few hundred bytes.
- **KUAL is obsolete** on the modern `kindlemodding.org` / `hdnext` / KPM jailbreak stack. Don't bother looking for it; it genuinely doesn't work on this ecosystem.
- Not every homebrew tool works regardless of firmware even once jailbroken — e.g. `Jobman` (SSH access) requires firmware ≥5.16.3; a device just below that will fail to install it. Check `;kpm update` / `;kpm install <name>` catalog contents rather than assuming a package exists (there's no Python package in this ecosystem at all, for instance — cross-compiling one yourself is a multi-day embedded-toolchain project, not worth it for most use cases).

## Scriptlets vs KOReader plugins — pick based on what you actually need

- **Scriptlets** (`.sh` files dropped in `/mnt/us/documents/`, indexed as "books," run on tap): good for one-shot triggered actions, zero typing on-device once deployed. stdout/stderr pipe to `fbink` by default (`# DontUseFBInk` to suppress). Library indexing can lag or just not show an icon — if it's stuck, you can bypass the icon entirely and run the same command directly via the home-screen search bar (`;kpm launch <name>`, or whatever the Scriptlet's last line actually does).
- **KOReader Lua plugins** (`.koplugin/main.lua`): the real option for anything interactive — custom screens, buttons, numeric input, persistent state across sleep/wake. No Python needed; KOReader bundles Lua + LuaSocket/LuaSec + its own widget toolkit.
- Getting a real on-device shell (`kterm`) is possible without `Jobman`/SSH and doesn't need registration or firmware ≥5.16.3 — a decent fallback for diagnostics even when SSH-based tools won't install.

## KOReader plugin development — what's actually confirmed to work

Verified directly against real KOReader source during this project (worth re-checking against your specific build before trusting, since paths can differ by version):

- `require("ui/widget/container/widgetcontainer")`, `require("ui/uimanager")`, `require("device").screen` (`Screen:getWidth()/getHeight()`).
- `ButtonTable` — **a single flat row of buttons works reliably; a nested multi-row structure (`{row1, row2}`) silently only rendered the last row in practice.** If you want multiple logical groups of buttons, append them into one row rather than nesting rows, at least until you've independently confirmed multi-row works on your build.
- `InputDialog` with `input_type = "number"`, read back via `getInputValue()` — has its own numeric keyboard, don't build one yourself.
- `ImageWidget` (`file = path, width=, height=`) + `OverlapGroup` (layer widgets on top of each other) + `BottomContainer`/`LeftContainer`/`RightContainer` (corner-anchor a widget within a `dimen`) is the combination for "fullscreen background image with buttons pinned to specific corners" — much better than a floating modal over whatever was on screen before.
- **`UIManager:show(widget)` without a refresh-type argument may not actually become visible until the next full e-ink refresh happens for some other reason** (e.g. a later sleep/wake). Pass `UIManager:show(widget, "full")` for anything the user needs to see immediately.
- **Always ship a tested, working close/cancel button on every custom screen before ever auto-launching anything on KOReader startup.** A fullscreen widget with no escape path genuinely trapped the device once during this project (had to power-cycle) — don't risk this even for "just testing."

## Networking

- Embedded `curl`/`wget` on a Kindle this old can still do modern TLS fine (confirmed against a real Let's Encrypt-issued cert) — don't assume ancient cert stores are a blocker without testing; it was a non-issue here.
- **Tailscale Funnel** is the right pattern when a jailbroken device with no VPN client of its own needs to reach a service that lives on a machine with an unstable/roaming IP (e.g. a laptop on eduroam). It exposes a stable public HTTPS URL; the Kindle just does normal `curl`/`https.request()` to it, no Tailscale client needed on the Kindle side. Once you do this, **the URL itself is not secret** (Funnel's certs are logged publicly in CT logs) — a real bearer-token check on every route is the actual security boundary, not obscurity.

## Device ground truth > guessing

- Get real hardware facts from the device itself where possible rather than trusting external docs or heuristics. `fbink -v` (it's at `/mnt/us/libkh/bin/fbink` if not on `$PATH`) gives the true panel resolution. **`/sys/class/graphics/fb0/virtual_size` is NOT the real panel size** — it's a multi-buffer framebuffer allocation and can report physically nonsensical numbers (seen a 1088x6144 "resolution" that was nothing like the real 1072x1448 panel).
- When the device is mounted as plain USB mass storage, you can directly read/edit its actual config files (e.g. `settings.reader.lua`) rather than only going through on-device menus — useful for finding settings with no obvious menu toggle. Two screensaver behaviors that mattered here, both independent of `screensaver_type`: `screensaver_rotate_auto_for_best_fit` (auto-rotates an image to fit the panel orientation) and `screensaver_show_message` (the global "Sleeping" text overlay, on by default).
- Ejecting a Kindle from the host side makes the device exit USB-drive mode entirely — the block device goes empty (0 bytes), and it can't be remounted without physically replugging the cable. Don't expect to "resume" a USB session after an eject.

## Working with someone who's physically typing on the device

- The Kindle's on-screen keyboard is genuinely painful to use for anything beyond a few characters. Minimize round-trips that require typing: build a Scriptlet/shortcut for any command that'll be run more than once, and prefer tap-driven flows over anything requiring real text entry wherever the task allows it.
