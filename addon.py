""" NOTE: THIS FILE IS INTENDED TO BE EXECUTED WITHIN BLENDER IT ALMOST CERTAINLY WON't WORK OTHERWISE. """

import json
import os
from os.path import (
    basename,
    dirname,
    exists,
    join,
    relpath,
)

import bpy
from bpy.props import (
    StringProperty,
    PointerProperty,
    EnumProperty,
)
from bpy.types import PropertyGroup

try:
    import render_graph
    import render_manager
    import local_processor
    import path_utils
except ImportError:
    # Initialize these so we can test against them.
    render_graph = None
    render_manager = None
    local_processor = None
    path_utils = None
    # TODO(mattkeller): find some way to report this in the UI?
    print("Custom imports failed. Set PYTHONPATH to include scripts dir for full functionality.")

bl_info = {
    "name": "DepRender",
    "author": "Matt Keller <matthew.ed.keller@gmail.com> and Jon Bedard <bedardjo@gmail.com:>",
    "version": (1, 0, 8),
    "blender": (2, 70, 0),
    "location": "Render Panel",
    "description": "Dependency aware rendering.",
    "warning": "",
    "wiki_url": "example.com",
    "tracker_url": "example.com",
    "support": "COMMUNITY",
    "category": "Render",
}

RELATIVE_RENDER_TASKS_DIRECTORY = join("Render Tasks", "new")

AUTORENDER_UNAVAILABLE_ERROR_MSG = "Rendering utility unavailable. Immediate rendering unsupported."


class DepRenderPanel(bpy.types.Panel):
    """Creates a Panel in the Object properties window"""
    bl_label = "Dependency Aware Render"
    bl_idname = "RENDER_PT_deprender"
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = "render"

    def draw(self, context):
        layout = self.layout

        settings = context.scene.dep_render_settings

        layout.prop(settings, "project_root", text="Project Root")

        row = layout.row(align=True)
        row.label(text="Render as:")
        row.operator("deprender.render_target")
        row.operator("deprender.render_file")

        row = layout.row(align=True)
        row.label(text="Strategy:")
        row.prop(settings, "render_strategy", expand=True)


def generate_render_file(context):
    # select the source for the new target
    blend_file = bpy.data.filepath
    target_directory = path_utils.get_target_root_for_blend_file(blend_file)
    absolute_project_root = bpy.path.abspath(context.scene.dep_render_settings.project_root)

    if target_directory:

        render_file = join(target_directory, 'RENDER.json')
        source_file = relpath(blend_file, target_directory).replace('\\', '/')

        # check if the file exists
        #     if so parse it as json.
        #     check if the target for this blend file exists (how do I do that?)
        #         if so update the dependencies and assets (eventually...)
        #
        if exists(render_file):
            with open(render_file, 'r') as f:
                render_file_dict = json.load(f)
        else:
            render_file_dict = {'targets': []}

        # We look through the existing targets in the file to see if this blend file is already represented.
        this_target = None
        if 'targets' in render_file_dict:
            for target in render_file_dict['targets']:
                if 'src' in target and target['src'] == source_file:
                    this_target = target
            if this_target is not None:
                render_file_dict['targets'].remove(this_target)

        # If we haven't found the target we setup a new one.
        if this_target is None:
            (new_target_name, _) = os.path.splitext(basename(source_file))
            this_target = {
                'src': source_file,
                'name': new_target_name
            }

        # We start with a clean slate in terms of determining dependencies.
        dependencies = set()

        # look for dependencies on rendered outputs of other targets.
        if context.scene.sequence_editor and context.scene.sequence_editor.sequences_all and render_graph:

            for sequence in context.scene.sequence_editor.sequences_all:
                if not hasattr(sequence, 'directory'):
                    continue
                sequence_directory = bpy.path.abspath(sequence.directory)
                # this looks like the output of a target.
                if basename(dirname(sequence_directory)) == 'latest':
                    target = path_utils.get_target_for_latest_image_sequence_directory(absolute_project_root,
                                                                                       sequence_directory)
                    dependencies.add(target)

        this_target['deps'] = list(dependencies)

        render_file_dict['targets'].append(this_target)
        with open(render_file, 'w') as f:
            # indent=2 pretty prints the json, otherwise it's all on one line.
            json.dump(render_file_dict, f, indent=2)

        if this_target['name'].startswith('//'):
            full_target = this_target['name']
        else:
            full_target = ':'.join([path_utils.replace_absolute_project_prefix(absolute_project_root, target_directory),
                                    this_target['name']])
        print(full_target)
        return full_target


class RENDER_PT_RenderAsTarget(bpy.types.Operator):
    """ Render the current blend file, taking into account its dependencies. """
    bl_idname = "deprender.render_target"
    bl_label = "Target"

    _timer = None

    rm = None

    def modal(self, context, event):
        if event.type in {'RIGHTMOUSE', 'ESC'}:
            self.cancel(context)
            return {'CANCELLED'}

        if event.type == 'TIMER':
            if not self.rm.is_done():
                self.rm.launch_next_tasks()
            else:
                wm = context.window_manager
                wm.event_timer_remove(self._timer)
                return {'FINISHED'}

        return {'PASS_THROUGH'}

    def execute(self, context):
        wm = context.window_manager
        self._timer = wm.event_timer_add(0.1, context.window)
        wm.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def invoke(self, context, event):
        full_target = generate_render_file(context)

        project_root = os.path.abspath(bpy.path.abspath(context.scene.dep_render_settings.project_root))

        task_spec = {
          'target': full_target,
          'dependency_invalidation_types': ['FILE_MODIFICATION_TIME'],
          'resolution_x': bpy.context.scene.render.resolution_x,
          'resolution_y': bpy.context.scene.render.resolution_y
        }

        if context.scene.dep_render_settings.render_strategy == 'distributed':
            new_render_task_file = join(project_root, RELATIVE_RENDER_TASKS_DIRECTORY,
                                        basename(bpy.data.filepath)) + '.json'
            with open(new_render_task_file, 'w') as f:
                json.dump(task_spec, f)
            return {'FINISHED'}

        self.rm = render_manager.RenderManager(
            project_root,
            task_spec,
            [local_processor.LocalProcessor(project_root)]
        )
        self.execute(context)
        return {'RUNNING_MODAL'}

    def cancel(self, context):
        wm = context.window_manager
        wm.event_timer_remove(self._timer)


class RENDER_PT_RenderAsFile(bpy.types.Operator):
    """ Render just this file. """
    bl_idname = "deprender.render_file"
    bl_label = "File"

    _timer = None

    rm = None

    def modal(self, context, event):
        if event.type in {'ESC'}:
            self.cancel(context)
            return {'CANCELLED'}

        if event.type == 'TIMER':
            if not self.rm.is_done():
                self.rm.launch_next_tasks()
            else:
                wm = context.window_manager
                wm.event_timer_remove(self._timer)
                return {'FINISHED'}

        return {'PASS_THROUGH'}

    def execute(self, context):
        wm = context.window_manager
        self._timer = wm.event_timer_add(0.1, context.window)
        wm.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def invoke(self, context, event):
        full_target = generate_render_file(context)

        project_root = os.path.abspath(bpy.path.abspath(context.scene.dep_render_settings.project_root))

        # An empty dependency_invalidation_types list indicates that just this target should be rendered
        task_spec = {
          'target': full_target,
          'dependency_invalidation_types': [],
          'resolution_x': bpy.context.scene.render.resolution_x,
          'resolution_y': bpy.context.scene.render.resolution_y
        }

        if context.scene.dep_render_settings.render_strategy == 'distributed':
            new_render_task_file = join(project_root, RELATIVE_RENDER_TASKS_DIRECTORY,
                                        basename(bpy.data.filepath)) + '.json'
            with open(new_render_task_file, 'w') as f:
                json.dump(task_spec, f)
            return {'FINISHED'}

        self.rm = render_manager.RenderManager(
            project_root,
            task_spec,
            [local_processor.LocalProcessor(project_root)]
        )
        self.execute(context)
        return {'RUNNING_MODAL'}

    def cancel(self, context):
        wm = context.window_manager
        wm.event_timer_remove(self._timer)


class DepRenderSettings(PropertyGroup):
    project_root = StringProperty(
        name="Project Root",
        description="The path which all targets and blend files are defined relative to.",
        subtype="DIR_PATH",
    )

    render_strategy = EnumProperty(
        name="Render Strategy",
        items=(
            ('immediate', "Immediate", "The render is executed immediately."),
            ('distributed', "Distributed", "A render task is created and will be processed by a slave.")),
        default='immediate',
        description="How to execute a render.",
    )


def register():
    bpy.utils.register_module(__name__)
    bpy.types.Scene.dep_render_settings = PointerProperty(type=DepRenderSettings)


def unregister():
    del bpy.types.Scene.dep_render_settings
    bpy.utils.unregister_module(__name__)


if __name__ == "__main__":
    register()
