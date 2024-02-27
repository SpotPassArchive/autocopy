#!/bin/python3

import sys
import os
import struct
import contextlib
import pathlib
import hashlib
import io
import argparse

try:
    from ninfs.mount import nandctr
    import pyreadpartitions
    import fuse
    from pyfatfs import PyFat, FatIO
    from pyctr.type.save.disa import DISA
except ImportError as exception:
    if __name__ == "__main__":
        print('Please run "pip install -r requirements.txt"', file=sys.stderr)
        sys.exit(1)
    else:
        raise exception from None

class CTRNandHandle(io.RawIOBase):
    "a stream used for reading from the CTRNAND image"
    def __init__(self, mount: nandctr.CTRNandImageMount, path: pathlib.Path) -> None:
        self.mount = mount
        self.path = path
        attr = self.mount.getattr(self.path)
        self._offset = 0
        self.size = attr["st_size"]
        self.__closed = False
        self._handle = self.mount.open(path, attr["st_mode"])

    def __check_closed(self) -> None:
        if self.__closed:
            raise ValueError("I/O operation on closed file.")

    def read(self, size: int=-1) -> bytes:
        self.__check_closed()
        read_bytes = self.mount.read(path=self.path, size=size, offset=self._offset, fh=self._handle)
        self._offset += len(read_bytes)
        return read_bytes

    def readable(self) -> bool:
        self.__check_closed()
        return True

    def seek(self, offset: int, whense: int=os.SEEK_SET) -> None:
        whense = int(whense)
        if whense == os.SEEK_SET:
            self._offset = offset
        elif whense == os.SEEK_CUR:
            pass
        elif whense == os.SEEK_END:
            self._offset = self.size
        else:
            raise ValueError("whense value {} unsupported".format(whense))

    def seekable(self) -> bool:
        self.__check_closed()
        return True

    def close(self) -> None:
        # I don't know how to close it properly, so I'm just marking it as closed
        self.__closed = True

def find_unused_filename(path: str) -> str:
    "find an unused filename (e.g. file.2.bin instead of file.bin)"
    path = os.path.abspath(path)
    filename = os.path.basename(path)
    directory = os.path.dirname(path)
    split_filename = filename.rsplit(os.path.extsep, 1)
    if len(split_filename) == 2:
        name, extension = split_filename
    elif len(split_filename) == 1:
        # no extension
        name, = split_filename
        extension = None

    directory_list = os.listdir(directory)
    number = 2
    while True:
        if filename not in directory_list:
            return filename
        if extension is None:
            filename = os.path.extsep.join([name, str(number)])
        else:
            filename = os.path.extsep.join([name, str(number), extension])
        number += 1

def byteswap32(n: int) -> int:
    return (((n << 24) & 0xFF000000) |
            ((n <<  8) & 0x00FF0000) |
            ((n >>  8) & 0x0000FF00) |
            ((n >> 24) & 0x000000FF))

def decode_key_y(key_y: bytes) -> str:
    """
    calculates ID0 from keyY
    see https://3dbrew.org/wiki/Nand/private/movable.sed for more information
    """
    key_y_hash = hashlib.sha256(key_y).hexdigest()
    id0 = ""
    for word_index in range(0, 32, 8):
        word = int(key_y_hash[word_index:word_index+8], 16)
        swapped = byteswap32(word)
        id0 += "{:02x}".format(swapped)
    return id0

def get_id0(mount: nandctr.CTRNandImageMount) -> str:
    "extracts id0 from a NAND dump's movable.sed"
    try:
        with CTRNandHandle(mount, "/essential/movable.bin") as movable_sed:
            movable_sed.seek(0x110)
            key_y = movable_sed.read(0x10)
    except fuse.FuseOSError:
        return None
    return decode_key_y(key_y)

def get_id0_alt(fat_handle: PyFat.PyFat, location: int=0) -> str:
    "gets the ID0 by listing the contents of /data"
    dir_entry = fat_handle.root_dir.get_entry("/data")
    dirs = dir_entry.get_entries()[0]
    return str(dirs[0]) # returns the name of the first directory

def get_mbr_partition_location(handle: io.IOBase, partition_index: int=0) -> int:
    "gets the location of a particular partition in a multi-partition disk image"
    partition_info = pyreadpartitions.get_mbr_info(handle)
    target_partition = partition_info.partitions[0]
    partition_location = target_partition.lba * partition_info.lba_size
    return partition_location

def extract_nand_backup(path: pathlib.Path, boot9: pathlib.Path = None, dev: bool=False, otp: str=None, cid: str=None, id0: str=None, force_disa: bool=False):
    "extracts 4 layers of encoding from the NAND dump in order to get partitionA.bin"
    print("Extracting NAND backup {}...".format(os.path.basename(path)))
    nand_stat = nandctr.get_time(path)
    with open(path, "rb") as nand:
        with contextlib.redirect_stdout(None): # suppress output
            mount = nandctr.CTRNandImageMount(nand_fp=nand, g_stat=nand_stat, dev=dev, readonly=True, otp=otp, cid=cid, boot9=boot9)
        # I am AMAZED I managed to do all this without a single temporary file or caching too much in memory
        with CTRNandHandle(mount, "/ctrnand_full.img") as ctrnand_handle:
            # the file is a multi-partition disk image, so this finds the first partition
            ctrnand_partition_location = get_mbr_partition_location(ctrnand_handle, 0)

            # mount the FAT partition
            fat_handle = PyFat.PyFat(offset=ctrnand_partition_location)
            fat_handle.set_fp(fp=ctrnand_handle)

            # detect the ID0
            if id0 is None:
                id0 = get_id0(mount=mount)
                if id0 is None:
                    print("failed to read id0. this is a bug in ninfs, using alternate id0 detection")
                    id0 = get_id0_alt(fat_handle=fat_handle)
                print("id0 = {}".format(id0))
            disa_path = "/data/{}/sysdata/00010034/00000000".format(id0)

            # now get the DISA image containing the data we want,
            # located at "/data/<id0>/sysdata/00010034/00000000"
            disa_image_handle = FatIO.FatIO(fs=fat_handle, path=disa_path)

            # now read that DISA image's partitionA.bin
            partition_a = extract_disa_partition_a(disa_handle=disa_image_handle)
            filename = find_unused_filename("partitionA.bin")

            # finally, write it to a file
            with open(filename, "wb") as partition_a_out:
                partition_a_out.write(partition_a)
            print("Extracted to {}".format(filename))

def extract_nand_backups(paths: list, boot9: pathlib.Path = None, dev: bool=False, otp: str=None, id0: str=None, force_disa: bool=False):
    for path in paths:
        extract_nand_backup(path=path, boot9=boot9, dev=dev, otp=otp, id0=id0, force_disa=force_disa)

def interactive() -> None:
    print("Welcome to autocopy!")
    print("This script will dump the BOSS databases for Pretendo using NAND dumps")
    print("(Hint: you can also use this from the command line, try --help)")
    print("You do not need to use your 3DS or GodMode9")
    print("If you still have the 3DS, you should instead dump it using the normal method from https://pretendo.network/docs/network-dumps")
    answer = input("Do you want to continue? [Y/n] ").strip().upper()
    if answer != "" and answer != "Y" and answer != "YES":
        print("Goodbye")
        return
    path = input("Type the file path: ").strip()
    if not path:
        return
    extract_nand_backup(path)

def main() -> None:
    # if there are no arguments, run in interactive mode
    if len(sys.argv) == 1:
        interactive()
    else:
        parser = argparse.ArgumentParser(description="A script to automatically dump Pretendo BOSS files from a NAND dump")
        parser.add_argument("nanddumps", type=pathlib.Path, nargs="+", help="path to NAND dump(s)")
        parser.add_argument("-9", "--boot9", type=pathlib.Path, required=True, help="the ARM9 BootROM (boot9.bin), can be dumped from any console")
        advanced = parser.add_argument_group("advanced")
        advanced.add_argument("-d", "--dev", action="store_true", help="extract from a development console's NAND")
        advanced.add_argument("-o", "--otp", type=str, help="only needed for old NAND dumps")
        advanced.add_argument("-c", "--cid", type=str, help="only needed for old NAND dumps")
        advanced.add_argument("-0", "--id0", type=str, help="only needed if you encounter an error")
        advanced.add_argument("--force-disa", action="store_true", help="if you got an error, this might make it work but will probably break things")
        args = parser.parse_args()
        extract_nand_backups(paths=args.nanddumps, boot9=args.boot9, dev=args.dev, otp=args.otp, id0=args.id0, force_disa=args.force_disa)

# thanks to ZeroSkill for making this a LOT simpler,
# and not return a corrupted file
def extract_disa_partition_a(disa_handle: io.IOBase) -> bytes:
    with DISA(disa_handle) as disa:
        partition = disa.partitions[0].dpfs_lv3_file
        partition.seek(0x9000)
        content = partition.read()
        return content

if __name__ == "__main__":
    main()
