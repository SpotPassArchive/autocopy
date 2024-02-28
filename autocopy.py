#!/bin/python3

VERSION = (0, 1, 0) # major, minor, patch
VERSION_STRING = "v{}".format(".".join([str(version_part) for version_part in VERSION]))

import sys
import os
import struct
import contextlib
import pathlib
import hashlib
import io
import argparse
import traceback

try:
    from pyctr.type.save.disa import DISA
    from pyctr.type.nand import NAND
    from pyctr.crypto import CryptoEngine
    from pyctr.crypto import engine
except ImportError as exception:
    if __name__ == "__main__":
        traceback.print_exception(exception)
        print('Please run "pip install -r requirements.txt"', file=sys.stderr)
        sys.exit(1)
    else:
        raise exception from None

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

def is_duplicate(path: str, filename: str, new_hash: bytes) -> bool:
    "checks if the file has been dumped already"
    # because "file.bin" will automatically be renamed to "file.2.bin",
    # this must remove the ".bin" and check every file starting with the prefix "file"
    filename_start = filename.rsplit(os.path.extsep, 1)[0]
    for existing_filename in os.listdir(path):
        existing_path = os.path.join(path, existing_filename)
        if not os.path.isfile(existing_path):
            continue
        if existing_filename.startswith(filename_start):
            with open(existing_path, "rb") as compare_file:
                file_hash = hashlib.md5(compare_file.read()).digest()
            if file_hash == new_hash:
                return True
    return False

def get_crypto_engine(boot9: pathlib.Path = None):
    if os.path.isfile(boot9):
        crypto = CryptoEngine(boot9=boot9)
    else:
        # use autodetection
        try:
            crypto = CryptoEngine(boot9=None)
        except engine.BootromNotFoundError:
            print("An ARM9 BootROM was not found.  "
                  "Please dump it from ANY console (not necessarily the one that had the NAND backup) "
                  "and place it here, making sure it's named boot9.bin", file=sys.stderr)
            sys.exit(1)
    return crypto

# thanks to ihaveahax for telling me about pyctr
def extract_nand_backup(path: pathlib.Path, crypto: CryptoEngine = None, boot9: pathlib.Path = None, dev: bool=False,
                        otp: str=None, cid: str=None, id0: str=None, skip_duplicate_check: bool=False, quiet: bool=False) -> None:
    "extracts 4 layers of encoding from the NAND dump in order to get partitionA.bin"
    if not quiet:
        print("Extracting NAND backup {}...".format(os.path.basename(path)))
    # this way, there doesn't need to be a seperate crypto for each console
    if crypto is None:
        crypto = get_crypto_engine(boot9=boot9)
    with NAND(file=path, dev=dev, crypto=crypto, otp_file=otp, cid_file=cid) as nand:
        # I am AMAZED I managed to do all this without a single temporary file or caching too much in memory
        with nand.open_ctr_fat() as ctrnand_handle:
            movable_sed = fat.readbytes("/private/movable.sed")
            crypto.setup_sd_key(data=movable_sed)
            # detect the ID0
            if id0 is None:
                id0 = crypto.id0.hex()
                if id0 is None:
                    print("failed to read id0. this is a bug in ninfs, using alternate id0 detection", file=sys.stderr)
                    id0 = ctrnand_handle.listdir("/data")[0] # simply open the first file/folder in /data
                if not quiet:
                    print("id0 = {}".format(id0))
            disa_path = "/data/{}/sysdata/00010034/00000000".format(id0)

            # get the DISA image containing the data we want,
            # located at "/data/<id0>/sysdata/00010034/00000000"
            with ctrnand_handle.openbin(path=disa_path, mode="rb") as disa_image_handle:
                # now read that DISA image's partitionA.bin
                partition_a = extract_disa_partition_a(disa_handle=disa_image_handle)
                filename = find_unused_filename("partitionA.bin")

                # check if the file has been dumped already
                if not skip_duplicate_check:
                    partition_a_hash = hashlib.md5(partition_a).digest()
                    if is_duplicate(path=os.path.curdir, filename="partitionA.bin", new_hash=partition_a_hash):
                        if not quiet:
                            print("Already dumped, skipping")
                        return

                # finally, write it to a file
                with open(filename, "wb") as partition_a_out:
                    partition_a_out.write(partition_a)
                if not quiet:
                    print("Dumped to {}".format(filename))

def extract_nand_backups(paths: list, boot9: pathlib.Path = None, dev: bool=False, otp: str=None, id0: str=None, skip_duplicate_check: bool=False, quiet: bool=False) -> None:
    crypto = get_crypto_engine(boot9=boot9)
    for path in paths:
        extract_nand_backup(path=path, crypto=crypto, boot9=boot9, dev=dev, otp=otp, id0=id0, skip_duplicate_check=skip_duplicate_check, quiet=quiet)

def interactive() -> None:
    print("Welcome to autocopy {}!".format(VERSION_STRING))
    print("This script will dump the BOSS databases for Pretendo using NAND dumps")
    print("(Hint: you can also use this from the command line, try --help)")
    print("You do not need to use your 3DS or GodMode9")
    print("If you still have the 3DS, you should instead dump it using the normal method from spotpassarchive.github.io")
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
        parser.add_argument("-9", "--boot9", type=pathlib.Path, default="boot9.bin", help="the ARM9 BootROM (boot9.bin), can be dumped from any console")
        parser.add_argument("-n", "--skip-duplicate-check", action="store_true", help="don't check if the file has been dumped already")
        parser.add_argument("-q", "--quiet", action="store_true", help="suppress output, except errors")
        parser.add_argument("-V", "--version", action="store_true", help="print version and exit")
        advanced = parser.add_argument_group("advanced")
        advanced.add_argument("-d", "--dev", action="store_true", help="extract from a development console's NAND")
        advanced.add_argument("-o", "--otp", type=pathlib.Path, help="path to the OTP file, only needed for old NAND dumps")
        advanced.add_argument("-c", "--cid", type=pathlib.Path, help="path to the CID file, only needed for old NAND dumps")
        advanced.add_argument("-0", "--id0", type=str, help="only needed if you encounter an error")
        args = parser.parse_args()
        if not args.quiet or args.version:
            print("autocopy {}".format(VERSION_STRING))
        if args.version:
            sys.exit()
        extract_nand_backups(paths=args.nanddumps, boot9=args.boot9, dev=args.dev, otp=args.otp, id0=args.id0, skip_duplicate_check=args.skip_duplicate_check, quiet=args.quiet)

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
