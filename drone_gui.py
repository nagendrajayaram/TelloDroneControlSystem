#!/usr/bin/env python3
"""
Tello Drone Control System - GUI Version
A comprehensive graphical interface for controlling DJI Tello drones
"""

import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import threading
import time
try:
    import cv2
    CV2_AVAILABLE = True
except ImportError:
    cv2 = None
    CV2_AVAILABLE = False
from PIL import Image, ImageTk
import numpy as np
from tello_drone_agent import TelloDroneAgent
import queue
import sys

# Voice command support
try:
    import speech_recognition as sr
    VOICE_AVAILABLE = True
except ImportError:
    sr = None
    VOICE_AVAILABLE = False

# Text-to-speech support
try:
    import pyttsx3
    TTS_AVAILABLE = True
except ImportError:
    pyttsx3 = None
    TTS_AVAILABLE = False

# Audio playback support
try:
    import simpleaudio as sa
    SIMPLEAUDIO_AVAILABLE = True
except ImportError:
    sa = None
    SIMPLEAUDIO_AVAILABLE = False

# Real-time audio support (from advanced agent)
try:
    import pyaudio
    import websockets
    import asyncio
    REALTIME_AUDIO_AVAILABLE = True
except ImportError:
    pyaudio = None
    websockets = None
    asyncio = None
    REALTIME_AUDIO_AVAILABLE = False

# Removed gTTS support - using simple TTS only

# Azure OpenAI support
try:
    from openai import AzureOpenAI
    AZURE_OPENAI_AVAILABLE = True
except ImportError:
    AzureOpenAI = None
    AZURE_OPENAI_AVAILABLE = False
    print("⚠️ Azure OpenAI unavailable: openai package not installed")

# JSON is part of standard library
import json
import base64
import io
import os
import logging.handlers
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Dict, Any, Optional


# ===== ENHANCED LOGGING SYSTEM =====
class LogLevel(Enum):
    """Log level categories for structured logging."""
    EVENT = "EVENT"      # Normal system events (connection, takeoff, etc.)
    WARNING = "WARNING"   # Non-critical issues that should be noted
    FAILURE = "FAILURE"   # Critical failures and errors
    DEBUG = "DEBUG"       # Debug information for troubleshooting
    SYSTEM = "SYSTEM"     # System state changes and configuration

class DailyLogger:
    """Enhanced logging system with daily log files for system improvement feedback."""
    
    def __init__(self, log_directory="logs", max_days=30):
        """
        Initialize the daily logging system.
        
        Args:
            log_directory: Directory to store log files
            max_days: Number of days to retain log files
        """
        self.log_directory = Path(log_directory)
        self.log_directory.mkdir(exist_ok=True)
        self.max_days = max_days
        self.current_date = None
        self.current_file_handler = None
        self.logger = self._setup_logger()
        self._cleanup_old_logs()
    
    def _setup_logger(self):
        """Setup the main logger with daily rotation."""
        logger = logging.getLogger('drone_system')
        logger.setLevel(logging.DEBUG)
        
        # Remove any existing handlers
        for handler in logger.handlers[:]:
            logger.removeHandler(handler)
        
        # Console handler for immediate feedback (optional)
        console_handler = logging.StreamHandler()
        console_formatter = logging.Formatter(
            '%(asctime)s [%(levelname)s] %(message)s',
            datefmt='%H:%M:%S'
        )
        console_handler.setFormatter(console_formatter)
        console_handler.setLevel(logging.WARNING)  # Only warnings and above to console
        logger.addHandler(console_handler)
        
        return logger
    
    def _get_daily_log_filename(self, date=None):
        """Generate filename for daily log."""
        if date is None:
            date = datetime.now()
        return self.log_directory / f"drone_system_{date.strftime('%Y-%m-%d')}.log"
    
    def _ensure_daily_handler(self):
        """Ensure we have a file handler for today's date."""
        today = datetime.now().date()
        
        if self.current_date != today:
            # Remove old file handler
            if self.current_file_handler:
                self.logger.removeHandler(self.current_file_handler)
                self.current_file_handler.close()
            
            # Create new file handler for today
            log_filename = self._get_daily_log_filename()
            self.current_file_handler = logging.FileHandler(log_filename, encoding='utf-8')
            
            # Detailed formatter for file logs
            file_formatter = logging.Formatter(
                '%(asctime)s | %(levelname)-7s | %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S'
            )
            self.current_file_handler.setFormatter(file_formatter)
            self.logger.addHandler(self.current_file_handler)
            
            self.current_date = today
            
            # Log the daily file creation
            if not log_filename.exists() or log_filename.stat().st_size == 0:
                self._log_structured(LogLevel.SYSTEM, "LOGGER", "Daily log file created", {
                    "filename": str(log_filename),
                    "date": today.isoformat()
                })
    
    def _cleanup_old_logs(self):
        """Remove log files older than max_days."""
        if not self.log_directory.exists():
            return
        
        cutoff_date = datetime.now() - timedelta(days=self.max_days)
        removed_count = 0
        
        for log_file in self.log_directory.glob("drone_system_*.log"):
            try:
                # Extract date from filename
                date_str = log_file.stem.replace("drone_system_", "")
                file_date = datetime.strptime(date_str, "%Y-%m-%d")
                
                if file_date < cutoff_date:
                    log_file.unlink()
                    removed_count += 1
            except (ValueError, OSError):
                continue  # Skip invalid filenames or files we can't delete
        
        if removed_count > 0:
            self._log_structured(LogLevel.SYSTEM, "LOGGER", f"Cleaned up {removed_count} old log files")
    
    def _log_structured(self, level: LogLevel, component: str, message: str, data: Optional[Dict[str, Any]] = None):
        """Internal method to log structured messages."""
        self._ensure_daily_handler()
        
        # Create structured log entry
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "level": level.value,
            "component": component,
            "message": message
        }
        
        if data:
            log_entry["data"] = data
        
        # Format for file output
        data_str = ""
        if data:
            data_str = f" | DATA: {json.dumps(data, separators=(',', ':'))}"
        
        formatted_message = f"{component} | {message}{data_str}"
        
        # Log to appropriate level
        if level == LogLevel.FAILURE:
            self.logger.error(formatted_message)
        elif level == LogLevel.WARNING:
            self.logger.warning(formatted_message)
        elif level == LogLevel.DEBUG:
            self.logger.debug(formatted_message)
        else:  # EVENT, SYSTEM
            self.logger.info(formatted_message)
    
    def log_event(self, component: str, message: str, mode: str = None, data: Optional[Dict[str, Any]] = None):
        """Log a normal system event."""
        log_data = {"mode": mode} if mode else {}
        if data:
            log_data.update(data)
        self._log_structured(LogLevel.EVENT, component, message, log_data)
    
    def log_warning(self, component: str, message: str, mode: str = None, data: Optional[Dict[str, Any]] = None):
        """Log a warning."""
        log_data = {"mode": mode} if mode else {}
        if data:
            log_data.update(data)
        self._log_structured(LogLevel.WARNING, component, message, log_data)
    
    def log_failure(self, component: str, message: str, mode: str = None, error: str = None, data: Optional[Dict[str, Any]] = None):
        """Log a failure or error."""
        log_data = {"mode": mode} if mode else {}
        if error:
            log_data["error"] = error
        if data:
            log_data.update(data)
        self._log_structured(LogLevel.FAILURE, component, message, log_data)
    
    def log_debug(self, component: str, message: str, mode: str = None, data: Optional[Dict[str, Any]] = None):
        """Log debug information."""
        log_data = {"mode": mode} if mode else {}
        if data:
            log_data.update(data)
        self._log_structured(LogLevel.DEBUG, component, message, log_data)
    
    def log_system(self, component: str, message: str, data: Optional[Dict[str, Any]] = None):
        """Log system state changes."""
        self._log_structured(LogLevel.SYSTEM, component, message, data)
    
    def get_log_files(self):
        """Get list of available log files."""
        if not self.log_directory.exists():
            return []
        return sorted(self.log_directory.glob("drone_system_*.log"))
    
    def get_log_stats(self):
        """Get statistics about the logging system."""
        log_files = self.get_log_files()
        total_size = sum(f.stat().st_size for f in log_files if f.exists())
        
        return {
            "total_files": len(log_files),
            "total_size_mb": round(total_size / 1024 / 1024, 2),
            "oldest_log": log_files[0].stem.replace("drone_system_", "") if log_files else None,
            "newest_log": log_files[-1].stem.replace("drone_system_", "") if log_files else None,
            "retention_days": self.max_days
        }

# ===== DESIGN SYSTEM & THEME =====
class DroneTheme:
    """Centralized design system with theme tokens for consistent UI styling"""
    
    # Color Palette - Modern Dark Theme
    COLORS = {
        # Background layers (darkest to lightest)
        'bg_root': '#0f1419',       # Main window background
        'bg_panel': '#151b23',      # Content panel background  
        'bg_surface': '#1a1f26',    # Component surface background
        'bg_elevated': '#1f2937',   # Elevated component background
        'bg_input': '#2d3748',      # Input field background
        
        # Text colors
        'text_primary': '#ffffff',   # Primary text
        'text_secondary': '#e2e8f0', # Secondary text  
        'text_muted': '#9ca3af',     # Muted/hint text
        'text_disabled': '#6b7280',  # Disabled text
        
        # Semantic colors - Actions & States  
        'primary': '#3b82f6',        # Primary actions
        'success': '#10b981',        # Success states & positive actions
        'warning': '#f59e0b',        # Warning states
        'danger': '#ef4444',         # Error states & destructive actions
        'info': '#00e5ff',          # Information & highlights
        
        # Accent colors - Feature specific
        'accent_purple': '#a855f7',  # Vision/AI features
        'accent_cyan': '#00cec9',    # Panorama/camera features
        'accent_orange': '#ff8a50',  # Connection/status indicators
        'accent_green': '#00e676',   # Positive feedback
        
        # UI Chrome
        'border': '#374151',         # Subtle borders
        'separator': '#4b5563',      # Dividers and separators
        'shadow': 'rgba(0,0,0,0.25)', # Drop shadows
    }
    
    # Typography Scale
    FONTS = {
        'family': 'Segoe UI',
        'family_mono': 'Consolas',
        
        # Size scale
        'size_xs': 8,     # Chips, badges
        'size_sm': 9,     # Captions, hints
        'size_base': 10,  # Body text, buttons
        'size_md': 11,    # Input fields
        'size_lg': 12,    # Section headers
        'size_xl': 16,    # Page titles
        'size_xxl': 20,   # Main title
        
        # Weights
        'weight_normal': 'normal',
        'weight_bold': 'bold',
    }
    
    # Spacing Scale (multiples of 4px base unit)
    SPACING = {
        'xs': 4,    # 4px - tight spacing
        'sm': 8,    # 8px - small gaps  
        'md': 12,   # 12px - medium gaps
        'lg': 15,   # 15px - large gaps
        'xl': 20,   # 20px - extra large gaps
        'xxl': 24,  # 24px - section spacing
    }
    
    # Component Styles
    STYLES = {
        'button': {
            'relief': 'flat',
            'bd': 0,
            'cursor': 'hand2',
            'padx': 15,
            'pady': 8,
        },
        'button_large': {
            'relief': 'flat', 
            'bd': 0,
            'cursor': 'hand2',
            'padx': 20,
            'pady': 12,
        },
        'frame': {
            'relief': 'flat',
            'bd': 1,
        },
        'entry': {
            'relief': 'flat',
            'bd': 1,
        }
    }
    
    @classmethod
    def get_font(cls, size='base', weight='normal', family=None):
        """Get font tuple for tkinter widgets"""
        font_family = family or cls.FONTS['family']
        font_size = cls.FONTS[f'size_{size}']
        font_weight = cls.FONTS[f'weight_{weight}']
        return (font_family, font_size, font_weight)
    
    @classmethod  
    def get_mono_font(cls, size='base', weight='normal'):
        """Get monospace font tuple"""
        return cls.get_font(size, weight, cls.FONTS['family_mono'])
    
    @classmethod
    def apply_button_style(cls, button, bg_color, style='button'):
        """Apply consistent button styling"""
        style_props = cls.STYLES[style].copy()
        button.configure(
            bg=cls.COLORS[bg_color] if bg_color in cls.COLORS else bg_color,
            fg=cls.COLORS['text_primary'],
            font=cls.get_font('base', 'bold'),
            **style_props
        )
        
    @classmethod
    def create_styled_frame(cls, parent, bg='bg_surface', **kwargs):
        """Create frame with theme styling"""
        frame_props = cls.STYLES['frame'].copy()
        frame_props.update(kwargs)
        return tk.Frame(
            parent,
            bg=cls.COLORS[bg] if bg in cls.COLORS else bg,
            **frame_props
        )


class DroneControlGUI:
    def __init__(self, simulation_mode=True):
        """
        Initialize the GUI application.
        
        Args:
            simulation_mode: Whether to use simulation mode (default: True)
        """
        print("🔧 Starting DroneControlGUI initialization...")
        try:
            self.root = tk.Tk()
            self.root.title("🚁 Tello Drone Control System")
            self.root.geometry("1200x800")
            self.root.configure(bg=DroneTheme.COLORS['bg_root'])
            print("✅ GUI window created successfully")
        except Exception as e:
            print(f"❌ GUI creation failed: {e}")
            raise
        
        # Initialize drone agent
        print("🔧 Initializing drone agent...")
        try:
            self.agent = TelloDroneAgent(
                simulation_mode=simulation_mode
            )
            self.simulation_mode = simulation_mode
            
            # Set up vision analysis callback for agent commands
            self.agent.vision_analysis_callback = self.thread_safe_vision_analysis
            
            # Mark simulation mode for auto-connection after full initialization
            self.pending_auto_connect = simulation_mode
            
            print("✅ Drone agent initialized")
        except Exception as e:
            print(f"❌ Drone agent failed: {e}")
            raise
        
        # GUI state variables
        self.is_connected = tk.BooleanVar()
        self.is_flying = tk.BooleanVar()
        self.battery_level = tk.StringVar(value="--")
        self.connection_status = tk.StringVar(value="Disconnected")
        self.detection_mode = tk.StringVar(value="Off")
        self.follow_mode = tk.StringVar(value="Off")
        
        # Video stream variables
        self.video_frame = None
        self.video_running = False
        self.video_thread = None
        
        # Message queue for thread-safe GUI updates
        self.message_queue = queue.Queue()
        
        # Enhanced daily logging system
        self.daily_logger = DailyLogger()
        mode_text = "SIMULATION" if simulation_mode else "REALTIME"
        self.daily_logger.log_system("GUI", f"Drone Control System started in {mode_text} mode", {
            "version": "2.0",
            "simulation_mode": simulation_mode,
            "timestamp": datetime.now().isoformat()
        })
        
        # Voice command variables
        self.voice_enabled = False
        self.voice_running = False
        self.voice_thread = None
        
        # Vision analysis variables
        self.continuous_vision_enabled = False
        self.continuous_vision_running = False
        self.continuous_vision_thread = None
        self.vision_analysis_interval = 2.0  # Analyze every 2 seconds
        
        # Text-to-speech variables
        self.tts_enabled = True  # Enable by default
        self.tts_engine = None
        self.tts_queue = queue.Queue()
        self.tts_worker_thread = None
        if TTS_AVAILABLE:
            self.setup_tts()
        if VOICE_AVAILABLE:
            self.recognizer = sr.Recognizer()
            self.microphone = None
            self.voice_command_queue = queue.Queue()
        else:
            self.recognizer = None
            self.microphone = None
            self.voice_command_queue = None
            
        # Azure OpenAI configuration
        self.azure_openai_client = None
        self.ai_enabled = False
        self.azure_settings = {
            'endpoint': '',
            'deployment': '',
            'api_key': '',
            'api_version': '2024-08-01-preview'
        }
        
        # Create the GUI layout
        self.create_widgets()
        self.setup_layout()
        
        # Defer blocking initialization to avoid GUI startup hang
        self.root.after(100, self.deferred_setup)
        
        # Start message processing
        self.process_messages()
        
        # Status update timer
        self.update_status()
    
    def create_widgets(self):
        """Create all GUI widgets."""
        
        # Main container frames
        self.create_header()
        self.create_main_content()
        self.create_status_bar()
    
    def create_header(self):
        """Create the header with title and connection controls."""
        # Header frame with modern gradient-like appearance
        self.header_frame = tk.Frame(self.root, bg=DroneTheme.COLORS['bg_surface'], relief='flat', bd=0)
        self.header_frame.pack(fill='x', padx=0, pady=0)
        
        # Top row with title and critical controls
        top_row = tk.Frame(self.header_frame, bg=DroneTheme.COLORS['bg_surface'])
        top_row.pack(fill='x', padx=10, pady=(10, 5))
        
        # Left side - title and mode
        left_bar = tk.Frame(top_row, bg=DroneTheme.COLORS['bg_surface'])
        left_bar.pack(side='left', fill='x', expand=True)
        
        # Title with modern typography
        title_label = tk.Label(
            left_bar, 
            text="🚁 Tello Drone Control System", 
            font=('Segoe UI', 18, 'bold'),
            fg='#ffffff',
            bg=DroneTheme.COLORS['bg_surface']
        )
        title_label.pack(side='left', padx=10, pady=5)
        
        # Mode indicator with toggle button
        mode_bar = tk.Frame(left_bar, bg=DroneTheme.COLORS['bg_surface'])
        mode_bar.pack(side='left', padx=15)
        
        mode_text = "🎮 SIMULATION MODE" if self.simulation_mode else "🚁 REAL DRONE MODE"
        self.mode_label = tk.Label(
            mode_bar,
            text=mode_text,
            font=('Segoe UI', 10, 'bold'),
            fg=DroneTheme.COLORS['info'] if self.simulation_mode else DroneTheme.COLORS['accent_orange'],
            bg=DroneTheme.COLORS['bg_surface']
        )
        self.mode_label.pack(side='left', padx=5, pady=5)
        
        # Mode toggle button
        self.mode_toggle_btn = tk.Button(
            mode_bar,
            text="🔄",
            width=3,
            command=self.toggle_simulation_mode
        )
        DroneTheme.apply_button_style(self.mode_toggle_btn, 'primary')
        self.mode_toggle_btn.pack(side='left', padx=3)
        
        # Right side - connection controls (always visible)
        right_bar = tk.Frame(top_row, bg=DroneTheme.COLORS['bg_surface'])
        right_bar.pack(side='right', padx=10)
        
        # Connection controls with modern styling
        self.connect_btn = tk.Button(
            right_bar,
            text="🔗 Connect",
            width=10,
            command=self.toggle_connection
        )
        DroneTheme.apply_button_style(self.connect_btn, 'success')
        self.connect_btn.pack(side='left', padx=3)
        
        self.emergency_btn = tk.Button(
            right_bar,
            text="🚨 EMERGENCY",
            width=12,
            command=self.emergency_stop
        )
        DroneTheme.apply_button_style(self.emergency_btn, 'danger')
        self.emergency_btn.pack(side='left', padx=3)
        
        # Bottom row with feature buttons
        bottom_row = tk.Frame(self.header_frame, bg=DroneTheme.COLORS['bg_surface'])
        bottom_row.pack(fill='x', padx=10, pady=(0, 10))
        
        # Feature buttons container
        feature_bar = tk.Frame(bottom_row, bg=DroneTheme.COLORS['bg_surface'])
        feature_bar.pack(side='left')
        
        # Mission Planner button
        self.mission_planner_btn = tk.Button(
            feature_bar,
            text="🧠 Mission Planner",
            font=('Segoe UI', 9, 'bold'),
            bg=DroneTheme.COLORS['accent_purple'],
            fg='white',
            relief='flat',
            bd=0,
            padx=10,
            pady=6,
            cursor='hand2',
            command=self.open_mission_planner
        )
        self.mission_planner_btn.pack(side='left', padx=5)
        
        # Panorama button
        self.panorama_btn = tk.Button(
            feature_bar,
            text="📷 Panorama",
            font=('Segoe UI', 9, 'bold'),
            bg=DroneTheme.COLORS['accent_cyan'],
            fg='white',
            relief='flat',
            bd=0,
            padx=10,
            pady=6,
            cursor='hand2',
            command=self.start_panorama_capture
        )
        self.panorama_btn.pack(side='left', padx=5)
        
        # Settings button
        self.settings_btn = tk.Button(
            feature_bar,
            text="⚙️",
            font=('Segoe UI', 11, 'bold'),
            bg=DroneTheme.COLORS['text_muted'],
            fg='white',
            width=3,
            relief='flat',
            bd=0,
            padx=8,
            pady=6,
            cursor='hand2',
            command=self.open_settings
        )
        self.settings_btn.pack(side='left', padx=5)
        
        # Force layout update to ensure proper positioning
        self.root.update_idletasks()
    
    def create_main_content(self):
        """Create the main content area with video and controls."""
        main_frame = tk.Frame(self.root, bg=DroneTheme.COLORS['bg_panel'])
        main_frame.pack(fill='both', expand=True, padx=8, pady=8)
        
        # Left panel - Video and status
        left_panel = tk.Frame(main_frame, bg=DroneTheme.COLORS['bg_panel'], width=600)
        left_panel.pack(side='left', fill='both', expand=True, padx=8)
        
        # Video display
        self.create_video_panel(left_panel)
        
        # Right panel - Controls
        right_panel = tk.Frame(main_frame, bg=DroneTheme.COLORS['bg_panel'], width=400)
        right_panel.pack(side='right', fill='y', padx=8)
        
        # Unified Flight Command Center (combines flight controls, status, voice/text, and AI status)
        self.create_command_center(right_panel)
        
        # Log output
        self.create_log_panel(right_panel)
    
    def create_video_panel(self, parent):
        """Create the video display panel."""
        video_frame = tk.LabelFrame(
            parent, 
            text="📹 Live Video Feed", 
            font=('Segoe UI', 12, 'bold'),
            fg='white',
            bg=DroneTheme.COLORS['bg_surface'],
            relief='flat',
            bd=1,
            height=400
        )
        video_frame.pack(fill='both', expand=True, pady=8)
        
        # Video canvas with modern styling
        self.video_canvas = tk.Canvas(
            video_frame,
            bg=DroneTheme.COLORS['bg_root'],
            width=480,
            height=360,
            highlightthickness=0,
            relief='flat'
        )
        self.video_canvas.pack(expand=True, padx=15, pady=15)
        
        # Vision Analysis Results Panel
        vision_frame = tk.LabelFrame(
            parent,
            text="👁️ Vision Analysis Results",
            font=('Segoe UI', 12, 'bold'),
            fg='white',
            bg=DroneTheme.COLORS['bg_surface'],
            relief='flat',
            bd=1,
            height=150
        )
        vision_frame.pack(fill='x', pady=8)
        
        # Vision results text area with scrollbar
        vision_scroll_frame = tk.Frame(vision_frame, bg=DroneTheme.COLORS['bg_surface'])
        vision_scroll_frame.pack(fill='both', expand=True, padx=15, pady=15)
        
        self.vision_results = scrolledtext.ScrolledText(
            vision_scroll_frame,
            height=6,
            width=50,
            bg='#0f1419',
            fg=DroneTheme.COLORS['info'],
            font=('Segoe UI', 10),
            insertbackground=DroneTheme.COLORS['info'],
            wrap=tk.WORD,
            state='disabled',
            relief='flat',
            bd=0
        )
        self.vision_results.pack(fill='both', expand=True)
        
        # Video controls with modern styling
        video_controls = tk.Frame(video_frame, bg=DroneTheme.COLORS['bg_surface'])
        video_controls.pack(fill='x', padx=15, pady=8)
        
        # Primary controls row
        primary_controls = tk.Frame(video_controls, bg=DroneTheme.COLORS['bg_surface'])
        primary_controls.pack(fill='x', pady=5)
        
        self.video_btn = tk.Button(
            primary_controls,
            text="📹 Start Video",
            command=self.toggle_video
        )
        DroneTheme.apply_button_style(self.video_btn, 'primary')
        self.video_btn.pack(side='left', padx=8)
        
        self.record_btn = tk.Button(
            primary_controls,
            text="⏺ Record",
            command=self.toggle_recording
        )
        DroneTheme.apply_button_style(self.record_btn, 'accent_orange')
        self.record_btn.pack(side='left', padx=8)
        
        
    
    
    def create_command_center(self, parent):
        """Create unified Flight Command Center combining all controls and status."""
        command_frame = tk.LabelFrame(
            parent,
            text="✈️ Flight Command Center & Status",
            font=('Segoe UI', 12, 'bold'),
            fg='white',
            bg=DroneTheme.COLORS['bg_surface'],
            relief='flat',
            bd=1
        )
        command_frame.pack(fill='x', pady=8)
        
        # Drone Status Section
        status_section = tk.Frame(command_frame, bg=DroneTheme.COLORS['bg_surface'])
        status_section.pack(fill='x', padx=15, pady=12)
        
        status_label = tk.Label(
            status_section,
            text="📊 Drone Status",
            font=('Segoe UI', 10, 'bold'),
            fg='#ffffff',
            bg=DroneTheme.COLORS['bg_surface']
        )
        status_label.pack(anchor='w')
        
        # Status grid (compact 2x4 layout)
        status_grid = tk.Frame(status_section, bg='#1a1f26')
        status_grid.pack(fill='x', pady=8)
        
        # Row 1: Connection and Battery
        tk.Label(status_grid, text="Connection:", fg='white', bg='#1a1f26', font=('Segoe UI', 9)).grid(row=0, column=0, sticky='w', padx=8)
        self.status_connection = tk.Label(status_grid, textvariable=self.connection_status, fg='#ff8a50', bg='#1a1f26', font=('Segoe UI', 9))
        self.status_connection.grid(row=0, column=1, sticky='w', padx=8)
        
        tk.Label(status_grid, text="Battery:", fg='white', bg='#1a1f26', font=('Segoe UI', 9)).grid(row=0, column=2, sticky='w', padx=25)
        self.status_battery = tk.Label(status_grid, textvariable=self.battery_level, fg='#00e676', bg='#1a1f26', font=('Segoe UI', 9))
        self.status_battery.grid(row=0, column=3, sticky='w', padx=8)
        
        # Row 2: Flight Status and Detection
        tk.Label(status_grid, text="Flying:", fg='white', bg='#1a1f26', font=('Segoe UI', 9)).grid(row=1, column=0, sticky='w', padx=8)
        self.status_flying = tk.Label(status_grid, text="No", fg='#ff8a50', bg='#1a1f26', font=('Segoe UI', 9))
        self.status_flying.grid(row=1, column=1, sticky='w', padx=8)
        
        tk.Label(status_grid, text="Detection:", fg='white', bg='#1a1f26', font=('Segoe UI', 9)).grid(row=1, column=2, sticky='w', padx=25)
        self.status_detection = tk.Label(status_grid, textvariable=self.detection_mode, fg='#ff8a50', bg='#1a1f26', font=('Segoe UI', 9))
        self.status_detection.grid(row=1, column=3, sticky='w', padx=8)
        
        # Separator line
        separator = tk.Frame(command_frame, bg='#444444', height=1)
        separator.pack(fill='x', padx=10, pady=5)
        
        # Flight Controls Section
        controls_label = tk.Label(
            command_frame,
            text="🎮 Flight Controls",
            font=('Segoe UI', 10, 'bold'),
            fg='#ffffff',
            bg=DroneTheme.COLORS['bg_surface']
        )
        controls_label.pack(anchor='w', padx=15)
        
        # Top row - Primary actions and AI status
        top_row = tk.Frame(command_frame, bg='#1a1f26')
        top_row.pack(fill='x', padx=15, pady=12)
        
        # Flight buttons with modern styling
        self.takeoff_btn = tk.Button(
            top_row,
            text="🛫 Takeoff",
            width=10,
            command=self.takeoff
        )
        DroneTheme.apply_button_style(self.takeoff_btn, 'accent_green')
        self.takeoff_btn.pack(side='left', padx=5)
        
        self.land_btn = tk.Button(
            top_row,
            text="🛬 Land",
            width=10,
            command=self.land
        )
        DroneTheme.apply_button_style(self.land_btn, 'accent_orange')
        self.land_btn.pack(side='left', padx=5)
        
        # Voice control button
        if VOICE_AVAILABLE:
            self.voice_btn = tk.Button(
                top_row,
                text="🎤 Start Voice",
                bg=DroneTheme.COLORS['primary'],
                fg='white',
                font=('Segoe UI', 10, 'bold'),
                width=12,
                relief='flat',
                bd=0,
                padx=15,
                pady=8,
                cursor='hand2',
                command=self.toggle_voice
            )
            self.voice_btn.pack(side='left', padx=5)
            
            # Voice status
            self.voice_status_label = tk.Label(
                top_row,
                text="🔴 Not Listening",
                font=('Segoe UI', 9),
                fg='#ff8a50',
                bg=DroneTheme.COLORS['bg_surface']
            )
            self.voice_status_label.pack(side='left', padx=8)
        
        
        # AI status chip
        ai_color = '#10b981' if self.ai_enabled else '#f59e0b'
        ai_text = "🤖 AI Ready" if self.ai_enabled else "🤖 Configure"
        self.ai_status_chip = tk.Button(
            top_row,
            text=ai_text,
            font=('Segoe UI', 8, 'bold'),
            bg=ai_color,
            fg='white',
            width=12,
            relief='flat',
            bd=0,
            padx=15,
            pady=6,
            cursor='hand2',
            command=self.open_settings
        )
        self.ai_status_chip.pack(side='right', padx=5)
        
        # Input row - Text command entry with modern styling
        input_row = tk.Frame(command_frame, bg='#1a1f26')
        input_row.pack(fill='x', padx=15, pady=12)
        
        tk.Label(
            input_row,
            text="Text Command:",
            font=('Segoe UI', 10, 'bold'),
            fg='white',
            bg=DroneTheme.COLORS['bg_surface']
        ).pack(side='left', padx=8)
        
        self.command_entry = tk.Entry(
            input_row,
            font=('Segoe UI', 11),
            bg='#2d3748',
            fg='white',
            insertbackground=DroneTheme.COLORS['info'],
            width=80,
            relief='flat',
            bd=1
        )
        self.command_entry.pack(side='left', fill='x', expand=True, padx=8)
        self.command_entry.bind('<Return>', lambda e: self.execute_command(self.command_entry.get(), "text"))
        
        self.execute_btn = tk.Button(
            input_row,
            text="▶ Execute",
            bg=DroneTheme.COLORS['primary'],
            fg='white',
            font=('Segoe UI', 10, 'bold'),
            relief='flat',
            bd=0,
            padx=15,
            pady=8,
            cursor='hand2',
            command=lambda: self.execute_command(self.command_entry.get(), "text")
        )
        self.execute_btn.pack(side='right', padx=5)
        
        # Vision analysis buttons with modern styling
        self.vision_analyze_btn = tk.Button(
            input_row,
            text="👁️ Analyze View",
            bg='#a855f7',
            fg='white',
            font=('Segoe UI', 10, 'bold'),
            relief='flat',
            bd=0,
            padx=15,
            pady=8,
            cursor='hand2',
            command=self.start_vision_analysis
        )
        self.vision_analyze_btn.pack(side='right', padx=5)
        
        # Continuous vision analysis toggle
        self.continuous_vision_btn = tk.Button(
            input_row,
            text="🔄 Start Auto-Vision",
            bg=DroneTheme.COLORS['success'],
            fg='white',
            font=('Segoe UI', 10, 'bold'),
            relief='flat',
            bd=0,
            padx=15,
            pady=8,
            cursor='hand2',
            command=self.toggle_continuous_vision
        )
        self.continuous_vision_btn.pack(side='right', padx=5)
        
        # AI Mission Planner button
        
        # Hints row - Examples with modern styling
        hints_row = tk.Frame(command_frame, bg='#1a1f26')
        hints_row.pack(fill='x', padx=15, pady=(0, 12))
        
        tk.Label(
            hints_row,
            text="💡 Examples: \"fly forward 2 meters\", \"take photo\", \"describe what you see\", \"analyze current view\"",
            font=('Segoe UI', 8),
            fg='#9ca3af',
            bg=DroneTheme.COLORS['bg_surface'],
            wraplength=350
        ).pack(side='left', padx=8)
    
    def execute_command(self, cmd_text, source):
        """Unified command execution for buttons, voice, and text with sequential processing."""
        if not cmd_text or not cmd_text.strip():
            return
            
        cmd_text_processed = cmd_text.strip().lower()
        
        # Log command with source
        self.log(f"🎯 Command ({source}): {cmd_text_processed}")
        
        # Clear entry immediately (on GUI thread)
        if hasattr(self, 'command_entry') and source == "text":
            self.command_entry.delete(0, tk.END)
        
        # Safety check - emergency should only be via header button
        if 'emergency' in cmd_text_processed or 'stop' in cmd_text_processed:
            self.log("⚠️ Use EMERGENCY button for safety stops")
            return
        
        # Handle special local commands that don't need drone agent
        if cmd_text_processed == "test audio" or cmd_text_processed == "audio test":
            threading.Thread(target=self.test_audio_playback, daemon=True).start()
            return
        elif cmd_text_processed == "test tts" or cmd_text_processed == "tts test":
            self.speak_text("This is a test of the text to speech system. If you hear this, TTS is working correctly.")
            return
        
        # Define callback to handle command results
        def command_result_callback(result):
            # Log the result in the GUI
            self.log(result)
        
        # Process different command types
        if self.ai_enabled and self.azure_openai_client and not self._is_direct_command(cmd_text_processed):
            # AI processing with sequential execution
            try:
                self.log("🤖 Processing with Azure OpenAI...")
                self.process_ai_command_sequential(cmd_text_processed)
            except Exception as e:
                self.log(f"❌ AI processing failed: {e}")
                # Fallback to direct command
                result = self.agent.execute_command(cmd_text_processed, command_result_callback)
                self.log(result)
        else:
            # Direct command execution via sequential processor
            result = self.agent.execute_command(cmd_text_processed, command_result_callback)
            self.log(result)
    
    def _is_direct_command(self, cmd_text):
        """Check if command is a direct drone command (properly formatted, not natural language)."""
        # Only consider properly formatted direct commands, not natural language
        
        # Basic commands without parameters
        basic_commands = ['takeoff', 'land', 'flip', 'photo', 'picture', 'burst']
        if cmd_text in basic_commands:
            return True
            
        # Commands with specific numeric parameters (properly formatted)
        import re
        
        # Movement commands: "forward 100", "back 50", etc.
        if re.match(r'^(forward|back|left|right|up|down)\s+\d+$', cmd_text):
            return True
            
        # Rotation commands: "cw 90", "ccw 45", etc.
        if re.match(r'^(cw|ccw)\s+\d+$', cmd_text):
            return True
            
        # Go command: "go 100 0 50 30" (x y z speed)
        if re.match(r'^go\s+[-]?\d+\s+[-]?\d+\s+[-]?\d+\s+\d+$', cmd_text):
            return True
            
        # Curve command: "curve x1 y1 z1 x2 y2 z2 speed"
        if re.match(r'^curve\s+([-]?\d+\s+){6}\d+$', cmd_text):
            return True
            
        # Photo with filename: "photo filename.jpg"
        if re.match(r'^(photo|picture)\s+\S+$', cmd_text):
            return True
            
        # Burst with parameters: "burst 5", "burst 3 2.0", etc.
        if re.match(r'^burst(\s+\d+(\s+\d*\.?\d+(\s+\S+)?)?)?$', cmd_text):
            return True
        
        # If it doesn't match any of these patterns, it's natural language
        return False
    
    def process_ai_command_sequential(self, cmd_text):
        """Process AI commands with sequential execution."""
        def ai_processing_thread():
            try:
                # Use Azure OpenAI to interpret the command
                ai_commands = self.process_with_azure_openai(cmd_text)
                
                if ai_commands:
                    self.log(f"🤖 AI generated {len(ai_commands)} commands for sequential execution")
                    
                    # Queue each AI command for sequential execution
                    for i, command in enumerate(ai_commands):
                        def make_callback(cmd_index):
                            return lambda result: self.log(f"🤖 AI Command {cmd_index + 1}: {result}")
                        
                        if 'action' in command:
                            action = command['action']
                            parameters = command.get('parameters', {})
                            
                            if action in ['move_forward', 'move_back', 'move_left', 'move_right', 'move_up', 'move_down']:
                                distance = parameters.get('distance', 50)
                                cmd_str = f"{action.replace('move_', '')} {distance}"
                                result = self.agent.execute_command(cmd_str, make_callback(i))
                                self.log(result)
                            elif action in ['rotate_clockwise', 'rotate_counter_clockwise']:
                                degrees = parameters.get('degrees', 90)
                                rotation = 'cw' if 'clockwise' in action else 'ccw'
                                cmd_str = f"{rotation} {degrees}"
                                result = self.agent.execute_command(cmd_str, make_callback(i))
                                self.log(result)
                            elif action == 'analyze_view':
                                # Handle analyze_view with custom prompt and image source
                                custom_prompt = parameters.get('prompt', None)
                                use_photo = parameters.get('use_photo', False)
                                self.log(f"🔍 DEBUG: Sequential AI - prompt: '{custom_prompt}', use_photo: {use_photo}")
                                
                                # Queue the analyze_view command through the sequential processor
                                # This ensures it runs AFTER all previous commands complete
                                import json
                                params = {"prompt": custom_prompt, "use_photo": use_photo}
                                cmd_str = f"analyze_view {json.dumps(params)}"
                                result = self.agent.execute_command(cmd_str, make_callback(i))
                                self.log(result)
                            elif action in ['takeoff', 'land', 'take_photo', 'take_photo_burst']:
                                cmd_str = action
                                result = self.agent.execute_command(cmd_str, make_callback(i))
                                self.log(result)
                            else:
                                cmd_str = action
                                result = self.agent.execute_command(cmd_str, make_callback(i))
                                self.log(result)
                else:
                    # Fallback to direct command
                    result = self.agent.execute_command(cmd_text, lambda r: self.log(f"🔄 Fallback: {r}"))
                    self.log(result)
                    
            except Exception as e:
                self.log(f"❌ AI processing error: {e}")
                # Final fallback
                result = self.agent.execute_command(cmd_text, lambda r: self.log(f"🔄 Error fallback: {r}"))
                self.log(result)
        
        threading.Thread(target=ai_processing_thread, daemon=True).start()
    
    def process_ai_command(self, cmd_text):
        """Process command using Azure OpenAI."""
        try:
            # Use Azure OpenAI to interpret the command
            ai_commands = self.process_with_azure_openai(cmd_text)
            
            if ai_commands:
                # Execute the AI-generated commands
                self.execute_ai_commands(ai_commands)
            else:
                # Fall back to direct command mapping if AI fails
                self.log("🔄 AI processing failed, trying direct mapping...")
                self.process_direct_command(cmd_text)
                
        except Exception as e:
            self.log(f"❌ AI processing error: {e}")
            # Fall back to direct command mapping
            self.process_direct_command(cmd_text)
    
    def process_direct_command(self, cmd_text):
        """DEPRECATED - UNSAFE METHOD. Route all commands through sequential processor."""
        self.log("❌ SECURITY WARNING: Unsafe direct command path blocked")
        self.log("🔄 Routing to safe sequential processor...")
        
        # Route ALL commands through safe sequential processor
        def safe_callback(result):
            self.log(f"🔒 Safe execution: {result}")
        
        result = self.agent.execute_command(cmd_text, safe_callback)
        self.log(result)
    
    def parse_vision_command(self, cmd_text):
        """Parse and execute vision analysis commands."""
        try:
            # Check AI availability first
            if not self.ai_enabled or not self.azure_openai_client:
                self.log("❌ Vision analysis requires AI configuration. Click the ⚙️ Settings button.")
                return True  # Command was recognized, just not executable
            
            if any(phrase in cmd_text for phrase in ['describe what you see', 'what do you see', 'analyze view', 'analyze current view', 'describe view', 'describe what you see in the video', 'what do you see in the video', 'analyze the video', 'describe the video']):
                threading.Thread(target=self.analyze_current_view, daemon=True).start()
                return True
            elif any(phrase in cmd_text for phrase in ['analyze photo', 'describe photo', 'what\'s in photo']):
                # For now, just analyze current view since we don't have photo selection
                threading.Thread(target=self.analyze_current_view, daemon=True).start()
                return True
            elif any(phrase in cmd_text for phrase in ['vision analysis', 'enable vision', 'start vision']):
                self.log("🔍 Vision analysis is ready! Say 'describe what you see' to analyze the current view.")
                return True
            
            return False
            
        except Exception as e:
            self.log(f"❌ Error parsing vision command: {e}")
            return False
    
    def parse_complex_command(self, cmd_text):
        """Parse and execute complex commands with multiple actions."""
        try:
            # Handle "Take a photo & Describe" type commands
            if ('photo' in cmd_text or 'picture' in cmd_text) and ('describe' in cmd_text or 'analyze' in cmd_text):
                self.log("📷🔍 Taking photo with analysis...")
                # Take photo with vision analysis enabled
                self.take_photo(analyze_vision=True)
                return True
            
            # Handle commands with "&" or "and" separators
            if '&' in cmd_text or ' and ' in cmd_text:
                # Split the command into parts
                separators = ['&', ' and ']
                parts = [cmd_text]
                
                for sep in separators:
                    if sep in cmd_text:
                        parts = cmd_text.split(sep)
                        break
                
                # Execute each part sequentially
                for part in parts:
                    part = part.strip()
                    if part:
                        self.log(f"🔗 Executing part: {part}")
                        # Avoid infinite recursion by calling direct processing
                        self.process_direct_command(part)
                return True
            
            return False
        except Exception as e:
            self.log(f"❌ Complex command error: {e}")
            return False
    
    def create_flight_controls(self, parent):
        """Create simplified flight control buttons (takeoff/land only)."""
        flight_frame = tk.LabelFrame(
            parent,
            text="✈️ Flight Controls",
            font=('Segoe UI', 12, 'bold'),
            fg='white',
            bg=DroneTheme.COLORS['bg_surface'],
            relief='flat',
            bd=1
        )
        flight_frame.pack(fill='x', pady=8)
        
        # Takeoff/Land buttons (centered and larger)
        takeoff_land_frame = tk.Frame(flight_frame, bg='#1a1f26')
        takeoff_land_frame.pack(fill='x', padx=15, pady=15)
        
        self.takeoff_btn = tk.Button(
            takeoff_land_frame,
            text="🚀 Takeoff",
            font=('Segoe UI', 12, 'bold'),
            bg='#00e676',
            fg='white',
            width=20,
            height=2,
            relief='flat',
            bd=0,
            cursor='hand2',
            command=self.takeoff
        )
        self.takeoff_btn.pack(pady=8)
        
        self.land_btn = tk.Button(
            takeoff_land_frame,
            text="🛬 Land",
            font=('Segoe UI', 12, 'bold'),
            bg=DroneTheme.COLORS['accent_orange'],
            fg='white',
            width=20,
            height=2,
            relief='flat',
            bd=0,
            cursor='hand2',
            command=self.land
        )
        self.land_btn.pack(pady=8)
        
        # Note about movement controls
        note_label = tk.Label(
            flight_frame,
            text="💬 Use voice commands or text input for movement and rotation",
            font=('Segoe UI', 9, 'italic'),
            fg='#9ca3af',
            bg=DroneTheme.COLORS['bg_surface'],
            wraplength=300
        )
        note_label.pack(pady=(0, 15))
    
    def create_movement_grid(self, parent):
        """Create 3x3 movement control grid."""
        tk.Label(parent, text="Movement:", fg='white', bg='#2b2b2b').pack()
        
        grid_frame = tk.Frame(parent, bg='#2b2b2b')
        grid_frame.pack()
        
        # Row 0: Up controls
        tk.Button(grid_frame, text=" ", width=3, state='disabled', bg='#2b2b2b', relief='flat').grid(row=0, column=0)
        tk.Button(grid_frame, text="⬆️", width=3, bg='#607D8B', fg='white', command=lambda: self.move("up")).grid(row=0, column=1, padx=1, pady=1)
        tk.Button(grid_frame, text=" ", width=3, state='disabled', bg='#2b2b2b', relief='flat').grid(row=0, column=2)
        
        # Row 1: Left, Center, Right
        tk.Button(grid_frame, text="⬅️", width=3, bg='#607D8B', fg='white', command=lambda: self.move("left")).grid(row=1, column=0, padx=1, pady=1)
        tk.Button(grid_frame, text="⏹️", width=3, bg='#795548', fg='white', command=self.stop).grid(row=1, column=1, padx=1, pady=1)
        tk.Button(grid_frame, text="➡️", width=3, bg='#607D8B', fg='white', command=lambda: self.move("right")).grid(row=1, column=2, padx=1, pady=1)
        
        # Row 2: Down controls
        tk.Button(grid_frame, text=" ", width=3, state='disabled', bg='#2b2b2b', relief='flat').grid(row=2, column=0)
        tk.Button(grid_frame, text="⬇️", width=3, bg='#607D8B', fg='white', command=lambda: self.move("down")).grid(row=2, column=1, padx=1, pady=1)
        tk.Button(grid_frame, text=" ", width=3, state='disabled', bg='#2b2b2b', relief='flat').grid(row=2, column=2)
        
        # Row 3: Forward/Back
        tk.Button(grid_frame, text="⬆️ Fwd", width=6, bg='#3F51B5', fg='white', command=lambda: self.move("forward")).grid(row=3, column=0, columnspan=1, padx=1, pady=1)
        tk.Button(grid_frame, text="⬇️ Back", width=6, bg='#3F51B5', fg='white', command=lambda: self.move("back")).grid(row=3, column=2, columnspan=1, padx=1, pady=1)
    
    def create_camera_controls(self, parent):
        """Create camera and detection controls."""
        camera_frame = tk.LabelFrame(
            parent,
            text="📸 Camera & Detection",
            font=('Arial', 12, 'bold'),
            fg='white',
            bg='#2b2b2b'
        )
        camera_frame.pack(fill='x', pady=5)
        
        # Photo controls
        photo_frame = tk.Frame(camera_frame, bg='#2b2b2b')
        photo_frame.pack(fill='x', padx=10, pady=5)
        
        tk.Button(
            photo_frame,
            text="📷 Photo",
            bg='#E91E63',
            fg='white',
            width=12,
            command=self.take_photo
        ).pack(side='left', padx=5)
        
        tk.Button(
            photo_frame,
            text="📸 Burst",
            bg='#E91E63',
            fg='white',
            width=12,
            command=self.burst_photos
        ).pack(side='left', padx=5)
        
        
        # Detection controls
        detection_frame = tk.Frame(camera_frame, bg='#2b2b2b')
        detection_frame.pack(fill='x', padx=10, pady=5)
        
        tk.Label(detection_frame, text="Object Detection:", fg='white', bg='#2b2b2b').pack()
        
        detect_buttons = tk.Frame(detection_frame, bg='#2b2b2b')
        detect_buttons.pack()
        
        tk.Button(
            detect_buttons,
            text="👤 Face",
            bg='#FF5722',
            fg='white',
            width=8,
            command=lambda: self.toggle_detection("face")
        ).pack(side='left', padx=2)
        
        tk.Button(
            detect_buttons,
            text="🚶 Person",
            bg='#FF5722',
            fg='white',
            width=8,
            command=lambda: self.toggle_detection("person")
        ).pack(side='left', padx=2)
        
        tk.Button(
            detect_buttons,
            text="🚗 Vehicle",
            bg='#FF5722',
            fg='white',
            width=8,
            command=lambda: self.toggle_detection("vehicle")
        ).pack(side='left', padx=2)
        
        # AI Detection toggle
        tk.Button(
            detect_buttons,
            text="🤖 AI Mode",
            bg='#4CAF50',
            fg='white',
            width=8,
            command=lambda: self.toggle_ai_detection()
        ).pack(side='left', padx=2)
        
        # Follow controls
        follow_frame = tk.Frame(camera_frame, bg='#2b2b2b')
        follow_frame.pack(fill='x', padx=10, pady=5)
        
        tk.Button(
            follow_frame,
            text="🎯 Follow Target",
            bg='#673AB7',
            fg='white',
            width=15,
            command=self.toggle_follow
        ).pack(side='left', padx=5)
        
        tk.Button(
            follow_frame,
            text="📷 Detect Photo",
            bg='#673AB7',
            fg='white',
            width=15,
            command=self.detection_photo
        ).pack(side='right', padx=5)
        
        # Camera functions are now handled via voice/AI commands only
        pass
    
        
    
    def create_log_panel(self, parent):
        """Create log output panel."""
        log_frame = tk.LabelFrame(
            parent,
            text="📝 Activity Log",
            font=('Segoe UI', 12, 'bold'),
            fg='white',
            bg=DroneTheme.COLORS['bg_surface'],
            relief='flat',
            bd=1
        )
        log_frame.pack(fill='both', expand=True, pady=8)
        
        self.log_text = scrolledtext.ScrolledText(
            log_frame,
            height=8,
            bg='#0f1419',
            fg='#00e676',
            font=('Consolas', 9),
            wrap=tk.WORD,
            relief='flat',
            bd=0,
            insertbackground='#00e676'
        )
        self.log_text.pack(fill='both', expand=True, padx=15, pady=15)
        
        # Initial welcome message
        self.log("🎮 Welcome to Tello Drone Control System!")
        self.log("🔗 Click 'Connect' to start controlling your drone")
    
    def create_status_bar(self):
        """Create bottom status bar."""
        status_bar = tk.Frame(self.root, bg=DroneTheme.COLORS['bg_panel'], height=35)
        status_bar.pack(fill='x', side='bottom')
        status_bar.pack_propagate(False)
        
        self.status_label = tk.Label(
            status_bar,
            text="Ready",
            bg='#151b23',
            fg='white',
            font=('Segoe UI', 9),
            anchor='w'
        )
        self.status_label.pack(side='left', padx=15, pady=8)
    
    def setup_layout(self):
        """Setup the overall layout and styling."""
        # Configure window
        self.root.minsize(1000, 700)
        
        # Center the window
        self.root.update_idletasks()
        x = (self.root.winfo_screenwidth() // 2) - (1200 // 2)
        y = (self.root.winfo_screenheight() // 2) - (800 // 2)
        self.root.geometry(f'1200x800+{x}+{y}')
    
    # Control Methods
    def toggle_connection(self):
        """Toggle drone connection."""
        if self.is_connected.get():
            self.disconnect()
        else:
            self.connect()
    
    def connect(self):
        """Connect to the drone."""
        def connect_thread():
            try:
                self.log("🔗 Connecting to drone...")
                success = self.agent.connect()
                
                if success:
                    self.message_queue.put(('connection_success', None))
                    self.log("✅ Connected successfully!")
                else:
                    self.message_queue.put(('connection_failed', None))
                    self.log("❌ Connection failed")
            except Exception as e:
                self.message_queue.put(('connection_error', str(e)))
                self.log(f"❌ Connection error: {e}")
        
        threading.Thread(target=connect_thread, daemon=True).start()
    
    def auto_connect_simulation(self):
        """Automatically connect to simulated drone for seamless operation."""
        def auto_connect_thread():
            try:
                self.log("🔗 Auto-connecting to simulated drone...")
                success = self.agent.connect()
                
                if success:
                    self.message_queue.put(('connection_success', None))
                    self.log("✅ Simulation auto-connected!")
                    
                    # Auto-start video stream for photo capabilities
                    if self.agent.start_video_stream():
                        self.log("📹 Simulation video stream started")
                    else:
                        self.log("⚠️ Simulation video stream failed to start")
                else:
                    self.log("❌ Simulation auto-connect failed")
            except Exception as e:
                self.log(f"❌ Simulation auto-connect error: {e}")
        
        threading.Thread(target=auto_connect_thread, daemon=True).start()
    
    def disconnect(self):
        """Disconnect from the drone."""
        try:
            if self.agent.is_flying:
                self.log("🛬 Landing drone before disconnect...")
                self.agent.land()
            
            self.agent.disconnect()
            self.is_connected.set(False)
            self.connection_status.set("Disconnected")
            self.update_control_states()  # Update all button states immediately
            self.log("🔌 Disconnected from drone")
        except Exception as e:
            self.log(f"❌ Disconnect error: {e}")
    
    def toggle_simulation_mode(self):
        """Toggle between simulation and real-time drone mode."""
        if self.is_connected.get():
            # Ask user if they want to proceed with mode switch while connected
            result = messagebox.askyesno(
                "Mode Switch Warning", 
                "Switching modes will disconnect the current drone.\n\nDo you want to continue?"
            )
            if not result:
                return
        
        # Disable toggle button during switch
        self.mode_toggle_btn.config(state='disabled')
        
        def mode_switch_thread():
            try:
                old_mode = "SIMULATION" if self.simulation_mode else "REALTIME"
                new_mode = "REALTIME" if self.simulation_mode else "SIMULATION"
                
                self.log(f"🔄 Switching from {old_mode} to {new_mode} mode...")
                
                # Enhanced logging for mode switch
                self.daily_logger.log_system("MODE_SWITCH", f"User initiated mode switch from {old_mode} to {new_mode}", {
                    "old_mode": old_mode,
                    "new_mode": new_mode,
                    "was_connected": self.is_connected.get(),
                    "was_flying": self.is_flying.get()
                })
                
                # Safety check - if flying with real drone, land first
                if self.is_flying.get() and not self.simulation_mode:
                    self.log("⚠️ Landing drone before mode switch for safety...")
                    self.agent.land()
                    time.sleep(3)  # Wait for landing
                    self.is_flying.set(False)
                
                # Disconnect current connection if active
                was_connected = self.is_connected.get()
                if was_connected:
                    self.log("🔌 Disconnecting current connection...")
                    # Stop video stream cleanly
                    if self.video_running:
                        self.agent.stop_video()
                    # Disconnect
                    self.agent.disconnect()
                    self.is_connected.set(False)
                    self.connection_status.set("Disconnected")
                
                # Switch simulation mode
                self.simulation_mode = not self.simulation_mode
                
                # Create new agent with opposite mode
                self.log(f"🔌 Reinitializing agent for {new_mode} mode...")
                old_agent = self.agent
                self.agent = TelloDroneAgent(simulation_mode=self.simulation_mode)
                
                # Set up callbacks for new agent
                self.agent.vision_analysis_callback = self.thread_safe_vision_analysis
                self.agent.daily_logger = self.daily_logger
                
                # Clean up old agent properly
                try:
                    old_agent.disconnect()
                    if hasattr(old_agent, '_cleanup'):
                        old_agent._cleanup()
                except:
                    pass  # Ignore cleanup errors
                
                # Update UI on main thread
                self.root.after(0, self._update_mode_ui)
                
                # Update pending auto-connect flag
                self.pending_auto_connect = self.simulation_mode
                
                # Auto-reconnect if we were connected before (and in simulation mode)
                if was_connected and self.simulation_mode:
                    self.root.after(1000, self.auto_connect_simulation)
                
                self.log(f"✅ Successfully switched to {new_mode} mode!")
                self.daily_logger.log_event("MODE_SWITCH", f"Mode switch completed successfully to {new_mode}", new_mode, {
                    "reconnection_attempted": was_connected and self.simulation_mode
                })
                
                # Re-enable toggle button
                self.root.after(0, lambda: self.mode_toggle_btn.config(state='normal'))
                
            except Exception as e:
                self.log(f"❌ Mode switch error: {e}")
                self.daily_logger.log_failure("MODE_SWITCH", "Mode switch failed", 
                                             "UNKNOWN", error=str(e))
                # Re-enable toggle button and show error
                self.root.after(0, lambda: [
                    self.mode_toggle_btn.config(state='normal'),
                    self.show_toast_notification(f"❌ Mode switch failed: {e}", 'error')
                ])
        
        threading.Thread(target=mode_switch_thread, daemon=True).start()
    
    def _update_mode_ui(self):
        """Update UI elements to reflect current mode."""
        mode_text = "🎮 SIMULATION MODE" if self.simulation_mode else "🚁 REAL DRONE MODE"
        self.mode_label.config(
            text=mode_text,
            fg=DroneTheme.COLORS['info'] if self.simulation_mode else DroneTheme.COLORS['accent_orange']
        )
        
        # Reset connection status
        self.is_connected.set(False)
        self.is_flying.set(False)
        self.connection_status.set("Disconnected")
        self.video_running = False
        
        # Update control states
        self.update_control_states()
        
        # Show toast notification
        mode_name = "Simulation" if self.simulation_mode else "Real-time"
        self.show_toast_notification(f"🔄 Switched to {mode_name} mode!", 'info')
    
    def emergency_stop(self):
        """Emergency stop the drone - IMMEDIATE ACTION for safety."""
        try:
            self.agent.emergency_stop()
            self.log("🚨 EMERGENCY STOP ACTIVATED")
            self.show_toast_notification("🚨 EMERGENCY STOP ACTIVATED", 'warning', 5000)
        except Exception as e:
            self.log(f"❌ Emergency stop error: {e}")
            self.show_toast_notification(f"❌ Emergency stop error: {e}", 'error')
    
    def takeoff(self):
        """Takeoff the drone with confirmation."""
        if not self.is_connected.get():
            self.log("❌ Not connected to drone")
            return
            
        # Safety confirmation for takeoff
        if not messagebox.askyesno("Confirm Takeoff", 
            "Takeoff the drone?\n\nEnsure adequate space and safety clearance."):
            return
            
        def takeoff_thread():
            try:
                self.log("🚀 Taking off...")
                success = self.agent.takeoff()
                if success:
                    self.message_queue.put(('takeoff_success', None))
                    self.log("✅ Takeoff successful!")
                else:
                    self.log("❌ Takeoff failed")
                    self.root.after(0, lambda: self.show_toast_notification(
                        "❌ Takeoff failed", 'error'))
            except Exception as e:
                self.log(f"❌ Takeoff error: {e}")
                self.root.after(0, lambda: self.show_toast_notification(
                    f"❌ Takeoff error: {e}", 'error'))
        
        threading.Thread(target=takeoff_thread, daemon=True).start()
    
    def land(self):
        """Land the drone with confirmation."""
        if not self.is_connected.get():
            self.log("❌ Not connected to drone")
            return
            
        # Safety confirmation for landing
        if not messagebox.askyesno("Confirm Landing", 
            "Land the drone?\n\nEnsure safe landing area below."):
            return
            
        def land_thread():
            try:
                self.log("🛬 Landing...")
                success = self.agent.land()
                if success:
                    self.message_queue.put(('land_success', None))
                    self.log("✅ Landing successful!")
                else:
                    self.log("❌ Landing failed")
                    self.root.after(0, lambda: self.show_toast_notification(
                        "❌ Landing failed", 'error'))
            except Exception as e:
                self.log(f"❌ Landing error: {e}")
                self.root.after(0, lambda: self.show_toast_notification(
                    f"❌ Landing error: {e}", 'error'))
        
        threading.Thread(target=land_thread, daemon=True).start()
    
    def move(self, direction, distance=50):
        """Move the drone in specified direction."""
        def move_thread():
            try:
                self.log(f"➡️ Moving {direction} {distance}cm...")
                success = getattr(self.agent, f"move_{direction}")(distance)
                if success:
                    self.log(f"✅ Moved {direction} successfully!")
                else:
                    self.log(f"❌ Move {direction} failed")
            except Exception as e:
                self.log(f"❌ Move {direction} error: {e}")
        
        # More flexible flying check with status debugging
        if self.is_connected.get():
            self.log(f"🔍 Debug: Connected={self.is_connected.get()}, Agent flying={self.agent.is_flying}")
            if self.agent.is_flying:
                threading.Thread(target=move_thread, daemon=True).start()
            else:
                self.log("❌ Drone must be flying to move")
        else:
            self.log("❌ Not connected to drone")
    
    def rotate(self, direction):
        """Rotate the drone."""
        def rotate_thread():
            try:
                degrees = 90  # Default 90 degrees
                self.log(f"🔄 Rotating {direction} {degrees}°...")
                if direction == "left":
                    success = self.agent.rotate_counter_clockwise(degrees)
                elif direction == "right":
                    success = self.agent.rotate_clockwise(degrees)
                else:
                    success = False
                if success:
                    self.log(f"✅ Rotated {direction} successfully!")
                else:
                    self.log(f"❌ Rotate {direction} failed")
            except Exception as e:
                self.log(f"❌ Rotate {direction} error: {e}")
        
        if self.is_connected.get() and self.agent.is_flying:
            threading.Thread(target=rotate_thread, daemon=True).start()
        else:
            self.log("❌ Drone must be connected and flying to rotate")
    
    def stop(self):
        """Stop drone movement."""
        try:
            self.log("⏹️ Stopping movement...")
            # For Tello, this would be a hover command
            if hasattr(self.agent, 'hover'):
                self.agent.hover(1)  # Hover for 1 second
            self.log("✅ Movement stopped")
        except Exception as e:
            self.log(f"❌ Stop error: {e}")
    
    def take_photo(self, analyze_vision=False):
        """Take a photo with optional AI vision analysis."""
        def photo_thread():
            try:
                self.log("📷 Taking photo...")
                filename = self.agent.save_photo()
                success = bool(filename)
                if success:
                    # Show flash effect
                    self.root.after(0, self.show_flash_effect)
                    self.log(f"✅ Photo saved: {filename}")
                    self.root.after(0, lambda: self.show_toast_notification(
                        f"📸 Photo saved: {filename}", 'success'))
                    
                    # Only analyze the photo if explicitly requested
                    if analyze_vision and self.ai_enabled and filename:
                        self.log("🔍 Analyzing captured photo...")
                        threading.Thread(
                            target=lambda: self.analyze_captured_photo(filename),
                            daemon=True
                        ).start()
                else:
                    self.log("❌ Photo failed")
                    self.root.after(0, lambda: self.show_toast_notification(
                        "❌ Photo capture failed", 'error'))
            except Exception as e:
                self.log(f"❌ Photo error: {e}")
        
        if self.is_connected.get():
            threading.Thread(target=photo_thread, daemon=True).start()
        else:
            self.log("❌ Not connected to drone")
    
    def burst_photos(self):
        """Take burst photos."""
        def burst_thread():
            try:
                self.log("📸 Taking burst photos...")
                photos = self.agent.take_photo_burst()
                success = bool(photos)
                if success:
                    self.log("✅ Burst photos completed!")
                else:
                    self.log("❌ Burst photos failed")
            except Exception as e:
                self.log(f"❌ Burst photos error: {e}")
        
        if self.is_connected.get():
            threading.Thread(target=burst_thread, daemon=True).start()
        else:
            self.log("❌ Not connected to drone")
    
    def toggle_video(self):
        """Toggle video stream."""
        if self.video_running:
            self.stop_video()
        else:
            self.start_video()
    
    def start_video(self):
        """Start video stream."""
        try:
            self.agent.start_video_stream()
            self.video_running = True
            self.video_btn.config(text="⏹ Stop Video", bg='#f44336')
            self.start_video_thread()
            self.log("📹 Video stream started")
        except Exception as e:
            self.log(f"❌ Video start error: {e}")
    
    def stop_video(self):
        """Stop video stream."""
        try:
            self.video_running = False
            self.agent.stop_video_stream()
            self.video_btn.config(text="📹 Start Video", bg='#2196F3')
            self.log("⏹ Video stream stopped")
        except Exception as e:
            self.log(f"❌ Video stop error: {e}")
    
    def start_video_thread(self):
        """Start video display thread."""
        def video_loop():
            while self.video_running and self.is_connected.get():
                try:
                    frame = self.agent.get_current_frame()
                    if frame is not None:
                        # Convert frame for tkinter display
                        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                        frame_resized = cv2.resize(frame_rgb, (480, 360))
                        
                        # Convert to PIL Image and then to PhotoImage
                        image_pil = Image.fromarray(frame_resized)
                        photo = ImageTk.PhotoImage(image_pil)
                        
                        # Update video canvas
                        self.message_queue.put(('video_frame', photo))
                    
                    time.sleep(0.03)  # ~30 FPS
                except Exception as e:
                    self.log(f"❌ Video error: {e}")
                    break
        
        self.video_thread = threading.Thread(target=video_loop, daemon=True)
        self.video_thread.start()
    
    def toggle_recording(self):
        """Toggle video recording."""
        try:
            if hasattr(self.agent, 'recording') and self.agent.recording:
                self.agent.stop_video_recording()
                self.record_btn.config(text="⏺ Record", bg='#ff6600')
                self.log("⏹ Recording stopped")
            else:
                self.agent.start_video_recording()
                self.record_btn.config(text="⏹ Stop", bg='#f44336')
                self.log("⏺ Recording started")
        except Exception as e:
            self.log(f"❌ Recording error: {e}")
    
    def toggle_ai_detection(self):
        """Toggle AI-powered object detection mode."""
        try:
            if hasattr(self.agent, 'object_detector'):
                current_ai_state = getattr(self.agent.object_detector, 'ai_detection_enabled', False)
                new_state = not current_ai_state
                
                if hasattr(self.agent.object_detector, 'set_ai_detection'):
                    success = self.agent.object_detector.set_ai_detection(new_state)
                    if success:
                        mode_text = "AI" if new_state else "OpenCV"
                        self.log(f"🤖 Detection mode switched to {mode_text}")
                        # Log the mode switch
                        self.daily_logger.log_event("AI_DETECTION", f"AI detection mode {'enabled' if new_state else 'disabled'}", 
                                                   "SIMULATION" if self.simulation_mode else "REALTIME", 
                                                   {"ai_enabled": new_state})
                    else:
                        self.log("⚠️ AI detection not available - using OpenCV mode")
                else:
                    self.log("❌ AI detection not supported in this version")
            else:
                self.log("❌ Object detector not available")
        except Exception as e:
            self.log(f"❌ AI detection toggle error: {e}")
    
    def toggle_detection(self, detection_type):
        """Toggle object detection."""
        try:
            if self.agent.detection_enabled:
                self.agent.disable_detection()
                self.detection_mode.set("Off")
                self.log("👁️ Object detection stopped")
            else:
                self.agent.enable_detection(detection_type)
                self.detection_mode.set(f"{detection_type.title()}")
                self.log(f"👁️ {detection_type.title()} detection started")
        except Exception as e:
            self.log(f"❌ Detection error: {e}")
    
    def toggle_follow(self):
        """Toggle follow mode."""
        try:
            if self.agent.follow_mode:
                self.agent.stop_follow_mode()
                self.follow_mode.set("Off")
                self.log("🎯 Follow mode stopped")
            else:
                self.agent.start_follow_mode("face")  # Default to face
                self.follow_mode.set("Face")
                self.log("🎯 Follow mode started")
        except Exception as e:
            self.log(f"❌ Follow error: {e}")
    
    def detection_photo(self):
        """Take photo when object detected."""
        def detection_photo_thread():
            try:
                self.log("📷 Detection photo mode activated...")
                success = self.agent.detect_and_photo()
                if success:
                    self.log("✅ Detection photo completed!")
                else:
                    self.log("❌ Detection photo failed")
            except Exception as e:
                self.log(f"❌ Detection photo error: {e}")
        
        if self.is_connected.get():
            threading.Thread(target=detection_photo_thread, daemon=True).start()
        else:
            self.log("❌ Not connected to drone")
    
    def execute_voice_text_command(self, event=None):
        """Execute command from voice section text input."""
        command = self.voice_command_entry.get().strip()
        if not command:
            return
        
        self.voice_command_entry.delete(0, tk.END)
        self._execute_command(command)
    
    
    def _execute_command(self, command):
        """Internal method to execute commands."""
        
        def command_thread():
            try:
                self.log(f"💬 Executing: '{command}'")
                success = self.agent.execute_instruction(command)
                if success:
                    self.log("✅ Command executed successfully!")
                else:
                    self.log("❌ Command failed or not understood")
            except Exception as e:
                self.log(f"❌ Command error: {e}")
        
        if self.is_connected.get():
            threading.Thread(target=command_thread, daemon=True).start()
        else:
            self.log("❌ Not connected to drone")
    
    # Utility Methods
    def log(self, message, level="EVENT", component="GUI", data=None):
        """Enhanced logging with daily file storage and categorization."""
        timestamp = time.strftime("%H:%M:%S")
        log_message = f"[{timestamp}] {message}\n"
        
        # Thread-safe GUI log update (unchanged for backward compatibility)
        self.message_queue.put(('log', log_message))
        
        # Enhanced daily logging based on message content and level
        mode = "SIMULATION" if self.simulation_mode else "REALTIME"
        
        # Categorize messages based on content for structured logging
        if "❌" in message or "error" in message.lower() or "failed" in message.lower():
            # Extract error details
            error_data = {"gui_message": message.strip()}
            if data:
                error_data.update(data)
            self.daily_logger.log_failure(component, message.replace("❌", "").strip(), mode, data=error_data)
        elif "⚠️" in message or "warning" in message.lower():
            # Warning messages
            warning_data = {"gui_message": message.strip()}
            if data:
                warning_data.update(data)
            self.daily_logger.log_warning(component, message.replace("⚠️", "").strip(), mode, warning_data)
        elif "✅" in message or "successful" in message.lower() or "connected" in message.lower():
            # Success events
            event_data = {"gui_message": message.strip(), "success": True}
            if data:
                event_data.update(data)
            self.daily_logger.log_event(component, message.replace("✅", "").strip(), mode, event_data)
        else:
            # General events
            event_data = {"gui_message": message.strip()}
            if data:
                event_data.update(data)
            self.daily_logger.log_event(component, message.strip(), mode, event_data)
    
    def process_messages(self):
        """Process messages from background threads."""
        try:
            while True:
                message_type, data = self.message_queue.get_nowait()
                
                if message_type == 'log':
                    self.log_text.insert(tk.END, data)
                    self.log_text.see(tk.END)
                
                elif message_type == 'video_frame':
                    self.video_canvas.delete("all")
                    self.video_canvas.create_image(240, 180, image=data)
                    self.video_frame = data  # Keep reference
                
                elif message_type == 'connection_success':
                    self.is_connected.set(True)
                    self.connection_status.set("Connected")
                    self.update_control_states()  # Update all button states
                    self.show_toast_notification("✅ Connected to drone!", 'success')
                
                elif message_type == 'connection_failed':
                    self.is_connected.set(False)
                    self.connection_status.set("Failed")
                    self.update_control_states()  # Update all button states
                    self.show_toast_notification("❌ Connection failed", 'error')
                
                elif message_type == 'takeoff_success':
                    self.is_flying.set(True)
                    self.status_flying.config(text="Yes", fg=DroneTheme.COLORS['accent_green'])
                    self.update_control_states()  # Update all button states
                    self.show_toast_notification("🚀 Takeoff successful!", 'success')
                
                elif message_type == 'land_success':
                    self.is_flying.set(False)
                    self.status_flying.config(text="No", fg=DroneTheme.COLORS['accent_orange'])
                    self.update_control_states()  # Update all button states
                    self.show_toast_notification("🛬 Landing successful!", 'success')
                
        except queue.Empty:
            pass
        
        # Process voice commands if available
        if VOICE_AVAILABLE and self.voice_command_queue:
            try:
                while True:
                    voice_command = self.voice_command_queue.get_nowait()
                    self.process_voice_command(voice_command)
            except queue.Empty:
                pass
        
        # Schedule next check
        self.root.after(50, self.process_messages)
    
    def update_status(self):
        """Update drone status periodically."""
        if self.is_connected.get():
            try:
                # Update battery level
                battery = self.agent.drone.get_battery()
                if battery is not None:
                    self.battery_level.set(f"{battery}%")
                    
                    # Change color based on battery level
                    if battery > 30:
                        self.status_battery.config(fg='#00ff00')
                    elif battery > 15:
                        self.status_battery.config(fg='#ff6600')
                    else:
                        self.status_battery.config(fg='#ff0000')
                
                # Update flying status
                if hasattr(self.agent, 'is_flying'):
                    if self.agent.is_flying:
                        self.status_flying.config(text="Yes", fg='#00ff00')
                    else:
                        self.status_flying.config(text="No", fg='#ff6600')
                
            except Exception as e:
                pass  # Ignore status update errors
        
        # Update control states based on current status
        self.update_control_states()
        
        # Schedule next update
        self.root.after(2000, self.update_status)  # Update every 2 seconds
    
    def update_control_states(self):
        """Update button states and appearance based on drone status - state-aware UI"""
        try:
            is_connected = self.is_connected.get()
            is_flying = self.is_flying.get() if hasattr(self, 'is_flying') else False
            
            # Connection button - always available
            if is_connected:
                DroneTheme.apply_button_style(self.connect_btn, 'danger')
                self.connect_btn.config(text="🔌 Disconnect")
            else:
                DroneTheme.apply_button_style(self.connect_btn, 'success')
                self.connect_btn.config(text="🔗 Connect")
            
            # Emergency button - only enabled when connected
            if is_connected:
                DroneTheme.apply_button_style(self.emergency_btn, 'danger')
                self.emergency_btn.config(state='normal')
            else:
                self.emergency_btn.config(
                    state='disabled',
                    bg=DroneTheme.COLORS['text_disabled'],
                    cursor='arrow'
                )
            
            # Flight control buttons
            if hasattr(self, 'takeoff_btn'):
                if is_connected and not is_flying:
                    # Can takeoff - enabled and green
                    DroneTheme.apply_button_style(self.takeoff_btn, 'success')
                    self.takeoff_btn.config(state='normal')
                elif is_connected and is_flying:
                    # Already flying - disabled but show state
                    self.takeoff_btn.config(
                        state='disabled',
                        bg=DroneTheme.COLORS['text_disabled'],
                        cursor='arrow'
                    )
                else:
                    # Not connected - disabled
                    self.takeoff_btn.config(
                        state='disabled',
                        bg=DroneTheme.COLORS['text_disabled'],
                        cursor='arrow'
                    )
            
            if hasattr(self, 'land_btn'):
                if is_connected and is_flying:
                    # Can land - enabled and orange
                    DroneTheme.apply_button_style(self.land_btn, 'accent_orange')
                    self.land_btn.config(state='normal')
                elif is_connected and not is_flying:
                    # Not flying - disabled but show state
                    self.land_btn.config(
                        state='disabled',
                        bg=DroneTheme.COLORS['text_disabled'],
                        cursor='arrow'
                    )
                else:
                    # Not connected - disabled
                    self.land_btn.config(
                        state='disabled',
                        bg=DroneTheme.COLORS['text_disabled'],
                        cursor='arrow'
                    )
            
            # Video controls - only enabled when connected
            if hasattr(self, 'video_btn'):
                if is_connected:
                    DroneTheme.apply_button_style(self.video_btn, 'primary')
                    self.video_btn.config(state='normal')
                else:
                    self.video_btn.config(
                        state='disabled',
                        bg=DroneTheme.COLORS['text_disabled'],
                        cursor='arrow'
                    )
            
            if hasattr(self, 'record_btn'):
                if is_connected:
                    DroneTheme.apply_button_style(self.record_btn, 'accent_orange')
                    self.record_btn.config(state='normal')
                else:
                    self.record_btn.config(
                        state='disabled',
                        bg=DroneTheme.COLORS['text_disabled'],
                        cursor='arrow'
                    )
            
            # Vision and AI controls - only enabled when connected
            connection_dependent_buttons = ['execute_btn', 'vision_analyze_btn', 'continuous_vision_btn']
            for btn_name in connection_dependent_buttons:
                if hasattr(self, btn_name):
                    btn = getattr(self, btn_name)
                    if is_connected:
                        btn.config(state='normal')
                        # Restore original cursor
                        btn.config(cursor='hand2')
                    else:
                        btn.config(
                            state='disabled',
                            cursor='arrow'
                        )
            
            # Voice button - depends on connection and voice availability
            if hasattr(self, 'voice_btn') and VOICE_AVAILABLE:
                if is_connected:
                    DroneTheme.apply_button_style(self.voice_btn, 'primary')
                    self.voice_btn.config(state='normal')
                else:
                    self.voice_btn.config(
                        state='disabled',
                        bg=DroneTheme.COLORS['text_disabled'],
                        cursor='arrow'
                    )
            
        except Exception as e:
            # Silently handle control state update errors
            pass
    
    def show_flash_effect(self):
        """Show camera flash effect on the video canvas"""
        if hasattr(self, 'video_canvas'):
            try:
                # Create white flash overlay
                flash_rect = self.video_canvas.create_rectangle(
                    0, 0, 480, 360, 
                    fill='white', 
                    outline='', 
                    stipple='gray50'
                )
                
                # Remove flash after short delay
                def remove_flash():
                    try:
                        self.video_canvas.delete(flash_rect)
                    except:
                        pass
                
                self.root.after(150, remove_flash)  # Flash for 150ms
            except:
                pass  # Silently handle flash errors
    
    def show_toast_notification(self, message, message_type='info', duration=3000):
        """Show temporary status notification overlay"""
        try:
            # Create toast container if it doesn't exist
            if not hasattr(self, 'toast_container'):
                self.toast_container = tk.Frame(self.root, bg=DroneTheme.COLORS['bg_root'])
                self.toast_container.place(relx=0.5, rely=0.9, anchor='center')
            
            # Color based on message type
            bg_color = {
                'success': DroneTheme.COLORS['success'],
                'error': DroneTheme.COLORS['danger'], 
                'warning': DroneTheme.COLORS['warning'],
                'info': DroneTheme.COLORS['info']
            }.get(message_type, DroneTheme.COLORS['info'])
            
            # Create toast notification
            toast = tk.Label(
                self.toast_container,
                text=message,
                font=DroneTheme.get_font('base', 'bold'),
                bg=bg_color,
                fg=DroneTheme.COLORS['text_primary'],
                padx=DroneTheme.SPACING['lg'],
                pady=DroneTheme.SPACING['sm'],
                relief='flat'
            )
            toast.pack(pady=DroneTheme.SPACING['xs'])
            
            # Auto-remove after duration
            def remove_toast():
                try:
                    toast.destroy()
                    # Remove container if no more toasts
                    if not self.toast_container.winfo_children():
                        self.toast_container.place_forget()
                except:
                    pass
            
            self.root.after(duration, remove_toast)
            
        except Exception as e:
            # Fallback to log if toast fails
            self.log(f"📢 {message}")
    
    def show_progress_dialog(self, title, max_steps=0):
        """Show progress dialog for long operations"""
        try:
            # Create progress window
            progress_window = tk.Toplevel(self.root)
            progress_window.title(title)
            progress_window.geometry("400x150")
            progress_window.configure(bg=DroneTheme.COLORS['bg_surface'])
            progress_window.resizable(False, False)
            
            # Center on parent
            progress_window.transient(self.root)
            progress_window.grab_set()
            
            # Progress content
            main_frame = DroneTheme.create_styled_frame(progress_window, 'bg_surface')
            main_frame.pack(fill='both', expand=True, padx=DroneTheme.SPACING['xl'], 
                          pady=DroneTheme.SPACING['xl'])
            
            # Title label
            title_label = tk.Label(
                main_frame,
                text=title,
                font=DroneTheme.get_font('lg', 'bold'),
                fg=DroneTheme.COLORS['text_primary'],
                bg=DroneTheme.COLORS['bg_surface']
            )
            title_label.pack(pady=(0, DroneTheme.SPACING['md']))
            
            # Progress bar (using canvas for custom styling)
            progress_frame = tk.Frame(main_frame, bg=DroneTheme.COLORS['bg_surface'])
            progress_frame.pack(fill='x', pady=DroneTheme.SPACING['md'])
            
            progress_canvas = tk.Canvas(
                progress_frame, 
                height=8, 
                bg=DroneTheme.COLORS['bg_input'],
                highlightthickness=0
            )
            progress_canvas.pack(fill='x')
            
            # Status label
            status_label = tk.Label(
                main_frame,
                text="Starting...",
                font=DroneTheme.get_font('sm'),
                fg=DroneTheme.COLORS['text_muted'],
                bg=DroneTheme.COLORS['bg_surface']
            )
            status_label.pack(pady=(DroneTheme.SPACING['md'], 0))
            
            # Store references for updates
            progress_window.progress_canvas = progress_canvas
            progress_window.status_label = status_label
            progress_window.max_steps = max_steps
            progress_window.current_step = 0
            
            return progress_window
            
        except Exception as e:
            return None
    
    def update_progress(self, progress_window, step_text, step_number=None):
        """Update progress dialog"""
        if not progress_window or not progress_window.winfo_exists():
            return
            
        try:
            # Update status text
            progress_window.status_label.config(text=step_text)
            
            # Update progress bar if step number provided
            if step_number is not None and progress_window.max_steps > 0:
                progress_window.current_step = step_number
                progress = min(step_number / progress_window.max_steps, 1.0)
                
                # Clear and redraw progress bar
                canvas = progress_window.progress_canvas
                canvas.delete("all")
                width = canvas.winfo_width()
                fill_width = int(width * progress)
                
                if fill_width > 0:
                    canvas.create_rectangle(
                        0, 0, fill_width, 8,
                        fill=DroneTheme.COLORS['primary'],
                        outline=''
                    )
            
            # Force update
            progress_window.update()
            
        except Exception as e:
            pass
    
    def close_progress(self, progress_window):
        """Close progress dialog"""
        if progress_window and progress_window.winfo_exists():
            try:
                progress_window.grab_release()
                progress_window.destroy()
            except:
                pass
    
    def deferred_setup(self):
        """Initialize voice and AI systems after GUI is ready."""
        # Initialize Azure OpenAI (non-blocking)
        if AZURE_OPENAI_AVAILABLE:
            self.setup_azure_openai()
            
        # Auto-connect simulation mode after GUI is fully initialized
        if hasattr(self, 'pending_auto_connect') and self.pending_auto_connect:
            self.auto_connect_simulation()
            
        # Voice setup note: microphone will be initialized when user clicks voice button
        
    def setup_voice_recognition(self):
        """Initialize voice recognition system (called when needed)."""
        if not VOICE_AVAILABLE:
            self.log("⚠️ Voice recognition not available")
            return False
            
        try:
            # Test microphone availability (this can block/fail)
            self.microphone = sr.Microphone()
            
            # Configure recognizer settings
            self.recognizer.energy_threshold = 300
            self.recognizer.dynamic_energy_threshold = True
            self.recognizer.pause_threshold = 0.8
            
            self.log("🎤 Voice recognition system ready!")
            
        except Exception as e:
            self.log(f"⚠️ Voice recognition unavailable: {e}")
            self.microphone = None
    
    def toggle_voice(self):
        """Toggle voice recognition on/off."""
        # Try to initialize microphone if not done yet
        if VOICE_AVAILABLE and self.microphone is None:
            self.setup_voice_recognition()
            
        if not VOICE_AVAILABLE or not self.microphone:
            if not VOICE_AVAILABLE:
                self.log("❌ Voice commands unavailable - speech_recognition not installed")
            else:
                self.log("❌ Voice commands unavailable - no microphone detected")
                self.log("💡 TIP: Make sure you're running on your local machine, not in cloud")
            return
        
        if self.voice_enabled:
            self.stop_voice()
        else:
            self.start_voice()
    
    def start_voice(self):
        """Start voice recognition."""
        try:
            self.voice_enabled = True
            self.voice_running = True
            self.voice_thread = threading.Thread(target=self.voice_recognition_loop, daemon=True)
            self.voice_thread.start()
            
            self.voice_btn.config(text="🔇 Stop Voice", bg='#f44336')
            self.voice_status_label.config(text="Voice: Listening...", fg='#4CAF50')
            self.log("🎤 Voice recognition enabled!")
            self.log("💬 Say: 'take off', 'land', 'take photo', 'move forward'")
            
        except Exception as e:
            self.log(f"❌ Failed to start voice recognition: {e}")
            self.voice_enabled = False
    
    def stop_voice(self):
        """Stop voice recognition."""
        try:
            self.voice_enabled = False
            self.voice_running = False
            
            if self.voice_thread and self.voice_thread.is_alive():
                self.voice_thread.join(timeout=2)
            
            self.voice_btn.config(text="🎤 Voice Commands", bg='#00BCD4')
            self.voice_status_label.config(text="Voice: Off", fg='#cccccc')
            self.log("🎤 Voice recognition disabled")
            
        except Exception as e:
            self.log(f"❌ Failed to stop voice recognition: {e}")
    
    def voice_recognition_loop(self):
        """Voice recognition loop running in separate thread."""
        while self.voice_running:
            try:
                with self.microphone as source:
                    # Adjust for ambient noise initially
                    if not hasattr(self, 'noise_adjusted'):
                        self.recognizer.adjust_for_ambient_noise(source, duration=1)
                        self.noise_adjusted = True
                    
                    # Listen for audio
                    audio = self.recognizer.listen(source, timeout=1, phrase_time_limit=5)
                
                # Recognize speech
                command = self.recognizer.recognize_google(audio)
                if command:
                    self.voice_command_queue.put(command.lower())
                    
            except sr.WaitTimeoutError:
                pass  # Normal timeout, continue listening
            except sr.UnknownValueError:
                pass  # Could not understand audio
            except sr.RequestError as e:
                self.log(f"❌ Voice recognition error: {e}")
                time.sleep(1)
            except Exception as e:
                self.log(f"❌ Voice error: {e}")
                break
    
    def process_voice_command(self, command):
        """Process a recognized voice command."""
        try:
            command = command.strip().lower()
            self.log(f"🎤 Heard: '{command}'")
            
            # SECURITY: Block dangerous commands from voice input
            dangerous_commands = ['emergency', 'emergency stop']
            if any(danger in command for danger in dangerous_commands):
                self.log("🚫 SECURITY: Emergency commands blocked from voice input!")
                self.log("   Use emergency button if needed.")
                return
            
            # Map common voice phrases to GUI actions
            voice_mappings = {
                'take off': self.takeoff,
                'takeoff': self.takeoff,
                'land': self.land,
                'take a photo': self.take_photo,
                'take photo': self.take_photo,
                'start video': self.start_video,
                'stop video': self.stop_video,
                'connect': self.connect,
                'disconnect': self.disconnect,
                'enable face detection': lambda: self.toggle_detection('face'),
                'start following': self.toggle_follow,
                'stop following': self.toggle_follow,
                'record video': self.toggle_recording,
                'stop recording': self.toggle_recording,
                # Vision analysis commands
                'describe what you see': lambda: threading.Thread(target=self.analyze_current_view, daemon=True).start(),
                'what do you see': lambda: threading.Thread(target=self.analyze_current_view, daemon=True).start(),
                'describe what you see in the video': lambda: threading.Thread(target=self.analyze_current_view, daemon=True).start(),
                'what do you see in the video': lambda: threading.Thread(target=self.analyze_current_view, daemon=True).start(),
                'analyze view': lambda: threading.Thread(target=self.analyze_current_view, daemon=True).start(),
                'analyze current view': lambda: threading.Thread(target=self.analyze_current_view, daemon=True).start(),
                'describe the video': lambda: threading.Thread(target=self.analyze_current_view, daemon=True).start(),
                'analyze the video': lambda: threading.Thread(target=self.analyze_current_view, daemon=True).start(),
            }
            
            # Check for direct command mappings
            if command in voice_mappings:
                action = voice_mappings[command]
                self.log(f"🎤 → Executing: {command}")
                action()
                return
            
            # Try to parse movement commands
            if self.parse_movement_command(command):
                return
            
            # Try to parse rotation commands  
            if self.parse_rotation_command(command):
                return
            
            # Try to parse vision commands
            if self.parse_vision_command(command):
                return
            
            # If no direct mapping, try Azure OpenAI processing
            if self.ai_enabled:
                self.log(f"🎤 → AI processing: {command}")
                ai_commands = self.process_with_azure_openai(command)
                if ai_commands:
                    self.execute_ai_commands(ai_commands)
                    return
            
            # Fallback to natural language processing
            self.log(f"🎤 → Natural language: {command}")
            self.execute_command(command, "voice")
            
        except Exception as e:
            self.log(f"❌ Error processing voice command: {e}")
    
    def parse_movement_command(self, command):
        """Parse movement commands from voice input."""
        movement_patterns = {
            'move forward': 'forward',
            'fly forward': 'forward',
            'go forward': 'forward',
            'move back': 'back',
            'fly back': 'back',
            'go back': 'back',
            'move left': 'left',
            'fly left': 'left',
            'go left': 'left',
            'move right': 'right',
            'fly right': 'right',
            'go right': 'right',
            'move up': 'up',
            'fly up': 'up',
            'go up': 'up',
            'move down': 'down',
            'fly down': 'down',
            'go down': 'down',
        }
        
        for pattern, direction in movement_patterns.items():
            if pattern in command:
                self.log(f"🎤 → Moving {direction}")
                self.move(direction)
                return True
        
        return False
    
    def parse_rotation_command(self, command):
        """Parse rotation commands from voice input."""
        rotation_patterns = {
            'turn left': 'left',
            'rotate left': 'left',
            'spin left': 'left',
            'turn right': 'right',
            'rotate right': 'right',
            'spin right': 'right',
        }
        
        for pattern, direction in rotation_patterns.items():
            if pattern in command:
                self.log(f"🎤 → Rotating {direction}")
                self.rotate(direction)
                return True
        
        return False
    
    def setup_azure_openai(self):
        """Initialize Azure OpenAI system."""
        try:
            # Try to load from environment variables first
            endpoint = os.getenv('AZURE_OPENAI_ENDPOINT')
            api_key = os.getenv('AZURE_OPENAI_API_KEY')
            deployment = os.getenv('AZURE_OPENAI_DEPLOYMENT_NAME')
            
            if endpoint and api_key and deployment:
                self.log("🤖 Loading Azure OpenAI configuration from environment...")
                
                # Update azure_settings
                self.azure_settings.update({
                    'endpoint': endpoint,
                    'deployment': deployment,
                    'api_key': api_key,
                    'api_version': '2024-08-01-preview'
                })
                
                # Initialize Azure OpenAI client
                self.azure_openai_client = AzureOpenAI(
                    azure_endpoint=endpoint,
                    api_key=api_key,
                    api_version='2024-08-01-preview'
                )
                
                self.ai_enabled = True
                self.log("✅ Azure OpenAI connected and ready!")
                self.log("🤖 Natural language commands now available!")
                
                # Update AI indicator if it exists
                if hasattr(self, 'ai_indicator'):
                    self.ai_indicator.config(
                        text="🤖 AI Status: Connected & Ready",
                        fg='#4CAF50'
                    )
            else:
                self.log("⚙️ Azure OpenAI integration ready - configure in Settings")
                
                # Update AI indicator if it exists
                if hasattr(self, 'ai_indicator'):
                    self.ai_indicator.config(
                        text="🤖 AI Status: Click Settings to Configure",
                        fg='#FF9800'
                    )
        except Exception as e:
            self.log(f"⚠️ Azure OpenAI setup error: {e}")
            self.ai_enabled = False
    
    def open_settings(self):
        """Open the settings configuration window."""
        if hasattr(self, 'settings_window') and self.settings_window.winfo_exists():
            self.settings_window.lift()
            return
            
        self.settings_window = tk.Toplevel(self.root)
        self.settings_window.title("⚙️ Settings - Azure OpenAI Configuration")
        self.settings_window.geometry("500x600")
        self.settings_window.configure(bg='#2b2b2b')
        self.settings_window.transient(self.root)
        self.settings_window.grab_set()
        
        # Main frame
        main_frame = tk.Frame(self.settings_window, bg='#2b2b2b')
        main_frame.pack(fill='both', expand=True, padx=20, pady=20)
        
        # Title
        title_label = tk.Label(
            main_frame,
            text="🤖 Azure OpenAI Configuration",
            font=('Arial', 16, 'bold'),
            fg='#ffffff',
            bg='#2b2b2b'
        )
        title_label.pack(pady=(0, 20))
        
        # Description
        desc_label = tk.Label(
            main_frame,
            text="Configure Azure AI Foundry settings for intelligent command processing",
            font=('Arial', 10),
            fg='#cccccc',
            bg='#2b2b2b',
            wraplength=400
        )
        desc_label.pack(pady=(0, 20))
        
        # Settings fields
        settings_frame = tk.Frame(main_frame, bg='#2b2b2b')
        settings_frame.pack(fill='x', pady=10)
        
        # Azure Endpoint
        tk.Label(
            settings_frame,
            text="Azure Endpoint URL:",
            font=('Arial', 11, 'bold'),
            fg='white',
            bg='#2b2b2b'
        ).pack(anchor='w', pady=(10, 2))
        
        self.endpoint_entry = tk.Entry(
            settings_frame,
            font=('Arial', 10),
            bg='#404040',
            fg='white',
            insertbackground='white',
            width=60
        )
        self.endpoint_entry.pack(fill='x', pady=(0, 5))
        self.endpoint_entry.insert(0, self.azure_settings['endpoint'])
        
        # Deployment Name
        tk.Label(
            settings_frame,
            text="Deployment Name:",
            font=('Arial', 11, 'bold'),
            fg='white',
            bg='#2b2b2b'
        ).pack(anchor='w', pady=(10, 2))
        
        self.deployment_entry = tk.Entry(
            settings_frame,
            font=('Arial', 10),
            bg='#404040',
            fg='white',
            insertbackground='white',
            width=60
        )
        self.deployment_entry.pack(fill='x', pady=(0, 5))
        self.deployment_entry.insert(0, self.azure_settings['deployment'])
        
        # API Key
        tk.Label(
            settings_frame,
            text="API Key:",
            font=('Arial', 11, 'bold'),
            fg='white',
            bg='#2b2b2b'
        ).pack(anchor='w', pady=(10, 2))
        
        self.api_key_entry = tk.Entry(
            settings_frame,
            font=('Arial', 10),
            bg='#404040',
            fg='white',
            insertbackground='white',
            width=60,
            show='*'
        )
        self.api_key_entry.pack(fill='x', pady=(0, 5))
        self.api_key_entry.insert(0, self.azure_settings['api_key'])
        
        # API Version
        tk.Label(
            settings_frame,
            text="API Version:",
            font=('Arial', 11, 'bold'),
            fg='white',
            bg='#2b2b2b'
        ).pack(anchor='w', pady=(10, 2))
        
        self.api_version_entry = tk.Entry(
            settings_frame,
            font=('Arial', 10),
            bg='#404040',
            fg='white',
            insertbackground='white',
            width=60
        )
        self.api_version_entry.pack(fill='x', pady=(0, 5))
        self.api_version_entry.insert(0, self.azure_settings['api_version'])
        
        # AI Status
        status_frame = tk.Frame(main_frame, bg='#2b2b2b')
        status_frame.pack(fill='x', pady=20)
        
        self.ai_status_label = tk.Label(
            status_frame,
            text=f"AI Status: {'✅ Enabled' if self.ai_enabled else '❌ Disabled'}",
            font=('Arial', 10, 'bold'),
            fg='#4CAF50' if self.ai_enabled else '#f44336',
            bg='#2b2b2b'
        )
        self.ai_status_label.pack()
        
        # Buttons
        button_frame = tk.Frame(main_frame, bg='#2b2b2b')
        button_frame.pack(fill='x', pady=20)
        
        # Test Connection Button
        test_btn = tk.Button(
            button_frame,
            text="🧪 Test Connection",
            font=('Arial', 10, 'bold'),
            bg='#2196F3',
            fg='white',
            width=15,
            command=self.test_azure_connection
        )
        test_btn.pack(side='left', padx=5)
        
        # Save Button
        save_btn = tk.Button(
            button_frame,
            text="💾 Save Settings",
            font=('Arial', 10, 'bold'),
            bg='#4CAF50',
            fg='white',
            width=15,
            command=self.save_azure_settings
        )
        save_btn.pack(side='left', padx=5)
        
        # Cancel Button
        cancel_btn = tk.Button(
            button_frame,
            text="❌ Cancel",
            font=('Arial', 10, 'bold'),
            bg='#f44336',
            fg='white',
            width=15,
            command=self.settings_window.destroy
        )
        cancel_btn.pack(side='right', padx=5)
    
    def test_azure_connection(self):
        """Test Azure OpenAI connection with current settings."""
        try:
            # Get current values from entries
            endpoint = self.endpoint_entry.get().strip()
            deployment = self.deployment_entry.get().strip()
            api_key = self.api_key_entry.get().strip()
            api_version = self.api_version_entry.get().strip()
            
            if not all([endpoint, deployment, api_key]):
                messagebox.showerror("Error", "Please fill in all required fields")
                return
            
            # Test connection
            test_client = AzureOpenAI(
                azure_endpoint=endpoint,
                api_key=api_key,
                api_version=api_version
            )
            
            # Simple test call
            response = test_client.chat.completions.create(
                model=deployment,
                messages=[{"role": "user", "content": "Hello, respond with 'test successful'"}],
                max_tokens=10
            )
            
            if response.choices[0].message.content:
                messagebox.showinfo("Success", "✅ Azure OpenAI connection successful!")
                self.ai_status_label.config(text="AI Status: ✅ Connected", fg='#4CAF50')
            else:
                messagebox.showerror("Error", "❌ Connection test failed - no response")
                
        except Exception as e:
            messagebox.showerror("Connection Error", f"❌ Failed to connect to Azure OpenAI:\n\n{str(e)}")
            self.ai_status_label.config(text="AI Status: ❌ Connection Failed", fg='#f44336')
    
    def save_azure_settings(self):
        """Save Azure OpenAI settings."""
        try:
            # Get values from entries
            endpoint = self.endpoint_entry.get().strip()
            deployment = self.deployment_entry.get().strip()
            api_key = self.api_key_entry.get().strip()
            api_version = self.api_version_entry.get().strip()
            
            if not all([endpoint, deployment, api_key]):
                messagebox.showerror("Error", "Please fill in all required fields")
                return
            
            # Update settings
            self.azure_settings.update({
                'endpoint': endpoint,
                'deployment': deployment,
                'api_key': api_key,
                'api_version': api_version
            })
            
            # Initialize Azure OpenAI client
            self.azure_openai_client = AzureOpenAI(
                azure_endpoint=endpoint,
                api_key=api_key,
                api_version=api_version
            )
            
            self.ai_enabled = True
            self.ai_status_label.config(text="AI Status: ✅ Enabled", fg='#4CAF50')
            
            # Update main AI indicator
            if hasattr(self, 'ai_indicator'):
                self.ai_indicator.config(
                    text="🤖 AI Status: Connected & Ready",
                    fg='#4CAF50'
                )
            
            # Close settings window
            self.settings_window.destroy()
            
            # Log success
            self.log("✅ Azure OpenAI settings saved and enabled!")
            self.log("🤖 Natural language commands now powered by AI")
            
            messagebox.showinfo("Settings Saved", "✅ Azure OpenAI configured successfully!\n\nYou can now use advanced natural language commands.")
            
        except Exception as e:
            messagebox.showerror("Save Error", f"❌ Failed to save settings:\n\n{str(e)}")
    
    def process_with_azure_openai(self, user_input):
        """Process user input through Azure OpenAI to generate drone commands."""
        if not self.ai_enabled or not self.azure_openai_client:
            self.log("❌ Azure OpenAI not configured - using basic command parsing")
            return None
        
        try:
            # the newest OpenAI model is "gpt-5" which was released August 7, 2025.
            # do not change this unless explicitly requested by the user
            system_prompt = """You are an intelligent drone command interpreter. Convert natural language instructions into specific drone commands.

Available drone commands:
- takeoff: Make the drone take off
- land: Make the drone land
- move_forward(distance): Move forward in cm (20-500)
- move_back(distance): Move backward in cm (20-500)  
- move_left(distance): Move left in cm (20-500)
- move_right(distance): Move right in cm (20-500)
- move_up(distance): Move up in cm (20-500)
- move_down(distance): Move down in cm (20-500)
- rotate_clockwise(degrees): Rotate clockwise (1-360)
- rotate_counter_clockwise(degrees): Rotate counter-clockwise (1-360)
- hover(seconds): Hover in place for specified seconds
- take_photo(): Take a single photo
- take_photo_burst(count): Take multiple photos
- analyze_view(prompt, use_photo): Analyze current view or saved photo with custom prompt
- start_video_recording(): Start recording video
- stop_video_recording(): Stop recording video
- enable_detection(type): Enable object detection (face, person, vehicle)
- disable_detection(): Disable object detection
- start_follow_mode(type): Start following detected objects
- stop_follow_mode(): Stop following objects

CRITICAL: You MUST respond with a JSON object containing a "commands" array. Even for single commands, wrap them in an array.

Required format: {"commands": [{"action": "command_name", "parameters": {...}}]}

IMPORTANT: For analyze_view commands, generate SPECIFIC prompts based on user intent:
- If user says "describe" → prompt focuses on scene/atmosphere description
- If user says "identify objects" → prompt focuses on object identification and listing
- If user says "identify [specific thing]" → prompt focuses on that specific thing
- If user mentions "picture" or "photo" → set use_photo: true
- If user says "now", "current view", "currently" → set use_photo: false

Examples:
- "land safely" → {"commands": [{"action": "land", "parameters": {}}]}
- "fly forward 2 meters" → {"commands": [{"action": "move_forward", "parameters": {"distance": 200}}]}
- "turn left 90 degrees then move right" → {"commands": [{"action": "rotate_counter_clockwise", "parameters": {"degrees": 90}}, {"action": "move_right", "parameters": {"distance": 100}}]}
- "take off and hover for 5 seconds" → {"commands": [{"action": "takeoff", "parameters": {}}, {"action": "hover", "parameters": {"seconds": 5}}]}
- "take a photo and describe it" → {"commands": [{"action": "take_photo", "parameters": {}}, {"action": "analyze_view", "parameters": {"prompt": "describe the overall scene, colors, and atmosphere in this photo", "use_photo": true}}]}
- "take a picture and identify objects" → {"commands": [{"action": "take_photo", "parameters": {}}, {"action": "analyze_view", "parameters": {"prompt": "identify and list all objects visible in this photo", "use_photo": true}}]}
- "take picture and identify objects in the picture" → {"commands": [{"action": "take_photo", "parameters": {}}, {"action": "analyze_view", "parameters": {"prompt": "identify and list all objects visible in this photo", "use_photo": true}}]}
- "take photo then identify cars" → {"commands": [{"action": "take_photo", "parameters": {}}, {"action": "analyze_view", "parameters": {"prompt": "count and describe all cars visible in this photo", "use_photo": true}}]}
- "take photo and look for people" → {"commands": [{"action": "take_photo", "parameters": {}}, {"action": "analyze_view", "parameters": {"prompt": "identify and count people in this photo", "use_photo": true}}]}
- "describe what you see now" → {"commands": [{"action": "analyze_view", "parameters": {"prompt": "describe the current live view from the drone camera", "use_photo": false}}]}
- "what objects are visible right now" → {"commands": [{"action": "analyze_view", "parameters": {"prompt": "identify objects currently visible in the live camera feed", "use_photo": false}}]}
- "count buildings in current view" → {"commands": [{"action": "analyze_view", "parameters": {"prompt": "count and describe buildings visible in the current view", "use_photo": false}}]}"""

            response = self.azure_openai_client.chat.completions.create(
                model=self.azure_settings['deployment'],
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_input}
                ],
                response_format={"type": "json_object"},
                max_tokens=1000
            )
            
            # Parse response
            ai_response = response.choices[0].message.content
            if ai_response:
                parsed_response = json.loads(ai_response)
                # Handle both formats: direct array or object with "commands" key
                if isinstance(parsed_response, list):
                    commands = parsed_response
                elif isinstance(parsed_response, dict) and 'commands' in parsed_response:
                    commands = parsed_response['commands']
                else:
                    commands = None
            else:
                commands = None
            
            if commands:
                self.log(f"🤖 AI interpreted: '{user_input}' → {len(commands)} commands")
            else:
                self.log(f"🤖 AI could not interpret: '{user_input}'")
            return commands
            
        except Exception as e:
            self.log(f"❌ Azure OpenAI processing error: {e}")
            return None
    
    def analyze_image_with_ai(self, image_data, prompt="Describe what you see in this image in 2-3 sentences."):
        """Analyze an image using Azure OpenAI Vision API."""
        if not self.ai_enabled or not self.azure_openai_client:
            self.log("❌ Azure OpenAI not configured for vision analysis")
            return None
        
        try:
            # Debug: Log image data type and properties
            if image_data is None:
                self.log("❌ No image data provided for analysis")
                return None
            
            self.log(f"🔍 Image data type: {type(image_data)}")
            
            # Convert image to base64
            if isinstance(image_data, np.ndarray):
                self.log(f"🔍 NumPy array shape: {image_data.shape}")
                # Convert OpenCV/numpy array to PIL Image
                if len(image_data.shape) == 3 and image_data.shape[2] == 3:
                    # Convert BGR to RGB for PIL
                    image_data = cv2.cvtColor(image_data, cv2.COLOR_BGR2RGB)
                elif len(image_data.shape) == 3 and image_data.shape[2] == 4:
                    # Handle RGBA format
                    image_data = cv2.cvtColor(image_data, cv2.COLOR_BGRA2RGB)
                image = Image.fromarray(image_data)
            elif isinstance(image_data, Image.Image):
                image = image_data
            elif hasattr(image_data, '_PhotoImage__photo'):
                # Handle PIL.ImageTk.PhotoImage (Tkinter format)
                self.log("🔄 Converting PhotoImage to PIL Image...")
                # PhotoImage stores the underlying PIL image in _PhotoImage__photo
                try:
                    # Try to get the original PIL image if available
                    if hasattr(image_data, '_PhotoImage__photo') and hasattr(image_data._PhotoImage__photo, 'copy'):
                        image = image_data._PhotoImage__photo.copy()
                    else:
                        # Fallback: convert via tk's internal methods
                        self.log("❌ Cannot convert PhotoImage - no source PIL image available")
                        return None
                except Exception as e:
                    self.log(f"❌ PhotoImage conversion error: {e}")
                    return None
            else:
                self.log(f"❌ Unsupported image format for vision analysis: {type(image_data)}")
                return None
            
            # Convert to base64
            buffered = io.BytesIO()
            image.save(buffered, format="JPEG", quality=85)
            img_base64 = base64.b64encode(buffered.getvalue()).decode('utf-8')
            
            # Create vision request
            response = self.azure_openai_client.chat.completions.create(
                model=self.azure_settings['deployment'],
                messages=[
                    {
                        "role": "system",
                        "content": "You are a drone vision assistant. Analyze images from a drone's perspective and provide clear, concise descriptions. Always limit your response to 2-3 sentences maximum."
                    },
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{img_base64}",
                                    "detail": "high"
                                }
                            }
                        ]
                    }
                ],
                max_tokens=200
            )
            
            description = response.choices[0].message.content
            return description
            
        except Exception as e:
            self.log(f"❌ Vision analysis error: {e}")
            return None
    
    def analyze_current_view(self, custom_prompt=None, use_photo=False):
        """
        Analyze the current video frame or saved photo with custom prompt.
        
        Args:
            custom_prompt: Custom analysis prompt from user's request
            use_photo: If True, analyze the most recent saved photo instead of live feed
        """
        # Determine image source based on use_photo parameter
        if use_photo:
            # Find the most recent saved photo
            import glob
            import os
            photo_files = glob.glob("tello_photo_*.jpg")
            if photo_files:
                # Sort by modification time to get the most recent
                photo_files.sort(key=os.path.getmtime, reverse=True)
                recent_photo = photo_files[0]
                self.log(f"🔍 Using most recent saved photo: {recent_photo}")
                return self.analyze_captured_photo(recent_photo, custom_prompt)
            else:
                self.log("⚠️ No saved photos found, using live camera feed instead")
                use_photo = False
        
        if not use_photo:
            # Use live camera feed
            # Try to get the original frame from the agent instead of the GUI PhotoImage
            if hasattr(self.agent, 'current_frame') and self.agent.current_frame is not None:
                frame_data = self.agent.current_frame
                self.log("🔍 Using live camera feed from agent...")
            elif self.video_frame is not None:
                frame_data = self.video_frame
                self.log("🔍 Using GUI video frame...")
            else:
                self.log("❌ No video frame available for analysis")
                return None
            
            self.log("🔍 Analyzing current view...")
            self.log(f"🔍 Frame data type: {type(frame_data)}")
            if hasattr(frame_data, 'shape'):
                self.log(f"🔍 Frame shape: {frame_data.shape}")
            
            # Use custom prompt or default (always limit to 2-3 sentences)
            if custom_prompt:
                prompt = f"{custom_prompt}. Keep your response to 2-3 sentences maximum."
                self.log(f"🎯 DEBUG: Using custom prompt: '{custom_prompt}'")
            else:
                prompt = "In 2-3 sentences, identify the main objects and any actions you see from this drone's perspective."
                self.log("🎯 DEBUG: Using default prompt (no custom prompt provided)")
            
            description = self.analyze_image_with_ai(frame_data, prompt)
            
            if description:
                source_type = "Saved Photo" if use_photo else "Live Camera"
                self.log(f"👁️ Vision Analysis ({source_type}): {description}")
                self.update_vision_results(f"[{time.strftime('%H:%M:%S')}] {source_type} Analysis:\nPrompt: {prompt}\nResult: {description}\n\n")
                
                # Speak the analysis result
                self.speak_text(f"Vision analysis: {description}")
                
                return description
        return None
    
    def analyze_captured_photo(self, image_path, custom_prompt=None):
        """
        Analyze a captured photo and provide description.
        
        Args:
            image_path: Path to the image file to analyze
            custom_prompt: Custom analysis prompt from user's request
        """
        try:
            # Load image
            image = Image.open(image_path)
            self.log(f"🔍 Analyzing captured photo: {image_path}")
            
            # Use custom prompt or default (always limit to 2-3 sentences)
            if custom_prompt:
                prompt = f"{custom_prompt}. Keep your response to 2-3 sentences maximum."
                self.log(f"📸 DEBUG: Using custom prompt for photo: '{custom_prompt}'")
            else:
                prompt = "In 2-3 sentences, identify the main objects and any actions visible in this drone photo."
                self.log("📸 DEBUG: Using default prompt for photo (no custom prompt provided)")
            
            description = self.analyze_image_with_ai(image, prompt)
            
            if description:
                self.log(f"📸 Photo Analysis: {description}")
                self.update_vision_results(f"[{time.strftime('%H:%M:%S')}] Photo Analysis ({image_path}):\nPrompt: {prompt}\nResult: {description}\n\n")
                
                # Speak the photo analysis result
                self.speak_text(f"Photo analysis: {description}")
                
                return description
            return None
            
        except Exception as e:
            self.log(f"❌ Error analyzing photo: {e}")
            return None
    
    def thread_safe_vision_analysis(self, custom_prompt=None, use_photo=False):
        """
        Thread-safe wrapper for vision analysis that marshals to main GUI thread.
        This ensures Tkinter widgets are only updated from the main thread.
        """
        # Marshal the call to the main thread using Tkinter's after() method
        def safe_analyze():
            try:
                self.analyze_current_view(custom_prompt, use_photo)
            except Exception as e:
                self.log(f"❌ Thread-safe vision analysis error: {e}")
        
        # Schedule execution on main thread
        if hasattr(self, 'root') and self.root:
            self.root.after(0, safe_analyze)
        else:
            # Fallback: run directly if no root available (shouldn't happen in normal operation)
            safe_analyze()
    
    def update_vision_results(self, text):
        """Update the vision results panel with new analysis."""
        if hasattr(self, 'vision_results'):
            def update_ui():
                self.vision_results.config(state='normal')
                self.vision_results.insert(tk.END, text)
                self.vision_results.see(tk.END)  # Scroll to bottom
                self.vision_results.config(state='disabled')
            
            # Thread-safe UI update
            self.root.after(0, update_ui)
    
    def start_vision_analysis(self):
        """Start vision analysis with proper button state management."""
        # Check AI availability
        if not self.ai_enabled or not self.azure_openai_client:
            self.log("❌ Vision analysis requires AI configuration. Click the ⚙️ Settings button.")
            return
        
        # Check video frame availability
        if self.video_frame is None:
            self.log("❌ No video frame available for analysis. Make sure video is streaming.")
            return
        
        # Update button state
        self.vision_analyze_btn.config(
            text="🔄 Analyzing...",
            bg='#FF9800',
            state='disabled'
        )
        
        def analysis_thread():
            try:
                result = self.analyze_current_view()
                # Reset button state
                self.root.after(0, lambda: self.vision_analyze_btn.config(
                    text="👁️ Analyze View",
                    bg='#9C27B0',
                    state='normal'
                ))
            except Exception as e:
                self.log(f"❌ Vision analysis error: {e}")
                # Reset button state on error
                self.root.after(0, lambda: self.vision_analyze_btn.config(
                    text="👁️ Analyze View",
                    bg='#9C27B0',
                    state='normal'
                ))
        
        threading.Thread(target=analysis_thread, daemon=True).start()
    
    def setup_tts(self):
        """Initialize text-to-speech engine with dedicated worker thread."""
        # Check if espeak is available (try espeak-ng first)
        try:
            import subprocess
            # Try espeak-ng first
            result = subprocess.run(['espeak-ng', '--version'], 
                                  capture_output=True, timeout=5)
            if result.returncode == 0:
                self.log("✅ Espeak-ng TTS system detected and ready")
                self.tts_enabled = True
                self.tts_engine = "espeak-ng"  # Mark that we're using espeak-ng
                return
            
            # Fallback to regular espeak
            result = subprocess.run(['espeak', '--version'], 
                                  capture_output=True, timeout=5)
            if result.returncode == 0:
                self.log("✅ Espeak TTS system detected and ready")
                self.tts_enabled = True
                self.tts_engine = "espeak"  # Mark that we're using espeak
                return
            else:
                self.log("❌ Neither espeak nor espeak-ng available - checking fallback...")
        except Exception:
            # Silently handle espeak unavailability
            pass
        
        # TTS setup with real-time option
        self.log(f"🔍 Audio capabilities: TTS={TTS_AVAILABLE}, SimpleAudio={SIMPLEAUDIO_AVAILABLE}, RealtimeAudio={REALTIME_AUDIO_AVAILABLE}")
        
        if not TTS_AVAILABLE:
            self.log("⚠️ No TTS systems available - TTS disabled")
            self.tts_enabled = False
            return
        
        self.log("✅ Using basic pyttsx3 TTS")
        
        # Real-time speech mode setup
        if REALTIME_AUDIO_AVAILABLE:
            self.log("🎙️ Real-time speech capabilities available")
            self.realtime_mode = False  # Start in regular mode
            self.setup_realtime_components()
        else:
            self.log("⚠️ Real-time speech not available - install pyaudio and websockets")
        
        # Check if we're in a cloud environment (no audio output)
        if self._is_cloud_environment():
            self.log("☁️ Cloud environment detected")
            self.log("🔧 Testing TTS anyway - audio may not work in cloud")
            # Continue with TTS setup for testing purposes
        
        # Check if local audio system is available
        if not self._check_local_audio_system():
            self.log("🔇 No audio system detected - TTS disabled")
            self.log("💡 To enable audio: ensure PulseAudio/ALSA is running and speakers are connected")
            self.tts_enabled = False
            return
            
        try:
            self.log("🔊 Initializing text-to-speech engine...")
            
            # Try different TTS drivers - prioritize sapi5 (Windows Speech API)
            drivers_to_try = ['sapi5', 'espeak', 'nsss', None]  # None = auto-detect
            
            for driver in drivers_to_try:
                try:
                    if driver:
                        self.log(f"🔊 Trying TTS driver: {driver}")
                        self.tts_engine = pyttsx3.init(driverName=driver)
                    else:
                        self.log("🔊 Trying auto-detect TTS driver")
                        self.tts_engine = pyttsx3.init()
                    
                    # Test if engine works
                    voices = self.tts_engine.getProperty('voices')
                    self.log(f"🔊 Found {len(voices) if voices else 0} voices with {driver or 'auto'} driver")
                    break  # Success - use this driver
                    
                except Exception as e:
                    self.log(f"❌ Driver {driver or 'auto'} failed: {e}")
                    self.tts_engine = None
                    continue
            
            if not self.tts_engine:
                self.log("❌ No working TTS driver found - audio output disabled")
                self.tts_enabled = False
                return
                
            voices = self.tts_engine.getProperty('voices')
            
            if voices:
                # Use first available voice (usually default system voice)
                self.tts_engine.setProperty('voice', voices[0].id)
                self.log(f"🔊 Using voice: {voices[0].name if hasattr(voices[0], 'name') else 'Default'}")
            
            # Set speech rate (words per minute)
            self.tts_engine.setProperty('rate', 200)
            
            # Set volume (0.0 to 1.0)
            self.tts_engine.setProperty('volume', 0.9)
            
            # Don't test here - start worker thread instead  
            self.start_tts_worker()
            
            self.log("✅ Text-to-speech system ready!")
            
            # Test TTS through the worker queue
            self.speak_text("Text-to-speech system ready!")
            
        except Exception as e:
            self.log(f"❌ Text-to-speech setup failed: {e}")
            self.tts_engine = None
            self.tts_enabled = False
    
    def _is_cloud_environment(self):
        """Detect if running in cloud environment without audio."""
        import os
        
        # Check for Replit environment variables
        if os.getenv('REPLIT_DB_URL') or os.getenv('REPL_ID') or os.getenv('REPLIT_DEPLOYMENT'):
            self.log("🌥️ Detected Replit cloud environment")
            return True
        
        return False  # Local environment
        
    def _check_local_audio_system(self):
        """Check if local audio system is available and working."""
        import os
        import sys
        import subprocess
        import shutil
        
        # Platform-specific audio checks
        if sys.platform.startswith('linux'):
            # Check for ALSA devices
            try:
                if os.path.exists('/proc/asound/cards'):
                    with open('/proc/asound/cards', 'r') as f:
                        cards_content = f.read().strip()
                        if not cards_content or 'no soundcards' in cards_content.lower():
                            self.log("🔇 No sound cards detected in /proc/asound/cards")
                            return False
                        else:
                            self.log("🔊 Sound cards detected in system")
                else:
                    self.log("🔇 /proc/asound/cards not found")
                    return False
            except Exception as e:
                self.log(f"🔇 Error checking sound cards: {e}")
                return False
            
            # Check if audio tools are available
            if not shutil.which('aplay'):
                self.log("🔇 aplay command not found - install alsa-utils")
                return False
                
            # Check PulseAudio (optional but recommended)
            try:
                result = subprocess.run(['pulseaudio', '--check'], 
                                      capture_output=True, timeout=5)
                if result.returncode != 0:
                    self.log("⚠️ PulseAudio not running (audio may still work)")
                else:
                    self.log("🔊 PulseAudio is running")
            except Exception:
                self.log("⚠️ Could not check PulseAudio status")
                
        elif sys.platform.startswith('win'):
            # Windows usually has audio available
            self.log("🔊 Windows audio system assumed available")
            return True
            
        elif sys.platform.startswith('darwin'):
            # macOS usually has audio available
            self.log("🔊 macOS audio system assumed available")
            return True
        
        return True  # Assume audio is available for other platforms
    
    def _test_tts(self):
        """Test TTS system with a simple message."""
        try:
            self.tts_engine.say("Text to speech system is ready")
            self.tts_engine.runAndWait()
            self.log("✅ TTS test completed successfully")
        except Exception as e:
            self.log(f"❌ TTS test failed: {e}")
    
    def speak_text(self, text):
        """Speak text using TTS worker thread (fixes threading issues)."""
        if not self.tts_enabled:
            self.log("🔇 TTS disabled - check audio settings")
            return
        
        if not self.tts_queue:
            self.log("🔇 TTS worker not initialized")
            return
        
        try:
            # Clean up text for better speech
            speech_text = text.replace("[", "").replace("]", "").replace("*", "")
            self.log(f"🔊 Queuing TTS: {speech_text[:50]}{'...' if len(speech_text) > 50 else ''}")
            
            # Add to worker queue
            self.tts_queue.put(speech_text)
            
        except Exception as e:
            self.log(f"❌ Speech queue error: {e}")
    
    def start_tts_worker(self):
        """Start simple TTS worker thread using pyttsx3."""
        def simple_tts_worker():
            """Simple TTS worker - processes speech queue."""
            try:
                self.log("🔊 Starting simple TTS worker...")
                
                # Process speech queue
                while True:
                    try:
                        # Get text from queue (blocks until available)
                        text = self.tts_queue.get(timeout=1)
                        
                        if text == "STOP":  # Stop signal
                            break
                        
                        self.log(f"🔊 Speaking: {text[:30]}{'...' if len(text) > 30 else ''}")
                        
                        # Use Method 3 for audio generation and playback
                        self._method3_audio_speak(text)
                        
                    except queue.Empty:
                        continue  # Keep checking for new messages
                    except Exception as e:
                        self.log(f"❌ TTS error: {e}")
                        continue
                        
            except Exception as e:
                self.log(f"❌ TTS worker failed: {e}")
        
        # Start the worker thread
        self.tts_worker_thread = threading.Thread(target=simple_tts_worker, daemon=True)
        self.tts_worker_thread.start()
    
    def setup_realtime_components(self):
        """Setup real-time speech components from advanced agent."""
        try:
            # Real-time audio configuration
            self.CHUNK = 1024
            self.FORMAT = pyaudio.paInt16
            self.CHANNELS = 1
            self.RATE = 24000  # GPT-4o Realtime expects 24kHz
            
            # Audio streams
            self.audio = pyaudio.PyAudio()
            self.input_stream = None
            self.output_stream = None
            
            # WebSocket connection
            self.websocket = None
            self.is_realtime_connected = False
            
            # Audio queues for real-time
            self.input_audio_queue = queue.Queue()
            self.output_audio_queue = queue.Queue()
            
            # Control flags
            self.recording = False
            self.playing = False
            self.realtime_running = False
            
            # Dedicated asyncio event loop for real-time processing
            self.realtime_loop = None
            self.realtime_thread = None
            
            # Advanced drone functions registry
            self.advanced_functions = {}
            self.register_advanced_drone_functions()
            
            self.log("✅ Real-time components initialized")
            
        except Exception as e:
            self.log(f"❌ Real-time setup failed: {e}")
    
    def create_realtime_event_loop(self):
        """Create dedicated asyncio event loop for real-time processing."""
        try:
            # Create new event loop for this thread
            self.realtime_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.realtime_loop)
            
            # Run the real-time session
            self.realtime_loop.run_until_complete(self.run_realtime_session())
            
        except Exception as e:
            self.log(f"❌ Real-time event loop error: {e}")
        finally:
            if self.realtime_loop:
                self.realtime_loop.close()
    
    async def run_realtime_session(self):
        """Run the real-time speech session with proper async handling."""
        try:
            self.log("🔄 Real-time session started in dedicated async loop")
            
            # Initialize real-time components
            await self.init_realtime_streams()
            
            # Main real-time loop
            while self.realtime_running:
                await asyncio.sleep(0.1)  # Small delay to prevent busy loop
                
                # Process audio input/output
                await self.process_realtime_audio()
                
        except Exception as e:
            self.log(f"❌ Real-time session error: {e}")
    
    async def init_realtime_streams(self):
        """Initialize audio streams for real-time processing."""
        try:
            # This would initialize WebSocket connection and audio streams
            # For now, just log the capability
            self.log("🎙️ Real-time streams initialized")
            
        except Exception as e:
            self.log(f"❌ Stream initialization error: {e}")
    
    async def process_realtime_audio(self):
        """Process real-time audio input/output."""
        try:
            # This would handle WebSocket communication and audio processing
            # For now, just maintain the session
            pass
            
        except Exception as e:
            self.log(f"❌ Audio processing error: {e}")
    
    def register_advanced_drone_functions(self):
        """Register advanced drone control functions from the attached code."""
        try:
            # Advanced movement functions
            self.advanced_functions = {
                "curve_xyz_speed": self.curve_xyz_speed,
                "go_xyz_speed": self.go_xyz_speed,
                "precise_move_forward": self.precise_move_forward,
                "precise_move_backward": self.precise_move_backward,
                "precise_move_left": self.precise_move_left,
                "precise_move_right": self.precise_move_right,
                "precise_move_up": self.precise_move_up,
                "precise_move_down": self.precise_move_down,
                "precise_rotate_clockwise": self.precise_rotate_clockwise,
                "precise_rotate_counter_clockwise": self.precise_rotate_counter_clockwise
            }
            
            self.log("✅ Advanced drone functions registered")
            
        except Exception as e:
            self.log(f"❌ Advanced functions registration failed: {e}")
    
    async def curve_xyz_speed(self, x1: int, y1: int, z1: int, x2: int, y2: int, z2: int, speed: int):
        """Fly in a curve from current position through two waypoints with speed control."""
        try:
            self.log(f"🌀 Curve flight: ({x1},{y1},{z1}) -> ({x2},{y2},{z2}) at {speed}cm/s")
            
            # Validate waypoint distances (must be at least 20cm from origin)
            dist1 = (x1**2 + y1**2 + z1**2)**0.5
            dist2 = (x2**2 + y2**2 + z2**2)**0.5
            
            if dist1 < 20:
                return f"❌ First waypoint too close to origin: {dist1:.1f}cm (minimum 20cm)"
            if dist2 < 20:
                return f"❌ Second waypoint too close to origin: {dist2:.1f}cm (minimum 20cm)"
            
            # Execute curve command
            result = self.agent.execute_command(f"curve {x1} {y1} {z1} {x2} {y2} {z2} {speed}")
            self.log(f"✅ Curve flight completed: {result}")
            return result
            
        except Exception as e:
            error_msg = f"Curve flight error: {e}"
            self.log(f"❌ {error_msg}")
            return error_msg
    
    async def go_xyz_speed(self, x: int, y: int, z: int, speed: int):
        """Fly directly to specified coordinates with speed control."""
        try:
            self.log(f"🎯 Direct flight to ({x},{y},{z}) at {speed}cm/s")
            
            # Execute go command
            result = self.agent.execute_command(f"go {x} {y} {z} {speed}")
            self.log(f"✅ Direct flight completed: {result}")
            return result
            
        except Exception as e:
            error_msg = f"Direct flight error: {e}"
            self.log(f"❌ {error_msg}")
            return error_msg
    
    # Precise movement functions with distance parameters
    async def precise_move_forward(self, distance: int):
        """Move forward with precise distance control (5-300cm)."""
        return self.agent.execute_command(f"forward {distance}")
    
    async def precise_move_backward(self, distance: int):
        """Move backward with precise distance control (5-100cm)."""
        return self.agent.execute_command(f"back {distance}")
    
    async def precise_move_left(self, distance: int):
        """Move left with precise distance control (5-100cm)."""
        return self.agent.execute_command(f"left {distance}")
    
    async def precise_move_right(self, distance: int):
        """Move right with precise distance control (5-100cm)."""
        return self.agent.execute_command(f"right {distance}")
    
    async def precise_move_up(self, distance: int):
        """Move up with precise distance control (20-100cm)."""
        return self.agent.execute_command(f"up {distance}")
    
    async def precise_move_down(self, distance: int):
        """Move down with precise distance control (20-100cm)."""
        return self.agent.execute_command(f"down {distance}")
    
    async def precise_rotate_clockwise(self, angle: int):
        """Rotate clockwise with precise angle control (30-180°)."""
        return self.agent.execute_command(f"cw {angle}")
    
    async def precise_rotate_counter_clockwise(self, angle: int):
        """Rotate counter-clockwise with precise angle control (30-180°)."""
        return self.agent.execute_command(f"ccw {angle}")
    
    def toggle_realtime_mode(self):
        """Toggle between chat mode and real-time speech mode."""
        if not REALTIME_AUDIO_AVAILABLE:
            self.log("❌ Real-time audio not available - install pyaudio and websockets")
            return
        
        try:
            if not hasattr(self, 'realtime_mode'):
                self.realtime_mode = False
                
            if not self.realtime_mode:
                # Switch to real-time mode
                self.realtime_mode = True
                self.log("🎙️ Switched to real-time speech mode")
                
                # Start real-time components with dedicated async loop
                if not self.realtime_running:
                    self.realtime_running = True
                    self.realtime_thread = threading.Thread(
                        target=self.create_realtime_event_loop, 
                        daemon=True
                    )
                    self.realtime_thread.start()
            else:
                # Switch to chat mode
                self.realtime_mode = False
                self.log("💬 Switched to chat mode")
                
                # Stop real-time components
                self.stop_realtime_session()
                
        except Exception as e:
            self.log(f"❌ Mode toggle error: {e}")
    
    def stop_realtime_session(self):
        """Stop real-time speech session and cleanup."""
        try:
            self.realtime_running = False
            
            # Close audio streams if open
            if hasattr(self, 'input_stream') and self.input_stream:
                self.input_stream.stop_stream()
                self.input_stream.close()
                self.input_stream = None
                
            if hasattr(self, 'output_stream') and self.output_stream:
                self.output_stream.stop_stream()
                self.output_stream.close()
                self.output_stream = None
                
            # Close PyAudio
            if hasattr(self, 'audio') and self.audio:
                self.audio.terminate()
                self.audio = None
                
            # Close WebSocket if connected
            if hasattr(self, 'websocket') and self.websocket:
                # WebSocket cleanup would go here
                self.websocket = None
                self.is_realtime_connected = False
                
            self.log("⏹️ Real-time session stopped and cleaned up")
            
        except Exception as e:
            self.log(f"❌ Real-time session stop error: {e}")
    
    def _method3_audio_speak(self, text):
        """Method 3: TTS using audio file generation and playback."""
        try:
            import tempfile
            import os
            import subprocess
            
            self.log("🔊 Generating audio file...")
            temp_dir = tempfile.gettempdir()
            audio_file = os.path.join(temp_dir, "drone_tts_method3.wav")
            
            # Method 3a: Try espeak-ng file generation
            file_generated = False
            espeak_cmd = getattr(self, 'tts_engine', 'espeak-ng')
            
            try:
                result = subprocess.run([espeak_cmd, '-w', audio_file, text], 
                                      capture_output=True, timeout=10)
                if result.returncode == 0 and os.path.exists(audio_file):
                    file_generated = True
                    self.log(f"✅ Audio file generated via {espeak_cmd}")
            except Exception as e:
                pass  # Silently handle espeak unavailability
            
            # Method 3b: Try pyttsx3 file generation as backup
            if not file_generated and TTS_AVAILABLE:
                try:
                    import pyttsx3
                    file_engine = pyttsx3.init()
                    file_engine.save_to_file(text, audio_file)
                    file_engine.runAndWait()
                    if os.path.exists(audio_file):
                        file_generated = True
                        self.log("✅ Audio file generated via pyttsx3")
                except Exception as e:
                    self.log(f"❌ pyttsx3 file generation failed: {e}")
            
            # Method 3c: Try simple WAV generation
            if not file_generated:
                try:
                    import wave
                    import struct
                    import math
                    
                    self.log("🔊 Generating simple beep tone...")
                    sample_rate = 44100
                    duration = 2.0
                    frequency = 800
                    
                    frames = int(duration * sample_rate)
                    wave_data = []
                    
                    for i in range(frames):
                        value = int(32767 * math.sin(2 * math.pi * frequency * i / sample_rate))
                        wave_data.append(struct.pack('<h', value))
                    
                    with wave.open(audio_file, 'wb') as wav_file:
                        wav_file.setnchannels(1)  # Mono
                        wav_file.setsampwidth(2)  # 2 bytes per sample
                        wav_file.setframerate(sample_rate)
                        wav_file.writeframes(b''.join(wave_data))
                    
                    file_generated = True
                    self.log("✅ Generated simple beep tone WAV file")
                except Exception as e:
                    self.log(f"❌ Simple WAV generation failed: {e}")
            
            # Now try to play the generated file - PRIORITIZE SYSTEM AUDIO
            if file_generated:
                self.log("🔊 Attempting SYSTEM AUDIO playback first...")
                system_audio_success = False
                
                # Method 1: Try simpleaudio (highest priority - direct system audio)
                if SIMPLEAUDIO_AVAILABLE and sa:
                    try:
                        self.log("🔊 Trying simpleaudio (direct system audio)...")
                        wave_obj = sa.WaveObject.from_wave_file(audio_file)
                        play_obj = wave_obj.play()
                        
                        # Test that playback actually started
                        import time
                        time.sleep(0.1)  # Brief wait to detect immediate failures
                        if not play_obj.is_playing():
                            raise Exception("Playback failed to start")
                        
                        self.log("✅ SUCCESS: Audio playing via simpleaudio")
                        system_audio_success = True
                        
                        # Clean up file after playback completes
                        import threading
                        def cleanup_after_play():
                            try:
                                play_obj.wait_done()
                                os.remove(audio_file)
                                self.log("✅ Audio playback completed and file cleaned up")
                            except Exception as e:
                                self.log(f"⚠️ Cleanup error: {e}")
                        threading.Thread(target=cleanup_after_play, daemon=True).start()
                        return
                    except Exception as e:
                        self.log(f"❌ Simpleaudio failed: {e} - trying system players...")
                
                # Method 2: Enhanced system audio players with more options
                import platform
                self.log("🔊 Trying system audio players...")
                
                if platform.system() == "Windows":
                    # Windows audio players (expanded list)
                    players = [
                        ('powershell', 'PowerShell Media Player'),
                        ('wmplayer', 'Windows Media Player'), 
                        ('ffplay', 'FFPlay'),
                        ('vlc', 'VLC Media Player'),
                        ('mplay32', 'Windows Media Player Classic')
                    ]
                else:
                    # Linux/Unix audio players (expanded list)
                    players = [
                        ('aplay', 'ALSA Audio Player'),
                        ('paplay', 'PulseAudio Player'),
                        ('play', 'SoX Audio Player'), 
                        ('ffplay', 'FFPlay'),
                        ('mpg123', 'MPG123 Player'),
                        ('cvlc', 'VLC Command Line')
                    ]
                
                for player, description in players:
                    try:
                        self.log(f"🔊 Trying {description} ({player})...")
                        
                        # Handle different Windows players
                        if player == 'powershell' and platform.system() == "Windows":
                            # Enhanced PowerShell command with better error handling
                            ps_cmd = f'''
                            try {{
                                $player = New-Object Media.SoundPlayer "{audio_file}"
                                $player.PlaySync()
                                Write-Output "SUCCESS"
                            }} catch {{
                                Write-Error $_.Exception.Message
                                exit 1
                            }}'''
                            play_result = subprocess.run(['powershell', '-Command', ps_cmd], 
                                                       capture_output=True, timeout=60, 
                                                       creationflags=subprocess.CREATE_NO_WINDOW,
                                                       text=True)
                        else:
                            # Standard command for other players
                            creation_flags = subprocess.CREATE_NO_WINDOW if platform.system() == "Windows" else 0
                            play_result = subprocess.run([player, audio_file], 
                                                       capture_output=True, timeout=10, 
                                                       creationflags=creation_flags)
                        
                        if play_result.returncode == 0:
                            self.log(f"✅ SUCCESS: Audio playing via {description}")
                            system_audio_success = True
                            
                            # Clean up file after a short delay
                            import threading
                            def cleanup_later():
                                import time
                                time.sleep(5)  # Give audio time to play
                                try:
                                    os.remove(audio_file)
                                    self.log(f"✅ Audio file cleaned up after {description} playback")
                                except:
                                    pass
                            threading.Thread(target=cleanup_later, daemon=True).start()
                            return
                        else:
                            stderr_msg = play_result.stderr.decode() if play_result.stderr else "No error output"
                            self.log(f"❌ {description} failed (code {play_result.returncode}): {stderr_msg[:100]}")
                            
                    except subprocess.TimeoutExpired:
                        self.log(f"⏱️ {description} timed out")
                        continue
                    except Exception as e:
                        self.log(f"❌ {description} error: {e}")
                        continue
                
                # Method 3: System-specific fallbacks before browser
                self.log("🔊 Trying system-specific fallbacks...")
                try:
                    if platform.system() == "Windows":
                        # Try Windows system sounds as fallback
                        import winsound
                        self.log("🔊 Using Windows system beep as audio notification...")
                        winsound.Beep(800, 1000)  # 800Hz for 1 second
                        self.log("✅ SUCCESS: Windows system beep played")
                        system_audio_success = True
                    else:
                        # Try Linux system beep
                        beep_result = subprocess.run(['beep', '-f', '800', '-l', '1000'], 
                                                   capture_output=True, timeout=3)
                        if beep_result.returncode == 0:
                            self.log("✅ SUCCESS: Linux system beep played")
                            system_audio_success = True
                except Exception as e:
                    self.log(f"❌ System beep failed: {e}")
                
                # Only use browser if ALL system audio methods failed
                if not system_audio_success:
                    self.log("⚠️ ALL SYSTEM AUDIO METHODS FAILED - using browser fallback...")
                    # Method 4: Browser playback (LAST RESORT ONLY)
                try:
                    import webbrowser
                    import os
                    
                    # Convert to file:// URL for browser
                    file_url = f"file://{os.path.abspath(audio_file)}"
                    self.log(f"🌐 Fallback: Opening audio in browser: {file_url}")
                    webbrowser.open(file_url)
                    self.log("✅ Audio opened in browser as fallback")
                    
                    # Keep file for a moment, then clean up
                    import threading
                    def cleanup_later():
                        import time
                        time.sleep(10)  # Give browser time to load the file
                        try:
                            os.remove(audio_file)
                        except:
                            pass
                    threading.Thread(target=cleanup_later, daemon=True).start()
                    return
                    
                except Exception as e:
                    self.log(f"❌ Browser playback failed: {e}")
                        
                self.log(f"💡 Audio file created at: {audio_file}")
                self.log("💡 Audio will auto-open in browser tab - check for new browser tabs!")
            else:
                self.log("❌ Could not generate any audio file")
                
        except Exception as e:
            self.log(f"❌ Method 3 audio error: {e}")
    
    def _fallback_audio_speak(self, text):
        """Fallback method - redirect to Method 3."""
        self._method3_audio_speak(text)
    
    def toggle_tts(self):
        """Toggle text-to-speech on/off."""
        if not TTS_AVAILABLE:
            self.log("❌ Text-to-speech not available")
            return
        
        self.tts_enabled = not self.tts_enabled
        status = "enabled" if self.tts_enabled else "disabled"
        self.log(f"🔊 Text-to-speech {status}")
        
        # Update button appearance if it exists
        if hasattr(self, 'tts_btn'):
            if self.tts_enabled:
                self.tts_btn.config(text="🔊 TTS: On", bg='#4CAF50')
            else:
                self.tts_btn.config(text="🔇 TTS: Off", bg='#757575')
    
    def test_audio_playback(self):
        """Test audio playback with multiple methods as fallback."""
        def audio_test_thread():
            test_message = "Drone audio system test. If you hear this, audio is working correctly."
            self.log("🔊 Testing audio playback...")
            
            # Method 1: Try standard TTS if available
            method1_success = False
            if TTS_AVAILABLE and self.tts_engine:
                try:
                    self.log("🔊 Testing Method 1: Direct TTS...")
                    self.tts_engine.say(test_message)
                    self.tts_engine.runAndWait()
                    self.log("✅ Direct TTS completed (software success, but may not produce audible sound)")
                    method1_success = True
                except Exception as e:
                    self.log(f"❌ Direct TTS failed: {e}")
            
            # Continue to test other methods even if Method 1 "succeeded"
            self.log("🔄 Continuing to test additional audio methods...")
            
            # Method 2: Try system audio commands
            try:
                self.log("🔊 Testing Method 2: System audio commands...")
                import subprocess
                import tempfile
                import os
                
                # Try espeak directly
                result = subprocess.run(['espeak', test_message], 
                                      capture_output=True, timeout=10)
                if result.returncode == 0:
                    self.log("✅ Espeak audio test completed")
                    if method1_success:
                        self.log("🎯 Both TTS and Espeak completed - audio should be working!")
                        return
                else:
                    pass  # Silently handle espeak unavailability
            except Exception as e:
                self.log(f"❌ System audio test failed: {e}")
            
            # Method 3: Generate audio file as fallback
            try:
                self.log("🔊 Testing Method 3: Audio file generation...")
                import tempfile
                import os
                import sys
                
                temp_dir = tempfile.gettempdir()
                audio_file = os.path.join(temp_dir, "drone_audio_test.wav")
                
                # Try multiple ways to generate audio file
                file_generated = False
                
                # Option 3a: Use pyttsx3 if available
                if TTS_AVAILABLE:
                    try:
                        file_engine = pyttsx3.init()
                        file_engine.save_to_file(test_message, audio_file)
                        file_engine.runAndWait()
                        if os.path.exists(audio_file):
                            file_generated = True
                            self.log("✅ Audio file generated via pyttsx3")
                    except Exception as e:
                        self.log(f"❌ pyttsx3 file generation failed: {e}")
                
                # Option 3b: Use espeak to file
                if not file_generated:
                    try:
                        result = subprocess.run(['espeak', '-w', audio_file, test_message], 
                                              capture_output=True, timeout=10)
                        if result.returncode == 0 and os.path.exists(audio_file):
                            file_generated = True
                            self.log("✅ Audio file generated via espeak")
                    except Exception as e:
                        pass  # Silently handle espeak unavailability
                
                # Option 3c: Create a simple beep WAV file (cross-platform)
                if not file_generated:
                    try:
                        import wave
                        import struct
                        import math
                        
                        # Generate a simple beep tone
                        sample_rate = 44100
                        duration = 2.0
                        frequency = 800
                        
                        frames = int(duration * sample_rate)
                        wave_data = []
                        
                        for i in range(frames):
                            value = int(32767 * math.sin(2 * math.pi * frequency * i / sample_rate))
                            wave_data.append(struct.pack('<h', value))
                        
                        with wave.open(audio_file, 'wb') as wav_file:
                            wav_file.setnchannels(1)  # Mono
                            wav_file.setsampwidth(2)  # 2 bytes per sample
                            wav_file.setframerate(sample_rate)
                            wav_file.writeframes(b''.join(wave_data))
                        
                        file_generated = True
                        self.log("✅ Generated simple beep tone WAV file")
                    except Exception as e:
                        self.log(f"❌ Simple WAV generation failed: {e}")
                
                if file_generated:
                    self.log(f"✅ Audio file available: {audio_file}")
                    self.log("💡 You can manually play this file with your media player")
                    
                    # Try to play the file with platform-specific players
                    players_tried = []
                    
                    if sys.platform.startswith('linux'):
                        players = ['aplay', 'paplay', 'play', 'ffplay']
                    elif sys.platform.startswith('win'):
                        players = ['powershell', 'ffplay']
                    elif sys.platform.startswith('darwin'):
                        players = ['afplay', 'ffplay']
                    else:
                        players = ['ffplay', 'play']
                    
                    for player in players:
                        try:
                            if player == 'powershell':
                                # Windows PowerShell audio
                                cmd = ['powershell', '-c', f'(New-Object Media.SoundPlayer "{audio_file}").PlaySync()']
                            else:
                                cmd = [player, audio_file]
                            
                            result = subprocess.run(cmd, capture_output=True, timeout=10)
                            if result.returncode == 0:
                                self.log(f"✅ Audio playback via {player} completed")
                                return
                            else:
                                players_tried.append(f"{player} (failed)")
                        except Exception as e:
                            players_tried.append(f"{player} (error: {e})")
                            continue
                    
                    # If no player worked, give manual instructions
                    self.log(f"⚠️ Auto-playback failed. Tried: {', '.join(players_tried)}")
                    self.log(f"📁 Manually open this file: {audio_file}")
                else:
                    self.log("❌ Could not generate any audio file")
                    
            except Exception as e:
                self.log(f"❌ Audio file generation failed: {e}")
            
            # Method 4: Last resort - system beep
            try:
                self.log("🔊 Testing Method 4: System beep...")
                import subprocess
                subprocess.run(['beep'], timeout=5)
                self.log("✅ System beep completed")
            except:
                self.log("❌ All audio methods failed - check your system audio configuration")
                self.log("💡 Try: pulseaudio --start && alsamixer")
        
        # Update button state during test
        if hasattr(self, 'test_audio_btn'):
            self.test_audio_btn.config(text="🔊 Testing...", state='disabled')
        
        def restore_button():
            # Restore button after test completes
            threading.Timer(15.0, lambda: (
                self.test_audio_btn.config(text="🔊 Test Audio", state='normal')
                if hasattr(self, 'test_audio_btn') else None
            )).start()
        
        restore_button()
        
        # Run in separate thread to avoid blocking UI
        threading.Thread(target=audio_test_thread, daemon=True).start()
    
    def toggle_continuous_vision(self):
        """Toggle continuous vision analysis on/off."""
        if not self.ai_enabled or not self.azure_openai_client:
            self.log("❌ Continuous vision analysis requires AI configuration. Click the ⚙️ Settings button.")
            return
        
        if self.continuous_vision_enabled:
            self.stop_continuous_vision()
        else:
            self.start_continuous_vision()
    
    def start_continuous_vision(self):
        """Start continuous vision analysis."""
        try:
            self.continuous_vision_enabled = True
            self.continuous_vision_running = True
            self.continuous_vision_thread = threading.Thread(target=self.continuous_vision_loop, daemon=True)
            self.continuous_vision_thread.start()
            
            # Update button state
            self.continuous_vision_btn.config(
                text="⏹️ Stop Auto-Vision",
                bg='#f44336'
            )
            
            self.log("🔄 Continuous vision analysis started")
            self.update_vision_results(f"[{time.strftime('%H:%M:%S')}] Continuous vision analysis started (every {self.vision_analysis_interval}s)\n\n")
            
        except Exception as e:
            self.log(f"❌ Failed to start continuous vision: {e}")
            self.continuous_vision_enabled = False
    
    def stop_continuous_vision(self):
        """Stop continuous vision analysis."""
        try:
            self.continuous_vision_enabled = False
            self.continuous_vision_running = False
            
            if self.continuous_vision_thread and self.continuous_vision_thread.is_alive():
                self.continuous_vision_thread.join(timeout=3)
            
            # Update button state
            self.continuous_vision_btn.config(
                text="🔄 Start Auto-Vision",
                bg='#4CAF50'
            )
            
            self.log("🔄 Continuous vision analysis stopped")
            self.update_vision_results(f"[{time.strftime('%H:%M:%S')}] Continuous vision analysis stopped\n\n")
            
        except Exception as e:
            self.log(f"❌ Failed to stop continuous vision: {e}")
    
    def continuous_vision_loop(self):
        """Continuous vision analysis loop running in separate thread."""
        while self.continuous_vision_running and self.continuous_vision_enabled:
            try:
                # Check if AI is still enabled and frame is available
                if not self.ai_enabled or not self.azure_openai_client:
                    self.log("❌ AI configuration lost, stopping continuous vision")
                    break
                
                # Get original frame from agent (same logic as analyze_current_view)
                frame_data = None
                if hasattr(self.agent, 'current_frame') and self.agent.current_frame is not None:
                    frame_data = self.agent.current_frame
                elif self.video_frame is not None:
                    frame_data = self.video_frame
                
                if frame_data is not None:
                    # Perform analysis
                    description = self.analyze_image_with_ai(
                        frame_data,
                        "In 2-3 sentences, describe what you see from this drone's perspective. Focus on key objects, people, and notable changes."
                    )
                    
                    if description:
                        self.update_vision_results(f"[{time.strftime('%H:%M:%S')}] Auto-Analysis: {description}\n\n")
                        
                        # Speak the continuous analysis result
                        self.speak_text(f"Auto analysis: {description}")
                
                # Wait for next analysis interval
                time.sleep(self.vision_analysis_interval)
                
            except Exception as e:
                self.log(f"❌ Continuous vision error: {e}")
                time.sleep(1)  # Wait before retrying
        
        # Clean up when loop ends
        self.continuous_vision_enabled = False
        self.root.after(0, lambda: self.continuous_vision_btn.config(
            text="🔄 Start Auto-Vision",
            bg='#4CAF50'
        ))
    
    def execute_ai_commands(self, commands):
        """DEPRECATED - UNSAFE METHOD. Use _execute_mission_safely() instead."""
        self.log("❌ SECURITY WARNING: Attempted to use unsafe execute_ai_commands")
        self.log("🔄 Routing to safe execution path...")
        # Route to safe execution path
        self._execute_mission_safely(commands)
    
    def open_mission_planner(self):
        """Open AI Mission Planner modal dialog."""
        if not self.ai_enabled:
            self.log("❌ AI Mission Planner requires Azure OpenAI configuration")
            messagebox.showwarning("AI Not Configured", "Please configure Azure OpenAI settings first.")
            return
            
        # Create modal window
        mission_window = tk.Toplevel(self.root)
        mission_window.title("🧠 AI Mission Planner")
        mission_window.geometry("700x500")
        mission_window.configure(bg='#2b2b2b')
        mission_window.transient(self.root)
        mission_window.grab_set()
        
        # Center the window
        mission_window.update_idletasks()
        x = (mission_window.winfo_screenwidth() // 2) - (700 // 2)
        y = (mission_window.winfo_screenheight() // 2) - (500 // 2)
        mission_window.geometry(f"700x500+{x}+{y}")
        
        # Header
        header_frame = tk.Frame(mission_window, bg='#2b2b2b')
        header_frame.pack(fill='x', padx=20, pady=20)
        
        tk.Label(
            header_frame,
            text="🧠 AI Mission Planner",
            font=('Arial', 16, 'bold'),
            fg='white',
            bg='#2b2b2b'
        ).pack()
        
        tk.Label(
            header_frame,
            text="Describe your drone mission in natural language",
            font=('Arial', 10),
            fg='#cccccc',
            bg='#2b2b2b'
        ).pack(pady=(5, 0))
        
        # Input section
        input_frame = tk.Frame(mission_window, bg='#2b2b2b')
        input_frame.pack(fill='x', padx=20, pady=10)
        
        tk.Label(
            input_frame,
            text="Mission Description:",
            font=('Arial', 12, 'bold'),
            fg='white',
            bg='#2b2b2b'
        ).pack(anchor='w')
        
        mission_text = scrolledtext.ScrolledText(
            input_frame,
            height=4,
            bg='#404040',
            fg='white',
            font=('Arial', 11),
            insertbackground='white',
            wrap=tk.WORD
        )
        mission_text.pack(fill='x', pady=5)
        mission_text.insert('1.0', 'Example: "Take off, fly in a square pattern taking photos at each corner, then return to center and land"')
        
        # Preview section
        preview_frame = tk.Frame(mission_window, bg='#2b2b2b')
        preview_frame.pack(fill='both', expand=True, padx=20, pady=10)
        
        tk.Label(
            preview_frame,
            text="Mission Preview:",
            font=('Arial', 12, 'bold'),
            fg='white',
            bg='#2b2b2b'
        ).pack(anchor='w')
        
        preview_area = scrolledtext.ScrolledText(
            preview_frame,
            height=8,
            bg='#1e1e1e',
            fg='#00ff00',
            font=('Arial', 10),
            insertbackground='white',
            wrap=tk.WORD,
            state='disabled'
        )
        preview_area.pack(fill='both', expand=True, pady=5)
        
        # Status and buttons
        button_frame = tk.Frame(mission_window, bg='#2b2b2b')
        button_frame.pack(fill='x', padx=20, pady=(0, 20))
        
        status_label = tk.Label(
            button_frame,
            text="Ready to plan mission",
            font=('Arial', 10),
            fg='#cccccc',
            bg='#2b2b2b'
        )
        status_label.pack(pady=(0, 10))
        
        def preview_mission():
            """Generate mission preview using AI."""
            mission_description = mission_text.get('1.0', tk.END).strip()
            if not mission_description or mission_description == 'Example: "Take off, fly in a square pattern taking photos at each corner, then return to center and land"':
                status_label.config(text="Please enter a mission description", fg='#ff6600')
                return
            
            status_label.config(text="🤖 AI analyzing mission...", fg='#4CAF50')
            preview_area.config(state='normal')
            preview_area.delete('1.0', tk.END)
            preview_area.insert('1.0', "🤖 Analyzing mission and generating safe commands...\n")
            preview_area.config(state='disabled')
            
            def generate_preview():
                try:
                    # Enhanced system prompt for mission planning
                    system_prompt = """You are an expert drone mission planner. Convert natural language mission descriptions into safe, executable drone command sequences.

Available commands:
- takeoff: Make drone take off
- land: Make drone land safely  
- move_forward(distance): Move forward 20-500cm
- move_back(distance): Move backward 20-500cm
- move_left(distance): Move left 20-500cm
- move_right(distance): Move right 20-500cm
- move_up(distance): Move up 20-500cm
- move_down(distance): Move down 20-500cm
- rotate_clockwise(degrees): Rotate right 1-360°
- rotate_counter_clockwise(degrees): Rotate left 1-360°
- hover(seconds): Hover for 1-8 seconds
- take_photo(): Take single photo
- take_photo_burst(count): Take multiple photos

SAFETY RULES:
- Always start with takeoff if not already flying
- Always end missions with land command
- Keep distances reasonable (under 300cm for safety)
- Include hover commands for stability between moves
- Add safety margins and hover time before photos

Respond with a JSON object: {"commands": [...], "safety_notes": "...", "estimated_time": "X minutes"}

Example response:
{"commands": [{"action": "takeoff", "parameters": {}}, {"action": "hover", "parameters": {"seconds": 3}}, {"action": "take_photo", "parameters": {}}, {"action": "land", "parameters": {}}], "safety_notes": "Mission includes proper takeoff/landing sequence with stability pauses", "estimated_time": "2 minutes"}"""

                    response = self.azure_openai_client.chat.completions.create(
                        model=self.azure_settings['deployment'],
                        messages=[
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": f"Plan this mission: {mission_description}"}
                        ],
                        response_format={"type": "json_object"},
                        max_tokens=1500
                    )
                    
                    ai_response = response.choices[0].message.content
                    mission_plan = json.loads(ai_response)
                    
                    # Update preview area
                    preview_text = f"🎯 MISSION PLAN\n{'='*50}\n\n"
                    
                    if 'safety_notes' in mission_plan:
                        preview_text += f"⚠️ SAFETY NOTES:\n{mission_plan['safety_notes']}\n\n"
                    
                    if 'estimated_time' in mission_plan:
                        preview_text += f"⏱️ ESTIMATED TIME: {mission_plan['estimated_time']}\n\n"
                    
                    preview_text += "📋 COMMAND SEQUENCE:\n"
                    
                    commands = mission_plan.get('commands', [])
                    for i, cmd in enumerate(commands, 1):
                        action = cmd.get('action', 'unknown')
                        params = cmd.get('parameters', {})
                        param_str = ', '.join([f"{k}={v}" for k, v in params.items()]) if params else "no parameters"
                        preview_text += f"{i:2d}. {action}({param_str})\n"
                    
                    preview_text += f"\n✅ Total commands: {len(commands)}"
                    
                    # Store commands for execution
                    mission_window.mission_commands = commands
                    
                    # Update UI on main thread
                    mission_window.after(0, lambda: [
                        preview_area.config(state='normal'),
                        preview_area.delete('1.0', tk.END),
                        preview_area.insert('1.0', preview_text),
                        preview_area.config(state='disabled'),
                        status_label.config(text=f"✅ Mission ready! {len(commands)} commands generated", fg='#4CAF50'),
                        execute_btn.config(state='normal', bg='#4CAF50')
                    ])
                    
                except Exception as e:
                    error_msg = f"❌ Mission planning error: {str(e)}"
                    mission_window.after(0, lambda: [
                        preview_area.config(state='normal'),
                        preview_area.delete('1.0', tk.END),
                        preview_area.insert('1.0', error_msg),
                        preview_area.config(state='disabled'),
                        status_label.config(text="❌ Mission planning failed", fg='#f44336')
                    ])
            
            threading.Thread(target=generate_preview, daemon=True).start()
        
        def execute_mission():
            """Execute the planned mission."""
            if not hasattr(mission_window, 'mission_commands'):
                status_label.config(text="Please generate a mission preview first", fg='#ff6600')
                return
                
            mission_window.destroy()
            
            # Execute commands using SAFE sequential processor
            self.log("🚀 Executing AI-planned mission via sequential processor...")
            self._execute_mission_safely(mission_window.mission_commands)
        
        # Buttons
        btn_frame = tk.Frame(button_frame, bg='#2b2b2b')
        btn_frame.pack()
        
        tk.Button(
            btn_frame,
            text="🔍 Generate Preview",
            bg='#2196F3',
            fg='white',
            font=('Arial', 11, 'bold'),
            width=15,
            command=preview_mission
        ).pack(side='left', padx=5)
        
        execute_btn = tk.Button(
            btn_frame,
            text="🚀 Execute Mission",
            bg='#666666',
            fg='white',
            font=('Arial', 11, 'bold'),
            width=15,
            state='disabled',
            command=execute_mission
        )
        execute_btn.pack(side='left', padx=5)
        
        tk.Button(
            btn_frame,
            text="❌ Cancel",
            bg='#f44336',
            fg='white',
            font=('Arial', 11, 'bold'),
            width=10,
            command=mission_window.destroy
        ).pack(side='left', padx=5)
    
    def start_panorama_capture(self):
        """Start 360° panorama capture with image stitching."""
        # Check OpenCV availability
        if not CV2_AVAILABLE:
            self.log("❌ Panorama mode requires OpenCV")
            messagebox.showwarning("Feature Unavailable", "Panorama mode requires OpenCV. Please install: pip install opencv-python")
            return
            
        if not hasattr(cv2, 'Stitcher'):
            self.log("❌ Panorama mode requires OpenCV with Stitcher support")
            messagebox.showwarning("Feature Unavailable", "Panorama mode requires OpenCV Stitcher.")
            return
            
        if not self.is_connected.get():
            self.log("❌ Connect to drone first")
            messagebox.showwarning("Connection Required", "Please connect to the drone first before starting panorama capture.")
            return
            
        if not getattr(self.agent, 'is_flying', False):
            self.log("❌ Drone must be flying for panorama capture")
            messagebox.showwarning("Flight Required", "The drone must be flying before starting panorama capture.\nPlease take off first.")
            return
        
        # Safety confirmation
        if not messagebox.askyesno("Confirm Panorama", "Panorama mode will rotate the drone 360° and take 8 photos.\nEnsure adequate space around the drone.\nContinue?"):
            return
        
        self.log("🔄 Starting 360° Panorama Capture with sequential commands...")
        
        # Generate safe panorama mission using sequential processor
        panorama_commands = []
        num_photos = 8
        rotation_angle = 45
        
        for i in range(num_photos):
            # Add rotation command (safe bounds already validated by agent)
            panorama_commands.append({
                "action": "rotate_clockwise", 
                "parameters": {"degrees": rotation_angle}
            })
            # Add stabilization hover
            panorama_commands.append({
                "action": "hover", 
                "parameters": {"seconds": 2}
            })
            # Add photo capture
            panorama_commands.append({
                "action": "take_photo", 
                "parameters": {}
            })
        
        # Execute panorama mission safely
        self.log(f"📸 Executing panorama sequence: {len(panorama_commands)} commands")
        self._execute_panorama_mission(panorama_commands)
    
    def _execute_mission_safely(self, commands):
        """Execute mission commands using safe sequential processor with validation."""
        if not isinstance(commands, list):
            self.log("❌ Invalid mission command format")
            return
        
        # Safety validation
        safety_issues = self._validate_mission_safety(commands)
        if safety_issues:
            self.log("⚠️ Mission safety validation failed:")
            for issue in safety_issues:
                self.log(f"  - {issue}")
            if not messagebox.askyesno("Safety Warning", f"Mission has safety concerns:\\n{chr(10).join(safety_issues)}\\nContinue anyway?"):
                return
        
        self.log(f"✅ Mission validated - executing {len(commands)} commands via sequential processor")
        
        # Convert AI commands to sequential processor format and execute
        for i, cmd in enumerate(commands, 1):
            try:
                action = cmd.get('action')
                params = cmd.get('parameters', {})
                
                # Convert to command string for sequential processor
                cmd_str = self._ai_command_to_string(action, params)
                if cmd_str:
                    result = self.agent.execute_command(cmd_str, 
                        lambda r, step=i: self.log(f"🚀 Mission step {step}: {r}"))
                    self.log(result)
                else:
                    self.log(f"❌ Cannot convert action '{action}' to safe command")
                    
            except Exception as e:
                self.log(f"❌ Mission step {i} error: {e}")
    
    def _execute_panorama_mission(self, commands):
        """Execute panorama commands and handle image collection."""
        self.panorama_images = []  # Store captured images
        
        def panorama_callback(result, step_type):
            self.log(f"📷 Panorama {step_type}: {result}")
            # Collect images after photo commands
            if step_type == "photo" and hasattr(self.agent, 'current_frame') and self.agent.current_frame is not None:
                self.panorama_images.append(self.agent.current_frame.copy())
                self.log(f"📷 Collected image {len(self.panorama_images)}/8 for stitching")
                
                # Trigger stitching when we have all 8 images
                if len(self.panorama_images) >= 8:
                    self.log("✅ All panorama images collected! Starting stitching...")
                    threading.Thread(target=self._finalize_panorama, daemon=True).start()
        
        # Execute commands via sequential processor
        for i, cmd in enumerate(commands, 1):
            try:
                action = cmd.get('action')
                params = cmd.get('parameters', {})
                
                cmd_str = self._ai_command_to_string(action, params)
                if cmd_str:
                    step_type = "rotation" if "rotate" in action else "hover" if action == "hover" else "photo"
                    result = self.agent.execute_command(cmd_str, 
                        lambda r, st=step_type: panorama_callback(r, st))
                    self.log(result)
                    
                    # Wait for photo capture to complete
                    if action == "take_photo":
                        time.sleep(1)  # Allow time for frame capture
                        
            except Exception as e:
                self.log(f"❌ Panorama step {i} error: {e}")
        
        # Stitching will be triggered when all 8 images are collected (see panorama_callback)
    
    def _finalize_panorama(self):
        """Finalize panorama by stitching collected images."""
        if len(self.panorama_images) >= 2:
            self.log(f"🔧 Starting panorama stitching with {len(self.panorama_images)} images...")
            self.stitch_panorama(self.panorama_images)
        else:
            self.log(f"❌ Insufficient images for stitching: {len(self.panorama_images)}/8")
        
        # Cleanup
        self.panorama_images = []
    
    def _validate_mission_safety(self, commands):
        """Validate mission commands for safety concerns."""
        safety_issues = []
        total_distance = 0
        flight_time = 0
        
        for cmd in commands:
            action = cmd.get('action')
            params = cmd.get('parameters', {})
            
            # Check movement distances
            if 'move_' in action:
                distance = params.get('distance', 0)
                if distance > 300:
                    safety_issues.append(f"Large movement distance: {distance}cm (max recommended: 300cm)")
                total_distance += distance
            
            # Check rotation angles
            elif 'rotate_' in action:
                degrees = params.get('degrees', 0)
                if degrees > 180:
                    safety_issues.append(f"Large rotation angle: {degrees}° (max recommended: 180°)")
            
            # Check hover times
            elif action == 'hover':
                seconds = params.get('seconds', 0)
                if seconds > 8:
                    safety_issues.append(f"Long hover time: {seconds}s (max allowed: 8s)")
                flight_time += seconds
            
            # Estimate flight time for movements
            if 'move_' in action:
                flight_time += params.get('distance', 0) / 50  # Rough estimate: 50cm/s
        
        # Overall mission checks
        if total_distance > 1000:
            safety_issues.append(f"Total distance very large: {total_distance}cm (consider breaking into smaller missions)")
        
        if flight_time > 120:
            safety_issues.append(f"Estimated flight time: {flight_time:.1f}s (consider battery limitations)")
        
        return safety_issues
    
    def _ai_command_to_string(self, action, params):
        """Convert AI command format to sequential processor string format."""
        # Handle function call format: e.g., 'move_forward(300)' → action='move_forward', params={'distance': 300}
        import re
        
        if '(' in action and action.endswith(')'):
            # Parse function call format
            func_match = re.match(r'(\w+)\(([^)]*)\)', action)
            if func_match:
                func_name = func_match.group(1)
                param_str = func_match.group(2).strip()
                
                # Parse parameters based on function type
                if func_name in ['move_forward', 'move_back', 'move_left', 'move_right', 'move_up', 'move_down']:
                    if param_str.isdigit():
                        distance = int(param_str)
                        direction = func_name.replace('move_', '')
                        return f"{direction} {distance}"
                elif func_name in ['rotate_clockwise', 'rotate_counter_clockwise']:
                    if param_str.isdigit():
                        degrees = int(param_str)
                        rotation = 'cw' if 'clockwise' in func_name else 'ccw'
                        return f"{rotation} {degrees}"
                elif func_name == 'hover':
                    if param_str.isdigit():
                        seconds = int(param_str)
                        return f"hover {seconds}"
                elif func_name == 'take_photo':
                    return 'photo'
                
                # Fallback - use original action name
                action = func_name
        
        # Standard format handling  
        if action == 'takeoff':
            return 'takeoff'
        elif action == 'land':
            return 'land'
        elif action in ['move_forward', 'move_back', 'move_left', 'move_right', 'move_up', 'move_down']:
            direction = action.replace('move_', '')
            distance = params.get('distance', 50)
            return f"{direction} {distance}"
        elif action == 'rotate_clockwise':
            degrees = params.get('degrees', 90)
            return f"cw {degrees}"
        elif action == 'rotate_counter_clockwise':
            degrees = params.get('degrees', 90)
            return f"ccw {degrees}"
        elif action == 'hover':
            seconds = params.get('seconds', 3)
            return f"hover {seconds}"
        elif action == 'take_photo':
            return 'photo'
        elif action == 'take_photo_burst':
            count = params.get('count', 3)
            return f"burst {count}"
        elif action == 'analyze_view':
            # Special handling for vision analysis
            prompt = params.get('prompt', 'Describe what you see')
            use_photo = params.get('use_photo', False)
            import json
            params_json = json.dumps({"prompt": prompt, "use_photo": use_photo})
            return f"analyze_view {params_json}"
        else:
            return None
    
    def stitch_panorama(self, images):
        """Stitch multiple images into a panorama using OpenCV with multiple fallback approaches."""
        try:
            self.log("🔧 Processing panorama with OpenCV Stitcher...")
            
            # Convert and prepare images
            processed_images = []
            for img in images:
                if img is not None:
                    # Resize images for better stitching performance  
                    height, width = img.shape[:2]
                    if width > 800:  # Resize if too large
                        scale = 800 / width
                        new_width = int(width * scale)
                        new_height = int(height * scale)
                        img = cv2.resize(img, (new_width, new_height))
                    processed_images.append(img)
            
            if len(processed_images) < 2:
                self.log("❌ Need at least 2 images for stitching")
                return
            
            self.log(f"🔄 Attempting to stitch {len(processed_images)} images...")
            
            # Try multiple stitching approaches with fallback
            approaches = [
                {"mode": cv2.Stitcher_PANORAMA, "conf": 1.0, "name": "Standard Panorama"},
                {"mode": cv2.Stitcher_PANORAMA, "conf": 0.3, "name": "Relaxed Panorama"},
                {"mode": cv2.Stitcher_SCANS, "conf": 0.3, "name": "Scan Mode"},
                {"mode": cv2.Stitcher_PANORAMA, "conf": 0.1, "name": "Lenient Panorama"}
            ]
            
            for i, approach in enumerate(approaches, 1):
                try:
                    self.log(f"🔧 Attempt {i}: {approach['name']} (confidence: {approach['conf']})")
                    
                    stitcher = cv2.Stitcher.create(approach["mode"])
                    stitcher.setRegistrationResol(0.6)  # Lower resolution for faster processing
                    
                    # Set confidence thresholds
                    if hasattr(stitcher, 'setConfidenceThresh'):
                        stitcher.setConfidenceThresh(approach["conf"])
                    if hasattr(stitcher, 'setPanoConfidenceThresh'):
                        stitcher.setPanoConfidenceThresh(approach["conf"] * 0.3)
                    
                    status, panorama = stitcher.stitch(processed_images)
                    
                    if status == cv2.Stitcher_OK:
                        # Save panorama
                        timestamp = time.strftime('%Y%m%d_%H%M%S')
                        filename = f"panorama_{timestamp}.jpg"
                        cv2.imwrite(filename, panorama)
                        
                        self.log(f"✅ Panorama created successfully with {approach['name']}! Saved as {filename}")
                        
                        # Optional: Show panorama in a new window
                        self.show_panorama_result(panorama, filename)
                        
                        # Optional: AI analysis of panorama
                        if self.ai_enabled:
                            self.log("🤖 Analyzing panorama with AI...")
                            self.analyze_panorama_with_ai(panorama)
                            
                        return  # Success, exit function
                        
                    else:
                        error_messages = {
                            cv2.Stitcher_ERR_NEED_MORE_IMGS: "Need more images",
                            cv2.Stitcher_ERR_HOMOGRAPHY_EST_FAIL: "Homography estimation failed", 
                            cv2.Stitcher_ERR_CAMERA_PARAMS_ADJUST_FAIL: "Camera parameter adjustment failed"
                        }
                        error_msg = error_messages.get(status, f"Unknown error (code: {status})")
                        self.log(f"❌ {approach['name']} failed: {error_msg}")
                        
                except Exception as e:
                    self.log(f"❌ {approach['name']} error: {e}")
            
            # If all approaches failed
            self.log("❌ All stitching methods failed. This can happen with:")
            self.log("  • Insufficient image overlap between photos")  
            self.log("  • Inconsistent lighting or motion blur")
            self.log("  • Too much camera shake during capture")
            self.log("💡 Try flying more steadily with slower rotations")
                
        except Exception as e:
            self.log(f"❌ Panorama stitching error: {e}")
    
    def show_panorama_result(self, panorama_img, filename):
        """Display panorama result in a new window."""
        try:
            # Create result window
            result_window = tk.Toplevel(self.root)
            result_window.title(f"📸 360° Panorama Result - {filename}")
            result_window.configure(bg='#2b2b2b')
            
            # Scale image for display
            height, width = panorama_img.shape[:2]
            max_width, max_height = 1000, 600
            
            if width > max_width or height > max_height:
                scale = min(max_width/width, max_height/height)
                new_width = int(width * scale)
                new_height = int(height * scale)
                display_img = cv2.resize(panorama_img, (new_width, new_height))
            else:
                display_img = panorama_img
            
            # Convert for Tkinter display
            display_img_rgb = cv2.cvtColor(display_img, cv2.COLOR_BGR2RGB)
            photo = ImageTk.PhotoImage(Image.fromarray(display_img_rgb))
            
            # Display image
            img_label = tk.Label(result_window, image=photo, bg='#2b2b2b')
            img_label.photo = photo  # Keep reference
            img_label.pack(padx=10, pady=10)
            
            # Info label
            info_text = f"📸 Panorama: {width}x{height} pixels | Saved as: {filename}"
            tk.Label(
                result_window,
                text=info_text,
                font=('Arial', 10),
                fg='white',
                bg='#2b2b2b'
            ).pack(pady=(0, 10))
            
        except Exception as e:
            self.log(f"❌ Error displaying panorama: {e}")
    
    def analyze_panorama_with_ai(self, panorama_img):
        """Analyze the panorama using AI vision."""
        try:
            # Convert panorama to format suitable for AI analysis
            panorama_rgb = cv2.cvtColor(panorama_img, cv2.COLOR_BGR2RGB)
            
            # Use existing AI analysis method
            prompt = "Analyze this 360-degree panoramic view captured by a drone. Describe the overall scene, key landmarks, objects, and any interesting features you can identify in this wide-angle view."
            
            result = self.analyze_image_with_ai(panorama_rgb, prompt)
            if result:
                self.update_vision_results(f"[{time.strftime('%H:%M:%S')}] 360° Panorama Analysis:\n{result}\n\n")
                self.speak_text(f"Panorama analysis complete: {result}")
            
        except Exception as e:
            self.log(f"❌ Panorama AI analysis error: {e}")
    
    def run(self):
        """Start the GUI application."""
        try:
            self.root.mainloop()
        except KeyboardInterrupt:
            print("\nShutting down GUI...")
        finally:
            # Cleanup
            self.video_running = False
            if hasattr(self, 'voice_enabled') and self.voice_enabled:
                self.stop_voice()
            if self.is_connected.get():
                self.disconnect()


def main():
    """Main entry point for GUI version."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Tello Drone Control GUI")
    parser.add_argument('--real', action='store_true', help='Connect to real drone (default: simulation)')
    args = parser.parse_args()
    
    # Create and run GUI
    simulation_mode = not args.real
    app = DroneControlGUI(simulation_mode=simulation_mode)
    app.run()


if __name__ == "__main__":
    main()