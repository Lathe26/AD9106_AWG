"""Communications and processing module for AWG based on Analog Device's AD9106.

It can issue commands to a AWG AD9106 device and load arbitrary waveforms into its SRAM.

This module provided the AWG_AD9106 class that implementat much of the implementation
and provides a "main" function for stand-alone execution.
"""

import time
import sys
import math
import csv
import wave
import argparse
import serial
import serial.tools.list_ports

class AWG_AD9106:   # pylint: disable=invalid-name
    """ Class that issues commands and sends arbitrary data to the AWG based on
    Analog Device's AD9106.
    """
    # pylint: disable=too-many-instance-attributes, too-many-arguments

    EOL = b'\r\n'
    RW_TIMEOUT = 2
    POST_CMD_DELAY = 0.1
    POST_CHANNEL_DELAY = 2.0
    POST_OVER_DELAY = 2.0
    OVER_R = b'OVER'
    OVER_W = OVER_R + EOL
    MAX_SRAM_SAMPLES = 4096
    MAX_SRAM_VALUE = 511
    AUTO_DETECT = -1
    CMD_XXX = b'XXX' + EOL
    RSP_XXX_SIZE = 1024

    def __init__(self,
                 portname: str,
                 generateWriteLog: bool,
                 printWriteLog: bool):
        """Constructor for AWG_AD9106 class
        """
        self._ser = None
        if portname is not None:
            self._ser   = serial.Serial(port = portname,\
                                        timeout = AWG_AD9106.RW_TIMEOUT,
                                        write_timeout = AWG_AD9106.RW_TIMEOUT)
        self._printWriteLog = printWriteLog
        self._generateWriteLog = generateWriteLog
        self._writeLog = bytearray()

        self._needsFinalOver = False

        self._columnRanges = []
        self._columnSelected = None
        self._columnWeights = []
        self._startingRowToRead = 0
        self._maxRowsToRead = AWG_AD9106.MAX_SRAM_SAMPLES
        self._maxRowsToWrite = AWG_AD9106.MAX_SRAM_SAMPLES
        self._hasCsvHeader = AWG_AD9106.AUTO_DETECT
        self._doesPrint = True
        self._doScaleAuto = False
        self._scaleMultiplier = 1.0

    def write(self,
              lines: []) -> None:
        """Write a list of bytes, bytearrays, and strings to the device.
        
        If a list item contains newlines or carriage returns, the item is split
        into multiple commands.
        """
        lines = AWG_AD9106._convertCommandsToListOfBytes(lines)

        for line in lines:
            if line == AWG_AD9106.OVER_W:
                self.sendOverWaitForOver()
            else:
                if line.startswith( b'Z' ):
                    self._needsFinalOver = True
                self._writeHandler( line )
                if line == AWG_AD9106.CMD_XXX:
                    print( self.read( AWG_AD9106.RSP_XXX_SIZE ).decode('utf-8') )
                if self._ser is not None:
                    if line.startswith( b'CHANNEL' ):
                        time.sleep(AWG_AD9106.POST_CHANNEL_DELAY)
                    else:
                        time.sleep(AWG_AD9106.POST_CMD_DELAY)

    def read(self,
             max_bytes: int) -> bytearray:
        """Reads bytes from the device, up to a max_bytes number of bytes
        """
        if self._ser is not None:
            return self._ser.read(max_bytes)
        return bytearray()

    def sendOverWaitForOver(self) -> None:
        """Sends an OVER command, waits for the OVER response.
        """
        self._needsFinalOver = False
        self._writeHandler( AWG_AD9106.OVER_W )
        dataRead = self.read(len( AWG_AD9106.OVER_R ))
        if dataRead != AWG_AD9106.OVER_R and self._ser is not None:
            raise TimeoutError( "Did not receive " + str(AWG_AD9106.OVER_R) + \
                                " from the device, got " + str(dataRead) + " instead." )
        if self._ser is not None:
            time.sleep(AWG_AD9106.POST_OVER_DELAY)

    def getWriteLog(self) -> bytearray:
        """Retrieves the write-log of commands written to the device.
        
        This depends on generateWriteLog being set to True when the constructor is called.
        """
        return self._writeLog

    def needsFinalOver(self) -> bool:
        """Returns whether a final OVER command should be sent.
        
        This is True when arbitrary data (using the Z command) was sent but no
        OVER command followed it.
        """
        return self._needsFinalOver

    def setLoadParameters( self,
                           startingRowToRead: int = None,
                           maxRowsToWrite: int = None,
                           maxRowsToRead: int = None,
                           doScaleAuto: bool = None,
                           scaleMultiplier: float = None,
                           columnRanges: [[float]] = None,
                           columnSelected: int = None,
                           columnWeights: [float] = None,
                           hasCsvHeader: bool = None,
                           doesPrint: bool = None ) -> None:
        """Sets a number of parameters for how data is loaded from CSV and WAV files.
        
        All parameters are optional.  If omitted, the prior values are returned, which
        come from either default values or previous calls to setLoadParameters().
        """
        # pylint: disable=too-many-branches

        if columnRanges is not None:
            self._columnRanges = columnRanges

        if columnSelected is not None:
            self._columnSelected = columnSelected

        if columnWeights is not None:
            self._columnWeights = columnWeights

        if doScaleAuto is not None:
            self._doScaleAuto = doScaleAuto

        if scaleMultiplier is not None:
            self._scaleMultiplier = scaleMultiplier

        if hasCsvHeader is not None:
            self._hasCsvHeader = hasCsvHeader

        if doesPrint is not None:
            self._doesPrint = doesPrint

        if startingRowToRead is not None:
            self._startingRowToRead = startingRowToRead

        if maxRowsToRead is not None:
            if maxRowsToRead == AWG_AD9106.AUTO_DETECT:
                self._maxRowsToRead = AWG_AD9106.MAX_SRAM_SAMPLES
            else:
                self._maxRowsToRead = min( maxRowsToRead, AWG_AD9106.MAX_SRAM_SAMPLES )

        if maxRowsToWrite is not None:
            if maxRowsToWrite == AWG_AD9106.AUTO_DETECT:
                self._maxRowsToWrite = AWG_AD9106.MAX_SRAM_SAMPLES
            else:
                self._maxRowsToWrite = min( maxRowsToWrite, AWG_AD9106.MAX_SRAM_SAMPLES )

    def loadNumbersFromCSV( self,
                            filename: str ) -> [int]:
        """Loads and processes CSV file numbers, returns a list SRAM integer values.
        """
        # pylint: disable=too-many-branches
        CSV_SNIFF_LENGTH = 1024

        finalOutput = []

        with open(filename, newline='', encoding='utf-8-sig') as csvfile:
            # Sniff the CSV for its dialect of CSV format
            dialectSniffed = csv.Sniffer().sniff(csvfile.read(CSV_SNIFF_LENGTH))
            csvfile.seek(0)

            hasHeader = self._hasCsvHeader

            if hasHeader == AWG_AD9106.AUTO_DETECT:
                # Auto-detect whether a header row is present
                hasHeader = csv.Sniffer().has_header(csvfile.read(CSV_SNIFF_LENGTH))
                if self._doesPrint:
                    print(  "Auto-detecting CSV header row... " + \
                            ( "detected." if hasHeader else "not detected." ) )
                csvfile.seek(0)
            else:
                # Convert to proper boolean
                hasHeader = hasHeader > 0

            # Figure out the max number of columns in the CSV file
            reader = csv.reader(csvfile, dialectSniffed)
            maxColumns = 0
            skipHeader = hasHeader
            for row in reader:
                if skipHeader:
                    skipHeader = False
                    continue
                maxColumns = max( maxColumns, len(row) )
            columns = []
            for i in range(0, maxColumns):
                columns.append([])

            # Read the values from the CSV
            # Transpose the rows and columns, handle short rows,
            # handle non-numbers and non-finite numbers
            csvfile.seek(0)
            reader = csv.reader(csvfile, dialectSniffed)
            skipHeader = hasHeader
            rowCount = 0
            for row in reader:
                if skipHeader:
                    skipHeader = False
                    continue
                if rowCount < self._startingRowToRead :
                    rowCount += 1
                    continue
                rowCount += 1
                if rowCount > self._startingRowToRead + self._maxRowsToRead:
                    break
                for i in range(0, maxColumns):
                    if i >= len(row):
                        columns[i].append(0.0)
                    else:
                        columns[i].append(AWG_AD9106._safeConvertToFloat(row[i]))

            finalOutput = self._weightedAverageChannels( columns, self._columnRanges )
            finalOutput = self._padRowsToWrite( finalOutput )
            finalOutput = self._applyScaling( finalOutput )
            finalOutput = self._normalizedValuesToRegisterValues( finalOutput )

        return finalOutput

    def loadNumbersFromWAV( self,
                            filename: str ) -> [float]:
        """Loads and processes WAV file data, returns a list SRAM integer values.
        """
        finalOutput = []

        with wave.open( filename, mode='rb') as wav:
            if wav.getcomptype() != 'NONE':
                raise TypeError("ERROR: compressed wave files are not supported (type = " + \
                                wav.compname + ")"  )

            if self._doesPrint:
                print( "Opened WAV file with the following properties:\n   " + \
                       str( wav.getparams() ) )

            numChannels = wav.getnchannels()
            sampleBytesWidth = wav.getsampwidth()
            frameBytes = wav.readframes( AWG_AD9106.MAX_SRAM_SAMPLES + self._startingRowToRead )

            channels = []
            for _ in range(0, numChannels):
                channels.append([])
            if sampleBytesWidth == 1:
                # Format is unsigned 8-bit values where 0x80 is 0.0.
                DIVISOR = AWG_AD9106.MAX_SRAM_VALUE / 4.0
                j = 0
                rowCount = 0
                for value in frameBytes:

                    if rowCount < self._startingRowToRead:
                        rowCount += 1
                        continue
                    rowCount += 1
                    if rowCount > self._startingRowToRead + self._maxRowsToRead:
                        break

                    channels[j].append( int(value) / DIVISOR - 1.0 )
                    j = (j + 1) % numChannels
            else:
                # Format is signed multiple-bit values where 0x00..00 is 0.0.
                channels = self._loadNumbersFromMultiByteWAV( channels,
                                                              frameBytes,
                                                              sampleBytesWidth,
                                                              numChannels)

            channelRanges = AWG_AD9106._copyListAndForceLength( [], len( channels ), [-1.0, 1.0] )
            finalOutput = self._weightedAverageChannels( channels, channelRanges )
            finalOutput = self._padRowsToWrite( finalOutput )
            finalOutput = self._applyScaling( finalOutput )
            finalOutput = self._normalizedValuesToRegisterValues( finalOutput )

        return finalOutput

    def _loadNumbersFromMultiByteWAV( self,
                                      channels: [[float]],
                                      frameBytes: [bytes],
                                      sampleBytesWidth: int,
                                      numChannels: int ) -> [[float]]:
        """Loads numbers from non-8-bit WAV files (i.e., loads signed integer values).
        
        Returns a list of lists of floats that are normalized to the -1.0 to 1.0 range.
        """
        # pylint: disable=consider-using-enumerate
        currentValue = 0
        isNegative = False
        zeroOffset = 1 << ( sampleBytesWidth * 8 - 1 )
        rowCount = 0

        for i in range(0, len(frameBytes)):
            channel = ( i // sampleBytesWidth ) % numChannels
            byteIndex   = i % sampleBytesWidth
            isFirstByte = byteIndex == 0
            isLastByte  = byteIndex == (sampleBytesWidth - 1)

            if rowCount < self._startingRowToRead:
                if isLastByte and channel == numChannels - 1:
                    rowCount += 1
                continue
            if isLastByte and channel == numChannels - 1:
                rowCount += 1
            if rowCount > self._startingRowToRead + self._maxRowsToRead:
                break

            if isFirstByte:
                currentValue = frameBytes[i] & 0xFF
            elif isLastByte:
                currentValue |= ( frameBytes[i] & 0x7F ) << (8 * byteIndex)
                isNegative   = frameBytes[i] & 0x80 != 0
                if isNegative:
                    currentValue -= zeroOffset
                channels[channel].append( currentValue / zeroOffset )
            else:
                currentValue |= frameBytes[i] << (8 * byteIndex)

        return channels


    def convertNumbersToZCommands(self,
                                  valuesInput: [float]) -> [bytearray]:
        """Given a list of numbers, convert them to a series of Z-commands.
        
        Z-commands are used to load arbitrary data into the SRAM.
        """
        #pylint: disable=consider-using-enumerate

        z_commandsOutput = []
        didClipNumbers = False

        if len(valuesInput) > AWG_AD9106.MAX_SRAM_SAMPLES:
            if self._doesPrint:
                print( "WARNING: too many values (" + str(len(valuesInput)) + \
                       ") specified for SRAM data, trucating to the first " + \
                       AWG_AD9106.MAX_SRAM_SAMPLES + " values" )
            valuesInput = valuesInput[0:AWG_AD9106.MAX_SRAM_SAMPLES]

        for i in range( 0, len( valuesInput ) ):
            if i % 64 == 0:
                z_command = bytearray()
                z_command.extend(b'Z')
                z_command.extend( (f"{i // 64:02d}").encode('utf-8') )

            # Restrict values to integers in the range of [0, MAX_SRAM_VALUE]
            value = max(0, min( AWG_AD9106.MAX_SRAM_VALUE, int(valuesInput[i]) ) )

            if value != int( valuesInput[i] ):
                didClipNumbers = True
            z_command.extend( (f"{value:03d}").encode('utf-8') )
            if i % 64 == 63 or i == len( valuesInput ) - 1:
                z_command.extend(b'\r\n')
                z_commandsOutput.append(z_command)
        if self._doesPrint and didClipNumbers:
            print( "WARNING: some values were out-of-range and clipped to 0 and/or "
                   "{AWG_AD9106.MAX_SRAM_VALUE}." )
        if self._doesPrint:
            print("Generated " + str(len(valuesInput)) + " SRAM values.")

        return z_commandsOutput

    @staticmethod
    def _convertCommandsToListOfBytes(lines: []) ->[bytearray]:
        """Converts a list of "commands" into a list of bytearray of true commands.
        
        For each item in the input list (each can be bytes, bytearray, or str type),
        they are split into separate commands if carriage return or linefeed bytes are
        found and the correct EOL is added to the end of each command.
        """
        if not isinstance( lines, list ):
            lines = { lines }

        bytesList = []

        for line in lines:
            if isinstance( line, (bytes, bytearray) ):
                pass
            elif isinstance( line, str ):
                line = line.encode('utf-8')
            else:
                raise TypeError( "Unhandled line with type " + type(line) + " was encountered." )

            line = line.replace(b'\r', b'\n')

            tempList = line.split(b'\n')
            for tempItem in tempList:
                if len(tempItem) > 0:
                    bytesList.append( tempItem + AWG_AD9106.EOL )

        return bytesList

    def _writeHandler(self,
                      line: bytearray) -> None:
        """Low-level handler for writing to the device.
        
        This hands the device write itself as well as the write-log and printing to the screen.
        """
        if self._printWriteLog:
            # Convert to platform's native screen output.
            print( line.decode().replace('\n', '').replace('\r', '') )
        if self._generateWriteLog:
            self._writeLog.extend( line )
        if self._ser is not None:
            self._ser.write( line )

    @staticmethod
    def _safeConvertToFloat( string: str ) -> float:
        """Safely convert a string to a numeric float (no infinities or non-a-numbers).
        
        Non-compliant values are silently converted to 0.0 value.
        """
        if string is None:
            return 0.0
        try:
            value = float(string)
            if math.isfinite( value ):
                return value
            return 0.0
        except ValueError:
            return 0.0

    def _weightedAverageChannels( self,
                                  channels: [[float]],
                                  channelRanges: [[float]] ) -> [float]:
        """Performs the weighted averaging across channels or columns of data.
        
        The channels input a list of lists of floats.
        The channelRanges is a list of lists each containing 2 floats that are the
        expected min and max values.  It uses the same indices as channels.
        """
        #pylint: disable=consider-using-enumerate

        maxChannelLength = 0
        for channel in channels:
            maxChannelLength = max( maxChannelLength, len(channel) )

        # Build or make a copy of columnWeights of the correct length
        columnWeights = None
        if self._columnSelected is not None:
            if self._columnSelected >= len( channels):
                raise IndexError( f"Selected column ({self._columnSelected}) is out-of-range, 0 "
                                  f"thru {len(channels) - 1} allowed for this file." )
            columnWeights = [ 0.0 ] * len( channels)
            columnWeights[ self._columnSelected ] = 1.0
        else:
            columnWeights = self._columnWeights.copy()
            if len( columnWeights ) == 0:
                columnWeights = AWG_AD9106._copyListAndForceLength(
                                                            columnWeights, len( channels ), 1.0 )

        columnWeights = AWG_AD9106._copyListAndForceLength( columnWeights, len( channels ), 0.0 )

        # Compute weightTotal and pad out columnWeights with 0.0 or truncate if needed.
        weightTotal = 0
        for channelWeight in columnWeights:
            weightTotal += abs(channelWeight)

        # Pad out channelRanges with None if needed.
        channelRanges = AWG_AD9106._copyListAndForceLength( channelRanges, len( channels ), None )

        finalOutput = []
        for i in range(0, maxChannelLength):
            weightedAverage = 0
            for j in range(0, len(channels)):
                # Safely get the weight and value
                weight = float( columnWeights[j] )
                value  = 0.0 if j >= len(channels) else channels[j][i]
                value  = AWG_AD9106._normalizeValue( value, channelRanges[j] )
                weightedAverage += weight * value
            if weightTotal > 0.0:
                weightedAverage /= weightTotal
            else:
                weightedAverage = 0.0
            finalOutput.append(weightedAverage)

        return finalOutput

    @staticmethod
    def _copyListAndForceLength( listInput: [],
                                 length: int,
                                 fillValue) -> []:
        """Copies a list and forces it to have the specified length.
        
        This is done via truncation or padding with the fillValue.
        """
        listOutput = []

        if listInput is not None:
            listOutput = listInput.copy()
        if len(listOutput) < length:
            listOutput.extend( [ fillValue ] * (length - len(listOutput) ) )
        listOutput = listOutput[:length]

        return listOutput


    @staticmethod
    def _normalizeValue( value: float,
                         channelRange: [float] ) -> float:
        """Normalizes a single value to the range of -1.0 to 1.0.
        
        channelRange is a list containing 2 floats that are the expected min and max
        for the input value.  This is used to convert value to the range of -1.0 to 1.0.
        """
        DEFAULT_RANGE = [ -1.0, 1.0 ]

        if channelRange is None or not isinstance(channelRange, list) or len(channelRange) < 2:
            channelRange = DEFAULT_RANGE

        if channelRange[0] > channelRange[1]:
            tempRangeValue  = channelRange[0]
            channelRange[0] = channelRange[1]
            channelRange[1] = tempRangeValue

        channelWidth = channelRange[1] - channelRange[0]
        if channelWidth == 0.0:
            return 0.0
        value -= channelRange[0]
        value = value * 2.0 / channelWidth
        value += DEFAULT_RANGE[0]
        return max( DEFAULT_RANGE[0], min( DEFAULT_RANGE[1], value ) )

    def _applyScaling( self,
                       normValues: [float] ) -> [float]:
        """Applies auto-scaling and/or the scaling multiplier to the list of values.
        """
        minValue = min( normValues )
        maxValue = max( normValues )

        if self._doScaleAuto:
            autoMultiplier = 1.0
            if minValue != 0 and maxValue != 0:
                autoMultiplier = 1 / max( abs( minValue ), abs( maxValue ) )
            normValues = [ autoMultiplier * item for item in normValues ]

        normValues = [ self._scaleMultiplier * item for item in normValues ]

        return normValues

    @staticmethod
    def _normalizedValuesToRegisterValues( normValues: [float] ) -> [float]:
        """Given values normalized to -1.0 to 1.0, convert them to correct SRAM register values.
        """
        registerValues = []

        for normValue in normValues:
            registerValue = int( round( (normValue + 1.0) *
                                        AWG_AD9106.MAX_SRAM_VALUE / 2.0, 0 ) )
            registerValue = max( 0, min( AWG_AD9106.MAX_SRAM_VALUE, registerValue ) )
            registerValues.append( registerValue )

        return registerValues

    def _padRowsToWrite(self,
                        valuesToPad: [float] ) -> [float]:
        """If the input valuesToPad is too short, repeat the final value until long enough.
        
        "Long enough" means to make the list as long as _maxRowsToWrite.
        """
        if len(valuesToPad) < self._maxRowsToWrite:
            padValue = 0.0 if len(valuesToPad) == 0 else valuesToPad[len(valuesToPad) - 1]
            for _ in range(len(valuesToPad), self._maxRowsToWrite):
                valuesToPad.append( padValue )

        return valuesToPad

def _parse_command_line():
    """Parses the command line for the main function.
    """
    desc_message =  "Tool to issue commands to a AWG AD9106 device and load arbitrary waveforms " \
                    "into its SRAM.  Commands can be issued from the command line and/or from " \
                    "text files that contains a series of commands.  The combined list " \
                    "of commands set to the device can be also saved to a text file " \
                    "for later playback.  Arbitrary waveforms can be input from the " \
                    "same text files, from CSV files, and/or from audio WAV files.  " \
                    "When data from from a CSV file, one column of data " \
                    "can be loaded or a weighted average from multiple columns.  The same " \
                    "is true for WAV files, with the only difference being that option " \
                    "that specific \'column numbers\' refer to audio channel numbers.  " \
                    "Column 0 refers to the mono channel or left channel.  Column " \
                    "1 refers to the right channel.  Columns numbers 2 or " \
                    "higher refer to their respective audio channel numbers.  WAV files with " \
                    "8-bit, 16-bit, and higher are supported."
    parser = argparse.ArgumentParser(
                    prog='AWG_AD9106',
                    description=desc_message)

    parser.add_argument('-p', '--port',
                        help="Device's serial port name, such as \'COM3\' or \'/dev/ttyS0\'.  If "
                             "omitted, no device will be connected to.",
                        default=None,
                        action='store')
    parser.add_argument('--list-ports',
                        help="Lists the available serial ports on the host system.",
                        action='store_true')
    parser.add_argument('-o', '--out-file',
                        help="Writes all commands out to a file, including any arbitrary waveform "
                             "data.  Intended for later use with --pre-cmd and --post-cmd.  Can be "
                             "used in repeated executions to build up a longer and longer list of "
                             "commands.",
                        default=None,
                        action='store')
    parser.add_argument('-d', '--display-commands',
                        help="Write all commands out to the screen, including any arbitrary "
                             "waveform data.",
                        action='store_true')
    parser.add_argument('-i', '--pre-cmd',
                        help="Adds a command to be sent before transmitting arbitrary waveform "
                             "data (if any).  Can be specified multipled times.  If the command "
                             "starts with \'@' then the remainder specifies a filename that "
                             "contains multiple commands.",
                        default=[],
                        action='append')
    parser.add_argument('-j', '--post-cmd',
                        help="Adds a command to be sent after transmitting arbitrary waveform data "
                             "(if any).  Can be specified multipled times.  If the command starts "
                             "with \'@' then the remainder specifies a filename that contains "
                             "multiple commands .",
                        default=[],
                        action='append')
    parser.add_argument('--csv',
                        help="File name of the CSV file to open to read arbitrary data from.  Data "
                             "in the columns is expected to be in the range of -1.0 to 1.0, unless "
                             "--columnRange is specified.  Can not be used in conjuction with the "
                             "--wav option.",
                        default=None,
                        action='store')
    parser.add_argument('--wav',
                        help="File name of the WAV file to open to read arbitrary data from.  Can "
                             "not be used in conjuction with the --csv option.",
                        default=None,
                        action='store')
    parser.add_argument('-c', '--column-selected',
                        help="Selects a single column (CSV) or channel (WAV) to read in.  0 is the "
                             "first column or channel.  Can not be used in conjuction with "
                             "--columnWeights.",
                        type=int,
                        default=None,
                        action='store')
    parser.add_argument('--csv-header',
                        help="Force how the first row of a CSV is treated.  If it is a header row, "
                             "it is treated as non-data and skipped over.  Default is to "
                             "auto-detect the header row's presence.",
                        action=argparse.BooleanOptionalAction)
    parser.add_argument('-a', '--scale-auto',
                        help="Automatically vertically scales the final arbitrary data so that "
                             "either min value is -1.0 or max value is 1.0.",
                        default=False,
                        action='store_true')
    parser.add_argument('-m', '--scale-multiplier',
                        help="Multiplies the vertical scale of the final arbitrary data.  Large "
                             "values may cause clipping.  If --scale-auto is also specified, "
                             "--scale-multiplier is applied after it",
                        type=float,
                        default=1.0,
                        action='store')
    parser.add_argument('-f', '--arb-first-read-index',
                        help="Index into the CSV or WAV file for the first arbitrary waveform data "
                             "sample to read.  The default is index 0.",
                        type=int,
                        default=None,
                        action='store')
    parser.add_argument('-n', '--arb-read-count',
                        help="Max number of arbitrary waveform data samples to READ from the CSV "
                             "or WAV file.  Default is to read all data, until the SRAM is full, "
                             "or up to --arb-write-count.",
                        type=int,
                        default=None,
                        action='store')
    parser.add_argument('-w', '--arb-write-count',
                        help="Max number of arbitrary waveform data samples to WRITE from the CSV "
                             "or WAV file into the SRAM.  If necessary, the final read-in value "
                             "will be repeated until the there are enough samples to write.  "
                             "Default is write all the read-in data or until the SRAM is filled.",
                        type=int,
                        default=None,
                        action='store')
    parser.add_argument('-t', '--column-weights',
                        help="(advanced feature) When reading multiple columns (CSV) or multiple "
                             "channels (WAV), use the provided weights to generate a weighted "
                             "average for the values in each row (CSV) or timepoint (WAV).  This "
                             "average value becomes the one of the sample value's written to "
                             "SRAM.  The is repeated for each row or timepoint until enough "
                             "average samples have been generated.  The 1st weight corresponds to "
                             "column or channel 0.  Negative weights allowed.  For example, using "
                             "\'--columnWeights 1.0 0.5\' with a WAV file will generate an "
                             "arbitrary waveform that combines the left and right channels but the "
                             "left channel is twice as strong as the right.  Can not be used in "
                             "conjuction with --columnWeights.  By default, WAV files will use a "
                             "weighted average of 1.0 for all the channels.  CSV files require "
                             "either --columnWeights or --columnSelected.",
                        type=float,
                        nargs='+',
                        default=[],
                        action='store')
    parser.add_argument('-r', '--column-range',
                        help="(advanced feature) Only used with CSV files.  Sets the range of "
                             "values for a column.  Useful for when the column's values don't "
                             "range from -1.0 to 1.0.  Can be specified multiple times to specify "
                             "multiple columns.  Requires 3 values.  The format is --columnRange "
                             "COLUMN_NUM RANGE_LOW RANGE_HIGH.  For example \'--columnRange 3 -4.0 "
                             "10.0\' indicates that column 3 ranges from -4.0 to 10.0.",
                        type=float,
                        nargs=3,
                        default=[],
                        action='append')
    parser.add_argument('--no-messages',
                        help="Disables writing message to the screen.  Separate from "
                             "--display-commands.",
                        action='store_true')

    args = parser.parse_args()

    if args.csv is not None and args.wav is not None:
        print("ERROR: can not use --csv and --wav at same time.")
        sys.exit(1)
    if args.column_selected is not None and len(args.column_weights) > 0:
        print("ERROR: can not use --column-selected and --column-weights at same time.")
        sys.exit(1)
    if args.csv is not None and args.column_selected is None and len(args.column_weights) == 0:
        print("ERROR: --csv requires --column-selected or --column-weights.")
        sys.exit(1)

    # Change None to AWG_AD9106.AUTO_DETECT, if necessary
    args.csv_header = AWG_AD9106.AUTO_DETECT if args.csv_header is None else args.csv_header

    if len(args.column_range) > 0:
        column_ranges = []

        max_index = -1
        for column_range in args.column_range:
            if column_range[0] < 0:
                print( 'ERROR: a --column-range with a negative index was given' )
                sys.exit(1)
            max_index = max( int( column_range[0] ), max_index )

        column_ranges = [ None ] * (max_index + 1)
        for column_range in args.column_range:
            index = int( column_range[0] )
            column_range = column_range[1:]
            column_ranges[index] = column_range

        args.column_range = column_ranges

    return args


def _execute_commands_list( device: serial.Serial,
                            commands: [str] ) -> None:
    """Executes the list of commands (or file of commands) sent by the main function.
    """
    for command in commands:
        if len(command) == 0:
            continue

        if command[0] != '@':
            device.write( command )
            continue

        filename = command[1:]
        with open( filename, 'rb' ) as file:
            device.write( file.read() )


def _main():
    """The main function when this module is executed as a command-line program.
    """
    args = _parse_command_line()

    if args.list_ports:
        print("Available serial ports (AWG AD9106 has USB VID & PID of 0x0483 & 0x5740):" )
        for port in serial.tools.list_ports.comports( True ):
            print(  '   Serial device:')
            print( f'      Device        : {port.device}')
            print( f'      Name          : {port.name}')
            print( f'      Description   : {port.description}')
            print( f'      Hardware ID   : {port.hwid}')
            print(  '      USB specific:' )
            print( f'      VID           : 0x{port.vid:04X}')
            print( f'      PID           : 0x{port.pid:04X}')
            print( f'      Serial Number : {port.serial_number}')
            print( f'      Location      : {port.location}')
            print( f'      Manufacturer  : {port.manufacturer}')
            print( f'      Product       : {port.product}')
            print( f'      Interface     : {port.interface}')
        if len( serial.tools.list_ports.comports( True ) ) == 0:
            print('   None found' )

    device = AWG_AD9106( args.port, args.out_file is not None, args.display_commands )

    device.setLoadParameters( columnRanges = args.column_range,
                              columnSelected = args.column_selected,
                              columnWeights = args.column_weights,
                              doScaleAuto = args.scale_auto,
                              scaleMultiplier = args.scale_multiplier,
                              startingRowToRead = args.arb_first_read_index,
                              maxRowsToRead = args.arb_read_count,
                              maxRowsToWrite = args.arb_write_count,
                              hasCsvHeader = args.csv_header,
                              doesPrint = not args.no_messages )

    # Run the pre-commands
    _execute_commands_list( device, args.pre_cmd )
    if device.needsFinalOver():
        device.sendOverWaitForOver()

    # Load arbitrary waveform data
    values = None
    if args.csv is not None:
        values = device.loadNumbersFromCSV( args.csv )
    elif args.wav is not None:
        values = device.loadNumbersFromWAV( args.wav )
    if values is not None:
        z_commands = device.convertNumbersToZCommands( values )
        device.write( z_commands )
        if device.needsFinalOver():
            device.sendOverWaitForOver()

    # Run the post-commands
    _execute_commands_list( device, args.post_cmd )
    if device.needsFinalOver():
        device.sendOverWaitForOver()

    if args.out_file is not None:
        with open( args.out_file, 'w+b' ) as file:
            file.write( device.getWriteLog() )


# commands to:
#   auto-adjust SP and Mod_Cyc... would need to know the active channel(s)... lot's more work.
#       maybe just output these values for the user to set / send?
#   handle XXX
if __name__ == "__main__":
    _main()
