#!/usr/bin/env python3
"""
Windows App Builder for Tello Drone Control System
Creates a standalone .exe file that runs without Python installation
"""

import os
import sys
import subprocess
import shutil
from pathlib import Path

def build_windows_app():
    """Build the Windows executable using PyInstaller."""
    
    print("🔨 Building Windows App for Tello Drone Control System...")
    print("=" * 60)
    
    # Check if PyInstaller is available
    try:
        import PyInstaller
        print(f"✅ PyInstaller version: {PyInstaller.__version__}")
    except ImportError:
        print("❌ PyInstaller not found. Installing...")
        subprocess.run([sys.executable, "-m", "pip", "install", "pyinstaller"], check=True)
        print("✅ PyInstaller installed successfully")
    
    # Clean previous builds
    build_dirs = ["build", "dist", "__pycache__"]
    for dir_name in build_dirs:
        if os.path.exists(dir_name):
            print(f"🧹 Cleaning {dir_name}/")
            shutil.rmtree(dir_name)
    
    # Remove old spec files
    spec_files = ["drone_cli.spec", "TelloDroneControl.spec"]
    for spec_file in spec_files:
        if os.path.exists(spec_file):
            os.remove(spec_file)
    
    # PyInstaller command for standalone executable
    pyinstaller_cmd = [
        "pyinstaller",
        "--onefile",                    # Single executable file
        "--name=TelloDroneControl",     # App name
        "--console",                    # Keep console window (for commands)
        "--noconfirm",                  # Overwrite output directory
        "--clean",                      # Clean cache
        "--distpath=release",           # Output to release/ folder
        "--workpath=build",             # Build files in build/ folder
        "--specpath=.",                 # Spec file in current directory
        
        # Include hidden imports (dependencies that might not be detected)
        "--hidden-import=cv2",
        "--hidden-import=numpy", 
        "--hidden-import=speech_recognition",
        "--hidden-import=pyaudio",
        "--hidden-import=djitellopy",
        
        # Add data files if they exist
        "--add-data=*.py:.",            # Include all Python files
        
        # Main script
        "drone_cli.py"
    ]
    
    print("🚀 Running PyInstaller...")
    print(f"Command: {' '.join(pyinstaller_cmd)}")
    print()
    
    try:
        # Run PyInstaller
        result = subprocess.run(pyinstaller_cmd, check=True, capture_output=True, text=True)
        
        print("✅ Build completed successfully!")
        print()
        
        # Show build results
        release_dir = Path("release")
        if release_dir.exists():
            exe_files = list(release_dir.glob("*.exe"))
            if exe_files:
                exe_file = exe_files[0]
                file_size_mb = exe_file.stat().st_size / (1024 * 1024)
                
                print("📦 BUILD RESULTS:")
                print(f"   Executable: {exe_file}")
                print(f"   Size: {file_size_mb:.1f} MB")
                print(f"   Location: {exe_file.absolute()}")
                print()
                
                # Instructions
                print("🎮 HOW TO USE:")
                print("   1. Copy TelloDroneControl.exe to any Windows computer")
                print("   2. Double-click to run (no Python installation needed)")
                print("   3. All drone features work offline except voice recognition")
                print()
                
                print("📋 FEATURES INCLUDED:")
                print("   ✅ Complete drone control (takeoff, land, move, rotate)")
                print("   ✅ Object detection (face, person, vehicle)")
                print("   ✅ Smart flight modes (follow, detection photography)")
                print("   ✅ Natural language commands ('say fly forward 100cm')")
                print("   ✅ Camera features (photo, video, recording)")
                print("   ✅ Simulation mode for testing")
                print("   ⚠️  Voice recognition requires internet connection")
                
            else:
                print("❌ No executable file found in release directory")
        else:
            print("❌ Release directory not created")
            
    except subprocess.CalledProcessError as e:
        print(f"❌ Build failed with error code {e.returncode}")
        print("Error output:")
        print(e.stderr)
        return False
    
    return True

def create_installer_script():
    """Create a simple batch file to distribute with the exe."""
    
    installer_content = """@echo off
echo.
echo ===============================================
echo   Tello Drone Control System - Windows App
echo ===============================================
echo.
echo This is a standalone drone control application.
echo No Python installation required!
echo.
echo FEATURES:
echo - Complete drone flight control
echo - Object detection and smart following
echo - Natural language commands
echo - Camera and video recording
echo - Works completely offline (except voice)
echo.
echo USAGE:
echo 1. Connect to your Tello drone's WiFi
echo 2. Run TelloDroneControl.exe
echo 3. Type 'help' for available commands
echo 4. Try 'connect' to start flying!
echo.
echo For voice commands, ensure internet connection.
echo.
pause
TelloDroneControl.exe
"""
    
    with open("release/START_DRONE_CONTROL.bat", "w") as f:
        f.write(installer_content)
    
    print("📄 Created START_DRONE_CONTROL.bat launcher")

if __name__ == "__main__":
    # Build the Windows app
    success = build_windows_app()
    
    if success:
        create_installer_script()
        print("\n🎉 Windows app build complete!")
        print("📁 Check the 'release/' folder for your executable")
    else:
        print("\n❌ Build failed. Check the error messages above.")