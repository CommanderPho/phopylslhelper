from typing import Dict, List, Tuple, Optional, Callable, Union, Any
from copy import deepcopy
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox, filedialog
import pylsl
import pyxdf
from datetime import datetime, timedelta
import pytz
import os
import threading
import time
import numpy as np
import json
import pickle
import mne
from pathlib import Path
import pystray
from PIL import Image, ImageDraw
import keyboard
import socket
import sys
from phopylslhelper.general_helpers import unwrap_single_element_listlike_if_needed, readable_dt_str, from_readable_dt_str, localize_datetime_to_timezone, tz_UTC, tz_Eastern, _default_tz




class SingletonInstanceMixin:
    """ 
    from phopylslhelper.mixins.app_helpers import SingletonInstanceMixin, AppThemeMixin, SystemTrayAppMixin

    Requires: self.root, 

    """
    _SingletonInstanceMixin_env_lock_port_variable_name: str = "LIVE_WHISPER_LOCK_PORT"

    # Class variable to track if an instance is already running
    _instance_running = False
    _lock_port = None  # Port to use for singleton check

    @classmethod
    def helper_SingletonInstanceMixin_get_lock_port(cls) -> int:
        if cls._lock_port is None:
            _SingletonInstanceMixin_env_lock_port_variable_name: str = cls._SingletonInstanceMixin_env_lock_port_variable_name
            print(f'.helper_SingletonInstanceMixin_get_lock_port():\n\t_SingletonInstanceMixin_env_lock_port_variable_name: "{_SingletonInstanceMixin_env_lock_port_variable_name}"')
            program_lock_port: int = int(os.environ.get(_SingletonInstanceMixin_env_lock_port_variable_name, 13375))
            print(f'\tprogram_lock_port: {program_lock_port}')
            cls._lock_port = program_lock_port  # Port to use for singleton check
            return cls._lock_port
        else:
            return cls._lock_port


    # @classmethod
    def init_SingletonInstanceMixin(self):
        """ 

        """
        # self
        # a_class = cls
        a_class = type(self)

        a_class._instance_running = False
        program_lock_port: int = a_class.helper_SingletonInstanceMixin_get_lock_port()

        # _SingletonInstanceMixin_env_lock_port_variable_name: str = a_class._SingletonInstanceMixin_env_lock_port_variable_name
        # print(f'.init_SingletonInstanceMixin():\n\t_SingletonInstanceMixin_env_lock_port_variable_name: "{_SingletonInstanceMixin_env_lock_port_variable_name}"')
        # program_lock_port = int(os.environ.get(_SingletonInstanceMixin_env_lock_port_variable_name, 13375))
        # print(f'\tprogram_lock_port: {program_lock_port}')
        # a_class._lock_port = program_lock_port  # Port to use for singleton check

        # Singleton lock socket
        self._lock_socket = None


    @classmethod
    def is_instance_running(cls):
        """Check if another instance is already running"""
        ## Get the correct lock port
        program_lock_port: int = cls.helper_SingletonInstanceMixin_get_lock_port()
        print(f'program_lock_port: {program_lock_port}')

        try:
            # Try to bind to a specific port
            test_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            test_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            test_socket.bind(('127.0.0.1', program_lock_port))
            test_socket.close()
            return False
        except OSError:
            # Port is already in use, another instance is running
            return True

    @classmethod
    def mark_instance_running(cls):
        """Mark that an instance is now running"""
        cls._instance_running = True

    @classmethod
    def mark_instance_stopped(cls):
        """Mark that the instance has stopped"""
        cls._instance_running = False


    def acquire_singleton_lock(self):
        """Acquire the singleton lock by binding to the port"""
        try:
            ## Get the correct lock port
            program_lock_port: int = self.helper_SingletonInstanceMixin_get_lock_port()

            self._lock_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._lock_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self._lock_socket.bind(('127.0.0.1', program_lock_port))
            self._lock_socket.listen(1)
            self.mark_instance_running()
            print("Singleton lock acquired successfully")
            return True
        except OSError as e:
            print(f"Failed to acquire singleton lock: {e}")
            return False

    def release_singleton_lock(self):
        """Release the singleton lock and clean up the socket"""
        try:
            if self._lock_socket:
                self._lock_socket.close()
                self._lock_socket = None
            self.mark_instance_stopped()
            print("Singleton lock released")
        except Exception as e:
            print(f"Error releasing singleton lock: {e}")





    # def __init__(self, root, xdf_folder=None):
    #     self.root = root
    #     self.root.title("LSL Logger with XDF Recording")
    #     self.root.geometry("520x720") # WxH

    #     self.stream_names = ['TextLogger', 'EventBoard', 'WhisperLiveLogger'] # : List[str]

    #     # Set application icon
    #     self.setup_app_icon()
    #     self.xdf_folder = (xdf_folder or _default_xdf_folder)

    #     # Recording state
    #     self.recording = False
    #     self.recording_thread = None
    #     # self.inlet = None
    #     self.inlets = {}
    #     self.outlets = {}

    #     self.recorded_data = []
    #     # self.recording_start_lsl_local_offset = None
    #     # self.recording_start_datetime = None

    #     self.init_EasyTimeSyncParsingMixin()
    #     # Live transcription state
    #     self.init_LiveWhisperTranscriptionAppMixin()

    #     # System tray and hotkey state
    #     self.system_tray = None
    #     self.hotkey_popover = None
    #     self.is_minimized = False

    #     # Singleton lock socket
    #     self._lock_socket = None

    #     # Shutdown flag to prevent GUI updates during shutdown
    #     self._shutting_down = False

    #     # Timestamp tracking for text entry
    #     self.main_text_start_editing_timestamp = None
    #     self.popover_text_timestamp = None

    #     # EventBoard configuration and outlet
    #     self.eventboard_config = None
    #     self.eventboard_outlet = None
    #     self.eventboard_buttons = {}
    #     self.eventboard_toggle_states = {}  # Track toggle states
    #     self.eventboard_time_offsets = {}   # Track time offset dropdowns

    #     self.capture_stream_start_timestamps() ## `EasyTimeSyncParsingMixin`: capture timestamps for use in LSL streams
    #     self.capture_recording_start_timestamps() ## capture timestamps for use in LSL streams

    #     # Load EventBoard configuration
    #     self.load_eventboard_config()

    #     # Create GUI elements first
    #     self.setup_gui()

    #     # Check for recovery files
    #     self.check_for_recovery()

    #     # Then create LSL outlets
    #     self.setup_lsl_outlet()

    #     ## setup transcirption
    #     self.root.after(200, self.auto_start_live_transcription)

    #     # Setup system tray and global hotkey
    #     self.setup_system_tray()
    #     self.setup_global_hotkey()



class AppThemeMixin:
    """ 
    Requires: self.root, 

    """
    def setup_app_icon(self):
        """Setup application icon from PNG file based on system theme"""
        try:
            # Detect system theme and choose appropriate icon
            icon_filename = self.get_theme_appropriate_icon()
            icon_path = Path("icons") / icon_filename

            if icon_path.exists():
                # Set window icon
                self.root.iconphoto(True, tk.PhotoImage(file=str(icon_path)))
                print(f"Application icon set from {icon_path}")
            else:
                print(f"Icon file not found: {icon_path}")
        except Exception as e:
            print(f"Error setting application icon: {e}")

    def get_theme_appropriate_icon(self):
        """Get the appropriate icon filename based on system theme"""
        try:
            import platform

            if platform.system() == "Windows":
                return self.detect_windows_theme()
            else:
                # For other systems, use a simple heuristic
                return self.detect_theme_simple()

        except Exception as e:
            print(f"Error detecting theme: {e}")
            # Fallback to dark icon
            return "LogToLabStreamingLayerIcon.png"

    def detect_windows_theme(self):
        """Detect Windows theme using registry"""
        try:
            import winreg

            # Check Windows 10/11 dark mode setting
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize") as key:
                try:
                    # Check if dark mode is enabled
                    dark_mode = winreg.QueryValueEx(key, "AppsUseLightTheme")[0]
                    if dark_mode == 0:  # Dark mode enabled
                        return "LogToLabStreamingLayerIcon.png"
                    else:  # Light mode
                        return "LogToLabStreamingLayerIcon_Light.png"
                except FileNotFoundError:
                    # Registry key doesn't exist, fall back to simple detection
                    return self.detect_theme_simple()
        except Exception as e:
            print(f"Error reading Windows theme registry: {e}")
            return self.detect_theme_simple()

    def detect_theme_simple(self):
        """Simple theme detection using tkinter"""
        try:
            import tkinter as tk

            # Create a temporary root to test theme
            temp_root = tk.Tk()
            temp_root.withdraw()  # Hide the window

            try:
                # Check the default background color
                bg_color = temp_root.cget('bg')

                # Simple heuristic: if background is very dark, use light icon
                if bg_color in ['#2e2e2e', '#3c3c3c', '#404040', 'SystemButtonFace']:
                    return "LogToLabStreamingLayerIcon.png"
                else:
                    return "LogToLabStreamingLayerIcon_Light.png"
            finally:
                temp_root.destroy()

        except Exception as e:
            print(f"Error in simple theme detection: {e}")
            # Default to dark icon
            return "LogToLabStreamingLayerIcon_Light.png"



class SystemTrayAppMixin:
    """ 
    Requires: self.root, self.system_tray
            self.show_app, self.show_hotkey_popover, self.quit_app


        self.get_theme_appropriate_icon
        self.on_closing()

    """

    def init_SystemTrayAppMixin(self):
        """

        """
        # System tray and hotkey state
        self.system_tray = None
        self.hotkey_popover = None
        self.is_minimized = False



    def setup_SystemTrayAppMixin(self):
        """

        """
        self.setup_app_icon()
        # Setup system tray and global hotkey
        self.setup_system_tray()
        self.setup_global_hotkey()


    def setup_system_tray(self):
        """Setup system tray icon and menu"""
        try:
            # Create a simple icon (you can replace this with a custom icon file)
            icon_image = self.create_tray_icon()

            # Create system tray menu
            menu = pystray.Menu(
                pystray.MenuItem("Show App", self.show_app),
                pystray.MenuItem("Quick Log", self.show_hotkey_popover),
                pystray.MenuItem("Exit", self.quit_app)
            )

            # Create system tray icon
            self.system_tray = pystray.Icon(
                "logger_app",
                icon_image,
                "LSL Logger",
                menu
            )

            # Add double-click handler to show app
            self.system_tray.on_activate = self.show_app ## double-clicking doesn't foreground the app by default. Also clicking the windows close "X" just hides it to taskbar by default which I don't want. 

            # Start system tray in a separate thread
            threading.Thread(target=self.system_tray.run, daemon=True).start()

        except Exception as e:
            print(f"Error setting up system tray: {e}")

    def create_tray_icon(self):
        """Create icon for the system tray from PNG file based on system theme"""
        try:
            # Use the same theme detection as the main icon
            icon_filename = self.get_theme_appropriate_icon()
            icon_path = Path("icons") / icon_filename

            if icon_path.exists():
                # Load and resize the PNG icon for system tray
                image = Image.open(str(icon_path))
                # Resize to appropriate size for system tray (16x16 or 32x32)
                image = image.resize((16, 16), Image.Resampling.LANCZOS)
                return image
            else:
                print(f"Tray icon file not found: {icon_path}, using default")
                return self.create_default_tray_icon()
        except Exception as e:
            print(f"Error loading tray icon: {e}, using default")
            return self.create_default_tray_icon()

    def create_default_tray_icon(self):
        """Create a simple default icon for the system tray"""
        # Create a 16x16 icon with a simple design
        width = 16
        height = 16

        # Create image with a dark background
        image = Image.new('RGB', (width, height), color='#2c3e50')
        draw = ImageDraw.Draw(image)

        # Draw a simple "L" shape in white
        draw.rectangle([2, 2, 6, 14], fill='white')  # Vertical line
        draw.rectangle([2, 10, 12, 14], fill='white')  # Horizontal line

        return image

    # Lifecycle methods __________________________________________________________________________________________________________________________________________________________________________________________________________________________________________________________________ #

    def show_app(self):
        """Show the main application window"""
        self.is_minimized = False
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()

    def minimize_to_tray(self):
        """Minimize the app to system tray"""
        self.is_minimized = True
        self.root.withdraw()  # Hide the window
        try:
            if not self._shutting_down:
                self.minimize_button.config(text="Restore from Tray")
        except tk.TclError:
            pass  # GUI is being destroyed

    def restore_from_tray(self):
        """Restore the app from system tray"""
        self.is_minimized = False
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()
        try:
            if not self._shutting_down:
                self.minimize_button.config(text="Minimize to Tray")
        except tk.TclError:
            pass  # GUI is being destroyed

    def toggle_minimize(self):
        """Toggle between minimize and restore"""
        if self.is_minimized:
            self.restore_from_tray()
        else:
            self.minimize_to_tray()

    def quit_app(self):
        """Quit the application completely"""
        if self.system_tray:
            self.system_tray.stop()
        self.on_closing()

