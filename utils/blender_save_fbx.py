import bpy
import os
import sys

argv = sys.argv
if len(argv) < 2:
    print("Usage: blender --background --python script.py -- <BASE_PATH> <MODEL_ID>")
    sys.exit(1)

WORK_DIR = argv[5] # "/home/younghoc/Downloads/capstone-data/quick_start"
TASK_ID = argv[6]  # "17872"

OBJ_PATH = os.path.join(WORK_DIR, f"{TASK_ID}_mesh.obj")
RIG_PATH = os.path.join(WORK_DIR, f"{TASK_ID}_ori_rig.txt")
FBX_PATH = os.path.join(WORK_DIR, f"{TASK_ID}.fbx")

def cvt_coord(coord):
    a = coord[0]
    b = coord[1]
    c = coord[2]
    return (a, -c, b)

def load_info(info_path):
    def base_name(name):
        return name.split('_dup_')[0]

    joint_pos = {}
    joint_hier = {}
    skin_data = []
    root_name = None
    root_pos = None
    with open(info_path, 'r') as f_info:
        for line in f_info:
            parts = line.strip().split()
            if not parts:
                continue
            key = parts[0]

            if key == 'joints':
                joint_pos[parts[1]] = cvt_coord(tuple(map(float, parts[2:5])))
            elif key == 'root':
                root_name = parts[1]
                root_pos = joint_pos.get(root_name)
            elif key == 'hier':
                parent, child = base_name(parts[1]), base_name(parts[2])
                if parent == child or (parent in joint_hier and child in joint_hier[parent]):
                    continue
                joint_hier.setdefault(parent, []).append(child)
            elif key == 'skin':
                v_idx = int(parts[1])
                weights = []
                for i in range(2, len(parts), 2):
                    bone = parts[i]
                    weight = float(parts[i+1])
                    weights.append((bone, weight))
                skin_data.append((v_idx, weights))
    return joint_pos, joint_hier, skin_data, root_name, root_pos

def create_joints(joint_pos, joint_hier, root_name, root_pos, arm_name="RigNetArmature"):
    # Create armature and enter edit mode
    bpy.ops.object.armature_add(enter_editmode=True)
    arm = bpy.context.active_object
    arm.name = arm_name
    arm.data.name = arm_name + "_data"
    bones = arm.data.edit_bones

    for auto_generated_bone in list(bones):
        bones.remove(auto_generated_bone)

    # Iterative breadth-first joint creation
    this_level = [root_name]
    while this_level:
        next_level = []

        for parent in this_level:
            if parent not in joint_hier:
                continue

            for child in joint_hier[parent]:
                bone = bones.new(child)
                bone.head = joint_pos[parent]
                bone.tail = joint_pos[child]

                if parent != root_name:
                    bone.parent = bones[parent]
                next_level.append(child)

        this_level = next_level

    # Exit edit mode
    bpy.ops.object.mode_set(mode='OBJECT')
    print(f"Created armature '{arm_name}' with {len(joint_pos)} bones.")
    return arm

def merge_mesh_by_distance(mesh_obj, distance=0.0001):
    if bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')

    bpy.ops.object.select_all(action='DESELECT')
    mesh_obj.select_set(True)
    bpy.context.view_layer.objects.active = mesh_obj

    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')

    bpy.ops.mesh.remove_doubles(threshold=distance)

    bpy.ops.object.mode_set(mode='OBJECT')

def decimate_mesh_to_face_count(mesh_obj, target_faces=9000):
    # 1) Object Mode로 전환
    if bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')

    # 2) Face 수 확인
    current_faces = len(mesh_obj.data.polygons)
    print(f"[Decimate] 현재 면 수: {current_faces}, 목표 면 수: {target_faces}")

    # 3) 이미 충분히 적으면 바로 리턴
    if current_faces <= target_faces:
        print("[Decimate] 이미 목표 이하이므로 처리하지 않습니다.")
        return

    # 4) Decimate 비율 계산
    ratio = target_faces / current_faces
    print(f"[Decimate] 적용할 비율: {ratio:.4f}")

    # 5) 오브젝트 선택 및 활성화
    bpy.ops.object.select_all(action='DESELECT')
    mesh_obj.select_set(True)
    bpy.context.view_layer.objects.active = mesh_obj

    # 6) Decimate Modifier 추가
    dec_mod = mesh_obj.modifiers.new(name="Decimate_Auto", type='DECIMATE')
    dec_mod.ratio = ratio
    dec_mod.use_collapse_triangulate = False  # 원한다면 True 로 설정 가능

    # 7) Modifier 적용
    bpy.ops.object.modifier_apply(modifier=dec_mod.name)

    # 8) 결과 리포트
    new_faces = len(mesh_obj.data.polygons)
    print(f"[Decimate] 처리 후 면 수: {new_faces}")

def export_fbx(mesh_obj, arm_obj, filepath):
    # 1) Object Mode로 전환
    if bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')

    # 2) 필요한 객체만 선택
    bpy.ops.object.select_all(action='DESELECT')
    mesh_obj.select_set(True)
    arm_obj.select_set(True)
    bpy.context.view_layer.objects.active = arm_obj

    # 3) FBX Export
    bpy.ops.export_scene.fbx(
        filepath=filepath,
        use_selection=True,
        apply_unit_scale=True,
        bake_space_transform=True,
        object_types={'ARMATURE', 'MESH'},
        mesh_smooth_type='FACE',
        add_leaf_bones=False,
        path_mode='AUTO'
    )
    print(f"Exported FBX to: {filepath}")

def main():
    try:
        bpy.ops.object.mode_set(mode='OBJECT')
    except RuntimeError:
        pass
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)

    for mesh in bpy.data.meshes:
        bpy.data.meshes.remove(mesh)
    for mat in bpy.data.materials:
        bpy.data.materials.remove(mat)

    if not os.path.isfile(OBJ_PATH):
        raise FileNotFoundError(f"OBJ file not found: {OBJ_PATH}")
    bpy.ops.wm.obj_import(filepath=OBJ_PATH)
    mesh_obj = bpy.context.selected_objects[0]
    print(f"Successfully imported: {OBJ_PATH}")

    # Merge by distance
    merge_mesh_by_distance(mesh_obj)

    # Reduce triangles
    decimate_mesh_to_face_count(mesh_obj)

    # Parse rig info
    if not os.path.isfile(RIG_PATH):
        raise FileNotFoundError(f"Rig info not found: {RIG_PATH}")
    joint_pos, joint_hier, skin_data, root_name, root_pos = load_info(RIG_PATH)

    # Summary
    print(f"Root joint: {root_name}, Position: {root_pos}")
    print(f"Total joints parsed: {len(joint_pos)}")
    print(f"Hierarchy links: {sum(len(v) for v in joint_hier.values())}")

    # Create joints
    arm = create_joints(joint_pos, joint_hier, root_name, root_pos)

    # Parent mesh to armature with automatic weights
    bpy.ops.object.select_all(action='DESELECT')
    mesh_obj.select_set(True)
    arm.select_set(True)
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.parent_set(type='ARMATURE_AUTO')

    export_fbx(mesh_obj, arm, FBX_PATH)

if __name__ == "__main__":
    main()
