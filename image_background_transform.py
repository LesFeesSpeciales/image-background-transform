# Copyright (C) 2018 Les Fees Speciales
# voeu@les-fees-speciales.coop
#
#  This program is free software; you can redistribute it and/or
#  modify it under the terms of the GNU General Public License
#  as published by the Free Software Foundation; either version 2
#  of the License, or (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program; if not, write to the Free Software Foundation,
#  Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301, USA.


bl_info = {
    "name": "Transform Background Image",
    "author": "Les Fees Speciales",
    "version": (1, 0),
    "blender": (2, 79, 0),
    "location": "View3D > Toolbar > Background Image > Transform Background Image",
    "description": "Move, rotate and scale background images interactively.",
    "warning": "",
    "wiki_url": "",
    "category": "3D View",
    }

import bpy
from bpy_extras import view3d_utils
from bpy.props import FloatVectorProperty
import bgl
from math import radians, degrees, pi, cos, sin
from mathutils import Vector

# TODO
# perspective
# scale/rotate around 3D cursor


def get_view_orientation_from_quaternion(view_quat):
    """From https://blender.stackexchange.com/a/3428/4979"""
    def r(x):
        return round(x, 3)
    view_rot = view_quat.to_euler()

    orientation_dict = {(0.0, 0.0, 0.0):          'TOP',
                        (r(pi), 0.0, 0.0):        'BOTTOM',
                        (r(pi/2), 0.0, 0.0):      'FRONT',
                        (r(pi/2), 0.0, r(pi)):    'BACK',
                        (r(pi/2), 0.0, r(-pi/2)): 'LEFT',
                        (r(pi/2), 0.0, r(pi/2)):  'RIGHT'}

    return orientation_dict.get(tuple(map(r, view_rot)), 'UNDEFINED')


AXIS_MAP = {
    'TOP':    'xy',
    'BOTTOM': 'xy',
    'FRONT':  'xz',
    'BACK':   'xz',
    'LEFT':   'yz',
    'RIGHT':  'yz',
}


def space_to_view_vector(view, vector):
    vector = getattr(vector, AXIS_MAP[view])
    if view in {'BACK', 'LEFT'}:
        vector.x *= -1.0
    if view in {'BOTTOM'}:
        vector.y *= -1.0
    return vector


def view_to_region_vector(region, rv3d, view, vector):
    vector_3d = Vector()
    setattr(vector_3d, AXIS_MAP[view], vector)
    vector = view3d_utils.location_3d_to_region_2d(region, rv3d, vector_3d)
    return vector


def draw_callback_px(self, context):
    if self.do_draw:
        # 50% alpha, 2 pixel width line
        bgl.glEnable(bgl.GL_BLEND)
        bgl.glEnable(bgl.GL_LINE_STIPPLE)
        bgl.glColor4f(0.0, 0.0, 0.0, 1.0)
        bgl.glLineWidth(2)

        bgl.glBegin(bgl.GL_LINE_STRIP)
        bgl.glVertex2i(int(self.draw_start.x), int(self.draw_start.y))
        bgl.glVertex2i(int(self.draw_end.x), int(self.draw_end.y))
        # bgl.glVertex2i(500, 500)  # *self.draw_end)

        bgl.glEnd()

        # restore opengl defaults
        bgl.glLineWidth(1)
        bgl.glDisable(bgl.GL_BLEND)
        bgl.glDisable(bgl.GL_LINE_STIPPLE)
        bgl.glColor4f(0.0, 0.0, 0.0, 1.0)


class BackgroundImageTransform(bpy.types.Operator):
    """Transform background image.
Press G to move, R to rotate, S to scale.
Mousewheel to select image"""
    bl_idname = "view3d.background_image_transform"
    bl_label = "Transform Background Image"

    @classmethod
    def poll(self, context):
        return (context.space_data.type == 'VIEW_3D'
            and len(context.space_data.background_images))

    def reset(self):
        self.background_image.offset_x, self.background_image.offset_y = self._initial_location
        self.background_image.rotation = self._initial_rotation
        self.background_image.size = self._initial_size

    def update(self, context, event):
        region = context.region
        rv3d = context.region_data

        region_position = Vector(
            (event.mouse_region_x + self.region_offset_x*region.width,
             event.mouse_region_y + self.region_offset_y*region.height))

        if event.mouse_region_x > region.width:
            self.region_offset_x += 1
            bpy.context.window.cursor_warp(region.x, event.mouse_y)
        elif event.mouse_region_x < 0:
            self.region_offset_x -= 1
            bpy.context.window.cursor_warp(region.x + region.width, event.mouse_y)
        if event.mouse_region_y > region.height:
            self.region_offset_y += 1
            bpy.context.window.cursor_warp(event.mouse_x, region.y)
        elif event.mouse_region_y < 0:
            self.region_offset_y -= 1
            bpy.context.window.cursor_warp(event.mouse_x, region.y + region.height)

        mouse_location_3d = view3d_utils.region_2d_to_location_3d(region, rv3d, region_position, Vector())
        initial_mouse_location_2d = space_to_view_vector(self.camera_orientation, self._initial_mouse_location_3d)

        if context.space_data.pivot_point == 'CURSOR':
            pivot_point = space_to_view_vector(self.camera_orientation, context.space_data.cursor_location)
        else:
            pivot_point = self._initial_location
        pivot_point_region = view_to_region_vector(region, rv3d, self.camera_orientation, pivot_point)

        help_string = ', Confirm: (Enter/LMB), Cancel: (Esc/RMB), Choose Image : (Mousewheel), Move: (G), Rotate: (R), Scale: (S), Constrain to axes: (X/Y)'

        if self.mode == 'TRANSLATE':
            offset = space_to_view_vector(self.camera_orientation, (mouse_location_3d - self._initial_mouse_location_3d))
            if event.ctrl:
                offset.x //= 1
                offset.y //= 1
            if event.shift:
                offset *= 0.1

            if self.constrain_x:
                offset.y = 0.0
            if self.constrain_y:
                offset.x = 0.0

            self.background_image.offset_x, self.background_image.offset_y = self._initial_location + offset
            context.area.header_text_set("Dx: %.4f Dy: %.4f" % tuple(offset) + help_string)
            self.do_draw = False

        elif self.mode == 'ROTATE':
            initial_mouse_vector = self._initial_mouse - pivot_point
            current_mouse_vector = space_to_view_vector(self.camera_orientation, mouse_location_3d) - pivot_point
            rotation_offset = initial_mouse_vector.angle_signed(current_mouse_vector)

            if event.ctrl:
                rotation_offset = radians((degrees(rotation_offset) // 5) * 5)
            if event.shift:
                rotation_offset *= 0.1

            if (context.space_data.pivot_point == 'CURSOR'
                    and (self._initial_location - pivot_point).length_squared != 0):
                initial_angle = (self._initial_location - pivot_point).angle_signed(Vector((1.0, 0.0)))
                rotation_distance = (pivot_point - self._initial_location).length
                offset = pivot_point
                offset.x += cos(initial_angle - rotation_offset) * rotation_distance
                offset.y += sin(initial_angle - rotation_offset) * rotation_distance
                self.background_image.offset_x, self.background_image.offset_y = offset

            self.background_image.rotation = self._initial_rotation + rotation_offset
            context.area.header_text_set("Rot: %.2f°" % degrees(rotation_offset) + help_string)
            self.do_draw = True
            self.draw_start = pivot_point_region
            self.draw_end = region_position

        elif self.mode == 'SCALE':
            scale_offset = (space_to_view_vector(self.camera_orientation, mouse_location_3d) - pivot_point).length / (initial_mouse_location_2d - pivot_point).length

            if event.ctrl:
                scale_offset = ((scale_offset * 10) // 1) / 10
            if event.shift:
                scale_offset = scale_offset * 0.5 + 0.5

            self.background_image.size = self._initial_size * scale_offset
            context.area.header_text_set("Scale: %.4f" % scale_offset + help_string)
            self.do_draw = True
            self.draw_start = pivot_point_region
            self.draw_end = region_position

    def modal(self, context, event):
        context.area.tag_redraw()
        if event.type in ('MOUSEMOVE', 'LEFT_CTRL', 'RIGHT_CTRL', 'LEFT_SHIFT', 'RIGHT_SHIFT'):
            self.update(context, event)

        elif event.type == 'X' and event.value == 'PRESS':
            self.constrain_y = False
            self.constrain_x = not self.constrain_x
            self.update(context, event)
        elif event.type == 'Y' and event.value == 'PRESS':
            self.constrain_x = False
            self.constrain_y = not self.constrain_y
            self.update(context, event)

        elif event.type == 'R' and event.value == 'PRESS':
            self.mode = 'ROTATE'
            self.reset()
            self.update(context, event)
        elif event.type == 'G' and event.value == 'PRESS':
            self.mode = 'TRANSLATE'
            self.reset()
            self.update(context, event)
        elif event.type == 'S' and event.value == 'PRESS':
            self.mode = 'SCALE'
            self.reset()
            self.update(context, event)

        elif event.type == 'WHEELUPMOUSE':
            self.reset()
            image_index = self.valid_images.index(self.background_image)
            image_index += 1
            if image_index > len(self.valid_images) - 1:
                image_index = 0
            self.init_image(self.valid_images[image_index])
            self.update(context, event)
        elif event.type == 'WHEELDOWNMOUSE':
            self.reset()
            image_index = self.valid_images.index(self.background_image)
            image_index -= 1
            if image_index < 0:
                image_index = len(self.valid_images) - 1
            self.init_image(self.valid_images[image_index])
            self.update(context, event)

        elif event.type in {'LEFTMOUSE', 'RET'}:
            context.area.header_text_set()
            bpy.types.SpaceView3D.draw_handler_remove(self._handle, 'WINDOW')
            return {'FINISHED'}

        elif event.type in {'RIGHTMOUSE', 'ESC'}:
            self.reset()
#            rv3d.view_location = self._initial_location
            context.area.header_text_set()
            bpy.types.SpaceView3D.draw_handler_remove(self._handle, 'WINDOW')
            return {'CANCELLED'}

        return {'RUNNING_MODAL'}

    def init_image(self, background_image):
        self.background_image = background_image
        self.image_orientation = background_image.view_axis
        self._initial_location = Vector((self.background_image.offset_x, self.background_image.offset_y))
        self._initial_rotation = self.background_image.rotation
        self._initial_size = self.background_image.size

    def invoke(self, context, event):
        rv3d = context.region_data
        region = context.region

        self.mode = "TRANSLATE"
        self.constrain_x = False
        self.constrain_y = False

        self.camera_orientation = get_view_orientation_from_quaternion(rv3d.view_rotation)
        self.region_offset_x = 0
        self.region_offset_y = 0

        self._initial_mouse = Vector((event.mouse_region_x, event.mouse_region_y))
        self._initial_mouse_location_3d = view3d_utils.region_2d_to_location_3d(region, rv3d, self._initial_mouse, Vector())

        self.valid_images = []

        for background_image in context.space_data.background_images:
            image_orientation = background_image.view_axis
            if background_image.show_background_image and self.camera_orientation != 'UNDEFINED' and image_orientation in {self.camera_orientation, 'ALL'}:
                self.valid_images.append(background_image)

        if len(self.valid_images):
            active_image = self.valid_images[0]
            self.init_image(active_image)
            context.window_manager.modal_handler_add(self)
            args = (self, context)
            self._handle = bpy.types.SpaceView3D.draw_handler_add(draw_callback_px, args, 'WINDOW', 'POST_PIXEL')
            return {'RUNNING_MODAL'}
        else:
            self.report({'WARNING'}, 'No background image found.')
            return {'CANCELLED'}


def background_image_transform_panel(self, context):
    layout = self.layout
    layout.operator("view3d.background_image_transform")

addon_keymaps = []

def register():
    bpy.utils.register_class(BackgroundImageTransform)
    bpy.types.VIEW3D_PT_background_image.append(background_image_transform_panel)

    wm = bpy.context.window_manager
    km = wm.keyconfigs.addon.keymaps.new(name='3D View', space_type='VIEW_3D')
    kmi = km.keymap_items.new(BackgroundImageTransform.bl_idname, 'B', 'PRESS', alt=True, shift=True)
    addon_keymaps.append(km)


def unregister():
    bpy.utils.unregister_class(BackgroundImageTransform)
    bpy.types.VIEW3D_PT_background_image.remove(background_image_transform_panel)

    wm = bpy.context.window_manager
    for km in addon_keymaps:
        wm.keyconfigs.addon.keymaps.remove(km)
    addon_keymaps.clear()


if __name__ == "__main__":
    register()
