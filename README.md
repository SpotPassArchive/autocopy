# autocopy
This script will dump the BOSS databases for Pretendo using NAND dumps.  For more information, see https://spotpassarchive.github.io/

# Running
These instructions will differ depending on the OS you use

## Windows
1. Download [autocopy.exe](https://github.com/SpotPassArchive/autocopy/releases/latest/download/autocopy.exe)
2. Run it, either by double-clicking it or through the Command Prompt
Note: if you get a SmartScreen notice, click allow

## macOS
1. Download [autocopy-macos](https://github.com/SpotPassArchive/autocopy/releases/latest/download/autocopy-macos)
2. Right-click (or control-click) the downloaded file, then click "Open"
**You MUST start it this way, or else it won't run**
<img src="https://github.com/SpotPassArchive/autocopy/raw/main/images/macos-1.png" alt="context menu showing Open" width="186">
3. Click "Open" on the dialog that appears
<img src="https://github.com/SpotPassArchive/autocopy/raw/main/images/macos-3.png" alt="dialog that says: Apple cannot check it for malicious software" width="372"></p>
4. From now on, you can skip steps 2 and 3

## Linux
1. Download [autocopy-linux](https://github.com/SpotPassArchive/autocopy/releases/latest/download/autocopy-linux)
2. Open a terminal and enter the directory you downloaded it from
3. Run `chmod +x ./autocopy-linux && ./autocopy-linux`

# Thanks
In no particular order:
* MisterSheeple: testing, introducing me to people in SpotPass Archival Project Discord, helping people use my script, many ideas
* ihaveamac: writing the incredibly useful [pyctr library](https://github.com/ihaveamac/pyctr), helping me with using it, building/signing the macOS and Windows versions
* ZeroSkill: testing, telling me when my script was broken, help with making an executable
* Zen: introducing me to ihaveamac, and many useful ideas
* Probably others (sorry!)
