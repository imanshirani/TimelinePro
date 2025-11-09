# ====================================================================
# ===                                                              ===
# ===      Timeline Tool for 3ds Max                               ===
# ===      Author: Iman Shirani                                    ===
# ===      Version: 0.0.2                                          ===
# ===                                                              ===
# ===                                                              ===           
# ====================================================================
import sys
import os
from PySide6 import QtWidgets, QtCore
import importlib
import pymxs 

# A global variable to hold the toolbar instance
# This helps us close the previous instance if the script is run again
if "_timeline_toolbar_instance" not in globals():
    _timeline_toolbar_instance = None

def launch_timeline():
    """The main function to launch and manage the timeline as a toolbar."""
    global _timeline_toolbar_instance

    app = QtWidgets.QApplication.instance()
    if not app:
        app = QtWidgets.QApplication(sys.argv)

    
    try:
        # Use pymxs to get the window's unique handle (HWND)
        max_hwnd = pymxs.runtime.windows.getMAXHWND()
        # Find the Qt widget that corresponds to that handle
        main_window = QtWidgets.QWidget.find(max_hwnd)
        if not main_window:
            raise RuntimeError("Could not find Qt widget for the main window.")
    except Exception as e:
        print(f"❌ ERROR: Could not find the 3ds Max main window. Details: {e}")
        return
    

    # Close the previous toolbar instance if it exists
    if _timeline_toolbar_instance:
        print("-> Closing previous timeline instance...")
        try:
            # ✅ This is the robust way to find the widget inside the toolbar
            for action in _timeline_toolbar_instance.actions():
                widget = action.defaultWidget()
                if widget and hasattr(widget, 'sync_timer'):
                    widget.sync_timer.stop()
                    print("   - Sync timer stopped.")
                    break
            
            _timeline_toolbar_instance.close()
            _timeline_toolbar_instance.deleteLater()
            _timeline_toolbar_instance = None
            print("   - Previous toolbar closed successfully.")
        except Exception as e:
            print(f"   - Warning: Could not properly close previous instance: {e}")

    # Add the script directory to Python's path
    script_dir = os.path.dirname(os.path.abspath(__file__))
    if script_dir not in sys.path:
        sys.path.append(script_dir)

    # Reload all your custom modules to get the latest changes
    try:
        import custom_widgets
        import timeline_logic
        import timeline_ui

        importlib.reload(custom_widgets)
        importlib.reload(timeline_logic)
        importlib.reload(timeline_ui)
        print("-> All modules reloaded successfully.")
        
        from timeline_ui import MyTimelineWidget
    except ImportError as e:
        print(f"❌ ERROR: Could not import a timeline module: {e}")
        return

    # Create the new toolbar and add your timeline widget to it
    toolbar = QtWidgets.QToolBar("TimelineProToolbar", main_window)
    toolbar.setObjectName("TimelineProToolbar")
    
    timeline_widget = MyTimelineWidget(parent_toolbar=toolbar)
    toolbar.addWidget(timeline_widget)

    # Add the toolbar to the bottom of the 3ds Max window
    main_window.addToolBar(QtCore.Qt.ToolBarArea.BottomToolBarArea, toolbar)
    toolbar.show()
    
    # Store the new instance in our global variable
    _timeline_toolbar_instance = toolbar
    print("✅ Timeline Pro launched successfully as a dockable toolbar!")

# --- Run the main function ---

launch_timeline()
