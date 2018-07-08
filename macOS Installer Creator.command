#!/usr/bin/python
# 0.0.0
from Scripts import *
import os, tempfile, shutil, time, plistlib, json, sys

class CIM:
    def __init__(self):
        self.r = run.Run()
        self.re = reveal.Reveal()
        self.u = utils.Utils()
        self.d = disk.Disk()
        self.name = "macOS Installer Creator"
        self.esd_loc = "Contents/SharedSupport"
        self.target_disk = None
        self.target_app  = None
        self.method      = None
        self.os_vers     = self.r.run({"args":["/usr/bin/sw_vers","-productVersion"]})[0].strip()
        self.target_os   = None
        self.format_disk = False
        self.rename      = True
        # Setup the defaults for versions
        # Mostly focuses on the cim method - as asr
        # will nearly always be the same
        self.min_cim = "10.9.0"
        self.v_default = {
            "version" : "0.0.0", 
            "operand" : "gtr", 
            "methods" : ["createinstallmedia", "asr"], 
            "cimargs" : [
                "/usr/bin/sudo", 
                "[[target_app]]/Contents/Resources/createinstallmedia", 
                "---volume", 
                "[[mount_point]]",
                "--applicationpath",
                "[[target_app]]",
                "--nointeraction"
                ]
            }
        self.versions = [
            { 
                "version" : "10.14.0", 
                "operand" : "geq",
                "cimargs" : [
                    "/user/bin/sudo",
                    "[[target_app]]/Contents/Resources/createinstallmedia",
                    "--volume",
                    "[[mount_point]]",
                    "--nointeraction",
                    "--downloadassets"
                ]
            }
        ]
    def select_method(self):
        self.u.head("Creation Method")
        print("")
        print("1. CreateInstallMedia (10.9+)")
        print("2. ASR (Apple Software Restore)")
        print("")
        print("M. Main Menu")
        print("Q. Quit")
        print("")
        menu = self.u.grab("Please select an option:  ").lower()
        if menu == "m":
            return
        elif menu == "q":
            self.u.custom_quit()
        elif menu == "1":
            if self.u.compare_versions(self.os_vers, self.min_cim) == True:
                # Version too low for CIM
                self.u.head("OS Version Too Low")
                print("")
                print("The current OS version ({}) is lower than the minimum".format(self.os_vers))
                print("needed to use createinstallmedia ({}).".format(self.min_cim))
                print("")
                self.u.grab("Press [enter] to return...")
                self.select_method()
                return
            self.method = "createinstallmedia"
            return
        elif menu == "2":
            self.method = "asr"
            return
        self.select_method()

    def select_disk(self):
        self.d.update()
        self.u.head("Select Disk")
        print("")
        vols = self.d.get_mounted_volume_dicts()
        count = 0
        for v in vols:
            count += 1
            print("{}. {} ({})".format(count, v['name'], v['identifier']))
        print("")
        print("M. Main Menu")
        print("Q. Quit")
        print("")
        menu = self.u.grab("Please pick the target volume:  ").lower()
        if menu == "m":
            return
        elif menu == "q":
            self.u.custom_quit()
        # Now we try to resolve menu to a number - or a disk
        try:
            m = int(menu)
            disk = vols[m-1]
        except:
            disk = None
            d = self.d.get_identifier(menu)
            if d:
                disk = { "name" : self.d.get_volume_name(menu), "identifier" : self.d.get_identifier(menu) }
        if disk:
            # We got something!
            self.target_disk = disk
            return
        self.select_disk()

    def select_app(self):
        self.u.head("Select macOS Install App")
        print("")
        print("M. Menu")
        print("Q. Quit")
        print("")
        menu = self.u.grab("Please drag and drop the Install macOS app onto the terminal:  ")
        if menu.lower() == "m":
            return
        elif menu.lower() == "q":
            self.u.custom_quit()
        # Check if it exists
        p = self.u.check_path(menu)
        if not p:
            self.select_app()
            return
        checkpath = os.path.join(p, self.esd_loc, "InstallESD.dmg")
        if not os.path.exists(checkpath):
            self.u.head("InstallESD.dmg doesn't exist!")
            print("")
            print("InstallESD.dmg was not found at:")
            print(os.path.abspath(checkpath))
            print("")
            self.u.grab("Press [enter] to select another install app...")
            self.select_app()
        else:
            self.target_app = p

    def mount_dmg(self, dmg, no_browse = False):
        # Mounts the passed dmg and returns the mount point(s)
        args = ["/usr/bin/hdiutil", "attach", dmg, "-plist"]
        if no_browse:
            args.append("-nobrowse")
        out = self.r.run({"args":args})
        if out[2] != 0:
            # Failed!
            print(out[1])
            return []
        # Get the plist data returned, and locate the mount points
        try:
            plist_data = plist.loads(out[0])
            mounts = [x["mount-point"] for x in plist_data.get("system-entities", []) if "mount-point" in x]
            return mounts
        except:
            return []

    def unmount_dmg(self, mount_point):
        # Unmounts the passed dmg or mount point - retries with force if failed
        # Can take either a single point or a list
        if not type(mount_point) is list:
            mount_point = [mount_point]
        unmounted = []
        for m in mount_point:    
            args = ["/usr/bin/hdiutil", "detach", m]
            out = self.r.run({"args":args})
            if out[2] != 0:
                # Polite failed, let's crush this b!
                args.append("-force")
                out = self.r.run({"args":args})
                if out[2] != 0:
                    # Oh... failed again... onto the next...
                    print(out[1])
                    continue
            unmounted.append(m)
        return unmounted

    def check_operand(self, target_os, check_os, operand):
        # Checks the two OS versions - and sees if they fit the operand
        # target_os vs check_os
        #
        # Operands are:
        # lss, leq, equ, geq, gtr
        #  <    <=   ==   >=   >
        checks = []
        if "eq" in operand.lower():
            checks.append(None)
        if "g" in operand.lower():
            checks.append(False)
        elif "l" in operand.lower():
            checks.append(True)
        if self.u.compare_versions(target_os, check_os) in checks:
            return True
        return False

    def get_os_version(self, path):
        # loads the plist at path and extracts the version if found
        return None

    def create_with_current(self):
        # Checks which method we're using, then validates the InstallESD.dmg
        esd = os.path.join(self.target_app, self.esd_loc, "InstallESD.dmg")
        cim = os.path.join(self.target_app, "Contents/Resources/createinstallmedia")
        # Validate some requirements
        if not os.path.exists(esd):
            self.u.head("Error!")
            print("")
            print("InstallESD.dmg doesn't exist!\n")
            self.u.grab("Press [enter] to return...")
            return False
        if self.method.lower() == "createinstallmedia" and not os.path.exists(cim):
            # CIM doesn't exist :(
            self.u.head("Error!")
            print("")
            print("Couldn't find createinstallmedia!\n")
            self.u.grab("Press [enter] to return...")
            return False
        # Get the target os version
        mounts = self.mount_dmg(esd, True)
        b_system = s_loc = s_vers = None
        for mount in mounts:
            b_system = None
            s_vers   = None
            b_test = os.path.join(mount, "BaseSystem.dmg")
            if not os.path.exists(b_test):
                # Missing BaseSystem.dmg
                continue
            b_system = b_test
            b_mounts = self.mount_dmg(b_system, True)
            for m in b_mounts:
                s_test = os.path.join(m, "System/Library/CoreServices/SystemVersion.plist")
                if not os.path.exists(s_test):
                    continue
                # Found it - let's get the version from it
                try:
                    plist_data = plist.readPlist(s_test)
                    s_vers = plist_data["ProductVersion"]
                    break
                except:
                    s_vers = None
            # Unmount the attempted BaseSystem mounts
            self.unmount_dmg(b_mounts)
            if b_system and s_vers:
                # Gotem!
                self.target_os = s_vers
                break
        # Unmount the ESD dmg stuff
        self.unmount_dmg(mounts)
        if not b_system:
            self.u.head("Error!")
            print("")
            print("Couldn't locate BaseSystem.dmg!\n")
            self.u.grab("Press [enter] to return...")
            return False
        if not self.target_os:
            self.u.head("Error!")
            print("")
            print("Couldn't locate ProductVersion from SystemVersion.plist!\n")
            self.u.grab("Press [enter] to return...")
            return False
        # Ask the user if they'd like to format
        if self.format_prompt() and not self.do_format(self.target_disk['identifier']):
            self.u.head("Error!")
            print("")
            print("Hmmm - either formatting failed, or the disk number changed\nand I couldn't find it again...\n")
            self.u.grab("Press [enter] to return...")
            return False
        # Setup our targets and such
        if self.method.lower() == "createinstallmedia":
            return self.create_with_cim()
        else:
            return self.create_with_asr()
        return False

    def format_prompt(self):
        # Ask the user if they want to format the usb with the following:
        #
        # 1 HFS+ partition, GUID Partition Map
        while True:
            self.u.head("Format Target Drive?")
            print("")
            print("Would you like to format {} ({}) as such:".format(self.target_disk['name'], self.target_disk['identifier']))
            print("")
            print("1 HFS+ Partition, GUID Partition Map")
            print("")
            print("Doing so WILL erase ALL DATA on the target drive!")
            print("")
            menu = self.u.grab("Please choose y/n:  ").lower()
            if not len(menu):
                continue
            menu = menu[0]
            if menu == "y":
                return True
            elif menu == "n":
                return False

    def do_format(self, disk):
        # Resolve to our top-level identifier, then format, then get
        # the resulting disk
        self.u.head("Formatting {}".format(disk))
        print("")
        self.d.update()
        top_ident = self.d.get_top_identifier(disk)
        disk_name = self.d.get_volume_name(disk)
        # diskutil partitionDisk /dev/disk"$usbDisk" GPT JHFS+ "$usbName" 100%
        args = ["/usr/sbin/diskutil", "partitionDisk", "/dev/{}".format(top_ident), "GPT", "JHFS+", disk_name, "100%"]
        # Try to format
        out = self.r.run({"args":args, "stream":True})
        if out[2] != 0:
            print(out[1])
            return False
        self.target_disk = self.resolve_disk(top_ident, disk_name)
        if not self.target_disk:
            return False
        return True

    def resolve_disk(self, ident, name = None):
        # Attempts to resovle the self.target_disk dict to the passed
        # ident's top level and name
        top_ident = self.d.get_top_identifier(ident)
        self.d.update()
        # Get the new identifier after formatting
        disk_dict = self.d.get_disks_and_partitions_dict()
        for d in disk_dict[top_ident]["partitions"]:
            # Let's make sure to resolve with our current disk number and stuff
            if name and d['name'] == name:
                # Got it!
                return d
            elif d['identifier'] == ident:
                # Got it by ident!
                return d
        return None

    def rename_disk(self, disk, name):
        self.r.run({"args":["/usr/sbin/diskutil", "rename", disk, name], "stream":True})

    def create_with_cim(self, notify = False):
        # First, make sure we can run createinstallmedia on the
        # target dmg's os
        if self.u.compare_versions(self.target_os, self.min_cim) == True:
            # Version too low for CIM
            self.u.head("OS Version Too Low")
            print("")
            print("The target OS version ({}) is lower than the minimum".format(self.target_os))
            print("needed to use createinstallmedia ({}).".format(self.min_cim))
            print("")
            self.u.grab("Press [enter] to return...")
            return False
        # Save the current disk's name
        original_name = self.target_disk['name']
        self.u.head("Creating with CIM")
        print("")
        # Let's setup our args
        cim_args = [x for x in self.v_default.get("cimargs", [])]
        for v in self.versions:
            if self.check_operand(self.target_os, v.get("version", "0.0.0"), v.get("operand", "lss")):
                cim_args = [x for x in v.get("cimargs", self.v_default.get("cimargs", []))]
        # Replace text with what's needed
        cim_args_final = []
        # Check if the target disk is mounted
        disk_mount = self.d.get_mount_point(self.target_disk["identifier"])
        if not disk_mount:
            self.u.head("Error!")
            print("")
            print("{} ({}) isn't mounted!\n".format(self.target_disk['name'], self.target_disk['identifier']))
            self.u.grab("Press [enter] to return...")
            return False
        # Replace [[target_app]] and [[mount_point]] with their respective values
        for arg in cim_args:
            cim_args_final.append(arg.replace("[[target_app]]", self.target_app).replace("[[mount_point]]", disk_mount))
        # Print this out for the user so we can see what's up
        out = self.r.run({"args":cim_args_final, "stream":True})
        if out[2] != 0:
            self.u.head("Error!")
            print("")
            print("CreateInstallMedia failed!\n")
            self.u.grab("Press [enter] to return...")
            return False
        if self.rename:
            self.rename_disk(self.target_disk['identifier'], original_name)
        return True
    
    def create_with_asr(self, notify = False):
        original_name = self.target_disk['name']
        # Use Apple Software Restore to clone the disk
        self.u.head("Creating with ASR")
        print("")
        # Attach InstallESD.dmg and BaseSystem.dmg first
        esd = os.path.join(self.target_app, self.esd_loc, "InstallESD.dmg")
        if not os.path.exists(esd):
            self.u.head("Error!")
            print("")
            print("Couldn't locate InstallESD.dmg!\n")
            self.u.grab("Press [enter] to return...")
            return False
        # Get the target os version
        esd_mounts = self.mount_dmg(esd, True)
        b_system = b_mounts = esd_mount = None
        print("Resolving dmgs...\n")
        for mount in esd_mounts:
            b_test = os.path.join(mount, "BaseSystem.dmg")
            if not os.path.exists(b_test):
                # Missing BaseSystem.dmg
                continue
            # We got BaseSystem
            esd_mount = mount
            b_mounts = self.mount_dmg(b_test, True)
            if len(b_mounts):
                # There's at least one mount point
                b_system = b_mounts[0]
            break
        if not esd_mount or not b_system:
            # We are missing essential stuff! Unmount drives
            self.unmount_dmg(b_mounts)
            self.unmount_dmg(esd_mounts)
            self.u.head("Error!")
            print("")
            print("The installer was missing required files!\n")
            self.u.grab("Press [enter] to return...")
            return False
        # At this point, InstallESD and BaseSystem should be located and mounted
        print("Restoring OS X Base System to {}.\nThis will take awhile...\n".format(self.target_disk['name']))
        # asr -source "$insBaseSystemMount" -target "$usbMount" -erase -noprompt
        self.r.run({"args":[
            "/usr/sbin/asr", 
            "-source", 
            b_system, 
            "-target", 
            self.d.get_mount_point(self.target_disk['identifier']),
            "-erase",
            "-noprompt"
        ], "stream":True})
        # Resolve the disk - use the identifier to locate
        self.target_disk = self.resolve_disk(self.target_disk['identifier'])
        if not self.target_disk:
            # We lost our target drive! Unmount drives
            self.unmount_dmg(b_mounts)
            self.unmount_dmg(esd_mounts)
            self.u.head("Error!")
            print("")
            print("Well.. this is embarrassing.  I seem to have lost\nthe target drive...\n")
            self.u.grab("Press [enter] to return...")
            return False
        # Rename the disk back
        if self.rename:
            print("Renaming {} --> {}".format(self.target_disk['name'], original_name))
            self.rename_disk(self.target_disk['identifier'], original_name)
        # Resolve the disk after rename
        self.target_disk = self.resolve_disk(self.target_disk['identifier'])
        if not self.target_disk:
            # We lost our target drive! Unmount drives
            self.unmount_dmg(b_mounts)
            self.unmount_dmg(esd_mounts)
            self.u.head("Error!")
            print("")
            print("Well.. this is embarrassing.  I seem to have lost\nthe target drive...\n")
            self.u.grab("Press [enter] to return...")
            return False
        # Unmount BaseSystem
        self.unmount_dmg(b_mounts)
        # Remove packages, then copy over other stuffs
        print("Copying packages from OS X Base System.\nThis will take awhile...")
        td_mount = self.d.get_mount_point(self.target_disk['identifier'])
        out = self.r.run([
            {"args":["/bin/rm", "-Rf", os.path.join(td_mount, "System/Installation/Packages")], "stream":True},
            {"args":["/bin/cp", "-R", "-p", os.path.join(esd_mount, "Packages"), os.path.join(td_mount, "System/Installation/Packages")], "stream":True},
            {
                "args":["/bin/cp", "-R", "-p", os.path.join(esd_mount, "BaseSystem.chunklist"), os.path.join(td_mount, "BaseSystem.chunklist")],
                "stream":True,
                "message":"Copying BaseSystem.chunklist to {}".format(os.path.basename(td_mount))
            },
            {
                "args":["/bin/cp", "-R", "-p", os.path.join(esd_mount, "BaseSystem.dmg"), os.path.join(td_mount, "BaseSystem.dmg")],
                "stream":True,
                "message":"Copying BaseSystem.dmg to {}".format(os.path.basename(td_mount))
            }
        ], True)
        # Unmount InstallESD at this point
        self.unmount_dmg(esd_mounts)
        # Check for errors
        if type(out) is list:
            out = out[-1]
        if out[2] != 0:
            # Failed!
            self.u.head("Error!")
            print("")
            print(out[1])
            self.u.grab("Press [enter] to return...")
            return False
        return True

    def main(self):
        # if not self.u.check_admin():
        #     self.u.elevate(__file__)
        while True:
            self.u.head(self.name)
            print("")
            print("Creation Method: {}".format(self.method))
            print("Selected App:    {}".format(os.path.basename(self.target_app) if self.target_app else None))
            print("Selected Disk:   {}".format("{} ({})".format(self.target_disk['name'], self.target_disk['identifier']) if self.target_disk else None))
            print("")
            print("C. Create Install USB")
            print("")
            print("M. Pick Creation Method")
            print("A. Select Install macOS App")
            print("D. Select Disk")
            print("Q. Quit")
            print("")
            menu = self.u.grab("Please select an option:  ").lower()
            if menu == "q":
                self.u.custom_quit()
            elif menu == "m":
                self.select_method()
            elif menu == "d":
                self.select_disk()
            elif menu == "a":
                self.select_app()
            elif menu == "c":
                # Check method - and if it didn't take, bail
                if not self.method:
                    self.select_method()
                if not self.method:
                    continue
                # Check app - and if it didn't take, bail
                if not self.target_app:
                    self.select_app()
                if not self.target_app:
                    continue
                # Check disk - and if it didn't take, bail
                if not self.target_disk:
                    self.select_disk()
                if not self.target_disk:
                    continue
                if self.create_with_current():
                    # Create completed successfully - let's hang for a sec
                    print("Created successfully!\n")
                    self.u.grab("Press [enter] to return...")
    
# Start the thing
cim = CIM()
cim.main()