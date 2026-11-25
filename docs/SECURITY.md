# Security and privacy

**What it can see.** To react to keys, LumiRipple reads key events of all real keyboards. It keeps the position of running waves
(seconds), which keys are held, and the last key presses for 2 seconds. It writes no key log.

**Typing effects** keep more, in memory only and never on disk: the heat map counts presses per key (the count halves after the
time you set, at most 30 minutes), the trail remembers when each key was last pressed (at most 20 seconds). Their colors show in
the keyboard preview on the settings page, so whoever can open that page (anyone with the token) can see roughly which keys were
used often or just now. Switch these effects off if that matters to you.

**Macros are the exception.** Between *Record* and *Stop* (at most 60 s) key presses are kept and, if you save, stored unencrypted in
the settings file (readable only by the service). Never record passwords. The settings page never gets macro contents back, only
the names of the last and next key while one is playing.

**Linux.** The key-reading service runs as a temporary user with the group `input`, may reach only localhost, cannot see your home
folder, and runs code owned by root, so other programs of your account cannot change it. It can type through `/dev/uinput`.
**Windows and macOS.** There is no such separation: it runs as you, like any program with key access.

**Settings page.** Listens on 127.0.0.1 only. Every command needs a random token from a file only you can read. The browser gets it
after the `#` of the address (never sent over the network) and adds it to each request itself. There are no cookies, so other web
sites cannot act in your name; `Host` and `Origin` are checked against DNS rebinding. Programs running under your account can read
the token, as they can read your other files. They could start a recording, but Escape blinks meanwhile and the content cannot be
read back through the page.

**Sound.** Converted to 16 levels in memory, never stored or sent. The microphone is opened only while it is on in the active profile.

**Network.** LumiRipple contacts only the OpenRGB/OpenLinkHub servers you configured (default: this computer). No telemetry, no
update check.

**Installer.** `curl | bash` means trusting the repository. Read the script first or install from a checkout.

Please report problems privately through GitHub's "Report a vulnerability".
