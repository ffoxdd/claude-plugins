@echo off
rem The chat adapter's entry point for a native Windows shell — cmd.exe or
rem PowerShell — where `slack-client login` is the one command a person types by
rem hand. Claude Code's Bash tool runs Git Bash, which reads the `slack-client`
rem shim beside this file; neither shell reads the other's, so both exist and
rem stay in step.
rem
rem The interpreter is named here for the same reason it is named there: the
rem dependencies live inline in the script under PEP 723, which is what lets this
rem plugin ship the adapter with no install step beyond `uv` itself.
uv run --script "%~dp0..\scripts\slack-client" %*
