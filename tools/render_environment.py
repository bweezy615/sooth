"""Render the room the panels stand in — wet black floor, ice, one teal.

    /Applications/Blender.app/Contents/MacOS/Blender --background \
        --factory-startup --python tools/render_environment.py

Why this exists
---------------
tools/render_panel.py replaced the CSS bezel with a real render, which fixed
the hardware but not the page: the panels still stood in flat black. The gloss
in the brand promos does not come from the frame, it comes from the ROOM — a
wet floor throwing reflections, ice catching a cold rim, and a single teal
source in a space that is otherwise unlit.

This renders that room once, as a wide backdrop the desk sits in front of. It
carries no product content and no text, so it never goes stale and never has to
be regenerated when the board changes.

What it produces
----------------
`site/public/assets/room.png` — a wide, dark plate:
  * a wet floor plane with real roughness variation, so the reflection is
    broken up rather than a mirror
  * slabs of ice at the horizon line, lit from behind by the one teal source
  * heavy falloff to true black at every edge, so it composites onto #06080A
    with no visible seam and needs no mask

Deliberately NOT in this render
-------------------------------
The panels. They are live iframes on top of it; baking a panel into the plate
would freeze the product into the wallpaper. The plate only has to give them a
floor to stand on and something to reflect in.

Same constraints as the panel render: Cycles on CPU (this GPU cannot host it),
Standard view transform so the blacks stay black against the page, and a
downsample before committing — see the note at the bottom of this file.
"""

import bpy
import math
import os
import random

OUT = os.path.join(os.getcwd(), "site/public/assets/room.png")

RES_X, RES_Y = 1600, 668
SAMPLES = 64

TEAL = (0.176, 0.831, 0.655, 1.0)
FROST = (0.749, 0.918, 0.949, 1.0)


def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    sc.cycles.device = "CPU"
    sc.cycles.samples = SAMPLES
    sc.cycles.use_denoising = True
    # Reflections are the whole point of a wet floor; give them enough bounces
    # to actually resolve, but not so many that a CPU still takes an hour.
    sc.cycles.max_bounces = 5
    sc.cycles.glossy_bounces = 6
    sc.cycles.transmission_bounces = 4
    sc.render.resolution_x = RES_X
    sc.render.resolution_y = RES_Y
    sc.render.image_settings.file_format = "PNG"
    sc.render.image_settings.color_mode = "RGB"
    sc.render.filepath = OUT
    sc.view_settings.view_transform = "Standard"
    sc.view_settings.look = "None"
    # A near-black world rather than pure black: pure black kills the ice edges
    # entirely, because there is nothing for the glass to refract.
    world = bpy.data.worlds.new("room")
    sc.world = world
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs[0].default_value = (0.002, 0.003, 0.004, 1)
    world.node_tree.nodes["Background"].inputs[1].default_value = 1.0
    return sc


def emit_socket(bsdf):
    """3.6 calls it "Emission"; 4.x calls it "Emission Color"."""
    return "Emission Color" if "Emission Color" in bsdf.inputs else "Emission"


def wet_floor():
    """A black floor that is wet, not a mirror.

    A perfectly smooth reflective plane reads as chrome and looks fake. Real
    wet asphalt has patches — so roughness is driven by noise, which breaks the
    reflection into streaks the way the promos' floor does.
    """
    bpy.ops.mesh.primitive_plane_add(size=60, location=(0, 0, 0))
    f = bpy.context.object
    m = bpy.data.materials.new("wet")
    m.use_nodes = True
    nt = m.node_tree
    b = nt.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (0.004, 0.006, 0.008, 1)
    b.inputs["Metallic"].default_value = 0.0

    noise = nt.nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 3.2
    noise.inputs["Detail"].default_value = 8.0
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.38
    ramp.color_ramp.elements[0].color = (0.04, 0.04, 0.04, 1)   # glassy pools
    ramp.color_ramp.elements[1].position = 0.72
    ramp.color_ramp.elements[1].color = (0.34, 0.34, 0.34, 1)   # duller patches
    nt.links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], b.inputs["Roughness"])
    f.data.materials.append(m)
    return f


def ice_material():
    m = bpy.data.materials.new("ice")
    m.use_nodes = True
    nt = m.node_tree
    b = nt.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (0.86, 0.95, 0.98, 1)
    b.inputs["Roughness"].default_value = 0.09
    b.inputs["IOR"].default_value = 1.31           # real ice, not glass at 1.45
    if "Transmission Weight" in b.inputs:          # 4.x
        b.inputs["Transmission Weight"].default_value = 1.0
    else:                                          # 3.x
        b.inputs["Transmission"].default_value = 1.0
    return m


def ice_field():
    """Slabs along the horizon. Irregular, because cubes read as boxes.

    Seeded so the render is reproducible — an asset that comes out different
    every run cannot be regenerated to match what is already deployed.
    """
    random.seed(7)
    mat = ice_material()
    for i in range(11):
        x = -14 + i * 2.8 + random.uniform(-0.7, 0.7)
        h = random.uniform(0.55, 1.9)
        bpy.ops.mesh.primitive_cube_add(size=1, location=(x, 6.5 + random.uniform(-1.2, 1.2), h / 2))
        c = bpy.context.object
        c.scale = (random.uniform(0.7, 1.9), random.uniform(0.6, 1.5), h)
        c.rotation_euler = (0, 0, random.uniform(0, 3.14))
        bpy.ops.object.transform_apply(scale=True, rotation=True)
        # Bevel then subdivide: the facets are what catch the rim light.
        bev = c.modifiers.new("b", "BEVEL")
        bev.width = random.uniform(0.04, 0.12)
        bev.segments = 2
        c.data.materials.append(mat)
        bpy.ops.object.shade_flat()


def lights():
    # The single teal source, behind the ice so it reads THROUGH the slabs.
    bpy.ops.object.light_add(type="AREA", location=(0, 12.5, 1.1))
    t = bpy.context.object
    t.data.shape = "RECTANGLE"
    t.data.size, t.data.size_y = 20.0, 0.9
    t.data.energy = 70
    t.data.color = TEAL[:3]
    t.rotation_euler = (math.radians(-72), 0, 0)

    # A cold overhead sliver so the floor has something to reflect near camera.
    bpy.ops.object.light_add(type="AREA", location=(0, -1.5, 6.0))
    o = bpy.context.object
    o.data.shape = "RECTANGLE"
    o.data.size, o.data.size_y = 18.0, 1.2
    o.data.energy = 45
    o.data.color = FROST[:3]
    o.rotation_euler = (0, 0, 0)


def camera():
    """Low and close to the floor — that is what makes a wet floor read."""
    bpy.ops.object.camera_add(location=(0, -7.6, 1.02))
    c = bpy.context.object
    c.data.lens = 40
    c.rotation_euler = (math.radians(86), 0, 0)
    bpy.context.scene.camera = c


def vignette():
    """Fall to true black at the frame edge so the plate needs no CSS mask.

    Done in the compositor rather than as CSS on top, because a gradient
    overlay in the page would sit above the panels and grey them out.
    """
    sc = bpy.context.scene
    sc.use_nodes = True
    nt = sc.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    rl = nt.nodes.new("CompositorNodeRLayers")
    ellipse = nt.nodes.new("CompositorNodeEllipseMask")
    ellipse.width, ellipse.height = 0.92, 1.15
    blur = nt.nodes.new("CompositorNodeBlur")
    blur.size_x, blur.size_y = 320, 220
    mix = nt.nodes.new("CompositorNodeMixRGB")
    mix.blend_type = "MULTIPLY"
    mix.inputs[0].default_value = 1.0
    comp = nt.nodes.new("CompositorNodeComposite")
    nt.links.new(ellipse.outputs["Mask"], blur.inputs["Image"])
    nt.links.new(rl.outputs["Image"], mix.inputs[1])
    nt.links.new(blur.outputs["Image"], mix.inputs[2])
    nt.links.new(mix.outputs["Image"], comp.inputs["Image"])


def main():
    reset()
    wet_floor()
    ice_field()
    lights()
    camera()
    vignette()
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    bpy.ops.render.render(write_still=True)
    print("RENDERED", OUT)


main()

# AFTER RENDERING, downsample before committing — same reason as the panel:
#
#     sips -Z 1800 site/public/assets/room.png --out /tmp/r.png \
#       && mv /tmp/r.png site/public/assets/room.png
#
# This plate is opaque RGB (no alpha needed — it is a backdrop), so it also
# converts to JPEG cheaply if the PNG is still too heavy:
#
#     sips -s format jpeg -s formatOptions 72 site/public/assets/room.png \
#       --out site/public/assets/room.jpg
