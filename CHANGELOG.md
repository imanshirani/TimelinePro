# Changelog

All notable changes to this project will be documented in this file.


## [0.0.3] - 2025-11-26
### 🐛 Bug Fixes
* Fixed a critical issue where baking clips would cause objects to "jump" or reset to zero due to incorrect layer processing order.
* Fixed an issue where "Relative" loop mode would reset the object position at the start of each cycle.
* Fixed `addNewKey` runtime error during baking by enforcing controller types (Position_XYZ, Euler_XYZ) before the bake process.
* Fixed the "Fade In/Out" context menu visibility logic.
  
### 🚀 New Features
* **Advanced Motion Mixer Baking:**
    * Implemented a completely new **Bottom-Up Baking Engine** to ensure correct layer stacking and blending order.
    * Added **"Phase 1" Pre-calculation** for Relative offsets, ensuring that clips with "Relative" loop mode maintain their global positions correctly across the timeline.
    * Added support for **Additive** and **Override** blend modes per track.
* **Looping System:**
    * Fully implemented 6 looping modes for mixer clips: **Once, Constant, Cycle, PingPong, Linear, and Relative**.
    * Added a "Set Loop Count" context menu to automatically extend clip duration based on loop iterations.


### 🛠 Improvements & Logic Updates
* **Robust Auto-Keying:**
    * Switched baking logic to a "Brute Force" Auto-Key method (`animButtonEnabled` + `sliderTime`) to guarantee keyframe registration in 3ds Max, resolving issues where keys were not being set during bake.
* **Smart Blending:**
    * Refined the `Lerp` (Linear Interpolation) and `Slerp` (Spherical Linear Interpolation) logic to prevent animation popping when transitioning between clips.
    * Updated **Fade In/Out** logic to work on any layer index (removed restriction on the bottom-most layer).
* **Performance:**
    * Optimized the `sync_scrollbars` function to ensure smooth scrolling between the Track List, Keyframe Area, and Curve Editor.
* **Visual Markers:**
    * Introduced a dedicated **MarkerView** widget.
    * Users can now Add, Edit (Color & Note), and Delete visual markers on the timeline (Shift+Click to add).
* **Settings & Customization:**
    * Added a **Settings Dialog** to customize layer colors (Lights, Cameras, Helpers, etc.).
    * Added "Default Hidden Tracks" configuration to filter out unwanted sub-anims (e.g., visibility, sound) automatically.
* **UI Improvements:**
    * Added **Scrubbers** (XYZ, Quat, Value) in the Track List for direct value manipulation via mouse drag.
    * Added **Zoom Sliders** for both horizontal (Time) and vertical (Value) axes.



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
