"""Render the landing hero — the product's own screen, frozen in a slab of ice.

    /Applications/Blender.app/Contents/MacOS/Blender --background \
        --factory-startup --python tools/render_slab.py

    SOOTH_SLAB_PREVIEW=1 ...   # third scale, 24 samples, for composition only

What this is, and why it is not just another view of hero.jpg
-------------------------------------------------------------
hero.jpg is a monolith with the seal locked inside it — the commitment, as an
object. This is the other half of the same idea: the BOARD frozen mid-market, a
landscape slab with a dark screen set into its face. The reference art puts the
wordmark, the strapline and a capability list on that screen.

THE SCREEN IS RENDERED EMPTY, ON PURPOSE
----------------------------------------
Nothing on it is baked in. Text baked into a 2000px raster is soft on a retina
display, cannot be selected, cannot be read by a screen reader, is invisible to
a crawler, and goes stale the first time a word changes — and this screen is
supposed to carry the product's own positioning, which has already been
rewritten twice. So Blender renders the GLASS: the cavity, its teal rim, the
reflections and the ice around it. The page lays real HTML inside the cavity.

That only works if the page knows exactly where the cavity is, so this script
prints the screen's bounding box in normalised screen space (0-1, origin top
left) at the end of the render. Those four numbers go straight into the CSS as
percentages. Re-render and the numbers reprint; if the camera moves, they move
with it, and the overlay cannot silently drift off the glass.

Same house constraints as the other renders: Cycles on CPU, Standard view
transform so the blacks stay at #06080A, ellipse-shaped area lights so their
reflections in the wet floor have no corners, and a downsample before
committing — see the note at the bottom.

Deliberately NOT importing from render_hero.py. The material and lighting
recipes below are the same ones, and sharing them would be tidier, but four
assets already in production (hero, seal, field, env) are reproduced by that
file and a refactor that perturbs any of them costs more than this duplication.
"""

import bpy
import math
import os
import random

from mathutils import Vector

OUT = os.path.join(os.getcwd(), "site/public/assets/slab.png")

# 16:10. The hero sits in a two-column grid beside the headline, so it wants to
# be wider than tall without going letterbox — at 21:9 the slab gets so short
# that the screen inside it cannot hold four lines of type.
RES_X, RES_Y = 2000, 1250
SAMPLES = 120

if os.environ.get("SOOTH_SLAB_PREVIEW"):
    RES_X, RES_Y = RES_X // 3, RES_Y // 3
    SAMPLES = 24

TEAL = (0.176, 0.831, 0.655)
FROST = (0.749, 0.918, 0.949)

# Half-extents of the slab, and of the screen set into its front face.
SLAB = (1.62, 0.34, 1.02)          # x half-width, y half-depth, z half-height
SCREEN = (1.16, 0.66)              # x half-width, z half-height
SCREEN_Y = -SLAB[1] + 0.055        # just inside the front face
CENTRE = (0.0, 0.0, 1.06)          # slab centre, sitting on the floor


def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    sc.cycles.device = "CPU"
    sc.cycles.samples = SAMPLES
    sc.cycles.use_denoising = True
    sc.cycles.max_bounces = 16
    sc.cycles.transmission_bounces = 16
    sc.cycles.glossy_bounces = 8
    sc.cycles.transparent_max_bounces = 16
    sc.cycles.volume_bounces = 2
    sc.cycles.caustics_reflective = False
    sc.cycles.caustics_refractive = False
    sc.cycles.sample_clamp_indirect = 6.0
    sc.render.resolution_x = RES_X
    sc.render.resolution_y = RES_Y
    sc.render.image_settings.file_format = "PNG"
    sc.render.image_settings.color_mode = "RGB"
    sc.render.filepath = OUT
    sc.view_settings.view_transform = "Standard"
    sc.view_settings.look = "None"
    world = bpy.data.worlds.new("slab")
    sc.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes["Background"]
    bg.inputs[0].default_value = (0.003, 0.005, 0.007, 1)
    bg.inputs[1].default_value = 1.0
    return sc


def tsock(b):
    return "Transmission Weight" if "Transmission Weight" in b.inputs else "Transmission"


def esock(b):
    return "Emission Color" if "Emission Color" in b.inputs else "Emission"


def wet_floor():
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
    ramp.color_ramp.elements[0].color = (0.03, 0.03, 0.03, 1)
    ramp.color_ramp.elements[1].position = 0.70
    ramp.color_ramp.elements[1].color = (0.30, 0.30, 0.30, 1)
    nt.links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], b.inputs["Roughness"])
    f.data.materials.append(m)


def ice_material():
    m = bpy.data.materials.new("ice")
    m.use_nodes = True
    nt = m.node_tree
    b = nt.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (0.90, 0.97, 0.99, 1)
    b.inputs["Roughness"].default_value = 0.06
    b.inputs["IOR"].default_value = 1.31
    b.inputs[tsock(b)].default_value = 1.0
    n = nt.nodes.new("ShaderNodeTexNoise")
    n.inputs["Scale"].default_value = 8.0
    n.inputs["Detail"].default_value = 6.0
    n.inputs["Roughness"].default_value = 0.6
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.13
    nt.links.new(n.outputs["Fac"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], b.inputs["Normal"])
    out = nt.nodes["Material Output"]
    vol = nt.nodes.new("ShaderNodeVolumeAbsorption")
    vol.inputs["Color"].default_value = (0.42, 0.78, 0.83, 1)
    vol.inputs["Density"].default_value = 0.55
    nt.links.new(vol.outputs["Volume"], out.inputs["Volume"])
    return m


def slab():
    """The block. Landscape, chamfered, and irregular enough not to read as a
    rendered cube — the corners are pushed around before bevelling."""
    random.seed(19)
    bpy.ops.mesh.primitive_cube_add(size=2, location=CENTRE)
    ice = bpy.context.object
    ice.scale = SLAB
    # location=False: transform_apply defaults every argument to True, and
    # baking the location would leave ice.location at the origin — the mistake
    # that put the hero's bubbles on the floor beside the block.
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    for v in ice.data.vertices:
        v.co.x += random.uniform(-0.09, 0.09)
        v.co.y += random.uniform(-0.05, 0.05)
        v.co.z += random.uniform(-0.07, 0.07)
    bev = ice.modifiers.new("bevel", "BEVEL")
    bev.width = 0.075
    bev.segments = 4
    bev.limit_method = "ANGLE"
    ice.data.materials.append(ice_material())
    bpy.ops.object.shade_flat()
    return ice


def screen():
    """The cavity the page writes into.

    Two planes. The back one is the panel itself — near-black, barely emissive,
    so the glass has something dark to sit in front of rather than a hole. The
    front one is very slightly larger and carries the teal hairline, which is
    the same coin-mark rim the bezel render and the seal both use.

    Returns the four world-space corners of the PANEL, which is what the page
    has to line its text up with.
    """
    cx, _, cz = CENTRE
    y = CENTRE[1] + SCREEN_Y

    rim = bpy.data.materials.new("rim")
    rim.use_nodes = True
    rb = rim.node_tree.nodes["Principled BSDF"]
    rb.inputs["Base Color"].default_value = (0.03, 0.10, 0.09, 1)
    rb.inputs["Roughness"].default_value = 0.30
    rb.inputs[esock(rb)].default_value = (*TEAL, 1.0)
    rb.inputs["Emission Strength"].default_value = 1.1

    panel = bpy.data.materials.new("panel")
    panel.use_nodes = True
    pb = panel.node_tree.nodes["Principled BSDF"]
    pb.inputs["Base Color"].default_value = (0.006, 0.011, 0.014, 1)
    pb.inputs["Roughness"].default_value = 0.55
    pb.inputs["Metallic"].default_value = 0.0
    pb.inputs[esock(pb)].default_value = (*TEAL, 1.0)
    # Just enough glow that the cavity reads as a screen that is ON rather than
    # a black rectangle, without lighting the type the page will lay over it.
    pb.inputs["Emission Strength"].default_value = 0.05

    # rim first, marginally deeper into the ice
    bpy.ops.mesh.primitive_plane_add(size=2, location=(cx, y + 0.012, cz),
                                     rotation=(math.radians(90), 0, 0))
    r = bpy.context.object
    r.scale = (SCREEN[0] + 0.014, SCREEN[1] + 0.014, 1)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    r.data.materials.append(rim)

    bpy.ops.mesh.primitive_plane_add(size=2, location=(cx, y, cz),
                                     rotation=(math.radians(90), 0, 0))
    p = bpy.context.object
    p.scale = (SCREEN[0], SCREEN[1], 1)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    p.data.materials.append(panel)

    return [Vector((cx - SCREEN[0], y, cz + SCREEN[1])),
            Vector((cx + SCREEN[0], y, cz + SCREEN[1])),
            Vector((cx + SCREEN[0], y, cz - SCREEN[1])),
            Vector((cx - SCREEN[0], y, cz - SCREEN[1]))]


def shards(mat):
    """Broken ice at the base. Says the slab was cut out of something, and puts
    a second specular in the foreground so the bottom of the frame is not dead."""
    for _ in range(9):
        s = random.uniform(0.08, 0.24)
        bpy.ops.mesh.primitive_cube_add(
            size=s, location=(random.uniform(-2.3, 2.3),
                              random.uniform(-1.4, 0.9), s * 0.4))
        c = bpy.context.object
        c.scale = (random.uniform(0.6, 1.7), random.uniform(0.6, 1.7),
                   random.uniform(0.4, 1.0))
        c.rotation_euler = (random.uniform(-0.5, 0.5), random.uniform(-0.5, 0.5),
                            random.uniform(0, 3.14))
        bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
        b = c.modifiers.new("bevel", "BEVEL")
        b.width = 0.010
        b.segments = 2
        c.data.materials.append(mat)
        bpy.ops.object.shade_flat()


def haze():
    bpy.ops.mesh.primitive_cube_add(size=1, location=(0, 0, 5))
    box = bpy.context.object
    box.scale = (30, 30, 12)
    m = bpy.data.materials.new("haze")
    m.use_nodes = True
    nt = m.node_tree
    out = nt.nodes["Material Output"]
    nt.links.remove(out.inputs["Surface"].links[0])
    sc = nt.nodes.new("ShaderNodeVolumeScatter")
    sc.inputs["Color"].default_value = (0.62, 0.86, 0.90, 1)
    sc.inputs["Density"].default_value = 0.0016
    sc.inputs["Anisotropy"].default_value = 0.35
    nt.links.new(sc.outputs["Volume"], out.inputs["Volume"])
    box.data.materials.append(m)
    box.visible_shadow = False


def lamp(loc, size, size_y, energy, color, rot, shape="ELLIPSE"):
    """Ellipse by default. A rectangle's reflection in a wet floor is a bright
    oblong WITH CORNERS, which is the clearest tell that a scene was lit by a CG
    area lamp — it had to be chased out of the hero twice, once directly and
    once by reflection."""
    bpy.ops.object.light_add(type="AREA", location=loc)
    o = bpy.context.object
    o.data.shape = shape
    o.data.size, o.data.size_y = size, size_y
    o.data.energy = energy
    o.data.color = color
    o.rotation_euler = tuple(math.radians(a) for a in rot)
    o.visible_camera = False
    return o


def lights():
    # THE one source, behind and above, reading through the top of the slab.
    lamp((0.9, 4.6, 2.9), 5.0, 2.2, 120, TEAL, (-122, 0, -6))
    # Cool key, camera-left and high: gives the slab a lit top edge and a front
    # face, so it is not a backlit silhouette.
    lamp((-3.4, -3.2, 5.2), 4.6, 2.0, 62, FROST, (46, 0, -40))
    # A soft floor bounce, high and far back so its pool runs off the bottom of
    # the frame instead of closing into a visible oval inside it.
    bpy.ops.object.light_add(type="POINT", location=(1.4, 4.6, 3.2))
    g = bpy.context.object
    g.data.shadow_soft_size = 4.6
    g.data.energy = 14
    g.data.color = TEAL
    g.visible_camera = False


def camera():
    """Near level and slightly right of the slab's centre, so the face is close
    to square-on. The overlay is flat HTML — a strongly angled face would need
    a CSS 3D transform to sit on it, and any mismatch between the render's
    perspective and the transform reads instantly as a sticker."""
    bpy.ops.object.camera_add(location=(0.10, -7.15, 1.30))
    c = bpy.context.object
    c.data.lens = 52
    c.rotation_euler = (math.radians(87.6), 0, math.radians(0.9))
    bpy.context.scene.camera = c
    return c


def vignette():
    sc = bpy.context.scene
    sc.use_nodes = True
    nt = sc.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    rl = nt.nodes.new("CompositorNodeRLayers")
    el = nt.nodes.new("CompositorNodeEllipseMask")
    el.width, el.height = 1.02, 1.16
    bl = nt.nodes.new("CompositorNodeBlur")
    # Fractions of the frame, not fixed pixels: hard-coded pixel blur made the
    # preview render a vignette three times tighter than the real one.
    bl.size_x, bl.size_y = int(RES_X * 0.15), int(RES_Y * 0.18)
    mix = nt.nodes.new("CompositorNodeMixRGB")
    mix.blend_type = "MULTIPLY"
    mix.inputs[0].default_value = 1.0
    comp = nt.nodes.new("CompositorNodeComposite")
    nt.links.new(el.outputs["Mask"], bl.inputs["Image"])
    nt.links.new(rl.outputs["Image"], mix.inputs[1])
    nt.links.new(bl.outputs["Image"], mix.inputs[2])
    nt.links.new(mix.outputs["Image"], comp.inputs["Image"])


def report_screen_rect(cam, corners):
    """Print the panel's bounding box in normalised screen space.

    This is the contract between the render and the stylesheet. world_to_camera
    returns y from the BOTTOM; CSS measures from the top, so it is flipped here
    rather than in the page, where the mistake would be invisible.
    """
    from bpy_extras.object_utils import world_to_camera_view
    sc = bpy.context.scene
    pts = [world_to_camera_view(sc, cam, c) for c in corners]
    xs = [p.x for p in pts]
    ys = [1.0 - p.y for p in pts]
    left, right = min(xs), max(xs)
    top, bottom = min(ys), max(ys)
    print("SCREEN_RECT_PCT "
          f"left={left * 100:.2f} top={top * 100:.2f} "
          f"width={(right - left) * 100:.2f} height={(bottom - top) * 100:.2f}")


def main():
    reset()
    wet_floor()
    ice = slab()
    corners = screen()
    random.seed(31)
    shards(ice.data.materials[0])
    haze()
    lights()
    cam = camera()
    vignette()
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    bpy.ops.render.render(write_still=True)
    report_screen_rect(cam, corners)
    print("RENDERED", OUT)


main()

# AFTER RENDERING, convert before committing — photographic, opaque, so JPEG:
#
#     sips -s format jpeg -s formatOptions 76 site/public/assets/slab.png \
#       --out site/public/assets/slab.jpg && rm site/public/assets/slab.png
#
# and take the SCREEN_RECT_PCT line printed above into the .hero-screen rule in
# assets/app.css. Those four numbers are the only thing keeping the live text
# on the glass.
