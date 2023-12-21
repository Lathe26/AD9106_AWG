# Tools

This folder contains tools related to the AD9106 AWG device.

All Python-based tools are run against pylint version 3.0.3 to verify portions of the code.  No warnings are logged pylint when it is run against awg_ad9106.py.  Only a few warnings are disable in specific code locations.  Any merge requests that include Python code must pass pylint without logging any warnings.

## awg_ad9106.py

**Summary:** Command-line tool to issue commands to a AWG AD9106 device and load arbitrary waveforms into its SRAM.

**Details**

Commands can be issued from the command line and/or from text files that contains a series of commands.  The combined list of commands set to the device can be also saved to a text file for later playback.  The parent folder's `README.md` documents the known commands.

Arbitrary waveforms can be input from the same text files, from CSV files, and/or from audio WAV files.  When data from from a CSV file, one column of data can be loaded or a weighted average from multiple columns.  The same is true for WAV files, with the only difference being that option that specific 'column numbers' refer to audio channel numbers.  Column 0 refers to the mono channel or left channel.  Column 1 refers to the right channel.  Columns numbers 2 or higher refer to their respective audio channel numbers.  WAV files with 8-bit, 16-bit, and higher are supported.

**Installation Requirements**

- python 3.x (developed and tested against 3.9.5)
- pyserial (developed and tested against 3.5)

**Further Documentation**

Run `python awg_ad9106.py --help` (or inspect the source code).

**Example Input Files**

- `Sample Formulas.csv` contains multiple waveforms of sines, parabolas, square waves, etc.  Use `--column-selected` to chose a single waveform
- `Fourier Frequencies.wav` contains the first 16 sine waves and 16 cosine waves used in Fourier Series.  These can be merged together if the Fourier Series co-effiecients are passed in via `--column-weights`.  The file is organized so that sin(x) and cos(x) are channels 0 and 1, sin(2x) and cos(2x) are channels 2 and 3, sin(3x) and cos(3x) are channels 4 and 5, and etc.  The file is a 32-channel, 16-bit, WAV file.

**Example Usages**

A slowing down square wave

`python awg_ad9106.py -d -p COM39 --csv "Sample Formulas.csv" --column-selected 10`

Sum of 16 sine waves shows as 16 strong peaks on a spectrum analyzer or an oscilloscope with FFT abilities

`python awg_ad9106.py -d -p COM39 --csv "Sample Formulas.csv" --column-selected 5`
`
A chirp waveform

`python awg_ad9106.py -d -p COM39 --csv "Sample Formulas.csv" --column-selected 6`

Fourier Series approximation of a Sawtooth Down wave, using the 1st 16 sin co-efficients as the column weights, which are 1, 1/2, 1/3, 1/4, ... 1/n.  Co-efficients for cos terms are 0.0

`python awg_ad9106.py -d -p COM4 --wav "Fourier Frequencies.wav" --scale-auto --column-weights 1.0 0.0 0.5 0.0 0.333333333 0.0 0.25 0.0 0.20 0.0 0.16666666666 0.0 0.142857142857 0.0 0.125 0.0 0.111111111111 0.0 0.1 0.0 0.090909090909 0.0 0.0833333333333333 0.0 0.0769230769230 0.0 0.071428571428 0.0 0.06666666666 0.0 0.0625`

Fourier Series approximation of a Square wave, using the 1st 16 sin co-efficients as the column weights, which are 1, 0, 1/3, 0, 1/5, 0, 1/7, ... 1/(2n+1).  Co-efficients for cos terms are 0.0

`python awg_ad9106.py -d -p COM4 --wav "Fourier Frequencies.wav" --scale-auto --column-weights 1.0 0.0 0.0 0.0 0.333333333 0.0 0.0 0.0 0.20 0.0 0.0 0.0 0.142857142857 0.0 0.0 0.0 0.111111111111 0.0 0.0 0.0 0.090909090909 0.0 0.0 0.0 0.0769230769230 0.0 0.0 0.0 0.06666666666 0.0 0.0`

## Future Tool Ideas

These are potential tools that folks can take on.

- Tool that parses a saved list of commands and converts the arbitrary data back to CSV file format.  Feature details:
    - High-pri: Save data normalized to -1.0 to 1.0 range.
    - High-pri: Handle gaps in the data, such as when a Z command does not contain 64 values or when block numbers are skipped or missing (i.e., the 2 digits that follow the 'Z' character).
    - Medium-pri: If SRAM0 thru SRAM2 commands are also detected, save the data that follows each SRAM command in columns 0, 1, and/or 2.
    - Medium-pri: Option to save as SRAM values of 0 to 511 range.
    - Low-pri: Option to convert to WAV file format.
- other ideas?