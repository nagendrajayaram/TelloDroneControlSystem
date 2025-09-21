#!/usr/bin/env python3
"""
Test script to demonstrate the Tello drone simulator.
This shows how to use the simulation mode with generated graphics.
"""

from drone_gui import DroneControlGUI


def main():
    print("🎬 Testing Tello Drone Simulator")
    print("=" * 50)

    # Create GUI instance in simulation mode
    gui = DroneControlGUI(simulation_mode=True)
    print("📹 Using generated simulation graphics")

    print()
    print("🎯 Features to test:")
    print("   • Drone connection and status")
    print("   • Flight controls (takeoff, land, movement)")
    print("   • Video stream with generated graphics")
    print("   • Voice commands and AI vision analysis")
    print("   • Object detection on simulated objects")
    print()
    print("✅ The simulation includes synthetic objects for testing:")
    print("   • Moving faces for face detection")
    print("   • People shapes for person detection")
    print("   • Vehicle shapes for object recognition")
    print("   • Dynamic environment for realistic testing")

    # Start the GUI
    gui.run()


if __name__ == "__main__":
    main()