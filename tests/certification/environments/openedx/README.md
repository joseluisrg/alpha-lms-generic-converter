# Open edX certification environment

The certification harness expects `tutor==22.0.4` on `PATH`. The workflow installs
it with `uv tool install`, enables the forum plugin, disables SMTP, and launches the
Verawood stack before running the Open edX import case.
