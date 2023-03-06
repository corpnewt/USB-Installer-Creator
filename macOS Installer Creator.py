#!/usr/bin/env python
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
            "operand" : ">", 
            "methods" : ["createinstallmedia", "asr"], 
            "cimargs" : [
                "/usr/bin/sudo", 
                "[[target_app]]/Contents/Resources/createinstallmedia", 
                "--volume", 
                "[[mount_point]]",
                "--applicationpath",
                "[[target_app]]",
                "--nointeraction"
                ]
            }
        self.versions = [
            { 
                "version" : "10.14.0", 
                "operand" : ">=",
                "cimargs" : [
                    "/usr/bin/sudo",
                    "[[target_app]]/Contents/Resources/createinstallmedia",
                    "--volume",
                    "[[mount_point]]",
                    "--nointeraction"
                ],
                "dlassets" : True
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
        if not next((x for x in ("InstallESD.dmg","SharedSupport.dmg") if os.path.exists(os.path.join(p,self.esd_loc,x))),None):
            self.u.head("Missing Files!")
            print("")
            print("Could not find InstallESD.dmg or SharedSuport.dmg at:")
            print(os.path.abspath(checkpath))
            print("")
            self.u.grab("Press [enter] to select another install app...")
            self.select_app()
        else:
            self.target_app = p

    def mount_dmg(self, dmg, no_browse = False):
        # Mounts the passed dmg and returns the mount point(s)
        args = ["/usr/bin/hdiutil", "attach", dmg, "-plist", "-noverify"]
        if no_browse:
            args.append("-nobrowse")
        out = self.r.run({"args":args})
        if out[2] != 0:
            # Failed!
            raise Exception("Mount Failed!", "{} failed to mount:\n\n{}".format(os.path.basename(dmg), out[1]))
        # Get the plist data returned, and locate the mount points
        try:
            plist_data = plist.loads(out[0])
            mounts = [x["mount-point"] for x in plist_data.get("system-entities", []) if "mount-point" in x]
            return mounts
        except:
            raise Exception("Mount Failed!", "No mount points returned from {}".format(os.path.basename(dmg)))

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

    def sum_lists(self, *args):
        # Returns a list that is the sum of all the passed lists
        return [y for x in args for y in x if type(x) is list]

    def check_operand(self, target_os, check_os, operand):
        # Checks the two OS versions - and sees if they fit the operand
        # target_os vs check_os
        #
        # Operands are:
        # lss, leq, equ, geq, gtr
        #  <    <=   ==   >=   >
        checks = []
        if "=" in operand.lower():
            checks.append(None)
        if ">" in operand.lower():
            checks.append(False)
        elif "<" in operand.lower():
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
        # Set a temp path to the same loc as InstallESD - just in case we're 10.14 or newer
        bsy = os.path.join(self.target_app, self.esd_loc, "BaseSystem.dmg")
        # And another temp path for SharedSupport.dmg
        ssp = os.path.join(self.target_app, self.esd_loc, "SharedSupport.dmg")
        cim = os.path.join(self.target_app, "Contents/Resources/createinstallmedia")
        # Validate some requirements
        if not os.path.exists(esd) and not os.path.exists(ssp):
            raise Exception("Missing Files!", "Could not find InstallESD.dmg or SharedSupport.dmg!")
        if self.method.lower() == "asr" and not os.path.exists(esd):
            raise Exception("Missing Files!", "Could not find InstallESD.dmg!")
        if self.method.lower() == "createinstallmedia" and not os.path.exists(cim):
            # CIM doesn't exist :(
            raise Exception("Missing Files!", "Couldn't find createinstallmedia!")
        # Set the target os version
        self.target_os = self.get_target_version()
        # Ask the user if they'd like to format
        if self.format_prompt() and not self.do_format(self.target_disk['identifier']):
            raise Exception("Formatting Issue!", "Hmmm - either formatting failed, or the disk number changed\nand I couldn't find it again...")
        # Setup our targets and such
        if self.method.lower() == "createinstallmedia":
            self.create_with_cim()
        else:
            if self.check_operand(self.target_os, "10.9", "<"):
                self.asr_lion()
            elif self.check_operand(self.target_os, "10.13", "<"):
                self.asr_sierra()
            else:
                self.asr_high_sierra()

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

    def dl_assets_prompt(self):
        # Ask the user if they want to download assets before creating the USB
        while True:
            self.u.head("Download Assets?")
            print("")
            print("Would you like to download additional installer assets?".format(self.target_disk['name'], self.target_disk['identifier']))
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

    def get_target_version(self):
        # Set temp InstallESD.dmg and BaseSystem.dmg paths to test
        esd = os.path.join(self.target_app, self.esd_loc, "InstallESD.dmg")
        bsy = os.path.join(self.target_app, self.esd_loc, "BaseSystem.dmg")
        ssp = os.path.join(self.target_app, self.esd_loc, "SharedSupport.dmg")
        # Set temp version stuff
        vers = s_plist = None
        b_mounts = e_mounts = []
        if os.path.exists(ssp):
            # We got SharedSupport - mount it and load the .xml
            b_mounts = self.mount_dmg(ssp, True)
            for d in os.listdir(b_mounts[0]):
                full_path = os.path.join(b_mounts[0],d)
                if not os.path.isdir(full_path) or not d.lower().startswith("com_apple_mobileasset_"):
                    continue
                # Got our folder - check for our .xml file
                for f in os.listdir(full_path):
                    if f.lower().startswith("com_apple_mobileasset_") and f.lower().endswith(".xml"):
                        s_plist = os.path.join(full_path,f)
                        break
                break
        if os.path.exists(bsy):
            # We got BaseSystem.dmg - mount it and save the path
            b_mounts = self.mount_dmg(bsy, True)
            s_plist = os.path.join(b_mounts[0], "System/Library/CoreServices/SystemVersion.plist")
        elif os.path.exists(esd):
            # No BaseSystem.dmg - let's check InstallESD.dmg
            e_mounts = self.mount_dmg(esd, True)
            # Check first for SystemVersion.plist
            s_plist = os.path.join(e_mounts[0], "System/Library/CoreServices/SystemVersion.plist")
            if not os.path.exists(s_plist):
                # No dice - check for BaseSystem.dmg
                b_path = os.path.join(e_mounts[0], "BaseSystem.dmg")
                if not os.path.exists(b_path):
                    raise Exception("Missing Files!", "Couldn't find SystemVersion.plist!", e_mounts)
                b_mounts = self.mount_dmg(b_path, True)
                s_plist = os.path.join(b_mounts[0], "System/Library/CoreServices/SystemVersion.plist")
                if not os.path.exists(s_plist):
                    raise Exception("Missing Files!", "Couldn't find SystemVersion.plist!", self.sum_lists(b_mounts, e_mounts))
        if not s_plist or not os.path.exists(s_plist):
            raise Exception("Version Error!", "Unable to locate SystemVersion.plist", self.sum_lists(b_mounts, e_mounts))
        # Found it - let's get the version from it
        try:
            plist_data = plist.readPlist(s_plist)
            s_vers = plist_data.get("ProductVersion",plist_data.get("Assets",[{}])[0].get("OSVersion",None))
            # Unmount the disks first
            self.unmount_dmg(self.sum_lists(b_mounts, e_mounts))
            if not s_vers: raise Exception("Plist Parse Error!","Could not locate installer OS version!")
            return s_vers
        except Exception as e:
            raise Exception("Plist Parse Error!", "Failed to parse system version:\n\n{}".format(str(e)), self.sum_lists(b_mounts, e_mounts))

    def create_with_cim(self, notify = False):
        # First, make sure we can run createinstallmedia on the
        # target dmg's os
        if self.u.compare_versions(self.target_os, self.min_cim) == True:
            # Version too low for CIM
            raise Exception("OS Version Too Low!", "The target OS version ({}) is lower than the minimum\nneeded to use createinstallmedia ({})".format(self.target_os, self.min_cim))
        # Save the current disk's name
        original_name = self.target_disk['name']
        # Let's setup our args - also check if we're downloading assets
        cim_args = [x for x in self.v_default.get("cimargs", [])]
        # Initialize our asset downloading capabilities
        dl_assets = False
        for v in self.versions:
            if self.check_operand(self.target_os, v.get("version", "0.0.0"), v.get("operand", "lss")):
                cim_args = [x for x in v.get("cimargs", self.v_default.get("cimargs", []))]
                dl_assets = v.get("dlassets",False)
        # Check if we can download assets - and prompt the user as needed
        if dl_assets and self.dl_assets_prompt():
            # We want to dl extra assets - we *do* need to redo our header though
            # as this overrides it
            cim_args.append("--downloadassets")
        # Replace text with what's needed
        cim_args_final = []
        # Check if the target disk is mounted
        disk_mount = self.d.get_mount_point(self.target_disk["identifier"])
        if not disk_mount:
            raise Exception("Error!", "{} ({}) isn't mounted!\n".format(self.target_disk['name'], self.target_disk['identifier']))
        # Replace [[target_app]] and [[mount_point]] with their respective values
        for arg in cim_args:
            cim_args_final.append(arg.replace("[[target_app]]", self.target_app).replace("[[mount_point]]", disk_mount))
        # Print this out for the user so we can see what's up
        self.u.head("Creating with CIM")
        print("")
        print("This will take some time - sit back and relax for a bit.\n\n")
        out = self.r.run({"args":cim_args_final, "stream":True})
        if out[2] != 0:
            raise Exception("Create Failed!", "CreateInstallMedia failed! :(\n\n{}".format(out[1]))
        if self.rename:
            self.rename_disk(self.target_disk['identifier'], original_name)
        return True

    def asr_lion(self, notify = False):
        # Save the original name in case we need to rename back
        original_name = self.target_disk['name']
        install_esd = os.path.join(self.target_app, self.esd_loc, "InstallESD.dmg")
        # Use Apple Software Restore to clone the disk
        self.u.head("Creating with ASR - 10.7 -> 10.8 Method")
        print("")
        # Actually restore the dmg
        print("Restoring InstallESD to {}.\nThis will take awhile...".format(self.target_disk['name']))
        out = self.r.run({"args":[
            "/usr/bin/sudo",
            "/usr/sbin/asr", 
            "-source", 
            install_esd, 
            "-target", 
            self.d.get_mount_point(self.target_disk['identifier']),
            "-erase",
            "-noprompt",
            "-noverify"
        ], "stream":True})
        if out[2] != 0:
            # Failed!
            raise Exception("Create Failed!", "ASR Failed! :(\n\n{}".format(out[1]))
        # Rename the disk back
        if self.rename:
            self.target_disk = self.resolve_disk(self.target_disk['identifier'])
            if self.target_disk:
                print("Renaming {} --> {}".format(self.target_disk['name'], original_name))
                self.rename_disk(self.target_disk['identifier'], original_name)
                self.target_disk = self.resolve_disk(self.target_disk['identifier'])

    def asr_sierra(self, notify = False):
        # Save the original name in case we need to rename back
        original_name = self.target_disk['name']
        install_esd = os.path.join(self.target_app, self.esd_loc, "InstallESD.dmg")
        # Use Apple Software Restore to clone the disk
        self.u.head("Creating with ASR - 10.9 -> 10.12 Method")
        print("")
        print("Mounting InstallESD.dmg...")
        esd_mounts = self.mount_dmg(install_esd, True)
        esd_mount = esd_mounts[0]
        b_loc = os.path.join(esd_mount, "BaseSystem.dmg")
        b_chunk = os.path.join(esd_mount, "BaseSystem.chunklist")
        print("Restoring BaseSystem.dmg to {}.\n\tThis will take awhile...".format(self.target_disk['name']))
        # asr -source "$insBaseSystemMount" -target "$usbMount" -erase -noprompt
        out = self.r.run({"args":[
            "/usr/bin/sudo",
            "/usr/sbin/asr", 
            "-source", 
            b_loc, 
            "-target", 
            self.d.get_mount_point(self.target_disk['identifier']),
            "-erase",
            "-noprompt",
            "-noverify"
        ], "stream":True})
        if out[2] != 0:
            raise Exception("Create Failed!", "ASR failed! :(\n\n{}".format(out[1]))
        if self.rename:
            self.target_disk = self.resolve_disk(self.target_disk['identifier'])
            if self.target_disk:
                print("Renaming {} --> {}".format(self.target_disk['name'], original_name))
                self.rename_disk(self.target_disk['identifier'], original_name)
                self.target_disk = self.resolve_disk(self.target_disk['identifier'])
        # Remove packages, then copy over other stuffs
        print("Copying packages from OS X Base System.\nThis will take awhile...")
        td_mount = self.d.get_mount_point(self.target_disk['identifier'])
        out = self.r.run([
            {
                "args":["/usr/bin/sudo", "/bin/rm", "-Rf", 
                os.path.join(td_mount, "System/Installation/Packages")], 
                "stream":True,
                "message":"Removing broken Packages alias..."
            },
            {
                "args":["/usr/bin/sudo", "/bin/cp", "-R", "-p", 
                os.path.join(esd_mount, "Packages"), 
                os.path.join(td_mount, "System/Installation/Packages")], 
                "stream":True,
                "message":"Copying installation packages\n\tThis will take awhile..."
            },
            {
                "args":["/usr/bin/sudo", "/bin/cp", "-R", "-p", b_chunk, os.path.join(td_mount, "BaseSystem.chunklist")],
                "stream":True,
                "message":"Copying BaseSystem.chunklist to {}...".format(os.path.basename(td_mount))
            },
            {
                "args":["/usr/bin/sudo", "/bin/cp", "-R", "-p", b_loc, os.path.join(td_mount, "BaseSystem.dmg")],
                "stream":True,
                "message":"Copying BaseSystem.dmg to {}...\n\tThis will take awhile...".format(os.path.basename(td_mount))
            }
        ], True)
        # Check for errors
        if type(out) is list:
            out = out[-1]
        if out[2] != 0:
            # Failed!
            raise Exception("Create Failed!", "ASR failed! :(\n\n{}".format(out[1]))

    def asr_high_sierra(self, notify = False):
        # Save the original name in case we need to rename back
        original_name = self.target_disk['name']
        base_system = os.path.join(self.target_app, self.esd_loc, "BaseSystem.dmg")
        # Use Apple Software Restore to clone the disk
        self.u.head("Creating with ASR - 10.13+ Method")
        print("")
        print("Restoring BaseSystem.dmg to {}.\n\tThis will take awhile...".format(self.target_disk['name']))
        # asr -source "$insBaseSystemMount" -target "$usbMount" -erase -noprompt
        out = self.r.run({"args":[
            "/usr/bin/sudo",
            "/usr/sbin/asr", 
            "-source", 
            base_system, 
            "-target", 
            self.d.get_mount_point(self.target_disk['identifier']),
            "-erase",
            "-noprompt",
            "-noverify"
        ], "stream":True})
        if out[2] != 0:
            # Failed!
            raise Exception("Create Failed!", "ASR failed! :(\n\n{}".format(out[1]))
        if self.rename:
            self.target_disk = self.resolve_disk(self.target_disk['identifier'])
            if self.target_disk:
                print("Renaming {} --> {}".format(self.target_disk['name'], original_name))
                self.rename_disk(self.target_disk['identifier'], original_name)
                self.target_disk = self.resolve_disk(self.target_disk['identifier'])
        # Copy the Install macOS [whatever].app to the USB as well
        check_path = os.path.join(self.d.get_mount_point(self.target_disk['identifier']), os.path.basename(self.target_app))
        if os.path.exists(check_path):
            print("Removing old {}...".format(os.path.basename(self.target_app)))
            out = self.r.run({"args":["/usr/bin/sudo", "/bin/rm", "-Rf", check_path], "stream":True})
            if out[2] != 0:
                # Failed!
                raise Exception("Create Failed!", out[1])
        print("Copying {} to {}.\n\tThis will take awhile...".format(os.path.basename(self.target_app), self.target_disk['name']))
        out = self.r.run({"args":[
            "/usr/bin/sudo",
            "/bin/cp", 
            "-R",
            self.target_app,
            self.d.get_mount_point(self.target_disk['identifier'])
        ], "stream":True})
        if out[2] != 0:
            # Failed!
            raise Exception("Create Failed!", "ASR failed! :(\n\n{}".format(out[1]))

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
                try:
                    self.create_with_current()
                except Exception as e:
                    # Expects the error args as follows:
                    # Error Title
                    # Error Text
                    # A list of mount points to unmount if needed
                    title   = "Error!"
                    message = "Something went wrong :(\n\n{}".format(str(e))
                    mounts  = []
                    try:
                        title   = e.args[0]
                        message = e.args[1]
                        mounts  = e.args[2]
                    except:
                        # We likely missed some stuff - carry on though
                        pass
                    self.u.head(title)
                    print("")
                    print(message)
                    print("")
                else:
                    # Create completed successfully - let's hang for a sec
                    print("\nCreated successfully!\n")
                self.u.grab("Press [enter] to return...")
                continue
# Start the thing
cim = CIM()
cim.main()
