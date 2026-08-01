"""Decoding, DSP, mixing and output. No Qt -- see the `core/` rule in CLAUDE.md.

Importing `engine` pulls in PortAudio via `sounddevice`; `decode`, `dsp` and
`sfx` are numpy only and stay importable on a machine with no sound card.
"""
