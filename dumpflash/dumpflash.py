# pylint: disable=invalid-name
# pylint: disable=line-too-long

#  uses ftdi: self.ftdi.set_bitmode(0, ftdi.Ftdi.BitMode.MCU)  --> BITMODE_MCU = 0x08      # MCU Host Bus Emulation mode,

# read approx 700 bytes and then goes stuck

# The K9F1G08X0C is a 1,056Mbit(1,107,296,256 bit) memory organized as 65,536 rows(pages) by 2,112x8 columns. 
# Spare 64x8 columns are located from column address of 2,048~2,111.
# Using samsung [/media/Rdisk/Info/Yealink/T36/recovery/T38G_IMG_20230129_022208_747_samsung_K9F1G08U0C.jpg]
#	size 128M x 8 Bit NAND Flash Memory
# 	Memory Cell Array : (128M + 4M) x 8bit
#   Data Register : (2K + 64) x 8bit
#   • Automatic Program and Erase
#   - Page Program : (2K + 64)Byte
#   - Block Erase : (128K + 4K)Byte
#   • Page Read Operation
#   - Page Size : (2K + 64)Byte
#   - Random Read : 25μs(Max.)
#   - Serial Access : 25ns(Min.)
# adressing: Column Address Low A0-A7 , Column Address High A8-A11, Row Address Low A12-A19, Row Address Hight A20-A27
# 1.056Mbit(1.107.296.256 bit) memory organized as 65,536 rows(pages) by 2,112x8 columns. Spare 64x8 columns are located from column address of 2,048~2,111.
# program and read operations are executed on a page basis, while the erase operation is executed on a block basis.
#
# apr 11 16:27:09 sh67 kernel: usb 2-1.7.1: usbfs: interface 1 claimed by ftdi_sio while 'python3' sets config #1

# works check pafoxp@sh67:~/code-dumpflash/dumpflash$ python3 dumpflash.py -c check_bad_blocks -v
# read pages last 64 bytes pafoxp@sh67:~/code-dumpflash/dumpflash$ python3 dumpflash.py -s -64 -c read -p 0 10
# test mode on fixed page65535 skip 10 insert aaaaa  python3 dumpflash.py  -t 16 -s 10 -d aaaaaaaa -c test

# Note: fix/explain oob

import sys
from optparse import OptionParser
import flashimage
import jffs2
import uboot
import random

parser = OptionParser()
# removed e[xtract],
parser.add_option("-c", dest = "command", default = "information", help = "Command (i[nformation], read, seq[uential_read], write, test, erase, extract_pages, check_ecc, find_uboot, dump_uboot,find_jffs2, dump_jffs2, check_bad_blocks, add_oob)")
parser.add_option("-i", dest = "raw_image_filename", default = '', help = "Use flashfile instead of flashdevice for operations")
parser.add_option("-o", dest = "output_filename", default = 'output.dmp', help = "Output filename")

parser.add_option("-t", type = "int", default = 0, dest = "tsize", help = "Transfer size FTDI")

parser.add_option("-L", action = "store_true", dest = "slow", default = False, help = "L-owSpeed, Set clock FTDI chip at 12MHz instead of 60MHz")
parser.add_option("-R", action = "store_true", dest = "raw_mode", default = False, help = "R-aw mode - skip bad block before readSeq/writing")
parser.add_option("-S", type = "int", default = 0, dest = "stream",  help = " Stream mode 0-off/per byte , 1-On "  )

parser.add_option("-r", action = "store_true", dest = "remove_oob", default = False, help = "r-emove OOB-part from write/read")
parser.add_option("--rof", action = "store_false", dest = "oob_xfile", default = True, help = "Remove OOB from fileoutput")
# TBD parser.add_option("--roc", action = "store_false", dest = "oob_xchip", default = True, help = "Remove OOB to chip")
# parser.add_option("-ri", action = "store_true", dest = "remove_oob_in", default = False, help = "Remove OOB from inputfile")
parser.add_option("-j", action = "store_true", dest = "add_jffs2_oob", default = False, help = "Add JFFS2 OOB to the source")

parser.add_option("-C", dest = "compare_target_filename", default = '', help = "When writing a file compare with this file before writing and write only differences", metavar = "COMPARE_TARGET_FILENAME")

parser.add_option("-n", dest = "name_prefix", default = '', help = "Set output file name prefix")

parser.add_option("-s", type = "int", default = 0, dest = "start_offset", help = "skip/size read or start/write offset (function dependant)")
parser.add_option("-d", dest = "output_datastring", default = chr(0xff), help = "Output databyte(s) string")

parser.add_option("-l", type = "int", default = 0, dest = "length")
parser.add_option("-p", type = "int", nargs = 2, dest = "pages", help = " start end (including)"  )
parser.add_option("-b", type = "int", nargs = 2, dest = "blocks", help = " start end (including)"  )

parser.add_option("-P", type = "int", default = 512, dest = "page_size", help = "override page size (2048)")
parser.add_option("-O", type = "int", default = 16, dest = "oob_size", help = "override OOB size (64)")
parser.add_option("--bp", type = "int", default = 32, dest = "pages_per_block", help = "override pages per block 64" )

parser.add_option("-v", action = "store_true", dest = "debug_info", default = False, help = "Display debug & addtional info lines")

(options, args) = parser.parse_args()

use_ansi = False
try:
    import colorama
    colorama.init()
    use_ansi = True
except:
    try:
        import tendo.ansiterm
        use_ansi = True
    except:
        pass

start_page = -1
end_page = -1

start_block = -1
end_block = -1

flash_image_io = flashimage.IO(options.raw_image_filename, options.start_offset,      \
                               options.length, options.page_size, options.oob_size,   \
                               options.pages_per_block, options.slow, options.stream, \
                               options.tsize, options.debug_info)


print('\n ====> initial I/O access mode for ftdi Slow=%s, Stream=%d' % (str(options.slow), options.stream ))

if not flash_image_io.is_initialized():
    print('Device not ready, aborting...')
    sys.exit(0)

flash_image_io.set_use_ansi(use_ansi)

print(' Command:', options.command ) # display the command we use


if options.pages is not None:
    if type(options.pages)==tuple:   # check type of list
       start_page = options.pages[0]
       if len(options.pages) > 1:
              end_page = options.pages[1]
    else: 
       start_page = options.pages
       end_page = start_page
    # print ( 'type(options.pages)', type(options.pages) ,', start_page=', type(start_page), ', end_page=', type(start_page) )
    if start_page < -1: start_page = (flash_image_io.SrcImage.PagePerBlock*flash_image_io.SrcImage.BlockCount) - ((start_page*-1)+1)
    if end_page < -1: end_page = (flash_image_io.SrcImage.PagePerBlock*flash_image_io.SrcImage.BlockCount) - (((end_page+1)*-1))

    if options.debug_info: 
        print('  Set Option Pages: %d ~ %d \n' % (start_page, end_page))

if options.blocks is not None:
    if type(options.blocks)==tuple:   # check type of list
       start_block = options.blocks[0]
       if len(options.blocks) > 1:
          end_block = options.blocks[1]
       else: 
          end_block = flash_image_io.SrcImage.BlockCount - 1
    else:  
       start_block = options.blocks
       end_block = start_block

    if end_block == 0:
       end_block = start_block
    if end_block < 0 or end_block >  flash_image_io.SrcImage.BlockCount:
       end_block = flash_image_io.SrcImage.BlockCount - 1
    if end_block <  start_block: end_block = start_block

    if options.debug_info: 
        print('  Set Option Blocks: %d ~ %d \n' % (start_block, end_block))

if start_page < 0 and start_block > -1:
    start_page = start_block * flash_image_io.SrcImage.PagePerBlock
    # if start_page < 0: start_page = 0
    # end_page = start_page

if end_page < 0 and end_block > -1:
    if end_block < start_block:
       end_block += start_block + end_block
    end_page = (start_block * flash_image_io.SrcImage.PagePerBlock) -1

if end_page < 0 and end_block > -1:
    if end_block >= start_block:
       end_page = end_block * flash_image_io.SrcImage.PagePerBlock
       if start_block == 0: 
           end_page = start_page + (flash_image_io.SrcImage.PagePerBlock - 1)
       elif end_block < 1: 
           end_page = (flash_image_io.SrcImage.PagePerBlock*flash_image_io.SrcImage.BlockCount) - (abs(end_block+1)*flash_image_io.SrcImage.PagePerBlock)
if options.debug_info: 
   print('>>>> checking parms1 resulting page : %d ~ %d  block : %d ~ %d' % (start_page, end_page, start_block, end_block) )


if end_page < start_page: end_page = start_page + end_page
if end_page > flash_image_io.SrcImage.PageCount:
   end_page = flash_image_io.SrcImage.PageCount
if end_page > flash_image_io.SrcImage.PageCount:
   end_page = flash_image_io.SrcImage.PageCount
if start_page  < 0: start_page = 0
if end_page    < 0: end_page   = (flash_image_io.SrcImage.PagePerBlock*flash_image_io.SrcImage.BlockCount) - 1
if options.debug_info: 
   print('>>>> checking parms2 resulting page : %d ~ %d  block : %d ~ %d' % (start_page, end_page, start_block, end_block) )

if start_block < 0:
   if start_page > 0:
      start_block = int(start_page / flash_image_io.SrcImage.PagePerBlock)
   else:
      start_block = 0
if end_block   < 0: 
   if end_page > 0:
      end_block = int((end_page + 1) / flash_image_io.SrcImage.PagePerBlock)
   else:
      end_block   = flash_image_io.SrcImage.BlockCount - 1
   if (end_block >= flash_image_io.SrcImage.BlockCount): end_block = flash_image_io.SrcImage.BlockCount - 1

if options.debug_info: 
   print('>>>> checking parms3 resulting page : %d ~ %d  block : %d ~ %d' % (start_page, end_page, start_block, end_block) )

if options.command == 'erase':	  # works //here5
  # sample: $ python3 dumpflash.py -b 1020 1020 -c erase -v
    flash_image_io.SrcImage.dump_info()
    start = start_block
    end = end_block
    
    print('Erasing Blocks: %d ~ %d , page %d - %d' % (start_block, end_block, start * flash_image_io.SrcImage.PagePerBlock, ((end+1) * flash_image_io.SrcImage.PagePerBlock)-1))
    flash_image_io.SrcImage.erase_block(start, end)
    
   # if options.blocks is not None:
   #    start = start_block
   #     end = end_block
   #    print('Erasing Blocks: %d ~ %d , page %d - %d' % (start_block, end_block, start * flash_image_io.SrcImage.PagePerBlock, end * flash_image_io.SrcImage.PagePerBlock))
   #    # flash_image_io.SrcImage.erase_block(start, end)
   # else:
   #    print('Erasing (default (all)')
   #    print('Erasing Blocks: %d ~ %d , page %d - %d' % (start_block, end_block, start * flash_image_io.SrcImage.PagePerBlock, end * flash_image_io.SrcImage.PagePerBlock))
   #     # flash_image_io.SrcImage.erase()

elif options.command == 'add_oob': # works and interact with files by adding oob to input file
  # sample: $ python3 dumpflash.py --bp 64 -P 2048 -O 64 -i datafiles/outputP65480-9.dmp -c add_oob   (-r -j )
    flash_image_io.SrcImage.dump_info()
    if options.raw_image_filename \
       and options.page_size:
         print('Add OOBS to (new) file %s' % (options.raw_image_filename))
         flash_image_io.add_oob(options.raw_image_filename, options.output_filename, options.add_jffs2_oob, options.remove_oob)
    else:
         print('(-r) --bp 64 -O-size 64 -P Pagesize 2048 -i input_file (NoOob!!) which create -o-utput=', options.output_filename )

elif options.command == 'extract_pages':  # works to interact on files  but unclear for purposes
  # sample command: $ python3 dumpflash.py -p 0 1 -O 64 -P 2048 --bp 64 -c extract_pages -i output_mtd1.dmp -v
    if options.raw_image_filename and options.page_size and options.oob_size:
        print('Extract data (0x%x - 0x%x) from file %s to %s remove_oob=%s' % (start_page, end_page, options.raw_image_filename, options.output_filename, str(options.remove_oob) ))
        flash_image_io.extract_pages(options.output_filename, start_page, end_page, remove_oob = options.remove_oob)
    else:
         print('(-r) --bp 64 -O-size 64 -P Pagesize 2048 -i input_file which extracts to -o-utput=', options.output_filename )

elif options.command == 'check_bad_blocks':  # works
  # sample: $ python3 dumpflash.py -c check_bad_blocks

    if options.blocks is not None:
       start_page = start_block * flash_image_io.SrcImage.PagePerBlock
       end_page = (end_block * flash_image_io.SrcImage.PagePerBlock) + 1

    print('Check bad blocks start_page: %d-%d' % (start_page, end_page))
    flash_image_io.check_bad_blocks(start_page, end_page)


elif options.command == 'check_ecc':
    flash_image_io.check_ecc()

elif options.command == 'find_uboot':  # works technically, not sure about function
  # sample python3 dumpflash.py -c find_uboot
    print('Searching for find_uboot')
    uboot_util = uboot.Util(flash_image_io)
    uboot_util.find()

elif options.command == 'dump_uboot':
    uboot_util = uboot.Util(flash_image_io)
    uboot_util.dump()

elif options.command == 'find_jffs2':
    jffs2_util = jffs2.Util(flash_image_io)
    jffs2_util.find()

elif options.command == 'dump_jffs2':
    jffs2_util = jffs2.Util(flash_image_io)
    jffs2_util.dump(options.name_prefix)

elif options.command[0] == 'i':  # works, prints chip information and allocated sizes
    flash_image_io.SrcImage.dump_info()

# elif options.command[0] == 'r' or options.command[0] == 's' :
elif options.command == 'read' or options.command == 'seq' :      # works for read
  # sample: $ python3 dumpflash.py -s 0 -t 1 -R -p 65216 65276  -c read (-r -j)
    if options.debug_info:    
       flash_image_io.SrcImage.dump_info()

    remove_oob = False
    if options.remove_oob:
        remove_oob = True

    sequential_read = False
    if options.command[0] == 's':
        sequential_read = True

    if end_page < start_page: end_page = start_page
    print('Command reading to file=%s, remove_oob=%s, start=%d, end=%d, Tsize=%d Skipping=%d' % (options.output_filename, str(remove_oob), start_page, end_page, options.tsize, options.start_offset))
    flash_image_io.read_pages(start_page, end_page, remove_oob, options.output_filename, seq = sequential_read, raw_mode = options.raw_mode, tsize = options.tsize, skip=options.start_offset)
    print('\nready, see file:', options.output_filename )

# elif options.command[0] == 'e':
#     if options.raw_image_filename:
#         print('Extract data from pages(0x%x - 0x%x) to %s' % (start_page, end_page, options.output_filename))
#         flash_image_io.extract_pages(options.output_filename, start_page, end_page, remove_oob = True)

elif options.command == 'write':  # works
  # sample: $ python3 dumpflash.py -s 0 -t 1 -p 65472 65472 -c write -v -j output_p65526.dmp  (-r -j  / remove these from input )
  #  offset $ python3 dumpflash.py -s 4 -t 1 -p 65529 65529 -c write -v outputP65529.dmp
  #    data $ python3 dumpflash.py -s 4 -t 1 -p 65529 65529 -c write -d abcdefg  -v outputP65529.dmp
    # filename = 'test'
    # Note: -r remove oob from input file

    # for i, arg in enumerate(sys.argv):
    #    print(f"Argument {i:>6}: {arg}")
    if len(args) > 0: filename = args[0]

    add_oob = True
    add_jffs2_eraser_marker = False

    if options.add_jffs2_oob:
        add_oob = True
        add_jffs2_eraser_marker = True

    if options.remove_oob:
        add_oob = False
        add_jffs2_eraser_marker = False

    if options.compare_target_filename != '':
        cfd = open(options.compare_target_filename, 'rb')
        cfd.seek(options.start_offset)

        fd = open(filename, 'rb')
        fd.seek(options.start_offset)

        current_page = 0
        while 1:
            cdata = cfd.read(flash_image_io.SrcImage.PageSize)  # compare dataset and write only differences
            data  =  fd.read(flash_image_io.SrcImage.PageSize)  # dataset

            if not data:
                break

            if cdata != data:
                print('Changed Page:0x%x file_offset: 0x%x' % (start_page+current_page, options.start_offset + current_page*flash_image_io.SrcImage.PageSize))
                current_block = current_page / flash_image_io.SrcImage.PagePerBlock

                print('Erasing and re-programming Block: %d' % (current_block))
                flash_image_io.SrcImage.erase_block_by_page(current_page)

                target_start_page = start_page+current_block*flash_image_io.SrcImage.PagePerBlock
                target_end_page = target_start_page+flash_image_io.SrcImage.PagePerBlock-1

                print('Programming Page: %d ~ %d' % (target_start_page, target_end_page))
                flash_image_io.SrcImage.write_pages(
                    filename, 
                    options.start_offset + current_block*flash_image_io.SrcImage.PagePerBlock*flash_image_io.SrcImage.PageSize, 
                    target_start_page, 
                    target_end_page, 
                    add_oob, 
                    add_jffs2_eraser_marker = add_jffs2_eraser_marker, 
                    raw_mode = options.raw_mode
                )

                current_page = (current_block+1)*flash_image_io.SrcImage.PagePerBlock+1
                fd.seek(options.start_offset+current_page * flash_image_io.SrcImage.PageSize)
                cfd.seek(options.start_offset+current_page * flash_image_io.SrcImage.PageSize)

            else:
                current_page += 1
    else:
        print('Writepages Page: file=%s start_offset=0x%x , start_page=0x%x, end_page=0x%x, oob=%s, jffs2=%s' % (filename, options.start_offset, start_page, end_page, str(add_oob), str(add_jffs2_eraser_marker))  )
        # oob_postfix = b'\xfe' * 13
        # if oob_postfix[5] != b'\xff': print('Writepages Page: oob_postfix length=%d ' % (len(oob_postfix))  )
        # if oob_postfix[5] != 0xff: print('Writepages Page: oob_postfix length=%d , oob5=0x%x ' % (len(oob_postfix), oob_postfix[5])  )
        flash_image_io.SrcImage.write_pages(filename, options.start_offset, start_page, end_page, add_oob, add_jffs2_eraser_marker = add_jffs2_eraser_marker, raw_mode = options.raw_mode, oob_file = options.oob_xfile )

elif options.command == 'testp':  # works , create  test pages using datasets
  # sample set:  $ python3 dumpflash.py -p 65519 65519 -c testp -v   # will skip write due -v
  #    dataset0  $ python3 dumpflash.py -s 0 -t 2112 -p 65519 65519 -c read output.dmp    # page rows 00-0f
  #    dataset6  $ python3 dumpflash.py -s 1 -t 2112 -p 65519 65519 -c read output.dmp    # random
  #     all00ds7  $ python3 dumpflash.py -s 7 -t 2112 -R -p 65472 65472  -c testr

    filename = ''
    use_datastring = ''

    current_block = int(start_page / flash_image_io.SrcImage.PagePerBlock)
    start_offset = options.start_offset

    oob_option = False
    if options.remove_oob:
        oob_option = True

    add_jffs2_eraser_marker = False
    if options.add_jffs2_oob:
        add_oob = True
        add_jffs2_eraser_marker = True

    if start_page < 0:
       print('\nInvalid start_page < 0=', start_page)
       raise Exception('Invalid start_page.')
     
    end_page = start_page
    if options.debug_info:
       print('\nWrite test data pages ', start_page,  ', end_page=', end_page)

    # create datasets
    read_data1 = chr(1)   # remainder 16  , rows 00 01 .. 0E 0F
    for i in range(1, 2112, 1):
        read_data1 += chr(i%16)

    read_data2 = chr(2)   # remainder 256 , col 00 01 .. ..  FF 
    for i in range(1, 2112, 1):
        read_data2 += chr(i%256)

    read_data3 = chr(3)   # special rowcount + 01 02 .. 0E 0F
    for i in range(1, 2112, 1):
        x = int(i%16)
        if x == 0: x = int(i/16) 
        read_data3 += chr(x)

    read_data4 = chr(4)   # spacial rownumber & double databyte 11..EE FF
    for i in range(1, 2112, 1):
        x = int(i%16)
        if x == 0: x = int(i/16)
        else: x += (x * 16) 
        read_data4 += chr(x)

    read_data5 = chr(5)   # spacial rownumber & double databyte 11..EE FF
    val1 = 0xaa  # (1010 1010)
    val2 = 0x55  # (0101 0101
    y = val2
    x = 5
    for i in range(1, 2048, 1):
        x = int(i%16)
        if x == 0:  
           x = int(i/16)
           # print ('i=', i, 'x1=', x)
        else: 
           if y == val1: y = val2
           else: y = val1
           x = y
           # print ('i=', i, ', x=', x)

        read_data5 += chr(x)

    read_data6 = chr(6)   # spacial rownumber & double databyte 11..EE FF
    for i in range(1, 2112, 1):
        x = int(i%256)
        read_data6 += chr(random.randrange(0, 255, 1))

    read_data7 = chr(7)   # spacial page 7  with zeroes
    for i in range(1, 2112, 1):
        read_data7 += chr(0x00)

    read_data8 = chr(8)   # special page 8  with zeroes
    for i in range(1, 2112, 1):
        read_data8 += chr(0xff)

    read_data9 = chr(9)   # spacial page 9 numbered 09 01..02+03..04  with ff
    read_data9 += chr(1) 
    for i in range(2, 2047, 1):
        read_data9 += chr(0xff)
    read_data9 += chr(2)
    read_data9 += chr(3)
    for i in range(1, 63, 1):
        read_data9 += chr(0xff)
    read_data9 += chr(4)

    read_data10 = chr(10)   # spacial page 10 numbered 09 01..02+03..04  with 00
    read_data10 += chr(1) 
    for i in range(2, 2047, 1):
        read_data10 += chr(0x00)
    read_data10 += chr(2)
    read_data10 += chr(3)
    for i in range(1, 63, 1):
        read_data10 += chr(0x00)
    read_data10 += chr(4)

    read_data11 = chr(11)   # spacial page 11 numbered 0B FE
    read_data11 += chr(1) 
    for i in range(2, 2047, 1):
        read_data11 += chr(0xFE)
    read_data11 += chr(2)
    read_data11 += chr(3)
    for i in range(1, 63, 1):
        read_data11 += chr(0xFE)
    read_data11 += chr(4)


    read_data12 = chr(12)   # spacial page 12 numbered 0C 7F
    read_data12 += chr(1) 
    for i in range(2, 2047, 1):
        read_data12 += chr(0x7F)
    read_data12 += chr(2)
    read_data12 += chr(3)
    for i in range(1, 63, 1):
        read_data12 += chr(0x7F)
    read_data12 += chr(4)

    read_data13 = chr(13)   # spacial page 12 numbered 0C 7E
    read_data13 += chr(1) 
    for i in range(2, 2047, 1):
        read_data13 += chr(0x7E)
    read_data13 += chr(2)
    read_data13 += chr(3)
    for i in range(1, 63, 1):
        read_data13 += chr(0x7E)
    read_data13 += chr(4)


         # check which dataset to use
    read_data = read_data1
    if  start_offset == 1:
       print ('Using dataset 01 col 00 01 .. 0E 0F')
    if  start_offset == 2:
       print ('Using dataset 02 col 00 01 .. ..  FF ')
       read_data = read_data2
    if  start_offset == 3:
       print ('Using dataset 03 row + 01 02 .. 0E 0F')
       read_data = read_data3
    if  start_offset == 4:
       print ('Using dataset 04 ddbyte row 11..EE FF')
       read_data = read_data4
    if  start_offset == 5:
       print ('Using dataset 05 0xAA 0x55')
       read_data = read_data5
    if  start_offset == 6:
       print ('Using dataset 06 random')
       read_data = read_data6
    if  start_offset == 7:
       print ('Using dataset 07 all 00')
       read_data = read_data7
    if  start_offset == 8:
       print ('Using dataset 08 all ff')
       read_data = read_data8
    if  start_offset == 9:
       print ('Using dataset 09 all 0901..02+03..04 + repeat ff')
       read_data = read_data9

    if  start_offset == 10:
       print ('Using dataset 10 all 0901..02+03..04 + repeat 00')
       read_data = read_data10
    if  start_offset == 11:
       print ('Using dataset 11 all 0BFE..02+03..04 + repeat FE')
       read_data = read_data11
    if  start_offset == 12:
       print ('Using dataset 12 all 0B7F..02+03..04 + repeat 7F')
       read_data = read_data12
    if  start_offset == 13:
       print ('Using dataset 13 all 0B7E..02+03..04 + repeat 7E')
       read_data = read_data13


    start_page -= 1  # start after this serie 

    # write comhinations:
    start_page += 1; end_page = start_page
    current_block = int(start_page / flash_image_io.SrcImage.PagePerBlock)
    start_offset = 0
    print ('\n--1 Create TestPage: ', start_page, 'Offset=', options.start_offset, 'Block=' , current_block, 'Start_offset=', start_offset, ', len(read_data)=', len(read_data)  )
    print ('Byte1=0x%x 0x%x 0x%x 0x%x 0x%x  ' % ( ord(read_data[0]), ord(read_data[1]), ord(read_data[2]), ord(read_data[3]), ord(read_data[4]) ) ) 
    flash_image_io.SrcImage.write_pages(filename, options.start_offset, start_page, end_page, oob_option, add_jffs2_eraser_marker = add_jffs2_eraser_marker, raw_mode = options.raw_mode, datastring = read_data) 

elif options.command == 'testr':
    remove_oob = False
    filename = options.output_filename

    if options.remove_oob:
        remove_oob = True
    sequential_read = False
    if options.command[0] == 's':
        sequential_read = True
    if end_page < start_page: end_page = start_page

    filename1 = options.output_filename + '1'
    flash_image_io.read_pages(start_page, end_page, remove_oob, filename1, seq = sequential_read, raw_mode = options.raw_mode, tsize = 1, skip=0)

    filename2 = options.output_filename + '2'
    flash_image_io.read_pages(start_page, end_page, remove_oob, filename2, seq = sequential_read, raw_mode = options.raw_mode, tsize = 1, skip=0)

    filename3 = options.output_filename + '3'
    flash_image_io.read_offset_pages(start_page, end_page, remove_oob, filename3, seq = sequential_read, raw_mode = options.raw_mode, tsize = options.tsize, skip=options.start_offset)

    filename4 = options.output_filename + '4'
    flash_image_io.read_pages(start_page, end_page, remove_oob, filename4, seq = sequential_read, raw_mode = options.raw_mode, tsize = 1, skip=0)


    print('\nready, output=', options.output_filename ,', see fileref:', filename4, '(1-4)')


elif options.command == 'test': # works and only uses page 65535
  # sample:   $ python3 dumpflash.py -c test  (-s offset -d string  -r -j )    # page rows 00-0f
    start_page = flash_image_io.SrcImage.PageCount-1  # fixed page
    end_page   = flash_image_io.SrcImage.PageCount-1
    # -s options.start_offset  in page
    filename = ''

    if options.debug_info:
       print('Test mode !!!: fixed start_page=', start_page,  ', end_page=', end_page)

    oob_option = False
    add_jffs2_eraser_marker = False

    use_datastring = ''
    if options.output_datastring:
       use_datastring = options.output_datastring
       if options.debug_info:
          print('We have a datastring=', options.output_datastring)

    if remove_oob:
        oob_option = True

    print('\nCommand test Writing to NaND=%s, start_offset=0x%x , start_page=0x%x, end_page=0x%x, oob=%s, jffs2=%s' % (filename, options.start_offset, start_page, end_page, str(oob_option), str(add_jffs2_eraser_marker))  )

    # print('Erasing and re-programming Block: %d' % (current_block))
    # flash_image_io.SrcImage.erase_block_by_page(current_page)

    # print('Programming Page: %d ~ %d' % (target_start_page, target_end_page))
    # 
    current_block = int(start_page / flash_image_io.SrcImage.PagePerBlock)
    # start_offset = options.start_offset + current_block*flash_image_io.SrcImage.PagePerBlock*flash_image_io.SrcImage.PageSize
    start_offset = options.start_offset
    if options.debug_info:
       print ('-- Pagecount=', flash_image_io.SrcImage.PageCount-1, 'Offset=', options.start_offset, 'Block=' , current_block, 'Start_offset=', start_offset, ', data=', use_datastring) 



    print('\nCommand Test reading to NanD=%s, Block=%d remove_oob=%s, start=0x%x, length=0x%x, Tsize=%d' % (filename, current_block, str(oob_option), start_page, end_page, options.tsize))
    read_data = flash_image_io.read_pages(start_page, end_page, False, filename = '', seq = False, raw_mode = False, tsize = options.tsize)


    data_offset = '-'
    if len(read_data) > options.start_offset: data_offset = read_data[options.start_offset]

    if options.debug_info:
       print('readdata: start_page=',start_page , 'length(read_data)=', len(read_data), ', class=', type(read_data) , ', Offset=', options.start_offset , ', data@s=0x%x' % (ord(data_offset)) )

    print('\nCommand test Writing to NaND=%s, start_offset=0x%x , start_page=0x%x, end_page=0x%x, oob=%s, jffs2=%s' % (filename, options.start_offset, start_page, end_page, str(oob_option), str(add_jffs2_eraser_marker))  )
    if options.debug_info:
       print ('-- Pagecount=', flash_image_io.SrcImage.PageCount-1, 'Offset=', options.start_offset, 'Block=' , current_block, 'Start_offset=', start_offset, ', use_datastring=', use_datastring) 

    # if oob_option: 
    #    oob_option = True

    # >>> x = "Hello World!" >>> x[2:] 'llo World!'
    #                       >>> x[:2] 'He'
    #                       >>> x[:-2] 'Hello Worl'
    #                       >>> x[-2:] 'd!'
    #                       >>> x[2:-2] 'llo Worl'
    # s = s[ beginning : beginning + LENGTH]
    # 
    # print('-- rewrite0: datalen=', len(read_data), ' replacelen=', len(use_datastring) ) # debug
    # print ('-- test_001: len(read_data)=', len(read_data)) 
    
    if start_offset == 0:
       read_data = use_datastring + read_data[len(use_datastring):len(read_data)]
       # read_data = read_data[0:len(read_data)]
       # test debug print('-- rewrite1: datalen=', len(read_data))
    else: 
       read_data = read_data[0:start_offset] + use_datastring + read_data[start_offset+len(use_datastring):len(read_data)] 
    # print('-- rewrite2: datalen=', len(read_data))  # test debug
    # read_data[start_offset] = use_datastring[0] # cannot itemize replace

    # if options.debug_info:  # check types in python
    #   testbyte1 = b'\xff'   # type class
    #   testbyte2 = chr(0xff) # type str
    #   testbyte3 = int(255)  # type int
    #   print('>--> testbyte1=%s testbyte2=%s testbyte3=%s, use_datastring=%s  read_data=%s' % (  type(testbyte1), type(testbyte2), type(testbyte3), type(use_datastring), type(read_data) ) )


    flash_image_io.SrcImage.write_pages(filename, options.start_offset, start_page, end_page, oob_option, add_jffs2_eraser_marker = add_jffs2_eraser_marker, raw_mode = options.raw_mode, datastring = read_data) 


