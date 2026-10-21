"""Model-specific helpers for the MacroRail scan module (built on fusion_helpers)."""
import sys, importlib
sys.path.insert(0, r'C:\Users\Sam\.claude\skills\parametric-cad')
import fusion_helpers as fh
importlib.reload(fh)
from fusion_helpers import *  # noqa

_orig_fix = Sk.fix_coord


def _fix_coord(self, spt, axis, expr, force=True):
    try:
        return _orig_fix(self, spt, axis, expr, force)
    except RuntimeError as err:
        if 'OVER_CONSTRAINT' in str(err):
            return None
        raise


Sk.fix_coord = _fix_coord

BASE = {'x': lambda: root.yZConstructionPlane, 'y': lambda: root.xZConstructionPlane, 'z': lambda: root.xYConstructionPlane}
INPLANE = {'x': ('y', 'z'), 'y': ('x', 'z'), 'z': ('x', 'y')}


def pl(axis, expr, name):
    """Plane normal to `axis` at coordinate expr (offset along +axis)."""
    e = str(expr).strip()
    if e in ('0', '0 mm'):
        return BASE[axis]()
    return plane_offset(BASE[axis](), e, name)


def sk(axis, expr, plname, skname):
    plane = pl(axis, expr, plname)
    return Sk(plane, skname, INPLANE[axis], offset_axis=axis, offset_expr=expr)


def ext(s, op, name, dist, direction=POS, bodies=None, profiles=None):
    return extrude(profiles or s.profiles(), op, name, dist=dist, direction=direction, bodies=bodies)


def ext_sym(s, op, name, dist, bodies=None, profiles=None):
    return extrude(profiles or s.profiles(), op, name, sym=dist, bodies=bodies)


def ext2(s, op, name, d1, d2, bodies=None, profiles=None):
    """Two-sided: d1 along +normal, d2 along -normal."""
    ex = F.extrudeFeatures
    inp = ex.createInput(profiles or s.profiles(), op)
    inp.setTwoSidesExtent(adsk.fusion.DistanceExtentDefinition.create(VI.createByString(d1)),
                          adsk.fusion.DistanceExtentDefinition.create(VI.createByString(d2)))
    if bodies is not None:
        inp.participantBodies = bodies
    f = ex.add(inp)
    f.name = name
    return f


def name_new(feature, name):
    b = feature.bodies.item(0)
    b.name = name
    return b


def name_all(feature, prefix):
    """Name every body a feature created (disjoint lumps become separate bodies)."""
    first = feature.bodies.item(0)
    first.name = '%s 1' % prefix
    n = 2
    for b in root.bRepBodies:
        if b.name.startswith('Body') and b.entityToken != first.entityToken:
            b.name = '%s %d' % (prefix, n)
            n += 1
    return first


def smallest_profile(s):
    best = None
    for i in range(s.s.profiles.count):
        p = s.s.profiles.item(i)
        a = p.areaProperties().area
        if best is None or a < best[0]:
            best = (a, p)
    oc = adsk.core.ObjectCollection.create()
    oc.add(best[1])
    return oc


def profiles_by_area(s, keep):
    """Profiles whose area (mm^2) satisfies keep(area)."""
    oc = adsk.core.ObjectCollection.create()
    for i in range(s.s.profiles.count):
        p = s.s.profiles.item(i)
        if keep(p.areaProperties().area * 100):
            oc.add(p)
    return oc


def revolve(s, axis_line, op, name, bodies=None, profiles=None):
    ri = F.revolveFeatures.createInput(profiles or s.profiles(), axis_line, op)
    ri.setAngleExtent(False, VI.createByString('360 deg'))
    if bodies is not None:
        ri.participantBodies = bodies
    f = F.revolveFeatures.add(ri)
    f.name = name
    return f


def con_ok(s):
    return s.s.isFullyConstrained


def coll(items):
    oc = adsk.core.ObjectCollection.create()
    for i in items:
        oc.add(i)
    return oc


def move_rot(bodies, axis_entity, angle_expr, name):
    mi = F.moveFeatures.createInput2(coll(bodies))
    mi.defineAsRotate(axis_entity, VI.createByString(angle_expr))
    f = F.moveFeatures.add(mi)
    f.name = name
    return f


def move_xyz(bodies, dx, dy, dz, name):
    mi = F.moveFeatures.createInput2(coll(bodies))
    mi.defineAsTranslateXYZ(VI.createByString(dx), VI.createByString(dy), VI.createByString(dz), True)
    f = F.moveFeatures.add(mi)
    f.name = name
    return f


def copy_body(b, name):
    f = F.copyPasteBodies.add(b)
    nb = f.bodies.item(0)
    nb.name = name
    return nb


def repair(sketch):
    """Tie under-constrained circle centres to a constrained centre sharing x or y.
    Works around distance dimensions that Fusion rejects as over-constraining."""
    s = sketch.s if isinstance(sketch, Sk) else sketch
    gc = s.geometricConstraints
    pts = [c.centerSketchPoint for c in s.sketchCurves.sketchCircles]
    for _ in range(4):
        loose = [p for p in pts if not p.isFullyConstrained]
        if not loose:
            break
        for p in loose:
            g = p.geometry
            for q in pts:
                if q is p or not q.isFullyConstrained:
                    continue
                h = q.geometry
                try:
                    if abs(g.x - h.x) < 1e-6:
                        gc.addVerticalPoints(p, q)
                    elif abs(g.y - h.y) < 1e-6:
                        gc.addHorizontalPoints(p, q)
                    else:
                        continue
                except RuntimeError:
                    continue
                if p.isFullyConstrained:
                    break
    return s.isFullyConstrained


def dd_bore(s, ca, cb, d_expr, flat_expr, chord_axis):
    """Double-D: circle + two chords parallel to model axis `chord_axis` (one of s.axes),
    at +/- flat/2 from the centre along the other in-plane axis. Returns the middle profile."""
    c = s.circle(ca, cb, d_expr)
    other = s.other(chord_axis)
    r = ev(d_expr) / 2
    h = ev(flat_expr) / 2
    import math
    w = math.sqrt(max(r * r - h * h, 1e-6))
    lines = []
    ctr = {s.axes[0]: ev(ca), s.axes[1]: ev(cb)}
    for sign in (1, -1):
        pts = []
        for t in (-w, w):
            v = {'x': 0.0, 'y': 0.0, 'z': 0.0}
            if s.off_axis:
                v[s.off_axis] = s.off
            v[chord_axis] = ctr[chord_axis] + t
            v[other] = ctr[other] + sign * h
            pts.append(s.s.modelToSketchSpace(adsk.core.Point3D.create(v['x'], v['y'], v['z'])))
        ln = s.s.sketchCurves.sketchLines.addByTwoPoints(pts[0], pts[1])
        s.c.addCoincident(ln.startSketchPoint, c)
        s.c.addCoincident(ln.endSketchPoint, c)
        g0, g1 = ln.startSketchPoint.geometry, ln.endSketchPoint.geometry
        if abs(g0.y - g1.y) < 1e-6:
            s.c.addHorizontal(ln)
        else:
            s.c.addVertical(ln)
        lines.append(ln)
    s.c.addSymmetry(lines[0].startSketchPoint, lines[1].startSketchPoint, s.axline[chord_axis]) if False else None
    g = lines[0].startSketchPoint.geometry
    dim = s.d.addOffsetDimension(lines[0], lines[1], adsk.core.Point3D.create(g.x + 0.4, g.y + 0.4, 0))
    dim.parameter.expression = flat_expr
    # centre the pair: distance from circle centre to one chord = flat/2
    dm = s.d.addDistanceDimension(c.centerSketchPoint, lines[0].startSketchPoint, s.orient(other),
                                  adsk.core.Point3D.create(g.x + 0.8, g.y + 0.8, 0))
    dm.parameter.expression = '(%s) / 2' % flat_expr
    best = None
    for i in range(s.s.profiles.count):
        p = s.s.profiles.item(i)
        if p.profileLoops.item(0).profileCurves.count == 4:
            best = p
    return coll([best])


def hexagon(s, ca, cb, af_expr, rot=0.0):
    """Fully constrained hexagon (nut pocket), across-flats dimensioned.
    Unlike Sk.hexagon this never mistakes the sketch origin for the polygon centre."""
    ctr = s.P((ca, cb))
    r = ev(af_expr) / 2
    lines = s.s.sketchCurves.sketchLines.addScribedPolygon(ctr, 6, rot, r, False)
    vs, hs = [], []
    for i in range(lines.count):
        ln = lines.item(i)
        if ln.isConstruction:
            continue
        p0, p1 = ln.startSketchPoint.geometry, ln.endSketchPoint.geometry
        if abs(p0.y - p1.y) < 1e-6:
            hs.append(ln)
        elif abs(p0.x - p1.x) < 1e-6:
            vs.append(ln)
    pair = vs if len(vs) == 2 else hs
    if pair is vs:
        s.c.addVertical(pair[0])
    else:
        s.c.addHorizontal(pair[0])
    g = pair[0].startSketchPoint.geometry
    dim = s.d.addOffsetDimension(pair[0], pair[1], adsk.core.Point3D.create(g.x + 0.5, g.y + 0.5, 0))
    dim.parameter.expression = af_expr
    centre = None
    origin = s.s.originPoint
    for p in s.s.sketchPoints:
        if p.geometry.distanceTo(ctr) < 1e-6 and p.entityToken != origin.entityToken:
            centre = p
            break
    if centre is None:
        return lines
    if str(ca).strip() in ('0', '0 mm') and str(cb).strip() in ('0', '0 mm'):
        s.c.addCoincident(centre, origin)
    else:
        s.fix_coord(centre, s.axes[0], ca)
        s.fix_coord(centre, s.axes[1], cb)
        # a dimension Fusion rejected (shared coordinate with an earlier shape): tie instead
        if not centre.isFullyConstrained:
            g = centre.geometry
            for p in s.s.sketchPoints:
                if p.entityToken == centre.entityToken or not p.isFullyConstrained:
                    continue
                h = p.geometry
                try:
                    if abs(g.x - h.x) < 1e-6:
                        s.c.addVerticalPoints(centre, p)
                    elif abs(g.y - h.y) < 1e-6:
                        s.c.addHorizontalPoints(centre, p)
                    else:
                        continue
                except RuntimeError:
                    continue
                if centre.isFullyConstrained:
                    break
    return lines


def ext_from(s, op, name, start, dist, direction=POS, bodies=None, profiles=None):
    """One-side extrude that starts `start` away from the sketch plane (same direction)."""
    ex = F.extrudeFeatures
    inp = ex.createInput(profiles or s.profiles(), op)
    inp.setOneSideExtent(adsk.fusion.DistanceExtentDefinition.create(VI.createByString(dist)), direction)
    inp.startExtent = adsk.fusion.OffsetStartDefinition.create(
        VI.createByString(start if direction == POS else '-(%s)' % start))
    if bodies is not None:
        inp.participantBodies = bodies
    f = ex.add(inp)
    f.name = name
    return f


def plane_angle(axis_entity, angle_expr, ref_plane, name):
    """Plane through an axis, rotated angle from ref_plane (reused if it exists)."""
    p = root.constructionPlanes.itemByName(name)
    if p:
        return p
    inp = root.constructionPlanes.createInput()
    inp.setByAngle(axis_entity, VI.createByString(angle_expr), ref_plane)
    p = root.constructionPlanes.add(inp)
    p.name = name
    return p


def look(target_mm, eye_dir, dist_mm, extent_mm=None, hide=()):
    """Point the viewport camera at target (mm) from direction eye_dir, dist away.
    hide: body names to hide (others shown)."""
    vp = app.activeViewport
    cam = vp.camera
    t = adsk.core.Point3D.create(*[v / 10 for v in target_mm])
    n = sum(c * c for c in eye_dir) ** 0.5
    e = adsk.core.Point3D.create(*[(target_mm[i] + eye_dir[i] / n * dist_mm) / 10 for i in range(3)])
    cam.target = t
    cam.eye = e
    cam.upVector = adsk.core.Vector3D.create(0, 0, 1)
    cam.isSmoothTransition = False
    if extent_mm:
        cam.viewExtents = extent_mm / 10
    vp.camera = cam
    for b in root.bRepBodies:
        b.isLightBulbOn = b.name not in hide
    if extent_mm is None:
        vp.fit()
    vp.refresh()


def report():
    s = []
    for i in range(root.sketches.count):
        k = root.sketches.item(i)
        if not k.isFullyConstrained:
            s.append(k.name)
    return {'unhealthy': unhealthy(), 'underconstrained': s, 'bodies': root.bRepBodies.count, 'timeline': des.timeline.count}
