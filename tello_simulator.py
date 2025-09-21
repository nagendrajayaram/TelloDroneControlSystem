"""
Tello Drone Simulator

A comprehensive simulator that mimics DJI Tello drone behavior for testing,
development, and training purposes without requiring actual hardware.
"""

import time
import random
import math
import numpy as np
import threading
from typing import Optional, Tuple
import logging


class SimulatedTello:
    """
    Simulated Tello drone that mimics real drone behavior.
    
    This simulator provides realistic responses for all Tello SDK commands,
    maintains virtual state (position, battery, etc.), and simulates
    flight physics and limitations.
    """
    
    def __init__(self):
        """Initialize the simulated drone with default state."""
        # Connection state
        self.connected = False
        self.host = "192.168.10.1"  # Simulated IP
        self.port = 8889
        
        # Flight state
        self.flying = False
        self.position = [0.0, 0.0, 0.0]  # x, y, z in cm
        self.rotation = 0.0  # degrees
        self.speed = 30  # cm/s
        
        # Battery simulation
        self.battery_level = random.randint(85, 100)  # Start with good battery
        self.battery_drain_rate = 0.1  # %/second when flying
        self.last_battery_update = time.time()
        
        # Environmental sensors
        self.temperature = random.randint(20, 35)  # Celsius
        self.height = 0  # cm above ground
        self.flight_time = 0  # seconds
        self.start_flight_time = None
        
        # Camera simulation
        self.camera_active = False
        self.recording = False
        
        # Physics simulation
        self.max_height = 1000  # cm
        self.max_distance = 500  # cm from home
        self.home_position = [0.0, 0.0, 0.0]
        
        # Error simulation (for realistic behavior) - Reduced for better testing
        self.error_probability = 0.001  # 0.1% chance of command failure (much more reliable)
        self.wind_effect = random.uniform(0.8, 1.2)  # Wind resistance factor
        
        # Logging
        self.logger = logging.getLogger("TelloSimulator")
        
        # Start battery drain simulation
        self.simulation_running = True
        self.simulation_thread = threading.Thread(target=self._simulation_loop, daemon=True)
        self.simulation_thread.start()
        
        self.logger.info("Tello Simulator initialized")
    
    def connect(self):
        """Simulate connection to drone."""
        time.sleep(0.5)  # Simulate connection delay
        
        # Simulate occasional connection failures
        if random.random() < 0.05:  # 5% failure rate
            self.logger.warning("Simulated connection failure")
            return False
        
        self.connected = True
        self.logger.info("Simulated drone connected")
        return True
    
    def end(self):
        """Simulate disconnection."""
        self.connected = False
        self.flying = False
        self.simulation_running = False
        self.logger.info("Simulated drone disconnected")
    
    def takeoff(self):
        """Simulate takeoff."""
        if not self.connected:
            raise Exception("Not connected")
        
        if self.flying:
            self.logger.warning("Already flying")
            return
        
        if self.battery_level < 20:
            raise Exception(f"Battery too low: {self.battery_level}%")
        
        # Simulate takeoff time and movement
        time.sleep(2)
        self.flying = True
        self.height = 80 + random.randint(-10, 10)  # Realistic takeoff height
        self.position[2] = self.height
        self.start_flight_time = time.time()
        self.flight_time = 0
        
        self.logger.info(f"Takeoff complete - Height: {self.height}cm")
    
    def land(self):
        """Simulate landing."""
        if not self.connected:
            raise Exception("Not connected")
        
        if not self.flying:
            self.logger.warning("Already on ground")
            return
        
        # Simulate command failure (much lower probability now)
        if random.random() < self.error_probability:
            raise Exception("Landing command failed")
        
        # Simulate landing time
        time.sleep(2)
        self.flying = False
        self.height = 0
        self.position[2] = 0
        
        if self.start_flight_time:
            self.flight_time = int(time.time() - self.start_flight_time)
        
        self.logger.info("Landing complete")
    
    def emergency(self):
        """Simulate emergency stop."""
        self.flying = False
        self.height = 0
        self.position[2] = 0
        self.logger.warning("Emergency stop activated!")
    
    def move_left(self, distance: int):
        """Simulate moving left."""
        self._move_command("left", distance, (-distance, 0, 0))
    
    def move_right(self, distance: int):
        """Simulate moving right."""
        self._move_command("right", distance, (distance, 0, 0))
    
    def move_forward(self, distance: int):
        """Simulate moving forward."""
        rad = math.radians(self.rotation)
        dx = distance * math.sin(rad)
        dy = distance * math.cos(rad)
        self._move_command("forward", distance, (dx, dy, 0))
    
    def move_back(self, distance: int):
        """Simulate moving back."""
        rad = math.radians(self.rotation)
        dx = -distance * math.sin(rad)
        dy = -distance * math.cos(rad)
        self._move_command("back", distance, (dx, dy, 0))
    
    def move_up(self, distance: int):
        """Simulate moving up."""
        self._move_command("up", distance, (0, 0, distance))
    
    def move_down(self, distance: int):
        """Simulate moving down."""
        self._move_command("down", distance, (0, 0, -distance))
    
    def _move_command(self, direction: str, distance: int, delta: Tuple[float, float, float]):
        """Helper for movement simulation."""
        if not self.connected or not self.flying:
            raise Exception("Not flying")
        
        # Simulate command failure
        if random.random() < self.error_probability:
            raise Exception(f"Movement command failed - {direction}")
        
        # Apply wind effect
        actual_delta = [d * self.wind_effect for d in delta]
        
        # Check boundaries
        new_pos = [self.position[i] + actual_delta[i] for i in range(3)]
        
        # Height limits
        if new_pos[2] < 30:  # Minimum safe height
            new_pos[2] = 30
        elif new_pos[2] > self.max_height:
            new_pos[2] = self.max_height
        
        # Distance from home limit
        home_distance = math.sqrt((new_pos[0] - self.home_position[0])**2 + 
                                 (new_pos[1] - self.home_position[1])**2)
        if home_distance > self.max_distance:
            # Scale back to maximum distance
            scale = self.max_distance / home_distance
            new_pos[0] = self.home_position[0] + (new_pos[0] - self.home_position[0]) * scale
            new_pos[1] = self.home_position[1] + (new_pos[1] - self.home_position[1]) * scale
        
        # Simulate movement time
        move_time = distance / self.speed
        time.sleep(min(move_time, 5))  # Cap at 5 seconds for simulation
        
        # Update position
        self.position = new_pos
        self.height = int(new_pos[2])
        
        self.logger.info(f"Moved {direction} {distance}cm - New position: ({int(new_pos[0])}, {int(new_pos[1])}, {int(new_pos[2])})")
    
    def rotate_clockwise(self, degrees: int):
        """Simulate clockwise rotation."""
        self._rotate_command("clockwise", degrees, degrees)
    
    def rotate_counter_clockwise(self, degrees: int):
        """Simulate counter-clockwise rotation."""
        self._rotate_command("counter_clockwise", degrees, -degrees)
    
    def _rotate_command(self, direction: str, degrees: int, delta: float):
        """Helper for rotation simulation."""
        if not self.connected:
            raise Exception("Not connected")
        
        if not self.flying:
            self.logger.warning("Cannot rotate - not flying")
            raise Exception("Not flying")
        
        # Simulate command failure (much lower probability now)
        if random.random() < self.error_probability:
            raise Exception(f"Rotation command failed - {direction}")
        
        # Simulate rotation time
        rotation_time = degrees / 90  # ~1 second per 90 degrees
        time.sleep(min(rotation_time, 3))
        
        self.rotation = (self.rotation + delta) % 360
        self.logger.info(f"Rotated {direction} {degrees}° - New heading: {int(self.rotation)}°")
    
    def flip_left(self):
        """Simulate left flip."""
        self._flip_command("left")
    
    def flip_right(self):
        """Simulate right flip."""
        self._flip_command("right")
    
    def flip_forward(self):
        """Simulate forward flip."""
        self._flip_command("forward")
    
    def flip_back(self):
        """Simulate backward flip."""
        self._flip_command("back")
    
    def _flip_command(self, direction: str):
        """Helper for flip simulation."""
        if not self.connected or not self.flying:
            raise Exception("Not flying")
        
        if self.height < 100:
            raise Exception(f"Height too low for flip: {self.height}cm")
        
        # Simulate flip time and slight position change
        time.sleep(2)
        self.position[0] += random.randint(-10, 10)
        self.position[1] += random.randint(-10, 10)
        
        self.logger.info(f"Flip {direction} completed")
    
    def set_speed(self, speed: int):
        """Set movement speed."""
        if not self.connected:
            raise Exception("Not connected")
        
        self.speed = max(10, min(100, speed))
        self.logger.info(f"Speed set to {self.speed} cm/s")
    
    def go_xyz_speed(self, x: int, y: int, z: int, speed: int):
        """Simulate movement to specific coordinates."""
        if not self.connected or not self.flying:
            raise Exception("Not flying")
        
        # Calculate movement distance and time
        distance = math.sqrt(x**2 + y**2 + z**2)
        move_time = distance / speed
        
        # Simulate movement
        time.sleep(min(move_time, 8))
        
        # Update position (relative movement)
        self.position[0] += x * self.wind_effect
        self.position[1] += y * self.wind_effect
        self.position[2] = max(30, min(self.max_height, self.position[2] + z))
        self.height = int(self.position[2])
        
        self.logger.info(f"Moved to relative coordinates ({x}, {y}, {z})")
    
    def streamon(self):
        """Simulate starting video stream."""
        if not self.connected:
            raise Exception("Not connected")
        
        self.camera_active = True
        time.sleep(0.5)  # Simulate startup time
        self.logger.info("Video stream started")
    
    def streamoff(self):
        """Simulate stopping video stream."""
        self.camera_active = False
        self.recording = False
        self.logger.info("Video stream stopped")
    
    def get_frame_read(self):
        """Simulate frame reader for video."""
        return SimulatedFrameReader()
    
    def get_battery(self) -> int:
        """Get current battery level."""
        return max(0, int(self.battery_level))
    
    def get_temperature(self) -> int:
        """Get current temperature."""
        return self.temperature + random.randint(-2, 2)  # Small variations
    
    def get_height(self) -> int:
        """Get current height above ground."""
        return self.height + random.randint(-2, 2)  # Sensor noise
    
    def get_speed_x(self) -> int:
        """Get speed in X direction."""
        return random.randint(-5, 5) if self.flying else 0
    
    def get_flight_time(self) -> int:
        """Get total flight time."""
        if self.flying and self.start_flight_time:
            return int(time.time() - self.start_flight_time)
        return self.flight_time
    
    def query_speed(self) -> int:
        """Get current speed setting."""
        return self.speed
    
    def _simulation_loop(self):
        """Background simulation loop for realistic behavior."""
        while self.simulation_running:
            try:
                current_time = time.time()
                
                # Update battery drain when flying
                if self.flying and self.connected:
                    time_diff = current_time - self.last_battery_update
                    drain = self.battery_drain_rate * time_diff
                    self.battery_level = max(0, self.battery_level - drain)
                    
                    # Force landing if battery critical
                    if self.battery_level < 5:
                        self.logger.warning("Critical battery - Auto landing!")
                        self.land()
                
                # Small temperature variations
                if random.random() < 0.1:  # 10% chance per second
                    self.temperature += random.choice([-1, 1])
                    self.temperature = max(15, min(45, self.temperature))
                
                self.last_battery_update = current_time
                time.sleep(1)  # Update every second
                
            except Exception as e:
                self.logger.error(f"Simulation error: {e}")
                time.sleep(1)


class SimulatedFrameReader:
    """Simulated frame reader for video stream."""
    
    def __init__(self):
        self.frame_count = 0
        
    @property
    def frame(self):
        """Generate a simulated camera frame."""
        import cv2
        import numpy as np
        
        self.frame_count += 1
        
        # Generate simulation frame
        # Create a 720p frame with some visual content
        height, width = 720, 960
        frame = np.zeros((height, width, 3), dtype=np.uint8)
        
        # Add some visual elements to simulate a camera view
        # Sky gradient
        for y in range(height//3):
            intensity = int(100 + (y / (height//3)) * 100)
            frame[y, :] = [intensity, intensity, 255]  # Blue sky
        
        # Ground
        for y in range(height//3, height):
            intensity = int(50 + random.randint(0, 30))
            frame[y, :] = [intensity, intensity + 20, intensity]  # Brownish ground
        
        # Add some "terrain" features
        for i in range(10):
            x = random.randint(0, width-100)
            y = random.randint(height//2, height-50)
            cv2.rectangle(frame, (x, y), (x+50, y+30), (0, 100, 0), -1)  # Green "trees"
        
        # Add synthetic objects for detection testing
        import time
        sim_time = time.time()
        
        # Simulate a moving face (changes position over time for dynamic testing)
        face_x = int(400 + 100 * np.sin(sim_time * 0.5))
        face_y = int(200 + 50 * np.cos(sim_time * 0.3))
        # Draw face-like oval
        cv2.ellipse(frame, (face_x, face_y), (40, 50), 0, 0, 360, (220, 180, 140), -1)  # Face color
        cv2.ellipse(frame, (face_x-15, face_y-10), (5, 8), 0, 0, 360, (0, 0, 0), -1)  # Left eye
        cv2.ellipse(frame, (face_x+15, face_y-10), (5, 8), 0, 0, 360, (0, 0, 0), -1)  # Right eye
        cv2.ellipse(frame, (face_x, face_y+10), (8, 4), 0, 0, 360, (150, 100, 100), -1)  # Mouth
        
        # Simulate a person shape (rectangle with head)
        person_x = int(200 + 80 * np.sin(sim_time * 0.7))
        person_y = int(height//2 + 100)
        cv2.rectangle(frame, (person_x, person_y), (person_x+30, person_y+80), (100, 150, 200), -1)  # Body
        cv2.circle(frame, (person_x+15, person_y-20), 20, (220, 180, 140), -1)  # Head
        
        # Simulate a vehicle (rectangular with wheels)
        vehicle_x = int(600 + 150 * np.sin(sim_time * 0.2))
        vehicle_y = int(height//2 + 150)
        cv2.rectangle(frame, (vehicle_x, vehicle_y), (vehicle_x+120, vehicle_y+40), (80, 80, 80), -1)  # Car body
        cv2.circle(frame, (vehicle_x+20, vehicle_y+40), 15, (50, 50, 50), -1)  # Left wheel
        cv2.circle(frame, (vehicle_x+100, vehicle_y+40), 15, (50, 50, 50), -1)  # Right wheel
        cv2.rectangle(frame, (vehicle_x+20, vehicle_y-15), (vehicle_x+100, vehicle_y), (150, 200, 250), -1)  # Windshield
        
        # Add overlay text
        text = f"TELLO SIM - Frame {self.frame_count}"
        cv2.putText(frame, text, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
        
        # Add detection indicator
        cv2.putText(frame, "OBJECTS FOR DETECTION", (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
        
        # Add timestamp
        timestamp = time.strftime("%H:%M:%S")
        cv2.putText(frame, timestamp, (width-150, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
        
        return frame


def create_simulated_tello():
    """Factory function to create a simulated Tello drone."""
    return SimulatedTello()