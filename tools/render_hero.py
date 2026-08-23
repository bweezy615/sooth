"""Render the landing page's hero — the seal, frozen in a block of ice.

    /Applications/Blender.app/Contents/MacOS/Blender --background \
        --factory-startup --python tools/render_hero.py

Why this exists
---------------
Two earlier renders fixed parts of the page and neither fixed the top of it.
`render_panel.py` made the hardware real; `render_environment.py` gave the
panels a floor to stand on, but the slabs were too literal to survive at any
scale and ended up blurred into pure atmosphere. In both cases the render was
supporting an interface. The page still opened on type over a gradient, which
is what "it looks like coding graphics" was describing.

This is the render that is allowed to be the subject. It sits full width above
the desk and carries the one idea the whole product rests on:

    the market is LIQUID -> the slate FREEZES at the seal -> it THAWS at kickoff

So the hero is the middle frame of that sentence. A monolith of ice with the
seal locked inside it, backlit by the single teal source, standing on a wet
black floor. Nothing about it can go out of date, because there is no product
content in it — no numbers, no dates, no team, no price.

Composition is built around the copy, not centred for its own sake
--------------------------------------------------------------------
The mass sits right of centre and the teal source sits behind it, throwing its
glow LEFT across the floor. That left third is deliberately the emptiest,
darkest part of the frame: it is where the headline goes. A centred block would
have forced a scrim over the middle of the image and we would be dimming the
render to rescue the text from it.

What it produces
----------------
`site/public/assets/hero.jpg` — 2000x920, opaque. JPEG rather than PNG on
purpose: it is a photographic subject with no alpha, and Cycles' dither in the
dark floor is exactly what PNG cannot compress (the panel render is 250KB for
far less image).

Techniques that matter for the ice reading as ice
-------------------------------------------------
Clear glass geometry renders as a plastic paperweight. Four things fix it, and
all four are cheap:
  * volume absorption inside the mesh, so thickness reads as colour depth
  * internal fracture planes — real ice is full of them and they are what
    catches a rim light from inside
  * air bubbles, small and irregular, in a loose column
  * surface bump from noise, so the faces are not optically flat
Cycles needs deep transmission bounces to resolve all of that; see reset().

Same house constraints as the other two scripts: Cycles on CPU (this GPU
cannot host it), Standard view transform so the blacks stay at #06080A and the
image seams into the page with no visible edge, and a downsample before
committing -- see the note at the bottom of this file.
"""

import bpy
import math
import os
import random

from mathutils import Euler, Vector

# TWO VIEWS OF ONE SCENE, not two scenes.
#
# /picks needs its own ice — it is the page the whole metaphor is ABOUT, the
# actual sealed slate — and the obvious way to get it would be a second script.
# That would be two lighting rigs to keep in step, and the moment they drifted
# the two pages would be showing two different rooms. So the block, the floor,
# the fractures, the bubbles, the shards and all three lamps are defined once,
# and a view only moves the camera and the frame.
#
#     SOOTH_HERO_VIEW=seal /Applications/Blender.app/Contents/MacOS/Blender \
#         --background --factory-startup --python tools/render_hero.py
#
#   hero — 2.17:1, the whole block standing in the room, right of centre with
#          the left third dark for the headline. A band across the top of the
#          landing page; wider than 16:9 because a 16:9 hero at full width
#          would push the desk entirely off the bottom of the screen.
#   seal — 3.91:1, close on the seal itself. A masthead strip for /picks, so
#          it is read as one detail of the same object rather than as a second
#          picture of the same thing.
VIEWS = {
    "hero": dict(out="hero.png", res=(2000, 920), samples=110,
                 cam=(-0.60, -9.60, 1.50), lens=46, pitch=89.0, yaw=-7.0),
    # Pulled back from the first attempt at (1.15,-4.70) / 52mm, which filled
    # the strip with the disc and cropped it top and bottom — a close-up with
    # no context and nowhere for the page's own heading to go. From here the
    # block occupies roughly the right 45% and the left stays dark room.
    "seal": dict(out="seal.png", res=(1800, 460), samples=110,
                 cam=(1.15, -7.00, 1.45), lens=44, pitch=90.0, yaw=0.0),
    # field — 4.74:1, camera almost on the floor, looking ACROSS the wet
    # surface at the broken-off shards with the block's base cut by the right
    # edge. No seal in frame at all.
    #
    # /tools and /predictor are neither the liquid half nor the frozen half of
    # the system: they are instruments. Giving them the seal plate would have
    # said "this is the sealed slate" on two pages that are not it, and three
    # pages carrying one identical picture reads as a template. This is the
    # same room and the same ice with the subject deliberately absent — the
    # reflection is what carries it.
    "field": dict(out="field.png", res=(1800, 380), samples=110,
                  cam=(-1.60, -5.20, 0.30), lens=40, pitch=88.5, yaw=-10.0),
}
VIEW = VIEWS[os.environ.get("SOOTH_HERO_VIEW", "hero")]

OUT = os.path.join(os.getcwd(), "site/public/assets", VIEW["out"])
RES_X, RES_Y = VIEW["res"]
SAMPLES = VIEW["samples"]

# Composition knob. A full-quality pass is minutes of CPU, and every lighting
# and framing decision above was found by iterating — so there is a cheap mode
# that renders the same scene small and noisy just to check where things sit:
#
#     SOOTH_HERO_PREVIEW=1 /Applications/Blender.app/Contents/MacOS/Blender \
#         --background --factory-startup --python tools/render_hero.py
#
# Never commit a preview: it writes to the same path.
if os.environ.get("SOOTH_HERO_PREVIEW"):
    RES_X, RES_Y = RES_X // 3, RES_Y // 3
    SAMPLES = 24

TEAL = (0.176, 0.831, 0.655)
FROST = (0.749, 0.918, 0.949)

# Half-extents of the block, in metres. Everything that lives INSIDE the ice is
# placed as a fraction of this rather than with its own hand-tuned numbers —
# the first pass used independent ranges and the fracture planes and bubbles
# rendered floating in the room beside the block, which is unmistakable and
# took a render to notice.
HALF = (1.05, 0.85, 1.35)


def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    sc.cycles.device = "CPU"
    sc.cycles.samples = SAMPLES
    sc.cycles.use_denoising = True

    # Transmission is the whole image. At the default 12 total / 12
    # transmission a ray entering the block, crossing two fracture planes and
    # a bubble runs out of bounces and returns black, which shows up as dark
    # blotches in the middle of the ice. These are set high deliberately.
    sc.cycles.max_bounces = 16
    sc.cycles.transmission_bounces = 16
    sc.cycles.glossy_bounces = 8
    sc.cycles.transparent_max_bounces = 16
    sc.cycles.volume_bounces = 2
    # Caustics through ice are almost pure noise at any sample count a CPU can
    # afford here, and they land on a floor that is nearly black anyway.
    sc.cycles.caustics_reflective = False
    sc.cycles.caustics_refractive = False
    # A single bright refracted sample becomes a permanent white speck that
    # denoising smears rather than removes. Clamp indirect only — clamping
    # direct would flatten the teal source itself.
    sc.cycles.sample_clamp_indirect = 6.0

    sc.render.resolution_x = RES_X
    sc.render.resolution_y = RES_Y

    # Detail knob, and the necessary companion to the preview knob above.
    # Preview mode answers "is everything in the right place"; it cannot answer
    # "does this small thing read", because at one third scale and 24 samples a
    # 3px highlight is indistinguishable from denoiser mush. SOOTH_HERO_CROP
    # renders a REGION at full resolution and full samples — the seal is about
    # a tenth of the frame, so it costs about a tenth of the time.
    #
    #     SOOTH_HERO_CROP=0.55,0.82,0.33,0.72 /Applications/.../Blender \
    #         --background --factory-startup --python tools/render_hero.py
    #
    # Order is xmin,xmax,ymin,ymax as 0-1 fractions, y measured from the BOTTOM.
    # Never commit a crop: it writes to the same path.
    crop = os.environ.get("SOOTH_HERO_CROP")
    if crop:
        x0, x1, y0, y1 = [float(v) for v in crop.split(",")]
        sc.render.use_border = True
        sc.render.use_crop_to_border = True
        sc.render.border_min_x, sc.render.border_max_x = x0, x1
        sc.render.border_min_y, sc.render.border_max_y = y0, y1
    sc.render.image_settings.file_format = "PNG"
    sc.render.image_settings.color_mode = "RGB"
    sc.render.filepath = OUT
    sc.view_settings.view_transform = "Standard"
    sc.view_settings.look = "None"

    # Near-black rather than black. Pure black leaves the ice with nothing to
    # refract at glancing angles and the edges of the block disappear.
    world = bpy.data.worlds.new("hero")
    sc.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes["Background"]
    bg.inputs[0].default_value = (0.003, 0.005, 0.007, 1)
    bg.inputs[1].default_value = 1.0
    return sc


def transmission_socket(b):
    """3.6 calls it "Transmission"; 4.x calls it "Transmission Weight"."""
    return "Transmission Weight" if "Transmission Weight" in b.inputs else "Transmission"


def emission_socket(b):
    """3.6 calls it "Emission"; 4.x calls it "Emission Color"."""
    return "Emission Color" if "Emission Color" in b.inputs else "Emission"


def wet_floor():
    """Black, wet, and broken up — not a mirror.

    Lifted from render_environment.py because it was the one part of that
    render that worked at full strength. A smooth reflective plane reads as
    chrome; noise-driven roughness gives the streaked reflection the promos
    have.
    """
    bpy.ops.mesh.primitive_plane_add(size=90, location=(0, 0, 0))
    f = bpy.context.object
    m = bpy.data.materials.new("wet")
    m.use_nodes = True
    nt = m.node_tree
    b = nt.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (0.004, 0.006, 0.008, 1)
    b.inputs["Metallic"].default_value = 0.0

    noise = nt.nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 2.4
    noise.inputs["Detail"].default_value = 9.0
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.36
    ramp.color_ramp.elements[0].color = (0.03, 0.03, 0.03, 1)   # glassy pools
    ramp.color_ramp.elements[1].position = 0.70
    ramp.color_ramp.elements[1].color = (0.30, 0.30, 0.30, 1)   # duller patches
    nt.links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], b.inputs["Roughness"])
    f.data.materials.append(m)
    return f


def ice_material():
    """Ice, not glass: IOR 1.31, and absorbing so thickness has colour."""
    m = bpy.data.materials.new("ice")
    m.use_nodes = True
    nt = m.node_tree
    b = nt.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (0.90, 0.97, 0.99, 1)
    b.inputs["Roughness"].default_value = 0.055
    b.inputs["IOR"].default_value = 1.31
    b.inputs[transmission_socket(b)].default_value = 1.0

    # Surface is not optically flat. Without this the faces mirror the room
    # cleanly and the block reads as acrylic.
    n = nt.nodes.new("ShaderNodeTexNoise")
    n.inputs["Scale"].default_value = 9.0
    n.inputs["Detail"].default_value = 6.0
    n.inputs["Roughness"].default_value = 0.6
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.11
    nt.links.new(n.outputs["Fac"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], b.inputs["Normal"])

    # Volume absorption: this is what makes 3 metres of ice read as ice and 3
    # centimetres read as a window. Faintly cyan, so the deep parts of the
    # block drift toward the one hue rather than toward grey.
    out = nt.nodes["Material Output"]
    vol = nt.nodes.new("ShaderNodeVolumeAbsorption")
    vol.inputs["Color"].default_value = (0.42, 0.78, 0.83, 1)
    vol.inputs["Density"].default_value = 0.34
    nt.links.new(vol.outputs["Volume"], out.inputs["Volume"])
    return m


def monolith():
    """The block. Chamfered and slightly irregular — a cube reads as a cube.

    Seeded: an asset that renders differently every run cannot be regenerated
    to match what is already deployed.
    """
    random.seed(11)
    bpy.ops.mesh.primitive_cube_add(size=2, location=(2.50, 1.60, 1.35))
    ice = bpy.context.object
    ice.scale = HALF
    # location=False MATTERS. Every argument of transform_apply defaults to
    # True, so `transform_apply(scale=True)` also bakes the object's location
    # into its mesh and leaves ice.location at the origin. The block still
    # renders in the right place, but everything placed relative to it — the
    # bubbles, the fractures, the seal — lands at the world origin instead,
    # scattered on the floor beside the ice.
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)

    # Nudge the corners so the silhouette is not a perfect extruded rectangle.
    # The first pass used +/-0.075 on a 2.1m block, which is half a percent and
    # invisible — it still read as a glass display case. This is enough to see.
    for v in ice.data.vertices:
        v.co.x += random.uniform(-0.20, 0.20)
        v.co.y += random.uniform(-0.16, 0.16)
        v.co.z += random.uniform(-0.14, 0.14)

    bev = ice.modifiers.new("bevel", "BEVEL")
    bev.width = 0.085
    bev.segments = 4
    bev.limit_method = "ANGLE"
    ice.data.materials.append(ice_material())
    bpy.ops.object.shade_flat()
    return ice


def shards(mat):
    """Broken-off pieces around the base.

    A single clean block on a clean floor reads as an object photographed in a
    studio. The debris is what says the ice was BROKEN — and each shard also
    picks up the teal and puts a second, smaller specular in the foreground,
    which is most of what stops the bottom third of the frame being dead.
    """
    for _ in range(7):
        s = random.uniform(0.10, 0.30)
        bpy.ops.mesh.primitive_cube_add(
            size=s,
            location=(2.50 + random.uniform(-2.6, 1.5),
                      1.60 + random.uniform(-2.2, 0.9),
                      s * 0.4))
        c = bpy.context.object
        c.scale = (random.uniform(0.6, 1.7), random.uniform(0.6, 1.7),
                   random.uniform(0.4, 1.1))
        c.rotation_euler = (random.uniform(-0.5, 0.5), random.uniform(-0.5, 0.5),
                            random.uniform(0, 3.14))
        bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
        for v in c.data.vertices:
            v.co.x += random.uniform(-0.04, 0.04)
            v.co.y += random.uniform(-0.04, 0.04)
            v.co.z += random.uniform(-0.03, 0.03)
        b = c.modifiers.new("bevel", "BEVEL")
        b.width = 0.012
        b.segments = 2
        c.data.materials.append(mat)
        bpy.ops.object.shade_flat()


def inside(centre, margin, extra=0.0):
    """A point inside the block, keeping `margin` of the half-extent clear.

    `extra` is the radius of whatever is being placed, so a plane or a sphere
    is contained rather than just its origin. This is the guard that was
    missing on the first pass.
    """
    return tuple(
        c + random.uniform(-1, 1) * max(0.0, h * margin - extra)
        for c, h in zip(centre, HALF))


def fractures(parent_loc):
    """Internal cracks. Real ice is full of them, and they are what catches
    the rim light from inside — they do more for the read than the surface
    does. Thin frosted planes rather than modelled splits: at this scale the
    difference is invisible and the cost is not.
    """
    m = bpy.data.materials.new("fracture")
    m.use_nodes = True
    nt = m.node_tree
    b = nt.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (0.93, 0.98, 1.0, 1)
    # Rougher and less transmissive than the block itself. At 0.38/0.86 they
    # were nearly as clear as their surroundings and disappeared; the interior
    # read as one uniform mint fog. These are meant to CATCH light.
    b.inputs["Roughness"].default_value = 0.52
    b.inputs["IOR"].default_value = 1.31
    b.inputs[transmission_socket(b)].default_value = 0.72

    for _ in range(8):
        # A plane of size s, freely rotated, needs s/sqrt(2) of clearance in
        # every axis; half of it is the radius, hence s*0.71 below.
        s = random.uniform(0.30, 0.66)
        bpy.ops.mesh.primitive_plane_add(size=s, location=inside(parent_loc, 0.80, s * 0.71))
        p = bpy.context.object
        p.rotation_euler = (random.uniform(-1.3, 1.3),
                            random.uniform(-1.3, 1.3),
                            random.uniform(0, 3.14))
        bpy.ops.object.transform_apply(location=False, rotation=True, scale=False)
        p.data.materials.append(m)


def bubbles(parent_loc):
    """Trapped air. IOR 1.0 inside ice reads as a void, which is what a bubble
    physically is — modelling them as glass spheres makes marbles.
    """
    m = bpy.data.materials.new("air")
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (1, 1, 1, 1)
    b.inputs["Roughness"].default_value = 0.0
    b.inputs["IOR"].default_value = 1.0
    b.inputs[transmission_socket(b)].default_value = 1.0

    for _ in range(30):
        r = random.uniform(0.012, 0.050)
        bpy.ops.mesh.primitive_ico_sphere_add(
            subdivisions=2, radius=r, location=inside(parent_loc, 0.86, r))
        bpy.context.object.data.materials.append(m)


def haze():
    """Thin fog through the whole room.

    This is the difference between "a 3D object composited on black" and "a
    photograph taken in a room", and it is worth more than any amount of
    material tuning. In clean vacuum a light either hits a surface or is
    invisible, so every earlier pass had the same failure: a lit subject with
    absolutely nothing between it and the camera, which no photograph has.
    With haze the teal source has a visible falloff IN THE AIR, the block
    throws a soft shaft, and the far floor recedes instead of ending.

    Density is very low on purpose, and lower than it looks like it should be.
    At 0.0075 across a 46m box the whole frame washed to a milky teal and the
    corners came up to roughly rgb(20,45,45) — which destroys the two things
    this image has to do: sit seamlessly on a #06080A page, and be black with
    ONE hue in it. Anything you can actually read as fog is a smoke machine.
    This should only be legible as depth.

    Scattering is forward-biased (anisotropy 0.35), which is how water vapour
    behaves — it puts the glow around the source rather than spreading it flat
    across the frame.
    """
    bpy.ops.mesh.primitive_cube_add(size=1, location=(0, 0, 5))
    box = bpy.context.object
    box.scale = (30, 30, 12)
    m = bpy.data.materials.new("haze")
    m.use_nodes = True
    nt = m.node_tree
    out = nt.nodes["Material Output"]
    # The surface must be fully transparent or the box is a frosted cube
    # sitting in front of everything.
    nt.links.remove(out.inputs["Surface"].links[0])
    sc = nt.nodes.new("ShaderNodeVolumeScatter")
    sc.inputs["Color"].default_value = (0.62, 0.86, 0.90, 1)
    sc.inputs["Density"].default_value = 0.0016
    sc.inputs["Anisotropy"].default_value = 0.35
    nt.links.new(sc.outputs["Volume"], out.inputs["Volume"])
    box.data.materials.append(m)
    # Never let the fog volume itself cast or receive a shadow — it only has to
    # be walked through by camera and light rays.
    box.visible_shadow = False
    return box


def seal(parent_loc):
    """The thing that is frozen: the seal, as a disc suspended in the block.

    Faintly emissive rather than a lamp. A real emitter inside a transmissive
    mesh is a firefly factory and it would also read as a light source, when
    what this has to read as is an OBJECT that has been sealed in. The teal
    behind the block does the lighting; this only has to hold its own edge.

    Tilted off-axis: face-on it reads as a logo pasted into the render.
    """
    # TWO materials, and that split is the whole fix.
    #
    # One material could not work. A polished metal in an unlit black room
    # reflects an unlit black room: at metallic 0.92 the disc rendered as a flat
    # dull grey-green circle with no form, no glint and no visible ring — the
    # weakest thing in a frame where it is supposed to be the SUBJECT. Raising
    # its emission instead just made it a bright mint sticker (tried, worse).
    #
    # So the face stops pretending to be polished and becomes dark frosted
    # metal, and the RING carries the one teal hairline — the same treatment
    # the coin mark already gets on the bezel in tools/render_panel.py. The
    # face reads as mass, the ring reads as struck, and the seal finally reads
    # as an object rather than a decal.
    face = bpy.data.materials.new("seal-face")
    face.use_nodes = True
    fnt = face.node_tree
    b = fnt.nodes["Principled BSDF"]
    # Darker than it looks like it should be, and barely emissive. At 0.30 the
    # emission WAS the disc: it rendered as one flat mid-teal circle, lighter
    # than the ice around it and completely featureless. The face is meant to
    # be the dark mass that the ring is bright against.
    b.inputs["Base Color"].default_value = (0.022, 0.062, 0.055, 1)
    b.inputs["Metallic"].default_value = 0.55
    b.inputs["Roughness"].default_value = 0.42
    b.inputs[emission_socket(b)].default_value = (*TEAL, 1.0)
    b.inputs["Emission Strength"].default_value = 0.10

    # Relief. A mathematically flat disc lit by a room with nothing in it
    # renders as a solid circle of one colour no matter what the material says
    # — there is no gradient across it because there is no variation to catch.
    fn = fnt.nodes.new("ShaderNodeTexNoise")
    fn.inputs["Scale"].default_value = 26.0
    fn.inputs["Detail"].default_value = 5.0
    fbump = fnt.nodes.new("ShaderNodeBump")
    fbump.inputs["Strength"].default_value = 0.22
    fnt.links.new(fn.outputs["Fac"], fbump.inputs["Height"])
    fnt.links.new(fbump.outputs["Normal"], b.inputs["Normal"])

    ring = bpy.data.materials.new("seal-ring")
    ring.use_nodes = True
    rb = ring.node_tree.nodes["Principled BSDF"]
    rb.inputs["Base Color"].default_value = (0.06, 0.20, 0.17, 1)
    rb.inputs["Metallic"].default_value = 0.0
    rb.inputs["Roughness"].default_value = 0.30
    rb.inputs[emission_socket(rb)].default_value = (*TEAL, 1.0)
    # Bright enough to be a hairline of light through 40cm of ice, dim enough
    # not to become the scene's second light source. sample_clamp_indirect in
    # reset() is what keeps this from throwing fireflies through the block.
    rb.inputs["Emission Strength"].default_value = 3.6

    centre = (parent_loc[0] - 0.06, parent_loc[1] - 0.12, parent_loc[2] + 0.10)
    # Turned closer to face-on than the first pass (74 deg), which foreshortened
    # it into an ellipse; smooth-shaded, that ellipse read as a ball rather than
    # as a struck disc. Still off-axis, because dead face-on reads as a logo
    # pasted onto the render rather than an object suspended in something.
    rot = (math.radians(62), math.radians(-7), math.radians(14))

    parts = []
    bpy.ops.mesh.primitive_cylinder_add(vertices=96, radius=0.60, depth=0.075,
                                        location=centre, rotation=rot)
    parts.append((bpy.context.object, face))
    # A concentric ring, and it is the whole reason the disc reads as a SEAL:
    # a plain puck has no feature to catch light, so nothing about it says it
    # was struck rather than moulded.
    #
    # OFFSET ALONG THE DISC'S OWN NORMAL, which the first attempt did not do.
    # Placed at the same centre, a torus of tube radius 0.026 sits entirely
    # inside a disc of half-depth 0.0375 — buried, and it rendered as nothing
    # at all. It has to be pushed out past the face to exist.
    normal = Vector((0.0, 0.0, 1.0))
    normal.rotate(Euler(rot, "XYZ"))
    bpy.ops.mesh.primitive_torus_add(
        major_radius=0.44, minor_radius=0.028, major_segments=72,
        minor_segments=12, rotation=rot,
        location=tuple(Vector(centre) + normal * 0.050))
    parts.append((bpy.context.object, ring))

    for p, mat in parts:
        bev = p.modifiers.new("bevel", "BEVEL")
        bev.width = 0.010
        bev.segments = 3
        bev.limit_method = "ANGLE"
        p.data.materials.append(mat)
        # Auto-smooth, not plain shade_smooth. Smoothing a cylinder outright
        # rounds its flat face into the barrel and the disc inflates into a
        # sphere; a 30-degree crease keeps the face flat and smooths only the rim.
        p.data.use_auto_smooth = True
        p.data.auto_smooth_angle = math.radians(30)
        for poly in p.data.polygons:
            poly.use_smooth = True
    return parts[0][0]


def lamp(loc, size, size_y, energy, color, rot):
    """An area light that lights the scene but is never photographed.

    `visible_camera = False` is not a nicety here. The first pass put a 9m
    teal rectangle behind a 2m block and the lamp itself filled a third of the
    frame as a flat glowing slab. Hiding it from camera rays means the source
    can be as large and as close as the falloff needs, which is what makes the
    light wrap rather than spot.
    """
    bpy.ops.object.light_add(type="AREA", location=loc)
    o = bpy.context.object
    o.data.shape = "RECTANGLE"
    o.data.size, o.data.size_y = size, size_y
    o.data.energy = energy
    o.data.color = color
    o.rotation_euler = tuple(math.radians(a) for a in rot)
    o.visible_camera = False
    return o


def lights():
    # THE one source. Behind the block and low, so it reads THROUGH the ice.
    #
    # Aimed DOWN and back rather than forward. Pointed forward it cleared the
    # block and printed its own rectangle on the floor in the foreground —
    # a hard-edged glowing oblong with four corners, which is the single most
    # obvious tell that a scene was lit by a CG area lamp. Now the direct pool
    # lands behind the block, where the block's own shadow cuts into it.
    lamp((1.6, 5.2, 2.30), 4.4, 2.0, 320, TEAL, (-118, 0, -8))

    # The teal that reaches the empty left of the frame: the bounce a wet floor
    # would be throwing anyway, made explicit because a nearly black floor
    # bounces almost nothing on its own.
    #
    # HIGH and far back, not low and near. At (1.0, 3.9, 0.90) this printed a
    # clearly bowed ellipse across the bottom-left of the frame — a pool with a
    # VISIBLE EDGE, which is the same tell as the area lamp's rectangle before
    # it, just curved. A point source close to a plane always draws its own
    # falloff as a shape. Lifted to 3.4m and pushed back behind the block, the
    # same light lands at a shallow enough angle that the pool runs off the
    # bottom of the frame instead of closing into an oval inside it.
    bpy.ops.object.light_add(type="POINT", location=(1.9, 5.4, 3.40))
    g = bpy.context.object
    g.data.shadow_soft_size = 4.6
    g.data.energy = 34
    g.data.color = TEAL
    g.visible_camera = False

    # Cool key from above and camera-left. Gives the block a top edge and a
    # lit front face — without it the whole thing is a backlit silhouette and
    # the fractures never catch anything from the front.
    lamp((-3.2, -3.4, 5.6), 4.5, 2.0, 92, FROST, (46, 0, -40))

    # Narrow rim down the camera-right edge, the specular streak from the
    # promos. Deliberately weak: at full strength it competes with the teal
    # and the frame ends up with two subjects.
    lamp((5.6, 0.4, 2.4), 0.5, 3.6, 60, (0.86, 0.95, 1.0), (90, 0, 96))


def camera():
    """Low and near level, so the block reads as a mass.

    At standing height the camera looks DOWN on it and it reads as an ornament
    on a table. Near level also keeps the floor in the bottom of the frame,
    which is where the reflection lives — the reflection is half of why the
    promos look wet.
    """
    bpy.ops.object.camera_add(location=VIEW["cam"])
    c = bpy.context.object
    c.data.lens = VIEW["lens"]
    # Yawed right so the block lands off-centre without moving the block: this
    # is what opens the dark left third the headline sits in.
    c.rotation_euler = (math.radians(VIEW["pitch"]), 0, math.radians(VIEW["yaw"]))
    bpy.context.scene.camera = c


def vignette():
    """Fall to true black at every edge, in the compositor rather than in CSS.

    A gradient overlay in the page would have to sit above the image, and
    anything that sits above the image also sits above the headline. Doing it
    here means the JPEG's edges already match #06080A and it composites onto
    the page with no seam and no mask.
    """
    sc = bpy.context.scene
    sc.use_nodes = True
    nt = sc.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    rl = nt.nodes.new("CompositorNodeRLayers")
    el = nt.nodes.new("CompositorNodeEllipseMask")
    # Tightened from 1.02 x 1.30. The looser mask left the top edge of the
    # frame at roughly rgb(16,32,34) where the haze catches above the block,
    # against a page ground of #06080A = rgb(6,8,10) — a visibly greener band
    # across the top of the viewport.
    el.width, el.height = 0.96, 1.12
    bl = nt.nodes.new("CompositorNodeBlur")
    # Fractions of the frame, not fixed pixel counts. Blur size in the
    # compositor is absolute pixels, so hard-coding it made the preview mode
    # (one third the width) render a vignette three times tighter than the
    # real one — the cheap check was not checking the same image.
    bl.size_x, bl.size_y = int(RES_X * 0.15), int(RES_Y * 0.21)
    mix = nt.nodes.new("CompositorNodeMixRGB")
    mix.blend_type = "MULTIPLY"
    mix.inputs[0].default_value = 1.0
    comp = nt.nodes.new("CompositorNodeComposite")
    nt.links.new(el.outputs["Mask"], bl.inputs["Image"])
    nt.links.new(rl.outputs["Image"], mix.inputs[1])
    nt.links.new(bl.outputs["Image"], mix.inputs[2])
    nt.links.new(mix.outputs["Image"], comp.inputs["Image"])


def main():
    reset()
    wet_floor()
    ice = monolith()
    loc = tuple(ice.location)
    random.seed(23)
    fractures(loc)
    bubbles(loc)
    seal(loc)
    shards(ice.data.materials[0])
    haze()
    lights()
    camera()
    vignette()
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    bpy.ops.render.render(write_still=True)
    print("RENDERED", OUT)


main()

# AFTER RENDERING, convert before committing. This is a photographic, opaque
# subject, so it is a JPEG — PNG cannot compress Cycles' dither in the dark
# floor and lands around 2MB for the same picture:
#
#     sips -s format jpeg -s formatOptions 74 site/public/assets/hero.png \
#       --out site/public/assets/hero.jpg \
#       && rm site/public/assets/hero.png
#
# Keep the full 2000px width: unlike the panel bezel this draws edge to edge
# on a 1440-1920 viewport and any downsample shows on the ice.
