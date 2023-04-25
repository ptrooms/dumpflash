# pylint: disable=line-too-long

# def __read1 vs def __read :   full size or per byte

# 07apr23: pafoxp@sh67:~/code-dumpflash/dumpflash$ python3 dumpflash.py -R -c write_file mtdblock1.img  (write 1000.000 bytes with oob) (not enought data, require file witjh oob)
# 07apr23: pafoxp@sh67:~/code-dumpflash/dumpflash$ python3 dumpflash.py -R -c write_file mtd1_oob.img  (write Writing 100% Page: 4095/4095 Block: 255/256 Speed: 61939 bytes/s)


from array import array as Array
import time
import struct
import sys
import traceback
from pyftdi import ftdi
import ecc
import flashdevice_defs
import time

class IO:
    def __init__(self, do_slow, debug = False, streamdata = 1 , simulation_mode = False, debug_info = True):
        self.Debug = debug
        self.PageSize = 0
        self.OOBSize = 0
        self.PageCount = 0
        self.BlockCount = 0
        self.PagePerBlock = 0
        self.BitsPerCell = 0
        self.WriteProtect = True
        self.CheckBadBlock = True
        self.RemoveOOB = False
        self.UseSequentialMode = False
        self.UseAnsi = False
        self.Slow = do_slow
        self.Identified = False
        self.SimulationMode = simulation_mode
        self.Tsize = 0                # size to transport exchange buffer with ftdi
        self.Debug_info = debug_info  # print informational messages
        self.StreamData = streamdata          # 0  = very slow per byte, 1 is equal to full speed (require SLOW) _read1/DoStream read/DoPerByte

        print (' flashdevice.__init__: self.Slow=', str(do_slow), 'self.StreamData=', streamdata, '\n')

        try:
            self.ftdi = ftdi.Ftdi()
        except:
            print("Error openging FTDI device")
            self.ftdi = None

        if self.ftdi is not None:
            try:
                self.ftdi.open(0x0403, 0x6010, interface = 1)  # Open ftdi interface Bus 002 Device 021: ID 0403:6010 Future Technology Devices International, Ltd FT2232C Dual USB-UART/FIFO IC
            except:
                traceback.print_exc(file = sys.stdout)

            # print('Type of FTDI=', self.ftdi.ic_name)
            print('Type of FTDI=', self.ftdi.ic_name, ', has_mpsse=', self.ftdi.has_mpsse, ', wideport=', self.ftdi.has_wide_port, ', bitbang=', self.ftdi.bitbang_enabled )  # Type of FTDI= ft2232h
            print(' write_data_get_chunksize=', self.ftdi.write_data_get_chunksize(), ', read_data_get_chunksize=', self.ftdi.read_data_get_chunksize() )

            if self.ftdi.is_connected:
                self.ftdi.set_bitmode(0, ftdi.Ftdi.BitMode.MCU)  # BITMODE_MCU = 0x08      # MCU Host Bus Emulation mode 
                # for MCU read: /media/Rdisk/Info/Yealink/T36/recovery/FT2232H_AN_108_Command_Processor_for_MPSSE_and_MCU_Host_Bus_Emulation_Modes.pdf

                # Note: In Host Bus Emulation mode the clock divisor has no effect. From documentation AN108:
                #   In Host Bus Emulation mode the clock divisor has no effect. The clock divisor is used for serial data and is
                #   a different part of the MPSSE block. In host bus emulation the 60MHz clock is always output and doesn’t
                #   change with any commands.
                if self.Slow:
                    # Clock FTDI chip at 12MHz instead of 60MHz 
                    # read /media/Rdisk/Info/Yealink/T36/recovery/datasheet_ftdi_DS_FT2232H.pdf
                    # When Div By 5 is on the device will return 2 bytes when doing a read.
                    # The clock period is 16.67 nS so most devices would need the Div By 5 to be set on.
                    self.ftdi.write_data(Array('B', [ftdi.Ftdi.ENABLE_CLK_DIV5]))  #  ENABLE_CLK_DIV5 = 0x8b
                    # self.ftdi.write_data(Array('B', [0x86, 0xFF, 0xFF]  ))  #  At 60mHZ this will do 0xFFFF 457.763 Hz
                    print(' --- flashdevice.__init_ : executing SLOW' ) 
                else:
                    self.ftdi.write_data(Array('B', [ftdi.Ftdi.DISABLE_CLK_DIV5])) #  DISABLE_CLK_DIV5 = 0x8a
                    print(' --- flashdevice.__init_ : executing FAST' ) 
                    # self.ftdi._set_frequency(12000) # does not work as ftdi.py only allows this in MPSSE mode
                    # self.ftdi.write_data(Array('B', [0x86, 0xFF, 0xFF]  ))  #  At 60mHZ this should do 0xFFFF 457.763 Hz bu has no effect


                # //here timer
                # self.ftdi.set_latency_timer(self.ftdi.LATENCY_MIN)		#     LATENCY_MIN = 12 LATENCY_MAX = 255
                self.ftdi.set_latency_timer(16)		#     LATENCY_MIN = 12 LATENCY_MAX = 255
                # self.ftdi.set_latency_timer(self.ftdi.LATENCY_MIN)		#     LATENCY_MIN = 12 LATENCY_MAX = 255
                # self.ftdi.set_latency_timer(128)		#     LATENCY_MIN = 12 LATENCY_MAX = 255
                self.ftdi.purge_buffers()

                #  ftdi.Ftdi.SET_BITS_HIGH (0xValue,0xDirection)   0x82,0xValue,0xDirection
                #     This will setup the direction of the high 4 lines and 
                #     force a value on the bits that are set as output. 
                #     A '1' in the Direction byte will make that bit an output.
                # The low byte would be ADBUS 7-0, and the high byte is ACBUS 7-0.
                # 0x0 writes a low to output pin 0000 0001  
                # Change MSB GPIO output pin 45 BD6 NanD Chip-Enable Low Output
                # org: self.ftdi.write_data(Array('B', [ftdi.Ftdi.SET_BITS_HIGH, 0x0, 0x1]))  # SET_BITS_HIGH = 0x82    I/O-0 set to Out-0x1
                self.ftdi.write_data(Array('B', [ftdi.Ftdi.SET_BITS_HIGH, 0x1, 0x1]))  # SET_BITS_HIGH = 0x82   I/O-0 BDBUS6 set to Out-0x1 active HIGH no LED no CE
                time.sleep(1)
                self.ftdi.write_data(Array('B', [ftdi.Ftdi.SET_BITS_HIGH, 0x0, 0x1]))  # SET_BITS_HIGH = 0x82   I/O-0 BDBUS6 set to Out-0x1 active LOW with upper led


        self.__wait_ready()
        self.__get_id()

    def __wait_ready(self):
    # wait until ftdi is free 
        if self.ftdi is None or not self.ftdi.is_connected:
            return

        while 1:  # Note: not sure if this TRUE causes a buffer fill ?
            self.ftdi.write_data(Array('B', [ftdi.Ftdi.GET_BITS_HIGH])) # GET_BITS_HIGH = 0x83    # Get MSB GPIO output pin 45+46 BDBUS0-7
            data = self.ftdi.read_data_bytes(1)
            if not data or len(data) <= 0:
                raise Exception('FTDI device Not ready, len=', len(data), '. Try restarting it.')

            if  data[0] & 6 != 0x6:   # check mask bit 0000 0020 pin 46 (BDBUS7) is HIGH means ready I/O-1 , LOW means busy.
                if  self.Debug_info:
                    print('__wait_ready: R_B NanD status 0x%x ..' % (data[0])) # 0x06     --> 0000 0110  print not ready status
            
            if  data[0] & 2 == 0x2:   # check mask bit 0000 0020 pin 46 (BDBUS7) is HIGH means ready I/O-1 , LOW means busy.
                return

            if self.Debug > 0:
                print('Not Ready', data)

        raise Exception('NAND device Not ready. Try restarting it.')

        return

    #  called for data read pages with return self.__read(0, 0, count) , for pages cout=2112 bytes
    # this builds the buffer which will be transferred to the FTDI by self.ftdi.write_data

    def __read1(self, self2, cl, al, count):  # this read will que all commands for one immediate execution
    # read data self.__read(0, 0, count) --> #byte1 0x91 0x00 0x00  + #bytes-1  0x90 0x00 ... ... + 0x87
        if self.ftdi is None or not self.ftdi.is_connected:
            return

        # 
        # TBD Fix by splitting the datastream into segments of 256 or 512bytes
        #
        cmds = []
        data = []
        cmd_type = 0x00                                 # Controls bits AC7-AC0  
        if cl == 1:
            cmd_type |= flashdevice_defs.ADR_CL         # mask 0X40 --> cmd_type = 0x40 activating CLE pin 33 ACBUS6
            cmd_type |= 0x01                            # ACBUS0 high
        if al == 1:
            cmd_type |= flashdevice_defs.ADR_AL         # mask 0x80 --> cmd_type = 0x80 activating ALE pin 34 ACBUS7
            cmd_type |= 0x01                            # ACBUS0 high

        cmds += [ftdi.Ftdi.READ_EXTENDED, cmd_type, 0]  # MCU mode ftdi READ_EXTENDED = 0x91 0x00=0xCL|0xAH 0x00=0xAL , for pagesdata cmd_type=0
                                                        # 0x91     0xAH 0xAL This will read 1 byte from the target device.
        # print('Page count:\t ', int(count) )
        for _ in range(1, int(count), 1):
            # print('Page count:\t ', count)
            cmds += [ftdi.Ftdi.READ_SHORT, 0]       # for each byte add a short READ_SHORT = 0x90 and a 0xAL=0x00
            # cmds += [0x84, 0x85, 0x97]            # tdi/tdo test, disable trying to delay read at no effect.

                                                    # 0x90 0xAL This will read 1 byte from the target device.
        cmds.append(ftdi.Ftdi.SEND_IMMEDIATE)       # add ftdi SEND_IMMEDIATE = 0x87
        # if len(cmds) > 4:  
        #    print ('__read: ftdi cmds len=%d 0x%x 0x%x 0x%x 0x%x 0x%x ... 0x%x' % (len(cmds), cmds[0], cmds[1], cmds[2], cmds[3], cmds[4], cmds[len(cmds)-1] ) )  # 4226
        # __read: cmds len=4226 0x91 0x0 0x0 0x90 ... 0x87 2x2112+2
        self.ftdi.write_data(Array('B', cmds))      # actually send my command 0x91 0x0 0x0 + (per requested byte) 0x90 0x00 ... + 0x87

        if self.is_slow_mode():                     # Note: slow does not change clockspeed but will elongate RD/WR windows, see also IORDY pin
            data3 = self.ftdi.read_data_bytes(count*2,2)  # 1st byte is value, second byte = 
            data2 = data3[0:-1:2]                 # 1st byte
            data1 = data3[1::2]                   # 2nd byte
            if data1 != data2: 
               print('  CLKDIV5 readerror len(data3)=%d len(data2)=%d len(data1)=%d double bytes not equal data1=0x , data2=0x' % (len(data3), len(data2), len(data1) ) )
        else:
            data2 = self.ftdi.read_data_bytes(count,4)   # def read_data_bytes(self, size, attempt=1 , get ftdi buffer

        if len(data2) != count:
            print('   LENTGH readerror len(data)=%d is not equal to count=%d Slow=%s cmdtype=0x%x' % (len(data), count, self.is_slow_mode(), cmd_type ) )

        data += data2

        # print(' count=%d  len(data)=%d len(data2)=%d ' % (count, len(data), len(data2) ) )

        # read_data_bytes --> 
        # /home/pafoxp/code-dumpflash/pyftdi-0.29.0/pyftdi/ftdi.py --> def read_data_get_chunksize(self) --> 
        #              data = self.usb_dev.read(self.out_ep, self.readbuffer_chunksize, self.usb_read_timeout)

        return bytes(data)  # converts an object to an immutable byte-represented object of given size and data.


    def __read(self, cl, al, count):  # approax 4K per second at 1 byte reads

        if self.StreamData == 1: return(self.__read1(self, cl, al, count))  # use original stream method
  
        # read data self.__read(0, 0, count) --> #byte1 0x91 0x00 0x00  + #bytes-1  0x90 0x00 ... ... + 0x87
        if self.ftdi is None or not self.ftdi.is_connected:
            return
        # 
        # Force and fix 1 byte reads
        #
        cmds = []
        data = []
        cmd_type = 0x00                                 # Controls bits AC7-AC0  

        if cl == 1:
            cmd_type |= flashdevice_defs.ADR_CL         # mask 0X40 --> cmd_type = 0x40 activating CLE pin 33 ACBUS6
            cmd_type |= 0x01                            # ACBUS0 high
        if al == 1:
            cmd_type |= flashdevice_defs.ADR_AL         # mask 0x80 --> cmd_type = 0x80 activating ALE pin 34 ACBUS7
            cmd_type |= 0x01                            # ACBUS0 high

        cmds += [ftdi.Ftdi.READ_EXTENDED, cmd_type, 0]  # MCU mode ftdi READ_EXTENDED = 0x91 0x00=0xCL|0xAH 0x00=0xAL , for pagesdata cmd_type=0
                                                        # 0x91     0xAH 0xAL This will read 1 byte from the target device.
        # print ('reading count=', count)

        if cl == 0 and al == 0:                    # read per data byte
            # print ('reading count1=', count)
            for _ in range(1, int(count+1), 1):
                cmds.append(ftdi.Ftdi.SEND_IMMEDIATE)       # add ftdi SEND_IMMEDIATE = 0x87
                self.ftdi.write_data(Array('B', cmds))      # actually send my command 0x91 0x0 0x0 + (per requested byte) 0x90 0x00 ... + 0x87

                if self.is_slow_mode():                     # Note: slow does not change clockspeed but will elongate RD/WR windows,see also IORDY pin
                    data3 = self.ftdi.read_data_bytes(1*2,2)  # 1st byte is value, second byte = 
                    data2 = data3[0:-1:2]                 # 1st byte
                    data1 = data3[1::2]                   # 2nd byte
                    if data1 != data2: 
                      print('  CLKDIV5 readerror len(data3)=%d len(data2)=%d len(data1)=%d double bytes not equal data1=0x , data2=0x' % (len(data3), len(data2), len(data1) ) )
                else:
                    data2 = self.ftdi.read_data_bytes(1,4)   # def read_data_bytes(self, size, attempt=1 , get ftdi buffer

                data += data2
                # data  += self.ftdi.read_data_bytes(1,1)      # def read_data_bytes(self, size, attempt=4 , get ftdi buffer
                cmds = [ftdi.Ftdi.READ_SHORT, 0]             # prepare next byte
        else:                                      # or do command or address sequence
            # print ('reading count2=', count) 
            for _ in range(1, int(count), 1):
                cmds += [ftdi.Ftdi.READ_SHORT, 0]       # for each byte add a short READ_SHORT = 0x90 and a 0xAL=0x00
                # cmds += [0x84, 0x85, 0x97]            # tdi/tdo test, disable trying to delay read at no effect.
                                                        # 0x90 0xAL This will read 1 byte from the target device.
                cmds.append(ftdi.Ftdi.SEND_IMMEDIATE)   # add ftdi SEND_IMMEDIATE = 0x87

            self.ftdi.write_data(Array('B', cmds))      # actually send my command 0x91 0x0 0x0 + (per requested byte) 0x90 0x00 ... + 0x87
            if self.is_slow_mode():
                data = self.ftdi.read_data_bytes(count*2)
                data = data[0:-1:2]
            else:
                data = self.ftdi.read_data_bytes(count,1)   # def read_data_bytes(self, size, attempt=1 works) , get ftdi buffer

        return bytes(data)  # converts an object to an immutable byte-represented object of given size and data.

    def __write(self, cl, al, data): # //here:write
        # called by address: 0x01 to adress page 1 via data bytes 0x00 0x00 0x01 0x00  < - colL colH rowL RowH

        # address --> self.__write(0, 1, data)   cmd_type = 0x40
        # command --> self.__write(1, 0, data)   cmd_type = 0x80
			# self.__send_cmd(flashdevice_defs.NAND_CMD_SEQIN)
			# self.__send_cmd(flashdevice_defs.NAND_CMD_PAGEPROG)
			# self.__send_cmd(flashdevice_defs.NAND_CMD_READ0)
			# self.__send_cmd(flashdevice_defs.NAND_CMD_READ1)
			# NAND_CMD_READSTART = 0x30  Nand Page read is initiated by writing 00h-30h


        # data = the command for the Nandchip

        # print('CL=0x%x AL=0x%x WP=0x%x ord=%s' % (flashdevice_defs.ADR_CL, flashdevice_defs.ADR_AL, flashdevice_defs.ADR_WP, hex(data[0]) ))
        # print('CL=0x%x AL=0x%x WP=0x%x ord=??' % (flashdevice_defs.ADR_CL, flashdevice_defs.ADR_AL, flashdevice_defs.ADR_WP ) )    
        # note ord('a') = inverse of chr()  , comprable to val of character,  returns integer 97. ord(Euro sign) returns 8364

        # masks ADR_CE = 0x10 (not used, here) , ADR_WP = 0x20 , ADR_CL = 0x40, ADR_AL = 0x80
        cmds = []
        cmd_type = 0

        if al == 1:
            cmd_type |= flashdevice_defs.ADR_AL    # for address this do: 0x80  pin 34 ACBUS7 A15
        if cl == 1:
            cmd_type |= flashdevice_defs.ADR_CL    # for command this do: 0x40  pin 33 ACBUS6 A14
        if not self.WriteProtect:
            cmd_type |= flashdevice_defs.ADR_WP    # for WP this does do: 0x20  pin 32 ACBUS5 A13

        # cmd = 4 bytes  0x92 0x00 0xAL 0xDATA

        # for read page address 1 this does do:  0x93  0x80 0x00 + 0x00 + loopresult ( 0x92 0x00 0x92 0x01 0x92 0x00 )
        cmds += [ftdi.Ftdi.WRITE_EXTENDED, cmd_type, 0, ord(data[0])]	# use first byte WRITE_EXTENDED = 0x93, ORD[] fails at strings > 1 byte
        # print('CL=0x%x AL=0x%x WP=0x%x ord=?? lendata=%d lencmds=%d' % (flashdevice_defs.ADR_CL, flashdevice_defs.ADR_AL, flashdevice_defs.ADR_WP, len(data), len(cmds))   )
        # cmds += [ ftdi.Ftdi.WRITE_EXTENDED, cmd_type, 0, data[0] ]

        for i in range(1, len(data), 1):
            # print('CL=0x%x AL=0x%x WP=0x%x ord=%s len=%d' % (flashdevice_defs.ADR_CL, flashdevice_defs.ADR_AL, flashdevice_defs.ADR_WP, hex(data[0]), len(data) )   )
            #if i == 256:
            #    cmds += [Ftdi.WRITE_SHORT, 0, ord(data[i])] # invalid call misses ftdi.....

            cmds += [ftdi.Ftdi.WRITE_SHORT, 0, ord(data[i])]   # add other bytes using WRITE_SHORT = 0x92

        if self.ftdi is None or not self.ftdi.is_connected:
            return
        # Addressfor reading page 1 this stream to ftdi is: 0x93  0x80 0x0 + 0x00 + ( 0x92 0x0 0x00   0x92 0x0 0x01 0x92 0x0 0x00 )
        #   1. 0x93 this writes ftdi-address AHigh = pin34-AC7-ALE, pin33=AC6=CLE, pin32=AC5=WP,0,0,0,0  ALow=0x00 with nand content 00 
        #   2. 0x92 this writes (keeps pin34-32)                                                         ALow=0x00 with nand content 01
        #   3. 0x92 this writes (keeps pin34-32)                                                         ALow=0x00 with nand content 00  
        #   4. 0x92 this writes (keeps pin34-32)                                                         ALow=0x00 with nand content 00 
        self.ftdi.write_data(Array('B', cmds))

    def __writestring(self, cl, al, data):
        # print('CL=0x%x AL=0x%x WP=0x%x ord=%s' % (flashdevice_defs.ADR_CL, flashdevice_defs.ADR_AL, flashdevice_defs.ADR_WP, hex(data[0]) ))
        # print('CL=0x%x AL=0x%x WP=0x%x ord=??' % (flashdevice_defs.ADR_CL, flashdevice_defs.ADR_AL, flashdevice_defs.ADR_WP ) )    

        # command NAND_CMD_READSTART = 0x30  ??? self.__write(1, 0, chr(cmd))
        # results into 
        #   NanD command 0x00 -->  1. 0x93 this writes ftdi-address AHigh = pin34-AC7-ALE, pin33=AC6=CLE, pin32=AC5=WP,0,0,0,0  ALow=0x00 with nand content 00
        #   NanD command 0x30 -->  1. 0x93 this writes ftdi-address AHigh = pin34-AC7-ALE, pin33=AC6=CLE, pin32=AC5=WP,0,0,0,0  ALow=0x00 with nand content 30

        # masks ADR_CE = 0x10 , ADR_WP = 0x20, ADR_CL = 0x40, ADR_AL = 0x80
        cmds = []
        cmd_type = 0
        if cl == 1:
            cmd_type |= flashdevice_defs.ADR_CL
        if al == 1:
            cmd_type |= flashdevice_defs.ADR_AL
        if not self.WriteProtect:
            cmd_type |= flashdevice_defs.ADR_WP

        # cmd = 4 bytes  0x92 0x00 0xAL 0xDATA
        cmds += [ftdi.Ftdi.WRITE_EXTENDED, cmd_type, 0, data[0] ]		# use first byte WRITE_EXTENDED = 0x93
        # print('WS CL=0x%x AL=0x%x WP=0x%x ord=?? lendata=%d lencmds=%d' % (flashdevice_defs.ADR_CL, flashdevice_defs.ADR_AL, flashdevice_defs.ADR_WP, len(data), len(cmds))   )
        for i in range(1, len(data), 1): # add other bytes using WRITE_SHORT = 0x92
            # print('CL=0x%x AL=0x%x WP=0x%x ord=%s len=%d' % (flashdevice_defs.ADR_CL, flashdevice_defs.ADR_AL, flashdevice_defs.ADR_WP, hex(data[0]), len(data) )   )
            #if i == 256:
            #    cmds += [Ftdi.WRITE_SHORT, 0, ord(data[i])] # invlaid call, missing ftdi... prefix
            cmds += [ftdi.Ftdi.WRITE_SHORT, 0, data[i] ]   # add other bytes using WRITE_SHORT = 0x92 0xAL 0xDATA  : 3 bytes 

        if self.ftdi is None or not self.ftdi.is_connected:
            return

        self.ftdi.write_data(Array('B', cmds))



    def __send_cmd(self, cmd):
        # print('\n__send_Command cmd=%s' % (hex(ord(chr(cmd))) ))  
        # NAND_CMD_READSTART = 0x30  ???
        self.__write(1, 0, chr(cmd))


    # addr  & number
    # self.__send_address((pageno<<16), self.AddrCycles)	# paged * 64K , 4 cycles to address start row for 2048 page 
    def __send_address(self, addr, count):
        # page 0x0000 = page     0  this translates to in readpage<<16 at          '0' --> 0x00 0x00 0x00 0x00  < - colL colH rowL RowH
        # page 0x0001 = page     1  this translates to in readpage<<16 at          '0' --> 0x00 0x00 0x01 0x00
        # page 0x00ff = page   255  this translates to in readpage<<16 at          '0' --> 0x00 0x00 0xff 0x00
        # page 0xffff = page 65535  this translates to in readpage<<16 at '4294901760' --> 0x00 0x00 0xff 0xff

        data = ''

        for _ in range(0, count, 1):    # do 4,3,2,1  --> move a value to a 4 bytes address  
                                        #      page1 = startbyte  65536 --> colH colL rowH rowL page1 = 00 00 01 00 
                                        #      page2 = startbyte 131072 --> colH colL rowH rowL page2 = 00 00 02 00 
            data += chr(addr & 0xff)    # get value byte  
            # print ('__ send_address: count=%d data=0x%x' % (count, ord(chr(addr & 0xff)) )  ) 
            addr = addr>>8				# shift next value 

        # print('\n__send_adress=%sFF' % (hex(ord(chr(addr))) ))
        # issue address 0x01 to adress page 1 via data bytes 0x00 0x00 0x01 0x00  < - colL colH rowL RowH
        self.__write(0, 1, data) # this instruct to issue address command as storedin data Page 0 = col/row = 00 00 00 00
                                 # this instruct to issue address command as storedin data Page 1 = col/row = 00 00 01 00
                                 # this instruct to issue address command as storedin data Page 1 = col/row = 00 00 02 00  

    def __get_status(self):
        self.__send_cmd(0x70)
        status = self.__read_data(1)
        if len(status) == 0: status = flashdevice_defs.NAND_STATUS_IDLE
        else: status = ord(status)
        return status

    def __read_data1(self, count) :   # read original stream
        return self.__read1(0, 0, count)

    def __read_data(self, count) :    # read per byte
        return self.__read(0, 0, count)

    def __write_data(self, data):
        # print('\n__write_data0,0=%s' % ( (hex(ord(chr(data[0]))) + hex(ord(chr(data[1])))) ) )  
        return self.__write(0, 0, data)

    def __write_datastring(self, data):
        # print('\n__write_datastring len=%d' % ( len(data)  )  )
        return self.__writestring(0, 0, data)


    def __get_id(self):
    # Does send 90h 00h to retrieve 8 bytes of which 5 show the info.
    # Samsung  new K9F1G08U0E does do: 0xec 0xf1  0x00  0x95  0x41  <>  0x41 0xec 0xf1  0x00
    # Samsung  old K9F1G08X0C does do: 0xec 0xf1  0x00  0x95  0x40  <>  0x41 0xec 0xf1  0x00
        self.Name = ''
        self.ID = 0
        self.PageSize = 0
        self.ChipSizeMB = 0
        self.EraseSize = 0
        self.Options = 0
        self.AddrCycles = 0
        self.Tsize = 0			# tranfer size for IO, default 0 = 512bytes

        if self.Debug_info:
           print('- flashdevice.__get_id: PageSize=%d' % ( self.PageSize ) ) # 0


        # samsung chip sequence: Read ID Command (90h) Device Address 1cycle 00h)
        # returns ECh (Maker) F1h (Device) 00h 95h 40h
        #	1st Byte Make Code ECh
        #	2nd Byte Device Code F1h
        #	3rd Byte Internal Chip Number io1+0, Cell Type io3+2, Number of Simultaneously Programmed Pages io5+4, Interleave io6, Cache io7
        #	4th Byte Page Size io1+0, Block Size io5+4,Redundant Area Size io2, Organization io6, Serial Access Minimum io7+io3
        #	5th Byte Plane Number io3+2, Plane Size io6-io5-io4, reserved io7+io1+io0
        # print('- flashdevice: send_cmd: 0x%x' % ( flashdevice_defs.NAND_CMD_READID ) ) # 0
        self.__send_cmd(flashdevice_defs.NAND_CMD_READID) # Read chipcommand ID 90h 00h  file /home/pafoxp/code-dumpflash/dumpflash/flashdevice_defs.py
        # print('- flashdevice: __send_address(0, 1)')  # 0
        self.__send_address(0, 1) # set address 00h (as 2nd byte) length=1

        flash_identifiers = self.__read_data(8) # get 8 bytes
        print ('getid read 1-5: 0x%x 0x%x  0x%x  0x%x  0x%x  0x%x  0x%x  0x%x' % (flash_identifiers[0], flash_identifiers[1], flash_identifiers[2], flash_identifiers[3], flash_identifiers[4], flash_identifiers[5], flash_identifiers[6], flash_identifiers[7] ) )
        # returns getid read 1-5: 0xec 0xf1  0x00  0x95  0x41 <> 0xec 0xf1  0x00 for K9F1G08U0E (new,....x41= 21nM )
        # returns getid read 1-5: 0xec 0xf1  0x00  0x95  0x40 <> ?? ?? ?? for K9F1G08X0C (old), .....x40)

        # 0 1st Maker: ECh - Samsung
        # 1 2nd Device Code = F1h
        # 2 3rd 0b0000 0000:  Byte Internal Chip Number io1+0=0=1, Cell Type io3+2=0=2ndLC, Number of Simultaneously Programmed Pages io5+4=0=1, Interleave io6=0=n/a, Cache io7=0=n/a
        # 3 4th 0b1001 0101:  Page Size io1+0=01=8kb, Block Size io5+4=11=512kb,Redundant Area Size io2=0=8byte/512, Organization io6=0=x8, Serial Access Minimum io7+io3=11=reserved
        # 4 5th 0b0100 0001:  Plane Number io3+2=0=1, Plane Size io6-io5-io4=100=1Gbit, reserved io7+io1+io0=001=n/a  

        # Single Chip, 1Gbit=128MB=134217728bytes,  , 64pages/block bits per cell = 4, single-layer
		# oob space 8/512 bytes --> ((128⋅1024⋅1024)/512)*8 = 262144*8 = 2097152 bytes (total data+oob=136314880 bytes)

        if not flash_identifiers:
            return False

        # print('Extid3 = 0x%x, PageSize=%d' % (flash_identifiers[3], self.PageSize ) ) # 0x95 & 0
        # check /home/pafoxp/code-dumpflash/dumpflash/flashdevice_defs.py
        self.Tsize = 0
        for device_description in flashdevice_defs.DEVICE_DESCRIPTIONS:  #  EC-F1-09541 = 
            if device_description[1] == flash_identifiers[1]: # (was flash_identifiers[0] 
                # ["NAND 128MiB 3,3V 8-bit", 0xF1, 0, 128, 0, LP_OPTIONS, 4],
                (self.Name, self.ID, self.PageSize, self.ChipSizeMB, self.EraseSize, self.Options, self.AddrCycles) = device_description
                self.Identified = True
                self.Tsize = 512
                if self.Debug_info: print('-- device_description Name=%s PageSize=%d ID=%x, Tsize=%d ' % (self.Name, self.PageSize, self.ID, self.Tsize ) ) # 0
                break

        # print('Extid3 = 0x%x, PageSize=%d' % (flash_identifiers[3], self.PageSize ) ) #  & 256

        if not self.Identified:
            return False

        #Check ONFI  adress 0x20 with readid  (n/a with Samsung)
        self.__send_cmd(flashdevice_defs.NAND_CMD_READID)
        self.__send_address(0x20, 1)
        onfitmp = self.__read_data(4)

        onfi = (onfitmp == [0x4F, 0x4E, 0x46, 0x49])	

        if onfi:
            self.__send_cmd(flashdevice_defs.NAND_CMD_ONFI)
            self.__send_address(0, 1)
            self.__wait_ready()
            onfi_data = self.__read_data(0x100)
            onfi = onfi_data[0:4] == [0x4F, 0x4E, 0x46, 0x49]

        if flash_identifiers[0] == 0x98:
            self.Manufacturer = 'Toshiba'
        elif flash_identifiers[0] == 0xec:    # Samsung
            self.Manufacturer = 'Samsung'
        elif flash_identifiers[0] == 0x04:
            self.Manufacturer = 'Fujitsu'
        elif flash_identifiers[0] == 0x8f:
            self.Manufacturer = 'National Semiconductors'
        elif flash_identifiers[0] == 0x07:
            self.Manufacturer = 'Renesas'
        elif flash_identifiers[0] == 0x20:
            self.Manufacturer = 'ST Micro'
        elif flash_identifiers[0] == 0xad:
            self.Manufacturer = 'Hynix'
        elif flash_identifiers[0] == 0x2c:
            self.Manufacturer = 'Micron'
        elif flash_identifiers[0] == 0x01:
            self.Manufacturer = 'AMD'
        elif flash_identifiers[0] == 0xc2:
            self.Manufacturer = 'Macronix'
        else:
            self.Manufacturer = 'Unknown'

        idstr = ''
        for idbyte in flash_identifiers:
            idstr += "%X" % idbyte

        if idstr[0:4] == idstr[-4:]:	# n/a: 0xec 0xf1  0x00  0x95  0x41 <>  0x41 0xec 0xf1  0x00
            idstr = idstr[:-4]
            if idstr[0:2] == idstr[-2:]:
                idstr = idstr[:-2]

        self.IDString = idstr			# 0xec 0xf1  0x00  0x95  0x41 0xec 0xf1  0x00
        self.IDLength = int(len(idstr) / 2) # 4 bytes


        # 2 3rd 0b0000 0000:  Byte Internal Chip Number io1+0=0=1, Cell Type io3+2=0=2ndLC, Number of Simultaneously Programmed Pages io5+4=0=1, Interleave io6=0=n/a, Cache io7=0=n/a
        self.BitsPerCell = self.get_bits_per_cell(flash_identifiers[2])  # returns 1
        # print('Extid3 = 0x%x, PageSize=%d' % (flash_identifiers[3], self.PageSize ) ) # 0x95

        if self.PageSize == 0:  # initial , set as 2048 (after corrections searchig fr id=0xF1)
            # 3 4th 0b1001 0101:  Page Size io1+0=01=8kb, Block Size io5+4=11=512kb,Redundant Area Size io2=0=8byte/512, Organization io6=0=x8, Serial Access Minimum io7+io3=11=reserved
            extid = flash_identifiers[3] # 3rd byte: 0x95 = 0b1001 0101
            # print('Extid3 = 0x%x ' % (extid) ) # 0x95
            if ((self.IDLength == 6) and (self.Manufacturer == "Samsung") and (self.BitsPerCell > 1)):  # this is called at sh67 fo waveshare chip
                self.Pagesize = 2048 << (extid & 0x03)
                extid >>= 2
                if (((extid >> 2) & 0x04) | (extid & 0x03)) == 1:
                    self.OOBSize = 128
                if (((extid >> 2) & 0x04) | (extid & 0x03)) == 2:
                    self.OOBSize = 218
                if (((extid >> 2) & 0x04) | (extid & 0x03)) == 3:
                    self.OOBSize = 400
                if (((extid >> 2) & 0x04) | (extid & 0x03)) == 4:
                    self.OOBSize = 436
                if (((extid >> 2) & 0x04) | (extid & 0x03)) == 5:
                    self.OOBSize = 512
                if (((extid >> 2) & 0x04) | (extid & 0x03)) == 6:
                    self.OOBSize = 640
                else:
                    self.OOBSize = 1024
                extid >>= 2
                self.EraseSize = (128 * 1024) << (((extid >> 1) & 0x04) | (extid & 0x03))

            elif ((self.IDLength == 6) and (self.Manufacturer == 'Hynix') and (self.BitsPerCell > 1)):
                self.PageSize = 2048 << (extid & 0x03)
                extid >>= 2
                if (((extid >> 2) & 0x04) | (extid & 0x03)) == 0:
                    self.OOBSize = 128
                elif (((extid >> 2) & 0x04) | (extid & 0x03)) == 1:
                    self.OOBSize = 224
                elif (((extid >> 2) & 0x04) | (extid & 0x03)) == 2:
                    self.OOBSize = 448
                elif (((extid >> 2) & 0x04) | (extid & 0x03)) == 3:
                    self.OOBSize = 64
                elif (((extid >> 2) & 0x04) | (extid & 0x03)) == 4:
                    self.OOBSize = 32
                elif (((extid >> 2) & 0x04) | (extid & 0x03)) == 5:
                    self.OOBSize = 16
                else:
                    self.OOBSize = 640
                tmp = ((extid >> 1) & 0x04) | (extid & 0x03)
                if tmp < 0x03:
                    self.EraseSize = (128 * 1024) << tmp
                elif tmp == 0x03:
                    self.EraseSize = 768 * 1024
                else: self.EraseSize = (64 * 1024) << tmp
            else:
                # 3rdbyte= byte 4 is 0b1001 0101:  Page Size io1+0=01=8kb, Block Size io5+4=11=512kb,Redundant Area Size io2=0=8byte/512, Organization io6=0=x8, Serial Access Minimum io7+io3=11=reserved
                # extid 0b1001 1001 = 0x95>>2 = 0b0010 0101 = 37 --> 0x25 --> 0b0010 0101
                self.PageSize = 1024 << (extid & 0x03)  # 0x95 & 0x03 = 0b0000 0001 & 0x03 = 512
                extid >>= 2  # bitwise right shift 0x95 ==> 0x25
                self.OOBSize = (8 << (extid & 0x01)) * (self.PageSize >> 9)  # 8 << (0x95&0x01)*(0>>9) = 8 bytes
                extid >>= 2 # 0x25>>2 = 0x09 = 0b0000 1001
                self.EraseSize = (64 * 1024) << (extid & 0x03) # = 65535 = 0xFFFF << (0x09&0x03) = 131072 = 128KB

                # n/a
                if ((self.IDLength >= 6) and (self.Manufacturer == "Toshiba") and (self.BitsPerCell > 1) and ((flash_identifiers[5] & 0x7) == 0x6) and not flash_identifiers[4] & 0x80):
                    self.OOBSize = 32 * self.PageSize >> 9
        else:
            self.OOBSize = int(self.PageSize / 32)  #  2048 /32 = 64

        if self.PageSize > 0:  # 2048
            self.PageCount = int(self.ChipSizeMB*1024*1024 / self.PageSize) 
        # print('PageCount=%d, self.ChipSizeMB=%d' % (self.PageCount, self.ChipSizeMB)) # PageCount=65536, self.ChipSizeMB=128

        self.RawPageSize = self.PageSize + self.OOBSize   # 512 + 8 = 520 bytes
        self.BlockSize = self.EraseSize # 131072 bytes = 128KB
        self.BlockCount = int((self.ChipSizeMB*1024*1024) / self.BlockSize) # 1024

        if self.Debug_info:
           print('--- has PageSize=%d, OOBSize=%d , RawPageSize=%d , BlockSize=EraseSize=%d, BlockCount=%d' % (self.PageSize, self.OOBSize, self.RawPageSize, self.BlockSize, self.BlockCount))
        # PageSize=2048, OOBSize=64 , RawPageSize=2112 , BlockSize=EraseSize=131072 BlockCount=1024

        if self.BlockCount <= 0:
            self.PagePerBlock = 0
            self.RawBlockSize = 0
            return False

        self.PagePerBlock = int(self.PageCount / self.BlockCount)
        self.RawBlockSize = self.PagePerBlock*(self.PageSize + self.OOBSize)
        if self.Debug_info:
           print('--- PagePerBlock=%d , RawBlockSize=%d' % (self.PagePerBlock, self.RawBlockSize) )
        # PagePerBlock=64 , RawBlockSize=135168

        return True

    def is_initialized(self):
        return self.Identified

    def set_use_ansi(self, use_ansi):
        self.UseAnsi = use_ansi

    def is_slow_mode(self):
        return self.Slow

    def get_bits_per_cell(self, cellinfo):
        # 2 3rd 0b0000 0000:  Byte Internal Chip Number io1+0=0=1, Cell Type io3+2=0=2ndLC, Number of Simultaneously Programmed Pages io5+4=0=1, Interleave io6=0=n/a, Cache io7=0=n/a
        # returns 1
        bits = cellinfo & flashdevice_defs.NAND_CI_CELLTYPE_MSK
        bits >>= flashdevice_defs.NAND_CI_CELLTYPE_SHIFT
        return bits+1

    def dump_info(self):
        print('Full ID:\t', self.IDString)
        print('ID Length:\t', self.IDLength)
        print('Name:\t\t', self.Name)
        print('ID:\t\t0x%x' % self.ID)
        print('Page size:\t 0x{0:x}({0:d})'.format(self.PageSize))
        print('Transfer size:\t', self.Tsize)
        print('OOB size:\t0x{0:x} ({0:d})'.format(self.OOBSize))
        print('Page count:\t0x%x' % self.PageCount)
        print('Size:\t\t0x%x' % self.ChipSizeMB)
        print('Erase size:\t0x%x' % self.EraseSize)
        print('Block count:\t', self.BlockCount)
        print('-block size:\t', int(self.PageCount/self.BlockCount) )
        print('Options:\t', self.Options)
        print('Address cycle:\t', self.AddrCycles)
        print('Bits per Cell:\t', self.BitsPerCell)
        print('Manufacturer:\t', self.Manufacturer)
        print('')

    def check_bad_blocks(self): # not called by routines here, dumpflash uses flashimage.py version   
        bad_blocks = {}
#        end_page = self.PageCount

        if self.PageCount%self.PagePerBlock > 0.0:
            self.BlockCount += 1

        curblock = 1
        for block in range(0, self.BlockCount):
            page += self.PagePerBlock
            curblock = curblock + 1
            if self.UseAnsi:
                sys.stdout.write('flashdevice: Checking bad blocks %d Block: %d/%d\n\033[A' % (curblock / self.BlockCount*100.0, curblock, self.BlockCount))
            else:
                sys.stdout.write('flashdevice: Checking bad blocks %d Block: %d/%d\n' % (curblock / self.BlockCount*100.0, curblock, self.BlockCount))

            for pageoff in range(0, 2, 1):
                oob = self.read_oob(page+pageoff)

                if oob[5] != b'\xff':
                    print('ooblen=', len(oob) ,', Bad block found:', block)
                    bad_blocks[page] = 1
                    break

        print('flashdevice: Checked %d blocks and found %d bad blocks' % (block+1, len(bad_blocks)))
        return bad_blocks



    def read_oob(self, pageno, oob_size=0): # //here_read_oob adapted to segmentation of 16 bytes that dopes read oob
        bytes_to_send = []
        bytes_to_read = bytearray()

        # Nand Page read is initiated by writing 00h - OxCol1 0xCol2 0xRow1 0xRow6 - 30h  followed by read for 64 bytes until count is reached 
        if self.Options & flashdevice_defs.LP_OPTIONS:           # execute for Samsung
            if oob_size < 1: oob_size = self.OOBSize
            # print ('read_oob: pageno=%d oobsize=%d, tsize=16' % (pageno, oob_size))

            # bytes_to_read = self.read_page_segment(self, address, length, cycles, tsize): # //here_readpage segmentation
            # print ('--> read_oob: pageno=%d, address=%d oobsize=%d, tsize=16, read=%d' % (pageno,((pageno<<16)+self.PageSize),self.OOBSize, len(bytes_to_read)))
            bytes_to_read = self.read_page_segment( (pageno<<16)+self.PageSize, oob_size, self.AddrCycles, 16)
            # self.__wait_ready()

            # time.sleep(0.1)
            # self.__send_cmd(flashdevice_defs.NAND_CMD_READ0)     # NAND_CMD_READ0 = 0x00
            # self.__send_address(((pageno<<16)+self.PageSize), self.AddrCycles)	 # paged * 64K , 4 cycles
            # self.__send_cmd(flashdevice_defs.NAND_CMD_READSTART) # NAND_CMD_READSTART = 0x30 
            # time.sleep(0.02)
            # self.__wait_ready()
            # bytes_to_send += self.__read_data(oob_size)	     # 64bytes  via return self.__read(0, 0, 64) -- > __read(self, cl, al, count

        else: # Note this else NAND_CMD_READ_OOB function does not exist on Samsung chip
            self.__send_cmd(flashdevice_defs.NAND_CMD_READ_OOB)		# NAND_CMD_READ_OOB = 0x50
            self.__wait_ready()
            self.__send_address(pageno<<8, self.AddrCycles)  # 4 cycles
            self.__wait_ready()
            bytes_to_send += self.__read_data()	 # 64bytes  via return self.__read(0, 0, 64) -- > __read(self, cl, al, count

        data = ''

        # for ch in bytes_to_send:
        for ch in bytes_to_read:
            data += chr(ch)
        return data


    def read_page_offset(self, pageno, length, offset): # //here7 readpage at specific offset 
        if offset > self.PageSize: offset = self.PageSize
        address = ((self.PageSize+self.OOBSize) * pageno)+offset
        
        if length < 1: length = self.PageSize
        if (length+offset) >= (self.PageSize+self.OOBSize): length = ((self.PageSize+self.OOBSize) - offset) 
        bytes_to_read = bytearray()
        addr_len = offset
        tsize = 1
        cycles = 4
        # print ('--> read segment page=', (int((address+1)/2112)), 'start=', addr_len, 'length=', length, 'tsize=', tsize  )

        err = self.__get_status()
        print('Status at' , pageno, ' state=',  err)

        print ('--> read offset0 page %d address 0x%x,  offset=%d length=%d, tsize=%d, length=%d\n' % (pageno, (pageno<<16)+addr_len, offset, addr_len, 1, length) )
        segment_to_read = bytearray()
        while length > 0: # //here6
            read_len = 1
            # print ('\n--> read offset1 page %d address 0x%x,  offset=%d length=%d, tsize=%d, read len=%d' % (pageno, address, offset, addr_len, 1, len(segment_to_read)) )
            if read_len > length: read_len = length           # if remaining length less than chunksize
            # print ('--> read offset2 page %d address 0x%x,  offset=%d length=%d, tsize=%d, read len=%d' % (pageno, address, offset, addr_len, 1, len(segment_to_read) ) )
            # self.__wait_ready()  # test if this improves
            self.__send_cmd(flashdevice_defs.NAND_CMD_READ0)  # NAND_CMD_READ0 = 0x00 -->  set I/O pins CLE 33

            # self.__send_address(address, cycles)  # (0--> 0, 1 --> 65536, 2 --> 131072 ) with Address cycle: 4 set I/O pins ALE 34
            self.__send_address((pageno<<16)+addr_len, cycles)  # (0--> 0, 1 --> 65536, 2 --> 131072 ) with Address cycle: 4 set I/O pins ALE 34

            self.__send_cmd(flashdevice_defs.NAND_CMD_READSTART)  # NAND_CMD_READSTART = 0x30 -->  set I/O pins CLE 33
            self.__wait_ready()  # test if this improves
            segment_to_read = self.__read_data(read_len)

            if (len(bytes_to_read) ) < 9:
                print ('--> read offset3 page %d address 0x%x,  offset=%d addr_len=%d, tsize=%d, addrlen=%d, bytelength=%d 1st byte=0x%x' % (pageno, (pageno<<16)+addr_len, offset, addr_len, 1, length, len(segment_to_read), segment_to_read[0] ) )

            bytes_to_read += segment_to_read
            address += read_len
            addr_len += read_len
            length -= 1
 
        return bytes_to_read


    def read_page_segment(self, address, length, cycles, tsize): # //here5_readpage segmentation
        if self.Debug_info:
           print ('--> read_page_segment address 0x%x, length=%d, tsize=%d       ' % (address, length, tsize) )
        bytes_to_read = bytearray()
        segment_to_read = bytearray()
        addr_len = 0
        # print ('--> read segment page=', (int((address+1)/2112)), 'start=', addr_len, 'length=', length, 'tsize=', tsize  )
        while length > 0: # //here6
            read_len = tsize
            if read_len > length: read_len = length           # if remaining length less than chunksize
            # self.__wait_ready()  # test if this improves
            self.__send_cmd(flashdevice_defs.NAND_CMD_READ0)  # NAND_CMD_READ0 = 0x00 -->  set I/O pins CLE 33
            # self.__wait_ready()  # test if this improves
            self.__send_address(address, cycles)  # (0--> 0, 1 --> 65536, 2 --> 131072 ) with Address cycle: 4 set I/O pins ALE 34
            # self.__wait_ready()  # test if this improves
            self.__send_cmd(flashdevice_defs.NAND_CMD_READSTART)  # NAND_CMD_READSTART = 0x30 -->  set I/O pins CLE 33
            # self.__wait_ready()  # test if this improves
            segment_to_read = self.__read_data(read_len)
            bytes_to_read += segment_to_read
            if self.Debug_info and len(bytes_to_read) < 10:  # used for/by testr
               print('   -- read_page_segment: address=%d len(bytes_to_read)=%d, len(segment_to_read)=%d, data=0x%x ' % (address, len(bytes_to_read)-1, len(segment_to_read), segment_to_read[0]  ) )

            # segment_to_read += b'\x00' # for test

            # bytes_to_read += self.__read_data(read_len+16)[:-16] # 2048 + 64 + 16 = 2128 - 16 = 2112
            # time.sleep(1)
            # self.__wait_ready()  # test if this improves

            # if segment_to_read.find(0x00) < 0:
            # print ('--> read segment page=', (int((address+1)/2112)), 'start=', addr_len, 'length=', read_len, 'tsize=', tsize , 'remaining=', length-read_len )

            # used at initial development, checking a virgin nandchip that has xFF and wehn we read x00 this is a shift error
            # if 0x00 in segment_to_read:  # check if we have zeroes (during testing)
            #   if self.Debug_info:
            #      print ('read 0x00 in segment page=', (int((address+1)/2112)), 'start=', addr_len, 'length=', read_len, 'tsize=', tsize , 'remaining=', length-read_len )

            err = self.__get_status()  ## added to force som delay as ftdi2232 tends to be too slow in reading complex bytes
            if (self.Debug_info and len(bytes_to_read) < 10) or err & flashdevice_defs.NAND_STATUS_IDLE:  # used for/by testr and info status
              print('... NAND_STATUS_IDLE status=%d, at address=0x%x page=%d/%d data=0x%x' % (err, address, address>>16, (address&0xffff), segment_to_read[0] ) )

            address += read_len
            addr_len += read_len
            length -= tsize

            # if tsize > 1: tsize = int(tsize / 2)
 
        return bytes_to_read

    def read_page(self, pageno, remove_oob = False, tsize = 512): # //here_readpage segmentation
    # called via for page in range(start_page, end_page, 1) 
    # Does do 0x00  byteadress-in4bytesutes 0x30
        bytes_to_read = bytearray()

        # print ( 'bytes_to_readinfo=', bytes_to_read.buffer_info())
        # the memoryview, the newbuffer and getbuffer functions are removed from multiarray in Py3 : their functionality is taken over by the new memoryview object.

        # readpage = 00h .. .. .. 30h     <-- dataread

        # command NAND_CMD_READ0 = 0x00
        # address for reading page 1 this stream to ftdi is: 0x93  0x80 0x0 + 0x00 + ( 0x92 0x0 0x00   0x92 0x0 0x01 0x92 0x0 0x00 )
        #   1. 0x93 this writes ftdi-address AHigh = pin34-AC7-ALE, pin33=AC6=CLE, pin32=AC5=WP,0,0,0,0  ALow=0x00 with nand content 00 
        #   2. 0x92 this writes (keeps pin34-32)                                                         ALow=0x00 with nand content 01
        #   3. 0x92 this writes (keeps pin34-32)                                                         ALow=0x00 with nand content 00  
        #   4. 0x92 this writes (keeps pin34-32)                                                         ALow=0x00 with nand content 00 
        # command NAND_CMD_READSTART = 0x30
        #
        # self.__read_data(read_len=2112) # for packet2048 + oob64
        #        read data self.__read(0, 0, count) --> #byte1 0x91 0x00 0x00  + #bytes-1  0x90 0x00 ... ... + 0x87

        if self.Options & flashdevice_defs.LP_OPTIONS:
            # print ('read_page:  send_address=%d \t\t, self.AddrCycles=%d, PageSize=%d, Tsize=%d' % (pageno<<16, self.AddrCycles, self.PageSize, tsize ) )

            # read_page:  send_address=0 , self.AddrCycles=4, PageSize=2048
            # read_page:  send_address=65536 , self.AddrCycles=4, PageSize=2048
            # read_page:  send_address=131072 , self.AddrCycles=4, PageSize=2048

            # this is done: CMD0 = reset, send address in for page 0=0, 1=65636, 2=131072, 3=196608

            # Nand Page read is initiated by writing 00h - OxCol1 0xCol2 0xRow1 0xRow6 - 30h  followed by read for 2112bytes until count is reached 
            # PageSize=2048, OOBSize=64 , RawPageSize=2112, PageCount: 65536, BlockSize=EraseSize=131072, BlockCount=1024 
            # (((0xffff<<16)>>0)>>0) 


            # s = Substr(s, beginning, LENGTH)

            if tsize > 0: # segmentation  (((1<<16)>>8)>>8)&0xff page 1 :    00 01

                addr_len = 2048                                  # skip data
                length = (self.PageSize+self.OOBSize)-addr_len   # output OOB

                addr_len = (2048-192)                              # skip these data
                length = (self.PageSize)-addr_len                # no OOB

                addr_len = 0                                  # skip data
                length = (self.PageSize+self.OOBSize)-addr_len   # output OOB

                # tsize=16 & result in 0 defects for 10, 100 & 1000 & 10000 pages 

                addr_len = 0
                length = (self.PageSize+self.OOBSize)   # output OOB
                #		python3 dumpflash.py -t 700 -o dump11apr23_00u13.bin -p 0 10000 -c r  # 873423 bytes/s
                addr_len = 0
                length = (self.PageSize+self.OOBSize)   # output OOB
                #		python3 dumpflash.py -t 512 -o dump11apr23_00u13.bin -p 0 10000 -c r  # 650627 bytes/s
 
                # Only do OOB
                addr_len = self.PageSize
                length = self.OOBSize
                # 		python3 dumpflash.py -t 22 -o dump11apr23_00u13.bin -p 0 10000 -c r  # 32134 bytes/s (640KB out)

                # 
                addr_len = 0            
                length = self.PageSize  # 2112
                # 		python3 dumpflash.py -t 704 -o dump11apr23_00u13.bin -p 0 10000 -c r  # 866913 bytes/s ()

                addr_len = self.PageSize
                length = self.OOBSize
                # 		python3 dumpflash.py -t 16 -o dump11apr23_00u13.bin -p 0 65535 -c r  # 25300 bytes/s ()

                addr_len = 0
                length = self.PageSize+self.OOBSize
                # 		python3 dumpflash.py -t 708 -o dump11apr23_00u13.bin -p 0 65535 -c r  # 856582 bytes/s ()


                # 2112  column 0x0840 =    0000 1000 0100 0000  = 12 adress bytes --> A11 to A0 for column
                # 65535 page   0xffff =    1111 1111 1111 1111  = 16 adress bytes --> A11 to A0 for column

                addr_len = self.PageSize
                length = self.OOBSize
                # 		python3 dumpflash.py -t 22 -o dump11apr23_00u13.bin -p 0 65535 -c r  # 32459 bytes/s (1000p/s)

                addr_len = 0
                length = self.PageSize+self.OOBSize
                # 		python3 dumpflash.py -t 707 -o dump11apr23_00u13.bin -p 0 65535 -c r  # 856582 bytes/s (some start errors)
                # 		python3 dumpflash.py -t 700 -o dump11apr23_00u13.bin -p 0 65535 -c r  # 877957 bytes/s ()

                # print (' Length=', length, 'Offset=', addr_len, 'tsize=', tsize  )

                if remove_oob: length = length - self.OOBSize

#                                def read_page_segment(self, address, length, cycles, tsize): # //here_readpage segmentation
                bytes_to_read = self.read_page_segment( (pageno<<16)+addr_len, length, self.AddrCycles, tsize)
#                while length > 0:
#                    read_len = tsize
#                    if length < tsize: read_len = length
#                    # self.__wait_ready()  # test if this improves
#                    print ('read length=', read_len, 'start=', addr_len, 'tsize=', tsize , 'remaining=', length-read_len )
#                    self.__send_cmd(flashdevice_defs.NAND_CMD_READ0)  # NAND_CMD_READ0 = 0x00 -->  set I/O pins CLE 33
#                    # self.__wait_ready()  # test if this improves
#                    self.__send_address((pageno<<16)+addr_len, self.AddrCycles)  # (0--> 0, 1 --> 65536, 2 --> 131072 ) with Address cycle: 4 set I/O pins ALE 34
#                    # self.__wait_ready()  # test if this improves
#                   self.__send_cmd(flashdevice_defs.NAND_CMD_READSTART)  # NAND_CMD_READSTART = 0x30 -->  set I/O pins CLE 33
#                    #bytes_to_read += self.__read_data(read_len)
#                    # bytes_to_read += self.__read_data(read_len+16)[:-16] # 2048 + 64 + 16 = 2128 - 16 = 2112
#                    # time.sleep(1)
#                    # self.__wait_ready()  # test if this improves
#                    addr_len += read_len
#                    length -= tsize
                    # if tsize > 1: tsize = int(tsize / 2)

            else:
                self.__send_cmd(flashdevice_defs.NAND_CMD_READ0)  # NAND_CMD_READ0 = 0x00 -->  set I/O pins CLE 33
                self.__send_address(pageno<<16, self.AddrCycles)  # (0--> 0, 1 --> 65536, 2 --> 131072 ) with Address cycle: 4 set I/O pins ALE 34
                self.__send_cmd(flashdevice_defs.NAND_CMD_READSTART)  # NAND_CMD_READSTART = 0x30 -->  set I/O pins CLE 33
                length = self.PageSize + self.OOBSize
                if self.PageSize > 0x1000:	# > 4096            # loop for page sizes > 4096
                    while length > 0:
                        read_len = 0x1000
                        if length < 0x1000:
                            read_len = length
                        bytes_to_read += self.__read_data(read_len)
                        length -= 0x1000
                else:
                #   -->this is executed for 2048+64 bytes = 2112
                    # bytes_to_read = self.__read_data(self.PageSize+self.OOBSize)  # 2048 + 64 = 2112 //here
                    bytes_to_read = self.__read_data(self.PageSize+self.OOBSize)  # 2048 + 64 = 2112
                    self.__wait_ready()  # test if this improves
                    #  does do return self.__read(0, 0, count)
                 #d: Implement remove_oob

        else:
            # Note this sequence is NOT supported for Samsung chip
            self.__send_cmd(flashdevice_defs.NAND_CMD_READ0)
            self.__wait_ready()
            self.__send_address(pageno<<8, self.AddrCycles)
            self.__wait_ready()
            bytes_to_read += self.__read_data(self.PageSize/2)

            self.__send_cmd(flashdevice_defs.NAND_CMD_READ1)
            self.__wait_ready()
            self.__send_address(pageno<<8, self.AddrCycles)
            self.__wait_ready()
            bytes_to_read += self.__read_data(self.PageSize/2)

            if not remove_oob:
                self.__send_cmd(flashdevice_defs.NAND_CMD_READ_OOB)
                self.__wait_ready()
                self.__send_address(pageno<<8, self.AddrCycles)
                self.__wait_ready()
                bytes_to_read += self.__read_data(self.OOBSize)

		# >>> x = "Hello World!" 
		# >>> x[2:] 'llo World!'
		# >>> x[:2] 'He'
		# >>> x[:-2] 'Hello Worl'
		# >>> x[-2:] 'd!'
		# >>> x[2:-2] 'llo Worl'

        # //here_oobstrip
        # return bytes_to_read[-64:] # oob parts
        return bytes_to_read

    def read_seq(self, pageno, remove_oob = False, raw_mode = False):
        page = []
        # construct 00h 0xColH 0xColL 0xRwoH 0xRowL 
        self.__send_cmd(flashdevice_defs.NAND_CMD_READ0)
        self.__wait_ready()
        self.__send_address(pageno<<8, self.AddrCycles)
        self.__wait_ready()

        bad_block = False

        for i in range(0, self.PagePerBlock, 1):
            page_data = self.__read_data(self.RawPageSize)

            if i in (0, 1):
                if page_data[self.PageSize + 5] != 0xff:
                    bad_block = True

            if remove_oob:
                page += page_data[0:self.PageSize]
            else:
                page += page_data

            self.__wait_ready()

        if self.ftdi is None or not self.ftdi.is_connected:
            return ''

         #  ftdi.Ftdi.SET_BITS_HIGH (0xValue,0xDirection)  0x82,0xValue,0xDirection
         #     This will setup the direction of the high 4 lines and 
         #     force a value on the bits that are set as output. 
         #     A '1' in the Direction byte will make that bit an output.
         # The low byte would be ADBUS 7-0, and the high byte is BDBUS 7-0.
        # self.ftdi.write_data(Array('B', [ftdi.Ftdi.SET_BITS_HIGH, 0x0, 0x1]))   # SET_BITS_HIGH = 0x82    # Change MSB GPIO output

        self.ftdi.write_data(Array('B', [ftdi.Ftdi.SET_BITS_HIGH, 0x1, 0x1]))   # SET_BITS_HIGH = 0x82    # Change MSB GPIO output
        self.ftdi.write_data(Array('B', [ftdi.Ftdi.SET_BITS_HIGH, 0x0, 0x1]))   # pin 45 NanD Chip-Enable Low Output

        data = ''

        if bad_block and not raw_mode:
            print('\nSkipping bad block at %d' % (pageno / self.PagePerBlock))
        else:
            for ch in page:
                data += chr(ch)

        return data

    def erase_block_by_page(self, pageno):

        if not self.Debug_info:
            self.WriteProtect = False
        else: 
            self.WriteProtect = True
            print('   Write protection for erase_block_by_page is active in -v mode.')

        # Block Erase 60h D0h  Block Erase : (128K + 4K)Byte, only the two row address cycles are used
        self.__send_cmd(flashdevice_defs.NAND_CMD_ERASE1)  # NAND_CMD_ERASE2 = 0x60 1st Cycle
        self.__send_address(pageno, self.AddrCycles)       # Note: only the two row address cycles are used
        self.__send_cmd(flashdevice_defs.NAND_CMD_ERASE2)  # NAND_CMD_ERASE2 = 0xd0 2nd Cycle
        self.__wait_ready()
        err = self.__get_status()

        if err & flashdevice_defs.NAND_STATUS_NOT_PROTECTED and not self.WriteProtect:
           print('Write protection active, is WP-pin connected to GND ?', pageno, ' error=',  err)
        else:
           if err != 64 or self.Debug_info:
              print ('  Issue erase_block_by_page: pageno=', pageno, ' block#', int(pageno/self.PagePerBlock), ', completed, retcode=', err, '\n' )

        self.WriteProtect = True

        return err

    def write_page(self, pageno, data):
        # 	summary: self.__send_cmd(flashdevice_defs.NAND_CMD_SEQIN) 	# NAND_CMD_SEQIN    = 0x80
        # 	self.__send_address(pageno<<16, self.AddrCycles)     		# construct 0xColH 0xColL 0xRowH 0xRowL
        #   self.__write_datastring(data)  --> return self.__writestring(0, 0, data)  # 0,0 NO CLacch and No ALatch
        #---#       cmds += [ftdi.Ftdi.WRITE_EXTENDED, cmd_type, 0, data[0] ]		# use first byte WRITE_EXTENDED = 0x93
            #       cmds += [ftdi.Ftdi.WRITE_SHORT, 0, data[i] ]                     # add other bytes using WRITE_SHORT = 0x92 0xAL 0xDATA  : 3 bytes 
            #       self.__send_cmd(flashdevice_defs.NAND_CMD_PAGEPROG)  		# NAND_CMD_PAGEPROG = 0x10
            #
            #---#   self.ftdi.write_data(Array('B', cmds))          In MPSSE mode, data contains the sequence of MPSSE commands and  data.
		        #   file: /home/pafoxp/code-dumpflash/pyftdi-0.29.0/pyftdi/ftdi.py
		        #                                                   Data buffer is split into chunk-sized blocks before being sent over the USB bus.
		        #---# 
					#	offset = 0
					#	size = len(data)
					#	try:
					#		while offset < size:
					#		    write_size = self.writebuffer_chunksize
					#		    if offset + write_size > size:
					#		        write_size = size - offset
					#		    length = self._write(data[offset:offset+write_size])
					#		    if length <= 0:
					#		        raise FtdiError("Usb bulk write error")
					#		    offset += length
					#		return offset

					#	if self.ftdi is None or not self.ftdi.is_connected:
					#		return



        err = 0
        self.WriteProtect = False    # write protect inactive  

        self.DebugPtro = False
        self.writeOoB = True  # Not used here when samsunng chip ID was read

        if self.Options & flashdevice_defs.LP_OPTIONS:  # executed for Samsun NandD
            if self.DebugPtro:
               print('Write init of ', pageno)

            # Samsung Program Flow Chart: Write 80h Write Address Write Data Write 10h Read Status Register
            self.__send_cmd(flashdevice_defs.NAND_CMD_SEQIN)     # NAND_CMD_SEQIN = 0x80
            self.__wait_ready()
            self.__send_address(pageno<<16, self.AddrCycles)     # construct 0xColH 0xColL 0xRowH 0xRowL
            self.__wait_ready()
            self.__write_datastring(data)
            self.__send_cmd(flashdevice_defs.NAND_CMD_PAGEPROG)  # NAND_CMD_PAGEPROG = 0x10
            self.__wait_ready()
            err = self.__get_status()
            # print('Getstatus of %d Pagesize=%d PAGEPROG' % (pageno, self.PageSize) )
            if err & flashdevice_defs.NAND_STATUS_FAIL:
               print('Failed to write', pageno, ' error=',  err)

        else:
            # Not used for/with Samsung Chip
            while 1:
                # problem as this writes the first 256 bytes of file..... and routine uses word for one
                if self.DebugPtro:
                    print('Write 1st half of %d Pagesize=%d block %d:%d' % (pageno, self.PageSize, 0, 256) )
                self.__send_cmd(flashdevice_defs.NAND_CMD_READ0)
                self.__send_cmd(flashdevice_defs.NAND_CMD_SEQIN)
                self.__wait_ready()
                self.__send_address(pageno<<8, self.AddrCycles)
                self.__wait_ready()

                self.__write_datastring(data[0:256])
                # print('Write 1st half of %d Pagesize=%d PAGEPROG' % (pageno, self.PageSize) )
                self.__send_cmd(flashdevice_defs.NAND_CMD_PAGEPROG)
                err = self.__get_status()
                # print('Getstatus of %d Pagesize=%d PAGEPROG' % (pageno, self.PageSize) )
                if err & flashdevice_defs.NAND_STATUS_FAIL:
                    print('Failed to write 1st half of ', pageno, err)
                    continue
                break

            # Not used for/with Samsung Chip
            while 1:
                # print('Write 2nd half of %d Pagesize=%d' % (pageno, self.PageSize) )
                if self.rPtro:
                    print('Write 2nd half of %d Pagesize=%d  from %d to %d before PAGEPROG' % (pageno, self.PageSize, self.PageSize/2, self.PageSize) )
                self.__send_cmd(flashdevice_defs.NAND_CMD_READ1)
                self.__send_cmd(flashdevice_defs.NAND_CMD_SEQIN)
                self.__wait_ready()
                self.__send_address(pageno<<8, self.AddrCycles)
                self.__wait_ready()
                self.__write_datastring(data[int(self.PageSize/2):int(self.PageSize)])  # int() fix scalars
                # print('Write 2nd half of %d Pagesize=%d after PAGEPROG' % (pageno, self.PageSize) )

                self.__send_cmd(flashdevice_defs.NAND_CMD_PAGEPROG)
                err = self.__get_status()
                if err & flashdevice_defs.NAND_STATUS_FAIL:
                    print('Failed to write 2nd half of ', pageno, err)
                    continue
                break

            while 1 & self.writeOoB:                                   # Not supported for Samsung
                # print('Write oob of ', pageno)
                if self.DebugPtro:
                    print('Write oob of %d Pagesize=%d' % (pageno, self.PageSize) )
                self.__send_cmd(flashdevice_defs.NAND_CMD_READ_OOB)    # NAND_CMD_READ_OOB = 0x50
                self.__send_cmd(flashdevice_defs.NAND_CMD_SEQIN)
                self.__wait_ready()
                self.__send_address(pageno<<8, self.AddrCycles)
                self.__wait_ready()
                self.__write_datastring(data[self.PageSize:self.RawPageSize])
                self.__send_cmd(flashdevice_defs.NAND_CMD_PAGEPROG)
                err = self.__get_status()
                if err & flashdevice_defs.NAND_STATUS_FAIL:
                    print('Failed to write OOB of ', pageno, err)
                    continue
                break

        self.WriteProtect = True
        return err

#    def write_block(self, block_data):
#        nand_tool.erase_block_by_page(0) #need to fix
#        page = 0
#        for i in range(0, len(data), self.RawPageSize):
#            nand_tool.write_page(pageno, data[i:i+self.RawPageSize])
#            page += 1

    def write_pages(self, filename, offset = 0, start_page = -1, end_page = -1, add_oob = False, add_jffs2_eraser_marker = False, raw_mode = False, datastring = '', oob_file = True):
    # datastring is used to write if filename is not used

        # print('write_pages: read filename=', filename, ' datalen=', len(datastring), 'data=', type(datastring))  #  <class 'bytes'>
        # data = bytearray(datastring, 'utf-8')	# conver string to byte array double size
        # data = Array("B",datastring) # TypeError: cannot use a str to initialize an array with typecode 'B'
        # data = Array("C",datastring) # TypeError: cannot use a str to initialize an array with typecode 'B'


        if not filename and len(datastring) == 0:
           print(' No file en no data, return without writing')
           return

        if filename:                        # data from file 
           fd = open(filename, 'rb')
           fd.seek(offset)                  # seek to this point
           data = fd.read()                 # read all of file
        else:                               # data from string
           data = struct.pack('B', ord(datastring[0]) )   # convert string to bytearray (python3.x)
           for i in range(1, len(datastring),1):                 
               data += struct.pack('B', ord(datastring[i]) )

        if self.Debug_info:
           print('-- write_pages: using datalen=', len(data), ', offset=', offset, 'start_page=', start_page , 'end_page=', end_page )
           print('---             raw_mode=', str(raw_mode), ', oob_file=', str(oob_file) , 'add_oob=', str(add_oob) )
           print('---             datalen=', len(data), 'data=', type(data))  #  <class 'bytes'>

        if start_page == -1:
           start_page = 0

        if end_page == -1:
           end_page = self.PageCount-1

        end_block = end_page/self.PagePerBlock

        if end_page % self.PagePerBlock > 0:
            end_block += 1

        start = time.time()
        ecc_calculator = ecc.Calculator()

        page = start_page
        block = int(page / self.PagePerBlock)
        current_data_offset = 0
        length = 0

        # print('\nWritten3 %x bytes / %d byte' % (length, len(data))) # debug test verify datalenght 2112
        # dilemma
        #   read without oob, read with oob : skip = 
        #
        while page <= end_page and current_data_offset < len(data) and block < self.BlockCount:
            if self.Debug_info:
               print('--- write_pages: page=%d current_data_offset=%d, block=%d' % ( page, current_data_offset, block))

            oob_postfix = b'\xff' * 13  # 13 byte array
            # print ('--- write_pages len(oob_postfix)=', len(oob_postfix))  # 13
            if page%self.PagePerBlock == 0:    # modulus 0 ??

                if not raw_mode:
                    bad_block_found = False
                    for pageoff in range(0, 2, 1):
                        oob = self.read_oob(page+pageoff)
                        print('--- +++ check badblock page=', page+pageoff, ', len(oob)=', len(oob))

                        # if oob[5] != b'\xff':  python2.7 not supported by python3
                        if oob[5] != chr(0xff):
                            bad_block_found = True
                            print('--- +++ bad block page=%d , oob(5)=0x%x' % (pageoff, ord(oob[5])) )
                            break

                    if bad_block_found:
                        page += self.PagePerBlock
                        print('\nSkipping bad block at ', block, ' nextblockpage=', page )
                        block += 1
                        continue

                if add_jffs2_eraser_marker:
                    print('--- add_jffs2_eraser_marker(', page, ') (testmode)')
                    oob_postfix = b"\xFF\xFF\xFF\xFF\xFF\x85\x19\x03\x20\x08\x00\x00\x00"   # 13 bytes

                if self.Debug_info:
                   print('\n write_pages: self.erase_block_by_page(', page, ') (testmode)')
                self.erase_block_by_page(page)

            if add_oob:  # do our own oob addition
                if self.Debug_info:
                   print('---- add_oob0 current_data_offset=%d, plusPageSize=%d, oob_file=%s' % (current_data_offset, current_data_offset+self.PageSize, str(oob_file)) )  # 2048

                orig_page_data = data[current_data_offset:current_data_offset + self.PageSize]  # get 2048 bytes datapart

                if oob_file:                              # claculate & skip for next read
                   current_data_offset += self.RawPageSize
                   if self.Debug_info:
                      print('------- use oob in file:  current_data_offset=%d, len(data)=%d' % (current_data_offset,len(data)) )  # check
                else:
                   current_data_offset += self.PageSize
                length += self.PageSize

                if self.Debug_info:
                   print('---- add_oob1 len(orig_page_data)=%d, self.PageSize=%d' % (len(orig_page_data), self.PageSize) )  # 2048

                # orig_page_data += (self.PageSize - len(orig_page_data)) * b'\x00'   # extend string to Pagesize 2048 with 0x00
                for x in range(self.PageSize - len(orig_page_data)):
                   # orig_page_data += chr(0)  # Python2.7
                   orig_page_data += b'\x00'   # Python3.5

                if self.Debug_info:
                   print('---- add_oob2 len(orig_page_data)=%d, cur1=0x%x par=0x%x' % (len(orig_page_data), orig_page_data[0],  ( orig_page_data[0]^0xff )  ) )  # shoudl be fixed to 2048 bytes

                if self.Debug_info:
                   print("---- add_oob1a:The variable, orig_page_data is of type:", type(orig_page_data))  #  <class 'bytes'>

                (ecc0, ecc1, ecc2) = ecc_calculator.calc(orig_page_data)    # calculate ecc bytes
                # cacl2 = add_oob3 ecc code 0x9b 0xab 0x69
                # calc1 = add_oob3 ecc code 0x65 0x55 0x95 

                if self.Debug_info:
                   print('---- add_oob3 ecc code 0x%x 0x%x 0x%x' % (ecc0, ecc1, ecc2) )  # print ecc codes

                oob = struct.pack('BBB', ecc0, ecc1, ecc2) + oob_postfix    # concatenate  bytaarray 3+13= 16 bytes

                if self.Debug_info:
                   print('---- add_oob4 ecc code 0x%x 0x%x 0x%x for ooblen=%d' % (ecc0, ecc1, ecc2, len(oob)) )  # print ecc codes 


                # page_data = orig_page_data+oob  # not vaid in python3
                page_data = orig_page_data
                # print("The variable, oob is of type:", type(oob))  #  <class 'bytes'>
                # print("The variable, page_data is of type:", type(page_data)) #  <class 'bytes'>
                page_data += oob   # 

                # for x in range(len(oob)+1):
                #   # page_data += chr(oob[x])   # Python2.7
                #   page_data += oob[x-1]        # Python2.7

                if len(page_data) < self.RawPageSize:               # check if we have a full page of 2112
                   if self.Debug_info:
                      print('---- add_oob4 adding %d bytes (xff) to fill page to %d' % (self.RawPageSize-len(page_data),self.RawPageSize) ) # 
                   for x in range(self.RawPageSize-len(page_data)): # fill unbtil 2112 witj 0xff
                         # page_data += chr(0xff) # Python2.7
                         page_data += b'\xff'     # Python3.5

                if self.Debug_info:
                   print('---- add_oob5 len(page_data)=%d, self.PageSize=%d, RawPageSize=%d' % (len(page_data), self.PageSize, self.RawPageSize ) ) # 2048

            else:
                if oob_file:
                   page_data = data[current_data_offset:current_data_offset + self.RawPageSize]  # get next datasegment from input file 2112
                   current_data_offset += self.RawPageSize
                else:
                   page_data = data[current_data_offset:current_data_offset + self.PageSize]  # get next datasegment from input file 2048
                   current_data_offset += self.PageSize
                length += len(page_data)

            if len(page_data) != self.RawPageSize:
                # 07apr23 hit by file ~/code-dumpflash/dumpflash size 1048576 bytes, seems to happen with write oob
                if self.Debug_info:
                   print('\nNot enough source page_data_len=%d != RawPageSize=%d (page %d truncated by %d bytes)' % (len(page_data), self.RawPageSize, page, self.RawPageSize-len(page_data) ) )
                # break

            current = time.time()

            if end_page == start_page:
                progress = 100
            else:
                progress = (page-start_page) * 100 / (end_page-start_page)

            lapsed_time = current-start

            if lapsed_time > 0:
                if self.UseAnsi:
                    sys.stdout.write('Writing %d%% Page: %d/%d Block: %d/%d Speed: %d bytes/s\n\033[A' % (progress, page, end_page, block, end_block, length/lapsed_time))
                else:
                    sys.stdout.write('Writing %d%% Page: %d/%d Block: %d/%d Speed: %d bytes/s\n' % (progress, page, end_page, block, end_block, length/lapsed_time))

            if self.Debug_info:
               print('\nwrite_pages: self.write_page(', page, ', lengtdata=', len(page_data)  , ') SKIPPING function in view testmode')
            else:
               # print('\nwrite_pages: self.write_page(', page, ', lengtdata=', len(page_data)  , ') NOT skipping function in testmode')
               self.write_page(page, page_data)

            if page%self.PagePerBlock == 0:
                block = page / self.PagePerBlock
            page += 1

        if filename:
           fd.close()

        print('\nWritten %d bytes / %d byte' % (length, len(data)))

    def erase(self):
        block = 0
        print('Erasing all Chip Blocks: 0x0 ~ %d' % (self.BlockCount))
        while block < self.BlockCount:

            self.erase_block_by_page(block * self.PagePerBlock)
            block += 1

    def erase_block(self, start_block, end_block):
        print('Erasing block pages: %d ~ %d (including)' % (start_block, end_block))
        for block in range(start_block, end_block+1, 1):
            print(" process busy erasing block", block)
            self.erase_block_by_page(block * self.PagePerBlock)

