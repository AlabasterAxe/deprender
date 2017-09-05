import glob
import json
import os
from os.path import join

# keeping local import separate
import local_processor
import render_manager


def check_for_new_tasks():
    animation_project_root_directory = os.environ['ANIMATION_PROJECT_ROOT']
    render_tasks_directory = join(animation_project_root_directory, 'Render Tasks')
    new_tasks_directory = join(render_tasks_directory, 'new')

    os.chdir(new_tasks_directory)

    task_filenames = glob.glob('*.json')

    if task_filenames:
        task_filename = task_filenames[0]

        with open(task_filename, 'r') as f:
            task_spec = json.load(f)
        os.remove(join(new_tasks_directory, task_filename))

        rm = render_manager.RenderManager(
            animation_project_root_directory,
            task_spec,
            [local_processor.LocalProcessor(animation_project_root_directory),
             local_processor.LocalProcessor(animation_project_root_directory),
             local_processor.LocalProcessor(animation_project_root_directory)]
        )

        rm.blocking_render()


if __name__ == "__main__":
    check_for_new_tasks()
