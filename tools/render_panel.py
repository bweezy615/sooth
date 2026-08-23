"""Render the landing page's hardware in Blender, headless.

    /Applications/Blender.app/Contents/MacOS/Blender --background \
        --factory-startup --python tools/render_panel.py

Why this exists
---------------
The landing page's five panels were CSS: linear-gradients for the housing,
box-shadows for the bevel, a skewed overlay for the "glass". At a glance it
reads as what it is — drawn by a stylesheet. The owner's own brand promos are
photoreal renders (black room, one teal, product encased in ice, wet floor),
and a gradient cannot get to that. So the housing is now an actual render and
the CSS only positions it.

What it produces
----------------
`site/public/assets/panel.png` — ONE bezel, straight on, transparent inside the
screen aperture and transparent outside the frame. The page lays it over each
live iframe and lets the existing transforms scale and rotate it. One asset,
five panels, no per-panel art and no change to the desk's geometry or routing.

Design constraints it has to satisfy
------------------------------------
* Straight-on orthographic. Any baked perspective would fight the CSS 3D
  transforms that angle the outer panels.
* Alpha in the middle. The screen is a hole, not a dark fill — the live page
  shows through it.
* Physically dark. It sits on #06080A and must not read as a grey rectangle,
  so the housing is near-black with the light doing the work.
* One teal. A single cool rim light on the top edge, matching --brand, is the
  only hue in the frame.

Cycles on CPU because this machine's GPU cannot host it; a still at this size
takes about five minutes, which is fine for an asset built once.

AFTER RENDERING, downsample before committing. The raw 1904px render is ~1.6MB
— Cycles leaves enough dither in the dark housing that PNG cannot compress it
well, and that is far too heavy for a landing page. The bezel draws at 952px on
screen, so 1400px is still ~1.5x and costs 250KB:

    sips -Z 1400 site/public/assets/panel.png --out /tmp/p.png \
      && mv /tmp/p.png site/public/assets/panel.png

(sips is macOS built-in. It preserves the alpha channel; verify colortype 6.
No pngquant/optipng/Pillow on this machine, and sips here has no webp encoder.)
"""

import bpy
import math
import os

OUT = os.path.join(os.getcwd(), "site/public/assets/panel.png")

# Aspect matches the .screen box in index.html (920x680) plus the bezel margin.
RES_X, RES_Y = 1904, 1424
SAMPLES = 128

TEAL = (0.176, 0.831, 0.655, 1.0)   # #2DD4A7 linearised closely enough
FROST = (0.749, 0.918, 0.949, 1.0)  # #BFEAF2


def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    sc.cycles.device = "CPU"
    sc.cycles.samples = SAMPLES
    sc.cycles.use_denoising = True
    sc.render.resolution_x = RES_X
    sc.render.resolution_y = RES_Y
    sc.render.film_transparent = True          # alpha outside the housing
    sc.render.image_settings.file_format = "PNG"
    sc.render.image_settings.color_mode = "RGBA"
    sc.render.filepath = OUT
    # Filmic crushes the blacks we need; standard keeps the housing readable
    # against #06080A instead of turning it into a grey slab.
    sc.view_settings.view_transform = "Standard"
    sc.view_settings.look = "None"
    return sc


def mat(name, base, rough, metallic=0.0, emit=None, emit_strength=0.0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = base
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metallic
    if emit is not None:
        # Blender renamed this socket: "Emission" in 3.x, "Emission Color" in
        # 4.x. This machine is pinned to 3.6 (the GPU cannot host 4.x), but the
        # script should not break the day that changes.
        key = "Emission Color" if "Emission Color" in b.inputs else "Emission"
        b.inputs[key].default_value = emit
        b.inputs["Emission Strength"].default_value = emit_strength
    return m


def rounded_frame():
    """The housing: a slab with the screen aperture cut out of it."""
    bpy.ops.mesh.primitive_cube_add(size=2, location=(0, 0, 0))
    outer = bpy.context.object
    outer.scale = (1.0, 0.75, 0.028)
    bpy.ops.object.transform_apply(scale=True)

    bev = outer.modifiers.new("bevel", "BEVEL")
    bev.width = 0.016
    bev.segments = 8
    bev.limit_method = "ANGLE"

    # the aperture
    bpy.ops.mesh.primitive_cube_add(size=2, location=(0, 0, 0))
    inner = bpy.context.object
    inner.scale = (0.945, 0.688, 0.12)
    bpy.ops.object.transform_apply(scale=True)
    ib = inner.modifiers.new("bevel", "BEVEL")
    ib.width = 0.010
    ib.segments = 6
    ib.limit_method = "ANGLE"

    bpy.context.view_layer.objects.active = outer
    boo = outer.modifiers.new("cut", "BOOLEAN")
    boo.operation = "DIFFERENCE"
    boo.object = inner
    bpy.ops.object.modifier_apply(modifier="bevel")
    bpy.ops.object.modifier_apply(modifier="cut")
    bpy.data.objects.remove(inner, do_unlink=True)

    outer.data.materials.append(
        mat("housing", (0.0075, 0.010, 0.013, 1.0), 0.34, metallic=0.35))
    bpy.ops.object.shade_smooth()
    outer.data.use_auto_smooth = True
    outer.data.auto_smooth_angle = math.radians(35)
    return outer


def rim_light():
    """The single teal hairline from the coin mark, as a real emitter."""
    # Faces the camera. Rotating it upright made it edge-on to the ortho
    # camera and it rendered nothing at all.
    bpy.ops.mesh.primitive_plane_add(size=2, location=(0, 0.727, 0.031))
    r = bpy.context.object
    r.scale = (0.93, 0.0075, 1)
    bpy.ops.object.transform_apply(scale=True)
    r.data.materials.append(
        mat("rim", (0, 0, 0, 1), 0.5, emit=TEAL, emit_strength=3.2))
    return r


def lights():
    # key: high and behind the camera, the promo's overhead source
    bpy.ops.object.light_add(type="AREA", location=(-1.6, -1.9, 2.6))
    k = bpy.context.object
    k.data.energy = 52
    k.data.size = 2.6
    k.rotation_euler = (math.radians(38), 0, math.radians(-38))

    # cool fill from the opposite side so the bevel reads on both edges
    bpy.ops.object.light_add(type="AREA", location=(2.2, -1.2, 0.9))
    f = bpy.context.object
    f.data.energy = 18
    f.data.size = 3.0
    f.data.color = (0.72, 0.86, 0.95)
    f.rotation_euler = (math.radians(76), 0, math.radians(58))

    # a long soft strip along the top edge — the wet specular streak
    bpy.ops.object.light_add(type="AREA", location=(0, -0.2, 2.2))
    s = bpy.context.object
    s.data.shape = "RECTANGLE"
    s.data.size, s.data.size_y = 4.0, 0.22
    s.data.energy = 74
    s.data.color = (0.86, 0.95, 1.0)


def camera():
    """Orthographic and dead-on: the CSS supplies all perspective."""
    bpy.ops.object.camera_add(location=(0, 0, 4))
    c = bpy.context.object
    c.data.type = "ORTHO"
    c.data.ortho_scale = 2.06
    c.rotation_euler = (0, 0, 0)
    bpy.context.scene.camera = c


def main():
    reset()
    rounded_frame()
    rim_light()
    lights()
    camera()
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    bpy.ops.render.render(write_still=True)
    print("RENDERED", OUT)


main()
