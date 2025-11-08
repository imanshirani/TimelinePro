# Changelog

All notable changes to this project will be documented in this file.

---

## [0.0.2] - 2025-11-08

### 🐛 Bug Fixes

* **Fixed:** Scrollbar jumping (flickering) behavior when synchronizing the Track List and Keyframe Area.
* **Fixed:** The Keyframe Area would not update live when scrolling from the Track List, requiring an extra click to refresh.
* **Fixed:** Scrollbar height calculation incorrectly included hidden items. The scrollbar range now correctly updates based on *visible* layers only.

---



### 🚀 Features

* **Added:** **Motion Mixer** panel for non-linear animation editing, allowing clips to be sequenced (back-to-back) and stacked (layered).
* **Added:** **Curve Editor** with full tangent controls (Linear, Curve, Smooth).
* **Added:** **Copy / Cut / Paste** functionality for keyframes within the Keyframe Area.
* **Added:** **Cache Mode** to significantly boost UI performance and allow for smoother clip manipulation.

### ⚡ Performance

* **Improved:** Rewrote the core of the **Keyframe Area** and **Curve Editor** to utilize **GPU acceleration** instead of the CPU, resulting in a much faster and smoother navigation experience.

### 🎨 UI Improvements

* **Added:** New set of professional icons across the entire user interface.
* **Added:** Dedicated icons for object types (e.g., Camera, Light, Bone) in the track list.



## [0.0.1] - 2025-11-01
