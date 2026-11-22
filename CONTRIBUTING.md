# Contributing

The most useful help is a report from real hardware: keyboard, system, layout, output of `lumiripple doctor`, what works and what
does not. Windows and macOS are untested so far.

Code: `python3 -m unittest` must pass on Python 3.10 and newer. Please add a test that fails without your change. Keep the service
free of dependencies on Linux. Text for users is plain English.

You may use AI tools, but you are responsible for what you submit: understand it and test it.

Before publishing from a private copy: `scripts/check-privacy.sh`.
