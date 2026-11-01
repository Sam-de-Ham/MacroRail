"""Helpers for building parametric models with the Fusion 360 API.

Scripts in this folder define run(context) and import this module through scanhelp.py:

    from scanhelp import *

    def run(_):
        param('cam_D', '80', 'MEAS D1 camera diameter')
        s = Sk(root.yZConstructionPlane, 'CC 01 Ring', ('y', 'z'))
        s.circle('0', 'axis_H', 'cam_ringOD')
        f = extrude(s.profiles(), NEW, 'CC Ring', sym='cam_W')
        f.bodies.item(0).name = 'Camera Collar'

Geometry is given in MODEL coordinates as parameter expressions per axis; the helper converts to
sketch space, adds H/V constraints and drives every coordinate with a dimension whose expression
is the parameter expression -> sketches come out fully constrained and parametric.
Negative coordinates: write '-(expr)'; the dimension gets 'expr'.
Zero coordinates: write '0'; the point is made coincident with the projected model axis.
"""
import adsk.core, adsk.fusion

app = adsk.core.Application.get()
des = adsk.fusion.Design.cast(app.activeProduct)
root = des.rootComponent
um = des.unitsManager
F = root.features
VI = adsk.core.ValueInput
H = adsk.fusion.DimensionOrientations.HorizontalDimensionOrientation
Vt = adsk.fusion.DimensionOrientations.VerticalDimensionOrientation
NEW = adsk.fusion.FeatureOperations.NewBodyFeatureOperation
JOIN = adsk.fusion.FeatureOperations.JoinFeatureOperation
CUT = adsk.fusion.FeatureOperations.CutFeatureOperation
INT = adsk.fusion.FeatureOperations.IntersectFeatureOperation
POS = adsk.fusion.ExtentDirections.PositiveExtentDirection
NEG = adsk.fusion.ExtentDirections.NegativeExtentDirection
AX = {'x': adsk.core.Vector3D.create(1, 0, 0), 'y': adsk.core.Vector3D.create(0, 1, 0), 'z': adsk.core.Vector3D.create(0, 0, 1)}


def ev(expr):
    """Evaluate an expression (mm units) -> internal cm."""
    return um.evaluateExpression(str(expr), 'mm')


def param(name, expr, comment=''):
    """Create or update a user parameter (mm)."""
    p = des.userParameters.itemByName(name)
    if p:
        p.expression = str(expr)
        p.comment = comment
    else:
        des.userParameters.add(name, VI.createByString(str(expr)), 'mm', comment)


def plane_offset(base, expr, name):
    """Named offset construction plane (reused if it already exists)."""
    pl = root.constructionPlanes.itemByName(name)
    if pl:
        return pl
    inp = root.constructionPlanes.createInput()
    inp.setByOffset(base, VI.createByString(str(expr)))
    pl = root.constructionPlanes.add(inp)
    pl.name = name
    return pl


class Sk:
    """Sketch wrapper. `axes` = the two in-plane model axes, e.g. ('y','z') for a YZ-type plane.
    For offset planes pass offset_axis + offset_expr so model points land on the plane."""

    def __init__(self, plane, name, axes, offset_axis=None, offset_expr='0'):
        self.s = root.sketches.add(plane)
        self.s.name = name
        self.axes = axes
        self.off_axis = offset_axis
        self.off = ev(offset_expr)
        self.c = self.s.geometricConstraints
        self.d = self.s.sketchDimensions
        # projected model axes lying in the plane (construction) for zero-coordinate constraints
        self.axline = {}
        for a in axes:
            ca = {'x': root.xConstructionAxis, 'y': root.yConstructionAxis, 'z': root.zConstructionAxis}[a]
            ents = self.s.project(ca)
            ln = adsk.fusion.SketchLine.cast(ents.item(0))
            ln.isConstruction = True
            self.axline[a] = ln

    def P(self, coords):
        v = {'x': 0.0, 'y': 0.0, 'z': 0.0}
        if self.off_axis:
            v[self.off_axis] = self.off
        for a, e in zip(self.axes, coords):
            v[a] = ev(e)
        return self.s.modelToSketchSpace(adsk.core.Point3D.create(v['x'], v['y'], v['z']))

    def orient(self, axis):
        xd = self.s.xDirection
        return H if abs(xd.dotProduct(AX[axis])) > 0.9 else Vt

    def other(self, axis):
        return self.axes[1] if axis == self.axes[0] else self.axes[0]

    def fix_coord(self, spt, axis, expr, force=True):
        """Drive the `axis` model coordinate of sketch point spt with expr (distance from origin)."""
        e = str(expr).strip()
        if e in ('0', '0 mm'):
            # coordinate zero -> point lies on the projected axis line of the OTHER in-plane axis
            self.c.addCoincident(spt, self.axline[self.other(axis)])
            return
        o = self.s.originPoint
        g = spt.geometry
        tp = adsk.core.Point3D.create(g.x / 2 + 0.3, g.y / 2 + 0.3, 0)
        try:
            dim = self.d.addDistanceDimension(o, spt, self.orient(axis), tp)
        except RuntimeError as err:
            if 'OVER_CONSTRAINT' in str(err):
                return  # already determined by existing constraints
            raise
        dim.parameter.expression = e[2:-1] if e.startswith('-(') else e.lstrip('-')

    def poly(self, verts):
        """Closed polyline. verts: list of (expr_a, expr_b) in self.axes order. Returns lines
        (line i starts at vertex i; the last line closes back to vertex 0)."""
        pts = [self.P(v) for v in verts]
        lines = []
        L = self.s.sketchCurves.sketchLines
        first = None
        prev = None
        for i in range(len(pts)):
            a = prev if prev else pts[i]
            b = pts[i + 1] if i < len(pts) - 1 else first
            ln = L.addByTwoPoints(a, b)
            if first is None:
                first = ln.startSketchPoint
            prev = ln.endSketchPoint
            lines.append(ln)
        for ln in lines:
            p0, p1 = ln.startSketchPoint.geometry, ln.endSketchPoint.geometry
            if abs(p0.y - p1.y) < 1e-6:
                self.c.addHorizontal(ln)
            elif abs(p0.x - p1.x) < 1e-6:
                self.c.addVertical(ln)
        # dimension each vertex coordinate; a coordinate shared with the previous vertex is
        # already tied by the H/V constraint of the connecting line
        for i, (ln, v) in enumerate(zip(lines, verts)):
            sp_ = ln.startSketchPoint
            for k, (a, e) in enumerate(zip(self.axes, v)):
                if str(verts[i - 1][k]).strip() == str(e).strip():
                    continue
                self.fix_coord(sp_, a, e)
        return lines

    def rect(self, a0, a1, b0, b1):
        return self.poly([(a0, b0), (a1, b0), (a1, b1), (a0, b1)])

    def circle(self, ca, cb, dia_expr):
        c = self.s.sketchCurves.sketchCircles.addByCenterRadius(self.P((ca, cb)), ev(dia_expr) / 2)
        self.fix_coord(c.centerSketchPoint, self.axes[0], ca)
        self.fix_coord(c.centerSketchPoint, self.axes[1], cb)
        g = c.centerSketchPoint.geometry
        dim = self.d.addDiameterDimension(c, adsk.core.Point3D.create(g.x + ev(dia_expr), g.y + ev(dia_expr), 0))
        dim.parameter.expression = dia_expr
        return c

    def hexagon(self, ca, cb, af_expr, rot=0.0):
        """Hexagon (nut pocket / nut), across-flats dimensioned.
        rot=0 -> flats perpendicular to sketch x; rot=math.pi/6 -> flats parallel to sketch x."""
        ctr = self.P((ca, cb))
        r = ev(af_expr) / 2
        L = self.s.sketchCurves.sketchLines
        lines = L.addScribedPolygon(ctr, 6, rot, r, False)  # r = apothem (half across-flats)
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
            self.c.addVertical(pair[0])
        else:
            self.c.addHorizontal(pair[0])
        g = pair[0].startSketchPoint.geometry
        dim = self.d.addOffsetDimension(pair[0], pair[1], adsk.core.Point3D.create(g.x + 0.5, g.y + 0.5, 0))
        dim.parameter.expression = af_expr
        for i in range(self.s.sketchPoints.count):
            p = self.s.sketchPoints.item(i)
            if p.geometry.distanceTo(ctr) < 1e-6:
                self.fix_coord(p, self.axes[0], ca)
                self.fix_coord(p, self.axes[1], cb)
                break
        return lines

    def align_vertical(self, p1, p2):
        """Tie two sketch points (e.g. circle centres sharing a coordinate) when a second
        distance dimension would be rejected."""
        if abs(p1.geometry.x - p2.geometry.x) < 1e-6:
            self.c.addVerticalPoints(p1, p2)
        else:
            self.c.addHorizontalPoints(p1, p2)

    def profiles(self):
        oc = adsk.core.ObjectCollection.create()
        for i in range(self.s.profiles.count):
            oc.add(self.s.profiles.item(i))
        return oc

    def hex_profiles(self):
        oc = adsk.core.ObjectCollection.create()
        for i in range(self.s.profiles.count):
            pr = self.s.profiles.item(i)
            if pr.profileLoops.item(0).profileCurves.count == 6:
                oc.add(pr)
        return oc


def body(name):
    for b in root.bRepBodies:
        if b.name == name:
            return b
    return None


def extrude(profiles, op, name, sym=None, dist=None, direction=POS, through=None, bodies=None):
    """sym='expr' -> symmetric full length. dist='expr' + direction -> one side.
    through='both'/'one' -> through-all (UNRELIABLE for splitting cuts; prefer sym with a big expr).
    bodies=[...] -> participant bodies (always set this for cuts once reference bodies exist)."""
    ex = F.extrudeFeatures
    inp = ex.createInput(profiles, op)
    if sym is not None:
        inp.setSymmetricExtent(VI.createByString(sym), True)
    elif through == 'both':
        inp.setTwoSidesExtent(adsk.fusion.ThroughAllExtentDefinition.create(), adsk.fusion.ThroughAllExtentDefinition.create())
    elif through == 'one':
        inp.setOneSideExtent(adsk.fusion.ThroughAllExtentDefinition.create(), direction)
    else:
        inp.setOneSideExtent(adsk.fusion.DistanceExtentDefinition.create(VI.createByString(dist)), direction)
    if bodies is not None:
        if any(b is None for b in bodies):
            raise ValueError('participant body not found (check body names)')
        inp.participantBodies = bodies
    f = ex.add(inp)
    f.name = name
    return f


def revolve_cut(sk, axis_line, name, bodies):
    ri = F.revolveFeatures.createInput(sk.s.profiles.item(0), axis_line, CUT)
    ri.setAngleExtent(False, VI.createByString('360 deg'))
    ri.participantBodies = bodies
    f = F.revolveFeatures.add(ri)
    f.name = name
    return f


def edges_parallel(bdy, axis, test):
    """Linear edges of body parallel to `axis` whose midpoint (mm) satisfies test(x, y, z)."""
    oc = adsk.core.ObjectCollection.create()
    for e in bdy.edges:
        g = e.geometry
        if not isinstance(g, adsk.core.Line3D):
            continue
        sp, ep = g.startPoint, g.endPoint
        v = sp.vectorTo(ep)
        if v.length < 1e-6:
            continue
        v.normalize()
        if abs(v.dotProduct(AX[axis])) < 0.999:
            continue
        m = (10 * (sp.x + ep.x) / 2, 10 * (sp.y + ep.y) / 2, 10 * (sp.z + ep.z) / 2)
        if test(*m):
            oc.add(e)
    return oc


def circular_edges(bdy, radius_mm):
    oc = adsk.core.ObjectCollection.create()
    for e in bdy.edges:
        g = e.geometry
        if isinstance(g, (adsk.core.Arc3D, adsk.core.Circle3D)) and abs(g.radius * 10 - radius_mm) < 1e-3:
            oc.add(e)
    return oc


def fillet(edges, radius_expr, name):
    fi = F.filletFeatures.createInput()
    fi.addConstantRadiusEdgeSet(edges, VI.createByString(radius_expr), True)
    f = F.filletFeatures.add(fi)
    f.name = name
    return f


def chamfer(edges, dist_expr, name):
    ci = F.chamferFeatures.createInput2()
    ci.chamferEdgeSets.addEqualDistanceChamferEdgeSet(edges, VI.createByString(dist_expr), False)
    f = F.chamferFeatures.add(ci)
    f.name = name
    return f


def unhealthy():
    """Names of unhealthy timeline features (looks inside groups; groups themselves report odd states)."""
    Hs = adsk.fusion.FeatureHealthStates.HealthyFeatureHealthState
    bad = []
    tl = des.timeline
    for i in range(tl.count):
        it = tl.item(i)
        if it.isGroup:
            g = adsk.fusion.TimelineGroup.cast(it)
            for j in range(g.count):
                if g.item(j).healthState != Hs:
                    bad.append(g.item(j).name)
        elif it.healthState != Hs:
            bad.append(it.name)
    return bad


def interference(include_coincident=False):
    bodies = adsk.core.ObjectCollection.create()
    for b in root.bRepBodies:
        bodies.add(b)
    inp = des.createInterferenceInput(bodies)
    inp.areCoincidentFacesIncluded = include_coincident
    res = des.analyzeInterference(inp)
    return [(r.entityOne.name, r.entityTwo.name, round(r.interferenceBody.volume * 1000, 3)) for r in res]


def stress_test(changes):
    """Temporarily set {param: expr}, report unhealthy features, then restore."""
    up = des.userParameters
    orig = {k: up.itemByName(k).expression for k in changes}
    for k, v in changes.items():
        up.itemByName(k).expression = v
    bad = unhealthy()
    for k, v in orig.items():
        up.itemByName(k).expression = v
    return bad, unhealthy()


def section(plane, name, offset_cm=0.0):
    sa = des.analyses.sectionAnalyses
    for a in sa:
        a.isLightBulbOn = False
    a = sa.add(sa.createInput(plane, offset_cm))
    a.name = name
    return a
