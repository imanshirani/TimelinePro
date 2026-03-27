
import sys
import os
import json
import uuid
import configparser
import math
import ctypes
import ctypes.wintypes
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
        'SpacewarpObject_color': "#ACA6A6", # white         
        'bone_color': '#C8BFE7', 
        'particle_color': "#886927"
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
        bg_color = self.current_color.name()
        r, g, b, _ = self.current_color.getRgb()
        brightness = (r * 299 + g * 587 + b * 114) / 1000
        text_color = "#000000" if brightness > 128 else "#FFFFFF"

        self.color_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {bg_color};
                color: {text_color};
                border: 1px solid #555555;
                padding: 5px;
                border-radius: 4px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                border: 1px solid #FFFFFF;
            }}
        """)

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
        #self.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.PreventContextMenu)

        self.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self.open_context_menu)

        print("✅ DEBUG: MarkerView widget created successfully.")
        self.timeline_widget = timeline_widget
        self.ruler = timeline_widget.ruler 
        self.setFixedHeight(32)
        #self.setStyleSheet("background-color: #ff0000;")
        
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
                painter.drawPolygon(marker_polygon)
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

    
    def _frame_at_pos(self, x_pos):
        if self.ruler.pixels_per_frame <= 0:
            return self.ruler.start_frame
        frame = self.ruler.start_frame + (x_pos / self.ruler.pixels_per_frame)
        return int(round(frame))

    def _marker_at_pos(self, pos):
        
        h = self.height()
        
        marker_click_rect = QtCore.QRectF(-7, 3, 14, h - 3) # x, y, w, h
        
        for marker_uid, marker in self.timeline_widget.markers.items():
            frame = marker['frame']
            x_pos = (frame - self.ruler.start_frame) * self.ruler.pixels_per_frame
            
            
            current_marker_rect = marker_click_rect.translated(x_pos, 0)
            
            
            if current_marker_rect.contains(pos):
                return marker_uid # UID
        return None 

    def mousePressEvent(self, event):
        
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            marker_uid = self._marker_at_pos(event.pos())
            modifiers = event.modifiers()

            if modifiers == QtCore.Qt.KeyboardModifier.ShiftModifier:
                
                frame = self._frame_at_pos(event.pos().x())
                self.timeline_widget._add_marker(frame)
            elif marker_uid:
                
                self.timeline_widget._edit_marker(marker_uid)
            else:
                
                pass
        
        
        super().mousePressEvent(event) 

    def open_context_menu(self, position):
        
        menu = QtWidgets.QMenu(self)
        marker_uid_at_pos = self._marker_at_pos(position)

        if marker_uid_at_pos:
            
            edit_action = menu.addAction("Edit Marker...")
            edit_action.triggered.connect(lambda: self.timeline_widget._edit_marker(marker_uid_at_pos))
            
            delete_action = menu.addAction("Delete Marker")
            delete_action.triggered.connect(lambda: self.timeline_widget._delete_marker(marker_uid_at_pos))
            
        else:
            
            frame = self._frame_at_pos(position.x())
            add_action = menu.addAction(f"Add Marker at frame {frame}")
            add_action.triggered.connect(lambda: self.timeline_widget._add_marker(frame))

        
        menu.exec(self.mapToGlobal(position))
    
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
            'geometry_color': QtWidgets.QPushButton(), 'SpacewarpObject_color': QtWidgets.QPushButton(),
            'bone_color': QtWidgets.QPushButton(), 'particle_color': QtWidgets.QPushButton()
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
        <p><b>Version:</b> 0.0.5</p>
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
            'geometry_color': "#475A6D", 'SpacewarpObject_color': "#ACA6A6",
            'bone_color': '#C8BFE7', 'particle_color': "#886927"
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
            
            self.parent().logic._load_default_hidden_tracks_from_settings()
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
        self.setMouseTracking(True)
        
        
        self.is_dragging_slider = False

    def _x_to_frame(self, x_pos):
        
        if self.pixels_per_frame <= 0: return self.start_frame
        frame = self.start_frame + (x_pos / self.pixels_per_frame)
        return int(round(frame))

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
        if hasattr(self.timeline_widget, 'curve_editor'):
            self.timeline_widget.curve_editor.update()
            
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
            painter.setBrush(QtGui.QColor("#ff4747"))
            
            painter.drawLine(int(slider_x), 0, int(slider_x), self.height())
            
            
            handle_polygon = QtGui.QPolygonF([
                QtCore.QPointF(slider_x, 8),
                QtCore.QPointF(slider_x - 5, 0),
                QtCore.QPointF(slider_x + 5, 0)
            ])
            painter.drawPolygon(handle_polygon)

    
    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            if self.timeline_widget.sync_timer.isActive():
                self.timeline_widget.sync_timer.stop()

            
            new_frame = self._x_to_frame(event.pos().x())
            pymxs.runtime.sliderTime = new_frame 
            
            self.timeline_widget.current_frame = int(new_frame)
            
            self.is_dragging_slider = True 
            self.setCursor(QtCore.Qt.CursorShape.SizeHorCursor)
            
            
            self.update()
            self.timeline_widget.keyframe_area.update()
            
            event.accept()

    def mouseMoveEvent(self, event):

        if self.is_dragging_slider:
            new_frame = self._x_to_frame(event.pos().x())
            clamped_frame = int(max(self.start_frame, min(new_frame, self.end_frame)))
            
            self.timeline_widget.current_frame = clamped_frame
            
            
            pymxs.runtime.sliderTime = clamped_frame
            
            
            self.update() 
            key_area = self.timeline_widget.keyframe_area
            if hasattr(key_area, 'slider_item') and key_area.slider_item:
                new_x = int((clamped_frame - self.start_frame) * self.pixels_per_frame)
                line = key_area.slider_item.line()
                line.setLine(new_x, line.y1(), new_x, line.y2())
                key_area.slider_item.setLine(line)
            else:
                
                key_area._redraw_scene()

            
            curve_editor = self.timeline_widget.curve_editor
            if hasattr(curve_editor, 'slider_item') and curve_editor.slider_item:
               
                new_x_curve = curve_editor._frame_to_x(clamped_frame)
                line = curve_editor.slider_item.line()
                line.setLine(new_x_curve, 0, new_x_curve, line.y2())
                curve_editor.slider_item.setLine(line)
            
            
            event.accept()
            return

        
        current_frame = self.timeline_widget.current_frame
        slider_x = int((current_frame - self.start_frame) * self.pixels_per_frame)
        
        if abs(event.pos().x() - slider_x) < 10:
            self.setCursor(QtCore.Qt.CursorShape.SizeHorCursor)
        else:
            self.unsetCursor()
            
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            self.is_dragging_slider = False
            self.unsetCursor()
            
            
            if not self.timeline_widget.sync_timer.isActive():
                self.timeline_widget.sync_timer.start(50)
                
            self.timeline_widget._force_ui_refresh()
            event.accept()


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
# # === ( QGraphicsView )             ===
# =======================================
class CurveEditorWidget(QtWidgets.QGraphicsView):
    selectionChanged = QtCore.Signal(int)
    def __init__(self, timeline_widget, parent=None):
        super().__init__(parent)
        self.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.PreventContextMenu)
        
        
        self.scene = QtWidgets.QGraphicsScene(self)
        self.setScene(self.scene)
        
        self.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        self.setAlignment(QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignTop)
        
        self.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)        
        self.setStyleSheet("background-color: #2d2d2d; border: none;")
        
        
        self.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        
        self.is_snapping = True

        self.timeline_widget = timeline_widget
        self.ruler = timeline_widget.ruler
        
        self.min_value = -100.0
        self.max_value = 100.0
        
        self.selected_keys = set()
        self.key_click_margin = 8
        self.handle_click_margin = 8

        
        self._is_panning = False
        self._last_pan_pos = QtCore.QPoint()

        
        self.drag_mode = None
        self.dragging_key_info = {}
        self.dragging_handle_info = None # (controller, index, 'in'/'out')
        self.drag_start_pos_scene = QtCore.QPointF()
        self.marquee_rect_item = None

        
        
        
        self.grid_pen = QtGui.QPen(QtGui.QColor("#4a4a4a"))
        self.zero_line_pen = QtGui.QPen(QtGui.QColor("#777777"))
        self.curve_pen_x = QtGui.QPen(QtGui.QColor("#d45656"), 2)
        self.curve_pen_y = QtGui.QPen(QtGui.QColor("#56d456"), 2)
        self.curve_pen_z = QtGui.QPen(QtGui.QColor("#5698d4"), 2)
        self.key_brush_x = QtGui.QBrush(QtGui.QColor("#d45656"))
        self.key_brush_y = QtGui.QBrush(QtGui.QColor("#56d456"))
        self.key_brush_z = QtGui.QBrush(QtGui.QColor("#5698d4"))
        self.selected_key_brush = QtGui.QBrush(QtGui.QColor("#d4a056"))
        
        self.tangent_pen = QtGui.QPen(QtGui.QColor("#FFFFFF"), 1, QtCore.Qt.PenStyle.DotLine)
        self.handle_brush = QtGui.QBrush(QtGui.QColor("#FFFFFF"))
        self.handle_size = 3.5
        self.key_polygon = QtGui.QPolygonF([QtCore.QPointF(-6, 0), QtCore.QPointF(0, -6), QtCore.QPointF(6, 0), QtCore.QPointF(0, 6)])

    
    
    def _redraw_scene(self):
        
        for item in self.scene.items():
            if item != self.marquee_rect_item:
                self.scene.removeItem(item)
        
        
        settings = self.timeline_widget.settings['Ruler_Smart_Ticking']
        if self.ruler.pixels_per_frame > settings.getfloat('zoom_level_1_threshold_px'): major_step = settings.getint('zoom_level_1_step_frames')
        elif self.ruler.pixels_per_frame > settings.getfloat('zoom_level_2_threshold_px'): major_step = settings.getint('zoom_level_2_step_frames')
        else: major_step = 10
        if major_step == 0: major_step = 1

        
        view_rect = self.mapToScene(self.viewport().rect()).boundingRect()
        
        
        start_draw = max(self.ruler.start_frame, int(self._x_to_frame(view_rect.left())))
        end_draw = min(self.ruler.end_frame, int(self._x_to_frame(view_rect.right())))
        
        
        start_draw -= major_step
        end_draw += major_step
        
        for frame in range(self.ruler.start_frame, self.ruler.end_frame + 1, major_step):
            x_pos = self._frame_to_x(frame)
            self.scene.addLine(x_pos, view_rect.top(), x_pos, view_rect.bottom(), self.grid_pen).setZValue(-10)
            
        
        y_zero = self._value_to_y(0)
        self.scene.addLine(view_rect.left(), y_zero, view_rect.right(), y_zero, self.zero_line_pen).setZValue(-9)

        
        track_list_widget = self.timeline_widget.track_list_panel.track_tree
        iterator = QtWidgets.QTreeWidgetItemIterator(track_list_widget)
        while iterator.value():
            item = iterator.value()
            if not item.isHidden() and item.parent() is not None:
                sub_anim = item.data(0, self.timeline_widget.SUBANIM_ROLE)
                try:
                    if sub_anim and sub_anim.controller:
                        controller_class = rt.classOf(sub_anim.controller)
                        
                        if controller_class in [rt.bezier_float, rt.linear_float, rt.tcb_float]:
                            if not (rt.isProperty(sub_anim.controller, "keys") and sub_anim.controller.keys.count > 0):
                                iterator += 1; continue

                            controller = sub_anim.controller
                            keys = controller.keys
                            track_name = item.text(1)
                            
                            
                            active_pen, active_brush = self.curve_pen_z, self.key_brush_z
                            if track_name.startswith("X "): active_pen, active_brush = self.curve_pen_x, self.key_brush_x
                            elif track_name.startswith("Y "): active_pen, active_brush = self.curve_pen_y, self.key_brush_y

                            
                            path = QtGui.QPainterPath()
                            first_pt = True
                            
                            for i in range(keys.count):
                                k = keys[i]
                                time, val = float(k.time), float(k.value)
                                x, y = self._frame_to_x(time), self._value_to_y(val)
                                
                                if first_pt:
                                    path.moveTo(x, y)
                                    first_pt = False
                                else:
                                    
                                    prev_k = keys[i-1]
                                    prev_x, prev_y = self._frame_to_x(float(prev_k.time)), self._value_to_y(float(prev_k.value))
                                    
                                    if controller_class == rt.bezier_float:
                                        
                                        cx1 = prev_x + (x - prev_x) * 0.33
                                        cy1 = prev_y 
                                        cx2 = x - (x - prev_x) * 0.33
                                        cy2 = y
                                        path.cubicTo(cx1, cy1, cx2, cy2, x, y)
                                    else:
                                        path.lineTo(x, y)
                            
                            self.scene.addPath(path, active_pen).setZValue(1)

                            
                            view_start_frame = self.ruler.start_frame
                            view_end_frame = self.ruler.end_frame

                            for i in range(keys.count):
                                key = keys[i]
                                key_time = float(key.time)
                                
                                
                                if key_time < view_start_frame or key_time > view_end_frame:
                                    continue 

                                key_val = float(key.value)
                                k_pos = QtCore.QPointF(self._frame_to_x(key_time), self._value_to_y(key_val))
                                
                                key_id = (controller, i)
                                is_selected = (key_id in self.selected_keys)
                                current_brush = self.selected_key_brush if is_selected else active_brush
                                
                                key_item = self.scene.addPolygon(self.key_polygon, QtGui.QPen(QtCore.Qt.PenStyle.NoPen), current_brush)
                                key_item.setPos(k_pos)
                                key_item.setData(self.timeline_widget.GRAPHICS_ITEM_KEY_ID_ROLE, key_id)
                                key_item.setZValue(10)

                                
                                if is_selected and rt.isProperty(key, 'inTangent'):
                                    self._draw_handles(key, controller, i, k_pos)

                except Exception as e:
                    print(f"Error drawing curve: {e}") 
            iterator += 1
            
        self._update_slider_visual()
       
    
    def _draw_handles(self, key, controller, i, key_pos_scene):
        out_handle_pos = self._get_handle_pos_scene(key, 'out')
        in_handle_pos = self._get_handle_pos_scene(key, 'in')
        
        self.scene.addLine(QtCore.QLineF(key_pos_scene, out_handle_pos), self.tangent_pen).setZValue(9)
        self.scene.addLine(QtCore.QLineF(key_pos_scene, in_handle_pos), self.tangent_pen).setZValue(9)
        
        hs = self.handle_size
        for h_type, pos in [('out', out_handle_pos), ('in', in_handle_pos)]:
            h_item = self.scene.addEllipse(-hs, -hs, hs*2, hs*2, QtGui.QPen(QtCore.Qt.PenStyle.NoPen), self.handle_brush)
            h_item.setPos(pos)
            h_item.setData(self.timeline_widget.GRAPHICS_ITEM_KEY_ID_ROLE, (controller, i, h_type))
            h_item.setZValue(11)

    def _update_slider_visual(self):
        
        current_frame = self.timeline_widget.current_frame
        ruler = self.timeline_widget.ruler
        if ruler.start_frame <= current_frame <= ruler.end_frame:
            slider_x = self._frame_to_x(current_frame) 
            slider_pen = QtGui.QPen(QtGui.QColor("#ff4747")); slider_pen.setWidth(2) 
            rect = self.viewport().rect()
            self.slider_item = self.scene.addLine(slider_x, 0, slider_x, rect.height(), slider_pen)
            self.slider_item.setZValue(100) 
        else:
            self.slider_item = None
    
    
    def fit_selected(self):
        
        target_keys = []
        
        
        if self.selected_keys:
            
            for key_id in self.selected_keys:
                
                controller, idx = key_id
                try: target_keys.append(controller.keys[idx])
                except: pass
        else:
            
            track_tree = self.timeline_widget.track_list_panel.track_tree
            iterator = QtWidgets.QTreeWidgetItemIterator(track_tree)
            while iterator.value():
                item = iterator.value()
                if not item.isHidden():
                    sub_anim = item.data(0, self.timeline_widget.SUBANIM_ROLE)
                    if sub_anim and hasattr(sub_anim, 'controller') and sub_anim.controller:
                         if rt.isProperty(sub_anim.controller, "keys"):
                             for k in sub_anim.controller.keys: target_keys.append(k)
                iterator += 1

        if not target_keys: return

        
        min_t, max_t = float('inf'), float('-inf')
        min_v, max_v = float('inf'), float('-inf')

        for k in target_keys:
            t, v = float(k.time), float(k.value)
            if t < min_t: min_t = t
            if t > max_t: max_t = t
            if v < min_v: min_v = v
            if v > max_v: max_v = v

        if min_t == float('inf'): return

        
        t_pad = max(5, (max_t - min_t) * 0.1) 
        v_pad = max(10, (max_v - min_v) * 0.2) 

        new_start = min_t - t_pad
        new_end = max_t + t_pad
        new_min_val = min_v - v_pad
        new_max_val = max_v + v_pad
        
        
        if new_start == new_end: new_start -= 10; new_end += 10
        if new_min_val == new_max_val: new_min_val -= 10; new_max_val += 10

        
        pymxs.runtime.animationRange = pymxs.runtime.interval(int(new_start), int(new_end))
        self.min_value = new_min_val
        self.max_value = new_max_val
        
        self.timeline_widget.ruler.update_range() 
        self._redraw_scene()
        self.timeline_widget.value_ruler.update()
        print(f"Focused View: Frames {int(new_start)}-{int(new_end)}, Values {int(new_min_val)}-{int(new_max_val)}")

    

    def mousePressEvent(self, event):
        item_under_mouse = self.itemAt(event.pos())
        
        
        if event.button() == QtCore.Qt.MouseButton.MiddleButton:
            self._is_panning = True
            self._last_pan_pos = event.pos()
            self.setCursor(QtCore.Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return
            
        
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            
            ruler = self.timeline_widget.ruler
            current_frame = self.timeline_widget.current_frame
            slider_x = self._frame_to_x(current_frame)
            
            slider_view_x = self.mapFromScene(QtCore.QPointF(slider_x, 0)).x()
            
            
            handle_rect = QtCore.QRectF(slider_view_x - 10, 0, 20, self.height())
            
            
            if handle_rect.contains(QtCore.QPointF(event.pos())):
                self.drag_mode = 'scrub_timeline'
                self.setCursor(QtCore.Qt.CursorShape.SizeHorCursor)
                
               
                if self.timeline_widget.sync_timer.isActive():
                    self.timeline_widget.sync_timer.stop()
                
                event.accept()
                return 

            
            item_under_mouse = self.itemAt(event.pos())
            data = item_under_mouse.data(self.timeline_widget.GRAPHICS_ITEM_KEY_ID_ROLE) if item_under_mouse else None
            modifiers = event.modifiers()

            
            if data and isinstance(data, tuple) and len(data) == 2:
                key_id = data
                is_key_already_selected = key_id in self.selected_keys

                if not is_key_already_selected:
                    if modifiers != QtCore.Qt.KeyboardModifier.ControlModifier:
                        self.selected_keys.clear()
                    self.selected_keys.add(key_id)
                elif modifiers == QtCore.Qt.KeyboardModifier.ControlModifier and is_key_already_selected:
                    self.selected_keys.remove(key_id)
                
                self.selectionChanged.emit(len(self.selected_keys))
                self.drag_mode = 'move_key'
                self.drag_start_pos_scene = self.mapToScene(event.pos())
                
                self.dragging_key_info.clear()
                for item in self.scene.items():
                    k_id = item.data(self.timeline_widget.GRAPHICS_ITEM_KEY_ID_ROLE)
                    if k_id and isinstance(k_id, tuple) and len(k_id) == 2 and k_id in self.selected_keys:
                        self.dragging_key_info[k_id] = item.pos()
                
                self._redraw_scene()
                event.accept()
                return

            
            if modifiers != QtCore.Qt.KeyboardModifier.ControlModifier:
                self.selected_keys.clear()
            self._redraw_scene()
            self.selectionChanged.emit(len(self.selected_keys))
            
            self.drag_mode = 'marquee_select'
            self.drag_start_pos_scene = self.mapToScene(event.pos())
            
            if self.marquee_rect_item: self.scene.removeItem(self.marquee_rect_item)
            marquee_pen = QtGui.QPen(QtGui.QColor(180, 180, 220, 200), 1, QtCore.Qt.PenStyle.DashLine)
            marquee_brush = QtGui.QBrush(QtGui.QColor(100, 100, 150, 40))
            self.marquee_rect_item = self.scene.addRect(QtCore.QRectF(self.drag_start_pos_scene, self.drag_start_pos_scene), marquee_pen, marquee_brush)
            self.marquee_rect_item.setZValue(99)
            
            event.accept()
            return

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        
        
        if self._is_panning:
            current_pos = event.pos()
            delta = current_pos - self._last_pan_pos
            
            # X-axis: Pan rt.animationRange
            delta_x_pixels = delta.x()
            delta_frames = delta_x_pixels / self.timeline_widget.ruler.pixels_per_frame
            new_start = rt.animationRange.start - delta_frames
            new_end = rt.animationRange.end - delta_frames
            rt.animationRange = rt.interval(int(new_start), int(new_end))

            # Y-axis: Pan Tree Scrollbar
            delta_y = delta.y()
            active_tree_scrollbar = self.timeline_widget._get_active_tree_widget().verticalScrollBar()
            active_tree_scrollbar.setValue(active_tree_scrollbar.value() - delta_y) 
            
            self._last_pan_pos = current_pos
            event.accept()
            super().mouseMoveEvent(event)
            return


        if self.drag_mode == 'scrub_timeline':
            scene_pos = self.mapToScene(event.pos())
            new_frame = self._x_to_frame(scene_pos.x())
            new_frame_int = int(new_frame)
            
            pymxs.runtime.sliderTime = new_frame_int
            self.timeline_widget.current_frame = new_frame_int            
            self.timeline_widget.ruler.update()
            if self.slider_item:
                new_x = self._frame_to_x(new_frame_int)
                line = self.slider_item.line()
                
                line.setLine(new_x, 0, new_x, line.y2()) 
                self.slider_item.setLine(line)
            else:
                self._redraw_scene()
            
            event.accept()
            return

        
        if not self.drag_mode:
            ruler = self.timeline_widget.ruler
            current_frame = self.timeline_widget.current_frame
            slider_x = self._frame_to_x(current_frame)
            slider_view_x = self.mapFromScene(QtCore.QPointF(slider_x, 0)).x()
            
            handle_rect = QtCore.QRectF(slider_view_x - 10, 0, 20, self.height())
            
            if handle_rect.contains(QtCore.QPointF(event.pos())):
                self.setCursor(QtCore.Qt.CursorShape.SizeHorCursor)
            else:
                self.unsetCursor()
            return
            
        current_pos_scene = self.mapToScene(event.pos())
            
        
        
        try:
            
            if self.drag_mode == 'move_key':
                delta_scene = current_pos_scene - self.drag_start_pos_scene
                
                for key_id, original_pos in self.dragging_key_info.items():
                    controller, index = key_id 
                    
                    
                    new_pos = original_pos + delta_scene
                    raw_frame = self._x_to_frame(new_pos.x())
                    
                    
                    if self.is_snapping:
                        final_frame = round(raw_frame) 
                    else:
                        final_frame = raw_frame
                    
                    try:
                        
                        if hasattr(controller, 'keys'):
                             controller.keys[index].time = final_frame
                             
                             new_value = self._y_to_value(new_pos.y())
                             controller.keys[index].value = new_value
                    except: pass
                
                self._redraw_scene()
                event.accept()
                return
                
            
            if self.drag_mode == 'move_handle':
                controller, key_index, handle_type = self.dragging_handle_info
                key = controller.keys[key_index]
                
                
                new_handle_frame = self._x_to_frame(current_pos_scene.x())
                new_handle_value = self._y_to_value(current_pos_scene.y())
                
                key_time, key_value = float(key.time), float(key.value)
                time_diff_5 = 5.0 
                
                new_tangent_val = 0.0
                
                
                if handle_type == 'out':
                    time_delta = new_handle_frame - key_time
                    if time_delta != 0:
                        new_tangent_val = (new_handle_value - key_value) / (time_delta / time_diff_5)
                    key.outTangent = new_tangent_val
                else: # 'in'
                    time_delta = key_time - new_handle_frame
                    if time_delta != 0:
                        new_tangent_val = (key_value - new_handle_value) / (time_delta / time_diff_5)
                    key.inTangent = new_tangent_val
                
                self._redraw_scene() 
                event.accept()
                return

        except Exception as e:
            print(f"DEBUG Error during live drag: {e}")
            self.drag_mode = None 

       
        if self.drag_mode == 'marquee_select' and self.marquee_rect_item:
            rect = QtCore.QRectF(self.drag_start_pos_scene, current_pos_scene).normalized()
            self.marquee_rect_item.setRect(rect)
            event.accept()
            return
            
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        
        
        if event.button() == QtCore.Qt.MouseButton.MiddleButton:
            self._is_panning = False
            self.setCursor(QtCore.Qt.CursorShape.ArrowCursor)
            event.accept()
            return

        
        if self.drag_mode == 'scrub_timeline':
             if not self.timeline_widget.sync_timer.isActive():
                 self.timeline_widget.sync_timer.start(50)
             
             self.drag_mode = None
             self.unsetCursor()
             self.timeline_widget._force_ui_refresh()
             event.accept()
             return
        
        if self.drag_mode == 'move_key' and event.button() == QtCore.Qt.MouseButton.LeftButton:
            try:
                
                with pymxs.undo(True, "Move Curve Keys"):
                    pass
            except Exception as e:
                print(f"Error creating Undo block: {e}")
            
            self.drag_mode = None
            self.dragging_key_info.clear()
            self._redraw_scene() 
            event.accept()
            return
            
        
        if self.drag_mode == 'move_handle' and event.button() == QtCore.Qt.MouseButton.LeftButton:
            try:
                
                with pymxs.undo(True, "Edit Tangent"):
                    pass
            except Exception as e:
                print(f"Error creating Undo block: {e}")

            self.drag_mode = None
            self.dragging_handle_info = None
            self._redraw_scene() 
            event.accept()
            return

        
        if self.drag_mode == 'marquee_select' and event.button() == QtCore.Qt.MouseButton.LeftButton:
            if self.marquee_rect_item:
                marquee_rect_in_scene = self.marquee_rect_item.rect()
                items_in_rect = self.scene.items(marquee_rect_in_scene)
                
                for item in items_in_rect:
                    key_id = item.data(self.timeline_widget.GRAPHICS_ITEM_KEY_ID_ROLE)
                    if key_id and isinstance(key_id, tuple) and len(key_id) == 2:
                        self.selected_keys.add(key_id)
                
                self.scene.removeItem(self.marquee_rect_item)
                self.marquee_rect_item = None
                
            self.drag_mode = None
            self._redraw_scene()
            self.selectionChanged.emit(len(self.selected_keys))
            event.accept()
            return

        super().mouseReleaseEvent(event)
       
    def wheelEvent(self, event):
        active_tree_scrollbar = self.timeline_widget._get_active_tree_widget().verticalScrollBar()

        
        if event.modifiers() == QtCore.Qt.KeyboardModifier.NoModifier:
            active_tree_scrollbar = self.timeline_widget._get_active_tree_widget().verticalScrollBar()
            delta = event.angleDelta().y()
            num_steps = - (delta / 120.0 * 3.0)
            step_size = active_tree_scrollbar.singleStep()            
            new_value = active_tree_scrollbar.value() + int(num_steps * step_size)
            active_tree_scrollbar.setValue(new_value)            
            event.accept()
            return
            
        
        elif event.modifiers() == QtCore.Qt.KeyboardModifier.ShiftModifier:
            delta = event.angleDelta().y()
            delta_frames = delta / 12.0 
            new_start = rt.animationRange.start - delta_frames 
            new_end = rt.animationRange.end - delta_frames 
            rt.animationRange = rt.interval(int(new_start), int(new_end))
            event.accept()

        
        elif event.modifiers() == QtCore.Qt.KeyboardModifier.ControlModifier:
            zoom_factor = 1.15
            
            
            center_x_scene = self.mapToScene(event.pos()).x()
            center_frame = self._x_to_frame(center_x_scene)
            
            current_duration = max(1.0, float(rt.animationRange.end - rt.animationRange.start))
            
            if event.angleDelta().y() > 0:
                new_duration = current_duration / zoom_factor
            else:
                new_duration = current_duration * zoom_factor
            
            
            alpha = (center_frame - rt.animationRange.start) / current_duration if current_duration > 0 else 0.5
            new_start = center_frame - (new_duration * alpha)
            new_end = new_start + new_duration
            
            
            rt.animationRange = rt.interval(int(new_start), int(new_end))
            
            if isinstance(self, CurveEditorWidget):
                
                center_y_scene = self.mapToScene(event.pos()).y()
                
                
                current_v_scale = self.transform().m22()
                if event.angleDelta().y() > 0:
                    new_v_scale = current_v_scale * zoom_factor
                else:
                    new_v_scale = current_v_scale / zoom_factor

                
                self.centerOn(center_x_scene, center_y_scene)
                transform = self.transform()
                transform.scale(1.0, zoom_factor if event.angleDelta().y() > 0 else 1.0/zoom_factor)
                self.setTransform(transform)

            event.accept()
            
        else:
            event.ignore()

    
    
    def _get_key_pos_scene(self, key):
        
        return QtCore.QPointF(self._frame_to_x(float(key.time)), self._value_to_y(float(key.value)))

    def _get_handle_pos_scene(self, key, handle_type):
        
        time_diff = 5.0 
        key_time, key_value = float(key.time), float(key.value)
        
        if handle_type == 'out':
            tangent_val = float(key.outTangent)
            handle_time, handle_value = key_time + time_diff, key_value + tangent_val * time_diff
        else: # 'in'
            tangent_val = float(key.inTangent)
            handle_time, handle_value = key_time - time_diff, key_value - tangent_val * time_diff
            
        return QtCore.QPointF(self._frame_to_x(handle_time), self._value_to_y(handle_value))

    def _frame_to_x(self, frame):
        
        if self.ruler.pixels_per_frame <= 0: return 0
        return (frame - self.ruler.start_frame) * self.ruler.pixels_per_frame

    def _value_to_y(self, value):
        
        value_range = self.max_value - self.min_value
        if value_range == 0: 
            return 0 
            
        
        
        
        view_height = self.viewport().height()
        if view_height == 0: view_height = 1000 
        
        alpha = (value - self.min_value) / value_range
        
        return view_height - (alpha * view_height)

    def _x_to_frame(self, x_pos):
        
        if self.ruler.pixels_per_frame <= 0: return 0
        return self.ruler.start_frame + (x_pos / self.ruler.pixels_per_frame)

    def _y_to_value(self, y_pos):
        
        value_range = self.max_value - self.min_value
        if value_range == 0: return self.min_value
        
        view_height = self.viewport().height()
        if view_height == 0: view_height = 1000
        
        alpha = (view_height - y_pos) / view_height
        return self.min_value + (alpha * value_range)
    

    def update(self):
        
        self._redraw_scene()

    def update_value_range(self):
        
        min_val, max_val, found_keys = float('inf'), float('-inf'), False
        track_list_widget = self.timeline_widget.track_list_panel.track_tree
        iterator = QtWidgets.QTreeWidgetItemIterator(track_list_widget)
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
        else: 
            self.min_value, self.max_value = -100.0, 100.0
            
        self._redraw_scene()
        self.timeline_widget.value_ruler.update()
        
    def set_vertical_zoom(self, value):
        
        key_values = []
        for c, i in self.selected_keys:
            try: key_values.append(float(c.keys[i].value))
            except IndexError: pass
            
        center_value = sum(key_values) / len(key_values) if key_values else (self.min_value + self.max_value) / 2.0
        total_range = 200.0 / (value / 100.0)
        self.min_value = center_value - total_range / 2.0; self.max_value = center_value + total_range / 2.0
        
        self._redraw_scene()
        self.timeline_widget.value_ruler.update()

    def apply_tangent_type(self, tangent_name):
        """
        'Linear''Bezier' 'Curve'
        """
        if not self.selected_keys:
            return

        
        keys_by_controller = {}
        for key_id in self.selected_keys:
            controller, key_index = key_id
            if controller not in keys_by_controller:
                keys_by_controller[controller] = []
            keys_by_controller[controller].append(key_index)

        try:
            with pymxs.undo(True, f"Set Tangent to {tangent_name.title()}"):
                for controller, indices in keys_by_controller.items():
                    
                    
                    if not (rt.isProperty(controller, "keys") and controller.keys.count > 0 and rt.isProperty(controller.keys[0], "inTangentType")):
                        print(f"Skipping controller {controller}: Does not support tangents (e.g., TCB).")
                        continue

                    
                    sorted_indices = sorted(indices)
                    
                    if tangent_name == 'linear':
                        
                        if len(sorted_indices) < 2:
                            
                            if sorted_indices:
                                key = controller.keys[sorted_indices[0]]
                                key.inTangentType = rt.name('linear')
                                key.outTangentType = rt.name('linear')
                            continue

                        
                        key_first = controller.keys[sorted_indices[0]]
                        key_last = controller.keys[sorted_indices[-1]]
                        
                        
                        indices_to_delete = sorted_indices[1:-1]
                        
                        if indices_to_delete:
                            
                            mxs_indices_to_delete = [i + 1 for i in indices_to_delete]
                            for mxs_index in sorted(mxs_indices_to_delete, reverse=True):
                                rt.deleteItem(controller.keys, mxs_index)
                        
                        
                        key_first.inTangentType = rt.name('linear')
                        key_first.outTangentType = rt.name('linear')
                        key_last.inTangentType = rt.name('linear')
                        key_last.outTangentType = rt.name('linear')

                    elif tangent_name == 'bezier':
                        
                        for index in sorted_indices:
                            key = controller.keys[index]
                            key.inTangentType = rt.name('custom')
                            key.outTangentType = rt.name('custom')

                    elif tangent_name == 'curve':
                        
                        for index in sorted_indices:
                            key = controller.keys[index]
                            key.inTangentType = rt.name('slow')
                            key.outTangentType = rt.name('slow')
                    
                    
                    elif tangent_name == 'smooth':
                        
                        for index in sorted_indices:
                            key = controller.keys[index]
                            key.inTangentType = rt.name('smooth')
                            key.outTangentType = rt.name('smooth')
                    
            print(f"Applied '{tangent_name}' to {len(keys_by_controller)} controller(s).")
            self._redraw_scene()

        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f"Failed to apply tangent type: {e}")

# =======================================
# # === END: CurveEditorWidget        ===
# =======================================




# =======================================
# # === START: KeyframeArea           ===
# # === (QGraphicsView)               ===
# =======================================
class KeyframeArea(QtWidgets.QGraphicsView):
    selectionChanged = QtCore.Signal(int)
    def __init__(self, timeline_widget, parent=None):
        super().__init__(parent)
        
        # GraphicsView ---
        self.scene = QtWidgets.QGraphicsScene(self)
        self.setScene(self.scene)

        self.setFrameShape(QtWidgets.QFrame.Shape.NoFrame) 
        self.setContentsMargins(0, 0, 0, 0)
        self.viewport().setContentsMargins(0, 0, 0, 0)
        self.setAlignment(QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignTop) 
        
        self.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        self.setStyleSheet("background-color: #2d2d2d; border: none;")
        
        self.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        
        self.setMouseTracking(True)
        self.setFocusPolicy(QtCore.Qt.FocusPolicy.StrongFocus)

        self.slider_item = None
        self.is_snapping = True

        self.timeline_widget = timeline_widget
        self.key_polygon = QtGui.QPolygonF([QtCore.QPointF(-4, 0), QtCore.QPointF(0, -4), QtCore.QPointF(4, 0), QtCore.QPointF(0, 4)])
        
        
        self._is_panning = False
        self._last_pan_pos = QtCore.QPoint()
        
        self.drag_mode = None
        self.drag_start_pos = None
        self.drag_start_pos_scene = QtCore.QPointF()
        self.trim_margin = 5
        self.key_click_margin = 5
        
        self.original_clip_ranges = {}
        self.original_key_times = {} 
        self.selected_keys = set()
        self.marquee_rect_item = None 
        self.panning_info = None #

        
        self.grid_pen = QtGui.QPen(QtGui.QColor("#4a4a4a")); self.grid_pen.setWidth(1)
        self.key_brush = QtGui.QBrush(QtGui.QColor("#5698d4"))
        self.selected_key_brush = QtGui.QBrush(QtGui.QColor("#d4a056"))
        self.key_pen = QtGui.QPen(QtGui.QColor("#8cceff"))
        self.slider_item = None

    def _redraw_scene(self):
        
        
        for item in self.scene.items():
            if item != self.marquee_rect_item:
                self.scene.removeItem(item)
        
        
        ruler = self.timeline_widget.ruler
        is_cache_enabled = self.timeline_widget.track_list_panel.cache_mode_btn.isChecked()
        is_mixer_mode = (self.timeline_widget.left_view_stack.currentIndex() == 1)
        
        
        view_rect = self.mapToScene(self.viewport().rect()).boundingRect()

        if is_mixer_mode:
            # ===Motion Mixer ===
            mixer_tree = self.timeline_widget.motion_mixer_panel.track_tree
            for i in range(mixer_tree.topLevelItemCount()):
                track_item = mixer_tree.topLevelItem(i)
                track_rect = mixer_tree.visualItemRect(track_item)
                
                y_bottom = track_rect.bottom()
                self.scene.addLine(view_rect.left(), y_bottom, view_rect.right(), y_bottom, self.grid_pen).setZValue(-10)

                for j in range(track_item.childCount()):
                    clip_item = track_item.child(j)
                    try:
                        start_frame = int(clip_item.text(3))
                        end_frame = int(clip_item.text(4))

                        clip_start_x = (start_frame - ruler.start_frame) * ruler.pixels_per_frame
                        clip_end_x = (end_frame - ruler.start_frame) * ruler.pixels_per_frame
                        clip_rect_f = QtCore.QRectF(clip_start_x, track_rect.top() + 2, clip_end_x - clip_start_x, track_rect.height() - 4)
                        
                        clip_brush_color = QtGui.QColor("#6D475A")
                        if clip_item.isSelected() or track_item.isSelected():
                            clip_brush_color = QtGui.QColor("#9E6984")
                        
                        clip_brush = QtGui.QBrush(clip_brush_color)
                        clip_pen = QtGui.QPen(clip_brush_color.lighter(150))
                        
                        self.scene.addRect(clip_rect_f, clip_pen, clip_brush).setZValue(1)

                        # ---Fade-in / Fade-out ---
                        crossfade_data = clip_item.data(0, self.timeline_widget.CROSSFADE_ROLE)
                        if isinstance(crossfade_data, dict):
                            # Fade In
                            if 'fade_in' in crossfade_data:
                                duration = crossfade_data['fade_in'].get('duration', 0)
                                if duration > 0:
                                    fade_width_px = duration * ruler.pixels_per_frame
                                    fade_rect = QtCore.QRectF(clip_rect_f.left(), clip_rect_f.top(), fade_width_px, clip_rect_f.height())
                                    
                                    self.scene.addRect(fade_rect, QtCore.Qt.PenStyle.NoPen, QtGui.QBrush(QtGui.QColor(0, 0, 0, 70))).setZValue(2)
                                    
                                    # --- FIX: Use QLineF ---
                                    line = QtCore.QLineF(fade_rect.topLeft(), fade_rect.bottomRight())
                                    self.scene.addLine(line, QtGui.QPen(QtGui.QColor(255, 255, 255, 150), 1)).setZValue(3)

                            # Fade Out
                            if 'fade_out' in crossfade_data:
                                duration = crossfade_data['fade_out'].get('duration', 0)
                                if duration > 0:
                                    fade_width_px = duration * ruler.pixels_per_frame
                                    fade_rect = QtCore.QRectF(clip_rect_f.right() - fade_width_px, clip_rect_f.top(), fade_width_px, clip_rect_f.height())
                                    
                                    self.scene.addRect(fade_rect, QtCore.Qt.PenStyle.NoPen, QtGui.QBrush(QtGui.QColor(0, 0, 0, 70))).setZValue(2)
                                    
                                    # --- FIX: Use QLineF ---
                                    line = QtCore.QLineF(fade_rect.topRight(), fade_rect.bottomLeft())
                                    self.scene.addLine(line, QtGui.QPen(QtGui.QColor(255, 255, 255, 150), 1)).setZValue(3)
                        
                        
                        text_item = self.scene.addText(clip_item.text(0))
                        text_item.setDefaultTextColor(QtCore.Qt.GlobalColor.white)
                        text_item.setPos(clip_rect_f.left() + 5, clip_rect_f.top() + (clip_rect_f.height() / 2) - text_item.boundingRect().height() / 2)
                        text_item.setZValue(3)
                    
                    except (ValueError, IndexError):
                        continue
        else:
            # === Track List Mode ===
            track_list_widget = self.timeline_widget.track_list_panel.track_tree
            
            
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
                        
                        
                        clip_rect_f = QtCore.QRectF(clip_start_x, rect.top() + 2, clip_end_x - clip_start_x, rect.height() - 4)
                        
                        #                   
                        base_brush = item.data(0, self.timeline_widget.VISIBILITY_ROLE)
                        if not base_brush:
                            base_brush = QtGui.QBrush(QtGui.QColor(self.timeline_widget.settings['Type_Colors'].get('geometry_color', "#475A6D")))
                        
                        if item.isSelected():
                            clip_brush = QtGui.QBrush(base_brush.color().lighter(150))
                            clip_pen = QtGui.QPen(base_brush.color().lighter(200), 2) 
                        else:
                            clip_brush = base_brush
                            clip_pen = QtGui.QPen(base_brush.color().lighter(150))
                        
                        #                   
                        clip_gitem = self.scene.addRect(clip_rect_f, clip_pen, clip_brush)
                        clip_gitem.setZValue(1)
                        clip_gitem.setData(self.timeline_widget.GRAPHICS_ITEM_KEY_ID_ROLE, item)

                # -------------------------------------------------------
                # (Track)->
                # -------------------------------------------------------
                else:
                    y_center = rect.center().y()
                    
                    try:
                        keys_to_draw = [] 

                        #(Cache)         
                        if is_cache_enabled:
                            parent_clip_item = item
                            while parent_clip_item.parent() is not None: 
                                parent_clip_item = parent_clip_item.parent()
                            
                            animation_map = parent_clip_item.data(0, self.timeline_widget.CLIP_DATA_ROLE)
                            if animation_map:
                                track_path = self._get_track_path(item)
                                track_data = animation_map.get("tracks", {}).get(track_path)
                                
                                if track_data and "keys" in track_data:
                                    for i, key_dict in enumerate(track_data["keys"]):
                                        key_frame = key_dict["time"]
                                        if ruler.start_frame <= key_frame <= ruler.end_frame:
                                            key_id = (parent_clip_item, track_path, i)
                                            keys_to_draw.append((key_frame, key_id))
                        
                        #(Live)    
                        else:
                            sub_anim = item.data(0, self.timeline_widget.SUBANIM_ROLE)
                            #             
                            if sub_anim and hasattr(sub_anim, 'controller') and sub_anim.controller:
                                controller = sub_anim.controller
                                if rt.isProperty(controller, "keys"):
                                    for idx in range(controller.keys.count):
                                        key_frame = int(controller.keys[idx].time)
                                        if ruler.start_frame <= key_frame <= ruler.end_frame:
                                            key_id = (controller, None, idx)
                                            keys_to_draw.append((key_frame, key_id))
                        
                        #              
                        for key_frame, key_id in keys_to_draw:
                            x_pos = (key_frame - ruler.start_frame) * ruler.pixels_per_frame
                            
                            is_selected = key_id in self.selected_keys
                            current_brush = self.selected_key_brush if is_selected else self.key_brush
                            
                            key_item = self.scene.addPolygon(self.key_polygon, self.key_pen, current_brush)
                            key_item.setPos(x_pos, y_center)
                            key_item.setZValue(10) 
                            
                            key_item.setData(self.timeline_widget.GRAPHICS_ITEM_KEY_ID_ROLE, key_id)
                            
                    except Exception:
                        pass

                #                       
                y_bottom = rect.bottom()
                self.scene.addLine(view_rect.left(), y_bottom, view_rect.right(), y_bottom, self.grid_pen).setZValue(-10)
                
                #                  
                iterator += 1

        
        current_frame = self.timeline_widget.current_frame
        if ruler.start_frame <= current_frame <= ruler.end_frame and ruler.pixels_per_frame > 0:            
            slider_x = int((current_frame - ruler.start_frame) * ruler.pixels_per_frame)
            slider_pen = QtGui.QPen(QtGui.QColor("#ff4747")); slider_pen.setWidth(2)
            
            
            self.slider_item = self.scene.addLine(slider_x, view_rect.top(), slider_x, view_rect.bottom(), slider_pen)
            self.slider_item.setZValue(100)
        else:
            self.slider_item = None
    
    # ==========================================
    # === mouse event handlers ================
    # ==========================================

    
    def find_keys_in_item_recursive(self, parent_item, start_f, end_f):
        
        for i in range(parent_item.childCount()):
            child_item = parent_item.child(i)
            sub_anim = child_item.data(0, self.timeline_widget.SUBANIM_ROLE)
            try:
                if hasattr(sub_anim, 'controller') and sub_anim.controller and rt.isProperty(sub_anim.controller, "keys"):
                    controller = sub_anim.controller
                    for key_index in range(controller.keys.count):
                        key = controller.keys[key_index]
                        if start_f <= key.time <= end_f:
                            
                            self.original_key_times[(controller, None, key_index)] = int(key.time)
                            self.selected_keys.add((controller, None, key_index))
            except Exception: pass
            if child_item.childCount() > 0: self.find_keys_in_item_recursive(child_item, start_f, end_f)

    
    def mouseReleaseEvent(self, event):
        
        
        if event.button() == QtCore.Qt.MouseButton.MiddleButton:
            self._is_panning = False
            self.setCursor(QtCore.Qt.CursorShape.ArrowCursor)
            event.accept()
            return

        if self.drag_mode == 'scrub_timeline':
             if not self.timeline_widget.sync_timer.isActive():
                 self.timeline_widget.sync_timer.start(50)
                 #print("DEBUG: Sync Timer RESTARTED.")
             
             self.drag_mode = None
             self.unsetCursor()
             self.timeline_widget._force_ui_refresh()
             event.accept()
             return
        
        if not self.drag_mode:
            return super().mouseReleaseEvent(event)

        print(f"\n--- DEBUG [mouseReleaseEvent] Mode: {self.drag_mode} --- ")
        
        
        is_cache_enabled = self.timeline_widget.track_list_panel.cache_mode_btn.isChecked()
        
        
        if self.drag_mode == 'marquee_select' and self.marquee_rect_item:
            marquee_scene_rect = self.marquee_rect_item.rect()
            
            
            track_list_widget = self.timeline_widget.track_list_panel.track_tree
            iterator = QtWidgets.QTreeWidgetItemIterator(track_list_widget, QtWidgets.QTreeWidgetItemIterator.IteratorFlag.NotHidden)
            
            while iterator.value():
                item = iterator.value()
                rect = track_list_widget.visualItemRect(item)
                y_center = rect.center().y()
                
                
                if marquee_scene_rect.top() <= y_center <= marquee_scene_rect.bottom():
                    
                    if is_cache_enabled:
                        
                        if item.parent() is None: 
                            iterator += 1
                            continue
                        
                        
                        parent_clip_item = item
                        while parent_clip_item.parent() is not None: parent_clip_item = parent_clip_item.parent()
                        
                        animation_map = parent_clip_item.data(0, self.timeline_widget.CLIP_DATA_ROLE)
                        if not animation_map:
                            iterator += 1
                            continue
                        
                        track_path = self._get_track_path(item)
                        track_data = animation_map.get("tracks", {}).get(track_path)

                        #
                        if track_data and "keys" in track_data:
                            for i, key_dict in enumerate(track_data["keys"]):
                                key_x = (key_dict["time"] - self.timeline_widget.ruler.start_frame) * self.timeline_widget.ruler.pixels_per_frame
                                
                                if marquee_scene_rect.left() <= key_x <= marquee_scene_rect.right():
                                    
                                    self.selected_keys.add((parent_clip_item, track_path, i))
                    
                    else:
                        
                        sub_anim = item.data(0, self.timeline_widget.SUBANIM_ROLE)
                        try:
                            if hasattr(sub_anim, 'controller') and sub_anim.controller and rt.isProperty(sub_anim.controller, "keys"):
                                for i in range(sub_anim.controller.keys.count):
                                    key = sub_anim.controller.keys[i]
                                    key_x = (int(key.time) - self.timeline_widget.ruler.start_frame) * self.timeline_widget.ruler.pixels_per_frame
                                    if marquee_scene_rect.left() <= key_x <= marquee_scene_rect.right():
                                        
                                        self.selected_keys.add((sub_anim.controller, None, i))
                        except Exception: pass
                
                iterator += 1
            

            self.selectionChanged.emit(len(self.selected_keys)) 
            self.scene.removeItem(self.marquee_rect_item)
            self.marquee_rect_item = None
            self._select_keys_in_max()
        
        
        elif self.drag_mode in ['move_key', 'move', 'trim_start', 'trim_end', 'scale_start', 'scale_end', 'move_mixer_clip']:
            
            try:
                with pymxs.undo(True, f"Timeline Edit: {self.drag_mode}"):
                    if self.drag_mode == 'move_key' and is_cache_enabled and self.selected_keys:
                         for p_clip, t_path, k_idx in self.selected_keys:
                            anim_map = p_clip.data(0, self.timeline_widget.CLIP_DATA_ROLE)
                            track_data = anim_map['tracks'][t_path]
                            
                            
                            if 'controller_ref' in track_data:
                                controller = track_data['controller_ref'] 
                                final_time = track_data['keys'][k_idx]['time']
                                controller.keys[k_idx].time = final_time
                            else:
                                
                                
                                pass 
                
                if self.drag_mode not in ['move_key', 'move_mixer_clip']: 
                    self.timeline_widget._save_timeline_state()
            except Exception as e:
                print(f"Error on mouse release: {e}")
        
        
        self.drag_mode = None
        self.drag_start_pos = None
        self.original_key_times.clear()
        self.original_clip_ranges.clear()
        self.unsetCursor()
        self._redraw_scene()
        super().mouseReleaseEvent(event)
        
    def wheelEvent(self, event):
        active_tree_scrollbar = self.timeline_widget._get_active_tree_widget().verticalScrollBar()

        
        if event.modifiers() == QtCore.Qt.KeyboardModifier.NoModifier:
            active_tree_scrollbar = self.timeline_widget._get_active_tree_widget().verticalScrollBar()
            delta = event.angleDelta().y()
            num_steps = - (delta / 120.0 * 3.0)
            step_size = active_tree_scrollbar.singleStep()            
            new_value = active_tree_scrollbar.value() + int(num_steps * step_size)
            active_tree_scrollbar.setValue(new_value)            
            event.accept()
            return
            
        
        elif event.modifiers() == QtCore.Qt.KeyboardModifier.ShiftModifier:
            delta = event.angleDelta().y()
            delta_frames = delta / 12.0 
            new_start = rt.animationRange.start - delta_frames 
            new_end = rt.animationRange.end - delta_frames 
            rt.animationRange = rt.interval(int(new_start), int(new_end))
            event.accept()

        
        elif event.modifiers() == QtCore.Qt.KeyboardModifier.ControlModifier:
            zoom_factor = 1.15
            
            
            center_x_scene = self.mapToScene(event.pos()).x()
            center_frame = self._x_to_frame(center_x_scene)
            
            current_duration = max(1.0, float(rt.animationRange.end - rt.animationRange.start))
            
            if event.angleDelta().y() > 0:
                new_duration = current_duration / zoom_factor
            else:
                new_duration = current_duration * zoom_factor
            
           
            alpha = (center_frame - rt.animationRange.start) / current_duration if current_duration > 0 else 0.5
            new_start = center_frame - (new_duration * alpha)
            new_end = new_start + new_duration
            
            
            rt.animationRange = rt.interval(int(new_start), int(new_end))
            
            if isinstance(self, CurveEditorWidget):
                
                center_y_scene = self.mapToScene(event.pos()).y()
                
                
                current_v_scale = self.transform().m22()
                if event.angleDelta().y() > 0:
                    new_v_scale = current_v_scale * zoom_factor
                else:
                    new_v_scale = current_v_scale / zoom_factor

                
                self.centerOn(center_x_scene, center_y_scene)
                transform = self.transform()
                transform.scale(1.0, zoom_factor if event.angleDelta().y() > 0 else 1.0/zoom_factor)
                self.setTransform(transform)

            event.accept()
            
        else:
            event.ignore()


    def mouseMoveEvent(self, event):
        
        if self._is_panning:
            current_pos = event.pos()
            delta = current_pos - self._last_pan_pos
            delta_x_pixels = delta.x()
            
            
            if self.timeline_widget.ruler.pixels_per_frame > 0:
                delta_frames = delta_x_pixels / self.timeline_widget.ruler.pixels_per_frame
                new_start = rt.animationRange.start - delta_frames
                new_end = rt.animationRange.end - delta_frames
                rt.animationRange = rt.interval(int(new_start), int(new_end))

            delta_y = delta.y()
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - delta_y) 
            self._last_pan_pos = current_pos
            event.accept()
            return

        
        if self.drag_mode == 'scrub_timeline':
            
            scene_pos = self.mapToScene(event.pos())
            new_frame = self._x_to_frame(scene_pos.x())
            new_frame_int = int(new_frame)

            
            pymxs.runtime.sliderTime = new_frame_int
            self.timeline_widget.current_frame = new_frame_int
            
            
            self.timeline_widget.ruler.update()

            
            if self.slider_item:
                ruler = self.timeline_widget.ruler
                new_x = int((new_frame_int - ruler.start_frame) * ruler.pixels_per_frame)
                
                
                line = self.slider_item.line()
                
                line.setLine(new_x, line.y1(), new_x, line.y2())
                self.slider_item.setLine(line)
            else:
                
                self._redraw_scene()
            
            
            #print(f"Scrubbing: Target={new_frame_int} | MaxIsNow={pymxs.runtime.sliderTime}")

            #self.timeline_widget.ruler.update()
            #self._redraw_scene() 
            event.accept()
            return

        
        if self.drag_mode == 'marquee_select':
            current_pos_scene = self.mapToScene(event.pos())
            if self.marquee_rect_item and self.drag_start_pos_scene:
                 rect = QtCore.QRectF(self.drag_start_pos_scene, current_pos_scene).normalized()
                 self.marquee_rect_item.setRect(rect)
            event.accept()
            return

        
        if not self.drag_mode:
            ruler = self.timeline_widget.ruler
            current_frame = self.timeline_widget.current_frame
            slider_scene_x = (current_frame - ruler.start_frame) * ruler.pixels_per_frame
            slider_view_x = self.mapFromScene(QtCore.QPointF(slider_scene_x, 0)).x()
            
            
            handle_rect = QtCore.QRectF(slider_view_x - 10, 0, 20, self.height())
            
            if handle_rect.contains(QtCore.QPointF(event.pos())):
                self.setCursor(QtCore.Qt.CursorShape.SizeHorCursor)
            else:
                self.unsetCursor()          
            
            return 

        
        if self.drag_start_pos is None:
            return

        ruler = self.timeline_widget.ruler
        if ruler.pixels_per_frame <= 0: return

        
        #delta_frames = round((event.pos().x() - self.drag_start_pos.x()) / ruler.pixels_per_frame)
        raw_delta = (event.pos().x() - self.drag_start_pos.x()) / ruler.pixels_per_frame
        
        if self.is_snapping:
            delta_frames = round(raw_delta) 
        else:
            delta_frames = raw_delta
        
        
        if self.drag_mode == 'move_mixer_clip':
             for item, (orig_start, orig_end) in self.original_clip_ranges.items():
                duration = orig_end - orig_start
                new_start = orig_start + delta_frames
                item.setText(3, str(new_start))
                item.setText(4, str(new_start + duration))
        
        elif self.drag_mode == 'move_key':
            is_cache_enabled = self.timeline_widget.track_list_panel.cache_mode_btn.isChecked()
            for key_id, original_time in self.original_key_times.items():
                p_clip_or_controller, track_path, key_index = key_id
                new_time = original_time + delta_frames
                if is_cache_enabled:
                    try:
                        anim_map = p_clip_or_controller.data(0, self.timeline_widget.CLIP_DATA_ROLE)
                        anim_map['tracks'][track_path]['keys'][key_index]['time'] = new_time
                    except: pass
                else:
                    try: p_clip_or_controller.keys[key_index].time = new_time
                    except Exception: pass
        
        elif self.drag_mode == 'move':
            for item, (orig_start, orig_end) in self.original_clip_ranges.items():
                item.setData(0, self.timeline_widget.CLIP_START_ROLE, orig_start + delta_frames)
                item.setData(0, self.timeline_widget.CLIP_END_ROLE, orig_end + delta_frames)
            try:
                for (controller, _, index), original_time in self.original_key_times.items():
                    controller.keys[index].time = original_time + delta_frames
            except Exception as e: pass

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
                
                for (controller, _, index), original_time in self.original_key_times.items():
                    try:
                        distance_from_pivot = original_time - pivot_frame
                        new_time = pivot_frame + (distance_from_pivot * scale_factor)
                        controller.keys[index].time = new_time
                    except Exception as e: pass

        self._redraw_scene()
        event.accept()
        super().mouseMoveEvent(event)

    def mousePressEvent(self, event):          
            
            
            if event.button() == QtCore.Qt.MouseButton.MiddleButton:
                self._is_panning = True
                self._last_pan_pos = event.pos()
                self.setCursor(QtCore.Qt.CursorShape.ClosedHandCursor)
                event.accept()
                return
                
            if event.button() == QtCore.Qt.MouseButton.LeftButton:
                ruler = self.timeline_widget.ruler
                current_frame = self.timeline_widget.current_frame
                
                
                slider_scene_x = (current_frame - ruler.start_frame) * ruler.pixels_per_frame
                slider_view_x = self.mapFromScene(QtCore.QPointF(slider_scene_x, 0)).x()
                handle_rect = QtCore.QRectF(slider_view_x - 10, 0, 20, self.height())
                
                
                if handle_rect.contains(QtCore.QPointF(event.pos())):
                    self.drag_mode = 'scrub_timeline'
                    self.setCursor(QtCore.Qt.CursorShape.SizeHorCursor)
                    
                    
                    if self.timeline_widget.sync_timer.isActive():
                        self.timeline_widget.sync_timer.stop()
                        #print("DEBUG: Sync Timer STOPPED forcefully.")
                    
                    event.accept()
                    return 

                
                self.drag_start_pos = event.pos()
                
            super().mousePressEvent(event)
            
            item_under_cursor_tree = self._item_at(event.pos().y())
            x_pos_scene = self.mapToScene(event.pos()).x()
            
            is_cache_enabled = self.timeline_widget.track_list_panel.cache_mode_btn.isChecked()
            modifiers = event.modifiers()
            is_mixer_mode = (self.timeline_widget.left_view_stack.currentIndex() == 1)
            
            if is_mixer_mode:
                
                mixer_tree = self.timeline_widget.motion_mixer_panel.track_tree
                if item_under_cursor_tree and item_under_cursor_tree.parent() is not None: 
                    self.drag_mode = 'move_mixer_clip'
                    self.drag_start_pos = event.pos()
                    self.original_clip_ranges.clear()
                    try:
                        start_frame = int(item_under_cursor_tree.text(3))
                        end_frame = int(item_under_cursor_tree.text(4))
                        self.original_clip_ranges[item_under_cursor_tree] = (start_frame, end_frame)
                    except (ValueError, IndexError):
                        self.drag_mode = None; return
                    mixer_tree.setCurrentItem(item_under_cursor_tree)
                    self.setCursor(QtCore.Qt.CursorShape.OpenHandCursor)
                    self._redraw_scene()
                return
            
            tree_widget = self.timeline_widget.track_list_panel.track_tree
            
            
            p_clip_or_controller, track_path, key_index = self._key_at(item_under_cursor_tree, x_pos_scene)
            
            if p_clip_or_controller and key_index is not None:
                
                self.drag_mode = 'move_key'
                self.drag_start_pos = event.pos() 
                key_id = (p_clip_or_controller, track_path, key_index)
                is_key_already_selected = key_id in self.selected_keys
                
                if not is_key_already_selected:
                    if modifiers != QtCore.Qt.KeyboardModifier.ControlModifier:
                        self.selected_keys.clear()
                    self.selected_keys.add(key_id)
                elif modifiers == QtCore.Qt.KeyboardModifier.ControlModifier and is_key_already_selected:
                    self.selected_keys.remove(key_id)
                    self.drag_mode = None
                    self._redraw_scene(); 
                    self.selectionChanged.emit(len(self.selected_keys))
                    return

                self.selectionChanged.emit(len(self.selected_keys))    
                self.original_key_times.clear()
                for id_part1, id_part2, id_part3 in self.selected_keys:
                    try:
                        if is_cache_enabled:
                            anim_map = id_part1.data(0, self.timeline_widget.CLIP_DATA_ROLE)
                            self.original_key_times[(id_part1, id_part2, id_part3)] = anim_map['tracks'][id_part2]['keys'][id_part3]['time']
                        else:
                            self.original_key_times[(id_part1, id_part2, id_part3)] = int(id_part1.keys[id_part3].time)
                    except (KeyError, IndexError, AttributeError): pass
                
                self.setCursor(QtCore.Qt.CursorShape.SizeHorCursor)
                self._redraw_scene()
                return

            
            if item_under_cursor_tree and item_under_cursor_tree.parent() is None:
                tree_widget.setCurrentItem(item_under_cursor_tree)
                
                self.drag_start_pos = event.pos() 
                self.original_clip_ranges.clear()
                for item in tree_widget.selectedItems():
                    if item.parent() is None:
                        start, end = item.data(0, self.timeline_widget.CLIP_START_ROLE), item.data(0, self.timeline_widget.CLIP_END_ROLE)
                        if start is not None: self.original_clip_ranges[item] = (start, end)
                
                start_frame, end_frame = self.original_clip_ranges.get(item_under_cursor_tree, (None, None))
                
                
                if start_frame is not None:
                    ruler = self.timeline_widget.ruler
                    clip_start_x = (start_frame - ruler.start_frame) * ruler.pixels_per_frame
                    clip_end_x = (end_frame - ruler.start_frame) * ruler.pixels_per_frame
                    x_pos = self.mapToScene(event.pos()).x()

                    self.drag_mode = None 
                    on_start_edge = abs(x_pos - clip_start_x) < self.trim_margin
                    on_end_edge = abs(x_pos - clip_end_x) < self.trim_margin

                    if modifiers == QtCore.Qt.KeyboardModifier.AltModifier and (on_start_edge or on_end_edge):
                        self.drag_mode = 'scale_start' if on_start_edge else 'scale_end'
                    elif on_start_edge: 
                        self.drag_mode = 'trim_start'
                    elif on_end_edge: 
                        self.drag_mode = 'trim_end'
                    elif clip_start_x < x_pos < clip_end_x: 
                        self.drag_mode = 'move'
                    
                    
                    if self.drag_mode is not None:
                        if self.drag_mode in ['move', 'scale_start', 'scale_end']:
                            self.original_key_times.clear()
                            self.selected_keys.clear()
                            for item in tree_widget.selectedItems():
                                if item.parent() is None:
                                    clip_range = self.original_clip_ranges.get(item)
                                    if clip_range: self.find_keys_in_item_recursive(item, clip_range[0], clip_range[1])
                        
                        
                        self.setCursor(QtCore.Qt.CursorShape.SizeHorCursor if 'trim' in self.drag_mode or 'scale' in self.drag_mode else QtCore.Qt.CursorShape.OpenHandCursor)
                        self._redraw_scene()
                        return 
                
                

            # --- (Marquee) ---
            
            self.drag_mode = 'marquee_select'
            self.drag_start_pos_scene = self.mapToScene(event.pos())
            if not modifiers == QtCore.Qt.KeyboardModifier.ControlModifier: 
                self.selected_keys.clear()

            self.selectionChanged.emit(len(self.selected_keys))

            if self.marquee_rect_item: self.scene.removeItem(self.marquee_rect_item)
            marquee_pen = QtGui.QPen(QtGui.QColor(180, 180, 220, 200), 1, QtCore.Qt.PenStyle.DashLine)
            marquee_brush = QtGui.QBrush(QtGui.QColor(100, 100, 150, 40))
            self.marquee_rect_item = self.scene.addRect(QtCore.QRectF(self.drag_start_pos_scene, self.drag_start_pos_scene), marquee_pen, marquee_brush)
            self.marquee_rect_item.setZValue(99)
            
            self._redraw_scene()
            super().mousePressEvent(event)


    # ==========================================
    # === Helper functions and other classes ===
    # ==========================================
    
    def update(self):        
        self._redraw_scene()

    def _item_at(self, y_pos):
        
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
        
        if not item:
            return None, None, None

        is_cache_enabled = self.timeline_widget.track_list_panel.cache_mode_btn.isChecked()
        ruler = self.timeline_widget.ruler

        if is_cache_enabled:
            if item.parent() is None:
                return None, None, None
            
            parent_clip_item = item
            while parent_clip_item.parent() is not None:
                parent_clip_item = parent_clip_item.parent()
            
            animation_map = parent_clip_item.data(0, self.timeline_widget.CLIP_DATA_ROLE)
            if not animation_map:
                return None, None, None

            track_path = self._get_track_path(item)
            track_data = animation_map.get("tracks", {}).get(track_path)

            if track_data and "keys" in track_data:
                for i, key_dict in enumerate(track_data["keys"]):
                    key_x_pos = (key_dict["time"] - ruler.start_frame) * ruler.pixels_per_frame
                    if abs(x_pos - key_x_pos) <= self.key_click_margin:
                        return parent_clip_item, track_path, i
            
            return None, None, None
        
        else:
            sub_anim = item.data(0, self.timeline_widget.SUBANIM_ROLE)
            try:
                if hasattr(sub_anim, 'controller') and sub_anim.controller and rt.isProperty(sub_anim.controller, "keys"):
                    controller = sub_anim.controller
                    for i in range(controller.keys.count):
                        key = controller.keys[i]
                        key_x_pos = (int(key.time) - ruler.start_frame) * ruler.pixels_per_frame
                        if abs(x_pos - key_x_pos) <= self.key_click_margin:
                            return controller, None, i
            except Exception:
                pass
            
            return None, None, None

    def _select_keys_in_max(self):
        """Copy selected keys to the clipboard."""
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

    def fit_selected(self):
        
        if not self.selected_keys: return

        min_t, max_t = float('inf'), float('-inf')
        
        
        is_cache_enabled = self.timeline_widget.track_list_panel.cache_mode_btn.isChecked()
        
        found_any = False
        for key_id in self.selected_keys:
            
            try:
                obj, track_path, idx = key_id
                time_val = 0
                
                if is_cache_enabled:
                    anim_map = obj.data(0, self.timeline_widget.CLIP_DATA_ROLE)
                    time_val = float(anim_map['tracks'][track_path]['keys'][idx]['time'])
                else:
                    
                    time_val = float(obj.keys[idx].time)
                
                if time_val < min_t: min_t = time_val
                if time_val > max_t: max_t = time_val
                found_any = True
            except Exception: pass

        if not found_any or min_t == float('inf'): return

        
        margin = max(5, (max_t - min_t) * 0.2)
        
        
        if min_t == max_t:
            margin = 10

        new_start = int(min_t - margin)
        new_end = int(max_t + margin)

        
        pymxs.runtime.animationRange = pymxs.runtime.interval(new_start, new_end)
        
        
        self.timeline_widget.ruler.update_range()
        self._redraw_scene()
        print(f"Focused Timeline: {new_start} to {new_end}")

    #def keyPressEvent(self, event):
        
        #if event.key() == QtCore.Qt.Key.Key_Delete: 
            
            #self.delete_selected_keys()
        #else: 
            #super().keyPressEvent(event)

    def keyPressEvent(self, event):
        
        if event.key() == QtCore.Qt.Key.Key_F:
            self.fit_selected() 
            event.accept()
            
        
        elif event.key() == QtCore.Qt.Key.Key_Delete: 
            self.delete_selected_keys() 
            event.accept()
            
        
        else:
            super().keyPressEvent(event)
            
    
    def _x_to_frame(self, x_pos):
        """contextMenuEvent)"""
        if self.timeline_widget.ruler.pixels_per_frame <= 0: return 0
        return self.timeline_widget.ruler.start_frame + (x_pos / self.timeline_widget.ruler.pixels_per_frame)

    def contextMenuEvent(self, event):
        """Click right mouse button to show context menu."""
        event.accept()
        is_mixer_mode = (self.timeline_widget.left_view_stack.currentIndex() == 1)
        
        item_under_cursor_tree = self._item_at(event.pos().y())
        
        if is_mixer_mode:
            if not item_under_cursor_tree or item_under_cursor_tree.parent() is None:
                return 
            
            item = item_under_cursor_tree
            menu = QtWidgets.QMenu(self)

            loop_action = menu.addAction("Set Loop Count...")
            loop_action.triggered.connect(lambda: self.timeline_widget.logic.set_clip_loop_count(item))
            
            menu.addSeparator()

            
            
            # Fade In
            fade_in_action = menu.addAction("Fade In...")
            fade_in_action.triggered.connect(lambda: self.timeline_widget.logic.setup_crossfade_for_clip(item, 'in'))
            
            # Fade Out
            fade_out_action = menu.addAction("Fade Out...")
            fade_out_action.triggered.connect(lambda: self.timeline_widget.logic.setup_crossfade_for_clip(item, 'out'))
            
            # =================================

            if menu.isEmpty(): return
            menu.exec(event.globalPos())
            
        else: 
            # Track List
            if item_under_cursor_tree and item_under_cursor_tree.parent() is None:
                
                menu = QtWidgets.QMenu(self)
                export_action = menu.addAction("Export Animation as .clip")
                export_action.triggered.connect(lambda: self.timeline_widget._export_clip_to_file(item_under_cursor_tree))
                menu.exec_(event.globalPos())
                return

            
            x_pos_scene = self.mapToScene(event.pos()).x()
            p_clip_or_controller, track_path, key_index = self._key_at(item_under_cursor_tree, x_pos_scene) if item_under_cursor_tree else (None, None, None)
            
            if p_clip_or_controller and key_index is not None:
                key_id = (p_clip_or_controller, track_path, key_index)
                if key_id not in self.selected_keys:
                    self.selected_keys.clear()
                    self.selected_keys.add(key_id)
                    self._redraw_scene()
                    
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

    def apply_ease_to_selection(self, ease_type_name):
        """ Apply Easing to Selected Keys. """
        if not self.selected_keys: return
        is_cache_enabled = self.timeline_widget.track_list_panel.cache_mode_btn.isChecked()
        if is_cache_enabled:
            print("Easing cannot be applied in Cache Mode yet.")
            return
            
        key_objects = [c.keys[i] for c, _track_path, i in self.selected_keys if not is_cache_enabled]
        EasingManager.apply_ease_to_keys(key_objects, ease_type_name)
        self._redraw_scene()

    def delete_selected_keys(self):
        """Delete Selected Keys."""
        if not self.selected_keys: return
        
        is_cache_enabled = self.timeline_widget.track_list_panel.cache_mode_btn.isChecked()
        keys_by_controller_or_clip = {}
        
        if is_cache_enabled:
            for p_clip, t_path, k_idx in self.selected_keys:
                clip_id = id(p_clip)
                if clip_id not in keys_by_controller_or_clip:
                    keys_by_controller_or_clip[clip_id] = {'clip': p_clip, 'paths': {}}
                if t_path not in keys_by_controller_or_clip[clip_id]['paths']:
                    keys_by_controller_or_clip[clip_id]['paths'][t_path] = []
                keys_by_controller_or_clip[clip_id]['paths'][t_path].append(k_idx)
        else:
            for controller, _track_path, index in self.selected_keys:
                if controller not in keys_by_controller_or_clip: 
                    keys_by_controller_or_clip[controller] = []
                keys_by_controller_or_clip[controller].append(index)
                
        try:
            with pymxs.undo(True, "Delete Selected Keys"):
                if is_cache_enabled:
                    for data in keys_by_controller_or_clip.values():
                        anim_map = data['clip'].data(0, self.timeline_widget.CLIP_DATA_ROLE)
                        for t_path, indices in data['paths'].items():
                            track_data = anim_map['tracks'][t_path]
                            controller = track_data['controller_ref']
                            for index in sorted(indices, reverse=True):
                                del track_data['keys'][index]
                                rt.deleteItem(controller.keys, index + 1)
                else:
                    for controller, indices in keys_by_controller_or_clip.items():
                        for index in sorted(indices, reverse=True):
                            rt.deleteItem(controller.keys, index + 1)
                            
            self.selected_keys.clear()
            self.selectionChanged.emit(0)
            self._redraw_scene()
            self.timeline_widget._force_ui_refresh()
        except Exception as e: 
            print(f"Error during deletion: {e}")
   

    def _get_key_properties(self, mxs_key):
        """New Key helper function to get key properties."""
        props = {}
        
        for prop_name in ['time', 'value', 'inTangent', 'outTangent', 'inTangentType', 'outTangentType', 'inTangentLength', 'outTangentLength']:
            if rt.isProperty(mxs_key, prop_name):
                val = getattr(mxs_key, prop_name)
                
                prop_class = rt.classOf(val)

                
                prop_class_str = str(prop_class)
                
                
                if prop_class_str in ['Point3', 'Quat', 'Point4', 'Color', 'RGBA', 'FRGBA', 'EulerAngles']:
                    props[prop_name] = [float(v) for v in val]
                
                
                elif prop_class == rt.Name:
                    props[prop_name] = str(val) # e.g., 'linear'
                else:
                    props[prop_name] = float(val) if isinstance(val, (int, float)) else str(val)
        return props

    def _set_key_properties(self, mxs_key, key_data):
        """Key helper function to set key properties."""
        
        for prop_name, py_val in key_data.items():
            if prop_name == 'time' or not rt.isProperty(mxs_key, prop_name):
                continue
            
            try:
                
                mxs_val = None
                if isinstance(py_val, list):
                    if len(py_val) == 3: mxs_val = rt.Point3(*py_val)
                    elif len(py_val) == 4: mxs_val = rt.Quat(*py_val)
                elif isinstance(py_val, str) and "rt.name" in str(rt.classOf(getattr(mxs_key, prop_name))):
                     mxs_val = rt.name(py_val)
                
                if mxs_val is None:
                    mxs_val = py_val 
                    
                setattr(mxs_key, prop_name, mxs_val)
            except Exception as e:
                print(f"Warn: Could not set key property '{prop_name}': {e}")

    def copy_selected_keys(self):
        """ Copy selected keys to the clipboard. """
        clipboard_data = []
        try:
            if not self.selected_keys:
                print("No keys selected to copy.")
                return

            is_cache_enabled = self.timeline_widget.track_list_panel.cache_mode_btn.isChecked()
            reference_time = float('inf')

            
            temp_ref_time = float('inf')
            for key_id in self.selected_keys:
                try:
                    p_clip_or_controller, track_path, key_index = key_id
                    
                    
                    current_time_val = 0.0 
                    if is_cache_enabled:
                        anim_map = p_clip_or_controller.data(0, self.timeline_widget.CLIP_DATA_ROLE)
                        current_time_val = float(anim_map['tracks'][track_path]['keys'][key_index]['time'])
                    else:
                        
                        current_time_val = float(p_clip_or_controller.keys[key_index].time)
                    
                    
                    temp_ref_time = min(temp_ref_time, current_time_val)
                    
                    
                except Exception as e:
                    print(f"Warn: Could not read time for key {key_id}: {e}")
                    continue
            
            reference_time = temp_ref_time
            if reference_time == float('inf'):
                print("Error: Could not determine reference time for copy.")
                return

            
            for key_id in self.selected_keys:
                try:
                    p_clip_or_controller, track_path, key_index = key_id
                    controller_obj = None
                    key_dict = {}
                    
                    
                    current_time_val = 0.0
                    if is_cache_enabled:
                        anim_map = p_clip_or_controller.data(0, self.timeline_widget.CLIP_DATA_ROLE)
                        track_data = anim_map['tracks'][track_path]
                        key_dict = track_data['keys'][key_index].copy()
                        current_time_val = float(key_dict['time'])
                        controller_obj = track_data.get('controller_ref') 
                    else:
                        controller_obj = p_clip_or_controller
                        mxs_key = controller_obj.keys[key_index]
                        key_dict = self._get_key_properties(mxs_key)
                        current_time_val = float(mxs_key.time) 
                    
                    if controller_obj:
                        clipboard_data.append({
                            "controller": controller_obj, 
                            "key_data": key_dict, 
                            "relative_time": current_time_val - reference_time 
                        })
                    
                    
                except Exception as e:
                    print(f"Warn: Could not copy key data for {key_id}: {e}")
                    continue
        
        finally:
            self.timeline_widget._internal_clipboard = clipboard_data
            self.timeline_widget.update_edit_button_states()
            print(f"Copied {len(clipboard_data)} keys to clipboard.")


    def cut_selected_keys(self):
        """Cut selected keys."""
        self.copy_selected_keys()
        self.delete_selected_keys()

    def paste_keys(self):
        """Patse keys from clipboard."""
        clipboard_data = self.timeline_widget._internal_clipboard
        if not clipboard_data:
            print("Clipboard is empty.")
            return

        is_cache_enabled = self.timeline_widget.track_list_panel.cache_mode_btn.isChecked()
        if is_cache_enabled:
            QtWidgets.QMessageBox.warning(self, "Paste Error", 
                "Pasting keys is disabled while Cache Mode is active.\n\n"
                "Please deactivate cache mode to paste keys.")
            return

        paste_time = self.timeline_widget.current_frame
        newly_created_key_ids = [] 

        try:
            with pymxs.undo(True, "Paste Keys"):
                for item in clipboard_data:
                    controller = item['controller']
                    key_data = item['key_data']
                    relative_time = item['relative_time']
                    new_key_time = paste_time + relative_time
                    
                    
                    new_key = rt.addNewKey(controller, new_key_time)
                    
                    self._set_key_properties(new_key, key_data)
                    
                    
                    new_key_index = -1
                    for i in range(controller.keys.count):
                         if controller.keys[i] == new_key:
                             new_key_index = i
                             break
                    if new_key_index != -1:
                         newly_created_key_ids.append((controller, None, new_key_index))

            print(f"Pasted {len(clipboard_data)} keys.")
            self.selected_keys.clear()
            self.selected_keys.update(newly_created_key_ids)
            self.selectionChanged.emit(len(self.selected_keys)) 
            self._redraw_scene()
            self.timeline_widget._force_ui_refresh()

        except Exception as e:
            print(f"Error during paste: {e}")


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
    CLIP_MODE_ROLE = QtCore.Qt.ItemDataRole.UserRole + 10
    GRAPHICS_ITEM_KEY_ID_ROLE = QtCore.Qt.ItemDataRole.UserRole + 11
    CLIP_LOOP_ROLE = QtCore.Qt.ItemDataRole.UserRole + 12

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
        self._internal_clipboard = None
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
        
        self.icon_trim_clip = QtGui.QIcon(os.path.join(SCRIPT_PATH, 'icons', 'TrimClips.png').replace('\\', '/'))
        self.icon_split_clip = QtGui.QIcon(os.path.join(SCRIPT_PATH, 'icons', 'SplitClips.png').replace('\\', '/'))
        self.icon_copy = QtGui.QIcon(os.path.join(SCRIPT_PATH, 'icons', 'Copykey.png').replace('\\', '/'))
        self.icon_cut = QtGui.QIcon(os.path.join(SCRIPT_PATH, 'icons', 'Cutkey.png').replace('\\', '/'))
        self.icon_delete = QtGui.QIcon(os.path.join(SCRIPT_PATH, 'icons', 'Deletekey.png').replace('\\', '/'))
        self.icon_paste = QtGui.QIcon(os.path.join(SCRIPT_PATH, 'icons', 'pastkey.png').replace('\\', '/'))
        self.icon_curve = QtGui.QIcon(os.path.join(SCRIPT_PATH, 'icons', 'Curve.png').replace('\\', '/'))
        self.icon_linear = QtGui.QIcon(os.path.join(SCRIPT_PATH, 'icons', 'Linear.png').replace('\\', '/'))
        self.icon_bezier = QtGui.QIcon(os.path.join(SCRIPT_PATH, 'icons', 'Bezier.png').replace('\\', '/'))
        self.icon_smooth = QtGui.QIcon(os.path.join(SCRIPT_PATH, 'icons', 'Smooth.png').replace('\\', '/'))

        self.icon_snap = QtGui.QIcon(os.path.join(SCRIPT_PATH, 'icons', 'SnapFrames.png').replace('\\', '/'))
        
        

        self.icon_track_transform = QtGui.QIcon(os.path.join(SCRIPT_PATH, 'icons', 'Transform.png').replace('\\', '/'))
        self.icon_track_position = QtGui.QIcon(os.path.join(SCRIPT_PATH, 'icons', 'position.png').replace('\\', '/'))
        self.icon_track_rotation = QtGui.QIcon(os.path.join(SCRIPT_PATH, 'icons', 'rotate.png').replace('\\', '/'))
        self.icon_track_scale = QtGui.QIcon(os.path.join(SCRIPT_PATH, 'icons', 'scale.png').replace('\\', '/'))

        self.icon_obj_light = QtGui.QIcon(os.path.join(SCRIPT_PATH, 'icons', 'Lights.png').replace('\\', '/'))
        self.icon_obj_geometry = QtGui.QIcon(os.path.join(SCRIPT_PATH, 'icons', 'Geometry.png').replace('\\', '/'))
        self.icon_obj_camera = QtGui.QIcon(os.path.join(SCRIPT_PATH, 'icons', 'Cameras.png').replace('\\', '/'))
        self.icon_obj_particle = QtGui.QIcon(os.path.join(SCRIPT_PATH, 'icons', 'ParticleSystems.png').replace('\\', '/'))
        self.icon_obj_bone = QtGui.QIcon(os.path.join(SCRIPT_PATH, 'icons', 'Bones.png').replace('\\', '/'))
        self.icon_obj_shape = QtGui.QIcon(os.path.join(SCRIPT_PATH, 'icons', 'Shapes.png').replace('\\', '/'))
        self.icon_obj_helper = QtGui.QIcon(os.path.join(SCRIPT_PATH, 'icons', 'Helpers.png').replace('\\', '/'))
        self.icon_obj_spacewarp = QtGui.QIcon(os.path.join(SCRIPT_PATH, 'icons', 'SpaceWarps.png').replace('\\', '/'))
        self.icon_obj_tyflow = QtGui.QIcon(os.path.join(SCRIPT_PATH, 'icons', 'tyFlow.png').replace('\\', '/'))

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
        splitter.addWidget(left_panel)
        
        right_panel = QtWidgets.QWidget()
        right_layout = QtWidgets.QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)

        
        right_toolbar = QtWidgets.QToolBar("Timeline Tools")
        right_toolbar.setIconSize(QtCore.QSize(32, 32))
        
        
        
        
        
        
        self.action_trim_clip = QtGui.QAction(self.icon_trim_clip, "Trim Clip At Playhead", self)
        self.action_trim_clip.setToolTip("Trims the end of the selected clip(s) to the current time.")
        self.action_trim_clip.triggered.connect(self.trim_selected_clip_to_current_frame) 

        
        self.action_split_clip = QtGui.QAction(self.icon_split_clip, "Split Clip At Playhead", self)
        self.action_split_clip.setToolTip("Splits the selected clip(s) into two at the current time.")
        self.action_split_clip.triggered.connect(self.split_selected_clips_at_current_frame)

        
        self.action_copy = QtGui.QAction(self.icon_copy, "Copy Keys", self)
        self.action_cut = QtGui.QAction(self.icon_cut, "Cut Keys", self)
        self.action_delete = QtGui.QAction(self.icon_delete, "Delete Keys", self)
        self.action_paste = QtGui.QAction(self.icon_paste, "Paste Keys", self)
        
        
        self.action_curve = QtGui.QAction(self.icon_curve, "Curve", self)
        self.action_linear = QtGui.QAction(self.icon_linear, "Linear", self)
        self.action_bezier = QtGui.QAction(self.icon_bezier, "Bezier", self)
        self.action_smooth = QtGui.QAction(self.icon_smooth, "Smooth", self)
        
        self.action_snap = QtGui.QAction(self.icon_snap, "Snap to Frames", self)
        self.action_snap.setCheckable(True)
        self.action_snap.setChecked(True) 
        self.action_snap.setToolTip("Toggle Snapping (Magnet)")
        self.action_snap.triggered.connect(self.toggle_snapping)
        
        tool_button_style = """
            QToolButton { 
                border: none; 
                padding: 6px; 
                color: white;
            }
            
            
            QToolButton:pressed {
                background-color: #E6A03C; 
                border-radius: 4px; 
            }

            QToolButton:checked { 
                
                background-color: #E6A03C; 
                border-radius: 4px; 
            }
            QToolButton:disabled {
                color: #555555;
            }
        """
        group_style = "QWidget { background-color: #3a3a3a; border-radius: 5px; }"

        
        tool_group_widget = QtWidgets.QWidget()
        tool_group_layout = QtWidgets.QHBoxLayout(tool_group_widget)
        tool_group_layout.setContentsMargins(2, 2, 2, 2); tool_group_layout.setSpacing(0)
        tool_group_widget.setStyleSheet(group_style)

        # === (Trim, Split) ===
        trim_btn = QtWidgets.QToolButton(); trim_btn.setDefaultAction(self.action_trim_clip); trim_btn.setStyleSheet(tool_button_style)
        split_btn = QtWidgets.QToolButton(); split_btn.setDefaultAction(self.action_split_clip); split_btn.setStyleSheet(tool_button_style)
        # === (Snap) ===
        snap_btn = QtWidgets.QToolButton();snap_btn.setDefaultAction(self.action_snap);snap_btn.setStyleSheet(tool_button_style)


        tool_group_layout.addWidget(trim_btn)
        tool_group_layout.addWidget(split_btn)
        tool_group_layout.addWidget(snap_btn)
        
        right_toolbar.addWidget(tool_group_widget)
        right_toolbar.addSeparator()

        # (select_btn, move_btn, scale_btn) 

        # === (Copy, Cut, Delete, Paste) ===
        edit_group_widget = QtWidgets.QWidget()
        edit_group_layout = QtWidgets.QHBoxLayout(edit_group_widget)
        edit_group_layout.setContentsMargins(2, 2, 2, 2); edit_group_layout.setSpacing(0)
        edit_group_widget.setStyleSheet(group_style)
        
        self.copy_btn = QtWidgets.QToolButton(); self.copy_btn.setDefaultAction(self.action_copy); self.copy_btn.setStyleSheet(tool_button_style)
        self.cut_btn = QtWidgets.QToolButton(); self.cut_btn.setDefaultAction(self.action_cut); self.cut_btn.setStyleSheet(tool_button_style)
        self.delete_btn = QtWidgets.QToolButton(); self.delete_btn.setDefaultAction(self.action_delete); self.delete_btn.setStyleSheet(tool_button_style)
        self.paste_btn = QtWidgets.QToolButton(); self.paste_btn.setDefaultAction(self.action_paste); self.paste_btn.setStyleSheet(tool_button_style)
        
        edit_group_layout.addWidget(self.copy_btn)
        edit_group_layout.addWidget(self.cut_btn)
        edit_group_layout.addWidget(self.delete_btn)
        edit_group_layout.addWidget(self.paste_btn)
        
        right_toolbar.addWidget(edit_group_widget)
        right_toolbar.addSeparator()

        # === (Curve, Linear, Bezier) ===
        tangent_group_widget = QtWidgets.QWidget()
        tangent_group_layout = QtWidgets.QHBoxLayout(tangent_group_widget)
        tangent_group_layout.setContentsMargins(2, 2, 2, 2); tangent_group_layout.setSpacing(0)
        tangent_group_widget.setStyleSheet(group_style)
        
        

        curve_btn = QtWidgets.QToolButton(); curve_btn.setDefaultAction(self.action_curve); curve_btn.setStyleSheet(tool_button_style)
        linear_btn = QtWidgets.QToolButton(); linear_btn.setDefaultAction(self.action_linear); linear_btn.setStyleSheet(tool_button_style)
        bezier_btn = QtWidgets.QToolButton(); bezier_btn.setDefaultAction(self.action_bezier); bezier_btn.setStyleSheet(tool_button_style)
        smooth_btn = QtWidgets.QToolButton(); smooth_btn.setDefaultAction(self.action_smooth); smooth_btn.setStyleSheet(tool_button_style)

        tangent_group_layout.addWidget(curve_btn)
        tangent_group_layout.addWidget(linear_btn)
        tangent_group_layout.addWidget(bezier_btn)
        tangent_group_layout.addWidget(smooth_btn)

        
        
        
        right_toolbar.addWidget(tangent_group_widget)

        # --- (Spacer, Curve Editor) ---

        spacer_widget = QtWidgets.QWidget(self)
        spacer_widget.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Preferred)
        right_toolbar.addWidget(spacer_widget)

        self.curve_toggle_btn = QtWidgets.QPushButton("Curve Editor")
        self.curve_toggle_btn.setCheckable(True)
        self.curve_toggle_btn.clicked.connect(self.toggle_curve_view)
        right_toolbar.addWidget(self.curve_toggle_btn) 
        
        
        
        #right_toolbar.setFixedHeight(top_bar_widget.sizeHint().height())
        right_layout.addWidget(right_toolbar) 

        
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
        self.editor_scroll_area.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        self.editor_scroll_area.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.editor_scroll_area.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        
        self.value_ruler = ValueRuler(self.curve_editor)
        self.value_zoom_slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Vertical)
        self.value_zoom_slider.setRange(10, 200) 
        self.value_zoom_slider.setValue(100)
        self.value_zoom_slider.valueChanged.connect(self.curve_editor.set_vertical_zoom)
        
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
        
        right_layout.addLayout(right_grid_layout)
        right_layout.addWidget(self.zoom_slider)

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
        self.motion_mixer_panel.track_tree.verticalScrollBar().valueChanged.connect(self.sync_scroll_from_track_list)
        
        
        #self.keyframe_area.verticalScrollBar().valueChanged.connect(self.sync_scroll_from_graphics_view)
        #self.curve_editor.verticalScrollBar().valueChanged.connect(self.sync_scroll_from_graphics_view)
        

        

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
        
        
        self.keyframe_area.selectionChanged.connect(self.update_edit_button_states)
        self.mixer_toggle_btn.clicked.connect(self.update_edit_button_states)
        
        
        self.action_delete.triggered.connect(self.keyframe_area.delete_selected_keys)
        
        
        self.action_copy.triggered.connect(self.keyframe_area.copy_selected_keys)
        self.action_cut.triggered.connect(self.keyframe_area.cut_selected_keys)
        self.action_paste.triggered.connect(self.keyframe_area.paste_keys)

        
        self.action_curve.triggered.connect(lambda: self.apply_tangent_type('curve'))
        self.action_linear.triggered.connect(lambda: self.apply_tangent_type('linear'))
        self.action_bezier.triggered.connect(lambda: self.apply_tangent_type('bezier'))
        self.action_smooth.triggered.connect(lambda: self.apply_tangent_type('smooth'))

        self.track_list_panel.track_tree.itemSelectionChanged.connect(self.keyframe_area.update)

        self.curve_editor.selectionChanged.connect(self.update_edit_button_states)
        self.mixer_toggle_btn.clicked.connect(self.update_edit_button_states)
        self.curve_toggle_btn.clicked.connect(self.update_edit_button_states)
        
        self.update_edit_button_states()
        # --- ---

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

    def toggle_snapping(self):
        state = self.action_snap.isChecked()
        self.keyframe_area.is_snapping = state
        self.curve_editor.is_snapping = state
        print(f"🧲 Snapping set to: {state}")

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
        
        self.keyframe_area.verticalScrollBar().blockSignals(True)
        self.curve_editor.verticalScrollBar().blockSignals(True)
        
        
        self.keyframe_area.verticalScrollBar().setValue(value)
        self.curve_editor.verticalScrollBar().setValue(value)
        
        
        self.keyframe_area.verticalScrollBar().blockSignals(False)
        self.curve_editor.verticalScrollBar().blockSignals(False)

        self.keyframe_area.update()
        self.curve_editor.update()

    
    

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
        
        print("DEBUG: Syncing scrollbars...")
        active_tree = self._get_active_tree_widget()
        track_sb = active_tree.verticalScrollBar()

        
        content_height = active_tree.header().height()
        iterator = QtWidgets.QTreeWidgetItemIterator(active_tree)
        iterator = QtWidgets.QTreeWidgetItemIterator(active_tree, QtWidgets.QTreeWidgetItemIterator.IteratorFlag.NotHidden)
        
        max_y = 0
        while iterator.value():
            item = iterator.value()
            if not item.isHidden():
                
                max_y = max(max_y, active_tree.visualItemRect(item).bottom())
            iterator += 1 

        #
        viewport_height = active_tree.viewport().height()
        
        content_height = max(max_y, viewport_height) 
        
        scene_rect = QtCore.QRectF(0, 0, 10000, content_height) 
        self.keyframe_area.setSceneRect(scene_rect)
        self.curve_editor.setSceneRect(scene_rect)
        
        
        track_sb.setRange(0, max(0, content_height - active_tree.viewport().height()))
        min_val, max_val = track_sb.minimum(), track_sb.maximum()
        page_step = track_sb.pageStep()
        current_val = track_sb.value()
        
        #
        key_sb = self.keyframe_area.verticalScrollBar()
        key_sb.blockSignals(True)
        key_sb.setRange(min_val, max_val); key_sb.setPageStep(page_step); key_sb.setValue(current_val)
        key_sb.blockSignals(False)
        
        curve_sb = self.curve_editor.verticalScrollBar()
        curve_sb.blockSignals(True)
        curve_sb.setRange(min_val, max_val); curve_sb.setPageStep(page_step); curve_sb.setValue(current_val)
        curve_sb.blockSignals(False)
        
        print(f"  -> Synced scrollbars. Range: 0-{max_val}, Value: {current_val}")
        self.keyframe_area.update()
        self.curve_editor.update()

    
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
            
            
            icon, brush = self._get_object_style(child_node)
            
            if icon:
                child_tree_item.setIcon(1, icon) 
            
            if brush:
                
                child_tree_item.setData(0, self.VISIBILITY_ROLE, brush)
            

            
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

                    
                    if pretty_name == "Transform":
                        tree_item.setIcon(1, self.icon_track_transform)
                        tree_item.setExpanded(True) 
                    elif pretty_name == "Position": 
                        tree_item.setIcon(1, self.icon_track_position)
                    elif pretty_name == "Rotation": 
                        tree_item.setIcon(1, self.icon_track_rotation)
                    elif pretty_name == "Scale": 
                        tree_item.setIcon(1, self.icon_track_scale)
                    elif pretty_name.startswith("X ") or pretty_name == "X":
                        tree_item.setIcon(1, self.red_icon)
                    elif pretty_name.startswith("Y ") or pretty_name == "Y":
                        tree_item.setIcon(1, self.green_icon)
                    elif pretty_name.startswith("Z ") or pretty_name == "Z":
                        tree_item.setIcon(1, self.blue_icon)
                    
                    
                    tree_item.setData(0, self.SUBANIM_ROLE, sub_anim)
                    tree_item.setData(0, self.PARENT_OBJ_ROLE, parent_max_object)
                    tree_item.setData(0, self.SUBANIM_NAME_ROLE, name)
                    #if pretty_name == "Transform":
                    #    tree_item.setExpanded(True)                    
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
            self.curve_editor._redraw_scene() 
            self.keyframe_area._redraw_scene()
            ui_needs_update = False 

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
            self.keyframe_area._redraw_scene()
            self.curve_editor._redraw_scene()

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

    def _get_object_style(self, node):
        
        color_settings = self.settings['Type_Colors']
        icon = None
        color_hex = None

        
        try:
            is_tyflow = rt.isKindOf(node, rt.tyFlow)
        except Exception:
            is_tyflow = False

       
        if (rt.isKindOf(node, rt.HubObject) or 
              rt.isKindOf(node, rt.CATParent) or 
              rt.isKindOf(node, rt.CATBone) or
              rt.isKindOf(node, rt.Dummy) or
              rt.isKindOf(node, rt.BoneGeometry) or 
              rt.isKindOf(node, rt.Biped_Object)):
            icon = self.icon_obj_bone
            color_hex = color_settings.get('bone_color')

        
        
        elif (is_tyflow or rt.isKindOf(node, rt.PF_Source)): 
            
            
            color_hex = color_settings.get('particle_color', '#886927')
            
            
            if is_tyflow:
                icon = self.icon_obj_tyflow
            else:
                icon = self.icon_obj_particle
        
        elif rt.isKindOf(node, rt.Light): 
            icon = self.icon_obj_light
            color_hex = color_settings.get('light_color')
        elif rt.isKindOf(node, rt.Camera): 
            icon = self.icon_obj_camera
            color_hex = color_settings.get('camera_color')
        elif rt.isKindOf(node, rt.Shape): 
            icon = self.icon_obj_shape
            color_hex = color_settings.get('shape_color')
        elif rt.isKindOf(node, rt.Helper): 
            icon = self.icon_obj_helper
            color_hex = color_settings.get('helper_color')
        elif rt.isKindOf(node, rt.SpacewarpObject): 
            icon = self.icon_obj_spacewarp
            color_hex = color_settings.get('SpacewarpObject_color')
        
        
        elif rt.isKindOf(node, rt.GeometryClass): 
            icon = self.icon_obj_geometry
            color_hex = color_settings.get('geometry_color')

        
        brush = None
        if color_hex:
            brush = QtGui.QBrush(QtGui.QColor(color_hex))
        else:
            
            brush = QtGui.QBrush(QtGui.QColor(color_settings.get('geometry_color', "#475A6D")))
        
        return icon, brush

    
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
        
        
        icon, brush = self._get_object_style(node)
        
        if icon:
            obj_item.setIcon(1, icon) 
        
        if brush:
            
            obj_item.setData(0, self.VISIBILITY_ROLE, brush) 
        
            
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
            
            

        self.update_edit_button_states() 
        
        # Ensure the scrollbars are synced after switching
        QtCore.QTimer.singleShot(0, self.sync_scrollbars)


    #CACHE FUNCTION
    
    def _on_cache_toggled(self, is_checked):
        """
        Shows the popup and runs the actual cache creation process.
        
        """
        
        
        if is_checked:
            if self.track_list_panel.track_tree.topLevelItemCount() == 0:
                
                QtWidgets.QMessageBox.warning(
                    self, 
                    "Cache Error", 
                    "You must add at least one object to the timeline first."
                )
                
                
                btn = self.track_list_panel.cache_mode_btn
                btn.blockSignals(True)
                btn.setChecked(False)
                btn.blockSignals(False)
                
                
                btn.setToolTip("Activate Cache Mode: Click to build a fast internal cache.")
                
                return 
            

            print("--- CACHE ACTIVATED ---")
            
            items_to_cache = []
            for i in range(self.track_list_panel.track_tree.topLevelItemCount()):
                item = self.track_list_panel.track_tree.topLevelItem(i)
                if item.data(0, self.PARENT_OBJ_ROLE) is not None: 
                    items_to_cache.append(item)
            
            if not items_to_cache:
                print("-> No clips to cache. Toggling button off.")
                
                self.track_list_panel.cache_mode_btn.blockSignals(True)
                self.track_list_panel.cache_mode_btn.setChecked(False)
                self.track_list_panel.cache_mode_btn.blockSignals(False)
                
                
                
                self.track_list_panel.cache_mode_btn.setToolTip("Activate Cache Mode: Click to build a fast internal cache.")
                
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
                    #
                    cache_was_successful = False
                    break 
                    

                progress_dialog.setLabelText(f"Processing: {item.text(1)} ({i+1}/{len(items_to_cache)})...")
                progress_dialog.setValue(i)
                QtWidgets.QApplication.processEvents()

                
                self._build_cache_for_item(item)
            
            progress_dialog.setValue(len(items_to_cache)) 

            if cache_was_successful:
                print("--- CACHE BUILD COMPLETE ---")
                
                # self.track_list_panel.cache_mode_btn.setText("Cache Active (Refresh)")
                self.track_list_panel.cache_mode_btn.setToolTip("Cache Active (Refresh): Click to rebuild the cache.")
                
            else:
                
                print("--- CACHE PROCESS INTERRUPTED ---")
                self.track_list_panel.cache_mode_btn.blockSignals(True)
                self.track_list_panel.cache_mode_btn.setChecked(False)
                
                #
                # self.track_list_panel.cache_mode_btn.setText("Activate Cache Mode")
                self.track_list_panel.cache_mode_btn.setToolTip("Activate Cache Mode: Click to build a fast internal cache.")
                
                self.track_list_panel.cache_mode_btn.blockSignals(False)

        else:
            
            print("--- CACHE DEACTIVATED (Live Mode) ---")
            
            
            # self.track_list_panel.cache_mode_btn.setText("Activate Cache Mode")
            self.track_list_panel.cache_mode_btn.setToolTip("Activate Cache Mode: Click to build a fast internal cache.")
            
        
        
        self.keyframe_area.update()
        btn = self.track_list_panel.cache_mode_btn
        btn.style().unpolish(btn)
        btn.style().polish(btn)
        btn.update()

    def _build_cache_for_item(self, item):
        """
        Reads the complete animation data for a specific clip item and stores it
        as a "cache" on the item itself.
        """
        handle = item.data(0, self.PARENT_OBJ_ROLE)
        if not handle:
            print(f"  -> SKIPPED: No handle found for '{item.text(1)}'.")
            return

        try:
            node = rt.maxOps.getNodeByHandle(handle)
            
            
            animation_map, _, _ = self.logic._capture_animation_data(node)
            
            
            item.setData(0, self.CLIP_DATA_ROLE, animation_map)
            
            print(f"  -> Successfully cached data for '{item.text(1)}'.")

        except Exception as e:
            print(f"  -> FAILED to cache data for '{item.text(1)}'. Error: {e}")

    
    def update_edit_button_states(self, selection_count=None):
        
        is_keyframe_area_active = (self.editor_container.currentWidget() == self.keyframe_area)
        is_curve_editor_active = (self.editor_container.currentWidget() == self.curve_editor)
        is_mixer_mode = (self.left_view_stack.currentIndex() == 1)

        
        keyframe_selection_count = len(self.keyframe_area.selected_keys)
        curve_editor_selection_count = len(self.curve_editor.selected_keys)
        
        
        has_keyframe_selection = (is_keyframe_area_active and keyframe_selection_count > 0) and not is_mixer_mode
        has_clipboard_data = bool(self._internal_clipboard) and is_keyframe_area_active and not is_mixer_mode
        
        self.copy_btn.setEnabled(has_keyframe_selection)
        self.cut_btn.setEnabled(has_keyframe_selection)
        self.delete_btn.setEnabled(has_keyframe_selection)
        self.paste_btn.setEnabled(has_clipboard_data)

        
        has_curve_selection = is_curve_editor_active and curve_editor_selection_count > 0
        
        self.action_curve.setEnabled(has_curve_selection)
        self.action_linear.setEnabled(has_curve_selection)
        self.action_bezier.setEnabled(has_curve_selection)
        self.action_smooth.setEnabled(has_curve_selection)
        
        
        if is_mixer_mode:
            self.copy_btn.setEnabled(False)
            self.cut_btn.setEnabled(False)
            self.delete_btn.setEnabled(False)
            self.paste_btn.setEnabled(False)
            self.action_curve.setEnabled(False)
            self.action_linear.setEnabled(False)
            self.action_bezier.setEnabled(False)
            self.action_smooth.setEnabled(False)

    
    def split_selected_clips_at_current_frame(self):
        """
        Splits all selected clips (or the clip under the playhead) at the current time.
        """
        current_t = int(rt.currentTime)
        items_to_split = []

        
        selected_items = self.track_list_panel.track_tree.selectedItems()
        if selected_items:
            for item in selected_items:
                if item.parent() is None:
                    items_to_split.append(item)
        
        if not items_to_split:
            for i in range(self.track_list_panel.track_tree.topLevelItemCount()):
                item = self.track_list_panel.track_tree.topLevelItem(i)
                start_frame = item.data(0, self.CLIP_START_ROLE)
                end_frame = item.data(0, self.CLIP_END_ROLE)
                if start_frame is not None and start_frame < current_t < end_frame:
                    items_to_split.append(item)
                    break 

        if not items_to_split:
            print("No selected clip or active clip found under the time slider to split.")
            return

        
        try:
            with pymxs.undo(True, f"Split {len(items_to_split)} clip(s)"):
                new_items_to_add = []
                
                
                import copy 

                for item in items_to_split:
                    start_frame = item.data(0, self.CLIP_START_ROLE)
                    end_frame = item.data(0, self.CLIP_END_ROLE)

                    if not (start_frame < current_t < end_frame):
                        print(f"Split for clip '{item.text(1)}' ignored: Playhead not inside clip.")
                        continue

                    
                    handle = item.data(0, self.PARENT_OBJ_ROLE)
                    anim_data = item.data(0, self.CLIP_DATA_ROLE)
                    node = rt.maxOps.getNodeByHandle(handle)
                    
                    if not node:
                        print(f"Split for clip '{item.text(1)}' failed: Node not found.")
                        continue

                    
                    item.setData(0, self.CLIP_END_ROLE, current_t)

                    
                    new_start = current_t
                    new_end = end_frame
                    new_name = f"{item.text(1)}_split"
                    
                    
                    new_anim_data = copy.deepcopy(anim_data)
                    
                    new_item = self._create_clip_item(node, new_name, new_start, new_end, new_anim_data)
                    
                    
                    self.add_tracks_recursively(new_item, node)
                    self._add_node_hierarchy_recursively(node, new_item)
                    
                    new_items_to_add.append(new_item)
                    print(f"Clip '{item.text(1)}' split at frame {current_t}.")
                
                
                if new_items_to_add:
                    last_item_index = self.track_list_panel.track_tree.indexOfTopLevelItem(items_to_split[-1])
                    self.track_list_panel.track_tree.insertTopLevelItems(last_item_index + 1, new_items_to_add)

            
            self.keyframe_area.update()
            self._save_timeline_state()
            self.sync_scrollbars() 

        except Exception as e:
            print(f"An error occurred during split: {e}")

    def apply_tangent_type(self, tangent_name):
        
        if self.editor_container.currentWidget() == self.curve_editor:
            self.curve_editor.apply_tangent_type(tangent_name)

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
        self.search_bar.setClearButtonEnabled(True)
        self.search_bar.textChanged.connect(timeline_widget.on_search_text_changed)
        
        add_icon = QtGui.QIcon(os.path.join(SCRIPT_PATH, 'icons', 'AddObjects.png').replace('\\', '/'))
        add_btn = QtWidgets.QPushButton(add_icon, " Add")
        # add_btn.setIconSize(QtCore.QSize(18, 18))
        add_btn.clicked.connect(timeline_widget.add_selected_objects)
        
        
        remove_icon = QtGui.QIcon(os.path.join(SCRIPT_PATH, 'icons', 'SubtractObjects.png').replace('\\', '/'))
        remove_btn = QtWidgets.QPushButton(remove_icon, " Remove")
        # add_btn.setIconSize(QtCore.QSize(18, 18))
        remove_btn.clicked.connect(timeline_widget.remove_selected_layers)

        #bake_btn = QtWidgets.QPushButton("Bake")
        #bake_btn.clicked.connect(timeline_widget.bake_selected_layers)

        clear_btn = QtWidgets.QPushButton("Clear")
        clear_btn.clicked.connect(timeline_widget.clear_all_layers)


        icon_path_inactive = os.path.join(SCRIPT_PATH, 'icons', 'Redchach.png').replace('\\', '/')
        icon_path_active = os.path.join(SCRIPT_PATH, 'icons', 'Greenchach.png').replace('\\', '/')


        self.cache_mode_btn = QtWidgets.QPushButton()
        self.cache_mode_btn.setCheckable(True) 
        self.cache_mode_btn.setToolTip("Activate Cache Mode: Click to build a fast internal cache for smoother UI performance.")
        self.cache_mode_btn.setIconSize(QtCore.QSize(24, 24))
        
        self.cache_mode_btn.setStyleSheet(f"""
            QPushButton {{
                image: url({icon_path_inactive});
                background-color: transparent;
                border: none;
                padding: 4px; 
            }}
            QPushButton:checked {{
                image: url({icon_path_active});
                background-color: transparent;
                border: none;
                padding: 4px;
            }}
            QPushButton:pressed {{
                
                border: 1px solid #777777; 
                border-radius: 4px;
            }}
        """)
        
        
        self.cache_mode_btn.toggled.connect(timeline_widget._on_cache_toggled)
        
        toolbar_layout.addWidget(self.search_bar)
        toolbar_layout.addWidget(self.cache_mode_btn)
        toolbar_layout.addStretch()
        toolbar_layout.addWidget(add_btn)
        toolbar_layout.addWidget(remove_btn)
        #toolbar_layout.addWidget(bake_btn)
        toolbar_layout.addWidget(clear_btn)
        
        
        self.track_tree = QtWidgets.QTreeWidget()
        self.track_tree.setColumnCount(4)
        self.value_delegate = ValueDelegate(self.track_tree, self)
        self.track_tree.setItemDelegateForColumn(3, self.value_delegate)
        self.track_tree.customContextMenuRequested.connect(timeline_widget.open_track_context_menu)
        self.track_tree.setHeaderLabels(['', 'Track Name', 'Controller', 'Value'])
        self.track_tree.setColumnWidth(0, 100)
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
        print("\n--- 💧 dropEvent Fired (With 6-Mode Loop) 💧 ---")
        
        #                   
        dragged_item = self.selectedItems()[0] if self.selectedItems() else None
        
        #                       
        event.setDropAction(QtCore.Qt.DropAction.MoveAction)
        super().dropEvent(event)
        
           
        for i in range(self.topLevelItemCount()):
            track_item = self.topLevelItem(i)
            
            # 1.         Blend Combo (     1)
            if self.itemWidget(track_item, 1) is None:
                blend_combo = QtWidgets.QComboBox(self)
                blend_combo.addItems(["Override", "Additive", "None"])
                current_mode = track_item.data(1, self.timeline_widget.BLEND_MODE_ROLE) or "Override"
                blend_combo.setCurrentText(current_mode)
                blend_combo.currentTextChanged.connect(
                    lambda text, bound_item=track_item: bound_item.setData(1, self.timeline_widget.BLEND_MODE_ROLE, text)
                )
                self.setItemWidget(track_item, 1, blend_combo)

            for j in range(track_item.childCount()):
                clip_item = track_item.child(j)
                
                # 2.         Clip Mode Combo (     2)
                #if self.itemWidget(clip_item, 2) is None:
                #    mode_combo = QtWidgets.QComboBox(self)
                #    mode_combo.addItems(["Absolute", "Relative"])
                #    current_mode = clip_item.data(2, self.timeline_widget.CLIP_MODE_ROLE) or "Absolute"
                #    mode_combo.setCurrentText(current_mode)
                #    mode_combo.currentTextChanged.connect(
                #        lambda text, bound_item=clip_item: bound_item.setData(2, self.timeline_widget.CLIP_MODE_ROLE, text)
                #    )
                #    self.setItemWidget(clip_item, 2, mode_combo)

                # 3. Re-create Loop Combo (Active)
                if self.itemWidget(clip_item, 5) is None:
                    loop_combo = QtWidgets.QComboBox(self)
                    # ---                 ---
                    loop_combo.addItems(["Once", "Constant", "Cycle", "PingPong", "Linear", "Relative"])
                    
                    current_loop = clip_item.data(5, self.timeline_widget.CLIP_LOOP_ROLE) or "Once"
                    loop_combo.setCurrentText(current_loop)
                    
                    loop_combo.currentTextChanged.connect(
                        lambda text, bound_item=clip_item: bound_item.setData(5, self.timeline_widget.CLIP_LOOP_ROLE, text)
                    )
                    self.setItemWidget(clip_item, 5, loop_combo)

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
        
        self.track_tree.setColumnCount(6)
        # 0:Name, 1:Blend, 2:Mode(Hidden), 3:Start, 4:End, 5:Loop
        self.track_tree.setHeaderLabels(["Track Name", "Blend Mode", "", "Start", "End", "Loop Mode"])
        self.track_tree.setColumnWidth(1, 100) 
        self.track_tree.setColumnWidth(2, 0)
        self.track_tree.setColumnWidth(5, 80)

        # Hide Mode Column
        self.track_tree.setColumnHidden(2, True)

        self.main_layout.addLayout(toolbar)
        self.main_layout.addWidget(self.track_tree)
        
    def _import_clip_file(self):
        """
        Modified Import: Always creates a NEW track for each clip.
        Mode column is handled as data-only (Hidden from UI).
        """
        file_paths, _ = QtWidgets.QFileDialog.getOpenFileNames(self, "Import Animation Clip(s)", "", "Animation Clips (*.clip)")
        if not file_paths: return

        
        for file_path in file_paths:
            try:
                with open(file_path, 'r') as f: clip_data = json.load(f)

                clip_name = os.path.basename(file_path)
                duration = clip_data.get("properties", {}).get("duration_frames", 100)
                track_name = os.path.splitext(clip_name)[0]

                # 1.                       
                track_item = QtWidgets.QTreeWidgetItem([track_name, "", "", "", "", ""])
                self.track_tree.addTopLevelItem(track_item)

                #       Blend Mode         
                blend_combo = QtWidgets.QComboBox(self.track_tree)
                blend_combo.addItems(["Override", "Additive", "None"])
                blend_combo.currentTextChanged.connect(
                    lambda text, item=track_item: item.setData(1, self.timeline_widget.BLEND_MODE_ROLE, text)
                )
                self.track_tree.setItemWidget(track_item, 1, blend_combo)
                track_item.setData(1, self.timeline_widget.BLEND_MODE_ROLE, "Override")

                
                start_time = 0
                end_time = start_time + int(duration)
                
                clip_item = QtWidgets.QTreeWidgetItem([clip_name, "", "", str(start_time), str(end_time), ""])
                clip_item.setData(0, QtCore.Qt.ItemDataRole.UserRole, clip_data)
                
                track_item.addChild(clip_item)
                track_item.setExpanded(True)

                 
                clip_item.setData(2, self.timeline_widget.CLIP_MODE_ROLE, "Absolute")


                
                loop_combo = QtWidgets.QComboBox(self.track_tree)
                loop_combo.addItems(["Once", "Constant", "Cycle", "PingPong", "Linear", "Relative"])
                loop_combo.setCurrentText("Once")
                clip_item.setData(5, self.timeline_widget.CLIP_LOOP_ROLE, "Once")
                
                loop_combo.currentTextChanged.connect(
                    lambda text, item=clip_item: item.setData(5, self.timeline_widget.CLIP_LOOP_ROLE, text)
                )
                self.track_tree.setItemWidget(clip_item, 5, loop_combo)

            except Exception as e:
                QtWidgets.QMessageBox.critical(self, "Import Error", f"Failed to import clip: {file_path}\nError: {e}")

        self.timeline_widget.keyframe_area.update()
        self.timeline_widget.sync_scrollbars()

    def _remove_selected(self):
        """
        Removes selected tracks. If a clip is selected, removes its parent track.
        """
        selected_items = self.track_tree.selectedItems()
        if not selected_items: return
            
        tracks_to_delete = set()
        for item in selected_items:
            if item.parent():
                #                                (   )          
                tracks_to_delete.add(item.parent())
            else:
                #                                           
                tracks_to_delete.add(item)
                
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