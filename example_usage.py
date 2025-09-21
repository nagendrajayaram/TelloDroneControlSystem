#!/usr/bin/env python3
"""
Example usage of the Tello Drone Agent

This script demonstrates how to use the TelloDroneAgent programmatically
for automated drone operations.
"""

import time
from tello_drone_agent import TelloDroneAgent


def basic_flight_demo():
    """Demonstrate basic flight operations."""
    print("🚁 Tello Drone Agent - Basic Flight Demo")
    print("=" * 50)
    
    # Initialize the agent
    agent = TelloDroneAgent()
    
    try:
        # Connect to drone
        print("1. Connecting to drone...")
        if not agent.connect():
            print("❌ Failed to connect to drone. Exiting.")
            return
        
        # Check status
        print("2. Checking drone status...")
        status = agent.get_status()
        print(f"   Battery: {status['battery']}%")
        print(f"   Temperature: {status['temperature']}°C")
        
        if status['battery'] < 20:
            print("⚠️  Battery too low for flight demo")
            return
        
        # Start video stream
        print("3. Starting video stream...")
        agent.start_video_stream()
        time.sleep(2)  # Wait for stream to stabilize
        
        # Take off
        print("4. Taking off...")
        if not agent.takeoff():
            print("❌ Takeoff failed")
            return
        
        time.sleep(3)  # Hover for a moment
        
        # Take a photo
        print("5. Taking photo...")
        photo_file = agent.save_photo("demo_flight.jpg")
        print(f"   Photo saved: {photo_file}")
        
        # Perform basic movements
        print("6. Performing basic movements...")
        
        # Move forward
        print("   Moving forward 50cm...")
        agent.move_forward(50)
        time.sleep(2)
        
        # Rotate 360 degrees
        print("   Rotating 360 degrees...")
        agent.rotate_clockwise(360)
        time.sleep(3)
        
        # Move back to start
        print("   Moving back 50cm...")
        agent.move_back(50)
        time.sleep(2)
        
        # Land
        print("7. Landing...")
        agent.land()
        
        # Stop video
        print("8. Stopping video stream...")
        agent.stop_video_stream()
        
        # Show flight log
        print("9. Flight log:")
        log = agent.get_flight_log()
        for entry in log:
            action_time = time.strftime("%H:%M:%S", time.localtime(entry['timestamp']))
            print(f"   [{action_time}] {entry['action']}")
        
        print("\n✅ Demo completed successfully!")
        
    except Exception as e:
        print(f"❌ Demo failed: {e}")
        
    finally:
        # Always disconnect safely
        agent.disconnect()


def photo_mission_demo():
    """Demonstrate automated photo mission."""
    print("🚁 Tello Drone Agent - Photo Mission Demo")
    print("=" * 50)
    
    agent = TelloDroneAgent()
    
    try:
        # Connect and setup
        if not agent.connect():
            print("❌ Failed to connect")
            return
        
        agent.start_video_stream()
        time.sleep(2)
        
        if not agent.takeoff():
            print("❌ Takeoff failed")
            return
        
        # Photo mission: take photos from different angles
        positions = [
            ("center", 0, 0),
            ("left", -100, 0),
            ("right", 200, 0),
            ("back", -100, 100),
            ("center", 0, -100)
        ]
        
        for i, (name, x_move, y_move) in enumerate(positions, 1):
            print(f"Position {i}: {name}")
            
            if x_move != 0:
                if x_move > 0:
                    agent.move_right(abs(x_move))
                else:
                    agent.move_left(abs(x_move))
            
            if y_move != 0:
                if y_move > 0:
                    agent.move_back(abs(y_move))
                else:
                    agent.move_forward(abs(y_move))
            
            time.sleep(1)
            agent.save_photo(f"mission_photo_{i}_{name}.jpg")
            print(f"   📸 Photo {i} captured")
        
        # Return to center and land
        agent.land()
        agent.stop_video_stream()
        
        print("📷 Photo mission completed!")
        
    except Exception as e:
        print(f"❌ Mission failed: {e}")
        
    finally:
        agent.disconnect()


def status_monitoring_demo():
    """Demonstrate continuous status monitoring."""
    print("🚁 Tello Drone Agent - Status Monitoring Demo")
    print("=" * 50)
    
    agent = TelloDroneAgent()
    
    try:
        if not agent.connect():
            return
        
        print("Monitoring drone status for 30 seconds...")
        start_time = time.time()
        
        while time.time() - start_time < 30:
            status = agent.get_status()
            print(f"Battery: {status['battery']}% | "
                  f"Temp: {status['temperature']}°C | "
                  f"Height: {status['height']}cm")
            time.sleep(5)
        
        print("Monitoring completed")
        
    except Exception as e:
        print(f"❌ Monitoring failed: {e}")
        
    finally:
        agent.disconnect()


if __name__ == "__main__":
    print("Choose a demo:")
    print("1. Basic Flight Demo")
    print("2. Photo Mission Demo")
    print("3. Status Monitoring Demo")
    
    choice = input("Enter choice (1-3): ").strip()
    
    if choice == "1":
        basic_flight_demo()
    elif choice == "2":
        photo_mission_demo()
    elif choice == "3":
        status_monitoring_demo()
    else:
        print("Invalid choice")