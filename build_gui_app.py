#!/usr/bin/env python3
"""
GUI Windows App Builder for Tello Drone Control System
Creates a standalone .exe file with full graphical interface
"""

import os
import sys
import subprocess
import shutil
from pathlib import Path

def build_gui_app():
    """Build the GUI Windows executable using PyInstaller."""
    
    print("🎨 Building GUI Windows App for Tello Drone Control System...")
    print("=" * 65)
    
    # Check if PyInstaller is available
    try:
        import PyInstaller
        print(f"✅ PyInstaller version: {PyInstaller.__version__}")
    except ImportError:
        print("❌ PyInstaller not found. Installing...")
        subprocess.run([sys.executable, "-m", "pip", "install", "pyinstaller"], check=True)
        print("✅ PyInstaller installed successfully")
    
    # Clean previous builds
    build_dirs = ["build", "dist", "gui_release", "__pycache__"]
    for dir_name in build_dirs:
        if os.path.exists(dir_name):
            print(f"🧹 Cleaning {dir_name}/")
            shutil.rmtree(dir_name)
    
    # Remove old spec files
    spec_files = ["drone_gui.spec", "TelloDroneGUI.spec"]
    for spec_file in spec_files:
        if os.path.exists(spec_file):
            os.remove(spec_file)
    
    # PyInstaller command for GUI executable
    pyinstaller_cmd = [
        "pyinstaller",
        "--onefile",                    # Single executable file
        "--name=TelloDroneGUI",         # App name
        "--windowed",                   # Hide console window (GUI only)
        "--noconfirm",                  # Overwrite output directory
        "--clean",                      # Clean cache
        "--distpath=gui_release",       # Output to gui_release/ folder
        "--workpath=build",             # Build files in build/ folder
        "--specpath=.",                 # Spec file in current directory
        
        # Include hidden imports (GUI-specific dependencies)
        "--hidden-import=tkinter",
        "--hidden-import=PIL",
        "--hidden-import=PIL.Image",
        "--hidden-import=PIL.ImageTk",
        "--hidden-import=cv2",
        "--hidden-import=numpy", 
        "--hidden-import=speech_recognition",
        "--hidden-import=pyaudio",
        "--hidden-import=djitellopy",
        "--hidden-import=threading",
        "--hidden-import=queue",
        
        # Add data files
        "--add-data=*.py:.",            # Include Python files
        
        # Main GUI script
        "drone_gui.py"
    ]
    
    print("🚀 Running PyInstaller for GUI version...")
    print(f"Command: {' '.join(pyinstaller_cmd)}")
    print()
    
    try:
        # Run PyInstaller
        result = subprocess.run(pyinstaller_cmd, check=True, capture_output=True, text=True)
        
        print("✅ GUI Build completed successfully!")
        print()
        
        # Show build results
        release_dir = Path("gui_release")
        if release_dir.exists():
            exe_files = list(release_dir.glob("*.exe"))
            if exe_files:
                exe_file = exe_files[0]
                file_size_mb = exe_file.stat().st_size / (1024 * 1024)
                
                print("📦 GUI BUILD RESULTS:")
                print(f"   Executable: {exe_file}")
                print(f"   Size: {file_size_mb:.1f} MB")
                print(f"   Location: {exe_file.absolute()}")
                print()
                
                # Instructions
                print("🎨 HOW TO USE GUI VERSION:")
                print("   1. Copy TelloDroneGUI.exe to any Windows computer")
                print("   2. Double-click to run - full graphical interface!")
                print("   3. Connect to drone WiFi first")
                print("   4. Click 'Connect' button in the GUI")
                print()
                
                print("🎮 GUI FEATURES:")
                print("   ✅ Full graphical interface with buttons and controls")
                print("   ✅ Live video display from drone camera")
                print("   ✅ Flight control buttons (takeoff, land, movement)")
                print("   ✅ Camera controls (photo, video, recording)")
                print("   ✅ Object detection and follow mode controls")
                print("   ✅ Real-time status display (battery, connection)")
                print("   ✅ Natural language command input field")
                print("   ✅ Activity log with real-time feedback")
                print("   ✅ Emergency stop and safety features")
                print("   ⚠️  Voice recognition requires internet connection")
                
            else:
                print("❌ No executable file found in gui_release directory")
        else:
            print("❌ GUI Release directory not created")
            
    except subprocess.CalledProcessError as e:
        print(f"❌ GUI Build failed with error code {e.returncode}")
        print("Error output:")
        print(e.stderr)
        return False
    
    return True

def create_gui_installer():
    """Create installation files for the GUI version."""
    
    gui_readme = """===============================================
   TELLO DRONE CONTROL SYSTEM - GUI VERSION
===============================================

🎨 GRAPHICAL USER INTERFACE VERSION
Point-and-click drone control with live video!

📦 WHAT'S INCLUDED:
- TelloDroneGUI.exe - Full graphical interface application
- No console window - pure GUI experience

✨ GUI FEATURES:
- 📹 Live video display from drone camera
- 🎮 Flight control buttons (takeoff, land, movement grid)
- 📸 Camera controls (photo, burst, video recording)
- 👁️ Object detection controls (face, person, vehicle)
- 🎯 Smart follow mode with visual feedback
- 📊 Real-time status displays (battery, connection, flying)
- 💬 Natural language command input
- 📝 Activity log with timestamps
- 🚨 Emergency stop and safety features

🎮 HOW TO USE:

1. SETUP YOUR DRONE:
   - Turn on your DJI Tello drone
   - Connect to drone's WiFi (starts with "TELLO-")

2. RUN THE GUI:
   - Double-click TelloDroneGUI.exe
   - Modern graphical interface opens automatically

3. CONNECT AND FLY:
   - Click "🔗 Connect" button
   - Click "🚀 Takeoff" when ready
   - Use directional arrow buttons to move
   - Click "🛬 Land" when finished

4. ADVANCED FEATURES:
   - Live Video: Click "📹 Start Video" for camera feed
   - Photos: Click "📷 Photo" or "📸 Burst"
   - Detection: Enable face/person/vehicle detection
   - Follow Mode: Click "🎯 Follow Target" 
   - Natural Language: Type commands like "fly forward 100cm"

🎯 GUI CONTROLS:

FLIGHT CONTROLS:
- Takeoff/Land buttons
- 3x3 movement grid (up/down/left/right/forward/back)
- Rotation controls (left/right)
- Emergency stop button

CAMERA CONTROLS:
- Live video toggle
- Photo capture
- Burst photos
- Video recording

DETECTION CONTROLS:
- Face detection toggle
- Person detection toggle  
- Vehicle detection toggle
- Follow target mode
- Detection photography

STATUS DISPLAYS:
- Connection status indicator
- Battery level with color coding
- Flight status (flying/landed)
- Detection mode status

⚠️  SYSTEM REQUIREMENTS:
- Windows 10 or later
- No additional software needed
- For voice: internet connection required
- For real drone: DJI Tello Standard or EDU

🎨 USER INTERFACE:
- Dark theme for easy viewing
- Color-coded buttons and status indicators
- Real-time activity log
- Responsive layout that works on different screen sizes

🐛 TROUBLESHOOTING:
- If GUI won't start: Run as administrator
- If drone won't connect: Check WiFi connection
- If buttons don't work: Ensure drone is connected
- If video is black: Click "Start Video" button

📁 DISTRIBUTION:
This is a portable GUI application. Copy to any Windows 
computer and double-click to run.

═══════════════════════════════════════════════════════════
GUI Version - Full graphical interface for drone control
Compatible with DJI Tello Standard and EDU drones
No command line experience needed!
═══════════════════════════════════════════════════════════"""

    with open("gui_release/GUI_README.txt", "w") as f:
        f.write(gui_readme)
    
    print("📄 Created GUI_README.txt with detailed instructions")

if __name__ == "__main__":
    # Build the GUI Windows app
    success = build_gui_app()
    
    if success:
        create_gui_installer()
        print("\n🎉 GUI Windows app build complete!")
        print("📁 Check the 'gui_release/' folder for your GUI executable")
        print("🎨 This version has a full graphical interface - no command line!")
    else:
        print("\n❌ GUI Build failed. Check the error messages above.")