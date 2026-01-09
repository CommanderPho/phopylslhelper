from typing import Dict, List, Tuple, Optional, Callable, Union, Any
from copy import deepcopy
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox, filedialog
import pylsl
import os
import atexit
import signal
from datetime import datetime, timedelta
import pytz
import threading
import time
import numpy as np
import json
import pickle
from pathlib import Path
import pystray
from PIL import Image, ImageDraw
import sys
import platform
try:
    import fcntl
except ImportError:
    fcntl = None
try:
    import msvcrt
except ImportError:
    msvcrt = None
from phopylslhelper.general_helpers import unwrap_single_element_listlike_if_needed, readable_dt_str, from_readable_dt_str, localize_datetime_to_timezone, tz_UTC, tz_Eastern, _default_tz


class SingletonInstanceMixin:
    """
    Safe singleton lock using file-based locking. Works across crashes and avoids port conflicts.
    Lock file is located in the executable directory.
    """

    _SingletonInstanceMixin_env_lock_file_name: str = "LIVE_WHISPER_LOCK_FILE"
    _instance_running = False
    _lock_file_path = None

    @classmethod
    def _get_executable_directory(cls) -> Path:
        """Get the directory containing the executable"""
        return Path(sys.executable).parent

    @classmethod
    def _get_lock_file_path(cls) -> Path:
        """Get the path to the lock file"""
        if cls._lock_file_path is None:
            env_file = os.environ.get(cls._SingletonInstanceMixin_env_lock_file_name)
            if env_file:
                cls._lock_file_path = Path(env_file)
            else:
                # Default: use executable name with .lock extension
                exe_dir = cls._get_executable_directory()
                exe_name = Path(sys.executable).stem if hasattr(sys, 'executable') else "app"
                cls._lock_file_path = exe_dir / f"{exe_name}.lock"
        return cls._lock_file_path

    @classmethod
    def _is_process_running(cls, pid: int) -> bool:
        """Check if a process with the given PID is still running"""
        try:
            if platform.system() == "Windows":
                # On Windows, os.kill with signal 0 checks if process exists
                # Use a more robust check to avoid SystemError on Windows
                try:
                    os.kill(pid, 0)
                    return True
                except OSError as e:
                    # On Windows, error 87 means invalid parameter (process doesn't exist)
                    # Error 3 means process not found
                    if e.winerror in (87, 3) or e.errno in (3,):
                        return False
                    # Re-raise other OSErrors
                    raise
            else:
                # On Unix/macOS, os.kill with signal 0 checks if process exists
                os.kill(pid, 0)
                return True
        except (OSError, ProcessLookupError, SystemError):
            return False

    @classmethod
    def _is_lock_stale(cls, lock_path: Path) -> bool:
        """Check if the lock file exists and if it's stale (process no longer running)"""
        if not lock_path.exists():
            return False
        try:
            with open(lock_path, 'r') as f:
                pid_str = f.read().strip()
                if pid_str:
                    pid = int(pid_str)
                    return not cls._is_process_running(pid)
        except (ValueError, IOError):
            # Lock file exists but is invalid, consider it stale
            return True
        return False

    def init_SingletonInstanceMixin(self):
        a_class = type(self)
        a_class._instance_running = False
        # Singleton lock file
        self._lock_file_handle = None

        # Ensure lock released on normal exit
        atexit.register(self.release_singleton_lock)
        # Ensure lock released on Ctrl+C / termination
        signal.signal(signal.SIGTERM, lambda *_: self.release_singleton_lock() or sys.exit(0))
        signal.signal(signal.SIGINT,  lambda *_: self.release_singleton_lock() or sys.exit(0))






    @classmethod
    def is_instance_running(cls):
        """Check if another instance is already running"""
        lock_path = cls._get_lock_file_path()
        
        # If lock file doesn't exist, no instance is running
        if not lock_path.exists():
            return False
        
        # Check if lock is stale (process no longer running)
        if cls._is_lock_stale(lock_path):
            return False
        
        # Try to acquire lock to verify it's actually held
        try:
            if platform.system() == "Windows":
                # Windows: use msvcrt.locking
                if msvcrt is None:
                    return True  # Assume running if we can't check
                with open(lock_path, 'r+b') as f:
                    try:
                        msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
                        # If we got here, lock is not held
                        return False
                    except IOError:
                        # Lock is held
                        return True
            else:
                # Unix/macOS: use fcntl.flock
                if fcntl is None:
                    return True  # Assume running if we can't check
                with open(lock_path, 'r') as f:
                    try:
                        fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                        # If we got here, lock is not held
                        fcntl.flock(f.fileno(), fcntl.LOCK_UN)
                        return False
                    except BlockingIOError:
                        # Lock is held
                        return True
        except (IOError, OSError):
            # Error checking lock, assume instance is running to be safe
            return True

    @classmethod
    def mark_instance_running(cls):
        cls._instance_running = True

    @classmethod
    def mark_instance_stopped(cls):
        cls._instance_running = False

    def acquire_singleton_lock(self, preferred_port=None, fallback_ports=None):
        """
        Acquire the singleton lock using file-based locking.
        Returns True if lock acquired.
        Note: preferred_port and fallback_ports parameters are kept for compatibility but ignored.
        """
        lock_path = self._get_lock_file_path()
        
        # Check if lock exists and is stale, remove it if so
        if self._is_lock_stale(lock_path):
            try:
                lock_path.unlink()
                print(f"Removed stale lock file: {lock_path}")
            except OSError as e:
                print(f"Warning: Could not remove stale lock file: {e}")
        
        try:
            # Create lock file directory if it doesn't exist
            lock_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Open lock file in appropriate mode
            if platform.system() == "Windows":
                # Windows: open in a+b mode (creates if doesn't exist) for msvcrt.locking
                self._lock_file_handle = open(lock_path, 'a+b')
                try:
                    msvcrt.locking(self._lock_file_handle.fileno(), msvcrt.LK_NBLCK, 1)
                except IOError:
                    self._lock_file_handle.close()
                    self._lock_file_handle = None
                    print(f"Lock file is already held: {lock_path}")
                    return False
            else:
                # Unix/macOS: open in w+ mode for fcntl.flock
                self._lock_file_handle = open(lock_path, 'w+')
                try:
                    fcntl.flock(self._lock_file_handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    self._lock_file_handle.close()
                    self._lock_file_handle = None
                    print(f"Lock file is already held: {lock_path}")
                    return False
            
            # Write PID to lock file
            pid = os.getpid()
            self._lock_file_handle.seek(0)
            self._lock_file_handle.truncate()
            if platform.system() == "Windows":
                self._lock_file_handle.write(str(pid).encode())
            else:
                self._lock_file_handle.write(str(pid))
            self._lock_file_handle.flush()
            
            self.mark_instance_running()
            print(f"Singleton lock acquired: {lock_path}")
            return True
        except (IOError, OSError) as e:
            if self._lock_file_handle:
                try:
                    self._lock_file_handle.close()
                except:
                    pass
                self._lock_file_handle = None
            print(f"Failed to acquire singleton lock: {e}")
            return False

    def release_singleton_lock(self):
        """Release the singleton lock"""
        try:
            if self._lock_file_handle:
                if platform.system() == "Windows":
                    if msvcrt is not None:
                        try:
                            msvcrt.locking(self._lock_file_handle.fileno(), msvcrt.LK_UNLCK, 1)
                        except:
                            pass
                else:
                    if fcntl is not None:
                        try:
                            fcntl.flock(self._lock_file_handle.fileno(), fcntl.LOCK_UN)
                        except:
                            pass
                self._lock_file_handle.close()
                self._lock_file_handle = None
            
            # Remove lock file
            lock_path = self._get_lock_file_path()
            if lock_path.exists():
                try:
                    lock_path.unlink()
                except OSError:
                    pass
            
            self.mark_instance_stopped()
            print("Singleton lock released")
        except Exception as e:
            print(f"Error releasing singleton lock: {e}")

    @classmethod
    def force_remove_lock(cls):
        """Force-remove any existing lock file, useful for cleaning up after crashes"""
        lock_path = cls._get_lock_file_path()
        if lock_path.exists():
            try:
                lock_path.unlink()
                print(f"Force-removed lock file: {lock_path}")
                return True
            except OSError as e:
                print(f"Error force-removing lock file: {e}")
                return False
        else:
            print(f"No lock file to remove: {lock_path}")
            return False



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

