# pylint: disable=invalid-name
# pylint: disable=line-too-long
from optparse import OptionParser
import pprint
import os
import struct
import sys
import time
import flashfile
import flashdevice
import uboot
import ecc

class IO:
       
    def __init__(self, filename = '', base_offset = 0, length = 0, \
                       page_size = 0x800, oob_size = 0x40,         \
                       page_per_block = 0x40, slow = False,        \
                       stream = 1, tsize = 0, debug_info = False):

        self.UseAnsi = False
        self.UseSequentialMode = False
        self.DumpProgress = True
        self.DumpProgressInterval = 1
        self.Tsize = tsize
        self.Debug_info = debug_info
        self.StreamData = stream

        if filename:
            if self.Debug_info: 
               print ('Using FlashFile', filename, 'Debug=', str(debug_info), ', Tsize=', tsize)
            self.SrcImage = flashfile.IO(filename, base_offset = base_offset, length = length, page_size = page_size, oob_size = oob_size, page_per_block = page_per_block)
        else:
            if self.Debug_info: 
               print ('Using Flashdevice', 'Debug=', str(debug_info), ', Tsize=', tsize)
            self.SrcImage = flashdevice.IO(slow, streamdata = stream, debug_info = debug_info, )
            self.SrcImage.__wait_ready()

        # self.SrcImage.Tsize = 0  # default tranfersize for interaction with ftdi

    def is_initialized(self):
        return self.SrcImage.is_initialized()

    def set_use_ansi(self, use_ansi):
        self.UseAnsi = use_ansi
        self.SrcImage.set_use_ansi(use_ansi)

    def check_ecc(self, start_page = 0, end_page = -1):
        block = 0
        count = 0
        error_count = 0

        if end_page == -1:
            end_page = self.SrcImage.PageCount

#        start_block = 0
        end_block = end_page/self.SrcImage.PagePerBlock
        if end_page%self.SrcImage.PagePerBlock > 0:
            end_block += 1

        ecc_calculator = ecc.Calculator()
        start = time.time()
        for page in range(0, self.SrcImage.PageCount, 1):
            block = page/self.SrcImage.PagePerBlock
            if self.DumpProgress:
                current = time.time()
                if current-start > self.DumpProgressInterval:
                    start = current
                    progress = (page-start_page) * 100 / (end_page-start_page)
                    if self.UseAnsi:
                        fmt_str = 'Checking ECC %d%% (Page: %3d/%3d Block: %3d/%3d)\n\033[A'
                    else:
                        fmt_str = 'Checking ECC %d%% (Page: %3d/%3d Block: %3d/%3d)\n'
                    sys.stdout.write(fmt_str % (progress, page, end_page, block, end_block))

            #if self.__check_bad_block(block) == self.BAD_BLOCK:
            #    print 'Bad Block: %d' % block
            #    print ''

            data = self.SrcImage.read_page(page)

            if not data:
#                end_of_file = True
                break

            count += 1
            body = data[0:self.SrcImage.PageSize]
            oob_ecc0 = ord(data[self.SrcImage.PageSize])
            oob_ecc1 = ord(data[self.SrcImage.PageSize+1])
            oob_ecc2 = ord(data[self.SrcImage.PageSize+2])

            if (oob_ecc0 == 0xff and oob_ecc1 == 0xff and oob_ecc2 == 0xff) or (oob_ecc0 == 0x00 and oob_ecc1 == 0x00 and oob_ecc2 == 0x00):
                continue

            (ecc0, ecc1, ecc2) = ecc_calculator.calc(body)

            ecc0_xor = ecc0 ^ oob_ecc0
            ecc1_xor = ecc1 ^ oob_ecc1
            ecc2_xor = ecc2 ^ oob_ecc2

            if ecc0_xor != 0 or ecc1_xor != 0 or ecc2_xor != 0:
                error_count += 1

#                page_in_block = page%self.SrcImage.PagePerBlock

                offset = self.SrcImage.get_page_offset(page)
                print('ECC Error (Block: %3d Page: %3d Data Offset: 0x%x OOB Offset: 0x%x)' % (block, page, offset, offset+self.SrcImage.PageSize))
                print('  OOB:  0x%.2x 0x%.2x 0x%.2x' % (oob_ecc0, oob_ecc1, oob_ecc2))
                print('  Calc: 0x%.2x 0x%.2x 0x%.2x' % (ecc0, ecc1, ecc2))
                print('  XOR:  0x%.2x 0x%.2x 0x%.2x' % (ecc0 ^ oob_ecc0, ecc1 ^ oob_ecc1, ecc2 ^ oob_ecc2))
                print('')

        print('Checked %d ECC record and found %d errors' % (count, error_count))

    def check_bad_block_page(self, oob):  # not called in these routines
        bad_block = False

        if oob[0:3] != b'\xff\xff\xff':
            bad_block = True
            if oob[0x8:] == b'\x85\x19\x03\x20\x08\x00\x00\x00': #JFFS CleanMarker
                bad_block = False

        return bad_block

    CLEAN_BLOCK = 0
    BAD_BLOCK = 1
    ERROR = 2

    def __check_bad_block(self, block): # modified to satisfy Python3.x
        for page in range(0, 2, 1):
            pageno = block * self.SrcImage.PagePerBlock + page

            # oob = self.SrcImage.read_oob(pageno, 0)   # def read_oob(self, pageno, oob_size=0):
            oob = self.SrcImage.read_oob(pageno)   # def read_oob(self, pageno, oob_size=0):

            # else: # debug
            #    print(" __check_bad_block: block: %d, pageno=%d : bad_block_marker 0x%x" % (block, pageno, ord(oob[6:7]) ) )  #
            
            bad_block_marker = oob[6:7]
            # print(" __check_bad_block check oob: len(bad_block_marker)=%d type(bad_block_marker)=%s" % (len(bad_block_marker), type(bad_block_marker) ) )  # 1 & class bytes
            # print (' len(bad_block_marker)=%d, content=0x%x   ' % ( len(bad_block_marker), ord(bad_block_marker)  ) )
            if len(oob) < 0:
               print(" __check_bad_block<oob: read error block: %d, pageno=%d : bad_block_marker 0x%x type(bad_block_marker)" % (block, pageno, ord(bad_block_marker), type(bad_block_marker) ) )  #

            # print(" __check_bad_block: bad_block_marker=0x%x 0x%x" % ( ord(bad_block_marker[0]) ) )  #  
            # if bad_block_marker[0] == b'\xff':  # python2.7
            # if bad_block_marker == ord(0xff):     # python3 error
            # if bad_block_marker == b'\xff':     # python3
            if bad_block_marker == chr(0xff) :     # python3
                # print(" __ return self.CLEAN_BLOCK" )  # //here5
                return self.CLEAN_BLOCK

            if not bad_block_marker:
                return self.ERROR

            # print ('\nlen(bad_block_marker)=%d, content=0x%x   ' % ( len(bad_block_marker), ord(bad_block_marker)  ) )
            return self.BAD_BLOCK

        # print (' len(bad_block_marker)=%d, content=0x%x   ' % ( len(bad_block_marker), ord(bad_block_marker)  ) )

        # return self.CLEAN_BLOCK # for test with NAND a FF page can be written
        return self.BAD_BLOCK

    def CheckBadBlock(self, block): # modified to satisfy Python3.x
        ret = self.__check_bad_block(block)



    def check_bad_blocks(self, start_page = -1, end_page = -1):  # python3 dumpflash.py -o dump11apr23_00u13.bin -b 0 1 -c check_bad_blocks
        start_block = 0
        end_block = self.SrcImage.BlockCount - 1

        if self.Debug_info: 
            print('flashimage: start_page=', start_page, 'end_page=', end_page , 'BlockCount=', self.SrcImage.BlockCount )

        if (start_page > 0 ): start_block = int(start_page / self.SrcImage.PagePerBlock)
        if (end_page < 1 ): end_page_page = self.SrcImage.BlockCount*self.SrcImage.PagePerBlock

        if (end_page < start_page ): end_page = start_page + (end_page - 1)
        if (end_page > 0 ): end_block = int(end_page / self.SrcImage.PagePerBlock) + 1

        end_block = int(end_page / self.SrcImage.PagePerBlock)
        if (end_block > self.SrcImage.BlockCount): end_block = self.SrcImage.BlockCount

        block = start_block

        block = 0

        error_count = 0
        page = 0
        pageno = (end_block+1) * self.SrcImage.PagePerBlock

        # Using page=1 pageno=4081 block=255 PagePerBlock=16 PageCount=4096
        if self.Debug_info: 
            print(" flashimage: Check bad_block: %d - %d" % (start_block, end_block ))
            # return  # testing

#        start_block = 0
#        end_page = self.SrcImage.PageCount
        # for block in range(self.SrcImage.BlockCount):
        for block in range(start_block,end_block+1,1):
            ret = self.__check_bad_block(block)

            progress = ((block-start_block)+1)*100.0/((end_block+1)-start_block)
            if self.Debug_info: 
               sys.stdout.write('  flashimage: Checking Bad Blocks %d%% Block: %d/%d at offset 0x%x\r' % (progress, block+1, end_block, (block * self.SrcImage.BlockSize)))

            if ret == self.BAD_BLOCK:
                error_count += 1
                print("   flashimage: Bad Block# %d (at page %d physical offset 0x%x)" % (block, (block*self.SrcImage.PagePerBlock),  (block * self.SrcImage.BlockSize)))

            elif ret == self.ERROR:
                print("\n   flashimage: Error Block# %d (at page %d physical offset 0x%x)" % (block, (block*self.SrcImage.PagePerBlock), (block * self.SrcImage.BlockSize))) 
                break
        
        print("\n  flashimage: Checked %d blocks and found %d errors" % ((end_block+1)-start_block, error_count))



    def check_bad_blocks_org(self):  # python3 dumpflash.py -o dump11apr23_00u13.bin -b 0 1 -c check_bad_blocks
        block = 0
        error_count = 0
        page = 0
        pageno = block * self.SrcImage.PagePerBlock + page
        # Using page=1 pageno=4081 block=255 PagePerBlock=16 PageCount=4096
        print(" flashimage: Start page=%d pageno=%d block=%d PagePerBlock=%d PageCount=%d" % (page, pageno, block, self.SrcImage.PagePerBlock, self.SrcImage.PageCount ))

#        start_block = 0
#        end_page = self.SrcImage.PageCount
        for block in range(self.SrcImage.BlockCount):
            ret = self.__check_bad_block(block)

            progress = (block+1)*100.0/self.SrcImage.BlockCount
            sys.stdout.write('  flashimage: Checking Bad Blocks %d%% Block: %d/%d at offset 0x%x\r' % (progress, block+1, self.SrcImage.BlockCount, (block * self.SrcImage.BlockSize)))

            if ret == self.BAD_BLOCK:
                error_count += 1
                print("\n   flashimage: Bad Block: %d (at page %d physical offset 0x%x)\n" % (block+1, (block*self.SrcImage.PagePerBlock),  (block * self.SrcImage.BlockSize)))

            elif ret == self.ERROR:
                print("\n   flashimage: Error Block: %d (at page %d physical offset 0x%x)\n" % (block+1, (block*self.SrcImage.PagePerBlock), (block * self.SrcImage.BlockSize))) 
                break
        
        print("\n  flashimage: Checked %d blocks and found %d errors" % (block+1, error_count))
        page = 0
        pageno = block * self.SrcImage.PagePerBlock + page
        # Using page=1 pageno=4081 block=255 PagePerBlock=16 PageCount=4096
        print(" flashimage: End page=%d pageno=%d block=%d PagePerBlock=%d PageCount=%d" % (page, pageno, block, self.SrcImage.PagePerBlock, self.SrcImage.PageCount ))


    def read_pages(self, start_page = -1, end_page = -1, remove_oob = False, filename = '', append = False, maximum = 0, seq = False, raw_mode = False, tsize = -1, skip=0):

        if self.Debug_info:
           print('* read_pages: %d ~ %d , options.tsize=%d, chip.Tsize=%d, Skipping=%d, Rawmode=%s' % (start_page, end_page, tsize, tsize, skip, str(raw_mode)))

        if seq:
            return self.read_seq_pages(start_page, end_page, remove_oob, filename, append = append, maximum = maximum, raw_mode = raw_mode)

        if filename:
           if append:
              fd = open(filename, 'ab')
           else:
              fd = open(filename, 'wb')

        if start_page < 0:
            start_page = 0

        if end_page < 0:
            end_page = self.SrcImage.PageCount-1

        if tsize < 1:                     # set tsize from chip routine
            tsize = self.SrcImage.Tsize

        end_block = int(end_page/self.SrcImage.PagePerBlock)
        if end_page%self.SrcImage.PagePerBlock:
            end_block += 1

        # if start_page == end_page:
        #    end_page += 1

        if self.Debug_info:
           print('* self.SrcImage.read_page: %d ~ %d , end_block=%d remove_oob=%s, tsize=%d skip=%d' % (start_page, end_page, end_block, str(remove_oob), tsize, skip)  )

        whole_data = ''
        length = 0
        start = time.time()
        last_time = time.time()

        for page in range(start_page, end_page+1, 1):

            for repeat in range(0, 10, 1):  # repeat/stress read
                page2 = page
                data = self.SrcImage.read_page(page2, remove_oob, tsize)  
                if (len(data) != self.SrcImage.PageSize and remove_oob == True) or (len(data) != self.SrcImage.RawPageSize and remove_oob == False):   # elongate read data of page
                    if len(data) != self.SrcImage.PageSize and remove_oob == True :   # elongate read data of page
                        print('  -- retry flashimage.read_page(OOBtrue)=', page2 , 'len(data)=', len(data), ', PageSize=', self.SrcImage.PageSize, ', difflen=', len(data) - self.SrcImage.PageSize  )
                        for x in range(self.SrcImage.PageSize - len(data)):
                           # orig_page_data += chr(0)  # Python2.7
                           data += b'\xAA'   # Python3.5
                    if len(data) != self.SrcImage.RawPageSize and remove_oob == False:   # elongate read data of page
                        print('  -- retry flashimage.read_page(OOBfalse)=', page2 , 'len(data)=', len(data), ', RawPageSize=', self.SrcImage.RawPageSize, ', difflen=', len(data) - self.SrcImage.RawPageSize  )
                        for x in range(self.SrcImage.RawPageSize - len(data)):
                            # orig_page_data += chr(0)  # Python2.7
                            data += b'\xAA'   # Python3.5
                    if repeat > 8:
                        print('  -- retry flashimage.read_page=', page2 , ' ERROR data elongated with xAA')
                else:  # data has good length
                    break


        # print('--- flashimage_readpages1: datalen=', len(whole_data) ) # 0

        # >>> x = "Hello World!" 
        # >>> x[2:] 'llo World!'
        # >>> x[:2] 'He'
        # >>> x[:-2] 'Hello Worl'
        # >>> x[-2:] 'd!'
        # >>> x[2:-2] 'llo Worl'

            if filename:
               if maximum != 0:
                  if length < maximum:
                      fd.write(data[0:maximum-length])
                  else:
                      break
               else:
                   if skip != 0 & abs(skip) < len(data):
                         fd.write(data[skip:])
                   else:
                      fd.write(data)
            else:
                # whole_data += data
                # print('--- flashimage_readpages2: datalen=', len(whole_data) )  # 0
                for byte in data:
                     whole_data += chr(byte) # Convert each byte to a character and append to the string
                # print('--- flashimage_readpages3: datalen=', len(whole_data) ) # 2112

            length += len(data)

            if self.DumpProgress:
                current = time.time()
                if current-last_time > self.DumpProgressInterval:
                    lapsed_time = current-start
                    last_time = current
                    progress = (page-start_page) * 100 / ((end_page-start_page)+1)  # prevent divide zero
                    block = page/self.SrcImage.PagePerBlock
                    if self.UseAnsi:
                        fmt_str = 'Reading %3d%% Page: %3d/%3d Block: %3d/%3d Speed: %8d bytes/s\n\033[A'
                    else:
                        fmt_str = 'Reading %3d%% Page: %3d/%3d Block: %3d/%3d Speed: %8d bytes/s\n'

                    if lapsed_time > 0:
                        bps = length/lapsed_time
                    else:
                        bps = -1

                    sys.stdout.write(fmt_str % (progress, page, end_page, block, end_block, bps))

        if filename:
           fd.close()

        if maximum != 0:
            return whole_data[0:maximum]

        # print('--- flashimage_readpages4: datalen=', len(whole_data) ) # 2112
        return whole_data


    def read_offset_pages(self, start_page = -1, end_page = -1, remove_oob = False, filename = '', append = False, maximum = 0, seq = False, raw_mode = False, tsize = -1, skip=0):

        # if seq: return self.read_seq_pages(start_page, end_page, remove_oob, filename, append = append, maximum = maximum, raw_mode = raw_mode)

        if filename:
           if append:
              fd = open(filename, 'ab')
           else:
              fd = open(filename, 'wb')

        if start_page < 0: start_page = 0
        if end_page < 0: end_page = self.SrcImage.PageCount-1
        if tsize < 1: tsize = self.SrcImage.PageSize                      # set tsize from chip routine

        end_block = int(end_page/self.SrcImage.PagePerBlock)
        if end_page%self.SrcImage.PagePerBlock: end_block += 1

        if self.Debug_info:
           print('* self.SrcImage.read_offset_page: %d ~ %d , end_block=%d length=%d offset=%d' % (start_page, end_page, end_block, tsize, skip)  )


        whole_data = ''
        length = 0
        start = time.time()
        last_time = time.time()

        for page in range(start_page, end_page+1, 1):
            data = self.SrcImage.read_page_offset(page, tsize, skip)
            print(' --- * self.SrcImage.read_offset_page: return dataen=%d, maximum=%d , length=%d' % (len(data), maximum, length)  )

            if filename:
               if maximum != 0:
                  if length < maximum:
                      fd.write(data[0:maximum-length])
                  else:
                      break
               else:
                  fd.write(data)
            else:
                # whole_data += data
                # print('--- flashimage_readpages2: datalen=', len(whole_data) )  # 0
                for byte in data:
                     whole_data += chr(byte) # Convert each byte to a character and append to the string
                # print('--- flashimage_readpages3: datalen=', len(whole_data) ) # 2112

            length += len(data)
            print(' --- * self.SrcImage.read_offset_page: return dataen=%d --> length2=%d' % (len(data), length)  )

            if self.DumpProgress:
                current = time.time()
                if current-last_time > self.DumpProgressInterval:
                    lapsed_time = current-start
                    last_time = current
                    progress = (page-start_page) * 100 / ((end_page-start_page)+1)  # prevent divide zero
                    block = page/self.SrcImage.PagePerBlock
                    if self.UseAnsi:
                        fmt_str = 'Reading %3d%% Page: %3d/%3d Block: %3d/%3d Speed: %8d bytes/s\n\033[A'
                    else:
                        fmt_str = 'Reading %3d%% Page: %3d/%3d Block: %3d/%3d Speed: %8d bytes/s\n'

                    if lapsed_time > 0:
                        bps = length/lapsed_time
                    else:
                        bps = -1

                    sys.stdout.write(fmt_str % (progress, page, end_page, block, end_block, bps))

        if filename:
           fd.close()

        if maximum != 0:
            return whole_data[0:maximum]

        # print('--- flashimage_readpages4: datalen=', len(whole_data) ) # 2112
        return whole_data


    def read_seq_pages(self, start_page = -1, end_page = -1, remove_oob = False, filename = '', append = False, maximum = 0, raw_mode = False):
        if filename:
            if append:
                # 30mar23 ptro --> problem TypeError: a bytes-like object is required, not 'str', cause as fs is opended as binary xb
                # fd = open(filename, 'ab')
                fd = open(filename, 'a')
            else:
                # 30mar23 ptro --> problem TypeError: a bytes-like object is required, not 'str', cause as fs is opended as binary xb
                # fd = open(filename, 'wb')
                fd = open(filename, 'w')
        if start_page == -1:
            start_page = 0

        if end_page == -1:
            end_page = self.SrcImage.PageCount

        end_block = end_page/self.SrcImage.PagePerBlock
        if end_page%self.SrcImage.PagePerBlock:
            end_block += 1

        whole_data = ''
        length = 0
        start = time.time()
        for page in range(start_page, end_page, self.SrcImage.PagePerBlock):
            data = self.SrcImage.read_seq(page, remove_oob, raw_mode)

            if filename:
                if maximum != 0:
                    if length < maximum:
                        fd.write(data[0:maximum-length])
                    else:
                        break
                else:
                    fd.write(data)
            else:
                whole_data += data

            length += len(data)
            current = time.time()

            if self.DumpProgress:
                block = page/self.SrcImage.PagePerBlock
                progress = (page-start_page) * 100 / (end_page-start_page)
                lapsed_time = current-start

                if lapsed_time > 0:
                    if self.UseAnsi:
                        sys.stdout.write('Reading %d%% Page: %d/%d Block: %d/%d Speed: %d bytes/s\n\033[A' % (progress, page, end_page, block, end_block, length/(current-start)))
                    else:
                        sys.stdout.write('Reading %d%% Page: %d/%d Block: %d/%d Speed: %d bytes/s\n' % (progress, page, end_page, block, end_block, length/(current-start)))

        if filename:
            fd.close()

        if maximum != 0:
            return whole_data[0:maximum]
        return whole_data

    def add_oob(self, filename, output_filename, jffs2 = False, remove_oob = False):

        print (' add_oob data to output file=', output_filename , 'using (non)inputfilenam=', filename )

        fd = open(filename, 'rb')
        wfd = open(output_filename, "wb")

        current_block_number = 0
        current_output_size = 0
        ecc_calculator = ecc.Calculator()
        while 1:
            if remove_oob:  # ignore from input
                page = fd.read(self.SrcImage.PageSize+self.SrcImage.OOBSize)
            else:
                page = fd.read(self.SrcImage.PageSize)

            page = page[0:self.SrcImage.PageSize]

            # print ('-- reading file=', filename , ' lendata=', len(page) )
            if not page:
                break

            for x in range( (self.SrcImage.PageSize) - len(page)):
                page += b'\xff'   # Python3.5

            (ecc0, ecc1, ecc2) = ecc_calculator.calc(page)

            oob_postfix = b'\xff' * 13

            if current_output_size% self.SrcImage.BlockSize == 0:
                if jffs2 and current_block_number%2 == 0:
                    oob_postfix = b'\xFF\xFF\xFF\xFF\xFF\x85\x19\x03\x20\x08\x00\x00\x00'
                current_block_number += 1


            data = page + struct.pack('BBB', ecc0, ecc1, ecc2) + oob_postfix
            # print ('-- creating file=', filename , ' lendata=', len(data) )
            for x in range( (self.SrcImage.PageSize+self.SrcImage.OOBSize) - len(data)):
                data += b'\xff'   # Python3.5

            wfd.write(data)
            current_output_size += len(data)
            # print ('-- writing file=', output_filename , ' lenout=', len(data), ' current_output_size=', current_output_size )

        #Write blank pages
        """
        while size>current_output_size:
            if current_output_size% self.RawBlockSize == 0:
                wfd.write(b"\xff"*0x200+ "\xFF\xFF\xFF\xFF\xFF\xFF\xFF\xFF\x85\x19\x03\x20\x08\x00\x00\x00")
            else:
                wfd.write(b"\xff"*0x210)
            current_output_size += 0x210
        """

        fd.close()
        wfd.close()

    def __extract_pages_by_offset(self, output_filename, start_offset = 0, end_offset = -1, remove_oob = True):
    #
    ## Needs working for an usable use , do we want  to read/extract block or page from file  ???
    ## now it is doing a whole block

        if start_offset == -1:
            start_offset = 0

        if end_offset == -1:
            end_offset = self.SrcImage.RawBlockSize * self.SrcImage.BlockCount


        print('  __extract_pages_by_offset in file seek: 0x%x - 0x%x to file -> %s' % (start_offset, end_offset-1, output_filename))

        start_block = int(start_offset / self.SrcImage.RawBlockSize)
        start_block_offset = start_offset % self.SrcImage.RawBlockSize
        start_page = int(start_block_offset / self.SrcImage.RawPageSize)
        start_page_offset = start_block_offset % self.SrcImage.RawPageSize

        end_block = int(end_offset / self.SrcImage.RawBlockSize)
        end_block_offset = end_offset % self.SrcImage.RawBlockSize
        end_page = int(end_block_offset / self.SrcImage.RawPageSize)
        end_page_offset = end_block_offset % self.SrcImage.RawPageSize


        print('  __extract_pages_by_offset Dump blocks (Block: 0x%x Offset: 0x%x ~  Block: 0x%x Offset: 0x%x)' % (start_block, start_block_offset, end_block, end_block_offset))

        with open(output_filename, 'wb') as wfd:  # //here4
            output_bytes = ''
            for block in range(start_block, end_block+1, 1): 
                if self.Debug_info: 
                   print('   __extract_pages_by_offset: block ', start_block , 'to', end_block+1 )
                ret = self.__check_bad_block(block)  # //here5

                if ret == self.CLEAN_BLOCK:

                    current_start_page = 0
                    current_end_page = self.SrcImage.PagePerBlock
                    if block == start_block:
                        current_start_page = start_page
                    elif block == end_block:
                        current_end_page = end_page+1

                    for page in range(current_start_page, current_end_page, 1):
                        # print("  --- write output page %d  of %d to file " % (page, current_end_page) )
                        pageno = block * self.SrcImage.PagePerBlock + page
                        data = self.SrcImage.read_page(pageno)

                        if not data:
                            break

                        if not remove_oob:
                            write_size = self.SrcImage.RawPageSize
                        else:
                            write_size = self.SrcImage.PageSize

                        if block == start_block and page == current_start_page and start_page_offset > 0:
                            wfd.write(data[start_page_offset: write_size])
                        elif block == end_block and page == current_end_page-1 and end_page_offset >= 0:
                            wfd.write(data[0: end_page_offset])
                        else:
                            wfd.write(data[0: write_size])
                elif ret == self.ERROR:
                    break
                else:
                    print("Skipping block %d , badmarker=%x " % (block, ret ))

    def extract_pages(self, output_filename, start_page = 0, end_page = -1, remove_oob = True):
        if start_page == -1:
            start_page = 0

        if end_page == -1:
            end_offset = self.SrcImage.BlockSize * self.SrcImage.RawPageSize * self.SrcImage.PagePerBlock
        else:
            end_offset = end_page * self.SrcImage.RawPageSize

        return self.__extract_pages_by_offset(output_filename, start_page * self.SrcImage.RawPageSize, end_offset, remove_oob)

    def extract_data(self, start_page, length, filename = ''):
        
        start_block = int(start_page / self.SrcImage.PagePerBlock)
        start_block_page = start_page % self.SrcImage.PagePerBlock

        expected_data_length = 0
        block = start_block
        blocks = []

        if self.Debug_info: 
           print ('  -- flashimage.py/extract_data: start_page=', start_page , 'length=', length ) # flashimage.py/extract_data: start_page= 65216 length= 64

        for _start_page in range(start_block*self.SrcImage.PagePerBlock, self.SrcImage.PageCount, self.SrcImage.PagePerBlock):
            is_bad_block = False
            for pageoff in range(0, 2, 1):
                oob = self.SrcImage.read_oob(_start_page+pageoff)
                # print ('  -- xtract_data/oob type=', type(oob))   # debug check type (fix python2.7 to python3)

                # if oob and oob[5] != b'\xff': # (fix python2.7 to python3)
                if oob and oob[5] != chr(0xff): # (fix python2.7 to python3)
                    is_bad_block = True
                    print ('  -- flashimage.py/extract_data, badblock detected on page=%d with oob5=0x%x ' % ( _start_page+pageoff, ord(oob[5])) )
                    break

            if not is_bad_block:
                if _start_page <= start_page and _start_page <= start_page+self.SrcImage.PagePerBlock: #First block
                    expected_data_length += (self.SrcImage.PagePerBlock-start_block_page) * self.SrcImage.PageSize
                    blocks.append(block)
                else:
                    expected_data_length += self.SrcImage.PagePerBlock * self.SrcImage.PageSize
                    blocks.append(block)

            if expected_data_length >= length:
                break
            block += 1

        if self.Debug_info: 
           print ('  -- flashimage.py/extract_data: expected_data_length=', expected_data_length , '>= length=', length ) # flashimage.py/extract_data: start_page= 65216 length= 64


        self.DumpProgress = False
        data = ''
        append = False
        maximum = length
        for block in blocks:
            start_page = block * self.SrcImage.PagePerBlock
            end_page = (block+1) * self.SrcImage.PagePerBlock
            if block == start_block:
                start_page += start_block_page

            data += self.read_pages(start_page, end_page, True, filename, append = append, maximum = maximum, seq = self.UseSequentialMode)

            maximum -= self.SrcImage.PagePerBlock*self.SrcImage.PageSize

            if len(data) > length:
                break

            append = True

        self.DumpProgress = True
        return data[0:length]

