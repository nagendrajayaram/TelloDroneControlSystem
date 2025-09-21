# AI-Powered Tello Drone Control System

**Advanced drone control system with AI-powered object detection, natural language commands, and comprehensive flight management capabilities.**

[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://python.org)
[![TensorFlow](https://img.shields.io/badge/TensorFlow-2.20+-orange.svg)](https://tensorflow.org)
[![OpenCV](https://img.shields.io/badge/OpenCV-4.12+-green.svg)](https://opencv.org)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

## 🌟 Features

### 🤖 Artificial Intelligence
- **TensorFlow Object Detection**: Real-time detection of 91+ object classes
- **Natural Language Commands**: Control drone using plain English commands
- **AI Mission Planner**: Automatically generate optimal flight paths
- **Smart Target Following**: AI-powered object tracking and following

### 🎮 User Interface
- **Modern GUI**: Contemporary dark theme with intuitive controls
- **Real-time Video Display**: Live drone camera feed with detection overlays
- **Comprehensive Flight Controls**: Manual and automated flight options
- **Status Monitoring**: Real-time telemetry and system status

### 🎙️ Voice & Audio
- **Voice Commands**: Hands-free drone control using speech recognition
- **Text-to-Speech**: Audio feedback and status announcements
- **Multi-language Support**: Multiple language options available

### 📹 Camera & Recording
- **Live Video Stream**: Real-time video from drone camera
- **360° Panorama Mode**: Automated panoramic photography
- **Photo/Video Capture**: High-quality media capture during flight

### 🛡️ Safety Features
- **Emergency Stop**: Immediate drone shutdown capability
- **Battery Monitoring**: Real-time battery level tracking
- **Flight Limits**: Configurable safety boundaries
- **Auto-Landing**: Automatic landing on low battery

## 🚁 Supported Drones

- **DJI Tello Standard**: Full compatibility
- **DJI Tello EDU**: Enhanced features support
- **Simulation Mode**: No physical drone required for testing

## 📋 Requirements

### System Requirements
- **Operating System**: Windows 10+, macOS 10.15+, or Linux (Ubuntu 18.04+)
- **Python**: Version 3.11 or higher
- **RAM**: Minimum 8GB (16GB recommended for AI features)
- **Storage**: 2GB free space
- **Network**: Wi-Fi capability for drone connection

### Dependencies
- TensorFlow 2.20+
- OpenCV 4.12+
- djitellopy 2.5+
- Azure OpenAI API (for natural language commands)

## 🔧 Installation

### Method 1: Quick Setup
```bash
# Clone the repository
git clone https://github.com/yourusername/TelloDroneControlSystem.git
cd TelloDroneControlSystem

# Create virtual environment
python -m venv drone_env
# Windows
drone_env\Scripts\activate
# macOS/Linux
source drone_env/bin/activate

# Install dependencies
pip install -r requirements.txt

# Set up environment variables
cp .env.example .env
# Edit .env with your API keys

# Run the application
python drone_gui.py
```

### Method 2: Manual Installation
```bash
# Install core dependencies
pip install djitellopy>=2.5.0
pip install tensorflow>=2.20.0
pip install opencv-python>=4.12.0.88
pip install pillow>=11.3.0
pip install numpy>=2.2.6
pip install openai>=1.107.3
# ... see full requirements in pyproject.toml
```

## 🚀 Quick Start

### Simulation Mode (No Drone Required)
1. Launch the application: `python drone_gui.py`
2. System automatically starts in simulation mode
3. Try natural language commands: *"take off and hover"*
4. Test AI detection using your webcam
5. Experiment with voice commands and manual controls

### Real Drone Operation
1. Power on your Tello drone
2. Connect to Tello Wi-Fi network (TELLO-XXXXXX)
3. Launch the application: `python drone_gui.py`
4. Click "Connect" to establish connection
5. Start with simple commands: *"take off"*

## 🎯 Usage Examples

### Natural Language Commands
```
"Take off, fly forward 2 meters, turn right 90 degrees, take a photo, then come back and land"

"Start recording video, fly in a circle around the yard, then stop recording and land"

"If you see a person, follow them for 30 seconds then return home"

"Scan the room for objects and tell me what you find"
```

### Voice Commands
- Activate microphone and speak naturally
- Supported languages: English, Spanish, French, German, Chinese
- Clear pronunciation recommended for best results

### AI Object Detection
- **Toggle Detection Mode**: Switch between OpenCV and AI detection
- **91+ Object Classes**: People, vehicles, animals, household items, etc.
- **Real-time Processing**: <100ms inference time on CPU
- **Confidence Scoring**: Adjustable detection thresholds

## 📖 Documentation

Complete documentation is available in multiple formats:

- **[User Guide (PDF)](TELLO_DRONE_CONTROL_DOCUMENTATION.pdf)** - Comprehensive 84-page guide
- **[Technical Manual (Word)](TELLO_DRONE_CONTROL_DOCUMENTATION.docx)** - Editable documentation
- **[Developer Reference (Markdown)](TELLO_DRONE_CONTROL_DOCUMENTATION.md)** - Full technical reference

## 🏗️ Project Structure

```
TelloDroneControlSystem/
├── drone_gui.py                 # Main GUI application
├── tello_drone_agent.py         # Core drone control logic
├── tello_simulator.py           # Simulation system
├── models/                      # AI detection models
│   ├── detect.tflite           # TensorFlow Lite model
│   └── labelmap.txt            # Object class labels
├── logs/                       # System logs
├── attached_assets/            # Media assets
├── pyproject.toml              # Project configuration
├── requirements.txt            # Python dependencies
└── README.md                   # This file
```

## 🔧 Configuration

### Environment Variables
Create a `.env` file with:
```env
AZURE_OPENAI_API_KEY=your_azure_openai_key_here
AZURE_OPENAI_DEPLOYMENT_NAME=your_deployment_name
AZURE_OPENAI_ENDPOINT=your_azure_endpoint
```

### Application Settings
Configure detection sensitivity, flight limits, and other preferences through the GUI settings panel.

## 🛠️ Development

### Running Tests
```bash
# Run simulation tests
python test_video_simulator.py

# Test CLI interface
python drone_cli.py --help
```

### Building Executables
```bash
# Build Windows executable
python build_windows_app.py

# Build GUI application
python build_gui_app.py
```

## 🐛 Troubleshooting

### Common Issues

**Connection Problems**
- Ensure drone is powered and in pairing mode
- Check Wi-Fi connection to Tello network
- Verify no firewall blocking UDP ports 8889/8890

**AI Detection Issues**
- Verify TensorFlow installation
- Check lighting conditions
- Update graphics drivers
- Ensure models are present in `models/` directory

**Performance Issues**
- Close unnecessary applications
- Use wired internet connection
- Optimize detection settings
- Check system resource usage

For detailed troubleshooting, see the [Complete Documentation](TELLO_DRONE_CONTROL_DOCUMENTATION.pdf).

## 🤝 Contributing

We welcome contributions! Please:

1. Fork the repository
2. Create a feature branch: `git checkout -b feature-name`
3. Commit changes: `git commit -am 'Add new feature'`
4. Push to branch: `git push origin feature-name`
5. Submit a Pull Request

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- **DJI** for the Tello drone platform
- **TensorFlow** team for the object detection models
- **OpenCV** community for computer vision tools
- **Azure OpenAI** for natural language processing capabilities

## 📞 Support

For support, bug reports, or feature requests:

- **Issues**: [GitHub Issues](https://github.com/yourusername/TelloDroneControlSystem/issues)
- **Discussions**: [GitHub Discussions](https://github.com/yourusername/TelloDroneControlSystem/discussions)
- **Email**: your.email@example.com

---

**🚁 Ready to take flight with AI-powered drone control!**

*Built with ❤️ for the drone community*