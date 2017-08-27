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
    import autorender
    import render_manager
    import local_processor
except ImportError:
    # Initialize these so we can test against them.
    render_graph = None
    autorender = None
    # TODO(mattkeller): find some way to report this in the UI?
    print("Custom imports failed. Set PYTHONPATH to include scripts dir for full functionality.")

bl_info = {
    "name": "DepRender",
    "author": "Matt Keller <matthew.ed.keller@gmail.com>",
    "version": (1, 0, 3),
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


def get_target_directory_from_blend_file(blend_file):
    blend_files_directory = dirname(blend_file)
    if basename(blend_files_directory) != 'blend_files':
        return None
    return dirname(blend_files_directory)


def get_target_name_from_blend_file(blend_file):
    if not render_graph:
        return None

    target_directory = get_target_directory_from_blend_file(blend_file)
    render_file = join(target_directory, 'RENDER.py')
    if not exists(render_file):
        return None

    render_graph.targets = {}
    exec(open(render_file).read())
    for key in render_graph.targets.keys():
        # there *should* only be one here.
        return key


def get_target_directory_from_latest_directory(latest_directory):
    if latest_directory.endswith('\\'):
        latest_directory = dirname(latest_directory)
    image_sequences_directory = dirname(latest_directory)
    renders_directory = dirname(image_sequences_directory)
    return dirname(renders_directory)


# This has a very similar cousin in autorender.py
# These two methods should probably be combined.
def replace_absolute_project_prefix(context, target_or_blend_file):
    absolute_project_root = bpy.path.abspath(context.scene.dep_render_settings.project_root)
    relative_blend_file = relpath(target_or_blend_file, absolute_project_root)
    relative_blend_file = relative_blend_file.replace('\\', '/')
    return "//" + relative_blend_file


def generate_render_file(context):
    # select the source for the new target
    blend_file = bpy.data.filepath
    target_directory = get_target_directory_from_blend_file(blend_file)

    if target_directory:
        render_file = join(target_directory, 'RENDER.py')

        if not exists(render_file) and target_directory:

            source_file = relpath(blend_file, target_directory).replace('\\', '/')

            dependencies = set()
            # look for dependencies on rendered outputs of other targets.
            if context.scene.sequence_editor and context.scene.sequence_editor.sequences_all and render_graph:
                for sequence in context.scene.sequence_editor.sequences_all:
                    if not hasattr(sequence, 'directory'):
                        continue
                    sequence_directory = bpy.path.abspath(sequence.directory)
                    # this looks like the output of a target.
                    if basename(dirname(sequence_directory)) == 'latest':
                        target_root_directory = get_target_directory_from_latest_directory(sequence_directory)
                        render_file = join(target_root_directory, 'RENDER.py')
                        if exists(render_file):
                            render_graph.targets = {}
                            exec(open(render_file).read())
                            for key in render_graph.targets.keys():
                                # there *should* only be one here.
                                dependencies.add(key)

            new_target_name = replace_absolute_project_prefix(context, target_directory) + ':seq'
            with open(join(target_directory, 'RENDER.py'), 'w') as f:
                f.write('from render_target import image_sequence\n\n')
                f.write('image_sequence(\n')
                f.write('  name = \'' + new_target_name + '\',\n')
                f.write('  src = \'' + source_file + '\',\n')
                f.write('  deps = [\n')
                for dep in dependencies:
                    f.write('    \'' + dep + '\',\n')
                f.write('  ],\n')
                f.write(')\n')


class RENDER_PT_RenderAsTarget(bpy.types.Operator):
    """Operator which runs its self from a timer"""
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
        generate_render_file(context)

        project_root = os.path.abspath(bpy.path.abspath(context.scene.dep_render_settings.project_root))

        target = get_target_name_from_blend_file(bpy.data.filepath)

        task_spec = {'target': target}

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
    """Operator which runs its self from a timer"""
    bl_idname = "deprender.render_file"
    bl_label = "File"

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
        generate_render_file(context)

        project_root = os.path.abspath(bpy.path.abspath(context.scene.dep_render_settings.project_root))

        relative_blend_file = replace_absolute_project_prefix(context, bpy.data.filepath)

        task_spec = {'blend_file': relative_blend_file}

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
