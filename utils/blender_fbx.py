import bpy
import os
import sys

######## configuration ########

argv = sys.argv
if len(argv) < 2:
    print("Usage: blender --background --python script.py -- <BASE_PATH> <MODEL_ID>")
    sys.exit(1)

BASE_PATH = argv[0] # "/home/younghoc/Downloads/capstone-data/quick_start"
MODEL_ID = argv[1]  # "17872"
OBJ_PATH     = os.path.join(BASE_PATH, f"{MODEL_ID}_ori.obj")
RIG_TXT_PATH = os.path.join(BASE_PATH, f"{MODEL_ID}_ori_rig.txt")
OUTPUT_FBX   = os.path.join(BASE_PATH, f"{MODEL_ID}.fbx")

######## utilities ########

def clear_scene():
    """Remove all objects from the scene."""
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)


def import_obj(filepath):
    """Import an OBJ file using Blender's built-in importer."""
    if bpy.app.version >= (4, 0, 0):
        bpy.ops.wm.obj_import(filepath=filepath)
    else:
        bpy.ops.import_scene.obj(filepath=filepath)
    return bpy.context.selected_objects[0]


def parse_rig_txt(path):
    """Parse .txt rig file: convert Maya coords to Blender bone coords (swap and flip axes)."""
    joint_pos = {}
    joint_hier = {}
    skin_data = []
    root_name = None
    with open(path, 'r') as f:
        for line in f:
            parts = line.split()
            if not parts:
                continue
            tag = parts[0]
            if tag == 'joints' and len(parts) >= 5:
                name = parts[1]
                x, y, z = map(float, parts[2:5])
                # Flip Maya axes: use x stays, y->z, z->-y, then invert both to fix bone upside-down
                # New mapping: x->x, y->-z, z->y
                joint_pos[name] = (x, -z, y)
            elif tag == 'root':
                root_name = parts[1]
            elif tag == 'hier' and len(parts) >= 3:
                parent, child = parts[1], parts[2]
                joint_hier.setdefault(parent, []).append(child)
            elif tag == 'skin' and len(parts) >= 3:
                skin_data.append(parts[1:])
    return root_name, joint_pos, joint_hier, skin_data

######## main ########

def main():
    # 1) Clear scene
    clear_scene()

    # 2) Import mesh
    mesh_obj = import_obj(OBJ_PATH)
    mesh_obj.name = "ImportedMesh"

    # 3) Parse rig
    root_name, joint_pos, joint_hier, skin_data = parse_rig_txt(RIG_TXT_PATH)
    if not root_name or root_name not in joint_pos:
        sys.exit(f"Root joint '{root_name}' not found.")

    # 4) Create armature
    bpy.ops.object.armature_add()
    armature = bpy.context.active_object
    armature.name = "RigArmature"
    bpy.context.view_layer.objects.active = armature
    bpy.ops.object.mode_set(mode='EDIT')

    # Remove default bone
    for b in list(armature.data.edit_bones):
        armature.data.edit_bones.remove(b)

    # Create bones recursively
    def create_bone(name):
        bone = armature.data.edit_bones.new(name)
        bone.head = joint_pos[name]
        # Tail 1cm along Blender Z axis
        bone.tail = (joint_pos[name][0], joint_pos[name][1], joint_pos[name][2] + 0.01)
        return bone

    bones = {root_name: create_bone(root_name)}
    queue = [root_name]
    while queue:
        parent = queue.pop(0)
        for child in joint_hier.get(parent, []):
            bone = create_bone(child)
            bone.parent = bones[parent]
            bone.use_connect = True
            bones[child] = bone
            queue.append(child)

    bpy.ops.object.mode_set(mode='OBJECT')

    # 5) Skin binding
    # Clear existing groups
    for vg in mesh_obj.vertex_groups:
        mesh_obj.vertex_groups.remove(vg)
    # Assign weights
    for entry in skin_data:
        vid = int(entry[0])
        for i in range(1, len(entry), 2):
            jn = entry[i]
            w = float(entry[i+1])
            if w <= 0.001:
                continue
            vg = mesh_obj.vertex_groups.get(jn) or mesh_obj.vertex_groups.new(name=jn)
            vg.add([vid], w, 'REPLACE')

    # 6) Parent mesh to armature
    bpy.ops.object.select_all(action='DESELECT')
    mesh_obj.select_set(True)
    armature.select_set(True)
    bpy.context.view_layer.objects.active = armature
    bpy.ops.object.parent_set(type='ARMATURE_AUTO')

    # 7) Export FBX with embedded textures
    bpy.ops.export_scene.fbx(
        filepath=OUTPUT_FBX,
        use_selection=False,
        apply_scale_options='FBX_SCALE_ALL',
        bake_anim=False,
        add_leaf_bones=False,
        embed_textures=True,
        path_mode='COPY',
        axis_forward='Y',
        axis_up='Z'
    )
    print(f"✅ Exported FBX with textures: {OUTPUT_FBX}")

if __name__ == '__main__':
    main()
