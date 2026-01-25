import pymxs
import os
import json
import uuid
import datetime
from PySide6 import QtWidgets, QtCore, QtGui

rt = pymxs.runtime

class TimelineLogic:
    def __init__(self, ui_instance):
        """A reference to the main UI class is stored to access widgets."""
        self.ui = ui_instance
        self.rt = rt

    def _register_save_callback(self):
        """⚙️ Registers a callback for the file save event in 3ds Max."""
        try:
            
            callback_code = f"python.execute(\"import timeline_ui; inst = timeline_ui.get_timeline_instance(); inst.logic._save_timeline_state() if inst else None\")"
            rt.callbacks.addScript(rt.name('filePostSave'), callback_code, id=rt.name(self.ui.save_callback_id))
            print("✅ Save callback successfully registered.")
        except Exception as e:
            print(f"❌ ERROR: Could not register save callback: {e}")

    def _register_selection_callback(self):
        """Registers a callback for the selection change event in the 3ds Max scene."""
        try:
            
            callback_code = f"python.execute(\"import timeline_ui; inst = timeline_ui.get_timeline_instance(); inst.logic.sync_selection_from_max() if inst else None\")"
            rt.callbacks.addScript(rt.name('selectionSetChanged'), callback_code, id=rt.name(self.ui.selection_callback_id))
            print("✅ Selection callback successfully registered.")
        except Exception as e:
            print(f"❌ ERROR: Could not register selection callback: {e}")

    def sync_selection_from_max(self):
        """When the selection in Max's scene changes, it selects the corresponding item in the timeline."""
        
        if self.ui.is_syncing_selection:
            return 
            
        self.ui.is_syncing_selection = True

        tree = self.ui.track_list_panel.track_tree
        tree.blockSignals(True)
        tree.clearSelection()

        selected_handles = {node.handle for node in rt.selection}
        
        iterator = QtWidgets.QTreeWidgetItemIterator(tree)
        while iterator.value():
            item = iterator.value()
            if item.parent() is None:
                handle = item.data(0, self.ui.PARENT_OBJ_ROLE) 
                if handle in selected_handles:
                    item.setSelected(True)
            iterator += 1
        
        tree.blockSignals(False)
        self.ui.is_syncing_selection = False

    def _load_default_hidden_tracks_from_settings(self):
        hidden_list_str = self.ui.settings.get('Default_Hidden_Tracks', 'hidden_list', fallback='')
        self.DEFAULT_HIDDEN_TRACKS = set(hidden_list_str.split(',')) if hidden_list_str else set() 
        print(f"DEBUG: Loaded default hidden tracks: {self.DEFAULT_HIDDEN_TRACKS}")

    

    def _convert_mxs_to_json_safe(self, mxs_value):
        """
        A powerful translator that converts 3ds Max data types into JSON-safe formats.
        Ultimate and error-proof using string comparison.
        """
        
        val_class_str = str(self.rt.classOf(mxs_value))

        
        if val_class_str in ['Point3', 'Quat', 'EulerAngles', 'Point4', 'Color', 'RGBA']:
            return [float(v) for v in mxs_value]
        
        
        elif val_class_str == 'bool':
            return bool(mxs_value)
            
        
        elif isinstance(mxs_value, (int, float)):
            return float(mxs_value)
            
        
        else:
            return str(mxs_value)
        
    def _get_local_prs_at_time(self, node, frame):
        """
        Calculates local PRS values by manually and safely changing the scene time.
        """
        original_time = self.rt.currentTime
        try:
            self.rt.currentTime = frame # Manually set the time
            
            if node.parent:
                local_transform = node.transform * self.rt.inverse(node.parent.transform)
            else:
                local_transform = node.transform
            
            pos = local_transform.translation
            rot = local_transform.rotationpart
            scl = local_transform.scalepart
            
            return {
                'pos': [pos.x, pos.y, pos.z],
                'rot': [rot.x, rot.y, rot.z, rot.w],
                'scl': [scl.x, scl.y, scl.z]
            }
        finally:
            self.rt.currentTime = original_time

    def _extract_keys_from_controller(self, controller, start_frame_offset):
        """
        A powerful translator that converts 3ds Max data types into JSON-safe formats.
        Ultimate and error-proof using string comparison.
        """
        if not controller or not rt.isProperty(controller, "keys") or controller.keys.count == 0:
            return []

        keys_list = []
        for key in controller.keys:
            
            if not rt.isProperty(key, 'value'):
                continue

            key_data = {
                "time": float(key.time) - start_frame_offset, 
                "value": self._convert_mxs_to_json_safe(key.value)
            }
            if rt.isProperty(key, 'inTangent'):
                key_data["inTangent"] = self._convert_mxs_to_json_safe(key.inTangent)
                key_data["outTangent"] = self._convert_mxs_to_json_safe(key.outTangent)
                key_data["inTangentType"] = str(key.inTangentType)
                key_data["outTangentType"] = str(key.outTangentType)
            keys_list.append(key_data)
        return keys_list
    
    #=============================
    # Export .CLIP
    #=============================       
    
    #=============================
    # Export .CLIP (Hierarchical)
    #=============================       

    def _build_hierarchy_data(self, node, anim_range, start_frame_offset):
        """
        - Recursively reads the animation structure.
        - Local animation: Extracts keys from all controllers.
        - World animation: Samples the transformation (position, rotation, scale) frame by frame.
        """
        if not node:
            return None
            
        print(f"\nProcessing Node: '{node.name}' (Handle: {node.handle})")
        print("--------------------------------------------------")
        
        
        local_anim_paths = {}

        def recursive_subanim_extractor(owner, path_prefix):
            if not owner: return
            
            if hasattr(owner, 'controller') and owner.controller:
                keys = self._extract_keys_from_controller(owner.controller, start_frame_offset)
                if keys:
                    clean_path = path_prefix.replace('__', '/').replace('_', ' ')
                    print(f"    ✅ Found {len(keys)} LOCAL keys for track: '{clean_path}'")
                    local_anim_paths[clean_path] = {"keys": keys}
            
            if hasattr(owner, 'numSubs') and owner.numSubs > 0:
                try:
                    for name in rt.getSubAnimNames(owner):
                        sub_anim = rt.getSubAnim(owner, name)
                        if sub_anim:
                            current_path = f"{path_prefix}/{name}" if path_prefix else str(name)
                            recursive_subanim_extractor(sub_anim, current_path)
                except Exception:
                    pass

        recursive_subanim_extractor(node, "BaseObject")
        for mod in node.modifiers:
            print(f"  -> Scanning Modifier: '{mod.name}'")
            recursive_subanim_extractor(mod, f"Modifiers/{mod.name}")

        
        world_anim_data = {}
        print(f"  -> Sampling WORLD Transform from frame {anim_range[0]} to {anim_range[1]}...")
        
        
        
        rt.disableSceneRedraw()
        try:
            for frame in range(anim_range[0], anim_range[1] + 1):
                
                with pymxs.attime(frame):
                    
                    
                    rt.redrawViews(False) 
                    
                    transform = node.transform 
                    pos = transform.translation
                    rot = transform.rotationpart
                    scl = transform.scalepart
                    
                    world_anim_data[str(frame)] = {
                        "position": [pos.x, pos.y, pos.z],
                        "rotation_quat": [rot.x, rot.y, rot.z, rot.w],
                        "scale": [scl.x, scl.y, scl.z]
                    }
                    
            
        finally:
            rt.enableSceneRedraw()
            rt.redrawViews() 
        

        
        this_node_data = {
            "object_name": node.name,
            "handle_id": str(node.handle),
            "local_animation": local_anim_paths,
            "world_animation": world_anim_data,
            "children": []
        }

        if node.children:
            for child_node in node.children:
                child_data = self._build_hierarchy_data(child_node, anim_range, start_frame_offset)
                if child_data:
                    this_node_data["children"].append(child_data)
                    
        return this_node_data
    
    def _export_clip_to_file(self, item):
        """
        This function saves the selected object and all its children with all animation details
        (Local and World) in a .clip file.
        """
        handle = item.data(0, self.ui.PARENT_OBJ_ROLE)
        start_frame = item.data(0, self.ui.CLIP_START_ROLE)
        end_frame = item.data(0, self.ui.CLIP_END_ROLE)
        
        if handle is None or start_frame is None or end_frame is None: 
            QtWidgets.QMessageBox.warning(self.ui, "Export Error", "Clip data is incomplete.")
            return

        try:
            root_node = self.rt.maxOps.getNodeByHandle(handle)
        except Exception:
            QtWidgets.QMessageBox.critical(self.ui, "Export Error", "Could not find the object in the scene. It may have been deleted.")
            return

        print(f"Exporting HIERARCHY for root node: '{root_node.name}'...")
        
        
        anim_range = (start_frame, end_frame)
        start_frame_offset = start_frame 
        
        
        hierarchy_data = self._build_hierarchy_data(root_node, anim_range, start_frame_offset)

        
        final_data_to_save = {
            "metadata": { 
                "version": "0.0.3 Timeline Pro -Export Clip File", 
                "export_date": datetime.datetime.now().isoformat(),
                "source_root_object": root_node.name
            },
            "properties": { 
                "start_frame_absolute": start_frame,
                "end_frame_absolute": end_frame,
                "duration_frames": end_frame - start_frame,
            },
            
            "animation_data": hierarchy_data 
        }

        default_name = f"{item.text(1)}.clip"
        file_path, _ = QtWidgets.QFileDialog.getSaveFileName(self.ui, "Save Animation Hierarchy", default_name, "Animation Clips (*.clip)")
        if not file_path: 
            print("Export cancelled by user.")
            return

        try:
            with open(file_path, 'w') as f:
                json.dump(final_data_to_save, f, indent=2)
            print(f"✅ HIERARCHY EXPORT COMPLETE! File saved to: {file_path}")
            QtWidgets.QMessageBox.information(self.ui, "Export Success", f"Animation hierarchy saved successfully to:\n{file_path}")
        except Exception as e:
            QtWidgets.QMessageBox.critical(self.ui, "Export Error", f"Failed to save file.\nError: {e}")
    #=============================
    # END Export .CLIP
    #=============================
    #=============================
    # Apply animation data to node
    #============================= 
    def _apply_animation_data_to_node(self, node, animation_data, start_frame_offset=0):
        """
        Uses frame-by-frame sampling and baking for perfect accuracy.
        """
        all_tracks = animation_data.get("tracks", {})
        if not all_tracks:
            print(f"No tracks to bake for '{node.name}'.")
            return

        min_time, max_time = float('inf'), float('-inf')
        for track_data in all_tracks.values():
            for key in track_data.get("keys", []):
                min_time = min(min_time, key['time'])
                max_time = max(max_time, key['time'])
        
        if max_time == float('-inf'): return

        bake_start_frame = int(start_frame_offset)
        bake_end_frame = int(start_frame_offset + max_time)

        print(f"Baking '{node.name}' from frame {bake_start_frame} to {bake_end_frame}...")

        with rt.redraw_disabled():
            for path, track_data in all_tracks.items():
                sub_anim = self._find_subanim_by_path(node, path)
                if sub_anim and not sub_anim.controller:
                    try:
                        val_class = rt.classOf(sub_anim.value)
                        if val_class == rt.Point3: sub_anim.controller = rt.Bezier_Position()
                        elif val_class == rt.Quat: sub_anim.controller = rt.Bezier_Rotation()
                        elif val_class == rt.Float: sub_anim.controller = rt.Bezier_Float()
                    except Exception: pass
            
            with rt.animate(True):
                for frame in range(bake_start_frame, bake_end_frame + 1):
                    local_time = frame - start_frame_offset
                    with rt.atTime(frame):
                        for path, track_data in all_tracks.items():
                            sub_anim = self._find_subanim_by_path(node, path)
                            if sub_anim and sub_anim.controller:
                                interpolated_value = self._get_value_at_time_from_keys(
                                    local_time, 
                                    track_data.get("keys", []), 
                                    track_data.get("controller_info", {})
                                )
                                if interpolated_value is not None:
                                    try:
                                        sub_anim.controller.value = interpolated_value
                                    except Exception as e:
                                        pass # Reduce log spam for non-critical errors


    #=============================
    # END Apply animation data to node
    #============================= 
    #=============================
    # bake selected layers
    #============================= 
    def bake_selected_layers(self):
        """
        The original Bake function now uses new, more precise logic.
        """
        selected_items = self.track_list_panel.track_tree.selectedItems()
        if not selected_items:
            print("Please select one or more layers to bake.")
            return

        clips_to_bake = [item for item in selected_items if item.parent() is None]
        if not clips_to_bake: return

        try:
            with pymxs.undo(True, f"Bake Animation for {len(clips_to_bake)} layer(s)"):
                for clip_item in clips_to_bake:
                    handle = clip_item.data(0, self.CLIP_START_ROLE)
                    if handle is None: continue
                    
                    try:
                        node = rt.maxOps.getNodeByHandle(handle)
                    except Exception:
                        continue

                    animation_data = clip_item.data(0, self.CLIP_DATA_ROLE)
                    start_frame = clip_item.data(0, self.CLIP_START_ROLE)
                    if not animation_data:
                        continue
                    
                    self._apply_animation_data_to_node(node, animation_data, start_frame)
            
            rt.redrawViews()
            print("Bake completed successfully!")
            self._force_ui_refresh()

        except Exception as e:
            print(f"An error occurred during bake: {e}")
    
    #=============================
    # END bake selected layers
    #=============================
    #=============================
    # Assign Controller
    #=============================
    def assign_specific_controller(self, item, script_name):
        
        sub_anim_track = item.data(0, self.ui.SUBANIM_ROLE)
        if not sub_anim_track:
            print(f"❌ ERROR: Could not find SubAnim data on item '{item.text(1)}'.")
            return

        print(f"Attempting to assign '{script_name}' to '{item.text(1)}'...")

        try:
            with pymxs.undo(True, f"Assign Controller: {script_name}"):
                
                controller_class = getattr(rt, script_name, None)
                if not controller_class:
                    print(f"❌ ERROR: Controller class '{script_name}' not found.")
                    return

                
                new_controller = controller_class()
                
                
                rt.mxs_target_subanim = sub_anim_track
                rt.mxs_new_controller = new_controller
                
                rt.execute("mxs_target_subanim.controller = mxs_new_controller")
                
                
                rt.execute("mxs_target_subanim = undefined")
                rt.execute("mxs_new_controller = undefined")
                
                new_controller_name = str(rt.classOf(sub_anim_track.controller))
                item.setText(2, new_controller_name)
                self.ui.update_single_item_value(item)
                
                
                self.ui._show_controller_in_motion_panel(item)
                
            print(f"✅ Successfully assigned '{script_name}' to '{item.text(1)}'.")

        except Exception as e:
            
            rt.execute("mxs_target_subanim = undefined")
            rt.execute("mxs_new_controller = undefined")
            print(f"❌ FAILED to assign controller '{script_name}': {e}")


    def handle_context_menu_request(self, position):
        """
        The ultimate, smart version based on user code:
        - [NEW] Adds a "Refresh Tracks" option for clips.
        - Displays the Export menu for clips.
        - Filters compatible controllers by track type.
        - Adds a "Reset to Default" option.
        """
        rt = self.rt
        
        track_tree = self.ui.track_list_panel.track_tree
        item = track_tree.itemAt(position)
        if not item: 
            return

        
        if item.parent() is None:
            menu = QtWidgets.QMenu()
            
            refresh_action = menu.addAction("Refresh Tracks")
            refresh_action.setToolTip("Reloads the track list for this item (e.g., after adding a new modifier).")
            refresh_action.triggered.connect(lambda: self.ui.refresh_item(item))
            menu.addSeparator()

            #export_action = menu.addAction("Export Animation as .clip")
            #export_action.triggered.connect(lambda: self._export_clip_to_file(item))
            
            menu.exec(track_tree.viewport().mapToGlobal(position))
            
            return

        
        sub_anim = item.data(0, self.ui.SUBANIM_ROLE)
        if not sub_anim: 
            return

        compatible_controllers_map = {}
        superclass_name = None 

        try:
            superclass_name = None 
            
            if rt.isController(sub_anim):
                controller_superclass_id = rt.superClassIDof(sub_anim)
                id_map = {0x2010: "Float_Control", 0x2011: "Position_Control", 0x2012: "Rotation_Control", 0x2013: "Scale_Control"}
                superclass_name = id_map.get(controller_superclass_id)

            if not superclass_name and rt.isProperty(sub_anim, 'value'):
                val_type = rt.classOf(sub_anim.value)
                
                if val_type == rt.Float or val_type == rt.Integer or rt.isKindOf(val_type, rt.Float) or val_type == rt.Double:
                    superclass_name = "Float_Control"
                elif val_type == rt.Point3 or rt.isKindOf(val_type, rt.Point3):
                    subanim_name_str = str(item.data(0, self.ui.SUBANIM_NAME_ROLE)).lower()
                    if 'scale' in subanim_name_str:
                        superclass_name = "Scale_Control"
                    else:
                        superclass_name = "Position_Control"
                elif val_type == rt.Quat or rt.isKindOf(val_type, rt.Quat):
                    superclass_name = "Rotation_Control"
                elif val_type == rt.Matrix3 or rt.isKindOf(val_type, rt.Matrix3):
                     superclass_name = "Transform_Control"

            if superclass_name and superclass_name in self.ui.controller_map_ui:
                compatible_controllers_map = self.ui.controller_map_ui[superclass_name]
            else:
                return

        except Exception as e:
            print(f"ERROR during controller detection: {e}")
            return

        if not compatible_controllers_map: return
            
        default_controller_map = {
            "Float_Control": "bezier_float",
            "Position_Control": "Position_XYZ",
            "Rotation_Control": "Euler_XYZ", 
            "Scale_Control": "bezier_scale",
            "Transform_Control": "prs" 
        }
        default_script_name = default_controller_map.get(superclass_name)
        
        menu = QtWidgets.QMenu()
        
        if default_script_name:
            reset_action = menu.addAction(f"Reset to Default ({default_script_name})")
            reset_action.setData(default_script_name)
            menu.addSeparator()
            
        assign_menu = menu.addMenu("Assign Controller")
        
        for ui_name, script_name in compatible_controllers_map.items():
            action = assign_menu.addAction(ui_name)
            action.setData(script_name)

        chosen_action = menu.exec(track_tree.viewport().mapToGlobal(position))
        
        if chosen_action and chosen_action.data():
            self.assign_specific_controller(item, chosen_action.data())

            
    #=============================
    # END Assign Controller
    #=============================

    #=============================
    # Context menu
    #=============================
    def open_track_context_menu(self, position):
        """
        This function is now just an interface and forwards the request to the logical class.
        """
        self.logic.handle_context_menu_request(position)
    #=============================
    # END Context menu
    #=============================

    #=============================
    # Capture animation data
    #=============================
    def _capture_animation_data(self, max_object):
        """
        Reads the animation. If the key exists, it sets the time range accordingly.
        If not, it uses the timeline cursor.
        """
        print(f"\n--- Capturing Animation for: '{max_object.name}' (Version 0.0.2) ---")
        animation_data = {"tracks": {}}
        all_keys = []

        
        def recursive_prescan(parent_obj):
            if not parent_obj: return
            if hasattr(parent_obj, 'controller'):
                controller = parent_obj.controller
                if controller and rt.isController(controller) and rt.isProperty(controller, "keys") and controller.keys.count > 0:
                    for key in controller.keys: all_keys.append(key)
            if hasattr(parent_obj, 'numSubs') and parent_obj.numSubs > 0:
                try:
                    for name in rt.getSubAnimNames(parent_obj):
                        recursive_prescan(rt.getSubAnim(parent_obj, name))
                except Exception: pass
        
        recursive_prescan(max_object)
        print(f"  -> Prescan complete. Found {len(all_keys)} total keyframes.")

        start_frame_offset = 0
        final_start_frame = 0
        final_end_frame = 0

        
        if not all_keys:
            
            print("  -> No keys found. Creating clip from current time.")
            start_frame_offset = int(rt.currentTime) 
            final_start_frame = int(rt.currentTime)
            final_end_frame = int(rt.animationRange.end)
        else:
            
            min_key_time = float(min(key.time for key in all_keys))
            max_key_time = float(max(key.time for key in all_keys))
            print(f"  -> Key range found: Frame {min_key_time} to {max_key_time}")
            
            start_frame_offset = min_key_time 
            final_start_frame = int(min_key_time)
            final_end_frame = int(max_key_time)

            
            def recursive_capture(parent_obj, path_prefix=""): 
                if hasattr(parent_obj, 'controller'):
                    controller = parent_obj.controller
                    if controller and rt.isController(controller) and rt.isProperty(controller, "keys") and controller.keys.count > 0:
                        keys_list = []
                        for key in controller.keys:
                            key_data = {}
                            prop_names = ['time', 'value', 'inTangent', 'outTangent', 'inTangentType', 'outTangentType', 'inTangentLength', 'outTangentLength']
                            for prop in prop_names:
                                if rt.isProperty(key, prop):
                                    val = getattr(key, prop)
                                    if prop == 'time':
                                        key_data[prop] = float(val) - start_frame_offset 
                                    else:
                                        prop_class = rt.classOf(val)
                                        prop_class_str = str(prop_class)
                                        if prop_class_str in ['Point3', 'Quat', 'Point4', 'Color', 'RGBA', 'FRGBA', 'EulerAngles']: 
                                            key_data[prop] = [float(v) for v in val]
                                        elif prop_class == rt.Name: key_data[prop] = str(val)
                                        else: key_data[prop] = float(val) if isinstance(val, (int, float)) else str(val)
                            
                            keys_list.append(key_data) 
                        
                        if keys_list:
                            controller_info = {
                                "class_of": str(rt.classOf(controller)),
                                "class_id": str(rt.classIDof(controller)),
                                "superclass_id": hex(rt.superClassIDof(controller))
                            }
                            animation_data["tracks"][path_prefix] = {
                                "controller_info": controller_info,
                                "keys": keys_list
                            }

                if hasattr(parent_obj, 'numSubs') and parent_obj.numSubs > 0:
                    try:
                        for name in rt.getSubAnimNames(parent_obj):
                            sub_anim = rt.getSubAnim(parent_obj, name)
                            current_path = f"{path_prefix}/{name}" if path_prefix else str(name)
                            recursive_capture(sub_anim, current_path)
                    except Exception: pass
            
            recursive_capture(max_object, "") 

        print(f"  -> SUCCESS: Clip created from {final_start_frame} to {final_end_frame}")
        
        return animation_data, final_start_frame, final_end_frame

    #=============================
    # END Capture animation data
    #=============================


    #=============================
    # START Add objects to timeline
    #=============================
    def _add_objects_to_timeline(self, objects_to_add, loaded_clip_data=None):
        
        if not objects_to_add and not loaded_clip_data:
            return

        self.ui.track_list_panel.track_tree.blockSignals(True)
        try:
            if loaded_clip_data:
                handle = loaded_clip_data.get("handle")
                try:
                    node = rt.maxOps.getNodeByHandle(handle)
                    if node:
                        layer_name = loaded_clip_data.get("name", f"{node.name}_Clip_Loaded")
                        start_frame = loaded_clip_data.get('start', 0)
                        end_frame = loaded_clip_data.get('end', 100)
                        animation_data = loaded_clip_data.get('animation_data', {"tracks": {}})
                        clip_uid = loaded_clip_data.get("uid")
                        
                        obj_item = self.ui._create_clip_item(node, layer_name, start_frame, end_frame, animation_data, clip_uid=clip_uid)
                        self.ui.track_list_panel.track_tree.addTopLevelItem(obj_item)
                        
                        self.ui.add_tracks_recursively(obj_item, node)
                        
                        self.ui._add_node_hierarchy_recursively(node, obj_item)
                        
                except Exception as e:
                    print(f"Could not load clip for handle {handle}, object may be deleted. Error: {e}")

            elif objects_to_add:
                rt.disableSceneRedraw()
                try:
                    for obj in objects_to_add:
                        
                        
                        animation_data, start_frame, end_frame = self._capture_animation_data(obj)
                                                
                        
                        obj_item = self.ui._create_clip_item(obj, obj.name, start_frame, end_frame, animation_data)
                        
                        
                        self.ui.track_list_panel.track_tree.addTopLevelItem(obj_item)
                                                
                        self.ui.add_tracks_recursively(obj_item, obj)
                        self.ui._add_node_hierarchy_recursively(obj, obj_item)
                finally:
                    rt.enableSceneRedraw()
                    rt.redrawViews()

        finally:
            self.ui.track_list_panel.track_tree.blockSignals(False)
            self.ui.update_track_values()
            self.ui.apply_visibility_filter()
            QtCore.QTimer.singleShot(0, self.ui.sync_scrollbars)
            
    #=============================
    # END Add objects to timeline
    #=============================

    

    #=============================
    # START remove selected layers
    #=============================
    def remove_selected_layers(self):
        selected_items = self.ui.track_list_panel.track_tree.selectedItems()
        if not selected_items: return

        root = self.ui.track_list_panel.track_tree.invisibleRootItem()
        for item in selected_items:
            (item.parent() or root).removeChild(item)

        QtCore.QTimer.singleShot(0, self.ui.sync_scrollbars)
        self._save_timeline_state()
        

    #=============================
    # END remove selected layers
    #=============================

    #=============================
    # START clear all layers
    #=============================
    def clear_all_layers(self):
        self.ui.track_list_panel.track_tree.clear()
        QtCore.QTimer.singleShot(0, self.ui.sync_scrollbars)        
        self._save_timeline_state()
        self.ui.curve_editor.update_value_range()
        

    #=============================
    # END clear all layers
    #=============================


    #=============================
    # START clear all keys
    #=============================
    def _delete_all_keys_from_object(self, max_object):
        """Clears all keys from an object and all its animated sub-sets."""
        def recursive_delete(parent_obj):
            if not parent_obj: return
            if rt.isController(parent_obj):
                controller = parent_obj
                if rt.isProperty(controller, "keys") and controller.keys.count > 0:
                    try:
                        rt.deleteKeys(controller, rt.name('allKeys'))
                        print(f"  -> Cleared keys from: {parent_obj}")
                    except Exception as e:
                        print(f"  -> Could not clear keys from {parent_obj}. Error: {e}")

            if hasattr(parent_obj, 'numSubs') and parent_obj.numSubs > 0:
                try:
                    for name in rt.getSubAnimNames(parent_obj):
                        recursive_delete(rt.getSubAnim(parent_obj, name))
                except Exception: pass
        
        print(f"Clearing all keys from object '{max_object.name}'...")
        with pymxs.undo(True, f"Clear keys for {max_object.name}"):
            recursive_delete(max_object)
        print("Key clearing complete.")
    
    #=============================
    # END clear all keys
    #=============================

    #=============================
    # Bake Motion Mixer to Scene
    #=============================

    def _get_subanim_from_path(self, node, path_string):
        """
        Finds a SubAnim based on its string path from the .clip file.
        This function first cleans up the path to match the actual 3ds Max structure.
        """
        clean_path = path_string.replace('\\', '/')

        if clean_path.startswith("BaseObject/transform/"):
            clean_path = clean_path.replace("BaseObject/", "", 1)
        if "Modified Object" in clean_path:
            clean_path = clean_path.replace("BaseObject/Modified Object", "Modifiers")
        if clean_path.startswith("BaseObject/Object/"):
            parts = clean_path.split('/')
            if len(parts) >= 4:
                clean_path = f"BaseObject/{parts[-1]}"

        
        try:
            parts = clean_path.split('/')
            current_target = node
            i = 0
            while i < len(parts):
                part = parts[i]
                if part == "BaseObject":
                    if hasattr(current_target, 'baseObject'):
                        current_target = current_target.baseObject
                        i += 1; continue
                    else: return None
                elif part == "Modifiers":
                    if i + 1 < len(parts):
                        modifier_name = parts[i + 1]
                        modifier = next((m for m in current_target.modifiers if m.name == modifier_name), None)
                        if modifier:
                            current_target = modifier
                            i += 2; continue
                    return None
                else:
                    part_clean = part.replace(" ", "_")
                    next_target = self.rt.getSubAnim(current_target, self.rt.name(part_clean))
                    if next_target:
                        current_target = next_target
                        i += 1; continue
                    else:
                        return None
            return current_target
        except Exception as e:
            print(f"[CRITICAL SubAnimError] Path='{path_string}' | Cleaned='{clean_path}' | Error: {e}")
            return None
        
    def _get_clip_transform_at_time(self, clip_item, frame):
        """
        [DEBUG VERSION]
        A helper function that returns the full transform values ​​for all nodes
        of a clip at a given frame.
        """
        
        clip_data = clip_item.data(0, QtCore.Qt.ItemDataRole.UserRole)
        if not clip_data:
            print(f"      -> DEBUG_ERROR: No clip_data (cache) found on item '{clip_item.text(0)}'.")
            return {}

        clip_start_mixer = int(clip_item.text(2))
        clip_start_file = int(clip_data['properties'].get('start_frame_absolute', 0))
        local_time = frame - clip_start_mixer
        json_frame_key = str(clip_start_file + local_time)

        transforms = {}
        
        def recursive_extractor(json_node):
            if not json_node: return
            
            handle_id = int(json_node.get("handle_id", "0"))
            world_data = json_node.get('world_animation', {}).get(json_frame_key)
            
            if world_data:
                pos = self.rt.Point3(*world_data['position'])
                rot = self.rt.Quat(*world_data['rotation_quat'])
                scl = self.rt.Point3(*world_data['scale'])
                transforms[handle_id] = {'pos': pos, 'rot': rot, 'scl': scl}
                # print(f"      -> Found transform for handle {handle_id} at local time {local_time}")

            for child_json in json_node.get('children', []):
                recursive_extractor(child_json)

        recursive_extractor(clip_data.get('animation_data'))
        
        if not transforms:
            print(f"      -> DEBUG_WARNING: No transform data found for ANY handle in clip '{clip_item.text(0)}' at frame {frame} (local time: {local_time}).")

        return transforms

            
    def _blend_transform_maps(self, map_from, map_to, alpha):
        """
        [DEBUG VERSION]
        Blends the values ​​of two transform dictionaries.
        """
        result = map_from.copy() 
        all_handles_to = set(map_to.keys())

        for handle in all_handles_to:
            data_to = map_to.get(handle)
            data_from = result.get(handle) 

            if data_from and data_to:
                try:
                    
                    pos = (data_from['pos'] * (1.0 - alpha)) + (data_to['pos'] * alpha)
                    scl = (data_from['scl'] * (1.0 - alpha)) + (data_to['scl'] * alpha)
                    
                    rot = self.rt.Slerp(data_from['rot'], data_to['rot'], alpha)
                    result[handle] = {'pos': pos, 'rot': rot, 'scl': scl}
                except Exception as e:
                    print(f"      -> DEBUG_ERROR: Blend failed for handle {handle}. Error: {e}")
            elif data_to:
                
                identity_pos, identity_scl = self.rt.Point3(0,0,0), self.rt.Point3(1,1,1)
                identity_rot = self.rt.Quat(0,0,0,1)
                
                pos = (identity_pos * (1.0 - alpha)) + (data_to['pos'] * alpha)
                scl = (identity_scl * (1.0 - alpha)) + (data_to['scl'] * alpha)
                rot = self.rt.Slerp(identity_rot, data_to['rot'], alpha)
                result[handle] = {'pos': pos, 'rot': rot, 'scl': scl}

        return result
    
    
    def _clear_keys_in_range(self, node, start_frame, end_frame):
        """Recursively clears all keys in a specified frame range for a node and its hierarchy."""
        if not node:
            return

        def recursive_clear(sub_anim):
            if not sub_anim: return
            
            controller = None
            if rt.isController(sub_anim):
                controller = sub_anim
            elif hasattr(sub_anim, 'controller') and sub_anim.controller:
                controller = sub_anim.controller

            if controller and rt.isProperty(controller, "keys") and controller.keys.count > 0:
                try:
                    
                    keys_to_delete_indices = []
                    for i in range(controller.keys.count):
                        key_time = controller.keys[i].time
                        if start_frame <= key_time <= end_frame:
                            
                            keys_to_delete_indices.append(i + 1)
                    
                    if keys_to_delete_indices:
                        
                        for idx in sorted(keys_to_delete_indices, reverse=True):
                            rt.deleteItem(controller.keys, idx)
                        
                except Exception as e:
                    print(f"  -> Warning: Could not clear keys from {controller}: {e}")

            if hasattr(sub_anim, 'numSubs') and sub_anim.numSubs > 0:
                try:
                    for name in rt.getSubAnimNames(sub_anim):
                        recursive_clear(rt.getSubAnim(sub_anim, name))
                except Exception: pass
        
        print(f"Clearing keys between {start_frame}-{end_frame} for '{node.name}'...")
        recursive_clear(node) 
        if hasattr(node, 'baseObject'):
             recursive_clear(node.baseObject) 
        for mod in node.modifiers:
             recursive_clear(mod)


    def _get_clip_world_transform_at_local_time(self, clip_item, local_time, scene_root_node):
        """
        A new helper function that returns the world transform values ​​of a clip at a specific local time (e.g. frame 0).
        This is crucial for calculating Relative offsets.
        """
        transforms = {}
        clip_data = clip_item.data(0, QtCore.Qt.ItemDataRole.UserRole)
        if not clip_data:
            return transforms

        json_root = clip_data.get('animation_data')
        if not json_root:
            return transforms
            
        clip_start_file = int(clip_data['properties'].get('start_frame_absolute', 0))
        json_frame_key = str(clip_start_file + local_time)

        def recursive_find(json_node, scene_node):
            if not json_node or not scene_node: return
            
            handle = scene_node.handle
            world_data = json_node.get('world_animation', {}).get(json_frame_key)
            
            if world_data:
                pos = self.rt.Point3(*world_data['position'])
                rot = self.rt.Quat(*world_data['rotation_quat'])
                scl = self.rt.Point3(*world_data['scale'])
                transforms[handle] = {'pos': pos, 'rot': rot, 'scl': scl}

            for child_idx in range(min(len(json_node.get('children', [])), len(scene_node.children))):
                recursive_find(json_node['children'][child_idx], scene_node.children[child_idx])

        recursive_find(json_root, scene_root_node)
        return transforms

    def _solve_looping(self, current_local_time, duration, loop_mode, start_val, end_val):
        """
        Calculates both the mapped time and the value offset based on 6 ORT modes.
        """
        if duration <= 0: return 0, None

        # 1. ONCE
        if loop_mode == "Once":
            if 0 <= current_local_time <= duration:
                return current_local_time, None
            return None, None 

        # 2. CONSTANT
        elif loop_mode == "Constant":
            if current_local_time < 0: return 0, None
            if current_local_time > duration: return duration, None
            return current_local_time, None

        # 3. CYCLE
        elif loop_mode == "Cycle":
            return current_local_time % duration, None

        # 4. PING PONG
        elif loop_mode == "PingPong":
            cycle = int(current_local_time / duration)
            rem = current_local_time % duration
            if cycle % 2 == 0:
                return rem, None # Forward
            else:
                return duration - rem, None # Backward

        # 5. LINEAR
        elif loop_mode == "Linear":
            if 0 <= current_local_time <= duration:
                return current_local_time, None
            
            if current_local_time > duration:
                time_past = current_local_time - duration
                def linear_fwd_offset(val_s, val_e):
                    if isinstance(val_s, (float, int)):
                        slope = (val_e - val_s) / float(duration)
                        return slope * time_past
                    elif hasattr(val_s, 'x'): # Point3
                        return ((val_e - val_s) / float(duration)) * time_past
                    return 0
                return duration, linear_fwd_offset

            else: # current_local_time < 0
                time_pre = current_local_time
                def linear_bwd_offset(val_s, val_e):
                    if isinstance(val_s, (float, int)):
                        slope = (val_e - val_s) / float(duration)
                        return slope * time_pre
                    elif hasattr(val_s, 'x'):
                        return ((val_e - val_s) / float(duration)) * time_pre
                    return 0
                return 0, linear_bwd_offset

        # 6. RELATIVE (Loop + Offset Accumulation)
        elif loop_mode == "Relative":
            mapped_time = current_local_time % duration
            cycle_count = int(current_local_time / duration)
            
            if cycle_count == 0: return mapped_time, None
            
            def relative_offset(val_s, val_e):
                delta = val_e - val_s
                if isinstance(delta, (float, int)):
                    return delta * cycle_count
                elif hasattr(delta, 'x'):
                    return delta * cycle_count
                # Quats are tricky for relative loop, skipping here for safety
                return 0
            
            return mapped_time, relative_offset

        return current_local_time, None
    
    # =================================================================
    # === Bake MIXER                                                ===
    # =================================================================
    
    
    # =================================================================
    # === Bake MIXER (Relative) ===
    # =================================================================
    
    def _smoothstep(self, t):
        
        return t * t * (3 - 2 * t)

    def _shortest_path_rot(self, rot_from, rot_to):
        
        dot = (rot_from.x * rot_to.x) + (rot_from.y * rot_to.y) + (rot_from.z * rot_to.z) + (rot_from.w * rot_to.w)
        if dot < 0.0: return -rot_to
        return rot_to

    def set_clip_loop_count(self, clip_item):
        """
        Asks the user for a loop count and extends the clip's end frame accordingly.
        """
        # 1. Get Clip Data to find Original Duration
        clip_data = clip_item.data(0, QtCore.Qt.ItemDataRole.UserRole)
        if not clip_data: return

        src_start = int(clip_data['properties'].get('start_frame_absolute', 0))
        src_end = int(clip_data['properties'].get('end_frame_absolute', 0))
        original_duration = src_end - src_start
        
        if original_duration <= 0:
            print("Error: Invalid clip duration.")
            return

        # 2. Ask User for Count
        count, ok = QtWidgets.QInputDialog.getInt(
            self.ui, 
            "Set Loop Count", 
            f"Original Duration: {original_duration} frames\nHow many loops do you want?", 
            value=1, 
            minValue=1, 
            maxValue=100
        )
        
        if ok:
            # 3. Calculate New End Frame
            # Formula: Start + (Original_Duration * Count)
            current_start_frame = int(clip_item.text(3))
            new_end_frame = current_start_frame + (original_duration * count)
            
            # 4. Update UI
            clip_item.setText(4, str(new_end_frame))
            
            # 5. Auto-set mode to Cycle if it was Once
            current_loop = clip_item.data(5, self.ui.CLIP_LOOP_ROLE)
            if current_loop == "Once" or current_loop is None:
                # Update Combo in UI (Column 5)
                tree = self.ui.motion_mixer_panel.track_tree
                combo = tree.itemWidget(clip_item, 5)
                if combo:
                    combo.setCurrentText("Cycle")
                else:
                    clip_item.setData(5, self.ui.CLIP_LOOP_ROLE, "Cycle")

            # Refresh UI
            self.ui.keyframe_area.update()
            self.ui.sync_scrollbars()
            print(f"Clip extended to {count} loops (End Frame: {new_end_frame})")

    def bake_mixer_to_scene(self):
        print ("\n=== START OF BAKE (Fixed User Logic: Bottom-Up + Relative) ===")
        
        # 1. Basic Setup & Validation
        if self.rt.selection.count != 1:
            QtWidgets.QMessageBox.warning(self.ui, "Selection Error", "Please select the single ROOT object.")
            return
        scene_root_node = self.rt.selection[0]
        root_handle = scene_root_node.handle 
        
        mixer_tree = self.ui.motion_mixer_panel.track_tree
        if mixer_tree.topLevelItemCount() == 0: return

        # Calculate Min/Max Frames
        min_frame, max_frame = float('inf'), float('-inf')
        all_clips_flat = [] 

        for i in range(mixer_tree.topLevelItemCount()):
            track_item = mixer_tree.topLevelItem(i)
            for j in range(track_item.childCount()):
                ci = track_item.child(j)
                try:
                    s_f = int(ci.text(3))
                    e_f = int(ci.text(4))
                    min_frame = min(min_frame, s_f)
                    max_frame = max(max_frame, e_f)
                    
                    all_clips_flat.append({
                        'item': ci,
                        'start': s_f,
                        'end': e_f,
                        'track_index': i,
                        'uid': ci.data(0, self.ui.CLIP_UID_ROLE) or str(uuid.uuid4())
                    })
                except: continue
        
        if max_frame == float('-inf'): return
        
        all_clips_flat.sort(key=lambda x: x['start'])

        self.rt.execute("holdMaxFile()")

        try:
            # 3. Clear Keys
            all_nodes_in_bake = {} 
            def find_all_scene_nodes(json_node, scene_node):
                if not json_node or not scene_node: return
                all_nodes_in_bake[scene_node.handle] = scene_node
                for child_idx in range(min(len(json_node.get('children', [])), len(scene_node.children))):
                    find_all_scene_nodes(json_node['children'][child_idx], scene_node.children[child_idx])

            for clip_info in all_clips_flat:
                clip_data = clip_info['item'].data(0, QtCore.Qt.ItemDataRole.UserRole)
                if clip_data:
                    find_all_scene_nodes(clip_data.get('animation_data'), scene_root_node)
            
            for node in all_nodes_in_bake.values():
                self._clear_keys_in_range(node, min_frame, max_frame)

            # ---------------------------------------------------------
            # PHASE 1: PRE-CALCULATE OFFSETS (Relative)
            # ---------------------------------------------------------
            clip_final_offsets = {} 
            for current_clip_info in all_clips_flat:
                current_item = current_clip_info['item']
                current_uid = current_clip_info['uid']
                start_t = current_clip_info['start']
                
                clip_final_offsets[current_uid] = {'pos': self.rt.Point3(0,0,0), 'rot': self.rt.Quat(0,0,0,1)}
                mode = current_item.data(2, self.ui.CLIP_MODE_ROLE) or "Absolute"
                
                if mode == "Relative":
                    ref_clip_info = None
                    candidates = []
                    for prev in all_clips_flat:
                        if prev['uid'] == current_uid: continue
                        if prev['start'] <= start_t:
                            if prev['end'] >= start_t: candidates.append(prev)
                            elif prev['end'] < start_t: pass 
                    if candidates: ref_clip_info = candidates[-1] 
                    
                    if ref_clip_info:
                        ref_item = ref_clip_info['item']
                        ref_uid = ref_clip_info['uid']
                        ref_start_t = int(ref_item.text(3))
                        ref_local_t = start_t - ref_start_t
                        c_data_ref = ref_item.data(0, QtCore.Qt.ItemDataRole.UserRole)
                        src_s_ref = int(c_data_ref['properties'].get('start_frame_absolute', 0))
                        src_e_ref = int(c_data_ref['properties'].get('end_frame_absolute', 0))
                        dur_ref = src_e_ref - src_s_ref
                        loop_ref = ref_item.data(5, self.ui.CLIP_LOOP_ROLE) or "Once"
                        map_t_ref, offset_func_ref = self._solve_looping(ref_local_t, dur_ref, loop_ref, 0, 0)
                        
                        if map_t_ref is not None:
                            ref_map = self._get_clip_world_transform_at_local_time(ref_item, map_t_ref, scene_root_node)
                            if root_handle in ref_map:
                                raw_ref_world = ref_map[root_handle]
                                ref_offset = clip_final_offsets.get(ref_uid, {'pos': self.rt.Point3(0,0,0), 'rot': self.rt.Quat(0,0,0,1)})
                                final_ref_pos = ref_offset['pos'] + raw_ref_world['pos']
                                if offset_func_ref:
                                    s_map_r = self._get_clip_world_transform_at_local_time(ref_item, 0, scene_root_node)
                                    e_map_r = self._get_clip_world_transform_at_local_time(ref_item, dur_ref, scene_root_node)
                                    if root_handle in s_map_r and root_handle in e_map_r:
                                        p_off_r = offset_func_ref(s_map_r[root_handle]['pos'], e_map_r[root_handle]['pos'])
                                        final_ref_pos += p_off_r
                                final_ref_rot = ref_offset['rot'] * raw_ref_world['rot']
                                curr_map = self._get_clip_world_transform_at_local_time(current_item, 0, scene_root_node)
                                if root_handle in curr_map:
                                    raw_curr = curr_map[root_handle]
                                    new_offset_pos = final_ref_pos - raw_curr['pos']
                                    new_offset_rot = final_ref_rot * self.rt.inverse(raw_curr['rot'])
                                    clip_final_offsets[current_uid] = {'pos': new_offset_pos, 'rot': new_offset_rot}

            # ---------------------------------------------------------
            # PHASE 2: FRAME-BY-FRAME BAKE
            # ---------------------------------------------------------

            with pymxs.animate(True):
                self.rt.disableSceneRedraw()
                progress_dialog = QtWidgets.QProgressDialog("Baking...", "Cancel", min_frame, max_frame, self.ui)
                progress_dialog.setWindowModality(QtCore.Qt.WindowModality.WindowModal)
                
                try:
                    for t in range(min_frame, max_frame + 1):
                        progress_dialog.setValue(t)
                        if progress_dialog.wasCanceled(): raise StopIteration

                        with pymxs.attime(t):
                            final_world_transforms = {} 
                            final_local_values = {}

                            
                            track_count = mixer_tree.topLevelItemCount()
                            for i in reversed(range(track_count)):
                                track_item = mixer_tree.topLevelItem(i)
                                blend_mode = track_item.data(1, self.ui.BLEND_MODE_ROLE) or "Override"
                                if blend_mode == "None": continue 

                                active_clip = next((track_item.child(j) for j in range(track_item.childCount()) if int(track_item.child(j).text(3)) <= t < int(track_item.child(j).text(4))), None)
                                
                                if active_clip:
                                    clip_data = active_clip.data(0, QtCore.Qt.ItemDataRole.UserRole)
                                    json_root = clip_data.get('animation_data')
                                    if not json_root: continue
                                    
                                    # Loop Info
                                    clip_start_frame = int(active_clip.text(3))
                                    raw_local_time = t - clip_start_frame
                                    src_start_file = int(clip_data['properties'].get('start_frame_absolute', 0))
                                    src_end_file = int(clip_data['properties'].get('end_frame_absolute', 0))
                                    source_duration = src_end_file - src_start_file
                                    loop_mode = active_clip.data(5, self.ui.CLIP_LOOP_ROLE) or "Once"
                                    
                                    mapped_local_time, offset_func = self._solve_looping(raw_local_time, source_duration, loop_mode, 0, 0)
                                    if mapped_local_time is None: continue 
                                    json_frame_key = str(int(src_start_file + mapped_local_time))

                                    # Offset Calculation
                                    c_uid = active_clip.data(0, self.ui.CLIP_UID_ROLE)
                                    active_offset = clip_final_offsets.get(c_uid, {'pos': self.rt.Point3(0,0,0), 'rot': self.rt.Quat(0,0,0,1)})
                                    clip_mode = active_clip.data(2, self.ui.CLIP_MODE_ROLE) or "Absolute"

                                    # Fade Logic
                                    alpha = 1.0 
                                    crossfade_data = active_clip.data(0, self.ui.CROSSFADE_ROLE) or {}
                                    clip_end = int(active_clip.text(4))
                                    fade_in = crossfade_data.get('fade_in', {}).get('duration', 0)
                                    fade_out = crossfade_data.get('fade_out', {}).get('duration', 0)
                                    
                                    def smoothstep(x): return x * x * (3 - 2 * x)
                                    
                                    if fade_in > 0:
                                        prog = float(t - clip_start_frame) / float(fade_in)
                                        if prog < 1.0: alpha = smoothstep(prog)
                                        
                                    if fade_out > 0:
                                        prog = float(clip_end - t) / float(fade_out) #         :                          
                                        if prog < 1.0: alpha = min(alpha, smoothstep(prog))
                                        
                                    
                                    if alpha <= 0.001 and blend_mode == "Override" and len(final_world_transforms) > 0: continue 

                                    # Recursive Apply
                                    def apply_layer_recursively(json_node, scene_node, current_alpha, active_offset, clip_mode, final_world_transforms):
                                        if not json_node or not scene_node: return
                                        handle = scene_node.handle
                                        is_root = (scene_node == scene_root_node)

                                        if is_root:
                                            world_data = json_node.get('world_animation', {}).get(json_frame_key)
                                            if world_data:
                                                pos = self.rt.Point3(*world_data['position'])
                                                rot = self.rt.Quat(*world_data['rotation_quat'])
                                                scl = self.rt.Point3(*world_data['scale'])

                                                if clip_mode == "Relative":
                                                    pos = active_offset['pos'] + pos
                                                    rot = active_offset['rot'] * rot

                                                # ***                 Bottom-Up ***
                                                if handle in final_world_transforms:
                                                    #                     (    )
                                                    prev = final_world_transforms[handle]
                                                    if blend_mode == "Additive":
                                                        prev['pos'] += (pos * current_alpha)
                                                        # Additive rot logic approx
                                                        # prev['rot'] *= ... 
                                                    else:
                                                        # Blend (Lerp/Slerp)
                                                        prev['pos'] = (prev['pos'] * (1.0 - current_alpha)) + (pos * current_alpha)
                                                        prev['rot'] = self.rt.Slerp(prev['rot'], rot, current_alpha)
                                                        prev['scl'] = (prev['scl'] * (1.0 - current_alpha)) + (scl * current_alpha)
                                                else:
                                                     
                                                    final_world_transforms[handle] = {'pos': pos, 'rot': rot, 'scl': scl, 'node': scene_node}

                                        # Local Animation Processing
                                        local_anim = json_node.get('local_animation', {})
                                        for path, track_data in local_anim.items():
                                            keys = track_data.get('keys', [])
                                            controller_info = track_data.get('controller_info', {})
                                            val = None
                                            if keys: val = self._get_value_at_time_from_keys(mapped_local_time, keys, controller_info)
                                            if val is None: continue
                                            
                                            if offset_func:
                                                
                                                def get_start_end_values(keys_list, class_type):
                                                    if not keys_list: return 0, 0
                                                    v_start = self._convert_json_to_mxs(keys_list[0]['value'], class_type)
                                                    v_end = self._convert_json_to_mxs(keys_list[-1]['value'], class_type)
                                                    return v_start, v_end
                                                v_s, v_e = get_start_end_values(keys, controller_info.get("class_of", ""))
                                                offset_val = offset_func(v_s, v_e)
                                                try: val = val + offset_val
                                                except: pass

                                            unique_path_id = f"{scene_node.handle}_{path}"
                                            
                                            
                                            if unique_path_id in final_local_values:
                                                prev_val = final_local_values[unique_path_id]['value']
                                                        
                                                try:
                                                    if blend_mode == "Additive":
                                                        final_local_values[unique_path_id]['value'] += (val * current_alpha)
                                                    else:
                                                        final_local_values[unique_path_id]['value'] = (prev_val * (1.0 - current_alpha)) + (val * current_alpha)
                                                except: pass
                                            else:
                                                final_local_values[unique_path_id] = {'path': path, 'value': val, 'node': scene_node}

                                        for child_idx in range(min(len(json_node.get('children', [])), len(scene_node.children))):
                                            apply_layer_recursively(json_node['children'][child_idx], scene_node.children[child_idx], current_alpha, active_offset, clip_mode, final_world_transforms)

                                    apply_layer_recursively(json_root, scene_root_node, alpha, active_offset, clip_mode, final_world_transforms)

                            # Apply to Scene
                            for data in final_world_transforms.values():
                                node = data['node']
                                try:
                                    node.pos = data['pos']
                                    node.rotation = data['rot']
                                except: pass
                            for data in final_local_values.values():
                                subanim = self._get_subanim_from_path(data['node'], data['path'])
                                if subanim:
                                    try:
                                        if hasattr(subanim, 'value'):
                                            subanim.value = self._convert_json_to_mxs(data['value'], str(self.rt.classOf(subanim.value)))
                                    except: pass

                except StopIteration: pass
                finally:
                    if progress_dialog: progress_dialog.close()
                    self.rt.enableSceneRedraw()
                    self.rt.redrawViews()

            print("✅ Bake Complete (Bottom-Up Corrected)!")
            self.ui._force_ui_refresh()

        except Exception as e:
            self.rt.execute("fetchMaxFile()") 
            print(f"An error occurred during bake: {e}")

    #=============================
    # End Bake Motion Mixer to Scene
    #=============================


    def _find_subanim_by_path(self, start_node, path_str):
        """
        Finds a SubAnim based on its string path.
        """
        current_obj = start_node
        path_parts = path_str.split('/')
        
        for part_from_path in path_parts:
            if not current_obj: return None
            
            found_match = False
            try:
                available_names = rt.getSubAnimNames(current_obj)
                normalized_part_from_path = part_from_path.lower().replace(" ", "").replace("_", "")

                for actual_name in available_names:
                    normalized_actual_name = str(actual_name).lower().replace(" ", "").replace("_", "")
                    
                    if normalized_part_from_path == normalized_actual_name:
                        current_obj = rt.getSubAnim(current_obj, actual_name)
                        found_match = True
                        break 
                
                if not found_match:
                    return None
                    
            except Exception:
                return None 
                
        return current_obj

    
    def _get_value_at_time_from_keys(self, time, keys, controller_info):
        """
        Calculates the animation value using linear interpolation and converts it to the correct MAXScript type.
        """
        if not keys: return None
        
        class_name = controller_info.get("class_of", "")
        
        sorted_keys = sorted(keys, key=lambda x: x['time'])
        key1 = next((k for k in reversed(sorted_keys) if k['time'] <= time), None)
        key2 = next((k for k in sorted_keys if k['time'] >= time), None)
        
        if key1 is None: return self._convert_json_to_mxs(sorted_keys[0]['value'], class_name)
        if key2 is None: return self._convert_json_to_mxs(sorted_keys[-1]['value'], class_name)
        if key1 == key2: return self._convert_json_to_mxs(key1['value'], class_name)

        time_diff = key2['time'] - key1['time']
        if time_diff == 0: return self._convert_json_to_mxs(key1['value'], class_name)
        
        alpha = (time - key1['time']) / time_diff
        val1, val2 = key1['value'], key2['value']

        try:
            if isinstance(val1, list) and isinstance(val2, list) and len(val1) == len(val2):
                blended_val = [v1 + (v2 - v1) * alpha for v1, v2 in zip(val1, val2)]
                return self._convert_json_to_mxs(blended_val, class_name)
            else:
                return float(val1) + (float(val2) - float(val1)) * alpha
        except (TypeError, ValueError):
            return self._convert_json_to_mxs(key1['value'], class_name)


    def _convert_json_to_mxs(self, py_value, class_name):
        """
        Converts a Python value (from JSON) to a value understandable to MAXScript.
        """
        try:
            
            if isinstance(py_value, (int, float)):
                return float(py_value)
                
            
            if not isinstance(py_value, list):
                return py_value 

            
            if "Position" in class_name or "Point3" in class_name or "Scale" in class_name:
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


    # ============================
    # === BLEND MODE FUNCTIONS ===
    # ============================

    def create_layer_blend(self):
        """
        Creates a transition between the selected layer and the layer directly below it based on visual overlap.
        """
        selected_items = self.track_list_panel.track_tree.selectedItems()
        if not selected_items or len(selected_items) != 1 or selected_items[0].parent() is not None:
            print("Please select the single TOP layer for the blend.")
            return

        clip_a = selected_items[0]  
        index_a = self.track_list_panel.track_tree.indexOfTopLevelItem(clip_a)

        if index_a == 0: 
            print("No layer found below the selected clip.")
            return

        
        clip_b = self.track_list_panel.track_tree.topLevelItem(index_a - 1)  

        handle_a = clip_a.data(0, QtCore.Qt.ItemDataRole.UserRole)
        handle_b = clip_b.data(0, QtCore.Qt.ItemDataRole.UserRole)

        if handle_a != handle_b:
            print("Error: The layer below does not belong to the same object.")
            return

        try:
            node = rt.maxOps.getNodeByHandle(handle_a)
        except Exception:
            print("Could not find the 3ds Max node.")
            return

        
        self._perform_blend_between_layers(node, clip_a, clip_b)


    def _perform_blend_between_layers(self, node, clip_a, clip_b):
        """
        Combines animation values ​​based on the overlap of two clips and bakes the result onto the object.
        clip_b: Bottom layer (From)
        clip_a: Top layer (To)
        """
        rt = pymxs.runtime

        # === REVISED LOGIC: Calculate blend based on actual overlap ===
        start_a = clip_a.data(0, self.CLIP_START_ROLE)
        end_a = clip_a.data(0, self.CLIP_END_ROLE)
        start_b = clip_b.data(0, self.CLIP_START_ROLE)
        end_b = clip_b.data(0, self.CLIP_END_ROLE)

        
        blend_start_frame = max(start_a, start_b)
        blend_end_frame = min(end_a, end_b)
        
        
        if blend_start_frame >= blend_end_frame:
            print("Error: No valid overlap found between the selected layer and the one below.")
            return

        duration = blend_end_frame - blend_start_frame
        if duration <= 0: return

        print(f"Blending '{node.name}' over {duration} frames (from {blend_start_frame} to {blend_end_frame})...")

        try:
            with pymxs.undo(True, f"Layer Blend for {node.name}"):
                with rt.redraw_disabled():
                    controllers = [c for c in [node.pos.controller, node.rotation.controller, node.scale.controller] if c is not None]

                    for frame in range(blend_start_frame, blend_end_frame + 1):
                        
                        alpha = float(frame - blend_start_frame) / duration
                        
                        
                        from_pos, from_rot, from_scale = self._get_transform_at_time(node, frame, clip_b)
                        
                        to_pos, to_rot, to_scale = self._get_transform_at_time(node, frame, clip_a)

                        
                        blended_pos = rt.Lerp(from_pos, to_pos, alpha)
                        blended_rot = rt.Slerp(from_rot, to_rot, alpha)
                        blended_scale = rt.Lerp(from_scale, to_scale, alpha)
                        
                        
                        with rt.atTime(frame):
                            node.pos = blended_pos
                            node.rotation = blended_rot
                            node.scale = blended_scale
                            for c in controllers:
                                rt.addNewKey(c, frame)
            
            self._force_ui_refresh()
            print("Layer blend completed successfully.")

        except Exception as e:
            print(f"FAILED to perform layer blend. Error: {e}")
            
    def _get_transform_at_time(self, node, frame, clip):
        """A helper function to get the animation value at a specific time"""
        
        with pymxs.runtime.atTime(frame):
            return (node.pos, node.rotation, node.scale)
        
    # ========= End BLEND MODE =========

    def _save_timeline_state(self):
        """Saves the full timeline state using the UID for persistence."""
        if not rt.maxFilePath or not rt.maxFileName:
            print("Scene must be saved first to save timeline data.")
            return

        data_file_path = os.path.splitext(os.path.join(rt.maxFilePath, rt.maxFileName))[0] + ".timeline"

        data_to_save = {
            "clips": [],
            "visibility": {},
            "markers": list(self.ui.markers.values()) 
        }

        tree = self.ui.track_list_panel.track_tree
        for i in range(tree.topLevelItemCount()):
            item = tree.topLevelItem(i)
            handle = item.data(0, self.ui.PARENT_OBJ_ROLE)
            if handle is None: continue

            clip_uid = item.data(0, self.ui.CLIP_UID_ROLE)
            if clip_uid is None:
                clip_uid = str(uuid.uuid4())
                item.setData(0, self.ui.CLIP_UID_ROLE, clip_uid)

            clip_data = {
                "uid": clip_uid,
                "handle": handle,
                "name": item.text(1),
                "start": item.data(0, self.ui.CLIP_START_ROLE),
                "end": item.data(0, self.ui.CLIP_END_ROLE),
                "animation_data": item.data(0, self.ui.CLIP_DATA_ROLE)
            }
            data_to_save["clips"].append(clip_data)

        def get_item_path_with_uid(item):
            path_parts = []
            temp_item = item
            while temp_item:
                uid = temp_item.data(0, self.ui.CLIP_UID_ROLE)
                path_parts.insert(0, uid if uid else temp_item.text(1))
                temp_item = temp_item.parent()
            return "/".join(path_parts)

        iterator = QtWidgets.QTreeWidgetItemIterator(tree, QtWidgets.QTreeWidgetItemIterator.IteratorFlag.All)
        while iterator.value():
            item = iterator.value()
            path = get_item_path_with_uid(item)
            is_visible = (item.icon(0).cacheKey() == self.ui.eye_open_icon.cacheKey())
            data_to_save["visibility"][path] = is_visible
            iterator += 1

        try:
            with open(data_file_path, 'w') as f:
                json.dump(data_to_save, f, indent=4)
            print("Timeline state saved successfully (with UIDs).")
        except Exception as e:
            print(f"FAILED to save timeline state: {e}")


    def _load_timeline_state(self):
        """
        Loads the complete timeline state from the file, supporting multiple layers for one object.
        """
        if not rt.maxFilePath or not rt.maxFileName: return
        data_file_path = os.path.splitext(os.path.join(rt.maxFilePath, rt.maxFileName))[0] + ".timeline"
        if not os.path.exists(data_file_path): return

        try:
            with open(data_file_path, 'r') as f: saved_data = json.load(f)
        except Exception: return

        # Access all UI elements through self.ui
        self.ui.track_list_panel.track_tree.clear()

        saved_markers = saved_data.get("markers", [])
        self.ui.markers = {m['uid']: m for m in saved_markers}

        clips_to_load = saved_data.get("clips", [])
        visibility_map = saved_data.get("visibility", {})

        # Each clip is sent to the add function individually
        for clip_data in clips_to_load:
            self._add_objects_to_timeline(None, loaded_clip_data=clip_data)

        # Use the UID-based path for loading visibility
        if visibility_map:
            def get_item_path_with_uid(item):
                path_parts = []
                temp_item = item
                while temp_item:
                    uid = temp_item.data(0, self.ui.CLIP_UID_ROLE)
                    path_parts.insert(0, uid if uid else temp_item.text(1))
                    temp_item = temp_item.parent()
                return "/".join(path_parts)

            iterator = QtWidgets.QTreeWidgetItemIterator(self.ui.track_list_panel.track_tree, QtWidgets.QTreeWidgetItemIterator.IteratorFlag.All)
            while iterator.value():
                item = iterator.value()
                path = get_item_path_with_uid(item)
                if path in visibility_map and not visibility_map[path]:
                    item.setIcon(0, self.ui.eye_closed_icon)
                iterator += 1
        
        # Call the filter and sync functions from the UI
        self.ui.apply_visibility_filter()
        QtCore.QTimer.singleShot(0, self.ui.sync_scrollbars)


    def add_selected_objects(self):
            print("\n--- '+ Add' button processed by Logic class ---")
            selection = self.rt.selection
            if selection.count == 0:
                print("  -> No objects selected in the viewport.")
                return
            
            self._add_objects_to_timeline(selection)
            self._save_timeline_state()
            self.ui.curve_editor.update_value_range()


    #=============================
    # START Crossfade Logic
    #=============================
    def setup_crossfade_for_clip(self, clip_item, fade_type):
        """
        Displays an input dialog to get Fade-In or Fade-Out duration.
        UNRESTRICTED: Allows setting fade on ANY layer (even the bottom-most).
        """
        if not clip_item or clip_item.parent() is None:
            return

        mixer_tree = self.ui.motion_mixer_panel.track_tree
        current_track = clip_item.parent()
        current_track_index = mixer_tree.indexOfTopLevelItem(current_track)
        
        
        other_clip_uid = None
        
                                              
        if current_track_index < mixer_tree.topLevelItemCount() - 1:
            other_track = mixer_tree.topLevelItem(current_track_index + 1)
            
                
            if other_track.childCount() > 0:
                other_clip = other_track.child(0)
                other_clip_uid = other_clip.data(0, self.ui.CLIP_UID_ROLE)
                
                #UID          
                if not other_clip_uid:
                    other_clip_uid = str(uuid.uuid4())
                    other_clip.setData(0, self.ui.CLIP_UID_ROLE, other_clip_uid)

        
        current_data = clip_item.data(0, self.ui.CROSSFADE_ROLE) or {}
        key_name = f"fade_{fade_type}" # 'fade_in' or 'fade_out'
        initial_duration = current_data.get(key_name, {}).get('duration', 0)

        
        duration, ok = QtWidgets.QInputDialog.getInt(
            self.ui,
            f"Set {fade_type.replace('_', ' ').title()}",
            f"Enter {fade_type.upper()} frames:",
            value=initial_duration,
            minValue=0,
            maxValue=10000
        )

                     
        if ok:
            if duration > 0:
                
                fade_info = {'duration': duration, 'target_uid': other_clip_uid}
                current_data[key_name] = fade_info
                print(f"✅ {key_name} set to {duration} frames.")
            
            elif key_name in current_data:
                
                del current_data[key_name]
                print(f"🚫 {key_name} removed.")

            
            final_data_to_store = current_data if current_data else None
            clip_item.setData(0, self.ui.CROSSFADE_ROLE, final_data_to_store)
            
            
            self.ui.keyframe_area.update()

    #=============================
    # END Crossfade Logic
    #=============================