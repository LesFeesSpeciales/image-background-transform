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
from math import radians, degrees, pi, cos, sin, copysign
from mathutils import Vector

# TODO
# perspective
# numeric input


persistent_settings = {'active_image': 0,
                       'transform_all': False,
                       'mode': 'TRANSLATE'}

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
    """Transform a 3D world vector to ortho view space."""
    vector = getattr(vector, AXIS_MAP[view])
    if view in {'BACK', 'LEFT'}:
        vector.x *= -1.0
    if view in {'BOTTOM'}:
        vector.y *= -1.0
    return vector


def view_to_region_vector(region, rv3d, view, vector):
    """Transform an ortho view vector to region space."""
    vector_3d = Vector()
    if view in {'BACK', 'LEFT'}:
        vector.x *= -1.0
    if view in {'BOTTOM'}:
        vector.y *= -1.0
    setattr(vector_3d, AXIS_MAP[view], vector)
    vector = view3d_utils.location_3d_to_region_2d(region, rv3d, vector_3d)
    return vector


def draw_callback_px(self, context):
    """From blender's operator_modal_draw.py modal operator template"""
    if self.do_draw:
        bgl.glEnable(bgl.GL_BLEND)
        bgl.glEnable(bgl.GL_LINE_STIPPLE)
        bgl.glColor4f(0.0, 0.0, 0.0, 1.0)
        bgl.glLineWidth(1)

        bgl.glBegin(bgl.GL_LINE_STRIP)
        bgl.glVertex2i(int(self.draw_start.x), int(self.draw_start.y))
        bgl.glVertex2i(int(self.draw_end.x), int(self.draw_end.y))

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
    bl_options = {'REGISTER', 'UNDO', 'GRAB_CURSOR', 'BLOCKING'}

    @classmethod
    def poll(self, context):
        return (context.space_data.type == 'VIEW_3D'
            and len(context.space_data.background_images))

    def reset(self):
        """Set current background image's transform to stored values"""
        for i_d in self.background_images:
            image = i_d['image']
            image.offset_x, image.offset_y = i_d['initial_location']
            image.rotation = i_d['initial_rotation']
            image.size = i_d['initial_size']

            image.use_flip_x = i_d['initial_flip_x']
            image.use_flip_y = i_d['initial_flip_y']

    def update(self, context, event):
        """Update transforms on each call"""
        region = context.region
        rv3d = context.region_data

        mouse_location_3d = view3d_utils.region_2d_to_location_3d(region, rv3d, (event.mouse_region_x, event.mouse_region_y), Vector())
        initial_mouse_location_2d = space_to_view_vector(self.camera_orientation, self.initial_mouse_location_3d)

        if self.transform_all:
            images = self.background_images
        else:
            images = (self.background_images[self.active_image],)

        # Get pivot type from space properties
        if context.space_data.pivot_point == 'CURSOR':
            pivot_point = space_to_view_vector(self.camera_orientation, context.space_data.cursor_location)
        elif context.space_data.pivot_point in ('BOUNDING_BOX_CENTER', 'MEDIAN_POINT', 'INDIVIDUAL_ORIGINS'):
            pivot_point = Vector((0.0, 0.0))
            for i_d in images:
                pivot_point += i_d['initial_location_view']
            pivot_point /= len(images)
        elif context.space_data.pivot_point == 'ACTIVE_ELEMENT':
            pivot_point = self.background_images[self.active_image]['initial_location_view'].copy()

        for i_i, i_d in enumerate(images):
            pivot_point_image = pivot_point.copy()
            pivot_point_image.y *= i_d['width'] / i_d['height']

            help_string = ', Confirm: (Enter/LMB), Cancel: (Esc/RMB), Choose Image: (Mousewheel), Transform All: (A), Move: (G), Rotate: (R), Scale: (S), Constrain to axis: (X/Y)'

            initial_mouse_vector = initial_mouse_location_2d - pivot_point
            current_mouse_vector = space_to_view_vector(self.camera_orientation, mouse_location_3d) - pivot_point

            if self.mode == 'TRANSLATE':
                # Get mouse differential in view space
                offset = space_to_view_vector(self.camera_orientation, (mouse_location_3d - self.initial_mouse_location_3d))

                # Offset is based a factor of width or height
                offset.y *= i_d['width'] / i_d['height']

                # Snap mode
                if event.ctrl:
                    offset.x //= 1
                    offset.y //= 1
                # Precision mode
                if event.shift:
                    offset *= 0.1

                # Axis constraint
                if self.constrain_x:
                    offset.y = 0.0
                if self.constrain_y:
                    offset.x = 0.0

                # Apply translation to background image
                i_d['image'].offset_x, i_d['image'].offset_y = i_d['initial_location'] + offset
                context.area.header_text_set("Dx: %.4f Dy: %.4f" % tuple(offset) + help_string)

            elif self.mode == 'ROTATE':
                # Get angles in view space
                rotation_offset = initial_mouse_vector.angle_signed(current_mouse_vector)

                # Add whole turns to avoid precision mode popping
                if (self.previous_rotation_offset < 0
                        and rotation_offset > 0
                        and abs(rotation_offset) > pi/2):
                    self.revolutions -= 1
                elif (self.previous_rotation_offset > 0
                        and rotation_offset < 0
                        and abs(rotation_offset) > pi/2):
                    self.revolutions += 1

                self.previous_rotation_offset = rotation_offset
                rotation_offset += self.revolutions * 2*pi

                # Snap mode
                if event.ctrl:
                    rotation_offset = radians((degrees(rotation_offset) // 5) * 5)
                # Precision mode
                if event.shift:
                    rotation_offset *= 0.1

                # Translate image in a circular path around 3D cursor
                if ((context.space_data.pivot_point in ('CURSOR', 'BOUNDING_BOX_CENTER', 'MEDIAN_POINT', 'ACTIVE_ELEMENT')
                        or context.space_data.pivot_point == 'ACTIVE_ELEMENT' and i_i != self.active_image)
                        and (i_d['initial_location_view'] - pivot_point).length_squared != 0):
                    initial_angle = (i_d['initial_location_view'] - pivot_point).angle_signed(Vector((1.0, 0.0)))
                    rotation_distance = (pivot_point - i_d['initial_location_view']).length
                    offset = pivot_point_image
                    offset.x += cos(initial_angle - rotation_offset) * rotation_distance
                    offset.y += sin(initial_angle - rotation_offset) * rotation_distance * i_d['width'] /  i_d['height']
                    i_d['image'].offset_x, i_d['image'].offset_y = offset

                # Apply rotation to background image
                i_d['image'].rotation = i_d['initial_rotation'] + rotation_offset
                context.area.header_text_set("Rot: %.2f°" % degrees(rotation_offset) + help_string)

            elif self.mode == 'SCALE':
                scale_offset = (space_to_view_vector(self.camera_orientation, mouse_location_3d) - pivot_point).length / (initial_mouse_location_2d - pivot_point).length

                # Snap mode
                if event.ctrl:
                    scale_offset = ((scale_offset * 10) // 1) / 10
                # Precision mode
                if event.shift:
                    scale_offset = scale_offset * 0.5 + 0.5

                # Detect flip (mouse has crossed line perpendicular to the pivot-initial mouse line)
                mouse_cross_product = initial_mouse_vector * current_mouse_vector
                if copysign(1, mouse_cross_product) != copysign(1, self.previous_mouse_cp):
                    i_d['image'].use_flip_x = not i_d['image'].use_flip_x
                    i_d['image'].use_flip_y = not i_d['image'].use_flip_y
                    self.previous_mouse_cp = mouse_cross_product

                flip = -1.0 if mouse_cross_product < 0 else 1.0

                # Translate image along a line between 3D cursor and original location
                if (context.space_data.pivot_point in ('CURSOR', 'BOUNDING_BOX_CENTER', 'MEDIAN_POINT')
                        or (context.space_data.pivot_point == 'ACTIVE_ELEMENT' and i_i != self.active_image)):
                    offset = i_d['initial_location_view'] + (pivot_point - i_d['initial_location_view']) * (1-scale_offset * flip)
                    offset.y *= i_d['width'] / i_d['height']
                    i_d['image'].offset_x, i_d['image'].offset_y = offset

                # Apply scale to background image
                i_d['image'].size = i_d['initial_size'] * scale_offset
                context.area.header_text_set("Scale: %.4f" % scale_offset + help_string)

        # Draw line from the mouse cursor
        pivot_point_region = view_to_region_vector(region, rv3d, self.camera_orientation, pivot_point)
        self.draw_start = Vector((event.mouse_region_x, event.mouse_region_y))
        # ...to the pivot point (image center or 3D cursor)...
        self.draw_end = pivot_point_region

    def modal(self, context, event):
        context.area.tag_redraw()
        if event.type in ('MOUSEMOVE', 'LEFT_CTRL', 'RIGHT_CTRL', 'LEFT_SHIFT', 'RIGHT_SHIFT'):
            self.update(context, event)

        # Axis constraint events
        elif event.type == 'X' and event.value == 'PRESS':
            self.constrain_y = False
            self.constrain_x = not self.constrain_x
            self.update(context, event)
        elif event.type == 'Y' and event.value == 'PRESS':
            self.constrain_x = False
            self.constrain_y = not self.constrain_y
            self.update(context, event)

        # Mode switch events
        elif event.type == 'R' and event.value == 'PRESS':
            self.mode = 'ROTATE'
            self.reset()
            self.update(context, event)
            self.do_draw = True
        elif event.type == 'G' and event.value == 'PRESS':
            self.mode = 'TRANSLATE'
            self.reset()
            self.update(context, event)
            # Do not draw stitched line in translation mode
            self.do_draw = False
        elif event.type == 'S' and event.value == 'PRESS':
            self.mode = 'SCALE'
            self.reset()
            self.update(context, event)
            self.do_draw = True

        # Image selection events : iterate through image list
        elif event.type == 'WHEELUPMOUSE':
            self.reset()
            self.active_image += 1
            if self.active_image > len(self.valid_images) - 1:
                self.active_image = 0
            self.update(context, event)
        elif event.type == 'WHEELDOWNMOUSE':
            self.reset()
            previous = self.active_image
            self.active_image -= 1
            if previous == 0:
                self.active_image = len(self.valid_images) - 1
            self.update(context, event)
        # Toggle transforming all images
        elif event.type == 'A' and event.value == 'PRESS':
            self.transform_all = not self.transform_all
            self.reset()
            self.update(context, event)

        # Confirm and apply
        elif event.type in {'LEFTMOUSE', 'RET'}:
            context.area.header_text_set()
            bpy.types.SpaceView3D.draw_handler_remove(self._handle, 'WINDOW')
            persistent_settings['active_image'] = self.active_image
            persistent_settings['transform_all'] = self.transform_all
            persistent_settings['mode'] = self.mode
            return {'FINISHED'}

        # Cancel and reset
        elif event.type in {'RIGHTMOUSE', 'ESC'}:
            self.reset()
            context.area.header_text_set()
            bpy.types.SpaceView3D.draw_handler_remove(self._handle, 'WINDOW')
            return {'CANCELLED'}

        return {'RUNNING_MODAL'}

    def init_images(self, background_images):
        self.background_images = []
        for bgi in background_images:
            i_d = {}
            i_d['image'] = bgi
            i_d['image_orientation'] = bgi.view_axis
            i_d['width'], i_d['height'] = bgi.image.size
            i_d['initial_flip_x'] = bgi.use_flip_x
            i_d['initial_flip_y'] = bgi.use_flip_y
            i_d['initial_location'] = Vector((bgi.offset_x, bgi.offset_y))
            i_d['initial_location_view'] = Vector((bgi.offset_x, bgi.offset_y))
            i_d['initial_location_view'].y *= i_d['height'] / i_d['width']
            i_d['initial_rotation'] = bgi.rotation
            i_d['initial_size'] = bgi.size
            self.background_images.append(i_d)

    def invoke(self, context, event):
        rv3d = context.region_data
        region = context.region

        self.mode = persistent_settings['mode']
        self.transform_all = persistent_settings['transform_all']
        self.constrain_x = False
        self.constrain_y = False

        self.camera_orientation = get_view_orientation_from_quaternion(rv3d.view_rotation)
        self.region_offset_x = 0
        self.region_offset_y = 0

        self.initial_mouse = Vector((event.mouse_region_x, event.mouse_region_y))
        self.initial_mouse_location_3d = view3d_utils.region_2d_to_location_3d(region, rv3d, self.initial_mouse, Vector())

        self.valid_images = []
        self.previous_rotation_offset = 0.0
        self.revolutions = 0

        self.previous_mouse_cp = 1.0

        # Get currently visible images
        for background_image in context.space_data.background_images:
            image_orientation = background_image.view_axis
            if background_image.show_background_image and self.camera_orientation != 'UNDEFINED' and image_orientation in {self.camera_orientation, 'ALL'}:
                self.valid_images.append(background_image)

        if len(self.valid_images):
            self.active_image = min(persistent_settings['active_image'], len(self.valid_images)-1)
            self.init_images(self.valid_images)
            context.window_manager.modal_handler_add(self)
            args = (self, context)
            self.do_draw = self.mode in ('ROTATE', 'SCALE')
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
