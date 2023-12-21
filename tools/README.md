# Tools

This folder contains tools related to the AD9106 AWG device.

All Python-based tools are run against pylint version 3.0.3 to verify portions of the code.  No warnings are logged pylint when it is run against awg_ad9106.py.  Only a few warnings are disable in specific code locations.  Any merge requests that include Python code must pass pylint without logging any warnings.

## awg_ad9106.py

**Summary:** Command-line tool to issue commands to a AWG AD9106 device and load arbitrary waveforms into its SRAM.

**Details:**

Commands can be issued from the command line and/or from text files that contains a series of commands.  The combined list of commands set to the device can be also saved to a text file for later playback.  The parent folder's `README.md` documents the known commands.

Arbitrary waveforms can be input from the same text files, from CSV files, and/or from audio WAV files.  When data from from a CSV file, one column of data can be loaded or a weighted average from multiple columns.  The same is true for WAV files, with the only difference being that option that specific 'column numbers' refer to audio channel numbers.  Column 0 refers to the mono channel or left channel.  Column 1 refers to the right channel.  Columns numbers 2 or higher refer to their respective audio channel numbers.  WAV files with 8-bit, 16-bit, and higher are supported.

**Installation Requirements:**

- python 3.x (developed and tested against 3.9.5)
- pyserial (developed and tested against 3.5)

**Further Documentation:**

Run `python awg_ad9106.py --help` (or inspect the source code).


## Future Tool Ideas

These are potential tools that folks can take on.

- Tool that parses a saved list of commands and converts the arbitrary data back to CSV file format.  Feature details:
    - High-pri: Save data normalized to -1.0 to 1.0 range.
    - High-pri: Handle gaps in the data, such as when a Z command does not contain 64 values or when block numbers are skipped or missing (i.e., the 2 digits that follow the 'Z' character).
    - Medium-pri: If SRAM0 thru SRAM2 commands are also detected, save the data that follows each SRAM command in columns 0, 1, and/or 2.
    - Medium-pri: Option to save as SRAM values of 0 to 511 range.
    - Low-pri: Option to convert to WAV file format.
- other ideas?