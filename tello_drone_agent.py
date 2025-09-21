"""
Tello Drone Control Agent

A comprehensive agent for controlling DJI Tello drones using the TelloSDK.
This agent provides safe and easy-to-use methods for drone operations including
flight control, camera operations, and status monitoring.
"""

import cv2
import time
import threading
import atexit
import queue
import uuid
import os
import numpy as np
from typing import Optional, Dict, Any, Callable, List, Tuple
import logging
from tello_simulator import create_simulated_tello

# Optional TensorFlow import for AI object detection
try:
    import tensorflow as tf
    TENSORFLOW_AVAILABLE = True
except ImportError:
    TENSORFLOW_AVAILABLE = False
    print("Warning: TensorFlow not available - AI detection disabled")

# Optional djitellopy import for simulation mode support
try:
    from djitellopy import Tello
    DJITELLOPY_AVAILABLE = True
except ImportError:
    Tello = None
    DJITELLOPY_AVAILABLE = False


class TelloDroneAgent:
    """
    A comprehensive agent for controlling DJI Tello drones.
    
    This agent provides a high-level interface for drone operations including:
    - Connection management
    - Flight commands (takeoff, land, movement, rotation)
    - Camera operations and video streaming
    - Battery and status monitoring
    - Safety features and error handling
    """
    
    def __init__(self, enable_logging: bool = True, simulation_mode: bool = False):
        """
        Initialize the Tello Drone Agent.
        
        Args:
            enable_logging: Whether to enable detailed logging
            simulation_mode: Use simulated drone instead of real hardware
        """
        self.simulation_mode = simulation_mode
        
        # Video quality settings
        self.video_resolution = "720p"  # Options: "720p", "480p", "360p"
        self.video_fps = 30
        self.video_quality = "medium"  # Options: "low", "medium", "high"
        
        # Initialize drone (real or simulated)
        if simulation_mode:
            self.drone = create_simulated_tello()
            self.logger_prefix = "[SIM] "
        else:
            if not DJITELLOPY_AVAILABLE:
                raise ImportError("djitellopy not available. Install it or use simulation_mode=True")
            self.drone = Tello()
            self.logger_prefix = "[REAL] "
        
        self.is_connected = False
        self.is_flying = False
        self.video_stream = None
        self.current_frame = None
        self.video_thread = None
        self.stop_video = False
        self.flight_log = []
        self.frame_lock = threading.Lock()  # Protect frame access
        
        # Command queue for sequential execution
        self.command_queue = queue.Queue()
        self.command_lock = threading.Lock()
        self.current_command_event = threading.Event()
        self.command_processor_running = False
        self.command_processor_thread = None
        
        # Object detection system
        self.object_detector = ObjectDetector()
        self.detection_enabled = False
        self.follow_mode = False
        self.follow_target = None  # 'face', 'person', etc.
        self.last_detections = {}
        
        # Register cleanup on exit
        atexit.register(self._cleanup)
        
        # Command history for execute_command
        self.command_history = []
        
        # Setup logging
        if enable_logging:
            logging.basicConfig(level=logging.INFO)
            self.logger = logging.getLogger(__name__)
        else:
            self.logger = logging.getLogger(__name__)
            self.logger.setLevel(logging.CRITICAL)
            
        # Enhanced daily logging integration
        try:
            from pathlib import Path
            from datetime import datetime
            import json
            
            # Import DailyLogger if available
            if hasattr(__builtins__, 'DailyLogger') or 'DailyLogger' in globals():
                self.daily_logger = None  # Will be set by GUI if available
            else:
                self.daily_logger = None
        except ImportError:
            self.daily_logger = None
        
        # Start command processor (after logger is initialized)
        self.start_command_processor()
    
    def connect(self) -> bool:
        """
        Connect to the Tello drone.
        
        Returns:
            bool: True if connection successful, False otherwise
        """
        try:
            if self.simulation_mode:
                self.logger.info(f"{self.logger_prefix}Connecting to simulated Tello drone...")
            else:
                self.logger.info(f"{self.logger_prefix}Attempting to connect to Tello drone...")
            
            self.drone.connect()
            
            # Verify connection by getting battery level
            battery = self.drone.get_battery()
            if battery is not None:
                self.is_connected = True
                mode_text = "simulated" if self.simulation_mode else "real"
                self.logger.info(f"{self.logger_prefix}Successfully connected to {mode_text} Tello! Battery: {battery}%")
                self._log_action("Connected", {"battery": battery, "simulation": self.simulation_mode})
                return True
            else:
                self.logger.error(f"{self.logger_prefix}Failed to connect to Tello drone")
                return False
                
        except Exception as e:
            self.logger.error(f"{self.logger_prefix}Connection failed: {str(e)}")
            return False
    
    def disconnect(self):
        """Safely disconnect from the drone."""
        try:
            if self.is_flying:
                self.land()
            
            if self.video_stream:
                self.stop_video_stream()
            
            # Stop command processor
            self.stop_command_processor()
            
            # Properly close drone connection
            self.drone.end()
            
            self.is_connected = False
            self.logger.info("Disconnected from Tello drone")
            self._log_action("Disconnected")
            
        except Exception as e:
            self.logger.error(f"Error during disconnect: {str(e)}")
    
    def _cleanup(self):
        """Cleanup method called on exit."""
        try:
            if self.is_connected:
                self.disconnect()
        except Exception:
            pass  # Ignore errors during cleanup
    
    def get_status(self) -> Dict[str, Any]:
        """
        Get comprehensive status information about the drone.
        
        Returns:
            Dict containing drone status information
        """
        if not self.is_connected:
            return {"error": "Not connected to drone"}
        
        try:
            status = {
                "connected": self.is_connected,
                "flying": self.is_flying,
                "battery": self.drone.get_battery(),
                "temperature": self.drone.get_temperature(),
                "height": self.drone.get_height(),
                "speed": self.drone.get_speed_x(),
                "flight_time": self.drone.get_flight_time(),
                # "wifi_signal": self.drone.get_wifi(),  # Not available in current SDK
                "video_stream_on": self.video_stream is not None
            }
            return status
        except Exception as e:
            self.logger.error(f"Error getting status: {str(e)}")
            return {"error": str(e)}
    
    def takeoff(self) -> bool:
        """
        Command the drone to take off.
        
        Returns:
            bool: True if takeoff successful, False otherwise
        """
        if not self.is_connected:
            self.logger.error("Cannot takeoff - not connected to drone")
            return False
        
        if self.is_flying:
            self.logger.warning("Drone is already flying")
            return True
        
        try:
            # Check battery level before takeoff
            battery = self.drone.get_battery()
            if battery < 20:
                self.logger.error(f"Battery too low for takeoff: {battery}%")
                return False
            
            self.logger.info("Taking off...")
            self.drone.takeoff()
            self.is_flying = True
            self._log_action("Takeoff", {"battery_at_takeoff": battery})
            self.logger.info("Takeoff successful!")
            return True
            
        except Exception as e:
            self.logger.error(f"Takeoff failed: {str(e)}")
            return False
    
    def land(self) -> bool:
        """
        Command the drone to land.
        
        Returns:
            bool: True if landing successful, False otherwise
        """
        if not self.is_connected:
            self.logger.error("Cannot land - not connected to drone")
            return False
        
        if not self.is_flying:
            self.logger.warning("Drone is already on the ground")
            return True
        
        try:
            self.logger.info("Landing...")
            self.drone.land()
            self.is_flying = False
            self._log_action("Land")
            self.logger.info("Landing successful!")
            return True
            
        except Exception as e:
            self.logger.error(f"Landing failed: {str(e)}")
            return False
    
    def move_left(self, distance: int) -> bool:
        """Move the drone left by specified distance (20-500 cm)."""
        return self._move_command("left", distance, self.drone.move_left)
    
    def move_right(self, distance: int) -> bool:
        """Move the drone right by specified distance (20-500 cm)."""
        return self._move_command("right", distance, self.drone.move_right)
    
    def move_forward(self, distance: int) -> bool:
        """Move the drone forward by specified distance (20-500 cm)."""
        return self._move_command("forward", distance, self.drone.move_forward)
    
    def move_back(self, distance: int) -> bool:
        """Move the drone back by specified distance (20-500 cm)."""
        return self._move_command("back", distance, self.drone.move_back)
    
    def move_up(self, distance: int) -> bool:
        """Move the drone up by specified distance (20-500 cm)."""
        return self._move_command("up", distance, self.drone.move_up)
    
    def move_down(self, distance: int) -> bool:
        """Move the drone down by specified distance (20-500 cm)."""
        return self._move_command("down", distance, self.drone.move_down)
    
    def rotate_clockwise(self, degrees: int) -> bool:
        """Rotate the drone clockwise by specified degrees (1-360)."""
        return self._rotate_command("clockwise", degrees, self.drone.rotate_clockwise)
    
    def rotate_counter_clockwise(self, degrees: int) -> bool:
        """Rotate the drone counter-clockwise by specified degrees (1-360)."""
        return self._rotate_command("counter_clockwise", degrees, self.drone.rotate_counter_clockwise)
    
    def start_command_processor(self):
        """Start the sequential command processor thread."""
        if not self.command_processor_running:
            self.command_processor_running = True
            self.command_processor_thread = threading.Thread(target=self._command_processor_loop, daemon=True)
            self.command_processor_thread.start()
            self.logger.info(f"{self.logger_prefix}Sequential command processor started")
    
    def stop_command_processor(self):
        """Stop the sequential command processor thread."""
        if self.command_processor_running:
            self.command_processor_running = False
            # Add poison pill to wake up processor
            self.command_queue.put(None)
            if self.command_processor_thread:
                self.command_processor_thread.join(timeout=2)
            self.logger.info(f"{self.logger_prefix}Sequential command processor stopped")
    
    def _command_processor_loop(self):
        """Main loop for processing commands sequentially with timeout."""
        while self.command_processor_running:
            try:
                # Get next command from queue (blocks until available)
                command_data = self.command_queue.get(timeout=1)
                
                # Check for poison pill (shutdown signal)
                if command_data is None:
                    break
                
                command_id, command_text, response_callback = command_data
                
                self.logger.info(f"{self.logger_prefix}Processing command {command_id}: {command_text}")
                self.current_command_event.clear()
                
                # Execute command with timeout
                result = None
                try:
                    # Start command execution in a separate thread with timeout
                    result_queue = queue.Queue()
                    
                    def execute_with_timeout():
                        try:
                            # Pass sequential_mode=True to skip unnecessary delays
                            result = self._execute_command_direct(command_text, sequential_mode=True)
                            result_queue.put(result)
                        except Exception as e:
                            result_queue.put(f"❌ Command execution error: {e}")
                    
                    exec_thread = threading.Thread(target=execute_with_timeout, daemon=True)
                    exec_thread.start()
                    
                    # Wait for completion with 10-second timeout
                    try:
                        result = result_queue.get(timeout=10)  # 10-second timeout as requested
                        self.logger.info(f"{self.logger_prefix}Command {command_id} completed: {result[:50]}...")
                    except queue.Empty:
                        result = f"⏱️ Command timeout after 10 seconds: {command_text}"
                        self.logger.warning(f"{self.logger_prefix}Command {command_id} timed out")
                        
                except Exception as e:
                    result = f"❌ Command processing error: {e}"
                    self.logger.error(f"{self.logger_prefix}Command {command_id} error: {e}")
                
                # Send result back through callback
                if response_callback:
                    response_callback(result)
                
                # Mark command as completed
                self.current_command_event.set()
                
                # Brief pause between commands for system stability
                time.sleep(0.1)
                
            except queue.Empty:
                continue  # No commands in queue, keep checking
            except Exception as e:
                self.logger.error(f"{self.logger_prefix}Command processor error: {e}")
                continue
    
    def execute_command(self, command: str, callback=None) -> str:
        """
        Queue a command for sequential execution.
        Commands are processed one at a time with 10-second timeout.
        
        Args:
            command: Command string to execute
            callback: Optional callback function to receive the result
        
        Returns:
            String indicating the command was queued
        """
        if not command or not command.strip():
            return "❌ Empty command"
            
        # Generate unique command ID for tracking
        command_id = str(uuid.uuid4())[:8]
        
        # Queue the command for sequential processing
        self.command_queue.put((command_id, command.strip(), callback))
        
        # Log immediate feedback
        queue_size = self.command_queue.qsize()
        if queue_size == 1:
            result = f"🎯 Executing: {command.strip()}"
        else:
            result = f"📋 Queued: {command.strip()} (position {queue_size})"
            
        self.logger.info(f"{self.logger_prefix}{result} [ID: {command_id}]")
        return result
    
    def _execute_command_direct(self, command: str, sequential_mode: bool = False) -> str:
        """
        Execute a text command directly with optional smart delays.
        
        Args:
            command: Command to execute
            sequential_mode: If True, skip completion delays for faster sequential processing
        """
        try:
            command = command.lower().strip()
            self.command_history.append(command)
            result_msg = ""
            delay_time = 0
            
            # Basic flight commands
            if command == "takeoff":
                result = self.takeoff()
                result_msg = "✅ Takeoff successful" if result else "❌ Takeoff failed"
                delay_time = 2.0  # Takeoff needs settling time
                
            elif command == "land":
                result = self.land()
                result_msg = "✅ Landing successful" if result else "❌ Landing failed"
                delay_time = 2.0  # Landing needs settling time
                
            elif command == "hover" or command.startswith("hover "):
                duration = 5.0  # default duration
                if command.startswith("hover "):
                    try:
                        duration = float(command.split()[1])
                        # Validate duration to prevent timeout issues
                        if duration <= 0:
                            return "❌ Hover duration must be positive"
                        elif duration > 8.0:
                            return "❌ Hover duration cannot exceed 8 seconds (timeout safety)"
                    except (ValueError, IndexError):
                        return "❌ Invalid duration for hover command"
                result = self.hover(duration)
                result_msg = f"✅ Hovered for {duration} seconds" if result else "❌ Hover failed"
                delay_time = duration + 0.5  # Hover duration + small buffer
            
            # Movement commands with distance parsing
            elif command.startswith("forward "):
                try:
                    distance = int(command.split()[1])
                    result = self.move_forward(distance)
                    result_msg = f"✅ Moved forward {distance}cm" if result else f"❌ Forward movement failed"
                    delay_time = max(1.0, distance / 80.0) if result else 0  # No delay on failure
                except ValueError:
                    return "❌ Invalid distance for forward command"
            
            elif command.startswith("back "):
                try:
                    distance = int(command.split()[1])
                    result = self.move_back(distance)
                    result_msg = f"✅ Moved back {distance}cm" if result else f"❌ Back movement failed"
                    delay_time = max(1.0, distance / 80.0) if result else 0
                except ValueError:
                    return "❌ Invalid distance for back command"
            
            elif command.startswith("left "):
                try:
                    distance = int(command.split()[1])
                    result = self.move_left(distance)
                    result_msg = f"✅ Moved left {distance}cm" if result else f"❌ Left movement failed"
                    delay_time = max(1.0, distance / 80.0) if result else 0
                except ValueError:
                    return "❌ Invalid distance for left command"
            
            elif command.startswith("right "):
                try:
                    distance = int(command.split()[1])
                    result = self.move_right(distance)
                    result_msg = f"✅ Moved right {distance}cm" if result else f"❌ Right movement failed"
                    delay_time = max(1.0, distance / 80.0) if result else 0
                except ValueError:
                    return "❌ Invalid distance for right command"
            
            elif command.startswith("up "):
                try:
                    distance = int(command.split()[1])
                    result = self.move_up(distance)
                    result_msg = f"✅ Moved up {distance}cm" if result else f"❌ Up movement failed"
                    delay_time = max(1.0, distance / 80.0) if result else 0
                except ValueError:
                    return "❌ Invalid distance for up command"
            
            elif command.startswith("down "):
                try:
                    distance = int(command.split()[1])
                    result = self.move_down(distance)
                    result_msg = f"✅ Moved down {distance}cm" if result else f"❌ Down movement failed"
                    delay_time = max(1.0, distance / 80.0) if result else 0
                except ValueError:
                    return "❌ Invalid distance for down command"
            
            # Rotation commands
            elif command.startswith("cw "):
                try:
                    degrees = int(command.split()[1])
                    result = self.rotate_clockwise(degrees)
                    result_msg = f"✅ Rotated clockwise {degrees}°" if result else f"❌ Clockwise rotation failed"
                    delay_time = max(1.0, degrees / 120.0) if result else 0  # Improved scaling, no delay on failure
                except ValueError:
                    return "❌ Invalid angle for clockwise rotation"
            
            elif command.startswith("ccw "):
                try:
                    degrees = int(command.split()[1])
                    result = self.rotate_counter_clockwise(degrees)
                    result_msg = f"✅ Rotated counter-clockwise {degrees}°" if result else f"❌ Counter-clockwise rotation failed"
                    delay_time = max(1.0, degrees / 120.0) if result else 0  # Improved scaling, no delay on failure
                except ValueError:
                    return "❌ Invalid angle for counter-clockwise rotation"
            
            # Advanced commands
            elif command.startswith("go "):
                parts = command.split()
                if len(parts) >= 5:  # Fixed: need 5 parts total (go + 4 parameters)
                    try:
                        x, y, z, speed = int(parts[1]), int(parts[2]), int(parts[3]), int(parts[4])
                        result_msg = self.go_xyz_speed(x, y, z, speed)
                        # Calculate delay based on distance and speed
                        distance = (x**2 + y**2 + z**2)**0.5
                        delay_time = max(1.5, distance / speed) if speed > 0 else 2.0
                    except (ValueError, IndexError):
                        return "❌ Invalid parameters for go command"
                else:
                    return "❌ Go command requires: go x y z speed"
            
            elif command.startswith("curve "):
                parts = command.split()
                if len(parts) >= 8:  # Fixed: need 8 parts total (curve + 7 parameters)
                    try:
                        x1, y1, z1, x2, y2, z2, speed = [int(p) for p in parts[1:8]]
                        result_msg = self.curve_xyz_speed(x1, y1, z1, x2, y2, z2, speed)
                        # Calculate curve delay based on approximate path length
                        path_dist = ((x1**2 + y1**2 + z1**2)**0.5 + ((x2-x1)**2 + (y2-y1)**2 + (z2-z1)**2)**0.5)
                        delay_time = max(2.5, path_dist / speed) if speed > 0 else 3.0
                    except (ValueError, IndexError):
                        return "❌ Invalid parameters for curve command"
                else:
                    return "❌ Curve command requires: curve x1 y1 z1 x2 y2 z2 speed"
            
            # Photo commands
            elif command in ["take_photo", "photo", "picture"]:
                try:
                    filename = self.save_photo()
                    result_msg = f"✅ Photo saved: {filename}"
                    delay_time = 0.5  # Brief delay for photo capture
                except Exception as e:
                    result_msg = f"❌ Photo failed: {e}"
                    delay_time = 0
                    
            elif command.startswith("take_photo ") or command.startswith("photo "):
                parts = command.split()
                if len(parts) == 2:
                    try:
                        filename = parts[1]
                        saved_file = self.save_photo(filename)
                        result_msg = f"✅ Photo saved: {saved_file}"
                        delay_time = 0.5
                    except Exception as e:
                        result_msg = f"❌ Photo failed: {e}"
                        delay_time = 0
                else:
                    return "❌ Usage: photo [filename]"
                    
            elif command.startswith("burst "):
                parts = command.split()
                count = 5  # default
                interval = 1.0  # default
                prefix = "burst"  # default
                
                if len(parts) >= 2:
                    try:
                        count = int(parts[1])
                        if len(parts) >= 3:
                            interval = float(parts[2])
                        if len(parts) >= 4:
                            prefix = parts[3]
                    except ValueError:
                        return "❌ Usage: burst [count] [interval] [prefix]"
                
                try:
                    photos = self.take_photo_burst(count=count, interval=interval, prefix=prefix)
                    result_msg = f"✅ Burst completed: {len(photos)} photos taken"
                    delay_time = count * interval + 1.0  # Total burst time
                except Exception as e:
                    result_msg = f"❌ Burst failed: {e}"
                    delay_time = 0
            
            elif command == "burst":
                try:
                    photos = self.take_photo_burst()  # Use defaults: 5 photos, 1s interval
                    result_msg = f"✅ Burst completed: {len(photos)} photos taken"
                    delay_time = 6.0  # 5 photos * 1s + 1s buffer
                except Exception as e:
                    result_msg = f"❌ Burst failed: {e}"
                    delay_time = 0
            
            # Vision analysis commands
            elif command.startswith("analyze_view") or command in ["analyze", "describe_view"]:
                try:
                    # Parse command with parameters (JSON format from AI)
                    if command.startswith("analyze_view "):
                        # Extract parameters from command
                        params_str = command[len("analyze_view "):].strip()
                        try:
                            import json
                            params = json.loads(params_str) if params_str else {}
                        except json.JSONDecodeError:
                            # Fallback to simple parsing
                            params = {"prompt": params_str, "use_photo": False}
                    else:
                        # Default parameters for simple commands
                        params = {"prompt": "describe what you see", "use_photo": False}
                    
                    custom_prompt = params.get("prompt", "describe what you see")
                    use_photo = params.get("use_photo", False)
                    
                    result_msg = f"✅ Vision analysis requested: {custom_prompt[:50]}..."
                    delay_time = 3.0  # Time for AI vision processing
                    
                    # Set context for callback
                    if hasattr(self, 'vision_analysis_callback') and self.vision_analysis_callback:
                        self.vision_analysis_callback(custom_prompt, use_photo)
                    else:
                        # Store analysis request for GUI to process
                        self.logger.info(f"Vision analysis: '{custom_prompt}' (use_photo: {use_photo})")
                        
                except Exception as e:
                    result_msg = f"❌ Vision analysis failed: {e}"
                    delay_time = 0
            
            else:
                return f"❌ Unknown command: {command}"
            
            # Apply smart delays only if not in sequential mode
            if not sequential_mode and delay_time > 0:
                if not self.simulation_mode:
                    self.logger.info(f"{self.logger_prefix}Waiting {delay_time:.1f}s for command completion...")
                    time.sleep(delay_time)
                else:
                    # Shorter delays in simulation mode for faster testing
                    simulation_delay = min(0.5, delay_time * 0.25)
                    time.sleep(simulation_delay)
            elif sequential_mode and delay_time > 0:
                # In sequential mode, add minimal delay only for safety
                safety_delay = min(0.1, delay_time * 0.05)  # Maximum 0.1s safety delay
                if safety_delay > 0:
                    time.sleep(safety_delay)
                
            return result_msg
                
        except Exception as e:
            return f"❌ Command execution error: {e}"
    
    def go_xyz_speed(self, x: int, y: int, z: int, speed: int) -> str:
        """
        Fly directly to specified coordinates with speed control.
        
        Args:
            x, y, z: Target coordinates (cm) relative to current position
            speed: Flight speed (10-100 cm/s)
        
        Returns:
            str: Result message
        """
        try:
            # Validate parameters
            if not self._check_flight_ready():
                return "❌ Drone not ready for flight"
                
            if not 10 <= speed <= 100:
                return f"❌ Invalid speed: {speed}. Must be between 10-100 cm/s"
            
            # Validate coordinates (must be within reasonable range)
            if not (-500 <= x <= 500) or not (-500 <= y <= 500) or not (-500 <= z <= 500):
                return f"❌ Coordinates out of range: ({x},{y},{z}). Must be within ±500cm"
            
            self.logger.info(f"Flying to coordinates ({x},{y},{z}) at {speed}cm/s")
            
            # Execute go command using Tello SDK
            if hasattr(self.drone, 'go_xyz_speed'):
                self.drone.go_xyz_speed(x, y, z, speed)
            else:
                # Fallback for simulation mode
                self.logger.info(f"[SIM] Go command: x={x}, y={y}, z={z}, speed={speed}")
            
            self._log_action("Go XYZ Speed", {"x": x, "y": y, "z": z, "speed": speed})
            return f"✅ Flying to ({x},{y},{z}) at {speed}cm/s"
            
        except Exception as e:
            error_msg = f"Go command failed: {e}"
            self.logger.error(error_msg)
            return f"❌ {error_msg}"
    
    def curve_xyz_speed(self, x1: int, y1: int, z1: int, x2: int, y2: int, z2: int, speed: int) -> str:
        """
        Fly in a curve from current position through two waypoints with speed control.
        
        Args:
            x1, y1, z1: First waypoint coordinates (cm)
            x2, y2, z2: Second waypoint coordinates (cm)  
            speed: Flight speed (10-100 cm/s)
        
        Returns:
            str: Result message
        """
        try:
            # Validate parameters
            if not self._check_flight_ready():
                return "❌ Drone not ready for flight"
                
            if not 10 <= speed <= 100:
                return f"❌ Invalid speed: {speed}. Must be between 10-100 cm/s"
            
            # Validate waypoint distances (must be at least 20cm from origin)
            dist1 = (x1**2 + y1**2 + z1**2)**0.5
            dist2 = (x2**2 + y2**2 + z2**2)**0.5
            
            if dist1 < 20:
                return f"❌ First waypoint too close to origin: {dist1:.1f}cm (minimum 20cm)"
            if dist2 < 20:
                return f"❌ Second waypoint too close to origin: {dist2:.1f}cm (minimum 20cm)"
            
            # Validate coordinates range
            for coord, name in [(x1, 'x1'), (y1, 'y1'), (z1, 'z1'), (x2, 'x2'), (y2, 'y2'), (z2, 'z2')]:
                if not (-500 <= coord <= 500):
                    return f"❌ {name} coordinate out of range: {coord}. Must be within ±500cm"
            
            self.logger.info(f"Curve flight: ({x1},{y1},{z1}) -> ({x2},{y2},{z2}) at {speed}cm/s")
            
            # Execute curve command using Tello SDK
            if hasattr(self.drone, 'curve_xyz_speed'):
                self.drone.curve_xyz_speed(x1, y1, z1, x2, y2, z2, speed)
            else:
                # Fallback for simulation mode
                self.logger.info(f"[SIM] Curve command: ({x1},{y1},{z1}) -> ({x2},{y2},{z2}), speed={speed}")
            
            self._log_action("Curve XYZ Speed", {
                "x1": x1, "y1": y1, "z1": z1,
                "x2": x2, "y2": y2, "z2": z2,
                "speed": speed
            })
            return f"✅ Curve flight completed: ({x1},{y1},{z1}) -> ({x2},{y2},{z2}) at {speed}cm/s"
            
        except Exception as e:
            error_msg = f"Curve command failed: {e}"
            self.logger.error(error_msg)
            return f"❌ {error_msg}"
    
    def _move_command(self, direction: str, distance: int, command_func: Callable) -> bool:
        """Helper method for movement commands."""
        if not self._check_flight_ready():
            return False
        
        if not 20 <= distance <= 500:
            self.logger.error(f"Invalid distance: {distance}. Must be between 20-500 cm")
            return False
        
        try:
            self.logger.info(f"Moving {direction} {distance} cm...")
            command_func(distance)
            self._log_action(f"Move {direction}", {"distance": distance})
            return True
        except Exception as e:
            self.logger.error(f"Move {direction} failed: {str(e)}")
            return False
    
    def _rotate_command(self, direction: str, degrees: int, command_func: Callable) -> bool:
        """Helper method for rotation commands."""
        if not self._check_flight_ready():
            return False
        
        if not 1 <= degrees <= 360:
            self.logger.error(f"Invalid degrees: {degrees}. Must be between 1-360")
            return False
        
        try:
            self.logger.info(f"Rotating {direction} {degrees} degrees...")
            command_func(degrees)
            self._log_action(f"Rotate {direction}", {"degrees": degrees})
            return True
        except Exception as e:
            self.logger.error(f"Rotate {direction} failed: {str(e)}")
            return False
    
    def start_video_stream(self) -> bool:
        """
        Start video streaming from the drone camera.
        
        Returns:
            bool: True if video stream started successfully
        """
        if not self.is_connected:
            self.logger.error("Cannot start video - not connected to drone")
            return False
        
        try:
            # Use drone camera (real or simulated)
            self.drone.streamon()
            
            # Get frame reader
            self.video_stream = self.drone.get_frame_read()
            
            self.stop_video = False
            
            # Start video capture thread
            self.video_thread = threading.Thread(target=self._video_capture_loop)
            self.video_thread.daemon = True
            self.video_thread.start()
            
            self.logger.info("Video stream started")
            self._log_action("Video stream started", {
                "resolution": self.video_resolution,
                "fps": self.video_fps,
                "quality": self.video_quality
            })
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to start video stream: {str(e)}")
            return False
    
    def stop_video_stream(self):
        """Stop the video stream."""
        try:
            self.stop_video = True
            if self.video_thread:
                self.video_thread.join(timeout=2)
            
            if self.video_stream:
                self.drone.streamoff()
                self.video_stream = None
            
            self.logger.info("Video stream stopped")
            self._log_action("Video stream stopped")
            
        except Exception as e:
            self.logger.error(f"Error stopping video stream: {str(e)}")
    
    def _video_capture_loop(self):
        """Video capture loop running in separate thread."""
        frame_delay = 1.0 / self.video_fps  # Dynamic frame rate
        
        while not self.stop_video and self.video_stream:
            try:
                frame = self.video_stream.frame
                
                # Apply quality enhancements
                if frame is not None:
                    frame = self._enhance_frame_quality(frame)
                
                # Apply object detection if enabled
                if self.detection_enabled and frame is not None:
                    frame, detections = self.object_detector.detect_objects(frame)
                    self.last_detections = detections
                    
                    # Follow mode - automatically track detected objects
                    if self.follow_mode and self.follow_target in detections:
                        self._execute_follow_behavior(detections[self.follow_target])
                
                with self.frame_lock:
                    self.current_frame = frame
                    
                time.sleep(frame_delay)  # Dynamic FPS control
            except Exception as e:
                self.logger.error(f"Video capture error: {str(e)}")
                break
    
    def get_current_frame(self):
        """Get the current video frame safely."""
        with self.frame_lock:
            return self.current_frame
    
    
    def _enhance_frame_quality(self, frame):
        """Apply quality enhancements to video frame."""
        if frame is None:
            return None
            
        try:
            # Apply quality enhancements based on video_quality setting
            if self.video_quality == "high":
                # High quality: denoise and sharpen
                frame = cv2.bilateralFilter(frame, 9, 75, 75)
                kernel = np.array([[-1,-1,-1], [-1,9,-1], [-1,-1,-1]])
                frame = cv2.filter2D(frame, -1, kernel)
                
            elif self.video_quality == "medium":
                # Medium quality: light denoising
                frame = cv2.bilateralFilter(frame, 5, 50, 50)
                
            # Low quality: no processing for performance
            
            # Ensure frame is in correct format
            if len(frame.shape) == 3 and frame.shape[2] == 3:
                # Already BGR format, good for OpenCV
                pass
            elif len(frame.shape) == 3 and frame.shape[2] == 4:
                # BGRA to BGR
                frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
            
            return frame
            
        except Exception as e:
            self.logger.warning(f"Frame enhancement failed: {e}")
            return frame
    
    def set_video_quality(self, resolution: str = "720p", fps: int = 30, quality: str = "medium"):
        """
        Set video quality parameters.
        
        Args:
            resolution: "720p", "480p", or "360p"
            fps: Frame rate (10-60)
            quality: "low", "medium", or "high"
        """
        self.video_resolution = resolution
        self.video_fps = max(10, min(60, fps))
        self.video_quality = quality
        
        self.logger.info(f"Video quality set: {resolution}@{fps}fps, quality={quality}")
        
    
    
    def save_photo(self, filename: Optional[str] = None) -> str:
        """
        Take a photo and save it to disk.
        
        Args:
            filename: Optional filename. If None, auto-generates timestamp-based name
            
        Returns:
            str: Path to saved photo file
        """
        if self.current_frame is None:
            if not self.start_video_stream():
                raise Exception("Cannot take photo - video stream not available")
            time.sleep(1)  # Wait for frame to be available
            
        if self.current_frame is None:
            raise Exception("No frame available for photo")
        
        if filename is None:
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            filename = f"tello_photo_{timestamp}.jpg"
        
        try:
            with self.frame_lock:
                frame_to_save = self.current_frame
            
            if frame_to_save is None:
                raise Exception("No frame available for photo")
            
            cv2.imwrite(filename, frame_to_save)
            self.logger.info(f"Photo saved: {filename}")
            self._log_action("Photo taken", {"filename": filename})
            return filename
        except Exception as e:
            self.logger.error(f"Failed to save photo: {str(e)}")
            raise
    
    def emergency_stop(self):
        """Emergency stop - immediately stop all motors (drone will fall!)."""
        try:
            self.logger.warning("EMERGENCY STOP ACTIVATED!")
            self.drone.emergency()
            self.is_flying = False
            self._log_action("EMERGENCY STOP")
        except Exception as e:
            self.logger.error(f"Emergency stop failed: {str(e)}")
    
    # ========== ADVANCED FLIGHT COMMANDS ==========
    
    def flip_left(self) -> bool:
        """Perform a flip to the left."""
        return self._flip_command("left", self.drone.flip_left)
    
    def flip_right(self) -> bool:
        """Perform a flip to the right."""
        return self._flip_command("right", self.drone.flip_right)
    
    def flip_forward(self) -> bool:
        """Perform a flip forward."""
        return self._flip_command("forward", self.drone.flip_forward)
    
    def flip_back(self) -> bool:
        """Perform a flip backward."""
        return self._flip_command("back", self.drone.flip_back)
    
    def _flip_command(self, direction: str, command_func: Callable) -> bool:
        """Helper method for flip commands."""
        if not self._check_flight_ready():
            return False
        
        # Check sufficient height for flip (recommend >100cm)
        height = self.drone.get_height()
        if height < 100:
            self.logger.error(f"Height too low for flip: {height}cm. Recommend >100cm")
            return False
        
        try:
            self.logger.info(f"Performing flip {direction}...")
            command_func()
            self._log_action(f"Flip {direction}", {"height": height})
            time.sleep(2)  # Give time for flip to complete
            return True
        except Exception as e:
            self.logger.error(f"Flip {direction} failed: {str(e)}")
            return False
    
    def set_speed(self, speed: int) -> bool:
        """
        Set drone movement speed.
        
        Args:
            speed: Speed in cm/s (10-100)
        """
        if not self.is_connected:
            self.logger.error("Not connected to drone")
            return False
        
        if not 10 <= speed <= 100:
            self.logger.error(f"Invalid speed: {speed}. Must be between 10-100 cm/s")
            return False
        
        try:
            self.drone.set_speed(speed)
            self.logger.info(f"Speed set to {speed} cm/s")
            self._log_action("Set speed", {"speed": speed})
            return True
        except Exception as e:
            self.logger.error(f"Failed to set speed: {str(e)}")
            return False
    
    
    def hover(self, duration: float = 5.0) -> bool:
        """
        Hover in place for specified duration.
        
        Args:
            duration: Hover time in seconds
        """
        if not self._check_flight_ready():
            return False
        
        try:
            self.logger.info(f"Hovering for {duration} seconds...")
            time.sleep(duration)
            self._log_action("Hover", {"duration": duration})
            return True
        except Exception as e:
            self.logger.error(f"Hover failed: {str(e)}")
            return False
    
    # ========== PATTERN MOVEMENTS ==========
    
    def fly_circle(self, radius: int = 100, speed: int = 30, clockwise: bool = True) -> bool:
        """
        Fly in a circular pattern.
        
        Args:
            radius: Circle radius in cm (50-200)
            speed: Flight speed in cm/s (10-50)
            clockwise: Direction of circle
        """
        if not self._check_flight_ready():
            return False
        
        if not 50 <= radius <= 200:
            self.logger.error("Radius must be between 50-200 cm")
            return False
        
        try:
            self.logger.info(f"Flying in {'clockwise' if clockwise else 'counter-clockwise'} circle, radius {radius}cm...")
            
            # Simple circle using 8 waypoints
            angles = [i * 45 for i in range(8)]  # 8 points around circle
            if not clockwise:
                angles.reverse()
            
            original_speed = self.drone.query_speed()
            self.set_speed(speed)
            
            for angle in angles:
                import math
                x = int(radius * math.cos(math.radians(angle)))
                y = int(radius * math.sin(math.radians(angle)))
                self.go_xyz_speed(x, y, 0, speed)
                time.sleep(1)
            
            # Return to center
            self.go_xyz_speed(0, 0, 0, speed)
            
            # Restore original speed
            if original_speed:
                self.set_speed(original_speed)
            
            self._log_action("Circle pattern", {"radius": radius, "clockwise": clockwise})
            return True
            
        except Exception as e:
            self.logger.error(f"Circle pattern failed: {str(e)}")
            return False
    
    def search_grid(self, grid_size: int = 100, spacing: int = 50, speed: int = 30) -> bool:
        """
        Perform a search grid pattern.
        
        Args:
            grid_size: Size of search area in cm
            spacing: Distance between grid lines in cm
            speed: Flight speed in cm/s
        """
        if not self._check_flight_ready():
            return False
        
        try:
            self.logger.info(f"Performing search grid {grid_size}x{grid_size}cm, spacing {spacing}cm...")
            
            self.set_speed(speed)
            
            # Grid pattern - back and forth
            rows = grid_size // spacing
            for row in range(rows):
                y = -grid_size//2 + row * spacing
                
                # Move to start of row
                if row % 2 == 0:  # Even rows: left to right
                    self.go_xyz_speed(-grid_size//2, y, 0, speed)
                    time.sleep(1)
                    self.go_xyz_speed(grid_size//2, y, 0, speed)
                else:  # Odd rows: right to left
                    self.go_xyz_speed(grid_size//2, y, 0, speed)
                    time.sleep(1)
                    self.go_xyz_speed(-grid_size//2, y, 0, speed)
                
                time.sleep(1)
            
            # Return to center
            self.go_xyz_speed(0, 0, 0, speed)
            
            self._log_action("Search grid", {"grid_size": grid_size, "spacing": spacing})
            return True
            
        except Exception as e:
            self.logger.error(f"Search grid failed: {str(e)}")
            return False
    
    # ========== ENHANCED CAMERA FEATURES ==========
    
    def start_video_recording(self, filename: Optional[str] = None) -> str:
        """
        Start recording video to file.
        
        Args:
            filename: Optional filename for video
            
        Returns:
            str: Path to video file
        """
        if not self.video_stream:
            if not self.start_video_stream():
                raise Exception("Cannot start recording - video stream not available")
        
        if filename is None:
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            filename = f"tello_video_{timestamp}.avi"
        
        try:
            # Get frame dimensions
            frame = self.get_current_frame()
            if frame is None:
                raise Exception("No frame available for recording")
            
            height, width, _ = frame.shape
            
            # Initialize video writer
            fourcc = cv2.VideoWriter.fourcc(*'XVID')
            self.video_writer = cv2.VideoWriter(filename, fourcc, 20.0, (width, height))
            self.recording = True
            self.recording_filename = filename
            
            # Start recording thread
            self.recording_thread = threading.Thread(target=self._recording_loop)
            self.recording_thread.daemon = True
            self.recording_thread.start()
            
            self.logger.info(f"Video recording started: {filename}")
            self._log_action("Video recording started", {"filename": filename})
            return filename
            
        except Exception as e:
            self.logger.error(f"Failed to start video recording: {str(e)}")
            raise
    
    def stop_video_recording(self) -> str:
        """
        Stop video recording.
        
        Returns:
            str: Path to recorded video file
        """
        if not hasattr(self, 'recording') or not self.recording:
            raise Exception("No recording in progress")
        
        try:
            self.recording = False
            
            if hasattr(self, 'recording_thread'):
                self.recording_thread.join(timeout=5)
            
            if hasattr(self, 'video_writer'):
                self.video_writer.release()
            
            filename = self.recording_filename
            self.logger.info(f"Video recording stopped: {filename}")
            self._log_action("Video recording stopped", {"filename": filename})
            return filename
            
        except Exception as e:
            self.logger.error(f"Failed to stop video recording: {str(e)}")
            raise
    
    def _recording_loop(self):
        """Video recording loop."""
        while self.recording and hasattr(self, 'video_writer'):
            try:
                frame = self.get_current_frame()
                if frame is not None:
                    self.video_writer.write(frame)
                time.sleep(0.05)  # 20 FPS
            except Exception as e:
                self.logger.error(f"Recording error: {str(e)}")
                break
    
    def take_photo_burst(self, count: int = 5, interval: float = 1.0, prefix: str = "burst") -> list:
        """
        Take multiple photos in sequence.
        
        Args:
            count: Number of photos to take
            interval: Time between photos in seconds
            prefix: Filename prefix
            
        Returns:
            list: List of saved photo filenames
        """
        if not self.video_stream:
            if not self.start_video_stream():
                raise Exception("Cannot take photos - video stream not available")
        
        photos = []
        try:
            self.logger.info(f"Taking {count} photos with {interval}s interval...")
            
            for i in range(count):
                timestamp = time.strftime("%Y%m%d_%H%M%S")
                filename = f"{prefix}_{i+1:02d}_{timestamp}.jpg"
                
                photo_path = self.save_photo(filename)
                photos.append(photo_path)
                
                if i < count - 1:  # Don't wait after last photo
                    time.sleep(interval)
            
            self._log_action("Photo burst", {"count": count, "interval": interval})
            self.logger.info(f"Photo burst completed: {len(photos)} photos")
            return photos
            
        except Exception as e:
            self.logger.error(f"Photo burst failed: {str(e)}")
            raise
    
    # ========== NATURAL LANGUAGE PROCESSING ==========
    
    def execute_instruction(self, instruction: str) -> bool:
        """
        Execute natural language instructions.
        
        Args:
            instruction: Natural language command like "fly in a circle" or "take 3 photos"
            
        Returns:
            bool: True if instruction was understood and executed
        """
        instruction = instruction.lower().strip()
        self.logger.info(f"Processing instruction: '{instruction}'")
        
        try:
            # Flight patterns
            if "circle" in instruction:
                return self._parse_circle_instruction(instruction)
            elif "grid" in instruction or "search" in instruction:
                return self._parse_grid_instruction(instruction)
            elif "flip" in instruction:
                return self._parse_flip_instruction(instruction)
            elif "hover" in instruction:
                return self._parse_hover_instruction(instruction)
            
            # Movement commands
            elif any(word in instruction for word in ["move", "go", "fly"]):
                return self._parse_movement_instruction(instruction)
            elif "rotate" in instruction or "turn" in instruction:
                return self._parse_rotation_instruction(instruction)
            elif "speed" in instruction:
                return self._parse_speed_instruction(instruction)
            
            # Camera commands
            elif "photo" in instruction or "picture" in instruction:
                return self._parse_photo_instruction(instruction)
            elif "video" in instruction:
                return self._parse_video_instruction(instruction)
            elif "record" in instruction:
                return self._parse_recording_instruction(instruction)
            
            # Flight control
            elif "takeoff" in instruction or "take off" in instruction:
                return self.takeoff()
            elif "land" in instruction:
                return self.land()
            elif "emergency" in instruction or "stop" in instruction:
                self.emergency_stop()
                return True
            
            else:
                self.logger.error(f"Unknown instruction: '{instruction}'")
                return False
                
        except Exception as e:
            self.logger.error(f"Failed to execute instruction '{instruction}': {str(e)}")
            return False
    
    def _parse_circle_instruction(self, instruction: str) -> bool:
        """Parse circle flight instructions."""
        import re
        
        # Extract radius if specified
        radius = 100  # default
        radius_match = re.search(r'(\d+)\s*(cm|centimeter)', instruction)
        if radius_match:
            radius = int(radius_match.group(1))
        
        # Extract direction
        clockwise = "counter" not in instruction and "ccw" not in instruction
        
        return self.fly_circle(radius=radius, clockwise=clockwise)
    
    def _parse_grid_instruction(self, instruction: str) -> bool:
        """Parse grid search instructions."""
        import re
        
        # Extract grid size if specified
        grid_size = 100  # default
        size_match = re.search(r'(\d+)\s*(cm|meter|m)', instruction)
        if size_match:
            size = int(size_match.group(1))
            unit = size_match.group(2)
            grid_size = size * 100 if unit in ['meter', 'm'] else size
        
        return self.search_grid(grid_size=grid_size)
    
    def _parse_flip_instruction(self, instruction: str) -> bool:
        """Parse flip instructions."""
        if "left" in instruction:
            return self.flip_left()
        elif "right" in instruction:
            return self.flip_right()
        elif "forward" in instruction or "front" in instruction:
            return self.flip_forward()
        elif "back" in instruction or "backward" in instruction:
            return self.flip_back()
        else:
            # Default to forward flip
            return self.flip_forward()
    
    def _parse_hover_instruction(self, instruction: str) -> bool:
        """Parse hover instructions."""
        import re
        
        # Extract duration if specified
        duration = 5.0  # default
        duration_match = re.search(r'(\d+(?:\.\d+)?)\s*second', instruction)
        if duration_match:
            duration = float(duration_match.group(1))
        
        return self.hover(duration=duration)
    
    def _parse_movement_instruction(self, instruction: str) -> bool:
        """Parse movement instructions."""
        import re
        
        # Extract direction
        direction = None
        if "left" in instruction:
            direction = "left"
        elif "right" in instruction:
            direction = "right"
        elif "forward" in instruction or "front" in instruction:
            direction = "forward"
        elif "back" in instruction or "backward" in instruction:
            direction = "back"
        elif "up" in instruction:
            direction = "up"
        elif "down" in instruction:
            direction = "down"
        
        if not direction:
            self.logger.error("No direction specified in movement instruction")
            return False
        
        # Extract distance
        distance = 50  # default
        distance_match = re.search(r'(\d+)\s*(cm|centimeter)', instruction)
        if distance_match:
            distance = int(distance_match.group(1))
        
        # Execute movement
        movement_map = {
            'left': self.move_left,
            'right': self.move_right,
            'forward': self.move_forward,
            'back': self.move_back,
            'up': self.move_up,
            'down': self.move_down
        }
        
        return movement_map[direction](distance)
    
    def _parse_rotation_instruction(self, instruction: str) -> bool:
        """Parse rotation instructions."""
        import re
        
        # Extract direction
        clockwise = True
        if "counter" in instruction or "ccw" in instruction or "left" in instruction:
            clockwise = False
        
        # Extract degrees
        degrees = 90  # default
        degrees_match = re.search(r'(\d+)\s*degree', instruction)
        if degrees_match:
            degrees = int(degrees_match.group(1))
        
        if clockwise:
            return self.rotate_clockwise(degrees)
        else:
            return self.rotate_counter_clockwise(degrees)
    
    def _parse_speed_instruction(self, instruction: str) -> bool:
        """Parse speed instructions."""
        import re
        
        # Extract speed value
        speed_match = re.search(r'(\d+)', instruction)
        if speed_match:
            speed = int(speed_match.group(1))
            return self.set_speed(speed)
        else:
            self.logger.error("No speed value found in instruction")
            return False
    
    def _parse_photo_instruction(self, instruction: str) -> bool:
        """Parse photo instructions."""
        import re
        
        # Check for burst/multiple photos
        count_match = re.search(r'(\d+)\s*photo', instruction)
        if count_match:
            count = int(count_match.group(1))
            if count > 1:
                self.take_photo_burst(count=count)
                return True
        
        # Single photo
        self.save_photo()
        return True
    
    def _parse_video_instruction(self, instruction: str) -> bool:
        """Parse video instructions."""
        if "start" in instruction or "begin" in instruction or "on" in instruction:
            return self.start_video_stream()
        elif "stop" in instruction or "end" in instruction or "off" in instruction:
            self.stop_video_stream()
            return True
        else:
            # Default to start video
            return self.start_video_stream()
    
    def _parse_recording_instruction(self, instruction: str) -> bool:
        """Parse recording instructions."""
        if "start" in instruction or "begin" in instruction:
            self.start_video_recording()
            return True
        elif "stop" in instruction or "end" in instruction:
            self.stop_video_recording()
            return True
        else:
            # Default to start recording
            self.start_video_recording()
            return True
    
    # ========== MISSION PLANNING ==========
    
    def execute_mission(self, mission_name: str, **kwargs) -> bool:
        """
        Execute predefined missions.
        
        Args:
            mission_name: Name of the mission to execute
            **kwargs: Mission parameters
            
        Returns:
            bool: True if mission executed successfully
        """
        missions = {
            "aerial_survey": self._mission_aerial_survey,
            "perimeter_check": self._mission_perimeter_check,
            "photo_session": self._mission_photo_session,
            "inspection_hover": self._mission_inspection_hover,
            "demo_flight": self._mission_demo_flight
        }
        
        if mission_name not in missions:
            self.logger.error(f"Unknown mission: {mission_name}")
            return False
        
        try:
            self.logger.info(f"Starting mission: {mission_name}")
            return missions[mission_name](**kwargs)
        except Exception as e:
            self.logger.error(f"Mission {mission_name} failed: {str(e)}")
            return False
    
    def _mission_aerial_survey(self, area_size: int = 200, photo_interval: int = 3) -> bool:
        """Aerial survey mission with grid pattern and photos."""
        if not self.takeoff():
            return False
        
        try:
            # Start video recording
            self.start_video_recording("aerial_survey.avi")
            
            # Perform grid search with photos
            self.search_grid(grid_size=area_size, spacing=50)
            
            # Take photos at key points
            for i in range(0, 360, 90):  # 4 directions
                self.rotate_clockwise(90)
                time.sleep(1)
                self.save_photo(f"survey_direction_{i}.jpg")
                time.sleep(photo_interval)
            
            # Stop recording and land
            self.stop_video_recording()
            return self.land()
            
        except Exception as e:
            self.logger.error(f"Aerial survey failed: {str(e)}")
            if self.is_flying:
                self.land()
            return False
    
    def _mission_perimeter_check(self, radius: int = 150) -> bool:
        """Perimeter check mission flying in expanding circles."""
        if not self.takeoff():
            return False
        
        try:
            # Fly in expanding circles
            for r in range(50, radius + 1, 50):
                self.fly_circle(radius=r, speed=20)
                self.save_photo(f"perimeter_{r}cm.jpg")
                time.sleep(2)
            
            return self.land()
            
        except Exception as e:
            self.logger.error(f"Perimeter check failed: {str(e)}")
            if self.is_flying:
                self.land()
            return False
    
    def _mission_photo_session(self, height_levels: Optional[list] = None) -> bool:
        """Photo session at different heights and angles."""
        if height_levels is None:
            height_levels = [50, 100, 150]
        
        if not self.takeoff():
            return False
        
        try:
            self.start_video_stream()
            
            for height in height_levels:
                # Move to height
                current_height = self.drone.get_height()
                height_diff = height - current_height
                
                if height_diff > 0:
                    self.move_up(min(abs(height_diff), 200))
                elif height_diff < 0:
                    self.move_down(min(abs(height_diff), 200))
                
                # Take photos in 4 directions
                for angle in [0, 90, 180, 270]:
                    self.rotate_clockwise(90)
                    time.sleep(1)
                    self.save_photo(f"photo_session_h{height}_a{angle}.jpg")
                    time.sleep(1)
            
            return self.land()
            
        except Exception as e:
            self.logger.error(f"Photo session failed: {str(e)}")
            if self.is_flying:
                self.land()
            return False
    
    def _mission_inspection_hover(self, hover_points: int = 4, hover_duration: float = 10.0) -> bool:
        """Inspection mission with hovering at multiple points."""
        if not self.takeoff():
            return False
        
        try:
            self.start_video_recording("inspection.avi")
            
            # Create hover points in a square pattern
            points = [(100, 0), (0, 100), (-100, 0), (0, -100)][:hover_points]
            
            for i, (x, y) in enumerate(points):
                # Move to position
                self.go_xyz_speed(x, y, 0, 30)
                
                # Hover and record
                self.hover(hover_duration)
                self.save_photo(f"inspection_point_{i+1}.jpg")
                
                # Return to center
                self.go_xyz_speed(0, 0, 0, 30)
                time.sleep(2)
            
            self.stop_video_recording()
            return self.land()
            
        except Exception as e:
            self.logger.error(f"Inspection mission failed: {str(e)}")
            if self.is_flying:
                self.land()
            return False
    
    def _mission_demo_flight(self) -> bool:
        """Demonstration flight showing various capabilities."""
        if not self.takeoff():
            return False
        
        try:
            self.start_video_recording("demo_flight.avi")
            
            # Demo sequence
            self.hover(3)
            self.save_photo("demo_start.jpg")
            
            # Basic movements
            self.move_forward(100)
            self.rotate_clockwise(360)
            self.move_back(100)
            
            # Pattern flight
            self.fly_circle(radius=80, speed=25)
            
            # Flip (if height allows)
            height = self.drone.get_height()
            if height > 120:
                self.flip_forward()
            
            # Final photo
            self.save_photo("demo_end.jpg")
            
            self.stop_video_recording()
            return self.land()
            
        except Exception as e:
            self.logger.error(f"Demo flight failed: {str(e)}")
            if self.is_flying:
                self.land()
            return False
    
    def _check_flight_ready(self) -> bool:
        """Check if drone is ready for flight commands."""
        if not self.is_connected:
            self.logger.error("Not connected to drone")
            return False
        
        if not self.is_flying:
            self.logger.error("Drone must be flying to execute movement commands")
            return False
        
        # Check battery level
        battery = self.drone.get_battery()
        if battery < 10:
            self.logger.error(f"Battery too low for flight operations: {battery}%")
            return False
        
        return True
    
    def _log_action(self, action: str, data: Optional[Dict] = None):
        """Log flight actions for record keeping."""
        log_entry = {
            "timestamp": time.time(),
            "action": action,
            "data": data or {}
        }
        self.flight_log.append(log_entry)
    
    def get_flight_log(self) -> list:
        """Get the complete flight log."""
        return self.flight_log.copy()
    
    def clear_flight_log(self):
        """Clear the flight log."""
        self.flight_log.clear()
        self.logger.info("Flight log cleared")
    
    # Object Detection Methods
    def enable_detection(self, detection_type: str = None) -> bool:
        """
        Enable object detection.
        
        Args:
            detection_type: Specific type to enable (face, person, vehicle) or None for all
        
        Returns:
            bool: True if successful
        """
        try:
            self.detection_enabled = True
            self.object_detector.detection_enabled = True
            
            if detection_type:
                self.object_detector.detection_types[detection_type] = True
                self.logger.info(f"{self.logger_prefix}Enabled {detection_type} detection")
            else:
                # Enable common detection types
                self.object_detector.detection_types['face'] = True
                self.object_detector.detection_types['person'] = True
                self.logger.info(f"{self.logger_prefix}Enabled all object detection")
            
            return True
        except Exception as e:
            self.logger.error(f"Failed to enable detection: {str(e)}")
            return False
    
    def disable_detection(self) -> bool:
        """Disable object detection."""
        try:
            self.detection_enabled = False
            self.object_detector.detection_enabled = False
            self.follow_mode = False
            self.logger.info(f"{self.logger_prefix}Object detection disabled")
            return True
        except Exception as e:
            self.logger.error(f"Failed to disable detection: {str(e)}")
            return False
    
    def start_follow_mode(self, target_type: str = 'face') -> bool:
        """
        Start follow mode to track detected objects.
        
        Args:
            target_type: Type of object to follow (face, person, vehicle)
        
        Returns:
            bool: True if successful
        """
        if not self.is_flying:
            self.logger.error("Must be flying to use follow mode")
            return False
        
        if target_type not in self.object_detector.detection_types:
            self.logger.error(f"Invalid target type: {target_type}")
            return False
        
        try:
            self.follow_mode = True
            self.follow_target = target_type
            self.enable_detection(target_type)
            self.logger.info(f"{self.logger_prefix}Follow mode started for {target_type}")
            return True
        except Exception as e:
            self.logger.error(f"Failed to start follow mode: {str(e)}")
            return False
    
    def stop_follow_mode(self) -> bool:
        """Stop follow mode."""
        try:
            self.follow_mode = False
            self.follow_target = None
            self.logger.info(f"{self.logger_prefix}Follow mode stopped")
            return True
        except Exception as e:
            self.logger.error(f"Failed to stop follow mode: {str(e)}")
            return False
    
    def get_detection_status(self) -> Dict[str, Any]:
        """Get current detection status and statistics."""
        return {
            'detection_enabled': self.detection_enabled,
            'follow_mode': self.follow_mode,
            'follow_target': self.follow_target,
            'last_detections': self.last_detections,
            'detector_stats': self.object_detector.get_detection_stats()
        }
    
    def _execute_follow_behavior(self, detected_objects: List[Dict]):
        """
        Execute follow behavior based on detected objects with safety limits.
        
        Args:
            detected_objects: List of detected objects with bbox and confidence
        """
        if not detected_objects or not self.is_flying:
            return
        
        # Safety check: Ensure video stream is active
        if not self.video_stream:
            self.logger.warning("Video stream required for follow mode")
            self.stop_follow_mode()
            return
        
        # Check battery level for safety
        try:
            battery = self.drone.get_battery()
            if battery < 20:
                self.logger.warning(f"Battery too low for follow mode: {battery}%")
                self.stop_follow_mode()
                return
        except Exception:
            pass  # Continue if battery check fails
        
        try:
            # Get the most confident detection
            target = max(detected_objects, key=lambda x: x.get('confidence', 0))
            bbox = target['bbox']
            x, y, w, h = bbox
            
            # Safety: Minimum confidence threshold
            if target.get('confidence', 0) < 0.6:
                self.logger.debug("Detection confidence too low for follow")
                return
            
            # Calculate center of detected object
            center_x = x + w // 2
            center_y = y + h // 2
            
            # Assume frame size (typical for Tello)
            frame_width = 960
            frame_height = 720
            
            # Calculate how far the object is from frame center
            frame_center_x = frame_width // 2
            frame_center_y = frame_height // 2
            
            offset_x = center_x - frame_center_x
            offset_y = center_y - frame_center_y
            
            # Movement thresholds and limits
            move_threshold = 100
            max_move_distance = 30  # Safety limit
            min_move_distance = 10  # Minimum meaningful movement
            
            # Rate limiting: Don't move too frequently
            current_time = time.time()
            if not hasattr(self, '_last_follow_move_time'):
                self._last_follow_move_time = 0
            
            if current_time - self._last_follow_move_time < 0.5:  # 0.5 second minimum between moves
                return
            
            movement_made = False
            
            # Adjust drone position to keep object centered (with safety limits)
            if abs(offset_x) > move_threshold:
                direction = "right" if offset_x > 0 else "left"
                distance = max(min_move_distance, min(max_move_distance, abs(offset_x) // 10))
                self.move(direction, distance)
                movement_made = True
            
            if abs(offset_y) > move_threshold:
                direction = "down" if offset_y > 0 else "up"
                distance = max(min_move_distance, min(max_move_distance, abs(offset_y) // 10))
                self.move(direction, distance)
                movement_made = True
            
            # Maintain safe distance based on object size
            object_size = w * h
            if object_size < 3000:  # Object too far - move closer (conservative)
                self.move("forward", 15)
                movement_made = True
            elif object_size > 30000:  # Object too close - back away
                self.move("back", 20)
                movement_made = True
            
            # Update last move time if movement was made
            if movement_made:
                self._last_follow_move_time = current_time
                self.logger.debug(f"Follow adjustment: center=({center_x},{center_y}), size={object_size}")
                
        except Exception as e:
            self.logger.error(f"Follow behavior error: {str(e)}")
            # Safety: Stop follow mode on repeated errors
            if not hasattr(self, '_follow_error_count'):
                self._follow_error_count = 0
            self._follow_error_count += 1
            if self._follow_error_count > 5:
                self.logger.error("Too many follow errors, stopping follow mode")
                self.stop_follow_mode()
    
    def detect_and_photo(self, target_type: str = 'face', max_photos: int = 5) -> bool:
        """
        Automatically take photos when objects are detected.
        
        Args:
            target_type: Type of object to detect for photos
            max_photos: Maximum number of photos to take
        
        Returns:
            bool: True if successful
        """
        if not self.is_flying:
            self.logger.error("Must be flying to use detection photography")
            return False
        
        try:
            self.enable_detection(target_type)
            photos_taken = 0
            start_time = time.time()
            timeout = 30  # 30 second timeout
            
            self.logger.info(f"{self.logger_prefix}Starting detection photography for {target_type}")
            
            while photos_taken < max_photos and (time.time() - start_time) < timeout:
                if target_type in self.last_detections and self.last_detections[target_type]:
                    # Object detected, take photo
                    photo_filename = f"detection_{target_type}_{photos_taken+1}_{int(time.time())}.jpg"
                    if self.take_photo(photo_filename):
                        photos_taken += 1
                        self.logger.info(f"{self.logger_prefix}Detection photo {photos_taken}/{max_photos}")
                        time.sleep(2)  # Wait between photos
                
                time.sleep(0.5)  # Check every 0.5 seconds
            
            self.logger.info(f"{self.logger_prefix}Detection photography complete: {photos_taken} photos")
            return True
            
        except Exception as e:
            self.logger.error(f"Detection photography failed: {str(e)}")
            return False


class ObjectDetector:
    """
    Object detection system for drone camera feed.
    Supports multiple detection types: faces, people, vehicles, etc.
    """
    
    def __init__(self):
        """Initialize object detection with classifiers and AI models."""
        self.detection_enabled = False
        self.ai_detection_enabled = False  # New AI detection mode
        self.detection_types = {
            'face': True,
            'person': True, 
            'vehicle': False,
            'eyes': False
        }
        
        # Detection statistics
        self.detection_counts = {dtype: 0 for dtype in self.detection_types}
        self.detection_history = []
        
        # Initialize OpenCV classifiers
        self._load_classifiers()
        
        # Initialize TensorFlow Lite model
        self.ai_detection_enabled = False  # Default to OpenCV mode
        self._load_tensorflow_model()
        
        # Detection visualization settings
        self.show_labels = True
        self.show_confidence = True
        
        # Colors in BGR format (OpenCV uses BGR by default)
        self.detection_colors = {
            'face': (0, 255, 0),     # Green (BGR)
            'person': (255, 0, 0),   # Blue (BGR) 
            'vehicle': (0, 0, 255),  # Red (BGR)
            'eyes': (255, 255, 0),   # Cyan (BGR)
            'ai_object': (255, 128, 0)  # Orange for AI detections (BGR)
        }
    
    def _load_classifiers(self):
        """Load OpenCV cascade classifiers."""
        try:
            # Face detection using Haar cascades (handle different OpenCV versions)
            try:
                if hasattr(cv2, 'data'):
                    face_cascade_path = cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
                    eye_cascade_path = cv2.data.haarcascades + 'haarcascade_eye.xml'
                else:
                    # Fallback for OpenCV versions without cv2.data
                    face_cascade_path = 'haarcascade_frontalface_default.xml'
                    eye_cascade_path = 'haarcascade_eye.xml'
            except Exception:
                face_cascade_path = 'haarcascade_frontalface_default.xml'
                eye_cascade_path = 'haarcascade_eye.xml'
            
            self.face_cascade = cv2.CascadeClassifier(face_cascade_path)
            self.eye_cascade = cv2.CascadeClassifier(eye_cascade_path)
            
            # Person detection using HOG
            try:
                self.hog = cv2.HOGDescriptor()
                if hasattr(cv2.HOGDescriptor, 'getDefaultPeopleDetector'):
                    detector = cv2.HOGDescriptor.getDefaultPeopleDetector()
                    self.hog.setSVMDetector(detector)
                else:
                    # Disable HOG if not available
                    self.hog = None
            except Exception:
                self.hog = None
            
            # Vehicle detection (simplified using contours)
            self.vehicle_detector_available = True
            
        except Exception as e:
            print(f"Warning: Some classifiers failed to load: {e}")
    
    def _load_tensorflow_model(self):
        """Load TensorFlow Lite model for AI object detection."""
        if not TENSORFLOW_AVAILABLE:
            self.tf_interpreter = None
            self.tf_labels = []
            print("TensorFlow not available - AI detection disabled")
            return
        
        try:
            # Load TensorFlow Lite model
            model_path = "models/detect.tflite"
            if os.path.exists(model_path):
                self.tf_interpreter = tf.lite.Interpreter(model_path=model_path)
                self.tf_interpreter.allocate_tensors()
                
                # Get input and output tensors
                self.tf_input_details = self.tf_interpreter.get_input_details()
                self.tf_output_details = self.tf_interpreter.get_output_details()
                
                # Load labels
                labels_path = "models/labelmap.txt"
                if os.path.exists(labels_path):
                    with open(labels_path, 'r') as f:
                        self.tf_labels = [line.strip() for line in f.readlines()]
                else:
                    self.tf_labels = []
                
                print(f"✅ TensorFlow Lite model loaded with {len(self.tf_labels)} object classes")
            else:
                self.tf_interpreter = None
                self.tf_labels = []
                print(f"Warning: TensorFlow model not found at {model_path}")
                
        except Exception as e:
            self.tf_interpreter = None
            self.tf_labels = []
            print(f"Warning: Failed to load TensorFlow model: {e}")
    
    def detect_objects(self, frame: np.ndarray) -> Tuple[np.ndarray, Dict[str, List]]:
        """
        Detect objects in the given frame.
        
        Args:
            frame: Input video frame
            
        Returns:
            Tuple of (annotated_frame, detections_dict)
        """
        if not self.detection_enabled:
            return frame, {}
        
        detections = {dtype: [] for dtype in self.detection_types}
        annotated_frame = frame.copy()
        
        # Convert to grayscale for cascade classifiers
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        
        # Face detection
        if self.detection_types['face']:
            faces = self.face_cascade.detectMultiScale(gray, 1.3, 5)
            for (x, y, w, h) in faces:
                detections['face'].append({'bbox': (x, y, w, h), 'confidence': 0.85})
                if self.show_labels:
                    cv2.rectangle(annotated_frame, (x, y), (x+w, y+h), self.detection_colors['face'], 2)
                    cv2.putText(annotated_frame, 'Face', (x, y-10), cv2.FONT_HERSHEY_SIMPLEX, 0.7, self.detection_colors['face'], 2)
        
        # Eye detection (within faces)
        if self.detection_types['eyes'] and detections['face']:
            for face_det in detections['face']:
                x, y, w, h = face_det['bbox']
                roi_gray = gray[y:y+h, x:x+w]
                roi_color = annotated_frame[y:y+h, x:x+w]
                eyes = self.eye_cascade.detectMultiScale(roi_gray)
                for (ex, ey, ew, eh) in eyes:
                    detections['eyes'].append({'bbox': (x+ex, y+ey, ew, eh), 'confidence': 0.80})
                    if self.show_labels:
                        cv2.rectangle(roi_color, (ex, ey), (ex+ew, ey+eh), self.detection_colors['eyes'], 2)
        
        # Person detection using HOG
        if self.detection_types['person'] and self.hog is not None:
            try:
                people, weights = self.hog.detectMultiScale(gray, winStride=(8,8), padding=(32,32), scale=1.05)
                for i, (x, y, w, h) in enumerate(people):
                    if len(weights) > i:
                        confidence = float(weights[i]) if hasattr(weights[i], '__iter__') else float(weights[i])
                    else:
                        confidence = 0.5
                    if confidence > 0.5:  # Confidence threshold
                        detections['person'].append({'bbox': (x, y, w, h), 'confidence': confidence})
                        if self.show_labels:
                            cv2.rectangle(annotated_frame, (x, y), (x+w, y+h), self.detection_colors['person'], 2)
                            cv2.putText(annotated_frame, f'Person {confidence:.2f}', (x, y-10), cv2.FONT_HERSHEY_SIMPLEX, 0.7, self.detection_colors['person'], 2)
            except Exception:
                pass  # HOG detection can be sensitive to frame size
        
        # Vehicle detection (simplified using edge detection and contours)
        if self.detection_types['vehicle']:
            self._detect_vehicles(gray, annotated_frame, detections)
        
        # Update detection statistics
        self._update_detection_stats(detections)
        
        return annotated_frame, detections
    
    def _detect_objects_ai(self, frame: np.ndarray) -> Tuple[np.ndarray, Dict[str, List]]:
        """AI-powered object detection using TensorFlow Lite."""
        detections = {'ai_objects': []}
        annotated_frame = frame.copy()
        
        try:
            # Prepare input image
            input_shape = self.tf_input_details[0]['shape']
            height, width = input_shape[1], input_shape[2]
            
            # Resize and normalize the frame
            resized_frame = cv2.resize(frame, (width, height))
            input_data = np.expand_dims(resized_frame, axis=0)
            
            # Normalize to [0, 1] if model expects float input
            if self.tf_input_details[0]['dtype'] == np.float32:
                input_data = input_data.astype(np.float32) / 255.0
            else:
                input_data = input_data.astype(np.uint8)
            
            # Run inference
            self.tf_interpreter.set_tensor(self.tf_input_details[0]['index'], input_data)
            self.tf_interpreter.invoke()
            
            # Get detection results
            boxes = self.tf_interpreter.get_tensor(self.tf_output_details[0]['index'])[0]  # Bounding box coordinates
            classes = self.tf_interpreter.get_tensor(self.tf_output_details[1]['index'])[0]  # Class indices
            scores = self.tf_interpreter.get_tensor(self.tf_output_details[2]['index'])[0]  # Confidence scores
            
            # Process detections
            frame_height, frame_width = frame.shape[:2]
            
            for i in range(len(scores)):
                if scores[i] > 0.5:  # Confidence threshold
                    # Convert normalized coordinates to pixel coordinates
                    ymin, xmin, ymax, xmax = boxes[i]
                    x = int(xmin * frame_width)
                    y = int(ymin * frame_height)
                    w = int((xmax - xmin) * frame_width)
                    h = int((ymax - ymin) * frame_height)
                    
                    # Get class label
                    class_id = int(classes[i])
                    label = self.tf_labels[class_id] if class_id < len(self.tf_labels) else f"Class {class_id}"
                    confidence = scores[i]
                    
                    # Store detection
                    detections['ai_objects'].append({
                        'bbox': (x, y, w, h),
                        'confidence': float(confidence),
                        'label': label,
                        'class_id': class_id
                    })
                    
                    # Draw detection on frame
                    if self.show_labels:
                        cv2.rectangle(annotated_frame, (x, y), (x+w, y+h), self.detection_colors['ai_object'], 2)
                        label_text = f"{label}: {confidence:.2f}"
                        cv2.putText(annotated_frame, label_text, (x, y-10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, self.detection_colors['ai_object'], 2)
            
            # Update detection statistics
            self._update_detection_stats(detections)
            
        except Exception as e:
            print(f"AI detection error: {e}")
            # Fallback to OpenCV detection
            return self._detect_objects_opencv(frame)
        
        return annotated_frame, detections
    
    def set_ai_detection(self, enabled: bool) -> bool:
        """Toggle AI detection mode."""
        if not hasattr(self, 'tf_interpreter') or self.tf_interpreter is None:
            return False  # AI detection not available
        
        self.ai_detection_enabled = enabled
        return True
    
    def get_ai_detection_status(self) -> bool:
        """Get current AI detection status."""
        return getattr(self, 'ai_detection_enabled', False)
    
    def _detect_vehicles(self, gray: np.ndarray, annotated_frame: np.ndarray, detections: Dict):
        """Simplified vehicle detection using contour analysis."""
        try:
            # Edge detection
            edges = cv2.Canny(gray, 50, 150)
            contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            
            for contour in contours:
                area = cv2.contourArea(contour)
                if 1000 < area < 50000:  # Filter by size
                    x, y, w, h = cv2.boundingRect(contour)
                    aspect_ratio = w / h
                    if 1.2 < aspect_ratio < 3.0:  # Typical vehicle aspect ratio
                        detections['vehicle'].append({'bbox': (x, y, w, h), 'confidence': 0.60})
                        if self.show_labels:
                            cv2.rectangle(annotated_frame, (x, y), (x+w, y+h), self.detection_colors['vehicle'], 2)
                            cv2.putText(annotated_frame, 'Vehicle', (x, y-10), cv2.FONT_HERSHEY_SIMPLEX, 0.7, self.detection_colors['vehicle'], 2)
        except Exception:
            pass
    
    def _update_detection_stats(self, detections: Dict):
        """Update detection statistics and history."""
        for dtype, dets in detections.items():
            self.detection_counts[dtype] += len(dets)
        
        # Store detection history (last 100 frames)
        self.detection_history.append({
            'timestamp': time.time(),
            'detections': {dtype: len(dets) for dtype, dets in detections.items()}
        })
        
        if len(self.detection_history) > 100:
            self.detection_history.pop(0)
    
    def toggle_detection(self, detection_type: str = None) -> bool:
        """Toggle detection on/off for specific type or all."""
        if detection_type is None:
            self.detection_enabled = not self.detection_enabled
            return self.detection_enabled
        elif detection_type in self.detection_types:
            self.detection_types[detection_type] = not self.detection_types[detection_type]
            return self.detection_types[detection_type]
        return False
    
    def get_detection_stats(self) -> Dict:
        """Get detection statistics."""
        return {
            'enabled': self.detection_enabled,
            'types': self.detection_types.copy(),
            'counts': self.detection_counts.copy(),
            'recent_activity': len(self.detection_history)
        }