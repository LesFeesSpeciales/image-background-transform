# Copyright (C) 2018 Les Fees Speciales
# voeu@les-fees-speciales.coop
##
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
from math import radians, degrees, pi
from mathutils import Vector
from bpy.props import FloatVectorProperty

# TODO
# wrap mouse
# perspective
# scale/rotate around 3D cursor
# draw lines from pivot to mouse

def get_view_orientation_from_quaternion(view_quat):
    """From https://blender.stackexchange.com/a/3428/4979"""
    r = lambda x: round(x, 3)
    view_rot = view_quat.to_euler()

    orientation_dict = {(0.0, 0.0, 0.0) : 'TOP',
                        (r(pi), 0.0, 0.0) : 'BOTTOM',
                        (r(pi/2), 0.0, 0.0) : 'FRONT',
                        (r(pi/2), 0.0, r(pi)) : 'BACK',
                        (r(pi/2), 0.0, r(-pi/2)) : 'LEFT',
                        (r(pi/2), 0.0, r(pi/2)) : 'RIGHT'}

    return orientation_dict.get(tuple(map(r, view_rot)), 'UNDEFINED')

def space_to_view_vector(view, vector):
    axis_map = {
                'TOP': 'xy',
                'BOTTOM': 'xy',
                'FRONT': 'xz',
                'BACK': 'xz',
                'LEFT': 'yz',
                'RIGHT': 'yz',
                }
    vector = getattr(vector, axis_map[view])
    if view in {'BACK', 'LEFT'}:
        vector.x *= -1.0
    if view in {'BOTTOM'}:
        vector.y *= -1.0
    return vector

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
        self.background_image.offset_x, self.background_image.offset_y = self._initial_offset
        self.background_image.rotation = self._initial_rotation
        self.background_image.size = self._initial_size

    def update(self, context, event):
        region = context.region
        rv3d = context.region_data

        mouse_location_3d = view3d_utils.region_2d_to_location_3d(region, rv3d, Vector((event.mouse_region_x, event.mouse_region_y)), Vector())

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

            self.background_image.offset_x, self.background_image.offset_y = self._initial_offset + offset
            context.area.header_text_set("Dx: %.4f Dy: %.4f" % tuple(offset) + help_string)

        elif self.mode == 'ROTATE':
            offset = -(space_to_view_vector(self.camera_orientation, mouse_location_3d) - self._initial_offset).angle_signed(space_to_view_vector(self.camera_orientation, self._initial_mouse_location_3d) - self._initial_offset)

            if event.ctrl:
                offset = radians((degrees(offset) // 5) * 5)
            if event.shift:
                offset *= 0.1

            self.background_image.rotation = self._initial_rotation + offset
            context.area.header_text_set("Rot: %.2f°" % degrees(offset) + help_string)

        elif self.mode == 'SCALE':
            offset = (space_to_view_vector(self.camera_orientation, mouse_location_3d) - self._initial_offset).length / (space_to_view_vector(self.camera_orientation, self._initial_mouse_location_3d) - self._initial_offset).length

            if event.ctrl:
                offset = ((offset*10) // 1) / 10
            if event.shift:
                offset *= 0.1

            self.background_image.size = self._initial_size * offset
            context.area.header_text_set("Scale: %.4f" % offset + help_string)

    def modal(self, context, event):
        if event.type in ('MOUSEMOVE', 'LEFT_CTRL', 'RIGHT_CTRL', 'LEFT_SHIFT', 'LEFT_SHIFT'):
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
            return {'FINISHED'}

        elif event.type in {'RIGHTMOUSE', 'ESC'}:
            self.reset()
#            rv3d.view_location = self._initial_location
            context.area.header_text_set()
            return {'CANCELLED'}

        return {'RUNNING_MODAL'}

    def init_image(self, background_image):
        self.background_image = background_image
        self.image_orientation = background_image.view_axis
        self._initial_offset = Vector((self.background_image.offset_x, self.background_image.offset_y))
        self._initial_rotation = self.background_image.rotation
        self._initial_size = self.background_image.size

    def invoke(self, context, event):
        rv3d = context.region_data
        region = context.region

        self.mode = "TRANSLATE"
        self.constrain_x = False
        self.constrain_y = False

        self.camera_orientation = get_view_orientation_from_quaternion(rv3d.view_rotation)

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
