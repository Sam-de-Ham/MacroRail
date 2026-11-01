"""Product renders of the rail and the scan module (Blender 5.1, Cycles).

    blender -b -P hardware/render/render.py -- <module_meshes> <raw_out> [shot ...]

<module_meshes> holds the module's bodies as STL in Fusion model coordinates, one folder per
pose: rest/, exploded/, tilted/, home/ (see README.md). The rail's printed parts come from
hardware/rail/stl (assembly coordinates); the bought parts are simple primitives built here.
Each shot is written to <raw_out>/<path>.png with a transparent background and the ground
shadow in alpha; finish.py puts it on the studio background.
"""

import math
import os
import sys
from fnmatch import fnmatch
from pathlib import Path

import bpy
import numpy as np
from mathutils import Matrix, Vector

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from shots import SHOTS  # noqa: E402

RAIL_STL = HERE / ".." / "rail" / "stl"
S = 0.001  # model units are mm, the scene is in metres
PARTS = {}  # key -> list of objects
BASE = {}  # object -> rest matrix

# Module model -> rail: the camera looks along the rail from the motor end (rail -X), so the
# module's +X (towards the camera) is rail -X; its base bolts on the carriage's platform holes.
MODULE_TO_RAIL = Matrix.Translation((170, 0, 142)) @ Matrix.Rotation(math.pi, 4, "Z")


# ---------------------------------------------------------------- materials
def material(name, color, metallic=0.0, rough=0.5, coat=0.0, bump=None):
    m = bpy.data.materials.new(name)
    nt = m.node_tree
    p = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
    p.inputs["Base Color"].default_value = (*color, 1)
    p.inputs["Metallic"].default_value = metallic
    p.inputs["Roughness"].default_value = rough
    p.inputs["Coat Weight"].default_value = coat
    if bump:  # thread bands along the object's local Z (lead screw)
        tc = nt.nodes.new("ShaderNodeTexCoord")
        wave = nt.nodes.new("ShaderNodeTexWave")
        wave.bands_direction = "Z"
        wave.inputs["Scale"].default_value = bump
        b = nt.nodes.new("ShaderNodeBump")
        b.inputs["Strength"].default_value = 0.8
        b.inputs["Distance"].default_value = 0.0004
        nt.links.new(tc.outputs["Object"], wave.inputs["Vector"])
        nt.links.new(wave.outputs["Fac"], b.inputs["Height"])
        nt.links.new(b.outputs["Normal"], p.inputs["Normal"])
    return m


MAT = {}


def materials():
    MAT.update(
        printed=material("Printed PETG", (0.20, 0.188, 0.172), rough=0.42),
        steel=material("Steel", (0.78, 0.78, 0.77), metallic=1, rough=0.18),
        satin=material("Satin steel", (0.62, 0.62, 0.62), metallic=1, rough=0.35),
        thread=material(
            "Lead screw", (0.70, 0.70, 0.69), metallic=1, rough=0.3, bump=2 * math.pi / (20 * 0.002)
        ),
        alu=material("Aluminium", (0.50, 0.50, 0.51), metallic=1, rough=0.5),
        brass=material("Brass", (0.80, 0.60, 0.32), metallic=1, rough=0.28),
        black=material("Black", (0.018, 0.018, 0.02), rough=0.38, coat=0.2),
        motorcap=material("Motor cap", (0.05, 0.05, 0.055), metallic=0.6, rough=0.4),
        oxide=material("Black oxide", (0.03, 0.03, 0.03), metallic=1, rough=0.35),
        rubber=material("Seal", (0.01, 0.01, 0.01), rough=0.6),
        pcb=material("PCB", (0.02, 0.025, 0.03), rough=0.45, coat=0.4),
        insect=material("Insect", (0.06, 0.035, 0.02), rough=0.3, coat=0.5),
    )


# ---------------------------------------------------------------- primitives (mm in)
def add(key, o, mat, bevel=0.0, smooth=True):
    o.data.materials.append(MAT[mat])
    if bevel:
        m = o.modifiers.new("bevel", "BEVEL")
        m.width = bevel * S
        m.segments = 3
        m.limit_method = "ANGLE"
        m.harden_normals = True
    if smooth:
        bpy.ops.object.shade_smooth_by_angle(angle=math.radians(35))
    PARTS.setdefault(key, []).append(o)
    BASE[o] = o.matrix_world.copy()
    return o


def cyl(key, p0, p1, r, mat, n=64, bevel=0.0):
    p0, p1 = Vector(p0) * S, Vector(p1) * S
    d = p1 - p0
    bpy.ops.mesh.primitive_cylinder_add(
        vertices=n, radius=r * S, depth=d.length, location=(p0 + p1) / 2
    )
    o = bpy.context.object
    o.rotation_mode = "QUATERNION"
    o.rotation_quaternion = Vector((0, 0, 1)).rotation_difference(d.normalized())
    bpy.context.view_layer.update()
    return add(key, o, mat, bevel)


def box(key, lo, hi, mat, bevel=0.6, rot=None):
    lo, hi = Vector(lo), Vector(hi)
    bpy.ops.mesh.primitive_cube_add(size=1, location=(lo + hi) / 2 * S)
    o = bpy.context.object
    o.scale = (hi - lo) * S
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    if rot:
        o.rotation_euler = [math.radians(a) for a in rot]
    bpy.context.view_layer.update()
    return add(key, o, mat, bevel, smooth=False)


def prism(key, x0, x1, half, chamfer, mat, yc=0, zc=30):
    """A square bar along X with chamfered corners (the NEMA 17 body)."""
    a, b = half, half - chamfer
    ring = [(a, b), (b, a), (-b, a), (-a, b), (-a, -b), (-b, -a), (b, -a), (a, -b)]
    verts = [((x0, yc + y, zc + z)) for y, z in ring] + [((x1, yc + y, zc + z)) for y, z in ring]
    faces = [list(range(7, -1, -1)), list(range(8, 16))] + [
        [i, (i + 1) % 8, 8 + (i + 1) % 8, 8 + i] for i in range(8)
    ]
    me = bpy.data.meshes.new(key)
    me.from_pydata([Vector(v) * S for v in verts], [], faces)
    o = bpy.data.objects.new(key, me)
    bpy.context.collection.objects.link(o)
    bpy.context.view_layer.objects.active = o
    return add(key, o, mat, bevel=0.5, smooth=False)


def hexnut(key, p0, p1, af, mat):
    return cyl(key, p0, p1, af / math.sqrt(3), mat, n=6, bevel=0.3)


def stl(key, path, mat, matrix=None):
    if matrix is None:
        matrix = Matrix()
    bpy.ops.wm.stl_import(filepath=str(path))
    o = bpy.context.object
    o.matrix_world = Matrix.Scale(S, 4) @ matrix
    bpy.context.view_layer.update()
    return add(key, o, mat)


# ---------------------------------------------------------------- the rail
def build_rail():
    for key, f in (
        ("motor_end", "01_motor_end_block"),
        ("far_end", "02_far_end_block"),
        ("carriage", "03_carriage"),
        ("nut_carrier", "04_floating_nut_carrier"),
        ("platform", "05_sample_platform"),
        ("trigger", "06_endstop_trigger"),
    ):
        stl(key, RAIL_STL / (f + ".stl"), "printed")
    for y in (40, -40):  # 2 x 8 x 380 guide rods
        cyl("rods", (0, y, 30), (380, y, 30), 4, "steel")
    cyl("lead_screw", (24.4, 0, 30), (369.4, 0, 30), 4, "thread")
    # NEMA 17 (42 x 42 x 37), face against the motor-end wall at x = 0
    prism("motor", -37, -29, 21, 4.5, "motorcap")
    prism("motor", -29.2, -7.8, 20.7, 4.4, "black")
    prism("motor", -8, -0.2, 21, 4.5, "motorcap")
    cyl("motor", (-0.2, 0, 30), (1.8, 0, 30), 11, "motorcap")
    box("motor", (-34, -6, 1.5), (-26, 6, 9.2), "black", bevel=0.5)  # connector
    for dy, dz in ((15.5, 15.5), (15.5, -15.5), (-15.5, 15.5), (-15.5, -15.5)):
        cyl("motor_bolts", (10, dy, 30 + dz), (13, dy, 30 + dz), 2.75, "oxide", bevel=0.4)
        cyl("motor_bolts", (-5, dy, 30 + dz), (10, dy, 30 + dz), 1.5, "oxide")
    # flexible coupler 5 -> 8, 25 long
    cyl("coupler", (4, 0, 30), (29, 0, 30), 9.3, "alu", bevel=0.6)
    for x in (12, 15, 18, 21):
        cyl("coupler", (x, 0, 30), (x + 0.8, 0, 30), 9.35, "oxide")
    # four SC8UU (30 x 34 x 22, rod 11 below the top), M4 screws from the carriage top
    for x in (130, 210):
        for y in (40, -40):
            box("bearings", (x - 15, y - 17, 19), (x + 15, y + 17, 41), "alu", bevel=1.0)
            for e in (-15, 15):
                cyl(
                    "bearings",
                    (x + e - 0.3 * np.sign(e), y, 30),
                    (x + e + 0.4 * np.sign(e), y, 30),
                    7.5,
                    "rubber",
                )
            for dx in (-9, 9):
                for dy in (-11.5, 11.5):
                    cyl(
                        "bearing_bolts",
                        (x + dx, y + dy, 47),
                        (x + dx, y + dy, 48.3),
                        3.5,
                        "oxide",
                        bevel=0.5,
                    )
                    cyl("bearing_bolts", (x + dx, y + dy, 38), (x + dx, y + dy, 47), 2, "oxide")
    # T8 nut: flange against the carrier plate, boss through it
    cyl("t8_nut", (170, 0, 30), (173.5, 0, 30), 11, "brass", bevel=0.4)
    cyl("t8_nut", (158.5, 0, 30), (170, 0, 30), 5, "brass", bevel=0.4)
    for dy, dz in ((5.5, 5.5), (5.5, -5.5), (-5.5, 5.5), (-5.5, -5.5)):
        cyl("t8_nut", (173.5, dy, 30 + dz), (175.5, dy, 30 + dz), 2.7, "oxide", bevel=0.3)
    # platform bolts (M4 on the 60 x 20 pattern)
    for x in (140, 200):
        for y in (10, -10):
            cyl("platform_bolts", (x, y, 52), (x, y, 54.2), 3.6, "oxide", bevel=0.6)
            cyl("platform_bolts", (x, y, 42), (x, y, 52), 2, "oxide")
    # roller microswitch on the motor-end tab (holes x 30 / 39.4, z 30), roller towards +X
    box("switch", (24.7, -74, 24), (44.7, -68, 34), "black", bevel=0.5)
    for x in (29, 34.7, 40.4):
        box("switch", (x - 1.6, -71.4, 19.5), (x + 1.6, -70.6, 24.2), "satin", bevel=0.1)
    box("switch", (27, -72.5, 34.0), (47.5, -70.5, 34.5), "satin", bevel=0.1, rot=None)
    cyl("switch", (48, -72.6, 33.5), (48, -69.4, 33.5), 2.4, "satin", bevel=0.3)
    for x in (30, 39.4):
        cyl("switch", (x, -67.8, 30), (x, -66.6, 30), 2.75, "oxide", bevel=0.3)
    # trigger screw (M4, head towards the switch) with its lock nut
    cyl("trigger_screw", (82, -67, 30), (86, -67, 30), 3.5, "oxide", bevel=0.5)
    cyl("trigger_screw", (86, -67, 30), (96, -67, 30), 2, "satin")
    hexnut("trigger_screw", (92, -67, 30), (95, -67, 30), 7, "satin")


# ---------------------------------------------------------------- the scan module
def module_material(name):
    if name in ("REF Yaw Motor", "REF Tilt Motor"):
        return "black"
    if name in ("REF KY-024 PCB",):
        return "pcb"
    if name in ("REF KY-024 Components", "REF Hall Sensor", "REF Switch"):
        return "black"
    if name == "REF Insect":
        return "insect"
    if name == "REF 608 Bearing":
        return "steel"
    if name.startswith("REF"):
        return "oxide" if ("Bolt" in name or "Screw" in name) and "Wood" not in name else "satin"
    return "printed"


def build_module(folder):
    for pose in ("rest", "exploded", "tilted", "home"):
        d = Path(folder) / pose
        for f in sorted(d.iterdir(), key=lambda p: p.name):
            name = f.name[:-4].replace("_", " ")
            if name in ("REF Carriage", "REF Objective"):
                continue
            stl(f"m.{pose}.{name}", f, module_material(name), MODULE_TO_RAIL)


# ---------------------------------------------------------------- studio
def studio():
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    prefs = bpy.context.preferences.addons["cycles"].preferences
    for dev in ("OPTIX", "CUDA"):
        try:
            prefs.compute_device_type = dev
            prefs.get_devices()
            if any(d.type == dev for d in prefs.devices):
                for d in prefs.devices:
                    d.use = d.type == dev
                sc.cycles.device = "GPU"
                print("render device", dev)
                break
        except TypeError:
            pass
    sc.cycles.samples = 128
    if os.environ.get("PREVIEW"):  # quick framing checks
        sc.cycles.samples = 24
        sc.render.resolution_percentage = 40
    sc.cycles.use_denoising = True
    sc.cycles.max_bounces = 8
    sc.render.film_transparent = True
    sc.render.image_settings.file_format = "PNG"
    sc.render.image_settings.color_mode = "RGBA"
    sc.view_settings.view_transform = "AgX"
    sc.view_settings.look = "AgX - Base Contrast"
    sc.view_settings.exposure = 0.0
    w = sc.world or bpy.data.worlds.new("World")
    sc.world = w
    nt = w.node_tree
    bg = next(n for n in nt.nodes if n.type == "BACKGROUND")
    tc = nt.nodes.new("ShaderNodeTexCoord")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.35
    ramp.color_ramp.elements[0].color = (0.18, 0.18, 0.18, 1)
    ramp.color_ramp.elements[1].position = 0.75
    ramp.color_ramp.elements[1].color = (1, 1, 1, 1)
    mr = nt.nodes.new("ShaderNodeMapRange")
    mr.inputs["From Min"].default_value = -1
    nt.links.new(tc.outputs["Generated"], sep.inputs[0])
    nt.links.new(sep.outputs["Z"], mr.inputs["Value"])
    nt.links.new(mr.outputs["Result"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], bg.inputs["Color"])
    bg.inputs["Strength"].default_value = 0.4
    bpy.ops.mesh.primitive_plane_add(size=20, location=(0, 0, 0))
    ground = bpy.context.object
    ground.is_shadow_catcher = True
    cam = bpy.data.objects.new("Camera", bpy.data.cameras.new("Camera"))
    sc.collection.objects.link(cam)
    sc.camera = cam
    cam.data.lens = 85
    cam.data.sensor_width = 36
    cam.data.clip_start = 0.01
    lights = []
    for name, power, size in (
        ("key", 42, 1.2),
        ("fill", 10, 1.6),
        ("top", 16, 1.4),
        ("rim", 24, 0.8),
    ):
        ld = bpy.data.lights.new(name, "AREA")
        ld.energy = power
        ld.size = size
        lo = bpy.data.objects.new(name, ld)
        lo.visible_camera = False
        sc.collection.objects.link(lo)
        lights.append(lo)
    return cam, lights, ground


def place_lights(lights, target, view):
    az = math.atan2(view.y, view.x)
    for lo, (daz, el, dist) in zip(
        lights, ((-55, 50, 1.6), (75, 22, 1.8), (0, 82, 1.5), (175, 35, 1.6)), strict=True
    ):
        a, e = az + math.radians(daz), math.radians(el)
        lo.location = target + dist * Vector(
            (math.cos(a) * math.cos(e), math.sin(a) * math.cos(e), math.sin(e))
        )
        lo.rotation_euler = (target - lo.location).to_track_quat("-Z", "Y").to_euler()


# ---------------------------------------------------------------- framing
def world_points(objs):
    pts = []
    dg = bpy.context.evaluated_depsgraph_get()
    for o in objs:
        me = o.evaluated_get(dg).to_mesh()
        v = np.empty(len(me.vertices) * 3)
        me.vertices.foreach_get("co", v)
        v = v.reshape(-1, 3)
        m = np.array(o.matrix_world)
        pts.append(v @ m[:3, :3].T + m[:3, 3])
        o.evaluated_get(dg).to_mesh_clear()
    return np.vstack(pts)


def frame(cam, pts, view, window, w, h):
    """Points the camera along -view and sets distance and lens shift so the points fill the
    window (u0, v0, u1, v1, fractions of the image)."""
    target = Vector(pts.min(0) + pts.max(0)) / 2
    fwd = -view.normalized()
    rot = fwd.to_track_quat("-Z", "Y").to_matrix()
    right, up = np.array(rot.col[0]), np.array(rot.col[1])
    f = cam.data.lens / cam.data.sensor_width
    big = max(w, h)  # the sensor width spans the larger image side
    u0, v0, u1, v1 = window
    dist = 1.0
    for _ in range(12):
        loc = np.array(target) - np.array(fwd) * dist
        rel = pts - loc
        z = rel @ np.array(fwd)
        u = f * (rel @ right) / z * big / w
        v = f * (rel @ up) / z * big / h
        k = max((u.max() - u.min()) / (u1 - u0), (v.max() - v.min()) / (v1 - v0))
        dist *= k**0.9
    cam.location = Vector(loc)
    cam.rotation_euler = rot.to_euler()
    cam.data.sensor_fit = "AUTO"
    cam.data.shift_x = ((u.max() + u.min()) / 2 - ((u0 + u1) / 2 - 0.5)) * w / big
    cam.data.shift_y = ((v.max() + v.min()) / 2 - ((v0 + v1) / 2 - 0.5)) * h / big
    return target


# ---------------------------------------------------------------- shots
def render(cam, lights, ground, out, shot):
    sc = bpy.context.scene
    show = [p for p in shot["show"] if not p.startswith("!")]
    hide = [p[1:] for p in shot["show"] if p.startswith("!")]
    keys = {
        k
        for k in PARTS
        if any(fnmatch(k, p) for p in show) and not any(fnmatch(k, p) for p in hide)
    }
    offsets = shot.get("offsets", {})
    flip = (
        Matrix.Rotation(math.pi, 4, "X") if shot.get("flip") else Matrix()
    )  # upside down, as on the bench
    for key, objs in PARTS.items():
        for o in objs:
            o.hide_render = key not in keys
            d = Vector(offsets.get(key, (0, 0, 0))) * S
            o.matrix_world = flip @ Matrix.Translation(d) @ BASE[o]
    bpy.context.view_layer.update()
    w, h = shot["size"]
    sc.render.resolution_x, sc.render.resolution_y = w, h
    view = Vector(shot["view"])
    pts = world_points([o for k in keys for o in PARTS[k]])
    ground.location.z = pts[:, 2].min() - 0.0001  # the lowest part stands on the floor
    lo, hi = shot.get("focus", ((-1e9,) * 3, (1e9,) * 3))  # frame only this box (mm)
    pts = pts[np.all((pts >= np.array(lo) * S) & (pts <= np.array(hi) * S), axis=1)]
    target = frame(cam, pts, view, shot.get("window", (0.06, 0.08, 0.94, 0.92)), w, h)
    place_lights(lights, target, view)
    sc.render.filepath = str(Path(out) / shot["path"])
    bpy.ops.render.render(write_still=True)


def main():
    args = sys.argv[sys.argv.index("--") + 1 :]
    module_dir, out, only = args[0], args[1], set(args[2:])
    bpy.ops.wm.read_factory_settings(use_empty=True)
    materials()
    cam, lights, ground = studio()
    build_rail()
    build_module(module_dir)
    for shot in SHOTS:
        if not only or shot["path"] in only or Path(shot["path"]).name[:-4] in only:
            render(cam, lights, ground, out, shot)


if __name__ == "__main__":
    main()
