# =============================================
# === FILE 1: timeline_logic.py             ===
# =============================================

import sys
import os
import json
import uuid
import configparser
import math
import ctypes
import ctypes.wintypes
try:
    from PySide2 import QtWidgets, QtCore, QtGui
except ImportError:
    from PySide6 import QtWidgets, QtCore, QtGui
import pymxs
from custom_widgets import XYZScrubber, QuatScrubber, ValueScrubber
from timeline_logic import TimelineLogic

rt = pymxs.runtime
_g_timeline_instance = None
SCRIPT_PATH = os.path.dirname(os.path.realpath(__file__))
SETTINGS_FILE = os.path.join(SCRIPT_PATH, 'settings.ini')

def get_timeline_instance():
    return _g_timeline_instance

# ... (Helper functions and other classes remain the same) ...
def load_settings():
    config = configparser.ConfigParser()
    # Section for Ruler ticking logic
    config['Ruler_Smart_Ticking'] = { 'zoom_level_1_threshold_px': '20', 'zoom_level_1_step_frames': '5', 'zoom_level_2_threshold_px': '10', 'zoom_level_2_step_frames': '10', 'zoom_level_3_threshold_px': '5', 'zoom_level_3_step_frames': '20', 'zoom_level_4_threshold_px': '2', 'zoom_level_4_step_frames': '50', 'default_step_frames': '100'}
    
    # --- NEW: Section for layer colors ---
    config['Type_Colors'] = {
        'light_color': '#555537',  # Yellowish
        'camera_color': '#374155', # Bluish
        'shape_color': '#375537',  # Greenish
        'helper_color': '#554B37',  # Orangish
        'geometry_color': "#475A6D", # Blue
        'SpacewarpObject_color': "#ACA6A6" # white
    }
    config['Default_Hidden_Tracks'] ={
        'hidden_list': 
        'Visibility,'
        'Space Warps,'
        'Material,'
        'Object,'
        'Image Motion Blur Multiplier,'
        'Object Motion Blur On Off,'
        'Object (Vray Properties),'
        'Object (Mental Ray),'
        'Image Bitmap,Render Effects,'
        'Sound,'
        'Global Tracks,'
        'MasterPoint Controller'
    }

    if os.path.exists(SETTINGS_FILE):
        config.read(SETTINGS_FILE)
    else:
        save_settings(config)
    return config


def save_settings(config):
    with open(SETTINGS_FILE, 'w') as configfile: config.write(configfile)

# ===================================
# === NEW CLASS: MarkerDialog     ===
# ===================================
class MarkerDialog(QtWidgets.QDialog):
    """A dialog for editing a marker's note and color."""
    def __init__(self, note="", color=QtGui.QColor("#d4a056"), parent=None):
        super().__init__(parent)
        self.setWindowTitle("Edit Marker")
        self.layout = QtWidgets.QVBoxLayout(self)

        self.note_edit = QtWidgets.QTextEdit()
        self.note_edit.setPlaceholderText("Enter your notes here...")
        self.note_edit.setText(note)
        self.layout.addWidget(self.note_edit)

        self.color_btn = QtWidgets.QPushButton("Change Color")
        self.current_color = color
        self._update_button_color()
        self.color_btn.clicked.connect(self.open_color_picker)
        self.layout.addWidget(self.color_btn)

        button_box = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Save | QtWidgets.QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        self.layout.addWidget(button_box)

    def _update_button_color(self):
        self.color_btn.setStyleSheet(f"background-color: {self.current_color.name()};")

    def open_color_picker(self):
        new_color = QtWidgets.QColorDialog.getColor(self.current_color, self, "Select Marker Color")
        if new_color.isValid():
            self.current_color = new_color
            self._update_button_color()

    def get_data(self):
        """Returns the final note and color from the dialog."""
        return self.note_edit.toPlainText(), self.current_color

# ================================
# === NEW WIDGET: MarkerView   ===
# ================================
class MarkerView(QtWidgets.QWidget):
    """A dedicated widget strip for displaying and interacting with markers."""
    def __init__(self, timeline_widget, parent=None):
        super().__init__(parent)
        self.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.PreventContextMenu)
        print("✅ DEBUG: MarkerView widget created successfully.")
        self.timeline_widget = timeline_widget
        self.ruler = timeline_widget.ruler 
        self.setFixedHeight(32)
        self.setStyleSheet("background-color: #ff0000;")
        
    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        
        
        painter.fillRect(self.rect(), QtGui.QColor("#313131")) 
        painter.setPen(QtCore.Qt.PenStyle.NoPen)

        h = self.height()
        marker_polygon = QtGui.QPolygonF([
            QtCore.QPointF(0, h - 2),    
            QtCore.QPointF(-6, 3),       
            QtCore.QPointF(6, 3)         
        ])
    
        for marker in self.timeline_widget.markers.values():
            frame = marker['frame']
            if self.ruler.start_frame <= frame <= self.ruler.end_frame:
                x_pos = (frame - self.ruler.start_frame) * self.ruler.pixels_per_frame
                painter.setBrush(QtGui.QBrush(QtGui.QColor(marker['color'])))
                
                painter.save()
                painter.translate(x_pos, 0)
                painter.restore()

    def _marker_at_pos(self, pos):
        """Checks if a click position is on top of a marker."""
        for marker in self.timeline_widget.markers.values():
            frame = marker['frame']
            x_pos = (frame - self.ruler.start_frame) * self.ruler.pixels_per_frame
            marker_rect = QtCore.QRectF(x_pos - 6, 0, 12, self.height())
            if marker_rect.contains(pos):
                return marker['uid']
        return None

    
    
    
class SettingsDialog(QtWidgets.QDialog):
    def __init__(self, settings_config, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Timeline Settings")
        self.settings = settings_config
        self.layout = QtWidgets.QVBoxLayout(self)

        self.tabs = QtWidgets.QTabWidget()
        self.layout.addWidget(self.tabs)

        self.create_timeline_tab()
        self.create_hidden_tracks_tab()
        self.create_editors_tab()
        self.create_about_tab()


        self.load_values_to_ui()

        button_box = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Save | QtWidgets.QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.save_and_accept); button_box.rejected.connect(self.reject)
        self.layout.addWidget(button_box)

    
    def create_timeline_tab(self):
        """Creates the timeline settings header (including your previous settings)."""
        tab_widget = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(tab_widget)
        
        
        ruler_group = QtWidgets.QGroupBox("Ruler Ticking Density")
        
        self.z1_thresh = QtWidgets.QSpinBox(); self.z1_step = QtWidgets.QSpinBox()
        self.z2_thresh = QtWidgets.QSpinBox(); self.z2_step = QtWidgets.QSpinBox()
        grid_layout = QtWidgets.QGridLayout()
        grid_layout.addWidget(QtWidgets.QLabel("If Pixels/Frame >"), 0, 0); grid_layout.addWidget(self.z1_thresh, 0, 1); grid_layout.addWidget(QtWidgets.QLabel("then show number every:"), 0, 2); grid_layout.addWidget(self.z1_step, 0, 3)
        grid_layout.addWidget(QtWidgets.QLabel("If Pixels/Frame >"), 1, 0); grid_layout.addWidget(self.z2_thresh, 1, 1); grid_layout.addWidget(QtWidgets.QLabel("then show number every:"), 1, 2); grid_layout.addWidget(self.z2_step, 1, 3)
        ruler_group.setLayout(grid_layout)
        layout.addWidget(ruler_group)

        
        self.current_colors = {}
        color_group = QtWidgets.QGroupBox("Layer Colors")
        
        color_layout = QtWidgets.QFormLayout()
        self.color_buttons = {
            'light_color': QtWidgets.QPushButton(), 'camera_color': QtWidgets.QPushButton(),
            'shape_color': QtWidgets.QPushButton(), 'helper_color': QtWidgets.QPushButton(),
            'geometry_color': QtWidgets.QPushButton(), 'SpacewarpObject_color': QtWidgets.QPushButton()
        }
        for key, button in self.color_buttons.items():
            label_text = key.replace('_color', ' Color').title()
            button.setFixedSize(100, 20)
            button.setAutoFillBackground(True)
            button.clicked.connect(lambda checked=False, k=key: self.open_color_picker(k))
            color_layout.addRow(label_text, button)
        self.reset_colors_btn = QtWidgets.QPushButton("Reset Defaults")
        self.reset_colors_btn.clicked.connect(self.reset_colors_to_default)
        color_layout.addRow(self.reset_colors_btn)
        color_group.setLayout(color_layout)
        layout.addWidget(color_group)
        
        layout.addStretch()
        self.tabs.addTab(tab_widget, "Timeline")

    def create_hidden_tracks_tab(self):
        """ Settings for tracks that are hidden by default. """
        tab_widget = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(tab_widget)
        
        hidden_group = QtWidgets.QGroupBox("Tracks to Hide by Default")
        hidden_layout = QtWidgets.QVBoxLayout(hidden_group)
        
        self.hidden_track_checkboxes = {} 
        
        
        for track_name in MyTimelineWidget.FILTERABLE_TRACKS:
            checkbox = QtWidgets.QCheckBox(track_name)
            self.hidden_track_checkboxes[track_name] = checkbox
            hidden_layout.addWidget(checkbox)
            
        layout.addWidget(hidden_group)
        layout.addStretch()
        self.tabs.addTab(tab_widget, "Hidden Tracks")

    def create_editors_tab(self):
        """The header makes settings for editors."""
        tab_widget = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(tab_widget)
        
        label = QtWidgets.QLabel("Settings for the Curve Editor and Motion Mixer will be available in future updates.")
        label.setWordWrap(True)
        layout.addWidget(label)
        layout.addStretch()
        
        self.tabs.addTab(tab_widget, "Editors")

    def create_about_tab(self):
        """Creates the "About Us" header."""
        tab_widget = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(tab_widget)
        self.github_url = "https://github.com/imanshirani/TimelinePro/"
        self.paypal_url = "https://www.paypal.com/donate/?hosted_button_id=LAMNRY6DDWDC4"

        
        
        about_text = f"""
        <h3>Timeline Pro</h3>
        <p><b>Version:</b> 0.0.1</p>
        <p>A professional non-linear animation timeline for 3ds Max.</p>
        <p>Developed by: <b>Iman shirani</b></p>
        <p>&copy; 2025</p>
        """

        
        
        label = QtWidgets.QLabel(about_text)
        label.setTextFormat(QtCore.Qt.TextFormat.RichText)
        label.setOpenExternalLinks(True)
        
        layout.addWidget(label)

        #Git HUB BUTTON
        layout.addWidget(QtWidgets.QLabel("Find a bug or have an idea? Visit the GitHub page:"))
        self.github_btn = QtWidgets.QPushButton("TimelinePro on GitHub")
        self.github_btn.setStyleSheet("""
            QPushButton {
                background-color: #333333; 
                color: #FFFFFF; 
                font-weight: bold;
                padding: 4px 8px;
                border-radius: 4px;
                border: none;
            }
            QPushButton:hover {
                background-color: #555555; 
            }
        """)
        
        self.github_btn.clicked.connect(self.open_github_link)
        self.github_btn.setToolTip("Opens the GitHub repository in your browser.")
        layout.addWidget(self.github_btn)

        layout.addSpacing(10)

        #PAYPAL BUTTON
        layout.addWidget(QtWidgets.QLabel("If you find this tool helpful, consider supporting its development:"))
        
        self.paypal_btn = QtWidgets.QPushButton("Support via PayPal")
        self.paypal_btn.setStyleSheet("""
            QPushButton {
                background-color: #FFC439; 
                color: #00457C; 
                font-weight: bold;
                padding: 4px 8px;
                border-radius: 4px;
                border: none;
            }
            QPushButton:hover {
                background-color: #FFD46A;
            }
        """)
        self.paypal_btn.clicked.connect(self.open_paypal_link)
        self.paypal_btn.setToolTip("Opens your browser to the PayPal support page.")
        layout.addWidget(self.paypal_btn)

        layout.addStretch()
        
        self.tabs.addTab(tab_widget, "About")

    def open_github_link(self):
        """Opens the GitHub link in the user's default web browser."""
        try:
            url = QtCore.QUrl(self.github_url)
            QtGui.QDesktopServices.openUrl(url)
        except Exception as e:
            print(f"Error opening GitHub link: {e}")
            QtWidgets.QMessageBox.warning(self, "Error", 
                f"Could not open the URL. Please visit:\n{self.github_url}")
            
    def open_paypal_link(self):
        """Opens the PayPal link in the user's default web browser."""
        try:
            
            url = QtCore.QUrl(self.paypal_url)
            QtGui.QDesktopServices.openUrl(url)
        except Exception as e:
            print(f"Error opening PayPal link: {e}")
            QtWidgets.QMessageBox.warning(self, "Error", 
                f"Could not open the URL. Please visit:\n{self.paypal_url}")

    def _apply_button_style(self, button, hex_color):
        """A helper function to set the button style consistently."""
        button.setStyleSheet(f"background-color: {hex_color}; border: 1px solid #777;")

    def reset_colors_to_default(self):
        default_colors = {
            'light_color': '#555537', 'camera_color': '#374155',
            'shape_color': '#375537', 'helper_color': '#554B37',
            'geometry_color': "#475A6D", 'SpacewarpObject_color': "#ACA6A6"
        }
        for key, button in self.color_buttons.items():
            hex_color = default_colors.get(key)
            if hex_color:
                self.current_colors[key] = hex_color
                self._apply_button_style(button, hex_color)

    def open_color_picker(self, key):
        initial_color = QtGui.QColor(self.current_colors.get(key, '#FFFFFF'))
        new_color = QtWidgets.QColorDialog.getColor(initial_color, self, "Select Color")
        if new_color.isValid():
            hex_name = new_color.name()
            self.current_colors[key] = hex_name
            self._apply_button_style(self.color_buttons[key], hex_name)

    def load_values_to_ui(self):
        ruler_cfg = self.settings['Ruler_Smart_Ticking']
        self.z1_thresh.setValue(ruler_cfg.getint('zoom_level_1_threshold_px')); self.z1_step.setValue(ruler_cfg.getint('zoom_level_1_step_frames'))
        self.z2_thresh.setValue(ruler_cfg.getint('zoom_level_2_threshold_px')); self.z2_step.setValue(ruler_cfg.getint('zoom_level_2_step_frames'))
        
        if self.settings.has_section('Type_Colors'):
            color_cfg = self.settings['Type_Colors']
        else:
            color_cfg = {}

        for key, button in self.color_buttons.items():
            hex_color = color_cfg.get(key, '#353535')
            self.current_colors[key] = hex_color
            self._apply_button_style(button, hex_color)

        hidden_list_str = self.settings.get('Default_Hidden_Tracks', 'hidden_list', fallback='')
        current_hidden_set = set(hidden_list_str.split(',')) if hidden_list_str else set()
        
        for track_name, checkbox in self.hidden_track_checkboxes.items():
            checkbox.setChecked(track_name in current_hidden_set)

    def save_and_accept(self):
        """Save values ​​from UI to settings and close dialog."""
        
        ruler_cfg = self.settings['Ruler_Smart_Ticking']
        ruler_cfg['zoom_level_1_threshold_px'] = str(self.z1_thresh.value())
        ruler_cfg['zoom_level_1_step_frames'] = str(self.z1_step.value())
        ruler_cfg['zoom_level_2_threshold_px'] = str(self.z2_thresh.value())
        ruler_cfg['zoom_level_2_step_frames'] = str(self.z2_step.value())

        
        if not self.settings.has_section('Type_Colors'): self.settings.add_section('Type_Colors')
        color_cfg = self.settings['Type_Colors']
        for key, hex_value in self.current_colors.items():
            color_cfg[key] = hex_value

        
        if not self.settings.has_section('Default_Hidden_Tracks'): self.settings.add_section('Default_Hidden_Tracks')
        hidden_cfg = self.settings['Default_Hidden_Tracks']
        
        selected_hidden_tracks = [name for name, checkbox in self.hidden_track_checkboxes.items() if checkbox.isChecked()]
        hidden_cfg['hidden_list'] = ",".join(selected_hidden_tracks)
        
        save_settings(self.settings)
        self.accept()
        
        
        if self.parent():
            self.parent().ruler.update()
            
            self.parent()._load_default_hidden_tracks_from_settings()
            self.parent().apply_visibility_filter() 
            self.parent()._full_ui_refresh()

   

class ValueDelegate(QtWidgets.QStyledItemDelegate):
    def __init__(self, tree_widget, parent=None):
        super().__init__(parent)
        self.tree_widget = tree_widget

    def createEditor(self, parent, option, index):
        if index.column() != 3:
            return None
        item = self.tree_widget.itemFromIndex(index)
        if not item:
            return super().createEditor(parent, option, index)
            
        sub_anim = item.data(0, MyTimelineWidget.SUBANIM_ROLE)
        if not sub_anim:
            return super().createEditor(parent, option, index)

        val = None
        try:
            val = sub_anim.value if not sub_anim.controller else sub_anim.controller.value
        except Exception:
            pass

        if val is None:
             return super().createEditor(parent, option, index)

        val_class = rt.classOf(val)
        if val_class == rt.Point3:
            return XYZScrubber(parent)
        elif val_class == rt.Quat:
            return QuatScrubber(parent)
        elif isinstance(val, float):
            return ValueScrubber(parent)
        elif val_class == rt.Matrix3:
            
            print("Info: Direct editing of Matrix3 values is not supported.")
            return None
        
        return super().createEditor(parent, option, index)

    def setEditorData(self, editor, index):
        editor.setText(index.model().data(index, QtCore.Qt.DisplayRole))

    def setModelData(self, editor, model, index):
        model.setData(index, editor.text(), QtCore.Qt.EditRole)

class TimelineRuler(QtWidgets.QWidget):
    def __init__(self, timeline_widget, parent=None):
        super().__init__(parent)
        self.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.PreventContextMenu)
        self.timeline_widget = timeline_widget
        self.setFixedHeight(20)
        self.pixels_per_frame = 1.0
        self.start_frame = 0
        self.end_frame = 100
    
    def update_range(self):
        try:
            self.start_frame = int(rt.animationRange.start)
            self.end_frame = int(rt.animationRange.end)
            self.resizeEvent(None)
            self.update()
        except Exception as e:
            print(f"Could not update animation range: {e}")

    def resizeEvent(self, event):
        frame_count = self.end_frame - self.start_frame
        if frame_count > 0:
            self.pixels_per_frame = self.width() / frame_count
        else:
            self.pixels_per_frame = self.width()
        if hasattr(self.timeline_widget, 'keyframe_area'):
            self.timeline_widget.keyframe_area.update()
        if event: super().resizeEvent(event)

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        background_color = QtGui.QColor("#3c3c3c")
        painter.fillRect(self.rect(), background_color)
        pen = QtGui.QPen(QtGui.QColor("#adadad"))
        pen.setWidth(1)
        painter.setPen(pen)
        font = QtGui.QFont("tahoma", 8)
        painter.setFont(font)

        frame_count = self.end_frame - self.start_frame
        if frame_count <= 0 or self.width() <= 0: return

        settings = self.timeline_widget.settings['Ruler_Smart_Ticking']
        if self.pixels_per_frame > settings.getfloat('zoom_level_1_threshold_px'): major_step = settings.getint('zoom_level_1_step_frames')
        elif self.pixels_per_frame > settings.getfloat('zoom_level_2_threshold_px'): major_step = settings.getint('zoom_level_2_step_frames')
        elif self.pixels_per_frame > settings.getfloat('zoom_level_3_threshold_px'): major_step = settings.getint('zoom_level_3_step_frames')
        elif self.pixels_per_frame > settings.getfloat('zoom_level_4_threshold_px'): major_step = settings.getint('zoom_level_4_step_frames')
        else: major_step = settings.getint('default_step_frames')
        
        if major_step == 0: major_step = 1
        minor_step = int(major_step / 2) if major_step > 5 else 1
        if minor_step == 0: minor_step = 1

        for frame in range(self.start_frame, self.end_frame + 1):
            x_pos = (frame - self.start_frame) * self.pixels_per_frame
            if frame % major_step == 0:
                painter.drawLine(int(x_pos), 10, int(x_pos), self.height())
                painter.drawText(QtCore.QRect(int(x_pos) - 50, 0, 100, 10), QtCore.Qt.AlignmentFlag.AlignCenter, str(frame))
            elif frame % minor_step == 0:
                painter.drawLine(int(x_pos), 15, int(x_pos), self.height())
        
        current_frame = self.timeline_widget.current_frame
        if self.start_frame <= current_frame <= self.end_frame:
            slider_x = (current_frame - self.start_frame) * self.pixels_per_frame
            slider_pen = QtGui.QPen(QtGui.QColor("#ff4747"))
            slider_pen.setWidth(2)
            painter.setPen(slider_pen)
            painter.drawLine(int(slider_x), 0, int(slider_x), self.height())

class EasingManager:
    """A dedicated class to handle the logic of applying easing functions to keyframes."""

    # This dictionary maps our UI names to 3ds Max's internal tangent types.
    # Format is: (inTangentType, outTangentType)
    EASE_MAP = {
        # Standard Eases
        "easeIn":      (rt.name('slow'), rt.name('fast')),
        "easeOut":     (rt.name('fast'), rt.name('slow')),
        "easeInOut":   (rt.name('slow'), rt.name('slow')),
        
        # More specific mappings (can be expanded)
        # For Bezier keys, many curves resolve to the same tangent types.
        "easeInSine":    (rt.name('slow'), rt.name('fast')),
        "easeOutSine":   (rt.name('fast'), rt.name('slow')),
        "easeInOutSine": (rt.name('slow'), rt.name('slow')),

        "easeInQuad":    (rt.name('slow'), rt.name('fast')),
        "easeOutQuad":   (rt.name('fast'), rt.name('slow')),
        "easeInOutQuad": (rt.name('slow'), rt.name('slow')),

        "easeInCubic":    (rt.name('slow'), rt.name('fast')),
        "easeOutCubic":   (rt.name('fast'), rt.name('slow')),
        "easeInOutCubic": (rt.name('slow'), rt.name('slow')),
        
        # A simple linear option
        "linear": (rt.name('linear'), rt.name('linear')),
    }

    @staticmethod
    def apply_ease_to_keys(keys, ease_type_name):
        """
        Applies a specific ease type to a list of keyframe objects.
        This is the main function that does the work.
        """
        if not keys or ease_type_name not in EasingManager.EASE_MAP:
            return

        in_tangent, out_tangent = EasingManager.EASE_MAP[ease_type_name]

        try:
            with pymxs.undo(True, f"Apply Easing: {ease_type_name}"):
                for key in keys:
                    # We only change tangents for Bezier keys
                    if rt.isProperty(key, "inTangentType"):
                        key.inTangentType = in_tangent
                        key.outTangentType = out_tangent
            print(f"Applied '{ease_type_name}' to {len(keys)} key(s).")
            
        except Exception as e:
            print(f"Failed to apply easing function. Error: {e}")

class ValueRuler(QtWidgets.QWidget):
    def __init__(self, curve_editor, parent=None):
        super().__init__(parent)
        self.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.PreventContextMenu)
        self.curve_editor = curve_editor
        self.setFixedWidth(50)

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.fillRect(self.rect(), QtGui.QColor("#3c3c3c"))
        painter.setPen(QtGui.QColor("#adadad"))
        font = QtGui.QFont("tahoma", 7)
        painter.setFont(font)

        min_val = self.curve_editor.min_value
        max_val = self.curve_editor.max_value
        val_range = max_val - min_val
        if val_range <= 1e-6: return # Safety check for zero or negative range

        pixels_per_value = self.height() / val_range
        
        min_step_pixels = 30 # Try to keep labels at least 30 pixels apart
        min_value_step = min_step_pixels / pixels_per_value
        
        # ✅ FIX: Use the 'math' library for log and floor operations
        if min_value_step <= 0: return # Another safety check
        power = 10.0 ** math.floor(math.log10(min_value_step))
        
        # Find a "nice" number for the step (e.g., 1, 2, 5)
        if min_value_step / (5.0 * power) < 1.0: step = 5.0 * power
        elif min_value_step / (2.0 * power) < 1.0: step = 2.0 * power
        else: step = 1.0 * power
        
        start_val = math.floor(min_val / step) * step
        
        i = 0
        while True:
            val = start_val + (i * step)
            if val > max_val: break
            
            y_pos = self.curve_editor._value_to_y(val)
            painter.drawLine(self.width() - 5, int(y_pos), self.width(), int(y_pos))
            painter.drawText(0, int(y_pos) - 5, self.width() - 8, 10, QtCore.Qt.AlignmentFlag.AlignRight, f"{val:.2f}")
            i += 1

# =======================================
# # === START: CurveEditorWidget      ===
# =======================================
class CurveEditorWidget(QtWidgets.QWidget):
    def __init__(self, timeline_widget, parent=None):
        super().__init__(parent)
        self.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.PreventContextMenu)
        self.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Expanding)
        self.timeline_widget = timeline_widget
        self.ruler = timeline_widget.ruler

        # Define pens and brushes for drawing
        self.grid_pen = QtGui.QPen(QtGui.QColor("#4a4a4a"))
        self.zero_line_pen = QtGui.QPen(QtGui.QColor("#777777"))
        # --- PENS SHOULD BE SOLID ---
        self.curve_pen_x = QtGui.QPen(QtGui.QColor("#d45656"), 2, QtCore.Qt.PenStyle.SolidLine)
        self.curve_pen_y = QtGui.QPen(QtGui.QColor("#56d456"), 2, QtCore.Qt.PenStyle.SolidLine)
        self.curve_pen_z = QtGui.QPen(QtGui.QColor("#5698d4"), 2, QtCore.Qt.PenStyle.SolidLine)
        
        self.key_brush_x = QtGui.QBrush(QtGui.QColor("#d45656"))
        self.key_brush_y = QtGui.QBrush(QtGui.QColor("#56d456"))
        self.key_brush_z = QtGui.QBrush(QtGui.QColor("#5698d4"))
        self.selected_key_brush = QtGui.QBrush(QtGui.QColor("#d4a056"))
        
        # --- TANGENT PEN IS DOTTED BY DESIGN ---
        self.tangent_pen = QtGui.QPen(QtGui.QColor("#FFFFFF"), 1, QtCore.Qt.PenStyle.DotLine)
        self.handle_brush = QtGui.QBrush(QtGui.QColor("#FFFFFF"))
        self.handle_size = 3.5
        self.key_polygon = QtGui.QPolygonF([QtCore.QPointF(-6, 0), QtCore.QPointF(0, -6), QtCore.QPointF(6, 0), QtCore.QPointF(0, 6)])

        self.min_value = -100.0; self.max_value = 100.0
        self.drag_mode = None; self.panning_info = None; self.dragging_key_info = None
        self.dragging_handle_info = None; self.marquee_rect = None

        self.selected_keys = set()
        self.key_click_margin = 8 # Increased margin for easier clicking
        self.handle_click_margin = 8

    
    def _get_handle_pos(self, key, handle_type):
        time_diff = 5.0
        key_time, key_value = float(key.time), float(key.value)
        if handle_type == 'out':
            tangent_val = float(key.outTangent)
            handle_time, handle_value = key_time + time_diff, key_value + tangent_val * time_diff
        else:
            tangent_val = float(key.inTangent)
            handle_time, handle_value = key_time - time_diff, key_value - tangent_val * time_diff
        return QtCore.QPointF(self._frame_to_x(handle_time), self._value_to_y(handle_value))

    def _handle_at_pos(self, pos):
        if not self.selected_keys: return None
        for controller, index in self.selected_keys:
            try:
                key = controller.keys[index]
                if not rt.isProperty(key, 'inTangent'): continue
                if (self._get_handle_pos(key, 'out') - pos).manhattanLength() < self.handle_click_margin: return (controller, index, 'out')
                if (self._get_handle_pos(key, 'in') - pos).manhattanLength() < self.handle_click_margin: return (controller, index, 'in')
            except IndexError: continue
        return None
        
    def _key_at_pos(self, pos):
        """Finds if there is a key at a given QPoint position."""
        
        
        mouse_pos_f = QtCore.QPointF(pos)
        track_list_widget = self.timeline_widget.track_list_panel.track_tree
        iterator = QtWidgets.QTreeWidgetItemIterator(self.timeline_widget.track_list_panel.track_tree)
        while iterator.value():
            item = iterator.value()
            if not item.isHidden() and item.parent() is not None:
                sub_anim = item.data(0, self.timeline_widget.SUBANIM_ROLE)
                try:
                    if sub_anim and sub_anim.controller:

                        
                        controller_class = rt.classOf(sub_anim.controller)
                        if controller_class in [rt.bezier_float, rt.linear_float, rt.tcb_float]:
                            
                            if rt.isProperty(sub_anim.controller, "keys"):
                                for i in range(sub_anim.controller.keys.count):
                                    key = sub_anim.controller.keys[i]
                                    key_pos = QtCore.QPointF(self._frame_to_x(float(key.time)), self._value_to_y(float(key.value)))
                                    
                                    # Use the converted mouse_pos_f for correct subtraction
                                    if (mouse_pos_f - key_pos).manhattanLength() < self.key_click_margin:
                                        return (sub_anim.controller, i)
                except Exception:
                    # Errors here are now expected for container tracks, so we can safely ignore them.
                    pass
            iterator += 1
        return (None, None)

    def _value_to_y(self, value):
        value_range = self.max_value - self.min_value
        if value_range == 0: return self.height() / 2.0
        return self.height() - (((value - self.min_value) / value_range) * self.height())

    def _frame_to_x(self, frame):
        if self.ruler.pixels_per_frame <= 0: return 0
        return (frame - self.ruler.start_frame) * self.ruler.pixels_per_frame

    def _x_to_frame(self, x_pos):
        if self.ruler.pixels_per_frame <= 0: return 0
        return self.ruler.start_frame + (x_pos / self.ruler.pixels_per_frame)

    def _y_to_value(self, y_pos):
        value_range = self.max_value - self.min_value
        if value_range == 0 or self.height() == 0: return self.min_value
        return self.min_value + (((self.height() - y_pos) / self.height()) * value_range)

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QtGui.QColor("#2d2d2d"))
        
        # Draw Grid
        settings = self.timeline_widget.settings['Ruler_Smart_Ticking']
        if self.ruler.pixels_per_frame > settings.getfloat('zoom_level_1_threshold_px'): major_step = settings.getint('zoom_level_1_step_frames')
        elif self.ruler.pixels_per_frame > settings.getfloat('zoom_level_2_threshold_px'): major_step = settings.getint('zoom_level_2_step_frames')
        else: major_step = 10
        if major_step == 0: major_step = 1
        painter.setPen(self.grid_pen)
        for frame in range(self.ruler.start_frame, self.ruler.end_frame + 1, major_step):
            x_pos = self._frame_to_x(frame); painter.drawLine(int(x_pos), 0, int(x_pos), self.height())
        painter.setPen(self.zero_line_pen)
        painter.drawLine(0, int(self._value_to_y(0)), self.width(), int(self._value_to_y(0)))

        # Draw Curves and Keyframes
        track_list_widget = self.timeline_widget.track_list_panel.track_tree
        iterator = QtWidgets.QTreeWidgetItemIterator(self.timeline_widget.track_list_panel.track_tree)
        while iterator.value():
            item = iterator.value()
            if not item.isHidden() and item.parent() is not None:
                sub_anim = item.data(0, self.timeline_widget.SUBANIM_ROLE)
                try:
                    if sub_anim and sub_anim.controller:
                        
                        
                        controller_class = rt.classOf(sub_anim.controller)
                        if controller_class in [rt.bezier_float, rt.linear_float, rt.tcb_float]:
                            
                            if not (rt.isProperty(sub_anim.controller, "keys") and sub_anim.controller.keys.count > 0):
                                iterator += 1
                                continue # Skip if there are no keys

                            controller = sub_anim.controller
                            keys = controller.keys
                            
                            track_name = item.text(1)
                            active_pen, active_brush = self.curve_pen_z, self.key_brush_z
                            if track_name.startswith("X "): active_pen, active_brush = self.curve_pen_x, self.key_brush_x
                            elif track_name.startswith("Y "): active_pen, active_brush = self.curve_pen_y, self.key_brush_y
                            
                            painter.setPen(active_pen)
                            painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
                            for i in range(keys.count - 1):
                                k1, k2 = keys[i], keys[i+1]
                                k1_time, k1_val = float(k1.time), float(k1.value)
                                k2_time, k2_val = float(k2.time), float(k2.value)
                                p1 = QtCore.QPointF(self._frame_to_x(k1_time), self._value_to_y(k1_val))
                                p2 = QtCore.QPointF(self._frame_to_x(k2_time), self._value_to_y(k2_val))
                                if controller_class == rt.bezier_float:
                                    time_diff_3 = (k2_time - k1_time) / 3.0
                                    c1 = QtCore.QPointF(self._frame_to_x(k1_time + time_diff_3), self._value_to_y(k1_val + float(k1.outTangent) * time_diff_3))
                                    c2 = QtCore.QPointF(self._frame_to_x(k2_time - time_diff_3), self._value_to_y(k2_val - float(k2.inTangent) * time_diff_3))
                                    path = QtGui.QPainterPath(p1); path.cubicTo(c1, c2, p2)
                                    painter.drawPath(path)
                                else: painter.drawLine(p1, p2)

                            painter.setPen(QtCore.Qt.PenStyle.NoPen)
                            for i in range(keys.count):
                                key = keys[i]
                                is_selected = (controller, i) in self.selected_keys
                                painter.setBrush(self.selected_key_brush if is_selected else active_brush)
                                k_pos = QtCore.QPointF(self._frame_to_x(float(key.time)), self._value_to_y(float(key.value)))
                                painter.save(); painter.translate(k_pos); painter.drawPolygon(self.key_polygon); painter.restore()

                except Exception as e:
                    # This print is kept just in case another error appears
                    print(f"A different paint error occurred on track '{item.text(1)}': {e}")
            iterator += 1
        
        # Draw Tangent Handles for selected keys
        for controller, index in self.selected_keys:
            try:
                key = controller.keys[index]
                if rt.isProperty(key, 'inTangent'):
                    key_pos = QtCore.QPointF(self._frame_to_x(float(key.time)), self._value_to_y(float(key.value)))
                    out_handle_pos, in_handle_pos = self._get_handle_pos(key, 'out'), self._get_handle_pos(key, 'in')
                    painter.setPen(self.tangent_pen)
                    painter.drawLine(key_pos, out_handle_pos); painter.drawLine(key_pos, in_handle_pos)
                    painter.setBrush(self.handle_brush); painter.setPen(QtCore.Qt.PenStyle.NoPen)
                    painter.drawEllipse(out_handle_pos, self.handle_size, self.handle_size)
                    painter.drawEllipse(in_handle_pos, self.handle_size, self.handle_size)
            except IndexError: continue
        
        # Draw Time Slider & Marquee
        slider_x = self._frame_to_x(self.timeline_widget.current_frame)
        painter.setPen(QtGui.QPen(QtGui.QColor("#ff4747"), 2))
        painter.drawLine(int(slider_x), 0, int(slider_x), self.height())
        if self.marquee_rect:
            painter.setPen(QtGui.QPen(QtGui.QColor(180, 180, 220, 200), 1, QtCore.Qt.PenStyle.DashLine))
            painter.setBrush(QtGui.QBrush(QtGui.QColor(100, 100, 150, 40)))
            painter.drawRect(self.marquee_rect.normalized())

    def update_value_range(self):
        
        min_val, max_val, found_keys = float('inf'), float('-inf'), False
        track_list_widget = self.timeline_widget.track_list_panel.track_tree
        iterator = QtWidgets.QTreeWidgetItemIterator(self.timeline_widget.track_list_panel.track_tree)
        while iterator.value():
            item = iterator.value()
            if not item.isHidden() and item.parent() is not None:
                sub_anim = item.data(0, self.timeline_widget.SUBANIM_ROLE)
                try:
                    if sub_anim and sub_anim.controller and rt.isProperty(sub_anim.controller, "keys"):
                        if rt.classOf(sub_anim.controller) in [rt.bezier_float, rt.linear_float, rt.tcb_float]:
                            for key in sub_anim.controller.keys:
                                min_val = min(min_val, key.value); max_val = max(max_val, key.value)
                                found_keys = True
                except Exception: pass
            iterator += 1
        if found_keys:
            padding = (max_val - min_val) * 0.15 or 10.0
            self.min_value, self.max_value = min_val - padding, max_val + padding
        else: self.min_value, self.max_value = -100.0, 100.0
        self.update(); self.timeline_widget.value_ruler.update()

    def mousePressEvent(self, event):
        print("\n--- mousePressEvent Fired ---")
        super().mousePressEvent(event)

       
        if event.button() == QtCore.Qt.MouseButton.MiddleButton or \
           (event.button() == QtCore.Qt.MouseButton.LeftButton and event.modifiers() == QtCore.Qt.KeyboardModifier.AltModifier):
            
            self.drag_mode = 'pan'
            self.panning_info = {'last_pos': event.pos()}
            self.setCursor(QtCore.Qt.CursorShape.OpenHandCursor)
            print("-> Mode: Pan")
            event.accept()
            return
            
        # Zoom
        if event.button() == QtCore.Qt.MouseButton.RightButton:
            self.drag_mode = 'zoom'
            self.panning_info = {'last_pos': event.pos()}
            self.setCursor(QtCore.Qt.CursorShape.SizeVerCursor) 
            print("-> Mode: Zoom")
            event.accept()
            return
       

        
        if event.button() != QtCore.Qt.MouseButton.LeftButton: 
            return
        
        self.setFocus()
        modifiers = event.modifiers()
        
        
        handle_info = self._handle_at_pos(event.pos())
        if handle_info:
            self.drag_mode = 'move_handle'
            self.drag_start_pos = event.pos()
            self.dragging_handle_info = handle_info
            
            key_id = (handle_info[0], handle_info[1])
            if key_id not in self.selected_keys:
                if modifiers != QtCore.Qt.KeyboardModifier.ControlModifier:
                    self.selected_keys.clear()
                self.selected_keys.add(key_id)
            
            self.setCursor(QtCore.Qt.CursorShape.SizeHorCursor) 
            self.update()
            return

        controller, key_index = self._key_at_pos(event.pos())
        if controller:
            self.drag_mode = 'move_key'
            self.drag_start_pos = event.pos()
            key_id = (controller, key_index)
            is_key_already_selected = key_id in self.selected_keys

            if not is_key_already_selected:
                if modifiers != QtCore.Qt.KeyboardModifier.ControlModifier:
                    self.selected_keys.clear()
                self.selected_keys.add(key_id)
            elif modifiers == QtCore.Qt.KeyboardModifier.ControlModifier and is_key_already_selected:
                self.selected_keys.remove(key_id)
                self.drag_mode = None
                self.update()
                return

            self.dragging_key_info = {}
            for c, i in self.selected_keys:
                try: self.dragging_key_info[(c,i)] = (float(c.keys[i].time), float(c.keys[i].value))
                except IndexError: pass
            
            self.setCursor(QtCore.Qt.CursorShape.SizeHorCursor)
            self.update()
            return
        
        self.drag_mode = 'marquee'
        self.drag_start_pos = event.pos()
        self.marquee_rect = QtCore.QRect(self.drag_start_pos, QtCore.QSize())
        if not modifiers == QtCore.Qt.KeyboardModifier.ControlModifier: self.selected_keys.clear()
        self.update()

    def mouseMoveEvent(self, event):
        if not self.drag_mode: 
            return super().mouseMoveEvent(event)
        
        # --- [ Pan/Zoom ] ---
        if self.drag_mode == 'pan':
            if not self.panning_info: return
            delta = event.pos() - self.panning_info['last_pos']
            self.panning_info['last_pos'] = event.pos()
            
            # 1. Pan 
            if self.ruler.pixels_per_frame > 0:
                frame_delta = delta.x() / self.ruler.pixels_per_frame
                new_start = self.ruler.start_frame - frame_delta
                new_end = self.ruler.end_frame - frame_delta
                rt.animationRange = rt.interval(int(new_start), int(new_end))
            
             
            value_range = self.max_value - self.min_value
            if value_range > 0 and self.height() > 0:
                value_delta = (delta.y() / self.height()) * value_range
                self.min_value += value_delta
                self.max_value += value_delta
            
            self.update() 
            self.timeline_widget.value_ruler.update() 
            return

        elif self.drag_mode == 'zoom':
            if not self.panning_info: return
            delta_y = event.pos().y() - self.panning_info['last_pos'].y()
            self.panning_info['last_pos'] = event.pos()
            
            zoom_factor = 1.0 - (delta_y * 0.01) 
            center_value = (self.min_value + self.max_value) / 2.0
            new_range = (self.max_value - self.min_value) * zoom_factor
            if new_range < 0.01: new_range = 0.01
            
            self.min_value = center_value - (new_range / 2.0)
            self.max_value = center_value + (new_range / 2.0)
            
            self.update() 
            self.timeline_widget.value_ruler.update() 
            return
        # ---Pan/Zoom ] ---

        
        elif self.drag_mode == 'move_key':
            if not self.dragging_key_info: return
            
            
            delta_x_frames = (event.pos().x() - self.drag_start_pos.x()) / self.ruler.pixels_per_frame
            
            
            delta_y_value = 0
            view_height = self.height()
            value_height = self.min_value - self.max_value
            if view_height != 0 and value_height != 0:
                delta_y_value = (event.pos().y() - self.drag_start_pos.y()) / (view_height / value_height)
            
            try:
                
                with pymxs.undo(False, "Move Curve Keys"):
                    for (c, i), (orig_t, orig_v) in self.dragging_key_info.items():
                        c.keys[i].time = orig_t + delta_x_frames
                        c.keys[i].value = orig_v + delta_y_value
            except Exception: pass
        
            
        elif self.drag_mode == 'move_handle':
            if not self.dragging_handle_info: return
            controller, key_index, handle_type = self.dragging_handle_info
            try:
                key = controller.keys[key_index]
                time_diff = 5.0
                key_time, key_value = float(key.time), float(key.value)
                
                mouse_frame = self._x_to_frame(event.pos().x())
                mouse_value = self._y_to_value(event.pos().y())
                
                new_tangent_val = 0.0
                if handle_type == 'out':
                    if (mouse_frame - key_time) != 0:
                        new_tangent_val = (mouse_value - key_value) / ((mouse_frame - key_time) / time_diff)
                    key.outTangent = new_tangent_val
                else: # 'in'
                    if (key_time - mouse_frame) != 0:
                        new_tangent_val = (key_value - mouse_value) / ((key_time - mouse_frame) / time_diff)
                    key.inTangent = new_tangent_val
            except Exception: pass

        elif self.drag_mode == 'marquee':
            self.marquee_rect.setBottomRight(event.pos())
        
        self.update()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        print(f"--- DEBUG [mouseReleaseEvent], Mode: {self.drag_mode} ---")
        if self.drag_mode == 'marquee' and self.marquee_rect:
            # ... marquee logic is likely fine ...
            normalized_rect = self.marquee_rect.normalized()
            iterator = QtWidgets.QTreeWidgetItemIterator(self.timeline_widget.track_list_panel.track_tree)
            while iterator.value():
                item = iterator.value()
                if item.parent() is not None and not item.isHidden():
                    sub_anim = item.data(0, self.timeline_widget.SUBANIM_ROLE)
                    try:
                        if sub_anim and hasattr(sub_anim, 'controller') and sub_anim.controller:
                            for i in range(sub_anim.controller.keys.count):
                                key = sub_anim.controller.keys[i]
                                key_pos = QtCore.QPoint(int(self._frame_to_x(float(key.time))), int(self._value_to_y(float(key.value))))
                                if normalized_rect.contains(key_pos): self.selected_keys.add((sub_anim.controller, i))
                    except Exception: pass
                iterator += 1
            print(f"-> Marquee selection finished. Total selected: {len(self.selected_keys)}")

        elif self.drag_mode in ['move_key', 'move_handle']:
             try:
                with pymxs.undo(True, "Edit Curve"): pass
                print("-> Undo block created.")
             except Exception as e:
                print(f"DEBUG_ERROR: Could not create undo block: {e}")
             self.timeline_widget._force_ui_refresh()

        self.drag_mode = self.panning_info = self.dragging_key_info = self.dragging_handle_info = self.marquee_rect = None
        self.unsetCursor()
        self.update()
        print("-> Cleaned up state.")

    def set_vertical_zoom(self, value):
        # This is also likely fine
        key_values = []
        for c, i in self.selected_keys:
            try: key_values.append(float(c.keys[i].value))
            except IndexError: pass
        center_value = sum(key_values) / len(key_values) if key_values else (self.min_value + self.max_value) / 2.0
        total_range = 200.0 / (value / 100.0)
        self.min_value = center_value - total_range / 2.0; self.max_value = center_value + total_range / 2.0
        self.update(); self.timeline_widget.value_ruler.update()

# =======================================
# # === END: CurveEditorWidget        ===
# =======================================

# =======================================
# # === START: KeyframeArea           ===
# =======================================
class KeyframeArea(QtWidgets.QWidget):
    def __init__(self, timeline_widget, parent=None):
        super().__init__(parent)
        self.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Expanding)
        self.timeline_widget = timeline_widget
        self.key_polygon = QtGui.QPolygonF([QtCore.QPointF(-4, 0), QtCore.QPointF(0, -4), QtCore.QPointF(4, 0), QtCore.QPointF(0, 4)])
        self.setMouseTracking(True)
        self.setFocusPolicy(QtCore.Qt.FocusPolicy.StrongFocus)
        
        
        self.drag_mode = None
        self.drag_start_pos = None
        self.trim_margin = 5
        self.key_click_margin = 5
        
        
        self.original_clip_ranges = {}
        self.original_key_times = {} 
        self.selected_keys = set()
        self.marquee_rect = None
        self.panning_info = None

    def _item_at(self, y_pos):
        """
        The final and smart version:
        - Correctly detects the active tree widget.
        - In mixer mode, always returns the child item (clip).
        """
        active_tree = self.timeline_widget._get_active_tree_widget()
        is_mixer_mode = (self.timeline_widget.left_view_stack.currentIndex() == 1)
        
        iterator = QtWidgets.QTreeWidgetItemIterator(active_tree, QtWidgets.QTreeWidgetItemIterator.IteratorFlag.NotHidden)
        while iterator.value():
            item = iterator.value()
            rect = active_tree.visualItemRect(item)
            if rect.top() <= y_pos <= rect.bottom():
                
                
               
                if is_mixer_mode and item.parent() is None:
                    
                    if item.childCount() > 0:
                        return item.child(0)
                
                
                return item
            iterator += 1
        return None

    def _get_track_path(self, item):
        path_parts = []
        temp_item = item
        while temp_item is not None and temp_item.parent() is not None:
            subanim_name = temp_item.data(0, self.timeline_widget.SUBANIM_NAME_ROLE)
            if subanim_name: path_parts.insert(0, str(subanim_name))
            temp_item = temp_item.parent()
        return "/".join(path_parts) if path_parts else ""
    
    def _key_at(self, item, x_pos):
        print(f"\n--- DEBUG [_key_at] --- Searching for key at x_pos: {x_pos:.2f}")
        if not item:
            print("-> Exit: No item under cursor.")
            return None, None, None

        is_cache_enabled = self.timeline_widget.track_list_panel.cache_mode_btn.isChecked()
        ruler = self.timeline_widget.ruler

        if is_cache_enabled:
            
            print("-> Mode: CACHED 🚀")
            if item.parent() is None:
                print("-> Exit: Item is a top-level clip, not a track.")
                return None, None, None
            
            parent_clip_item = item
            while parent_clip_item.parent() is not None:
                parent_clip_item = parent_clip_item.parent()
            
            animation_map = parent_clip_item.data(0, self.timeline_widget.CLIP_DATA_ROLE)
            if not animation_map:
                print(f"-> Exit: No animation_map (cache) found on parent clip '{parent_clip_item.text(1)}'.")
                return None, None, None

            track_path = self._get_track_path(item)
            print(f"-> Searching in Track Path: '{track_path}'")
            track_data = animation_map.get("tracks", {}).get(track_path)

            if track_data and "keys" in track_data:
                print(f"  -> Found {len(track_data['keys'])} keys in cache for this track.")
                for i, key_dict in enumerate(track_data["keys"]):
                    key_x_pos = (key_dict["time"] - ruler.start_frame) * ruler.pixels_per_frame
                    
                    # print(f"    - Checking key index {i} at time {key_dict['time']} (x_pos: {key_x_pos:.2f})...")
                    if abs(x_pos - key_x_pos) <= self.key_click_margin:
                        print(f"  ✅ SUCCESS: Key found in cache! Index: {i}, Time: {key_dict['time']}")
                        return parent_clip_item, track_path, i
            else:
                print("  -> No track_data or keys found in cache for this path.")
            
            print("-> No key found at this position in cached mode.")
            return None, None, None
        
        else:
            
            print("-> Mode: LIVE ⚡️")
            sub_anim = item.data(0, self.timeline_widget.SUBANIM_ROLE)
            try:
                if hasattr(sub_anim, 'controller') and sub_anim.controller and rt.isProperty(sub_anim.controller, "keys"):
                    controller = sub_anim.controller
                    print(f"-> Searching in Controller: {controller}")
                    for i in range(controller.keys.count):
                        key = controller.keys[i]
                        key_x_pos = (int(key.time) - ruler.start_frame) * ruler.pixels_per_frame
                        if abs(x_pos - key_x_pos) <= self.key_click_margin:
                            print(f"  ✅ SUCCESS: Key found in live mode! Index: {i}, Time: {key.time}")
                            
                            return controller, None, i
            except Exception as e:
                print(f"  -> ERROR during live search: {e}")
            
            print("-> No key found at this position in live mode.")
            return None, None, None

    def _select_keys_in_max(self):
        try:
            if rt.trackviews.current:
                rt.trackviews.current.clearSelection()
                keys_by_controller = {}
                for controller, _track_path, index in self.selected_keys:
                    if controller not in keys_by_controller: keys_by_controller[controller] = []
                    keys_by_controller[controller].append(index + 1)
                for controller, indices in keys_by_controller.items():
                    rt.selectKeys(controller, indices)
        except Exception: pass


    def wheelEvent(self, event):
        main_scrollbar = self.timeline_widget.track_list_panel.track_tree.verticalScrollBar()
        current_value = main_scrollbar.value()
        delta_y = event.angleDelta().y()
        scroll_amount = delta_y // 4
        new_value = current_value - scroll_amount
        
        print(f"DEBUG [Wheel]: Delta={delta_y}, Amount={scroll_amount}, OldVal={current_value}, NewVal={new_value}")
        
        main_scrollbar.setValue(new_value)
        event.accept()

    def mousePressEvent(self, event):
        
        if event.button() == QtCore.Qt.MouseButton.MiddleButton:
            self.drag_mode = 'pan'
            self.panning_info = {'last_pos': event.pos()}
            self.setCursor(QtCore.Qt.CursorShape.OpenHandCursor)
            event.accept()
            return
            
        
        if event.button() != QtCore.Qt.MouseButton.LeftButton:
            super().mousePressEvent(event)
            return

        print("\n--- mousePressEvent Fired (Left-Click Only) ---")
        super().mousePressEvent(event) 
        
        is_cache_enabled = self.timeline_widget.track_list_panel.cache_mode_btn.isChecked()
        modifiers = event.modifiers()

        item_under_cursor = self._item_at(event.pos().y())         
        is_mixer_mode = (self.timeline_widget.left_view_stack.currentIndex() == 1)

        
        if is_mixer_mode:
            print("  -> Mode: Motion Mixer")
            mixer_tree = self.timeline_widget.motion_mixer_panel.track_tree
            print(f"  -> Item under cursor: {item_under_cursor.text(0) if item_under_cursor else 'None'}")

            if item_under_cursor and item_under_cursor.parent() is not None: 
                print("  -> Condition MET: Item is a valid clip (child item).")
                self.drag_mode = 'move_mixer_clip'
                self.drag_start_pos = event.pos()
                self.original_clip_ranges.clear()
                try:
                    start_frame = int(item_under_cursor.text(2))
                    end_frame = int(item_under_cursor.text(3))
                    self.original_clip_ranges[item_under_cursor] = (start_frame, end_frame)
                    print(f"  -> SUCCESS: Drag mode set to 'move_mixer_clip' for '{item_under_cursor.text(0)}'.")
                except (ValueError, IndexError) as e:
                    self.drag_mode = None 
                    print(f"  -> FAILED: Could not read start/end frames. Error: {e}")
                    return
                mixer_tree.setCurrentItem(item_under_cursor)
                self.setCursor(QtCore.Qt.CursorShape.OpenHandCursor)
                self.update()
            return
        
        
        else:
            tree_widget = self.timeline_widget.track_list_panel.track_tree
            tree_widget.mousePressEvent(event) 

            
            p_clip_or_controller, track_path, key_index = self._key_at(item_under_cursor, event.pos().x())
            print(f"-> _key_at result: Controller/Clip={p_clip_or_controller}, Path='{track_path}', Index={key_index}")
            
            if p_clip_or_controller and key_index is not None:
                print("DEBUG [Press]: Key found. Evaluating multi-select drag logic...")
                self.drag_mode = 'move_key'
                self.drag_start_pos = event.pos() 
                key_id = (p_clip_or_controller, track_path, key_index)
                is_key_already_selected = key_id in self.selected_keys
                print(f"  -> Is the clicked key already selected? {is_key_already_selected}")
                if not is_key_already_selected:
                    print("  -> Clicked key is NEW to the selection.")
                    if modifiers != QtCore.Qt.KeyboardModifier.ControlModifier:
                        print("  -> No 'Ctrl' key. Clearing previous selection.")
                        self.selected_keys.clear()
                    self.selected_keys.add(key_id)
                elif modifiers == QtCore.Qt.KeyboardModifier.ControlModifier and is_key_already_selected:
                    print("  -> 'Ctrl' key pressed on a selected key. REMOVING it.")
                    self.selected_keys.remove(key_id)
                    self.drag_mode = None
                    self.update() 
                    return
                print(f"  -> Final selection count for drag operation: {len(self.selected_keys)}")
                self.original_key_times.clear()
                for id_part1, id_part2, id_part3 in self.selected_keys:
                    try:
                        if is_cache_enabled:
                            anim_map = id_part1.data(0, self.timeline_widget.CLIP_DATA_ROLE)
                            self.original_key_times[(id_part1, id_part2, id_part3)] = anim_map['tracks'][id_part2]['keys'][id_part3]['time']
                        else:
                            self.original_key_times[(id_part1, id_part2, id_part3)] = int(id_part1.keys[id_part3].time)
                    except (KeyError, IndexError, AttributeError) as e:
                        print(f"  -> WARNING: Could not get original time for a key. Error: {e}")
                self.setCursor(QtCore.Qt.CursorShape.SizeHorCursor)
                self.update()
                return
            
            
            if item_under_cursor and item_under_cursor.parent() is None:
                self.drag_start_pos = event.pos() 
                self.original_clip_ranges.clear()
                for item in tree_widget.selectedItems():
                    if item.parent() is None:
                        start, end = item.data(0, self.timeline_widget.CLIP_START_ROLE), item.data(0, self.timeline_widget.CLIP_END_ROLE)
                        if start is not None: self.original_clip_ranges[item] = (start, end)
                
                start_frame, end_frame = self.original_clip_ranges.get(item_under_cursor, (None, None))
                if start_frame is None: return

                ruler = self.timeline_widget.ruler
                clip_start_x = (start_frame - ruler.start_frame) * ruler.pixels_per_frame
                clip_end_x = (end_frame - ruler.start_frame) * ruler.pixels_per_frame
                x_pos = event.pos().x()

                self.drag_mode = None
                on_start_edge = abs(x_pos - clip_start_x) < self.trim_margin
                on_end_edge = abs(x_pos - clip_end_x) < self.trim_margin

                
                if modifiers == QtCore.Qt.KeyboardModifier.AltModifier and (on_start_edge or on_end_edge):
                    self.drag_mode = 'scale_start' if on_start_edge else 'scale_end'
                elif on_start_edge: self.drag_mode = 'trim_start'
                elif on_end_edge: self.drag_mode = 'trim_end'
                else: self.drag_mode = 'move'
                
                print(f"DEBUG [Press]: Mode determined -> '{self.drag_mode}'")
                self.setCursor(QtCore.Qt.CursorShape.SizeHorCursor if 'trim' in self.drag_mode or 'scale' in self.drag_mode else QtCore.Qt.CursorShape.OpenHandCursor)
                
                if self.drag_mode in ['move', 'scale_start', 'scale_end']:
                    self.original_key_times.clear()
                    self.selected_keys.clear()
                    def find_keys_in_item_recursive(parent_item, start_f, end_f):
                        for i in range(parent_item.childCount()):
                            child_item = parent_item.child(i)
                            sub_anim = child_item.data(0, self.timeline_widget.SUBANIM_ROLE)
                            try:
                                if hasattr(sub_anim, 'controller') and sub_anim.controller and rt.isProperty(sub_anim.controller, "keys"):
                                    controller = sub_anim.controller
                                    for key_index in range(controller.keys.count):
                                        key = controller.keys[key_index]
                                        if start_f <= key.time <= end_f:
                                            self.original_key_times[(controller, key_index)] = int(key.time)
                                            self.selected_keys.add((controller, key_index))
                            except Exception: pass
                            if child_item.childCount() > 0: find_keys_in_item_recursive(child_item, start_f, end_f)
                    for item in tree_widget.selectedItems():
                        if item.parent() is None:
                            clip_range = self.original_clip_ranges.get(item)
                            if clip_range: find_keys_in_item_recursive(item, clip_range[0], clip_range[1])
                    print(f"DEBUG [Press]: Found {len(self.original_key_times)} keys to '{self.drag_mode}'.")
                
                self.update(); 
                return 

            
            self.drag_mode = 'marquee_select'
            self.drag_start_pos = event.pos() 
            self.marquee_rect = QtCore.QRect(self.drag_start_pos, QtCore.QSize())
            if not modifiers == QtCore.Qt.KeyboardModifier.ControlModifier: self.selected_keys.clear()
            print("DEBUG [Press]: Mode determined -> 'marquee_select'")
            self.update()

    def mouseMoveEvent(self, event):
        
        if not self.drag_mode: 
            return super().mouseMoveEvent(event)

        ruler = self.timeline_widget.ruler

        
        if self.drag_mode == 'pan':
            if not self.panning_info: return
            delta = event.pos() - self.panning_info['last_pos']
            self.panning_info['last_pos'] = event.pos()
            
            if ruler.pixels_per_frame > 0:
                frame_delta = delta.x() / ruler.pixels_per_frame
                new_start = ruler.start_frame - frame_delta
                new_end = ruler.end_frame - frame_delta
                rt.animationRange = rt.interval(int(new_start), int(new_end))
            
            self.update() 
            return 

        
        elif self.drag_mode == 'marquee_select':
            self.marquee_rect.setBottomRight(event.pos())
            self.update()
            return
            
        
        if ruler.pixels_per_frame <= 0: return
        delta_frames = round((event.pos().x() - self.drag_start_pos.x()) / ruler.pixels_per_frame)
        

        if self.drag_mode == 'move_mixer_clip':
            for item, (orig_start, orig_end) in self.original_clip_ranges.items():
                duration = orig_end - orig_start
                new_start = orig_start + delta_frames
                item.setText(2, str(new_start))
                item.setText(3, str(new_start + duration))
            self.update()
            return 
        
        
        is_cache_enabled = self.timeline_widget.track_list_panel.cache_mode_btn.isChecked()

        if self.drag_mode == 'move_key':
            for key_id, original_time in self.original_key_times.items():
                p_clip_or_controller, track_path, key_index = key_id
                new_time = original_time + delta_frames
                if is_cache_enabled:
                    anim_map = p_clip_or_controller.data(0, self.timeline_widget.CLIP_DATA_ROLE)
                    anim_map['tracks'][track_path]['keys'][key_index]['time'] = new_time
                else:
                    try: p_clip_or_controller.keys[key_index].time = new_time
                    except Exception: pass
            self.update()
            return 
        
        
        if self.drag_mode == 'move':
            for item, (orig_start, orig_end) in self.original_clip_ranges.items():
                item.setData(0, self.timeline_widget.CLIP_START_ROLE, orig_start + delta_frames)
                item.setData(0, self.timeline_widget.CLIP_END_ROLE, orig_end + delta_frames)
            try:
                for (controller, index), original_time in self.original_key_times.items():
                    controller.keys[index].time = original_time + delta_frames
            except Exception as e: print(f"Error moving keys: {e}")

        elif self.drag_mode == 'trim_start':
            for item, (orig_start, orig_end) in self.original_clip_ranges.items():
                new_start = min(orig_start + delta_frames, orig_end - 1)
                item.setData(0, self.timeline_widget.CLIP_START_ROLE, new_start)
        
        elif self.drag_mode == 'trim_end':
            for item, (orig_start, orig_end) in self.original_clip_ranges.items():
                new_end = max(orig_end + delta_frames, orig_start + 1)
                item.setData(0, self.timeline_widget.CLIP_END_ROLE, new_end)
        
        elif self.drag_mode in ['scale_start', 'scale_end']:
            for item, (orig_start, orig_end) in self.original_clip_ranges.items():
                original_duration = orig_end - orig_start
                if original_duration <= 0: continue
                
                if self.drag_mode == 'scale_start':
                    new_start = min(orig_start + delta_frames, orig_end - 1)
                    item.setData(0, self.timeline_widget.CLIP_START_ROLE, new_start)
                    pivot_frame = orig_end
                else: 
                    new_end = max(orig_end + delta_frames, orig_start + 1)
                    item.setData(0, self.timeline_widget.CLIP_END_ROLE, new_end)
                    pivot_frame = orig_start
                
                new_duration = item.data(0, self.timeline_widget.CLIP_END_ROLE) - item.data(0, self.timeline_widget.CLIP_START_ROLE)
                
                if original_duration == 0: continue
                scale_factor = new_duration / original_duration
                
                print(f"\rDEBUG [Scale]: Factor={scale_factor:.2f}, Pivot Frame={pivot_frame}   ", end="") 

                for (controller, index), original_time in self.original_key_times.items():
                    try:
                        distance_from_pivot = original_time - pivot_frame
                        new_time = pivot_frame + (distance_from_pivot * scale_factor)
                        controller.keys[index].time = new_time
                    except Exception as e:
                        print(f"Error scaling key: {e}")

    def mouseReleaseEvent(self, event):
        print(f"\n--- DEBUG [mouseReleaseEvent] --- ")
        is_cache_enabled = self.timeline_widget.track_list_panel.cache_mode_btn.isChecked()
        
        if self.drag_mode == 'move_key':
            
            if is_cache_enabled and self.selected_keys:
                try:
                    with pymxs.undo(True, "Move Timeline Keys (Cached)"):
                        for p_clip, t_path, k_idx in self.selected_keys:
                            anim_map = p_clip.data(0, self.timeline_widget.CLIP_DATA_ROLE)
                            track_data = anim_map['tracks'][t_path]
                            controller = track_data['controller_ref']
                            final_time = track_data['keys'][k_idx]['time']
                            controller.keys[k_idx].time = final_time
                except Exception as e:
                    print(f"ERROR: Could not commit cached key changes: {e}")
            
            elif not is_cache_enabled:
                 with pymxs.undo(True, "Move Timeline Keys (Live)"): pass
        
        elif self.drag_mode == 'marquee_select' and self.marquee_rect:
            normalized_rect = self.marquee_rect.normalized()
            iterator = QtWidgets.QTreeWidgetItemIterator(self.timeline_widget.track_list_panel.track_tree)
            while iterator.value():
                item = iterator.value()
                if item.parent() is not None:
                    rect = self.timeline_widget.track_list_panel.track_tree.visualItemRect(item)
                    if normalized_rect.intersects(rect):
                         sub_anim = item.data(0, self.timeline_widget.SUBANIM_ROLE)
                         try:
                            if hasattr(sub_anim, 'controller') and sub_anim.controller and rt.isProperty(sub_anim.controller, "keys"):
                                for i in range(sub_anim.controller.keys.count):
                                    key = sub_anim.controller.keys[i]
                                    key_x = (int(key.time) - self.timeline_widget.ruler.start_frame) * self.timeline_widget.ruler.pixels_per_frame
                                    if normalized_rect.left() <= key_x <= normalized_rect.right():
                                        #self.selected_keys.add((sub_anim.controller, i))
                                        self.selected_keys.add((sub_anim.controller, None, i))
                         except Exception: pass
                         except Exception: pass
                iterator += 1
            self._select_keys_in_max()

        elif self.drag_mode in ['move_key', 'move', 'trim_start', 'trim_end', 'scale_start', 'scale_end']:
            try:
                with pymxs.undo(True, f"Timeline Edit: {self.drag_mode}"): pass
                if self.drag_mode != 'move_key': self.timeline_widget._save_timeline_state()
            except Exception: pass
        elif self.drag_mode in ['move_key', 'move', 'trim_start', 'trim_end', 'scale_start', 'scale_end', 'move_mixer_clip']:
            try:
                with pymxs.undo(True, f"Timeline Edit: {self.drag_mode}"): pass
                
                
                if self.drag_mode not in ['move_key', 'move_mixer_clip']: 
                    self.timeline_widget._save_timeline_state()
            except Exception: pass
        
        
        self.drag_mode = None
        self.drag_start_pos = None
        self.marquee_rect = None
        self.original_key_times.clear()
        self.original_clip_ranges.clear()
        self.unsetCursor()
        self.update() 
        self.timeline_widget._force_ui_refresh()
        super().mouseReleaseEvent(event)


    
    def sync_scrollbars(self):
        """
        Smart version: Adjusts height and scroll to match the active tree widget.
        """
        active_tree = self._get_active_tree_widget()
        keyframe_widget = self.keyframe_area
        key_scroll_area = self.editor_scroll_area

        
        content_height = active_tree.header().height()
        iterator = QtWidgets.QTreeWidgetItemIterator(active_tree)
        max_y = 0
        while iterator.value():
            item = iterator.value()
            if not item.isHidden():
                max_y = max(max_y, active_tree.visualItemRect(item).bottom())
            iterator += 1
        content_height = max_y if max_y > 0 else content_height

        keyframe_widget.setMinimumHeight(content_height)

        
        track_sb = active_tree.verticalScrollBar()
        key_sb = key_scroll_area.verticalScrollBar()
        
        key_sb.blockSignals(True)
        key_sb.setRange(track_sb.minimum(), track_sb.maximum())
        key_sb.setPageStep(track_sb.pageStep())
        key_sb.setValue(track_sb.value())
        key_sb.blockSignals(False)
        
        keyframe_widget.update()
        
    
    
    # paintEvent 
    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        background_color = QtGui.QColor("#2d2d2d")
        grid_pen = QtGui.QPen(QtGui.QColor("#4a4a4a")); grid_pen.setWidth(1)
        key_brush = QtGui.QBrush(QtGui.QColor("#5698d4"))
        selected_key_brush = QtGui.QBrush(QtGui.QColor("#d4a056"))
        key_pen = QtGui.QPen(QtGui.QColor("#8cceff"))
        painter.fillRect(self.rect(), background_color)
        track_list_widget = self.timeline_widget.track_list_panel.track_tree
        ruler = self.timeline_widget.ruler
        
        is_cache_enabled = self.timeline_widget.track_list_panel.cache_mode_btn.isChecked()
        is_mixer_mode = (self.timeline_widget.left_view_stack.currentIndex() == 1)

        if is_mixer_mode:
            mixer_tree = self.timeline_widget.motion_mixer_panel.track_tree
            
            for i in range(mixer_tree.topLevelItemCount()):
                track_item = mixer_tree.topLevelItem(i)
                track_rect = mixer_tree.visualItemRect(track_item)

                y_bottom = track_rect.bottom()
                painter.setPen(grid_pen)
                painter.drawLine(0, y_bottom, self.width(), y_bottom)

                for j in range(track_item.childCount()):
                    clip_item = track_item.child(j)
                    
                    try:
                        
                        start_frame = int(clip_item.text(2))
                        end_frame = int(clip_item.text(3))

                        clip_start_x = (start_frame - ruler.start_frame) * ruler.pixels_per_frame
                        clip_end_x = (end_frame - ruler.start_frame) * ruler.pixels_per_frame
                        
                        clip_rect = QtCore.QRectF(clip_start_x, track_rect.top() + 2, clip_end_x - clip_start_x, track_rect.height() - 4)
                        
                        clip_brush = QtGui.QBrush(QtGui.QColor("#6D475A")) 
                        if clip_item.isSelected() or track_item.isSelected():
                            clip_brush = QtGui.QBrush(QtGui.QColor("#9E6984"))
                        
                        clip_pen = QtGui.QPen(clip_brush.color().lighter(150))
                        painter.setPen(clip_pen); painter.setBrush(clip_brush)
                        painter.drawRoundedRect(clip_rect, 3, 3)

                        # ==========================
                        # === Fade-in , Fade-out ===
                        # ==========================
                        crossfade_data = clip_item.data(0, self.timeline_widget.CROSSFADE_ROLE)
                        if isinstance(crossfade_data, dict):
                            
                            # --- Fade-In---
                            if 'fade_in' in crossfade_data:
                                duration = crossfade_data['fade_in'].get('duration', 0)
                                if duration > 0:
                                    fade_width_px = duration * ruler.pixels_per_frame
                                    fade_rect = QtCore.QRectF(clip_rect.left(), clip_rect.top(), fade_width_px, clip_rect.height())
                                    
                                    
                                    painter.setPen(QtCore.Qt.PenStyle.NoPen)
                                    painter.setBrush(QtGui.QBrush(QtGui.QColor(0, 0, 0, 70)))
                                    painter.drawRect(fade_rect)
                                    
                                    
                                    painter.setPen(QtGui.QPen(QtGui.QColor(255, 255, 255, 150), 1))
                                    painter.drawLine(fade_rect.topLeft(), fade_rect.bottomRight())
                                    
                                    
                                    font = painter.font(); font.setPointSize(7); painter.setFont(font)
                                    painter.drawText(fade_rect, QtCore.Qt.AlignmentFlag.AlignCenter, f"{duration}f")

                            # --- Fade-Out---
                            if 'fade_out' in crossfade_data:
                                duration = crossfade_data['fade_out'].get('duration', 0)
                                if duration > 0:
                                    fade_width_px = duration * ruler.pixels_per_frame
                                    fade_rect = QtCore.QRectF(clip_rect.right() - fade_width_px, clip_rect.top(), fade_width_px, clip_rect.height())
                                    
                                    
                                    painter.setPen(QtCore.Qt.PenStyle.NoPen)
                                    painter.setBrush(QtGui.QBrush(QtGui.QColor(0, 0, 0, 70)))
                                    painter.drawRect(fade_rect)
                                    
                                    
                                    painter.setPen(QtGui.QPen(QtGui.QColor(255, 255, 255, 150), 1))
                                    painter.drawLine(fade_rect.topRight(), fade_rect.bottomLeft())
                                    
                                    
                                    font = painter.font(); font.setPointSize(7); painter.setFont(font)
                                    painter.drawText(fade_rect, QtCore.Qt.AlignmentFlag.AlignCenter, f"{duration}f")
                        

                        
                        painter.setPen(QtCore.Qt.GlobalColor.white)
                        painter.drawText(clip_rect.adjusted(5, 0, -5, 0), QtCore.Qt.AlignmentFlag.AlignVCenter, clip_item.text(0))

                    except (ValueError, IndexError):
                        continue
        else:
            
            track_list_widget = self.timeline_widget.track_list_panel.track_tree
            is_cache_enabled = self.timeline_widget.track_list_panel.cache_mode_btn.isChecked()
            iterator = QtWidgets.QTreeWidgetItemIterator(track_list_widget, QtWidgets.QTreeWidgetItemIterator.IteratorFlag.NotHidden)
            while iterator.value():
                item = iterator.value()
                rect = track_list_widget.visualItemRect(item)
                
                if item.parent() is None:
                    start_frame = item.data(0, self.timeline_widget.CLIP_START_ROLE)
                    end_frame = item.data(0, self.timeline_widget.CLIP_END_ROLE)
                    if start_frame is not None and end_frame is not None and ruler.pixels_per_frame > 0:
                        clip_start_x = (start_frame - ruler.start_frame) * ruler.pixels_per_frame
                        clip_end_x = (end_frame - ruler.start_frame) * ruler.pixels_per_frame
                        clip_rect = QtCore.QRectF(clip_start_x, rect.top() + 2, clip_end_x - clip_start_x, rect.height() - 4)
                        clip_brush = item.background(1)
                        clip_pen = QtGui.QPen(clip_brush.color().lighter(150))
                        painter.setPen(clip_pen); painter.setBrush(clip_brush)
                        painter.drawRoundedRect(clip_rect, 3, 3)
                else:
                    y_center = rect.center().y()
                    
                    if is_cache_enabled:
                        parent_clip_item = item
                        while parent_clip_item.parent() is not None: parent_clip_item = parent_clip_item.parent()
                        animation_map = parent_clip_item.data(0, self.timeline_widget.CLIP_DATA_ROLE)
                        if animation_map:
                            track_path = self._get_track_path(item)
                            track_data = animation_map.get("tracks", {}).get(track_path)
                            if track_data and "keys" in track_data:
                                for i, key_dict in enumerate(track_data["keys"]):
                                    key_frame = key_dict["time"]
                                    if ruler.start_frame <= key_frame <= ruler.end_frame:
                                        x_pos = (key_frame - ruler.start_frame) * ruler.pixels_per_frame
                                        key_id = (parent_clip_item, track_path, i)
                                        is_selected = key_id in self.selected_keys
                                        current_brush = selected_key_brush if is_selected else key_brush
                                        painter.setPen(key_pen); painter.setBrush(current_brush)
                                        painter.save(); painter.translate(x_pos, y_center); painter.drawPolygon(self.key_polygon); painter.restore()
                    else:
                        sub_anim = item.data(0, self.timeline_widget.SUBANIM_ROLE)
                        try:
                            if hasattr(sub_anim, 'controller') and sub_anim.controller and rt.isProperty(sub_anim.controller, "keys"):
                                controller = sub_anim.controller
                                for idx in range(controller.keys.count):
                                    key = controller.keys[idx]
                                    key_frame = int(key.time)
                                    if ruler.start_frame <= key_frame <= ruler.end_frame:
                                        x_pos = (key_frame - ruler.start_frame) * ruler.pixels_per_frame
                                        is_selected = (controller, None, idx) in self.selected_keys
                                        current_brush = selected_key_brush if is_selected else key_brush
                                        painter.setPen(key_pen); painter.setBrush(current_brush)
                                        painter.save(); painter.translate(x_pos, y_center); painter.drawPolygon(self.key_polygon); painter.restore()
                        except Exception: pass

                y_bottom = rect.bottom()
                painter.setPen(grid_pen)
                painter.drawLine(0, y_bottom, self.width(), y_bottom)
                iterator += 1

        # Frame Slider 
        current_frame = self.timeline_widget.current_frame
        if ruler.start_frame <= current_frame <= ruler.end_frame and ruler.pixels_per_frame > 0:
            slider_x = (current_frame - ruler.start_frame) * ruler.pixels_per_frame
            slider_pen = QtGui.QPen(QtGui.QColor("#ff4747")); slider_pen.setWidth(2)
            painter.setPen(slider_pen)
            painter.drawLine(int(slider_x), 0, int(slider_x), self.height())
        if self.marquee_rect:
            marquee_pen = QtGui.QPen(QtGui.QColor(180, 180, 220, 200), 1, QtCore.Qt.PenStyle.DashLine)
            marquee_brush = QtGui.QBrush(QtGui.QColor(100, 100, 150, 40))
            painter.setPen(marquee_pen); painter.setBrush(marquee_brush)
            painter.drawRect(self.marquee_rect.normalized())

    def keyPressEvent(self, event):
        if event.key() == QtCore.Qt.Key.Key_Delete: self.delete_selected_keys()
        else: super().keyPressEvent(event)
            
    def contextMenuEvent(self, event):
        event.accept()
        is_mixer_mode = (self.timeline_widget.left_view_stack.currentIndex() == 1)
        
        if is_mixer_mode:
            # Motion Mixer ---
            item = self._item_at(event.pos().y())
            if not item or item.parent() is None:
                return

            menu = QtWidgets.QMenu(self)
            track_item = item.parent()
            track_index = self.timeline_widget.motion_mixer_panel.track_tree.indexOfTopLevelItem(track_item)
            
            can_fade_in = (track_index > 0 and self.timeline_widget.motion_mixer_panel.track_tree.topLevelItem(track_index - 1).childCount() > 0)
            can_fade_out = (track_index < self.timeline_widget.motion_mixer_panel.track_tree.topLevelItemCount() - 1 and self.timeline_widget.motion_mixer_panel.track_tree.topLevelItem(track_index + 1).childCount() > 0)

            if can_fade_in:
                fade_in_action = menu.addAction("Create/Edit Fade-In From Below...")
                fade_in_action.triggered.connect(lambda: self.timeline_widget.logic.setup_crossfade_for_clip(item, 'in'))

            if can_fade_out:
                fade_out_action = menu.addAction("Create/Edit Fade-Out To Above...")
                fade_out_action.triggered.connect(lambda: self.timeline_widget.logic.setup_crossfade_for_clip(item, 'out'))
            
            if menu.isEmpty():
                return
            
            menu.exec_(event.globalPos())
            
        else: 
            # --- Track List  ---
            item_under_cursor = self._item_at(event.pos().y())
            if item_under_cursor and item_under_cursor.parent() is None:
                menu = QtWidgets.QMenu(self)
                export_action = menu.addAction("Export Animation as .clip")
                export_action.triggered.connect(lambda: self.timeline_widget._export_clip_to_file(item_under_cursor))
                menu.exec_(event.globalPos())
                return

            p_clip_or_controller, track_path, key_index = self._key_at(item_under_cursor, event.pos().x()) if item_under_cursor else (None, None, None)
            if p_clip_or_controller and key_index is not None:
                key_id = (p_clip_or_controller, track_path, key_index)
                if key_id not in self.selected_keys:
                    self.selected_keys.clear()
                    self.selected_keys.add(key_id)
                    self.update()
                menu = QtWidgets.QMenu(self)
                if self.selected_keys:
                    easing_menu = menu.addMenu("Apply Easing")
                    menu_structure = {
                        "Sine": [("Ease In", "easeInSine"), ("Ease Out", "easeOutSine"), ("Ease In-Out", "easeInOutSine")],
                        "Quad": [("Ease In", "easeInQuad"), ("Ease Out", "easeOutQuad"), ("Ease In-Out", "easeInOutQuad")],
                        "Cubic": [("Ease In", "easeInCubic"), ("Ease Out", "easeOutCubic"), ("Ease In-Out", "easeInOutCubic")],
                    }
                    for category, items in menu_structure.items():
                        category_menu = easing_menu.addMenu(category)
                        for display_name, internal_name in items:
                            action = category_menu.addAction(display_name)
                            action.triggered.connect(lambda checked=False, name=internal_name: self.apply_ease_to_selection(name))
                    easing_menu.addSeparator()
                    linear_action = easing_menu.addAction("Linear")
                    linear_action.triggered.connect(lambda: self.apply_ease_to_selection("linear"))
                    menu.addSeparator()
                delete_action = menu.addAction("Delete Key(s)")
                delete_action.triggered.connect(self.delete_selected_keys)
                menu.exec_(event.globalPos())
                return

        
        #super().contextMenuEvent(event)

    def apply_ease_to_selection(self, ease_type_name):
        if not self.selected_keys: return
        key_objects = [c.keys[i] for c, _track_path, i in self.selected_keys]
        EasingManager.apply_ease_to_keys(key_objects, ease_type_name)
        self.update()

    def delete_selected_keys(self):
        if not self.selected_keys: return
        keys_by_controller = {}
        for controller, _track_path, index in self.selected_keys:
            if controller not in keys_by_controller: keys_by_controller[controller] = []
            keys_by_controller[controller].append(index)
        try:
            with pymxs.undo(True, "Delete Selected Keys"):
                for controller, indices in keys_by_controller.items():
                    # Sort indices in reverse to avoid shifting problems during deletion
                    for index in sorted(indices, reverse=True):
                        rt.deleteItem(controller.keys, index + 1)
            self.selected_keys.clear()
            self.update()
            self.timeline_widget._force_ui_refresh()
        except Exception as e: print(f"Error during deletion: {e}")

# =======================================
# # === END: KeyframeArea             ===
# =======================================

# =======================================
# # === START: MyTimelineWidget       ===
# =======================================
class MyTimelineWidget(QtWidgets.QWidget):
    SUBANIM_ROLE = QtCore.Qt.ItemDataRole.UserRole + 0
    PARENT_OBJ_ROLE = QtCore.Qt.ItemDataRole.UserRole + 1
    SUBANIM_NAME_ROLE = QtCore.Qt.ItemDataRole.UserRole + 2
    CLIP_START_ROLE = QtCore.Qt.ItemDataRole.UserRole + 3
    CLIP_END_ROLE = QtCore.Qt.ItemDataRole.UserRole + 4
    VISIBILITY_ROLE = QtCore.Qt.ItemDataRole.UserRole + 5
    CLIP_DATA_ROLE = QtCore.Qt.ItemDataRole.UserRole + 6
    CLIP_UID_ROLE = QtCore.Qt.ItemDataRole.UserRole + 7
    BLEND_MODE_ROLE = QtCore.Qt.ItemDataRole.UserRole + 8
    CROSSFADE_ROLE = QtCore.Qt.ItemDataRole.UserRole + 9

    DEFAULT_HIDDEN_TRACKS = sorted({
        "Visibility", "Space Warps", "Material", "Object",
        "Image Motion Blur Multiplier", "Object Motion Blur On Off",
        "Object (Vray Properties)", "Object (Mental Ray)", "Image Bitmap",
        "Render Effects", "Sound", "Global Tracks", "MasterPoint Controller"
    })
    FILTERABLE_TRACKS = sorted([
        "Visibility", "Space Warps", "Material", "Object",
        "Image Motion Blur Multiplier", "Object Motion Blur On Off",
        "Object (Vray Properties)", "Object (Mental Ray)", "Image Bitmap",
        "Render Effects", "Sound", "Global Tracks", "MasterPoint Controller"
    ])
    
    def __init__(self, parent_toolbar=None):
        super().__init__(parent_toolbar)
        self.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.PreventContextMenu)
        global _g_timeline_instance
        _g_timeline_instance = self
        self.rt = pymxs.runtime
        self.parent_toolbar = parent_toolbar
        self.settings = load_settings()
        
        

        self.save_callback_id = "myTimelineProSaveCallback"
        self.selection_callback_id = "myTimelineProSelectionCallback"
        self.current_frame = int(rt.currentTime)
        self.markers = {}
        self.last_start_frame = 0; self.last_end_frame = 0
        self.is_renaming_from_ui = False
        self.is_updating_values = False
        self.red_icon = self.create_color_icon(QtGui.QColor(255, 70, 70))
        self.green_icon = self.create_color_icon(QtGui.QColor(70, 255, 70))
        self.blue_icon = self.create_color_icon(QtGui.QColor(70, 70, 255))
        self.eye_open_icon = QtGui.QIcon(os.path.join(SCRIPT_PATH, 'icons', 'eye-open.png').replace('\\', '/'))
        self.eye_closed_icon = QtGui.QIcon(os.path.join(SCRIPT_PATH, 'icons', 'eye-closed.png').replace('\\', '/'))
        self.is_syncing_selection = False

        print("DEBUG: MyTimelineWidget initializing...")
        self.logic = TimelineLogic(self)
        self.logic._load_default_hidden_tracks_from_settings()
        self.logic._register_save_callback()
        self.logic._register_selection_callback()
        
        self.main_layout = QtWidgets.QHBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal)
        self.main_layout.addWidget(splitter)
        
        # Left Panel
        left_panel = QtWidgets.QWidget()
        left_layout = QtWidgets.QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(0)
        
        # Top Bar
        top_bar_widget = QtWidgets.QWidget()
        top_bar_layout = QtWidgets.QHBoxLayout(top_bar_widget)
        top_bar_layout.setContentsMargins(5, 5, 5, 5)

        self.mixer_toggle_btn = QtWidgets.QPushButton("Motion Mixer")
        self.mixer_toggle_btn.setCheckable(True)
        self.mixer_toggle_btn.clicked.connect(self._toggle_left_view)
        
        self.filter_hidden_btn = QtWidgets.QPushButton("Show Hidden")
        self.filter_hidden_btn.setCheckable(True); self.filter_hidden_btn.setChecked(False)
        self.filter_hidden_btn.clicked.connect(self.apply_visibility_filter)
        
        settings_btn = QtWidgets.QPushButton("Settings")
        settings_btn.clicked.connect(self.open_settings_dialog)
        
        close_btn = QtWidgets.QPushButton("X")
        close_btn.clicked.connect(self.close_parent_toolbar)

        top_bar_layout.addWidget(self.mixer_toggle_btn)
        top_bar_layout.addStretch()
        top_bar_layout.addWidget(self.filter_hidden_btn)
        top_bar_layout.addWidget(settings_btn)
        top_bar_layout.addWidget(close_btn)
        
        # Left View
        self.left_view_stack = QtWidgets.QStackedWidget()
        
        
        self.track_list_panel = TrackListPanel(self)
        self.motion_mixer_panel = MotionMixerPanel(self)

        self.left_view_stack.addWidget(self.track_list_panel) # Index 0
        self.left_view_stack.addWidget(self.motion_mixer_panel) # Index 1

        left_layout.addWidget(top_bar_widget)
        left_layout.addWidget(self.left_view_stack)
        # --- end of left panel ---

        # --- Right Panel ---
        right_panel = QtWidgets.QWidget()
        right_layout = QtWidgets.QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)

        top_spacer_widget = QtWidgets.QWidget()
        top_spacer_layout = QtWidgets.QHBoxLayout(top_spacer_widget)
        top_spacer_layout.setContentsMargins(5, 5, 5, 5)
        
        cut_btn = QtWidgets.QPushButton("Cut")
        cut_btn.clicked.connect(self.trim_selected_clip_to_current_frame)
        
        self.curve_toggle_btn = QtWidgets.QPushButton("Curve Editor")
        self.curve_toggle_btn.setCheckable(True)
        self.curve_toggle_btn.clicked.connect(self.toggle_curve_view)
        
        top_spacer_layout.addWidget(cut_btn)
        top_spacer_layout.addWidget(self.curve_toggle_btn)
        top_spacer_layout.addStretch()
        top_spacer_widget.setFixedHeight(top_bar_widget.sizeHint().height()) 

        self.ruler = TimelineRuler(self)
        self.marker_view = MarkerView(self)
        self.keyframe_area = KeyframeArea(self)
        self.curve_editor = CurveEditorWidget(self)
        
        self.editor_container = QtWidgets.QStackedWidget()
        self.editor_container.addWidget(self.keyframe_area)
        self.editor_container.addWidget(self.curve_editor)
        
        self.editor_scroll_area = QtWidgets.QScrollArea()
        self.editor_scroll_area.setWidget(self.editor_container)
        self.editor_scroll_area.setWidgetResizable(True)
        self.editor_scroll_area.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        

        self.value_ruler = ValueRuler(self.curve_editor)
        self.value_zoom_slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Vertical)
        self.value_zoom_slider.setRange(10, 200) 
        self.value_zoom_slider.setValue(100)
        self.value_zoom_slider.valueChanged.connect(self.curve_editor.set_vertical_zoom)
        # value_zoom_slider
        
        right_grid_layout = QtWidgets.QGridLayout()
        right_grid_layout.setContentsMargins(0,0,0,0); 
        right_grid_layout.setSpacing(0)
        right_grid_layout.addWidget(self.ruler, 0, 1)
        right_grid_layout.addWidget(self.marker_view, 1, 1)
        right_grid_layout.addWidget(self.value_ruler, 2, 0)
        right_grid_layout.addWidget(self.editor_scroll_area, 2, 1)
        right_grid_layout.addWidget(self.value_zoom_slider, 2, 2)
        right_grid_layout.setColumnStretch(1, 1)
        right_grid_layout.setRowStretch(2, 1)
        self.value_ruler.hide(); self.value_zoom_slider.hide()
        
        self.zoom_slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        
        
        right_layout.addWidget(top_spacer_widget)
        right_layout.addLayout(right_grid_layout)
        right_layout.addWidget(self.zoom_slider)

        splitter.addWidget(left_panel)
        splitter.addWidget(right_panel)
        splitter.setSizes([450, 800])
        
        h_handle_icon_path = os.path.join(SCRIPT_PATH, 'icons', 'left-and-right.png').replace('\\', '/')
        slider_style = f"""
            QSlider {{ height: 20px; }}
            QSlider::groove:horizontal {{ border: 1px solid #2d2d2d; height: 4px; background: #2d2d2d; margin: 2px 0; border-radius: 2px; }}
            QSlider::handle:horizontal {{ image: url({h_handle_icon_path}); width: 16px; height: 16px; margin: -6px 0; border: none; background-color: transparent; }}
        """
        self.zoom_slider.setStyleSheet(slider_style)
        self.zoom_slider.valueChanged.connect(self.on_zoom_slider_changed)
        
        v_handle_icon_path = os.path.join(SCRIPT_PATH, 'icons', 'Up-and-down.png').replace('\\', '/')
        vertical_slider_style = f"""
            QSlider {{ width: 20px; }}
            QSlider::groove:vertical {{ border: 1px solid #2d2d2d; width: 4px; background: #2d2d2d; margin: 0 2px; border-radius: 2px; }}
            QSlider::handle:vertical {{ image: url({v_handle_icon_path}); height: 16px; width: 16px; margin: 0 -6px; border: none; background-color: transparent; }}
        """
        self.value_zoom_slider.setStyleSheet(vertical_slider_style)

        
        header_style = """
            QHeaderView::section {
                background-color: #3c3c3c; padding: 4px;
                border-top: 1px solid #555555; border-bottom: 1px solid #555555;
                border-right: 1px solid #2d2d2d;
            }
        """
        
        # === A comprehensive UI map based on user screenshots and 3ds Max defaults ===
        self.controller_map_ui = {
            "Float_Control": {
                "Alembic Float": "AlembicFloat",
                "AudioFloat": "AudioFloat",
                "Bezier Float": "Bezier_Float",
                "Biped SubAnim": "Biped_SubAnim",
                "Boolean Controller": "boolean_float",
                "DrivenFloat":  "DrivenFloat",
                "Float Expression": "Float_Expression",
                "Float Limit": "Float_Limit",
                "Float List": "float_list",
                "Float Motion Capture": "Float_Motion_Capture",
                "Float Reaction": "Float_Reactor",
                "Float Script": "Float_Script",
                "Linear Float": "Linear_Float",
                "LinkTimeControl": "LinkTimeControl",
                "Noise Float": "Noise_Float",
                "On/Off": "On_Off",
                "Set Key": "Set_Key_Crtl",
                "TCB Float": "TCB_Float",
                "USD Float": "USDFloatController",
                "Waveform Float": "Waveform_Float",
                "tyRateOfChange": "tyRateOfChange"
            },
            "Position_Control": {
                "Attachment": "Attachment",
                "AudioPosition": "AudioPosition",
                "Bezier Position": "Bezier_Position",                
                "Driven Position": "DrivenPos",
                "Linear Position": "Linear_Position",
                "Motion clip Driven Position": "Motion_Clip_DrivenPos",
                "Noise Position": "Noise_Position",
                "OctAccXy Controller": "OctAccXyController",
                "Path Constraint": "Path_Constraint",
                "Position Constraint": "PositionConstraint",
                "Position Expression": "Position_Expression",
                "Position List": "Position_List",
                "Position Motion Capture": "Position_Motion_Capture",
                "Position Reaction": "Position_Reactor",
                "Position Script": "Position_Script",
                "Position XYZ": "Position_XYZ",
                "Ray To Surface Position": "MCG_rayToSurfacePosition",
                "Spring": "SpringPositionController",
                "Surface": "Surface_position",
                "TCB Position": "TCB_Position",
                "USD Position": "USDPositionController"
            },
            "Rotation_Control": {
                "AudioRotation": "AudioRotation",
                "Driven Rotation": "DrivenRotation",
                "Euler XYZ": "Euler_XYZ",
                "Linear Rotation": "Linear_Rotation",
                "LookAt Constraint": "LookAt_Constraint",
                "MCG LOOKAT": "MCG_lookAt",
                "Motion clip Driven Rotation": "Motion_Clip_DrivenRotation",
                "Noise Rotation": "Noise_Rotation",
                "Orientation Constraint": "rientation_Constraint",
                "Ray To Surface Rotation": "MCG_rayToSurfaceOrientation",
                "Rotation List": "Rotation_List",
                "Rotation Motion Capture": "Rotation_Motion_Capture",
                "Rotation Reaction": "Rotation_Reactor",                
                "Rotation Script": "Rotation_Script",
                "Smooth Rotation": "bezier_rotation",
                "TCB Rotation": "TCB_Rotation"
            },
            "Scale_Control": {
                "AudioScale": "AudioScale",
                "Bezier Scale": "Bezier_Scale",
                "Driven Scale": "DrivenScale",
                "Linear Scale": "Linear_Scale",
                "Motion clip Driven Scale": "Motion_Clip_DrivenScale",
                "Noise Scale": "Noise_Scale",
                "Scale Expression": "Scale_Expression",
                "Scale List": "Scale_List",
                "Scale Motion Capture": "Scale_Motion_Capture",
                "Scale Reaction": "Scale_Reactor",
                "Scale Script": "Scale_Script",
                "Scale XYZ": "ScaleXYZ",
                "TCB Scale": "TCB_Scale",
                "USD Scale": "USDScaleController"
            },
            "Transform_Control": {
                "AlembicXform": "AlembicXform",
                "CATGizmoTransform": "CATGizmoTransform",
                "CATDPIvotTrans": "CATDPIvotTrans",
                "CATHPIvotTrans": "CATHPIvotTrans",
                "CATTransformOffset": "CATTransformOffset",
                "Link Constraint": "Link_Constraint",
                "Position/Rotation/Scale": "prs", 
                "Ray To Surface Transform": "MCG_rayToSurfaceTransform",
                "Rotational Spring 1 DOF Transform": "MCG_rotationalSpring1DOFTransform",
                "Rotational Spring 3 DOF Transform": "MCG_rotationalSpring3DOFTransform",
                "Transform List": "Transform_List",
                "Transform Script": "Transform_Script",
                "USD Xformable": "USDXformableController",
                "XRef Controller": "XRef_Controller",
                "tyParticle Controller": "tyParticleController",
                "tyRetime Controller": "tyRetimeController"
            }
        }

        self.track_list_panel.track_tree.verticalScrollBar().valueChanged.connect(self.sync_scroll_from_track_list)
        #self.editor_scroll_area.verticalScrollBar().valueChanged.connect(self.sync_scroll_from_keyframe_area)
        self.track_list_panel.track_tree.itemExpanded.connect(lambda: QtCore.QTimer.singleShot(0, self.sync_scrollbars))
        self.track_list_panel.track_tree.itemCollapsed.connect(lambda: QtCore.QTimer.singleShot(0, self.sync_scrollbars))

        
        self.motion_mixer_panel.track_tree.model().rowsMoved.connect(self.keyframe_area.update)
        self.motion_mixer_panel.track_tree.itemExpanded.connect(lambda: QtCore.QTimer.singleShot(0, self.sync_scrollbars))
        self.motion_mixer_panel.track_tree.itemCollapsed.connect(lambda: QtCore.QTimer.singleShot(0, self.sync_scrollbars))

        self.sync_timer = QtCore.QTimer(self)
        self.sync_timer.timeout.connect(self.periodic_sync_with_max)
        self.sync_timer.start(50)
        
        QtCore.QTimer.singleShot(0, self.sync_scrollbars)
        QtCore.QTimer.singleShot(0, self.logic._load_timeline_state)
        
        self.save_callback_id = "myTimelineProSaveCallback"
        self.track_list_panel.track_tree.itemSelectionChanged.connect(self.sync_selection_to_max)
        print("✅✅✅ DEBUG: CONNECTION TEST PASSED! The signal is now connected. ✅✅✅")
        
        print("DEBUG: MyTimelineWidget initialization complete.")

    
    #=============================
    # Connections and Callbacks TIMELINE UI
    #=============================
    def add_selected_objects(self):
        """This function sends an "add object" request to the logical class."""
        self.logic.add_selected_objects()

    def remove_selected_layers(self):
        """This function sends a "delete layer" request to the logical class."""
        self.logic.remove_selected_layers()

    def clear_all_layers(self):
        """This function sends a "clear all" request to the logical class."""
        self.logic.clear_all_layers()

    def bake_selected_layers(self):
        """This function sends a "Bake" request to the logical class."""
        self.logic.bake_selected_layers()

    def _save_timeline_state(self):
        """This function sends a "save state" request to the logic class."""
        self.logic._save_timeline_state()
        
    def _export_clip_to_file(self, item):
        """
        This function sends the "Export Clip" request to the logic class.
        Note: It now correctly receives and sends the 'item' input.
        """
        self.logic._export_clip_to_file(item)

    
    
    def open_track_context_menu(self, position):
        """
        This function sends the "Open right-click menu" request to the logic class.
        (Note: The function name is different in logic and that's perfectly fine)
        """
        self.logic.handle_context_menu_request(position)


    #=============================
    # End of Connections and Callbacks TIMELINE UI
    #=============================
    
    def closeEvent(self, event):
        """🗑️ This function clears callbacks when the widget is closed."""
        print("\n--- Closing Timeline: Unregistering callbacks ---")
        try:
            rt.callbacks.removeScripts(id=rt.name(self.save_callback_id))
            print("✅ Save callback successfully removed.")
            
            if hasattr(self, 'selection_callback_id'):
                rt.callbacks.removeScripts(id=rt.name(self.selection_callback_id))
                print("✅ Selection callback successfully removed.")
        except Exception as e:
            print(f"❌ ERROR: Could not remove a callback: {e}")
        super().closeEvent(event)

    def _get_active_tree_widget(self):
        """
        Checks which panel on the left is active and returns the corresponding TreeWidget.
        """
        if self.left_view_stack.currentIndex() == 1:
            #Motion Mixer
            return self.motion_mixer_panel.track_tree
        else:
            #Track List
            return self.track_list_panel.track_tree
        
    def _full_ui_refresh(self):
        """
        This function refreshes all parts of the UI in a complete and synchronized manner.
        """
        print("DEBUG: Executing full UI refresh...")        
        self.update_track_values()        
        self.sync_scrollbars()        
        self.keyframe_area.update()
        self.curve_editor.update()
        
    def _refresh_ui_after_switch(self):
        """Fully refreshes the entire UI after changing views."""
        print("DEBUG: Forcing UI refresh after view switch.")
        self._force_ui_refresh()
        self.sync_scrollbars()
        self.keyframe_area.update()

    
    
    def _toggle_left_view(self):
        """Switches between Track List view and Motion Mixer in the left panel."""
        if self.mixer_toggle_btn.isChecked():
            self.left_view_stack.setCurrentIndex(1) #Motion Mixer
            self.mixer_toggle_btn.setText("Track List")
            print("DEBUG: Switched to Motion Mixer view.")
        else:
            self.left_view_stack.setCurrentIndex(0) #Track List
            self.mixer_toggle_btn.setText("Motion Mixer")
            print("DEBUG: Switched to Track List view.")
        
       
        QtCore.QTimer.singleShot(0, self._full_ui_refresh)

    # === ZOOM SLIDER  ===
    def on_zoom_slider_changed(self, value):
        """Called when the user drags the zoom slider."""
        if self.sync_timer.isActive():
            self.sync_timer.stop()

        # === THE FIX IS HERE ===
        # Instead of zooming around the current time, we now anchor to the start of the range.
        start_frame = int(rt.animationRange.start)
        new_end = start_frame + value
        
        rt.animationRange = rt.interval(start_frame, new_end)
        
        QtCore.QTimer.singleShot(60, self.sync_timer.start)

    def wheelEvent(self, event):
        """Handles mouse wheel scrolling for zooming."""
        # ✅ FIX: Only zoom the horizontal timeline if the Ctrl key is held down
        if event.modifiers() == QtCore.Qt.KeyboardModifier.ControlModifier:
            zoom_slider = self.zoom_slider
            current_value = zoom_slider.value()
            # A more intuitive zoom sensitivity
            zoom_sensitivity = max(10, int(current_value * 0.1)) 
            
            if event.angleDelta().y() > 0:
                zoom_slider.setValue(current_value - zoom_sensitivity)
            else:
                zoom_slider.setValue(current_value + zoom_sensitivity)
            event.accept() # We've handled the event
        else:
            event.ignore()

    # === END: ZOOM SLIDER ===

    
    def resizeEvent(self, event):
        super().resizeEvent(event)
        # Use a timer to ensure the layout has settled before syncing
        QtCore.QTimer.singleShot(0, self.sync_scrollbars)

    def sync_scroll_from_track_list(self, value):
        print(f"DEBUG [Scroll]: Left scroll sent value -> {value}")
        right_scrollbar = self.editor_scroll_area.verticalScrollBar()
        right_scrollbar.blockSignals(True)
        right_scrollbar.setValue(value)
        right_scrollbar.blockSignals(False)
        self.keyframe_area.update()

    def sync_scroll_from_keyframe_area(self, value):
        sb = self.track_list_panel.track_tree.verticalScrollBar()
        sb.blockSignals(True)
        sb.setValue(value)
        sb.blockSignals(False)

    def sync_selection_to_max(self):
        """
        Final version: Selects the object and then returns focus to 3ds Max
        so that the selection highlight is displayed correctly.
        """
        print("\n--- SYNC: Timeline -> Max Scene ---")
        if self.is_syncing_selection:
            print("  -> SKIPPED: Already syncing.")
            return

        self.is_syncing_selection = True
        print("  -> LOCK acquired.")

        selected_nodes = []
        selected_items = self.track_list_panel.track_tree.selectedItems()

        for item in selected_items:
            if item.parent() is None:
                handle = item.data(0, QtCore.Qt.ItemDataRole.UserRole)
                if handle:
                    try:
                        node = rt.maxOps.getNodeByHandle(handle)
                        if node:
                            selected_nodes.append(node)
                    except Exception:
                        pass
        
        
        rt.selection = selected_nodes
        
        rt.redrawViews()
        
      
        try:
            user32 = ctypes.windll.user32
            max_hwnd = rt.windows.getMAXHWND()
            user32.SetForegroundWindow(max_hwnd)
            print("  -> Focus successfully returned to 3ds Max.")
        except Exception as e:
            print(f"  -> WARNING: Could not set focus back to 3ds Max. Error: {e}")
        
        
        self.is_syncing_selection = False
        print("  -> LOCK released.")

    # === Search In Timeline ===
    def on_search_text_changed(self, search_text):
        """Called every time the text in the search bar changes."""
        search_text_lower = search_text.lower()
        
        # Iterate over all top-level items and apply the filter recursively
        for i in range(self.track_list_panel.track_tree.topLevelItemCount()):
            item = self.track_list_panel.track_tree.topLevelItem(i)
            self._filter_recursive(item, search_text_lower)

    def apply_visibility_filter(self):
        """
        Applies the visibility filter, correctly respecting the entire layer hierarchy.
        """
        show_hidden_is_active = self.filter_hidden_btn.isChecked()
        
        # Iterate through every single item in the tree
        iterator = QtWidgets.QTreeWidgetItemIterator(self.track_list_panel.track_tree, QtWidgets.QTreeWidgetItemIterator.IteratorFlag.All)
        while iterator.value():
            item = iterator.value()
            
            # --- NEW HIERARCHICAL LOGIC ---
            
            
            is_visible_in_hierarchy = True
            temp_item = item
            while temp_item is not None:
                # Check the logical state from the icon
                is_logically_visible = (temp_item.icon(0).cacheKey() == self.eye_open_icon.cacheKey())
                if not is_logically_visible:
                    is_visible_in_hierarchy = False
                    break # If any parent is hidden, the child must be hidden
                temp_item = temp_item.parent()

            
            should_be_displayed = True # Assume visible
            if not is_visible_in_hierarchy and not show_hidden_is_active:
                # Hide it ONLY if it's supposed to be hidden AND the filter is off
                should_be_displayed = False
                
            item.setHidden(not should_be_displayed)
            iterator += 1
            
        # --- END OF NEW LOGIC ---

        self.keyframe_area.update()
        self.track_list_panel.track_tree.viewport().update()
        self.curve_editor.update_value_range()

    def _add_marker(self, frame): 
        """Adds a new marker at the specified frame."""
        marker_uid = str(uuid.uuid4())
        
        new_marker = {
            "uid": marker_uid,
            "clip_uid": None, 
            "frame": frame,
            "note": "",
            "color": "#d4a056"
        }
        self.markers[marker_uid] = new_marker
        print(f"DEBUG: Added new marker {marker_uid} at frame {frame}.")
        self.marker_view.update() 
        self._save_timeline_state()

    def _edit_marker(self, marker_uid):
        """Opens a dialog to edit an existing marker."""
        marker_data = self.markers.get(marker_uid)
        if not marker_data: return

        dialog = MarkerDialog(note=marker_data['note'], color=QtGui.QColor(marker_data['color']), parent=self)
        if dialog.exec():
            new_note, new_color = dialog.get_data()
            self.markers[marker_uid]['note'] = new_note
            self.markers[marker_uid]['color'] = new_color.name()
            print(f"DEBUG: Edited marker {marker_uid}.")
            self.ruler.update()
            self._save_timeline_state()

    def _delete_marker(self, marker_uid):
        """Deletes a marker."""
        if marker_uid in self.markers:
            del self.markers[marker_uid]
            print(f"DEBUG: Deleted marker {marker_uid}.")
            self.ruler.update()
            self._save_timeline_state()

            
    def _filter_recursive(self, item, search_text):
        """
        A helper function to recursively show or hide items based on the search text.
        Returns True if the item or any of its children match, otherwise False.
        """
        # Check if this item's name matches the search text
        item_name_lower = item.text(1).lower()
        item_matches = search_text in item_name_lower

        # Now, check if any of this item's children match
        child_matches = False
        for i in range(item.childCount()):
            child_item = item.child(i)
            # The 'or' ensures that if a child matches, the flag stays True
            if self._filter_recursive(child_item, search_text):
                child_matches = True
                
        # The item should be visible if either the item itself matches, or one of its children matches
        if item_matches or child_matches:
            item.setHidden(False)
            return True
        else:
            # If neither this item nor any of its children match, hide it
            item.setHidden(True)
            return False
    
    def sync_scrollbars(self):
        """
        This function sets the height of the right widget to the left
        and matches the scrollbar properties.
        """
        track_tree = self.track_list_panel.track_tree
        keyframe_widget = self.keyframe_area
        key_scroll_area = self.editor_scroll_area

        
        header_height = track_tree.header().height()
        content_height = header_height
        
        iterator = QtWidgets.QTreeWidgetItemIterator(track_tree)
        max_y = 0
        while iterator.value():
            item = iterator.value()
            if not item.isHidden():
                item_bottom = track_tree.visualItemRect(item).bottom()
                if item_bottom > max_y:
                    max_y = item_bottom
            iterator += 1

        if max_y > 0:
            content_height = max_y

        
        keyframe_widget.setMinimumHeight(content_height)

        
        track_sb = track_tree.verticalScrollBar()
        key_sb = key_scroll_area.verticalScrollBar()
        
        key_sb.blockSignals(True)
        key_sb.setRange(track_sb.minimum(), track_sb.maximum())
        key_sb.setPageStep(track_sb.pageStep())
        key_sb.setValue(track_sb.value()) 
        key_sb.blockSignals(False)
        
        keyframe_widget.update()

    
    def create_color_icon(self, color):
        pixmap = QtGui.QPixmap(6, 16)
        pixmap.fill(color)
        return QtGui.QIcon(pixmap)
    

    def refresh_item(self, item_to_refresh):
        if not item_to_refresh: return
        owner_object = None
        if item_to_refresh.parent() is None:
            handle = item_to_refresh.data(0, self.PARENT_OBJ_ROLE) 
            if handle:
                try: owner_object = rt.maxOps.getNodeByHandle(handle)
                except Exception: pass
        else:
            owner_object = item_to_refresh.data(0, self.SUBANIM_ROLE)
        
        if not owner_object: 
            print("Refresh Error: Could not find owner object.")
            return

        
        
        children_state = {}
        for i in range(item_to_refresh.childCount()):
            child = item_to_refresh.child(i)
            track_name = child.text(1)             
            
            is_visible = (child.icon(0).cacheKey() == self.eye_open_icon.cacheKey())
            is_expanded = child.isExpanded()            
            children_state[track_name] = {'visible': is_visible, 'expanded': is_expanded}       

        
        item_to_refresh.takeChildren() 
        self.add_tracks_recursively(item_to_refresh, owner_object) 
        
        
        for i in range(item_to_refresh.childCount()):
            child = item_to_refresh.child(i)
            track_name = child.text(1)
            
            if track_name in children_state:
                state = children_state[track_name]              
                
                child.setExpanded(state['expanded'])               
                
                if not state['visible']:
                    child.setIcon(0, self.eye_closed_icon)
                
        
        self.update_track_values()
      
        self.apply_visibility_filter() 
        
        self.keyframe_area.update()
        QtCore.QTimer.singleShot(0, self.sync_scrollbars)
    
    def on_item_double_clicked(self, item, column):
        """
        Final version with modified logic (no else):
        Handles double-click behavior as two independent and readable conditions.
        """
        
        if item.parent() is None:
            if column == 1:
                self.track_list_panel.track_tree.editItem(item, column)
            return

        
        if column == 1 or column == 2:
            
            self._show_controller_in_motion_panel(item)
            return

    def _show_controller_in_motion_panel(self, item):
        """
        Opens the motion panel for the selected item (track) and highlights it.
        This function is correctly placed in the MyTimelineWidget class.
        """
        sub_anim = item.data(0, self.SUBANIM_ROLE)
        if not sub_anim: return
        top_level_item = item
        while top_level_item.parent() is not None:
            top_level_item = top_level_item.parent()
        
        node_handle = top_level_item.data(0, self.PARENT_OBJ_ROLE)
        if not node_handle: return

        try:
            node_to_select = rt.maxOps.getNodeByHandle(node_handle)
            if not node_to_select: return
            rt.select(node_to_select)
            rt.setCommandPanelTaskMode(rt.name('motion'))            
            if rt.trackviews.current is not None:
                rt.trackviews.current.selectSubAnim(sub_anim)

        except Exception as e:
            print(f"An error occurred while switching to Motion Panel: {e}")

    
    def _add_node_hierarchy_recursively(self, parent_max_node, parent_tree_item):
        """
        A recursive function that finds all the children of an object in the scene
        and adds them to the timeline in a nested manner.
        """
        color_settings = self.settings['Type_Colors']

        for child_node in parent_max_node.children:
            child_tree_item = QtWidgets.QTreeWidgetItem(['', child_node.name, 'N/A', ''])
            child_tree_item.setIcon(0, self.eye_open_icon)            
            child_tree_item.setData(0, self.SUBANIM_ROLE, child_node)
            
            color_hex = None
            if rt.isKindOf(child_node, rt.Light): color_hex = color_settings.get('light_color')
            elif rt.isKindOf(child_node, rt.Camera): color_hex = color_settings.get('camera_color')
            elif rt.isKindOf(child_node, rt.Shape): color_hex = color_settings.get('shape_color')
            elif rt.isKindOf(child_node, rt.Helper): color_hex = color_settings.get('helper_color')
            elif rt.isKindOf(child_node, rt.GeometryClass): color_hex = color_settings.get('geometry_color')
            elif rt.isKindOf(child_node, rt.SpacewarpObject): color_hex = color_settings.get('SpacewarpObject_color')

            
            if color_hex:
                brush = QtGui.QBrush(QtGui.QColor(color_hex))
                child_tree_item.setBackground(1, brush)

            
            parent_tree_item.addChild(child_tree_item)
            self.add_tracks_recursively(child_tree_item, child_node)

            self._add_node_hierarchy_recursively(child_node, child_tree_item)

    

    
    # =================================================================
    # === MOTION MIXER BAKE (FINAL & CLEANED VERSION)               ===
    # =================================================================

    def _get_mixer_value_at_time(self, time, keys):
        """
        A helper function that calculates an animated value at a specific time
        using linear interpolation. It's designed to be simple and robust.
        """
        if not keys:
            return None
        
        # Find the two keys surrounding the current time
        sorted_keys = sorted(keys, key=lambda x: x['time'])
        key1 = next((k for k in reversed(sorted_keys) if k['time'] <= time), None)
        key2 = next((k for k in sorted_keys if k['time'] >= time), None)
        
        # Handle edge cases where time is before the first key or after the last key
        if key1 is None:
            return float(key2.get('value', 0.0))
        if key2 is None:
            return float(key1.get('value', 0.0))
        if key1 == key2:
            return float(key1.get('value', 0.0))

        # Perform linear interpolation
        time_diff = key2['time'] - key1['time']
        if time_diff == 0:
            return float(key1.get('value', 0.0))
        
        alpha = (time - key1['time']) / time_diff
        val1 = float(key1.get('value', 0.0))
        val2 = float(key2.get('value', 0.0))
        
        return val1 + (val2 - val1) * alpha

    
    
    
    def _convert_json_to_mxs(self, py_value, class_name):
        """
        Converts a Python value (from JSON) to a value understandable to MAXScript.
        """
        try:
            if isinstance(py_value, (int, float)):
                return float(py_value)
            if not isinstance(py_value, list):
                return py_value 

            if "Position" in class_name or "Point3" in class_name or "Scale" in class_name or "Color" in class_name:
                if len(py_value) == 3:
                    return rt.Point3(py_value[0], py_value[1], py_value[2])
            elif "Rotation" in class_name or "Quat" in class_name:
                if len(py_value) == 4:
                    return rt.Quat(py_value[0], py_value[1], py_value[2], py_value[3])
            
            if len(py_value) == 1:
                return float(py_value[0])
                
        except Exception as e:
            print(f"  -> ERROR [Convert]: Failed to convert value {py_value}. {e}")
        
        return py_value
        
    
    def trim_selected_clip_to_current_frame(self):
        """
        Trims all selected clips, or the clip under the playhead if none are selected.
        """
        current_t = int(rt.currentTime)
        items_to_trim = []

        # --- NEW LOGIC: Collect ALL selected clips first ---
        selected_items = self.track_list_panel.track_tree.selectedItems()
        if selected_items:
            for item in selected_items:
                if item.parent() is None:
                    items_to_trim.append(item)
        
        # --- FALLBACK: If no clips were selected, find the one under the playhead ---
        if not items_to_trim:
            for i in range(self.track_list_panel.track_tree.topLevelItemCount()):
                item = self.track_list_panel.track_tree.topLevelItem(i)
                start_frame = item.data(0, self.CLIP_START_ROLE)
                end_frame = item.data(0, self.CLIP_END_ROLE)

                if start_frame is not None and start_frame < current_t < end_frame:
                    items_to_trim.append(item)
                    break # In this mode, only cut the first one found

        # --- Now, perform the trim on all items we found ---
        if items_to_trim:
            for item_to_trim in items_to_trim:
                clip_start_frame = item_to_trim.data(0, self.CLIP_START_ROLE)
                if current_t > clip_start_frame:
                    item_to_trim.setData(0, self.CLIP_END_ROLE, current_t)
                    print(f"Clip '{item_to_trim.text(0)}' trimmed to frame {current_t}.")
                else:
                    print(f"Cut for clip '{item_to_trim.text(0)}' ignored: Cut position is before the start time.")
            self.keyframe_area.update()
            self._save_timeline_state()
        else:
            print("No selected clip or active clip found under the time slider to cut.")


    def get_keys_from_item(self, item):
        """Helper to get key objects from a single track item."""
        keys = []
        sub_anim = item.data(0, self.SUBANIM_ROLE)
        try:
            if sub_anim and sub_anim.controller and rt.isProperty(sub_anim.controller, "keys"):
                if sub_anim.controller.keys.count > 0:
                    keys.extend(sub_anim.controller.keys)
        except Exception: pass
        return keys

    def _force_ui_refresh(self, **kwargs):
        """This function forces a full UI refresh."""
        if self.isVisible():
            self.update_track_values()
            self.keyframe_area.update()

    def on_item_changed(self, item, column):
        # Ignore signals fired by the script itself
        if self.is_renaming_from_ui or self.is_updating_values:
            return
        
        
        # Handle renaming, which is in column 1 (this part is unchanged)
        if item.parent() is None and column == 1:
            handle = item.data(0, QtCore.Qt.ItemDataRole.UserRole)
            new_name = item.text(1)
            try:
                node = rt.maxOps.getNodeByHandle(handle)
                if node and node.name != new_name:
                    node.name = new_name
            except Exception as e:
                print(f"Could not rename node: {e}")

        # Handle value editing, which is in column 3 (this part is unchanged)
        if column == 3:
            sub_anim = item.data(0, self.SUBANIM_ROLE)
            new_val_str = item.text(3)
            if not sub_anim: return
            try:
                with pymxs.animate(True):
                    new_val = rt.execute(new_val_str)
                    sub_anim.value = new_val
                if not sub_anim.controller:
                    self.refresh_item(item.parent())
                else:
                    self.keyframe_area.update()
            except Exception as e:
                print(f"Could not set new value '{new_val_str}'. Error: {e}")
                self.update_track_values()
    
    def show_all_layers(self):
        """Makes all items visible again by checking their boxes and un-hiding them."""
        self.track_list_panel.track_tree.blockSignals(True)
        iterator = QtWidgets.QTreeWidgetItemIterator(self.track_list_panel.track_tree, QtWidgets.QTreeWidgetItemIterator.IteratorFlag.All)
        while iterator.value():
            item = iterator.value()
            item.setHidden(False)
            
            if item.parent() is None: 
                item.setIcon(0, self.eye_open_icon)

            iterator += 1
        self.track_list_panel.track_tree.blockSignals(False)
        self.keyframe_area.update()
        self._save_timeline_state()

    def on_visibility_icon_clicked(self, item, column):
        """Handles clicks on the eye icon, updating the logical state."""
        if column == 0:
            
            is_logically_visible = (item.icon(0).cacheKey() == self.eye_open_icon.cacheKey())           
            new_logical_visibility = not is_logically_visible         
            new_icon = self.eye_open_icon if new_logical_visibility else self.eye_closed_icon
            item.setIcon(0, new_icon)
            self.apply_visibility_filter()
            self.keyframe_area.update()
            self._save_timeline_state()
                        
    def add_tracks_recursively(self, parent_widget_item, parent_max_object):
        if not parent_max_object or parent_max_object.numSubs == 0: return
        try:
            sub_anim_names = rt.getSubAnimNames(parent_max_object)
            if sub_anim_names:
                for name in sub_anim_names:
                    sub_anim = rt.getSubAnim(parent_max_object, name)
                    if not sub_anim: continue
                    
                    controller_info = "N/A"
                    if hasattr(sub_anim, 'controller') and sub_anim.controller:
                        controller_info = str(rt.classOf(sub_anim.controller))
                    
                    pretty_name = str(name).replace('__', ' ').replace('_', ' ').title()
                    tree_item = QtWidgets.QTreeWidgetItem(['', pretty_name, controller_info, ""])
                    
                    
                    is_value_editable = False
                    if hasattr(sub_anim, 'controller') and sub_anim.controller:
                        if rt.isProperty(sub_anim.controller, 'value'): is_value_editable = True
                    elif rt.isProperty(sub_anim, 'value'):
                        is_value_editable = True
                    
                    
                    if is_value_editable:
                        tree_item.setFlags(tree_item.flags() | QtCore.Qt.ItemFlag.ItemIsEditable)
                    

                    tree_item.setIcon(0, self.eye_open_icon)
                    if pretty_name in self.DEFAULT_HIDDEN_TRACKS:
                        tree_item.setHidden(True)
                        tree_item.setIcon(0, self.eye_closed_icon)

                    if pretty_name.startswith("X ") or pretty_name == "X":
                        tree_item.setIcon(1, self.red_icon)
                    elif pretty_name.startswith("Y ") or pretty_name == "Y":
                        tree_item.setIcon(1, self.green_icon)
                    elif pretty_name.startswith("Z ") or pretty_name == "Z":
                        tree_item.setIcon(1, self.blue_icon)
                    
                    tree_item.setData(0, self.SUBANIM_ROLE, sub_anim)
                    tree_item.setData(0, self.PARENT_OBJ_ROLE, parent_max_object)
                    tree_item.setData(0, self.SUBANIM_NAME_ROLE, name)
                    if pretty_name == "Transform":
                        tree_item.setExpanded(True)                    
                    parent_widget_item.addChild(tree_item)
                    self.add_tracks_recursively(tree_item, sub_anim)

        except Exception as e:
            print(f"Error processing sub-anims for {parent_max_object}: {e}")
            error_item = QtWidgets.QTreeWidgetItem(["", f"Error reading tracks", str(e), ""])
            parent_widget_item.addChild(error_item)


    
    def periodic_sync_with_max(self):
        
        ui_needs_update = False

        
        max_time = int(rt.currentTime)
        if self.current_frame != max_time:
            self.current_frame = max_time
            self.ruler.update()
            self.curve_editor.update()
            self.value_ruler.update() 
            self.update_track_values()
            ui_needs_update = True 

        
        max_start = int(rt.animationRange.start)
        max_end = int(rt.animationRange.end)
        if self.last_start_frame != max_start or self.last_end_frame != max_end:
            self.last_start_frame = max_start
            self.last_end_frame = max_end
            self.ruler.update_range()
            new_duration = max_end - max_start
            if new_duration < 10: new_duration = 10
            self.zoom_slider.blockSignals(True)
            self.zoom_slider.setValue(new_duration)
            self.zoom_slider.blockSignals(False)
            ui_needs_update = True 

        
        items_to_remove = []
        for i in range(self.track_list_panel.track_tree.topLevelItemCount()):
            item = self.track_list_panel.track_tree.topLevelItem(i)
            handle = item.data(0, self.PARENT_OBJ_ROLE)
            if not handle: continue
            try:
                node = rt.maxOps.getNodeByHandle(handle)
                if not node: items_to_remove.append(item)
            except RuntimeError:
                items_to_remove.append(item)
            except Exception as e:
                print(f"Sync error: {e}")

        if items_to_remove:
            root = self.track_list_panel.track_tree.invisibleRootItem()
            for item in items_to_remove:
                root.removeChild(item)
            self._save_timeline_state()
            QtCore.QTimer.singleShot(0, self.sync_scrollbars)
            ui_needs_update = True 
            
        
        if ui_needs_update:
            self.keyframe_area.update()

    def update_track_values(self):
        self.is_updating_values = True
        try:
            iterator = QtWidgets.QTreeWidgetItemIterator(self.track_list_panel.track_tree)
            while iterator.value():
                self.update_single_item_value(iterator.value())
                iterator += 1
        finally: self.is_updating_values = False


    def update_single_item_value(self, item):
        sub_anim = item.data(0, self.SUBANIM_ROLE)
        if not sub_anim: return
        
        val_str = ""
        controller_str = "N/A"
        val = None
        controller = None
        
        if hasattr(sub_anim, 'controller') and sub_anim.controller:
            controller_str = str(rt.classOf(sub_anim.controller))
            if rt.isProperty(sub_anim.controller, 'value'):
                try: val = sub_anim.controller.value
                except Exception: pass
        elif rt.isProperty(sub_anim, 'value'):
            try: val = sub_anim.value
            except Exception: pass

        if val is not None:
            if isinstance(val, float): val_str = f"{val:.3f}"
            elif isinstance(val, bool): val_str = str(val)
            else: val_str = str(val)

        
        has_key_at_current_time = False
        # First, ensure we have a valid controller that actually supports keys
        if controller and rt.isProperty(controller, "keys") and controller.keys.count > 0:
            current_f = int(self.current_frame)
            try:
                # Loop through the keys to find an exact match for the current frame
                for i in range(controller.keys.count):
                    if int(controller.keys[i].time) == current_f:
                        has_key_at_current_time = True
                        break # Exit the loop as soon as we find one
            except Exception:
                has_key_at_current_time = False # Safety net if accessing keys fails

        color = QtGui.QColor("#ff4747") if has_key_at_current_time else QtGui.QColor("#56a0d4")
        item.setForeground(3, QtGui.QBrush(color))
        
           
        # === THE FIX IS HERE ===
        # Column 2 is 'Controller Type', Column 3 is 'Value'
        if item.text(2) != controller_str: item.setText(2, controller_str)
        if item.text(3) != val_str: item.setText(3, val_str)


    def _create_clip_item(self, node, layer_name, start, end, anim_data, clip_uid=None):
        """The helper function now also receives and stores a UID."""
        obj_item = QtWidgets.QTreeWidgetItem(['', layer_name, 'N/A', ''])
        font = obj_item.font(1); font.setBold(True); obj_item.setFont(1, font)
        

        
        obj_item.setData(0, self.PARENT_OBJ_ROLE, node.handle)
        obj_item.setFlags(obj_item.flags() | QtCore.Qt.ItemFlag.ItemIsEditable)
        obj_item.setData(0, self.CLIP_START_ROLE, start)
        obj_item.setData(0, self.CLIP_END_ROLE, end)
        obj_item.setData(0, self.CLIP_DATA_ROLE, anim_data)
        obj_item.setIcon(0, self.eye_open_icon)
        
        if clip_uid is None:
            clip_uid = str(uuid.uuid4()) 
        obj_item.setData(0, self.CLIP_UID_ROLE, clip_uid)

        
        color_settings = self.settings['Type_Colors']
        color_hex = None
        if rt.isKindOf(node, rt.Light): color_hex = color_settings.get('light_color')
        elif rt.isKindOf(node, rt.Camera): color_hex = color_settings.get('camera_color')
        elif rt.isKindOf(node, rt.Shape): color_hex = color_settings.get('shape_color')
        elif rt.isKindOf(node, rt.Helper): color_hex = color_settings.get('helper_color')
        elif rt.isKindOf(node, rt.GeometryClass): color_hex = color_settings.get('geometry_color')
        elif rt.isKindOf(node, rt.SpacewarpObject): color_hex = color_settings.get('SpacewarpObject_color')

        if color_hex:
            brush = QtGui.QBrush(QtGui.QColor(color_hex))
            
            obj_item.setBackground(1, brush)
            
        return obj_item

    
    def on_item_clicked(self, item, column):
        """Handles clicks on the visibility icon."""
        if column == 0:
            # Toggle the visibility state
            is_currently_visible = item.data(0, self.VISIBILITY_ROLE)
            new_visibility = not is_currently_visible
            
            item.setData(0, self.VISIBILITY_ROLE, new_visibility)
            
            # Update icon
            icon = self.eye_open_icon if new_visibility else self.eye_closed_icon
            item.setIcon(0, icon)
            
            # Hide/show children in the tree view
            item.setExpanded(new_visibility)
            for i in range(item.childCount()):
                item.child(i).setHidden(not new_visibility)
                
            self.keyframe_area.update() # Redraw keyframes
            self._save_timeline_state() # Save the new state

    def unhide_all_layers(self):
        """Makes ALL items (parents and children) visible again and sets their icons to open."""
        self.track_list_panel.track_tree.blockSignals(True)
        iterator = QtWidgets.QTreeWidgetItemIterator(self.track_list_panel.track_tree, QtWidgets.QTreeWidgetItemIterator.IteratorFlag.All)
        while iterator.value():
            item = iterator.value()
            
            
            item.setHidden(False)
            item.setIcon(0, self.eye_open_icon)

            iterator += 1
            
        self.track_list_panel.track_tree.blockSignals(False)
        self.keyframe_area.update()
        self._save_timeline_state()
            
       
    
    def open_settings_dialog(self):
        dialog = SettingsDialog(self.settings, self);
        if dialog.exec(): self.ruler.update()
    def close_parent_toolbar(self):
        if self.parent_toolbar: self.parent_toolbar.close()
    
         
        
    def toggle_curve_view(self): 
        if self.curve_toggle_btn.isChecked(): 
            # Switch to Curve Editor
            self.editor_container.setCurrentWidget(self.curve_editor)
            self.value_ruler.show()
            self.value_zoom_slider.show()
            self.curve_toggle_btn.setText("Keyframe View")
            self.curve_editor.update_value_range()
        else:
            # Switch back to Keyframe View
            self.editor_container.setCurrentWidget(self.keyframe_area)
            self.value_ruler.hide()
            self.value_zoom_slider.hide() 
            self.curve_toggle_btn.setText("Curve Editor")
        
        # Ensure the scrollbars are synced after switching
        QtCore.QTimer.singleShot(0, self.sync_scrollbars)


    #CACHE FUNCTION
    def _on_cache_toggled(self, is_checked):
        """
        This function is executed when the user clicks the cache button.
        If the button is lit, a progress popup will appear and the cache creation process will begin.
        """
        if is_checked:
            print("--- CACHE ACTIVATED ---")
            
            
            items_to_cache = []
            for i in range(self.track_list_panel.track_tree.topLevelItemCount()):
                item = self.track_list_panel.track_tree.topLevelItem(i)
                
                if item.data(0, QtCore.Qt.ItemDataRole.UserRole) is not None:
                    items_to_cache.append(item)
            
            if not items_to_cache:
                print("-> No clips to cache. Toggling button off.")
                self.track_list_panel.cache_mode_btn.setChecked(False) 
                return

            
            progress_dialog = QtWidgets.QProgressDialog(
                "Building performance cache...", 
                "Cancel", 
                0, 
                len(items_to_cache), 
                self 
            )
            progress_dialog.setWindowTitle("Caching Animation Data")
            progress_dialog.setWindowModality(QtCore.Qt.WindowModality.WindowModal) 
            progress_dialog.show()

            
            for i, item in enumerate(items_to_cache):
                
                if progress_dialog.wasCanceled():
                    print("-> Cache building CANCELED by user.")
                    self.track_list_panel.cache_mode_btn.setChecked(False) 
                    break

                
                progress_dialog.setLabelText(f"Processing: {item.text(1)}...")
                progress_dialog.setValue(i + 1)
                
                
                # self._build_cache_for_item(item) 
                
                
                QtWidgets.QApplication.processEvents()

            print("--- CACHE BUILD COMPLETE ---")
            self.track_list_panel.cache_mode_btn.setText("Cache Active (Refresh)")

        else:
            
            print("--- CACHE DEACTIVATED (Live Mode) ---")
            self.track_list_panel.cache_mode_btn.setText("Activate Cache Mode")
        
        
        self.keyframe_area.update()

    def _build_cache_for_item(self, item):
        """
        Reads the complete animation data for a specific clip item and stores it
        as a "cache" on the item itself.
        """
        handle = item.data(0, QtCore.Qt.ItemDataRole.UserRole)
        if not handle:
            print(f"  -> SKIPPED: No handle found for '{item.text(1)}'.")
            return

        try:
            node = rt.maxOps.getNodeByHandle(handle)
            
            
            animation_map, _, _ = self._capture_full_animation_map(node)
            
            
            item.setData(0, self.CLIP_DATA_ROLE, animation_map)
            
            print(f"  -> Successfully cached data for '{item.text(1)}'.")

        except Exception as e:
            print(f"  -> FAILED to cache data for '{item.text(1)}'. Error: {e}")

    def _on_cache_toggled(self, is_checked):
        """
        Shows the popup and runs the actual cache creation process.
        """
        if is_checked:
            print("--- CACHE ACTIVATED ---")
            
            items_to_cache = []
            for i in range(self.track_list_panel.track_tree.topLevelItemCount()):
                item = self.track_list_panel.track_tree.topLevelItem(i)
                if item.data(0, QtCore.Qt.ItemDataRole.UserRole) is not None:
                    items_to_cache.append(item)
            
            if not items_to_cache:
                self.track_list_panel.cache_mode_btn.setChecked(False)
                return

            progress_dialog = QtWidgets.QProgressDialog(
                "Building performance cache...", "Cancel", 0, len(items_to_cache), self
            )
            progress_dialog.setWindowTitle("Caching Animation Data")
            progress_dialog.setWindowModality(QtCore.Qt.WindowModality.WindowModal)
            progress_dialog.show()

            cache_was_successful = True 
            for i, item in enumerate(items_to_cache):
                if progress_dialog.wasCanceled():
                    print("-> Cache building CANCELED by user.")
                    self.track_list_panel.cache_mode_btn.setChecked(False) 
                    cache_was_successful = False
                    break

                progress_dialog.setLabelText(f"Processing: {item.text(1)} ({i+1}/{len(items_to_cache)})...")
                progress_dialog.setValue(i)
                QtWidgets.QApplication.processEvents()

                
                self._build_cache_for_item(item)
            
            progress_dialog.setValue(len(items_to_cache)) 

            if cache_was_successful:
                print("--- CACHE BUILD COMPLETE ---")
                self.track_list_panel.cache_mode_btn.setText("Cache Active (Refresh)")
            else:
                print("--- CACHE PROCESS INTERRUPTED ---")
                
                self.track_list_panel.cache_mode_btn.blockSignals(True)
                self.track_list_panel.cache_mode_btn.setChecked(False)
                self.track_list_panel.cache_mode_btn.setText("Activate Cache Mode")
                self.track_list_panel.cache_mode_btn.blockSignals(False)

        else:
            print("--- CACHE DEACTIVATED (Live Mode) ---")
            self.track_list_panel.cache_mode_btn.setText("Activate Cache Mode")
        
        self.keyframe_area.update()

    #END CACHE FUNCTION
    
# =======================================
# # === END: MyTimelineWidget         ===
# =======================================

# =======================================
# # === START: TrackListPanel         ===
# =======================================
class TrackListPanel(QtWidgets.QWidget):
    def __init__(self, timeline_widget, parent=None):
        super().__init__(parent)
        self.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.PreventContextMenu)
        self.timeline_widget = timeline_widget
        self.main_layout = QtWidgets.QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)

        print("DEBUG: TrackListPanel created.") 

        
        toolbar = QtWidgets.QWidget()
        toolbar_layout = QtWidgets.QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(5, 5, 5, 5)

        self.search_bar = QtWidgets.QLineEdit()
        self.search_bar.setPlaceholderText("Search Layers...")
        self.search_bar.textChanged.connect(timeline_widget.on_search_text_changed)
        
        add_btn = QtWidgets.QPushButton("+ Add")
        add_btn.clicked.connect(timeline_widget.add_selected_objects)
        
        remove_btn = QtWidgets.QPushButton("- Remove")
        remove_btn.clicked.connect(timeline_widget.remove_selected_layers)

        bake_btn = QtWidgets.QPushButton("Bake")
        bake_btn.clicked.connect(timeline_widget.bake_selected_layers)

        clear_btn = QtWidgets.QPushButton("Clear")
        clear_btn.clicked.connect(timeline_widget.clear_all_layers)

        self.cache_mode_btn = QtWidgets.QPushButton("Activate Cache Mode")
        self.cache_mode_btn.setCheckable(True) 
        self.cache_mode_btn.setToolTip("Click to build a fast internal cache for smoother UI performance on heavy scenes.")
        
        
        self.cache_mode_btn.setStyleSheet("""
            QPushButton {
                background-color: #8c4343; /*Red for silent mode*/
                color: white;              /*Makes the text color white and legible */
                border: none;              /*Remove any default margins */
                padding: 4px 8px;          /*A little inner space for beauty*/
                border-radius: 4px;        /*Modern rounded corners*/
            }
            QPushButton:checked {
                background-color: #4a6d4a; /*Green for light mode */
                font-weight: bold;         /*Text becomes bolder in light mode*/
            }
        """)
        
        
        self.cache_mode_btn.toggled.connect(timeline_widget._on_cache_toggled)
        
        toolbar_layout.addWidget(self.search_bar)
        toolbar_layout.addWidget(self.cache_mode_btn)
        toolbar_layout.addStretch()
        toolbar_layout.addWidget(add_btn)
        toolbar_layout.addWidget(remove_btn)
        toolbar_layout.addWidget(bake_btn)
        toolbar_layout.addWidget(clear_btn)
        
        
        self.track_tree = QtWidgets.QTreeWidget()
        self.track_tree.setColumnCount(4)
        self.value_delegate = ValueDelegate(self.track_tree, self)
        self.track_tree.setItemDelegateForColumn(3, self.value_delegate)
        self.track_tree.customContextMenuRequested.connect(timeline_widget.open_track_context_menu)
        self.track_tree.setHeaderLabels(['', 'Track Name', 'Controller', 'Value'])
        self.track_tree.setColumnWidth(0, 25)
        self.track_tree.setColumnWidth(1, 150)
        self.track_tree.header().setStretchLastSection(True)
        self.track_tree.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.ExtendedSelection)
        self.track_tree.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.CustomContextMenu)
        
        
        self.track_tree.customContextMenuRequested.connect(timeline_widget.open_track_context_menu)
        self.track_tree.itemDoubleClicked.connect(timeline_widget.on_item_double_clicked)
        self.track_tree.itemChanged.connect(timeline_widget.on_item_changed)
        self.track_tree.itemClicked.connect(timeline_widget.on_visibility_icon_clicked)
        
        self.main_layout.addWidget(toolbar)
        self.main_layout.addWidget(self.track_tree)


# =======================================
# # === END: TrackListPanel           ===
# =======================================

# =======================================
# # === START: Custom MixerTreeWidget ===
# =======================================
class MixerTreeWidget(QtWidgets.QTreeWidget):
    """
    Final version with full debugging:
    This version shows us whether dropEvent is executed and why
    a move may succeed or fail.
    """
    def __init__(self, timeline_widget, parent=None):
        super().__init__(parent)
        self.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.PreventContextMenu)
        self.timeline_widget = timeline_widget
        self.setDragDropMode(QtWidgets.QAbstractItemView.DragDropMode.InternalMove)
        self.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)


    def dropEvent(self, event: QtGui.QDropEvent):
        print("\n--- 💧 dropEvent Fired (Final Version with Debug) 💧 ---")

        dragged_item = self.selectedItems()[0] if self.selectedItems() else None
        if not dragged_item or dragged_item.parent() is not None:
            print("  -> ❌ REJECTED: Drag operation is not valid.")
            event.ignore()
            return

        event.setDropAction(QtCore.Qt.DropAction.MoveAction)
        super().dropEvent(event)
        print("  -> Base class dropEvent completed. Now reapplying widgets if necessary.")

        for i in range(self.topLevelItemCount()):
            item = self.topLevelItem(i)
            if self.itemWidget(item, 1) is None:
                print(f"  -> FIXING: Re-creating ComboBox for '{item.text(0)}'")
                
                blend_combo = QtWidgets.QComboBox(self)
                blend_combo.addItems(["Override", "None"])
                
                
                current_mode = item.data(1, self.timeline_widget.BLEND_MODE_ROLE) or "Override"
                blend_combo.setCurrentText(current_mode)
                
                blend_combo.currentTextChanged.connect(
                    lambda text, bound_item=item: bound_item.setData(1, self.timeline_widget.BLEND_MODE_ROLE, text)
                )
                self.setItemWidget(item, 1, blend_combo)

        print("--- ✅ dropEvent Finished ---")

    


    def startDrag(self, supportedActions):
        """
        This function is executed before any drawing operation begins.
        """
        
        selected_items = self.selectedItems()
        
        
        if not selected_items:
            return

        
        item = selected_items[0]
        
        
        if item.parent() is not None:
            
            return
        
        
        super().startDrag(supportedActions)

    
    def contextMenuEvent(self, event):
        event.accept()

# =======================================
# # === END: Custom MixerTreeWidget   ===
# =======================================

# =======================================
# # === START: MotionMixerPanel       ===
# =======================================
class MotionMixerPanel(QtWidgets.QWidget):
    def __init__(self, timeline_widget, parent=None):
        super().__init__(parent)
        self.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.PreventContextMenu)
        self.timeline_widget = timeline_widget
        self.main_layout = QtWidgets.QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        
        toolbar = QtWidgets.QHBoxLayout()
        import_btn = QtWidgets.QPushButton("+ Import Clip")
        import_btn.clicked.connect(self._import_clip_file)
        remove_btn = QtWidgets.QPushButton("- Remove Selected")
        remove_btn.clicked.connect(self._remove_selected)
        #blend_btn = QtWidgets.QPushButton("Create Blend")
        #blend_btn.setToolTip("Creates a transition between the selected layer and the one directly below it.")
        #blend_btn.clicked.connect(self.timeline_widget.logic.create_mixer_layer_blend)
        self.bake_btn = QtWidgets.QPushButton("Bake Mixer")
        self.bake_btn.clicked.connect(self._on_bake_clicked)
        toolbar.addWidget(import_btn)
        toolbar.addWidget(remove_btn)
        #toolbar.addWidget(blend_btn)
        toolbar.addStretch()
        #toolbar.addWidget(blend_btn)
        toolbar.addWidget(self.bake_btn)
        
        self.track_tree = MixerTreeWidget(self.timeline_widget) 
        
        self.track_tree.setColumnCount(4)
        self.track_tree.setHeaderLabels(["Track Name", "Blend Mode", "Start", "End"])
        self.track_tree.setColumnWidth(1, 100) 

        
        
        self.main_layout.addLayout(toolbar)
        self.main_layout.addWidget(self.track_tree)
        
    def _import_clip_file(self):
        file_paths, _ = QtWidgets.QFileDialog.getOpenFileNames(self, "Import Animation Clip(s)", "", "Animation Clips (*.clip)")
        if not file_paths: return

        for file_path in file_paths:
            try:
                with open(file_path, 'r') as f: clip_data = json.load(f)

                clip_name = os.path.basename(file_path)
                duration = clip_data.get("properties", {}).get("duration_frames", 100)
                start_time = int(rt.currentTime)
                end_time = start_time + int(duration)
                track_name = os.path.splitext(clip_name)[0]
                
                
                track_item = QtWidgets.QTreeWidgetItem([track_name, "", "", ""])
                
                
                self.track_tree.addTopLevelItem(track_item)

                
                blend_combo = QtWidgets.QComboBox(self.track_tree)
                blend_combo.addItems(["Override", "None"])
                
                blend_combo.currentTextChanged.connect(
                    lambda text, item=track_item: item.setData(1, self.timeline_widget.BLEND_MODE_ROLE, text)
                )
                
                self.track_tree.setItemWidget(track_item, 1, blend_combo)
                track_item.setData(1, self.timeline_widget.BLEND_MODE_ROLE, "Override")

                
                clip_item = QtWidgets.QTreeWidgetItem([clip_name, "", str(start_time), str(end_time)])
                clip_item.setData(0, QtCore.Qt.ItemDataRole.UserRole, clip_data)
                
                track_item.addChild(clip_item)
                track_item.setExpanded(True)

            except Exception as e:
                QtWidgets.QMessageBox.critical(self, "Import Error", f"Failed to import clip: {file_path}\nError: {e}")

        self.timeline_widget.keyframe_area.update()
        self.timeline_widget.sync_scrollbars()

    def _remove_selected(self):
        selected_items = self.track_tree.selectedItems()
        if not selected_items: return
            
        tracks_to_delete = set()
        for item in selected_items:
            tracks_to_delete.add(item.parent() if item.parent() else item)
                
        root = self.track_tree.invisibleRootItem()
        for track in tracks_to_delete:
            root.removeChild(track)
            
        self.timeline_widget.keyframe_area.update()
        self.timeline_widget.sync_scrollbars()

    def _on_bake_clicked(self):
        
        self.timeline_widget.logic.bake_mixer_to_scene()


    def contextMenuEvent(self, event):
        event.accept()

    
# =======================================
# # === END: MotionMixerPanel         ===

# =======================================
