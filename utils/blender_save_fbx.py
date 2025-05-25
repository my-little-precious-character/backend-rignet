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
    root_name = None
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
    return joint_pos, joint_hier, root_name

def create_joints(joint_pos, joint_hier, root_name, arm_name="RigNetArmature"):
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
        path_mode='COPY',
        embed_textures=True
    )
    print(f"Exported FBX to: {filepath}")

def find_leaves(joint_hier, joint_pos):
    all_parents = set(joint_hier.keys())
    all_children = set(child for children in joint_hier.values() for child in children)
    leaves = all_children - all_parents


    # arm
    leftlowerarm = max(leaves, key=lambda x: joint_pos[x][0])
    rightlowerarm = min(leaves, key=lambda x: joint_pos[x][0])

    # leg
    z_sorted_leaves = sorted(leaves, key=lambda x: joint_pos[x][2])
    z_min_two = z_sorted_leaves[:2]
    if joint_pos[z_min_two[0]][0] < joint_pos[z_min_two[1]][0]:
        rightlowerleg = z_min_two[0]
        leftlowerleg = z_min_two[1]
    else:
        leftlowerleg = z_min_two[0]
        rightlowerleg = z_min_two[1]

    # head
    head = max(leaves, key=lambda x: joint_pos[x][2])

    return {
        'LeftLowerArm': leftlowerarm,
        'RightLowerArm': rightlowerarm,
        'LeftLowerLeg': leftlowerleg,
        'RightLowerLeg': rightlowerleg,
        'Head': head
    }

def find_arm_leg_neck(joint_hier, leaves):
    child_to_parent = {child: parent for parent, children in joint_hier.items() for child in children}

    leftupperarm = child_to_parent.get(leaves['LeftLowerArm'], None)
    rightupperarm = child_to_parent.get(leaves['RightLowerArm'], None)
    leftupperleg = child_to_parent.get(leaves['LeftLowerLeg'], None)
    rightupperleg = child_to_parent.get(leaves['RightLowerLeg'], None)
    neck = child_to_parent.get(leaves['Head'], None)

    return {
        'LeftUpperArm': leftupperarm,
        'RightUpperArm': rightupperarm,
        'LeftUpperLeg': leftupperleg,
        'RightUpperLeg': rightupperleg,
        'Neck': neck
    }

def apply_rename(joint_pos, joint_hier, lower_map, upper_map):
    rename_dict = {}
    for new_name, old_name in lower_map.items():
        rename_dict[old_name] = new_name
    for new_name, old_name in upper_map.items():
        rename_dict[old_name] = new_name

    joint_pos_renamed = {rename_dict.get(name, name): pos for name, pos in joint_pos.items()}

    joint_hier_renamed = {}
    for parent, children in joint_hier.items():
        new_parent = rename_dict.get(parent, parent)
        new_children = [rename_dict.get(child, child) for child in children]
        joint_hier_renamed[new_parent] = new_children

    return joint_pos_renamed, joint_hier_renamed

def make_hand_foot(joint_pos, joint_hier):
    lower_bones = {
        'LeftHand': 'LeftLowerArm',
        'RightHand': 'RightLowerArm',
        'LeftFoot': 'LeftLowerLeg',
        'RightFoot': 'RightLowerLeg'
    }

    for new_bone, lower_bone in lower_bones.items():
        parent_bone = None
        for parent, children in joint_hier.items():
            if lower_bone in children:
                parent_bone = parent
                break
        if parent_bone is None:
            print(f"[Warning] {lower_bone}의 부모를 못찾음. pass")
            continue

        head = joint_pos[parent_bone]
        tail = joint_pos[lower_bone]
        direction = (tail[0] - head[0], tail[1] - head[1], tail[2] - head[2])
        new_tail = (tail[0] + direction[0],
                    tail[1] + direction[1],
                    tail[2] + direction[2])

        joint_pos[new_bone] = tuple(new_tail)
        joint_hier.setdefault(lower_bone, []).append(new_bone)

    return joint_pos, joint_hier

# 자식이 3개인 joints를 찾아서 up, down 배정
def get_up_and_down(joint_pos, joint_hier):
    children_count = {parent: len(children) for parent, children in joint_hier.items()}

    three_children_joints = []
    for parent, count in children_count.items():
        if count == 3:
            pos = joint_pos[parent]
            dist = math.sqrt(pos[0]**2 + pos[1]**2 + pos[2]**2)
            three_children_joints.append({'joint': parent, 'distance': dist})

    three_children_joints = sorted(three_children_joints, key=lambda x: x['distance'])[:2]
    if len(three_children_joints) != 2:
        raise ValueError(f"자식이 3개인 본이 2개가 아닙니다: {len(three_children_joints)}개")

    j0, j1 = three_children_joints[0], three_children_joints[1]
    z0 = joint_pos[j0['joint']][2]
    z1 = joint_pos[j1['joint']][2]
    if z0 < z1:
        down, up = j0['joint'], j1['joint']
    else:
        down, up = j1['joint'], j0['joint']

    return up, down

# down을 가랑이의 중심으로 조정
def adjust_to_middle(joint_pos, joint_hier, down):
    down_children = joint_hier.get(down, [])
    two_lowest_children = sorted(down_children, key=lambda c: joint_pos[c][2])[:2]

    p0 = joint_pos[two_lowest_children[0]]
    p1 = joint_pos[two_lowest_children[1]]
    midpoint = tuple((a + b) / 2 for a, b in zip(p0, p1))

    joint_pos[down] = midpoint

    return joint_pos

from collections import defaultdict

def re_root_tree(joint_hier, new_root):
    # 1. 양방향 그래프 만들기
    bi_graph = defaultdict(list)
    for parent, children in joint_hier.items():
        for child in children:
            bi_graph[parent].append(child)
            bi_graph[child].append(parent)
    
    # 2. new_root를 루트로 트리 구조 만들기 (DFS)
    def build_tree(current, parent):
        children = [node for node in bi_graph[current] if node != parent]
        return {current: [build_tree(child, current) for child in children]} if children else {current: []}
    
    # 3. 트리 형태를 평평하게(원래 joint_hier 형태로) 정리
    def flatten(tree):
        result = {}
        for k, v in tree.items():
            result[k] = [list(child.keys())[0] for child in v]
            for child in v:
                result.update(flatten(child))
        return result

    tree = build_tree(new_root, None)
    return flatten(tree)

def insert_hips_spine_chest(joint_pos, joint_hier, up, down):
    p_down = joint_pos[down]
    p_up = joint_pos[up]
    v = [p_up[i] - p_down[i] for i in range(3)]
    p_hips = tuple(p_down[i] + v[i]/3 for i in range(3))
    p_spine = tuple(p_down[i] + v[i]*2/3 for i in range(3))
    p_chest = tuple(p_down[i] + v[i] for i in range(3))  # == p_up

    hips_name = 'Hips'
    spine_name = 'Spine'
    chest_name = 'Chest'

    # 2. down의 자식 목록에서 up 제거
    down_children = joint_hier.get(down, [])
    new_down_children = [c for c in down_children if c != up]
    joint_hier[down] = new_down_children + [hips_name]  # 기존 자식 + Hips 추가

    # 3. Hips → Spine → Chest → up
    joint_hier[hips_name] = [spine_name]
    joint_hier[spine_name] = [chest_name]
    joint_hier[chest_name] = [up]

    # 4. up의 모든 부모에서 up을 제거 (Chest가 부모가 됨)
    for parent, children in joint_hier.items():
        if parent != chest_name:
            joint_hier[parent] = [c for c in children if c != up]

    # 5. up의 기존 자식들은 그대로 둠 (joint_hier[up]을 변경하지 않음)

    # 6. joint_pos에 새 joint 추가
    joint_pos[hips_name] = p_hips
    joint_pos[spine_name] = p_spine
    joint_pos[chest_name] = p_chest  # == p_up

    return joint_pos, joint_hier
    
def adjust_hips_spine_chest_neck(joint_pos, joint_hier):
    up, down = get_up_and_down(joint_pos, joint_hier)
    
    # joint_pos = adjust_to_middle(joint_pos, joint_hier, down)
    joint_pos = adjust_to_middle(joint_pos, joint_hier, up)

    # 1. down을 root로 만들기
    joint_hier = re_root_tree(joint_hier, down)

    # 2. 3등분하기
    joint_pos, joint_hier = insert_hips_spine_chest(joint_pos, joint_hier, up, down)

    return joint_pos, joint_hier, down

def insert_shoulder(joint_pos, joint_hier, side="Left"):
    """
    side: "Left" 또는 "Right"
    """
    # 키 이름 정하기
    upper = f"{side}UpperArm"
    lower = f"{side}LowerArm"
    shoulder = f"{side}Shoulder"
    chest = "Chest"

    # 1. 좌표: Chest~UpperArm의 중간에 Shoulder 삽입
    p_chest = joint_pos[chest]
    p_upper = joint_pos[upper]
    v = [p_upper[i] - p_chest[i] for i in range(3)]
    p_shoulder = tuple(p_chest[i] + v[i] * 0.5 for i in range(3))
    joint_pos[shoulder] = p_shoulder

    # 2. Chest의 자식에서 UpperArm 제거, 대신 Shoulder 추가
    joint_hier[chest] = [shoulder if c == upper else c for c in joint_hier.get(chest, [])]

    # 3. Shoulder의 자식으로 UpperArm 등록
    joint_hier[shoulder] = [upper]

    # 4. UpperArm의 부모를 Shoulder로 변경 (다른 부모에서 UpperArm 제거)
    for parent, children in joint_hier.items():
        if parent != shoulder:
            joint_hier[parent] = [c for c in children if c != upper]
    # 5. UpperArm의 자식(보통 LowerArm)은 그대로 둠

    return joint_pos, joint_hier

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
    joint_pos, joint_hier, root_name = load_info(RIG_PATH)

    # Rename bone
    lower_map = find_leaves(joint_hier, joint_pos)
    upper_map = find_arm_leg_neck(joint_hier, lower_map)
    joint_pos, joint_hier = apply_rename(joint_pos, joint_hier, lower_map, upper_map)

    # Make hand and foot bones
    joint_pos, joint_hier = make_hand_foot(joint_pos, joint_hier)

    # Adjust hips, spine, check, neck
    joint_pos, joint_hier, root_name = adjust_hips_spine_chest_neck(joint_pos, joint_hier)

    # Adjust shoulder
    joint_hier["Chest"] = ["Neck", "RightUpperArm", "LeftUpperArm"]
    joint_pos, joint_hier = insert_shoulder(joint_pos, joint_hier, side="Left")
    joint_pos, joint_hier = insert_shoulder(joint_pos, joint_hier, side="Right")

    # Summary
    print(f"Root joint: {root_name}")
    print(f"Total joints parsed: {len(joint_pos)}")
    print(f"Hierarchy links: {sum(len(v) for v in joint_hier.values())}")

    # Create joints
    arm = create_joints(joint_pos, joint_hier, root_name)

    # Parent mesh to armature with automatic weights
    bpy.ops.object.select_all(action='DESELECT')
    mesh_obj.select_set(True)
    arm.select_set(True)
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.parent_set(type='ARMATURE_AUTO')

    # Lift up
    min_z = min(pos[2] for pos in joint_pos.values())
    arm.location.z -= min_z

    export_fbx(mesh_obj, arm, FBX_PATH)

if __name__ == "__main__":
    main()
