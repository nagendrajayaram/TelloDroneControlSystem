#!/usr/bin/env python3
"""
Tello Drone Command Line Interface

A user-friendly CLI for controlling DJI Tello drones using the TelloDroneAgent.
Provides interactive commands for all drone operations.
"""

import sys
import time
import cv2
import speech_recognition as sr
import threading
import queue
from tello_drone_agent import TelloDroneAgent


class DroneCLI:
    """Command Line Interface for Tello Drone Control."""
    
    def __init__(self, simulation_mode: bool = False):
        self.simulation_mode = simulation_mode
        self.agent = TelloDroneAgent(simulation_mode=simulation_mode)
        self.running = True
        
        # Voice recognition setup
        self.voice_enabled = False
        self.voice_thread = None
        self.voice_running = False
        self.recognizer = sr.Recognizer()
        self.microphone = None
        self.voice_command_queue = queue.Queue()  # Thread-safe command queue
        self.command_lock = threading.Lock()  # Serialize all drone commands
        
        # Keyboard input handling for non-blocking
        self.keyboard_input_queue = queue.Queue()
        self.keyboard_thread = None
        self.keyboard_running = False
        
        self._setup_voice_recognition()
        
        # Command mapping
        self.commands = {
            # Basic commands
            'connect': self.cmd_connect,
            'disconnect': self.cmd_disconnect,
            'status': self.cmd_status,
            'takeoff': self.cmd_takeoff,
            'land': self.cmd_land,
            'move': self.cmd_move,
            'rotate': self.cmd_rotate,
            'speed': self.cmd_speed,
            'hover': self.cmd_hover,
            
            # Advanced flight
            'flip': self.cmd_flip,
            'goto': self.cmd_goto,
            'circle': self.cmd_circle,
            'grid': self.cmd_grid,
            
            # Camera & Video
            'video_on': self.cmd_video_on,
            'video_off': self.cmd_video_off,
            'photo': self.cmd_photo,
            'burst': self.cmd_burst,
            'record_start': self.cmd_record_start,
            'record_stop': self.cmd_record_stop,
            
            # Object Detection
            'detect_on': self.cmd_detection_on,
            'detect_off': self.cmd_detection_off,
            'detect_status': self.cmd_detection_status,
            'follow': self.cmd_follow,
            'follow_stop': self.cmd_follow_stop,
            'detect_photo': self.cmd_detection_photo,
            
            # Missions
            'mission': self.cmd_mission,
            'say': self.cmd_natural_language,
            'tell': self.cmd_natural_language,
            'instruct': self.cmd_natural_language,
            
            # Voice Commands
            'voice_on': self.cmd_voice_on,
            'voice_off': self.cmd_voice_off,
            'voice_status': self.cmd_voice_status,
            
            # System
            'emergency': self.cmd_emergency,
            'log': self.cmd_log,
            'sim': self.cmd_toggle_simulation,
            'simulation': self.cmd_toggle_simulation,
            'mode': self.cmd_show_mode,
            'help': self.cmd_help,
            'commands': self.cmd_help,
            'quit': self.cmd_quit,
            'exit': self.cmd_quit
        }
    
    def run(self):
        """Start the CLI interface."""
        mode_text = "🎮 SIMULATION MODE" if self.simulation_mode else "🚁 REAL DRONE MODE"
        print(f"🚁 Tello Drone Control Interface - {mode_text}")
        print("=" * 60)
        print("Welcome to the Tello Drone Control System!")
        if self.simulation_mode:
            print("🎮 Running in SIMULATION mode - safe for testing!")
            print("   Use 'sim' to toggle to real drone mode")
        else:
            print("⚠️  Running in REAL DRONE mode - connects to actual hardware")
            print("   Use 'sim' to toggle to simulation mode for safe testing")
        print("Type 'help' for available commands or 'quit' to exit.")
        print("💬 Try natural language: 'say fly in a circle' or 'tell take 3 photos'")
        print("Remember to connect to your drone first!")
        print()
        
        # Show initial prompt
        print("drone> ", end='', flush=True)
        
        while self.running:
            try:
                # Process any queued voice commands continuously
                self._process_voice_command_queue()
                
                # Check for keyboard input without blocking (non-blocking I/O)
                user_input = self._get_keyboard_input_non_blocking()
                if user_input is not None:
                    if user_input.strip():
                        # Execute user command with thread safety
                        self._execute_command_line_direct(user_input.strip())
                    print("drone> ", end='', flush=True)
                
                # Small sleep to prevent busy waiting
                time.sleep(0.1)  # 100ms - allows responsive voice processing
                    
            except KeyboardInterrupt:
                print("\nShutting down...")
                self.cmd_quit([])
            except Exception as e:
                print(f"Error: {e}")
    
    def _get_keyboard_input_non_blocking(self):
        """Get keyboard input without blocking."""
        import select
        import sys
        
        try:
            # Check if input is available (Unix/Linux)
            ready, _, _ = select.select([sys.stdin], [], [], 0)
            if ready:
                return sys.stdin.readline()
            return None
        except (OSError, AttributeError):
            # Fallback for Windows or unsupported environments
            # Use threading approach for keyboard input
            return self._get_keyboard_input_threaded()
    
    def _get_keyboard_input_threaded(self):
        """Fallback keyboard input using threading (for Windows)."""
        # Start keyboard thread if not running
        if not self.keyboard_running:
            self.keyboard_running = True
            self.keyboard_thread = threading.Thread(target=self._keyboard_input_loop, daemon=True)
            self.keyboard_thread.start()
        
        # Check for input from keyboard thread
        try:
            return self.keyboard_input_queue.get_nowait()
        except queue.Empty:
            return None
    
    def _keyboard_input_loop(self):
        """Background keyboard input loop for Windows compatibility."""
        import sys
        while self.keyboard_running and self.running:
            try:
                line = sys.stdin.readline()
                if line:
                    self.keyboard_input_queue.put(line)
            except Exception:
                break
    
    def _process_voice_command_queue(self):
        """Process all queued voice commands safely."""
        while True:
            try:
                # Get command from queue (non-blocking)
                command_line = self.voice_command_queue.get_nowait()
                print(f"\n🎤 Executing: {command_line}")
                self._execute_command_line_direct(command_line)
                self.voice_command_queue.task_done()
            except queue.Empty:
                break
    
    def cmd_connect(self, args):
        """Connect to the Tello drone."""
        print("Connecting to Tello drone...")
        if self.agent.connect():
            print("✅ Successfully connected to Tello drone!")
            status = self.agent.get_status()
            print(f"Battery: {status.get('battery', 'N/A')}%")
            print(f"Temperature: {status.get('temperature', 'N/A')}°C")
        else:
            print("❌ Failed to connect to drone. Please check:")
            print("  - Drone is powered on")
            print("  - You're connected to drone's WiFi network")
            print("  - Drone is within range")
    
    def cmd_disconnect(self, args):
        """Disconnect from the drone."""
        self.agent.disconnect()
        print("Disconnected from drone.")
    
    def cmd_status(self, args):
        """Display drone status information."""
        status = self.agent.get_status()
        
        if "error" in status:
            print(f"❌ {status['error']}")
            return
        
        print("\n📊 Drone Status:")
        print("-" * 20)
        print(f"Connected: {'✅' if status['connected'] else '❌'}")
        print(f"Flying: {'✈️' if status['flying'] else '🛬'}")
        print(f"Battery: {status['battery']}% {'🔋' if status['battery'] > 20 else '🪫'}")
        print(f"Temperature: {status['temperature']}°C")
        print(f"Height: {status['height']} cm")
        print(f"Speed: {status['speed']} cm/s")
        print(f"Flight Time: {status['flight_time']} seconds")
        print(f"Video Stream: {'📹' if status['video_stream_on'] else '📷'}")
        print()
    
    def cmd_takeoff(self, args):
        """Command drone to take off."""
        print("🛫 Taking off...")
        if self.agent.takeoff():
            print("✅ Takeoff successful! Drone is now flying.")
            print("⚠️  Use 'land' command to safely land the drone.")
        else:
            print("❌ Takeoff failed. Check status and try again.")
    
    def cmd_land(self, args):
        """Command drone to land."""
        print("🛬 Landing...")
        if self.agent.land():
            print("✅ Landing successful! Drone is safely on the ground.")
        else:
            print("❌ Landing failed.")
    
    def cmd_move(self, args):
        """Move the drone in specified direction and distance."""
        if len(args) != 2:
            print("Usage: move <direction> <distance>")
            print("Directions: left, right, forward, back, up, down")
            print("Distance: 20-500 cm")
            print("Example: move forward 100")
            return
        
        direction = args[0].lower()
        try:
            distance = int(args[1])
        except ValueError:
            print("Distance must be a number between 20-500 cm")
            return
        
        direction_map = {
            'left': self.agent.move_left,
            'right': self.agent.move_right,
            'forward': self.agent.move_forward,
            'back': self.agent.move_back,
            'up': self.agent.move_up,
            'down': self.agent.move_down
        }
        
        if direction not in direction_map:
            print("Invalid direction. Use: left, right, forward, back, up, down")
            return
        
        print(f"Moving {direction} {distance} cm...")
        if direction_map[direction](distance):
            print(f"✅ Moved {direction} {distance} cm successfully!")
        else:
            print(f"❌ Failed to move {direction}")
    
    def cmd_rotate(self, args):
        """Rotate the drone in specified direction and degrees."""
        if len(args) != 2:
            print("Usage: rotate <direction> <degrees>")
            print("Directions: cw (clockwise), ccw (counter-clockwise)")
            print("Degrees: 1-360")
            print("Example: rotate cw 90")
            return
        
        direction = args[0].lower()
        try:
            degrees = int(args[1])
        except ValueError:
            print("Degrees must be a number between 1-360")
            return
        
        print(f"Rotating {direction} {degrees} degrees...")
        if direction == 'cw' or direction == 'clockwise':
            success = self.agent.rotate_clockwise(degrees)
        elif direction == 'ccw' or direction == 'counter-clockwise':
            success = self.agent.rotate_counter_clockwise(degrees)
        else:
            print("Invalid direction. Use: cw (clockwise) or ccw (counter-clockwise)")
            return
        
        if success:
            print(f"✅ Rotated {direction} {degrees} degrees successfully!")
        else:
            print(f"❌ Failed to rotate {direction}")
    
    def cmd_video_on(self, args):
        """Start video streaming."""
        print("📹 Starting video stream...")
        if self.agent.start_video_stream():
            print("✅ Video stream started!")
            print("Use 'photo' command to take pictures")
            print("Use 'video_off' to stop the stream")
        else:
            print("❌ Failed to start video stream")
    
    def cmd_video_off(self, args):
        """Stop video streaming."""
        print("Stopping video stream...")
        self.agent.stop_video_stream()
        print("✅ Video stream stopped")
    
    def cmd_photo(self, args):
        """Take a photo with the drone camera."""
        if len(args) > 1:
            print("Usage: photo [filename]")
            print("Example: photo my_aerial_shot.jpg")
            return
        
        filename = args[0] if args else None
        
        try:
            print("📸 Taking photo...")
            saved_file = self.agent.save_photo(filename)
            print(f"✅ Photo saved: {saved_file}")
        except Exception as e:
            print(f"❌ Failed to take photo: {e}")
            print("Make sure video stream is active (use 'video_on')")
    
    def cmd_emergency(self, args):
        """Emergency stop - immediately stop all motors (drone will fall!)"""
        print("⚠️  EMERGENCY STOP - This will cause the drone to fall!")
        confirm = input("Type 'YES' to confirm emergency stop: ").strip()
        
        if confirm == 'YES':
            print("🚨 ACTIVATING EMERGENCY STOP!")
            self.agent.emergency_stop()
            print("Emergency stop activated. Drone motors stopped.")
        else:
            print("Emergency stop cancelled.")
    
    def cmd_log(self, args):
        """Display flight log."""
        log = self.agent.get_flight_log()
        
        if not log:
            print("No flight log entries.")
            return
        
        print("\n📝 Flight Log:")
        print("-" * 40)
        for i, entry in enumerate(log, 1):
            timestamp = time.strftime("%H:%M:%S", time.localtime(entry['timestamp']))
            action = entry['action']
            data = entry.get('data', {})
            
            print(f"{i:2d}. [{timestamp}] {action}")
            if data:
                for key, value in data.items():
                    print(f"    {key}: {value}")
        print()
    
    def cmd_help(self, args):
        """Display help information."""
        print("\n🚁 Tello Drone Commands:")
        print("=" * 40)
        print("Connection:")
        print("  connect          - Connect to Tello drone")
        print("  disconnect       - Disconnect from drone")
        print("  status           - Show drone status")
        print()
        print("Flight Control:")
        print("  takeoff          - Take off (requires battery > 20%)")
        print("  land             - Land the drone safely")
        print("  move <dir> <cm>  - Move drone (left/right/forward/back/up/down)")
        print("  rotate <dir> <°> - Rotate drone (cw/ccw)")
        print()
        print("Camera:")
        print("  video_on         - Start video streaming")
        print("  video_off        - Stop video streaming")
        print("  photo [filename] - Take a photo")
        print()
        print("🔍 Object Detection:")
        print("  detect_on [type] - Enable detection (face/person/vehicle)")
        print("  detect_off       - Disable object detection")
        print("  detect_status    - Show detection statistics")
        print("  follow [type]    - Start following detected objects")
        print("  follow_stop      - Stop follow mode")
        print("  detect_photo [type] [count] - Auto-photo when objects detected")
        print()
        print("🎤 Voice Commands:")
        print("  voice_on         - Enable voice recognition")
        print("  voice_off        - Disable voice recognition")
        print("  voice_status     - Show voice recognition status")
        print()
        print("🔧 Safety & System:")
        print("  emergency        - Emergency stop (drone will fall!)")
        print("  log              - Show flight log")
        print("  sim/simulation   - Toggle simulation/real mode")
        print("  mode             - Show current mode (sim/real)")
        print("  help/commands    - Show this help")
        print("  quit/exit        - Exit the program")
        print()
        print("Examples:")
        print("  move forward 50")
        print("  rotate cw 90")
        print("  photo aerial_view.jpg")
        print()
    
    # ========== NEW ADVANCED COMMANDS ==========
    
    def cmd_speed(self, args):
        """Set drone movement speed."""
        if len(args) != 1:
            print("Usage: speed <cm/s>")
            print("Speed range: 10-100 cm/s")
            print("Example: speed 50")
            return
        
        try:
            speed = int(args[0])
            if self.agent.set_speed(speed):
                print(f"✅ Speed set to {speed} cm/s")
            else:
                print("❌ Failed to set speed")
        except ValueError:
            print("Speed must be a number between 10-100")
    
    def cmd_hover(self, args):
        """Hover in place for specified duration."""
        duration = 5.0  # default
        if args:
            try:
                duration = float(args[0])
            except ValueError:
                print("Duration must be a number (seconds)")
                return
        
        print(f"🛸 Hovering for {duration} seconds...")
        if self.agent.hover(duration):
            print(f"✅ Hovered for {duration} seconds")
        else:
            print("❌ Hover failed")
    
    def cmd_flip(self, args):
        """Perform aerobatic flips."""
        if len(args) != 1:
            print("Usage: flip <direction>")
            print("Directions: left, right, forward, back")
            print("Example: flip forward")
            return
        
        direction = args[0].lower()
        flip_map = {
            'left': self.agent.flip_left,
            'right': self.agent.flip_right,
            'forward': self.agent.flip_forward,
            'back': self.agent.flip_back
        }
        
        if direction not in flip_map:
            print("Invalid direction. Use: left, right, forward, back")
            return
        
        print(f"🤸 Performing {direction} flip...")
        if flip_map[direction]():
            print(f"✅ {direction.title()} flip completed!")
        else:
            print(f"❌ {direction.title()} flip failed")
    
    def cmd_goto(self, args):
        """Move to specific coordinates."""
        if len(args) not in [3, 4]:
            print("Usage: goto <x> <y> <z> [speed]")
            print("Coordinates: -500 to 500 cm relative to current position")
            print("Speed: 10-100 cm/s (optional, default 30)")
            print("Example: goto 100 50 0 25")
            return
        
        try:
            x, y, z = int(args[0]), int(args[1]), int(args[2])
            speed = int(args[3]) if len(args) == 4 else 30
            
            print(f"📍 Moving to coordinates ({x}, {y}, {z}) at {speed} cm/s...")
            if self.agent.go_xyz_speed(x, y, z, speed):
                print(f"✅ Reached coordinates ({x}, {y}, {z})")
            else:
                print("❌ Failed to reach coordinates")
                
        except ValueError:
            print("All coordinates and speed must be numbers")
    
    def cmd_circle(self, args):
        """Fly in a circular pattern."""
        radius = 100  # default
        speed = 30    # default
        direction = "cw"  # default
        
        if args:
            try:
                radius = int(args[0])
                if len(args) > 1:
                    speed = int(args[1])
                if len(args) > 2:
                    direction = args[2].lower()
            except ValueError:
                print("Usage: circle [radius] [speed] [direction]")
                print("Radius: 50-200 cm, Speed: 10-50 cm/s")
                print("Direction: cw (clockwise) or ccw (counter-clockwise)")
                return
        
        clockwise = direction in ['cw', 'clockwise']
        direction_text = "clockwise" if clockwise else "counter-clockwise"
        
        print(f"🔄 Flying in {direction_text} circle, radius {radius}cm...")
        if self.agent.fly_circle(radius=radius, speed=speed, clockwise=clockwise):
            print("✅ Circle pattern completed!")
        else:
            print("❌ Circle pattern failed")
    
    def cmd_grid(self, args):
        """Perform search grid pattern."""
        grid_size = 100  # default
        spacing = 50     # default
        speed = 30       # default
        
        if args:
            try:
                grid_size = int(args[0])
                if len(args) > 1:
                    spacing = int(args[1])
                if len(args) > 2:
                    speed = int(args[2])
            except ValueError:
                print("Usage: grid [size] [spacing] [speed]")
                print("Size: search area in cm, Spacing: line spacing in cm")
                print("Speed: 10-50 cm/s")
                return
        
        print(f"🔍 Performing search grid {grid_size}x{grid_size}cm...")
        if self.agent.search_grid(grid_size=grid_size, spacing=spacing, speed=speed):
            print("✅ Search grid completed!")
        else:
            print("❌ Search grid failed")
    
    def cmd_burst(self, args):
        """Take multiple photos in sequence."""
        count = 5        # default
        interval = 1.0   # default
        prefix = "burst" # default
        
        if args:
            try:
                count = int(args[0])
                if len(args) > 1:
                    interval = float(args[1])
                if len(args) > 2:
                    prefix = args[2]
            except ValueError:
                print("Usage: burst [count] [interval] [prefix]")
                print("Count: number of photos, Interval: seconds between photos")
                print("Example: burst 3 2.0 action")
                return
        
        print(f"📸 Taking {count} photos with {interval}s interval...")
        try:
            photos = self.agent.take_photo_burst(count=count, interval=interval, prefix=prefix)
            print(f"✅ Photo burst completed: {len(photos)} photos taken")
            for photo in photos:
                print(f"  📷 {photo}")
        except Exception as e:
            print(f"❌ Photo burst failed: {e}")
    
    def cmd_record_start(self, args):
        """Start video recording."""
        filename = args[0] if args else None
        
        try:
            print("🎬 Starting video recording...")
            video_file = self.agent.start_video_recording(filename)
            print(f"✅ Video recording started: {video_file}")
            print("Use 'record_stop' to stop recording")
        except Exception as e:
            print(f"❌ Failed to start recording: {e}")
    
    def cmd_record_stop(self, args):
        """Stop video recording."""
        try:
            print("⏹️  Stopping video recording...")
            video_file = self.agent.stop_video_recording()
            print(f"✅ Video recording saved: {video_file}")
        except Exception as e:
            print(f"❌ Failed to stop recording: {e}")
    
    def cmd_mission(self, args):
        """Execute predefined missions."""
        if len(args) < 1:
            print("Available missions:")
            print("  aerial_survey    - Grid pattern with photos")
            print("  perimeter_check  - Expanding circles patrol")
            print("  photo_session    - Photos at different heights")
            print("  inspection_hover - Hover at multiple points")
            print("  demo_flight      - Demonstration of capabilities")
            print("Usage: mission <mission_name>")
            return
        
        mission_name = args[0]
        print(f"🚀 Starting mission: {mission_name}")
        
        if self.agent.execute_mission(mission_name):
            print(f"✅ Mission '{mission_name}' completed successfully!")
        else:
            print(f"❌ Mission '{mission_name}' failed")
    
    def cmd_natural_language(self, args):
        """Process natural language instructions."""
        if not args:
            print("Examples of natural language commands:")
            print("  say fly in a circle")
            print("  tell take 3 photos")
            print("  say flip forward")
            print("  tell hover for 10 seconds")
            print("  say move forward 100 cm")
            print("Usage: say/tell <instruction>")
            return
        
        instruction = " ".join(args)
        print(f"🤔 Processing: '{instruction}'")
        
        if self.agent.execute_instruction(instruction):
            print("✅ Instruction executed successfully!")
        else:
            print("❌ Could not understand or execute instruction")
    
    def cmd_toggle_simulation(self, args):
        """Toggle between simulation and real drone mode."""
        if self.agent.is_connected:
            print("⚠️  Cannot change mode while connected to drone.")
            print("Please disconnect first using 'disconnect' command.")
            return
        
        # Toggle mode
        self.simulation_mode = not self.simulation_mode
        
        # Create new agent with new mode
        self.agent = TelloDroneAgent(simulation_mode=self.simulation_mode)
        
        if self.simulation_mode:
            print("🎮 Switched to SIMULATION mode")
            print("   ✅ Safe for testing without real drone")
            print("   📝 All commands will be simulated")
        else:
            print("🚁 Switched to REAL DRONE mode")
            print("   ⚠️  Will connect to actual hardware")
            print("   🔌 Make sure you're connected to drone WiFi")
    
    def cmd_show_mode(self, args):
        """Show current operation mode."""
        if self.simulation_mode:
            print("🎮 Current mode: SIMULATION")
            print("   Status: Safe testing mode")
            print("   Description: All commands are simulated")
        else:
            print("🚁 Current mode: REAL DRONE")
            print("   Status: Hardware control mode")
            print("   Description: Commands control actual drone")
        
        connected_text = "✅ Connected" if self.agent.is_connected else "❌ Not connected"
        print(f"   Connection: {connected_text}")
    
    def cmd_detection_on(self, args):
        """Enable object detection."""
        detection_type = args[0] if args else None
        
        print(f"🔍 Enabling object detection...")
        if self.agent.enable_detection(detection_type):
            type_text = f" for {detection_type}" if detection_type else ""
            print(f"✅ Object detection enabled{type_text}!")
            print("Available types: face, person, vehicle")
        else:
            print("❌ Failed to enable object detection")
    
    def cmd_detection_off(self, args):
        """Disable object detection."""
        print("🔍 Disabling object detection...")
        if self.agent.disable_detection():
            print("✅ Object detection disabled!")
        else:
            print("❌ Failed to disable object detection")
    
    def cmd_detection_status(self, args):
        """Show detection status and statistics."""
        try:
            status = self.agent.get_detection_status()
            print("🔍 Object Detection Status:")
            print(f"  Detection enabled: {'✅' if status['detection_enabled'] else '❌'}")
            print(f"  Follow mode: {'✅' if status['follow_mode'] else '❌'}")
            if status['follow_target']:
                print(f"  Following: {status['follow_target']}")
            
            # Show last detections
            if status['last_detections']:
                print("  Recent detections:")
                for obj_type, detections in status['last_detections'].items():
                    if detections:
                        print(f"    {obj_type}: {len(detections)} objects")
            
            # Show statistics
            stats = status['detector_stats']
            if stats['counts']:
                print("  Detection counts:")
                for obj_type, count in stats['counts'].items():
                    if count > 0:
                        print(f"    {obj_type}: {count}")
        except Exception as e:
            print(f"❌ Failed to get detection status: {e}")
    
    def cmd_follow(self, args):
        """Start follow mode for detected objects."""
        target_type = args[0] if args else 'face'
        
        print(f"🎯 Starting follow mode for {target_type}...")
        if self.agent.start_follow_mode(target_type):
            print(f"✅ Follow mode started! Drone will track {target_type}")
            print("Use 'follow_stop' to stop following")
        else:
            print("❌ Failed to start follow mode")
    
    def cmd_follow_stop(self, args):
        """Stop follow mode."""
        print("🎯 Stopping follow mode...")
        if self.agent.stop_follow_mode():
            print("✅ Follow mode stopped!")
        else:
            print("❌ Failed to stop follow mode")
    
    def cmd_detection_photo(self, args):
        """Take photos automatically when objects are detected."""
        target_type = args[0] if args else 'face'
        max_photos = int(args[1]) if len(args) > 1 else 5
        
        print(f"📸 Starting detection photography for {target_type}...")
        print(f"Will take up to {max_photos} photos when {target_type} detected")
        
        if self.agent.detect_and_photo(target_type, max_photos):
            print("✅ Detection photography completed!")
        else:
            print("❌ Detection photography failed")

    def _setup_voice_recognition(self):
        """Initialize voice recognition system."""
        try:
            # Test microphone availability
            self.microphone = sr.Microphone()
            
            # Adjust for ambient noise (one-time calibration)
            print("🎤 Calibrating microphone for ambient noise...")
            with self.microphone as source:
                self.recognizer.adjust_for_ambient_noise(source, duration=1)
            
            # Configure recognizer settings
            self.recognizer.energy_threshold = 300
            self.recognizer.dynamic_energy_threshold = True
            self.recognizer.pause_threshold = 0.8
            
            print("✅ Voice recognition system ready!")
            
        except Exception as e:
            print(f"⚠️  Voice recognition unavailable: {e}")
            self.microphone = None
    
    def cmd_voice_on(self, args):
        """Enable voice recognition mode."""
        if not self.microphone:
            print("❌ No microphone detected. Voice commands unavailable.")
            return
        
        if self.voice_enabled:
            print("🎤 Voice recognition is already enabled!")
            return
        
        try:
            self.voice_enabled = True
            self.voice_running = True
            self.voice_thread = threading.Thread(target=self._voice_recognition_loop, daemon=True)
            self.voice_thread.start()
            
            print("🎤 Voice recognition enabled!")
            print("💬 Say drone commands clearly. Say 'stop listening' to disable.")
            print("📢 Examples: 'fly forward 50', 'take a photo', 'enable face detection'")
            
        except Exception as e:
            print(f"❌ Failed to start voice recognition: {e}")
            self.voice_enabled = False
    
    def cmd_voice_off(self, args):
        """Disable voice recognition mode."""
        if not self.voice_enabled:
            print("🎤 Voice recognition is already disabled.")
            return
        
        try:
            self.voice_enabled = False
            self.voice_running = False
            
            if self.voice_thread and self.voice_thread.is_alive():
                self.voice_thread.join(timeout=2)
            
            print("🎤 Voice recognition disabled!")
            
        except Exception as e:
            print(f"❌ Failed to stop voice recognition: {e}")
    
    def cmd_voice_status(self, args):
        """Show voice recognition status."""
        print("🎤 Voice Recognition Status:")
        print(f"  Microphone available: {'✅' if self.microphone else '❌'}")
        print(f"  Voice recognition: {'✅ Enabled' if self.voice_enabled else '❌ Disabled'}")
        
        if self.voice_enabled:
            print("  Listening for commands...")
            print("  Say 'stop listening' to disable")
        
        if self.microphone:
            print(f"  Energy threshold: {self.recognizer.energy_threshold}")
            print(f"  Pause threshold: {self.recognizer.pause_threshold}s")
    
    def _voice_recognition_loop(self):
        """Background voice recognition loop."""
        print("🎤 Listening for voice commands...")
        
        while self.voice_running and self.voice_enabled:
            try:
                with self.microphone as source:
                    # Listen for audio with timeout
                    audio = self.recognizer.listen(source, timeout=1, phrase_time_limit=5)
                
                try:
                    # Recognize speech using Google's free service
                    command = self.recognizer.recognize_google(audio).lower()
                    
                    if command:
                        print(f"🎤 Voice: '{command}'")
                        
                        # Check for stop listening command
                        if any(phrase in command for phrase in ['stop listening', 'voice off', 'disable voice']):
                            self.voice_enabled = False
                            self.voice_running = False
                            print("🎤 Voice recognition disabled by voice command")
                            break
                        
                        # Process the voice command
                        self._process_voice_command(command)
                
                except sr.UnknownValueError:
                    # Couldn't understand the audio, continue listening
                    continue
                except sr.RequestError as e:
                    print(f"⚠️  Speech recognition service error: {e}")
                    time.sleep(2)
                    
            except sr.WaitTimeoutError:
                # No speech detected, continue listening
                continue
            except Exception as e:
                print(f"⚠️  Voice recognition error: {e}")
                time.sleep(1)
        
        print("🎤 Voice recognition stopped")
    
    def _process_voice_command(self, command: str):
        """Process a recognized voice command."""
        try:
            # Clean up the command
            command = command.strip().lower()
            
            # SECURITY: Block dangerous commands from voice input
            dangerous_commands = ['emergency', 'emergency stop']
            if any(danger in command for danger in dangerous_commands):
                print("🚫 SECURITY: Emergency commands blocked from voice input for safety!")
                print("   Use keyboard to type 'emergency' if needed.")
                return
            
            # Map common voice phrases to CLI commands (excluding dangerous ones)
            voice_mappings = {
                'take off': 'takeoff',
                'land': 'land',
                'take a photo': 'photo',
                'take photo': 'photo',
                'start video': 'video_on',
                'stop video': 'video_off',
                'connect': 'connect',
                'disconnect': 'disconnect',
                'show status': 'status',
                'enable face detection': 'detect_on face',
                'disable detection': 'detect_off',
                'start following': 'follow face',
                'stop following': 'follow_stop',
            }
            
            # Check for direct command mappings
            if command in voice_mappings:
                mapped_command = voice_mappings[command]
                print(f"🎤 → {mapped_command}")
                self._execute_command_line(mapped_command)
                return
            
            # Try to parse movement commands
            if self._parse_movement_command(command):
                return
            
            # Try to parse rotation commands  
            if self._parse_rotation_command(command):
                return
            
            # If no direct mapping, try natural language processing
            print(f"🎤 → say {command}")
            self._execute_command_line(f"say {command}")
            
        except Exception as e:
            print(f"❌ Error processing voice command: {e}")
    
    def _parse_movement_command(self, command: str) -> bool:
        """Parse movement commands from voice input."""
        import re
        
        # Pattern: "fly/move [direction] [distance] [units]"
        movement_patterns = [
            r'(?:fly|move)\s+(forward|back|backward|left|right|up|down)\s+(\d+)(?:\s*(?:cm|centimeters?))?',
            r'(?:go|move)\s+(\d+)(?:\s*(?:cm|centimeters?))?\s+(forward|back|backward|left|right|up|down)',
        ]
        
        for pattern in movement_patterns:
            match = re.search(pattern, command)
            if match:
                if 'forward|back' in pattern:  # First pattern
                    direction, distance = match.groups()
                else:  # Second pattern  
                    distance, direction = match.groups()
                
                # Convert "back" to "backward" for consistency
                if direction == 'back':
                    direction = 'backward'
                
                mapped_command = f"move {direction} {distance}"
                print(f"🎤 → {mapped_command}")
                self._execute_command_line(mapped_command)
                return True
        
        return False
    
    def _parse_rotation_command(self, command: str) -> bool:
        """Parse rotation commands from voice input."""
        import re
        
        # Pattern: "rotate/turn [direction] [degrees]"
        rotation_patterns = [
            r'(?:rotate|turn)\s+(left|right|clockwise|counterclockwise|cw|ccw)\s+(\d+)(?:\s*degrees?)?',
            r'(?:turn|rotate)\s+(\d+)(?:\s*degrees?)?\s+(left|right|clockwise|counterclockwise|cw|ccw)',
        ]
        
        for pattern in rotation_patterns:
            match = re.search(pattern, command)
            if match:
                if 'left|right' in pattern:  # First pattern
                    direction, degrees = match.groups()
                else:  # Second pattern
                    degrees, direction = match.groups()
                
                # Convert directions to cw/ccw
                if direction in ['right', 'clockwise']:
                    direction = 'cw'
                elif direction in ['left', 'counterclockwise']:
                    direction = 'ccw'
                
                mapped_command = f"rotate {direction} {degrees}"
                print(f"🎤 → {mapped_command}")
                self._execute_command_line(mapped_command)
                return True
        
        return False
    
    def _execute_command_line(self, command_line: str):
        """Queue a command line for safe execution by main thread."""
        try:
            # Add command to thread-safe queue instead of executing directly
            self.voice_command_queue.put(command_line)
        except Exception as e:
            print(f"❌ Error queuing voice command: {e}")
    
    def _execute_command_line_direct(self, command_line: str):
        """Execute a command line directly with full thread safety."""
        try:
            parts = command_line.strip().split()
            if not parts:
                return
            
            cmd = parts[0].lower()
            args = parts[1:] if len(parts) > 1 else []
            
            # CRITICAL: Always use command lock for complete thread safety
            with self.command_lock:
                try:
                    if cmd in self.commands:
                        self.commands[cmd](args)
                    else:
                        # Try natural language processing for unknown commands
                        full_instruction = command_line
                        print(f"🤔 Trying to understand: '{full_instruction}'")
                        if self.agent.execute_instruction(full_instruction):
                            print("✅ Instruction executed successfully!")
                        else:
                            print(f"❌ Unknown command: {cmd}")
                            print("Type 'help' for available commands or try natural language.")
                finally:
                    # Ensure prompt is restored after command execution
                    pass
                
        except Exception as e:
            print(f"❌ Error executing command: {e}")
            print("drone> ", end='', flush=True)  # Restore prompt after error
    
    def cmd_quit(self, args):
        """Exit the program with complete cleanup."""
        print("Shutting down drone control system...")
        
        # Set running flag to stop all loops
        self.running = False
        
        # Stop voice recognition and cleanup
        if self.voice_enabled:
            print("Stopping voice recognition...")
            self.voice_enabled = False
            self.voice_running = False
            
            # Wait for voice thread to finish
            if self.voice_thread and self.voice_thread.is_alive():
                self.voice_thread.join(timeout=3)
                if self.voice_thread.is_alive():
                    print("⚠️  Voice thread did not stop gracefully")
        
        # Stop keyboard input thread
        if self.keyboard_running:
            self.keyboard_running = False
            if self.keyboard_thread and self.keyboard_thread.is_alive():
                self.keyboard_thread.join(timeout=1)
                if self.keyboard_thread.is_alive():
                    print("⚠️  Keyboard thread did not stop gracefully")
        
        # Clear any remaining queued commands
        try:
            while not self.voice_command_queue.empty():
                self.voice_command_queue.get_nowait()
                self.voice_command_queue.task_done()
        except:
            pass
        
        # Safely disconnect drone with thread safety
        try:
            with self.command_lock:
                if self.agent.is_connected:
                    if self.agent.is_flying:
                        print("Landing drone before shutdown...")
                        self.agent.land()
                    self.agent.disconnect()
        except Exception as e:
            print(f"⚠️  Cleanup warning: {e}")
        
        print("Goodbye! 👋")
        sys.exit(0)


def main():
    """Main entry point."""
    try:
        # Start in simulation mode by default for safety
        simulation_mode = True
        
        # Check for command line argument to use real drone
        if len(sys.argv) > 1 and sys.argv[1] == "--real":
            simulation_mode = False
            print("⚠️  Starting in REAL DRONE mode (--real flag detected)")
        else:
            print("🎮 Starting in SIMULATION mode (use --real flag for actual drone)")
        
        cli = DroneCLI(simulation_mode=simulation_mode)
        cli.run()
    except Exception as e:
        print(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()