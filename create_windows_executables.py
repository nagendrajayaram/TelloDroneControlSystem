#!/usr/bin/env python3
"""
Complete Windows Executable Builder
Creates both console and GUI versions for Windows distribution
"""

import os
import sys
import subprocess
import shutil
from pathlib import Path

def build_executables():
    """Build both console and GUI executables."""
    
    print("🎯 Building Complete Windows Package...")
    print("=" * 50)
    
    # Clean and prepare
    build_dirs = ["build", "dist", "windows_package", "__pycache__"]
    for dir_name in build_dirs:
        if os.path.exists(dir_name):
            shutil.rmtree(dir_name)
    
    os.makedirs("windows_package", exist_ok=True)
    
    # Build 1: Console CLI Version
    print("\n🔧 Building Console CLI Version...")
    console_cmd = [
        "pyinstaller", "--onefile", "--console",
        "--name=TelloDroneControl",
        "--distpath=windows_package",
        "--clean", "--noconfirm",
        "drone_cli.py"
    ]
    
    try:
        subprocess.run(console_cmd, check=True, capture_output=True)
        print("✅ Console version built successfully")
    except subprocess.CalledProcessError:
        print("❌ Console version build failed")
        return False
    
    # Build 2: GUI Version (with console for debugging)
    print("\n🎨 Building GUI Version...")
    gui_cmd = [
        "pyinstaller", "--onefile", "--console",
        "--name=TelloDroneGUI",
        "--distpath=windows_package", 
        "--clean", "--noconfirm",
        "--hidden-import=tkinter",
        "--hidden-import=PIL.Image",
        "--hidden-import=PIL.ImageTk",
        "drone_gui.py"
    ]
    
    try:
        subprocess.run(gui_cmd, check=True, capture_output=True)
        print("✅ GUI version built successfully")
    except subprocess.CalledProcessError:
        print("❌ GUI version build failed")
        return False
    
    return True

def create_package_documentation():
    """Create comprehensive documentation for the Windows package."""
    
    package_readme = """===============================================
   TELLO DRONE CONTROL SYSTEM - WINDOWS PACKAGE
===============================================

🎁 COMPLETE WINDOWS PACKAGE
Two versions: Command Line + Graphical Interface

📦 WHAT'S INCLUDED:
- TelloDroneControl.exe - Command line version (161 MB)
- TelloDroneGUI.exe - Graphical interface version (135 MB)
- Complete documentation and examples

🎮 CHOOSE YOUR VERSION:

COMMAND LINE VERSION (TelloDroneControl.exe):
✅ Type commands like "takeoff", "land", "move forward 100"
✅ Natural language: "say fly in a circle"
✅ Voice commands (with internet)
✅ Perfect for experienced users and automation
✅ All advanced features available

GUI VERSION (TelloDroneGUI.exe):
✅ Point-and-click interface with buttons
✅ Live video display from drone camera
✅ Visual status indicators and controls
✅ Perfect for beginners and visual users
✅ All features accessible through buttons

🚀 QUICK START:

1. SETUP DRONE:
   - Turn on DJI Tello drone
   - Connect computer to drone WiFi (TELLO-XXXXXX)

2. CHOOSE VERSION:
   - For typing commands: Double-click TelloDroneControl.exe
   - For button interface: Double-click TelloDroneGUI.exe

3. CONNECT AND FLY:
   - Type "connect" (CLI) or click "Connect" (GUI)
   - Type "takeoff" (CLI) or click "Takeoff" (GUI)
   - Start flying!

⚠️  SYSTEM REQUIREMENTS:
- Windows 10 or later (64-bit recommended)
- No additional software installation needed
- For voice: internet connection required
- For real drone: DJI Tello Standard or EDU

🎯 FEATURE COMPARISON:

FLIGHT CONTROLS:
- CLI: Type "takeoff", "land", "move up 50", "rotate left 90"
- GUI: Click takeoff/land buttons, use movement grid

CAMERA:
- CLI: Type "photo", "video_on", "record"
- GUI: Click photo/video buttons, see live video display

OBJECT DETECTION:
- CLI: Type "detect_on face", "follow face"
- GUI: Click detection toggles, visual overlays on video

NATURAL LANGUAGE:
- CLI: Type "say fly forward 100cm"
- GUI: Enter in command input field

VOICE CONTROL:
- CLI: Type "voice_on" to enable hands-free control
- GUI: Not implemented (use CLI version for voice)

STATUS MONITORING:
- CLI: Type "status" to see drone information
- GUI: Always visible status panel

🔧 TROUBLESHOOTING:

STARTUP ISSUES:
- If exe won't start: Run as administrator
- If antivirus blocks: Add to exclusions (false positive)
- If missing DLL errors: Ignore - applications will still work

CONNECTION ISSUES:
- Ensure drone is powered on and WiFi is connected
- Windows firewall may block - allow when prompted
- Try "connect" command multiple times if needed

PERFORMANCE:
- First startup may be slower (Windows security scan)
- Subsequent launches will be faster
- Close other applications for best video performance

📁 DISTRIBUTION:
Both executables are portable - copy to any Windows computer
and run directly. No installation or setup required.

🎮 ADVANCED USAGE:

AUTOMATION (CLI):
- Create .bat files with command sequences
- Use for automated missions and routines
- Perfect for repetitive tasks

VISUAL OPERATION (GUI):
- Real-time video feedback
- Point-and-click simplicity
- Status monitoring at a glance
- Perfect for demonstrations

HYBRID APPROACH:
- Use GUI for visual flight control
- Switch to CLI for advanced automation
- Both can be run simultaneously

═══════════════════════════════════════════════════════════
Complete Windows Package - CLI + GUI versions included
Compatible with DJI Tello Standard and EDU drones
No installation required - just download and fly!
═══════════════════════════════════════════════════════════"""

    with open("windows_package/WINDOWS_PACKAGE_README.txt", "w") as f:
        f.write(package_readme)
    
    # Create quick start guide
    quick_start = """QUICK START GUIDE - TELLO DRONE CONTROL
======================================

🚀 FASTEST WAY TO FLY:

1. Turn on Tello drone
2. Connect to drone WiFi (TELLO-XXXXXX)
3. Double-click TelloDroneControl.exe OR TelloDroneGUI.exe
4. Type "connect" (CLI) or click "Connect" (GUI)
5. Type "takeoff" (CLI) or click "Takeoff" (GUI)
6. You're flying!

⚠️  IMPORTANT:
- Always connect to drone WiFi BEFORE running the program
- Type "help" (CLI) for all commands
- Click buttons (GUI) for all functions
- Type "land" or click "Land" when finished

🎯 FIRST FLIGHT COMMANDS:
takeoff -> move up 50 -> rotate left 90 -> land

Have fun flying! 🚁"""

    with open("windows_package/QUICK_START.txt", "w") as f:
        f.write(quick_start)
    
    print("📄 Documentation created")

if __name__ == "__main__":
    success = build_executables()
    
    if success:
        create_package_documentation()
        
        # Show results
        package_dir = Path("windows_package")
        if package_dir.exists():
            files = list(package_dir.glob("*"))
            total_size = sum(f.stat().st_size for f in files if f.is_file()) / (1024*1024)
            
            print(f"\n🎉 Windows Package Complete!")
            print(f"📁 Location: windows_package/")
            print(f"📦 Total size: {total_size:.0f} MB")
            print(f"📄 Files included:")
            for file in sorted(files):
                if file.is_file():
                    size_mb = file.stat().st_size / (1024*1024)
                    print(f"   - {file.name} ({size_mb:.0f} MB)")
            
            print(f"\n✅ Ready for distribution!")
            print(f"📋 Copy entire 'windows_package' folder to any Windows computer")
    else:
        print("\n❌ Build failed")