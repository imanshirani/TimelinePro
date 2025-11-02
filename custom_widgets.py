from PySide6 import QtWidgets, QtCore, QtGui


# ==========================================
# === CLASS: class ValueScrubber         ===
# ==========================================
class ValueScrubber(QtWidgets.QLineEdit):
    """
    A QLineEdit that allows the user to change its numeric value by dragging the mouse.

    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.scrubbing = False
        self.start_pos = None
        self.start_val = 0.0        
        self.setValidator(QtGui.QDoubleValidator())        
        self.setCursor(QtCore.Qt.CursorShape.SizeHorCursor)

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            self.scrubbing = True
            self.start_pos = event.globalPosition() 
            try:
                self.start_val = float(self.text())
            except ValueError:
                self.start_val = 0.0
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.scrubbing:
            delta_x = event.globalPosition().x() - self.start_pos.x()
            
            modifiers = event.modifiers()
            if modifiers == QtCore.Qt.KeyboardModifier.ControlModifier:                
                sensitivity = 0.01
            elif modifiers == QtCore.Qt.KeyboardModifier.ShiftModifier:                
                sensitivity = 1.0
            else:                
                sensitivity = 0.1
            
            new_val = self.start_val + (delta_x * sensitivity)
            
            self.setText(f"{new_val:.3f}")
            self.editingFinished.emit()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            self.scrubbing = False
            self.start_pos = None
        super().mouseReleaseEvent(event)

# ==========================================
# === END CLASS: class ValueScrubber     ===
# ==========================================

# ==========================================
# === CLASS: class XYZScrubber           ===
# ==========================================
class XYZScrubber(QtWidgets.QWidget):
    editingFinished = QtCore.Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout = QtWidgets.QHBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(2)
        
        
        self.x_scrubber = ValueScrubber()
        self.y_scrubber = ValueScrubber()
        self.z_scrubber = ValueScrubber()
        
        self.layout.addWidget(self.x_scrubber)
        self.layout.addWidget(self.y_scrubber)
        self.layout.addWidget(self.z_scrubber)
        
        
        self.x_scrubber.editingFinished.connect(self.editingFinished)
        self.y_scrubber.editingFinished.connect(self.editingFinished)
        self.z_scrubber.editingFinished.connect(self.editingFinished)

    def text(self):
        """Returns the final value as a text string."""
        try:
            x = float(self.x_scrubber.text())
            y = float(self.y_scrubber.text())
            z = float(self.z_scrubber.text())
            return f"[{x:.3f},{y:.3f},{z:.3f}]"
        except ValueError:
            return "[0,0,0]"

    def setText(self, value_str):
        """Takes a text string and displays it in three separate boxes."""
        try:
            
            vals = value_str.replace('[','').replace(']','').replace('(Point3','').replace(')','').split(',')
            self.x_scrubber.setText(vals[0].strip())
            self.y_scrubber.setText(vals[1].strip())
            self.z_scrubber.setText(vals[2].strip())
        except (IndexError, ValueError):
            self.x_scrubber.setText("0.0")
            self.y_scrubber.setText("0.0")
            self.z_scrubber.setText("0.0")


# ==========================================
# === END  CLASS XYZScrubber             ===
# ==========================================

# ==========================================
# === CLASS: class QuatScrubber          ===
# ==========================================
class QuatScrubber(QtWidgets.QWidget):
    editingFinished = QtCore.Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout = QtWidgets.QHBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(2)
        
        
        self.x_scrubber = ValueScrubber()
        self.y_scrubber = ValueScrubber()
        self.z_scrubber = ValueScrubber()
        self.w_scrubber = ValueScrubber()
        
        self.layout.addWidget(self.x_scrubber)
        self.layout.addWidget(self.y_scrubber)
        self.layout.addWidget(self.z_scrubber)
        self.layout.addWidget(self.w_scrubber)
        
        
        self.x_scrubber.editingFinished.connect(self.editingFinished)
        self.y_scrubber.editingFinished.connect(self.editingFinished)
        self.z_scrubber.editingFinished.connect(self.editingFinished)
        self.w_scrubber.editingFinished.connect(self.editingFinished)

    def text(self):
        """Returns the final value as a text string."""
        try:
            x = float(self.x_scrubber.text())
            y = float(self.y_scrubber.text())
            z = float(self.z_scrubber.text())
            w = float(self.w_scrubber.text())
            
            return f"(quat {x:.3f} {y:.3f} {z:.3f} {w:.3f})"
        except ValueError:
            return "(quat 0 0 0 1)"

    def setText(self, value_str):
        """Takes a text string and displays it in four separate boxes."""
        try:
            
            cleaned_str = value_str.lower().replace('(quat','').replace(')','')
            parts = cleaned_str.split()
            self.x_scrubber.setText(parts[0].strip())
            self.y_scrubber.setText(parts[1].strip())
            self.z_scrubber.setText(parts[2].strip())
            self.w_scrubber.setText(parts[3].strip())
        except (IndexError, ValueError):
            self.x_scrubber.setText("0.0")
            self.y_scrubber.setText("0.0")
            self.z_scrubber.setText("0.0")
            self.w_scrubber.setText("1.0") 

# ==========================================
# === END  CLASS QuatScrubber            ===
# ==========================================