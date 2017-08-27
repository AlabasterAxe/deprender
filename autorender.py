import copy
import glob
import json
import os
import sys
import time
from os.path import join
from subprocess import Popen

# keeping local import separate
import render_graph


def get_directory_for_target(project_root, target):
    try:
        [target_prefix, _] = target.split(':')
    except ValueError:
        print('Invalid target name. Too many colons?')
        sys.exit(1)
    assert target_prefix.startswith('//')
    stripped_target_prefix = target_prefix.replace('//', '')
    return join(project_root, stripped_target_prefix)


def get_render_directory_for_target(project_root, target):
    return join(get_directory_for_target(project_root, target), 'renders')


def get_image_sequence_directory_for_target(project_root, target):
    return join(get_render_directory_for_target(project_root, target), 'image_sequences')


def get_latest_image_sequence_directory_for_target(project_root, target):
    return join(get_image_sequence_directory_for_target(project_root, target), 'latest')


def get_blend_files_directory_for_target(project_root, target):
    return join(get_directory_for_target(project_root, target), 'blend_files')


# This method requires that the target is available in the current render_graph context.
#
# TODO(mattkeller): maybe this should be updated to actually find and execute the RENDER.py file
#                   instead of just hoping that it will available in the render_graph
def get_blend_file_for_target(project_root, target):
    return join(get_directory_for_target(project_root, target), render_graph.targets[target]['src'])


# This method returns the "root" directory for the target that we assume this blend file is associated with.
# It was written under the assumption that we are given an absolute blend_file but it should still work as long as
# consumers of this method expect the behavior relative in -> relative out, absolute in -> absolute out.
#
# It assumes that targets follow the form:
#
#     target_directory/
#         blend_files/
#             target_directory.blend
#
# In this example, the method will return the absolute path to target_directory.
#
# If we don't see the blend_files directory, we return None under the assumption that this is a blend file
# that doesn't live in a well defined target so we're sure where we should put the results of a render, for example.
def get_target_root_for_blend_file(blend_file):
    (blend_files_directory, _) = os.path.split(blend_file)
    (target_root_directory, blend_files_directory_name) = os.path.split(blend_files_directory)
    if blend_files_directory_name != 'blend_files':
        return None
    else:
        return target_root_directory


def get_render_directory_for_blend_file(blend_file):
    target_root_directory = get_target_root_for_blend_file(blend_file)
    if target_root_directory:
        return join(target_root_directory, 'renders')
    else:
        return None


def get_image_sequence_directory_for_blend_file(blend_file):
    render_directory = get_render_directory_for_blend_file(blend_file)
    if render_directory:
        return join(render_directory, 'image_sequences')
    else:
        return None


def get_latest_image_sequence_directory_for_blend_file(blend_file):
    image_sequence_directory = get_image_sequence_directory_for_blend_file(blend_file)
    if image_sequence_directory:
        return join(image_sequence_directory, 'latest')
    else:
        return None


def replace_absolute_project_prefix(project_root, target_or_blend_file):
    relative_blend_file = os.path.relpath(target_or_blend_file, project_root)
    relative_blend_file = relative_blend_file.replace('\\', '/')
    return '//' + relative_blend_file


def replace_relative_project_prefix(project_root, target_or_blend_file):
    stripped_path = target_or_blend_file.replace('//', '')
    path = os.path.normpath(join(project_root, stripped_path))
    return path


def needs_rerender(project_root, target):
    blend_file_mtime = os.path.getmtime(get_blend_file_for_target(project_root, target))
    latest_image_sequence_directory = get_latest_image_sequence_directory_for_target(project_root, target)
    done_file = join(latest_image_sequence_directory, 'DONE.json')

    # TODO(mattkeller): pull this out into a helper function
    if not os.path.exists(done_file):
        return True
    else:
        with open(done_file, 'r') as f:
            completion_metadata_file = json.load(f)

        latest_render = completion_metadata_file['start_time']

    return latest_render < blend_file_mtime


def get_blend_file_task_linearized_dag_from_target_task(project_root, target_task):
    assert 'target' in target_task
    target = target_task['target']

    new_task_template = copy.copy(target_task)
    del new_task_template['target']

    absolute_target_directory = get_directory_for_target(project_root, target)
    render_file = join(absolute_target_directory, 'RENDER.py')
    exec(open(render_file).read())
    blend_files = []
    if 'deps' in render_graph.targets[target] and render_graph.targets[target]['deps']:
        for dep_target in render_graph.targets[target]['deps']:
            dep_task = copy.copy(new_task_template)
            dep_task['target'] = dep_target
            blend_files.extend(get_blend_file_task_linearized_dag_from_target_task(project_root, dep_task))

    # basically, if the blend file has changed or any of this blend files dependencies have declared that
    # they need to be rerendered we rerender this file.

    if needs_rerender(project_root, target) or blend_files:
        new_task = copy.copy(new_task_template)
        absolute_blend_file = get_blend_file_for_target(project_root, target)
        new_task['blend_file'] = replace_absolute_project_prefix(project_root, absolute_blend_file)
        blend_files.append(new_task)
    return blend_files


# This is 
#
def process_blend_file(project_root, task_spec):
    assert 'blend_file' in task_spec
    blend_file = join(project_root, os.path.normpath(task_spec['blend_file'].replace('//', '')))
    start_time = time.time()
    output_directory = get_latest_image_sequence_directory_for_blend_file(blend_file)
    if os.path.exists(output_directory) and os.listdir(output_directory):
        completion_metadata_file = join(output_directory, 'DONE.json')
        if os.path.exists(completion_metadata_file):
            with open(completion_metadata_file, 'r') as f:
                completion_metadata = json.load(f)
                new_directory_name = time.strftime("%Y-%m-%d_%H-%M-%S", time.gmtime(completion_metadata['start_time']))
        else:
            # TODO(mattkeller): we should be able to grab the start time from the IN_PROGRESS.json file.
            #                   IMO we should better reflect that this was an incomplete render in the directory name
            #                   replaced_* doesn't really indicate much.
            new_directory_name = "replaced_" + time.strftime("%Y-%m-%d_%H-%M-%S", time.gmtime())
        old_render_directory = join(get_image_sequence_directory_for_blend_file(blend_file), new_directory_name)
        os.makedirs(old_render_directory)
        for file in os.listdir(output_directory):
            os.rename(join(output_directory, file), join(old_render_directory, file))
    else:
        os.makedirs(output_directory)

    output_format = join(output_directory, 'frame_#####')

    custom_settings_script = join(output_directory, 'settings.py')

    with open(custom_settings_script, 'w') as f:
        f.write("import bpy\n\n")
        if 'resolution_x' in task_spec:
            f.write('bpy.context.scene.render.resolution_x = ' + str(task_spec['resolution_x']) + '\n')
        if 'resolution_y' in task_spec:
            f.write('bpy.context.scene.render.resolution_y = ' + str(task_spec['resolution_y']) + '\n')

    status_indicator = join(output_directory, 'IN_PROGRESS.json')
    with open(status_indicator, 'w') as f:
        json.dump({
            'start_time': start_time,
            'task_spec': task_spec,
        }, f)

    print(blend_file)
    assert os.path.exists(blend_file)

    # Actually execute the render
    return Popen([
        'blender',
        '-b',  # run in the background
        blend_file,  # render this file
        '-P', custom_settings_script,
        '-o', output_format,  # output the results in this format
        '-a',  # render the animation from start frame to end frame, inclusive
    ])


# this method should be called once the render to update the status files:
def finalize_blend_file_render(project_root, task_spec, returncode):
    absolute_blend_file = replace_relative_project_prefix(project_root, task_spec['blend_file'])
    print('absolute_blend_file: ')
    print(absolute_blend_file)
    output_directory = get_latest_image_sequence_directory_for_blend_file(absolute_blend_file)

    # Maybe this should all just be in one STATUS.json file?
    completion_indicator_file = join(output_directory, 'DONE.json')
    error_indicator_file = join(output_directory, 'ERROR.json')

    if os.path.exists(completion_indicator_file):
        print("Trying to finalize a finalized directory. Aborting.")
        return

    status_indicator_file = join(output_directory, 'IN_PROGRESS.json')

    done_dict = {'completion_time': time.time()}

    # this means that neither the DONE.json file nor the IN_PROGRESS.json file
    # are in the directory, which is weird.
    # we'll proceed under the assumption that the process calling this method
    # is correct that the render process has completed successfully.
    if not os.path.exists(status_indicator_file):
        print("No in-progress indicator file. We'll lose the start time")
    else:
        # we add everything from the status indicator file into the done file
        with open(status_indicator_file, 'r') as f:
            done_dict.update(json.load(f))

        os.remove(status_indicator_file)

    if not returncode:
        with open(completion_indicator_file, 'w') as f:
            json.dump(done_dict, f)
    else:
        done_dict['error_code'] = returncode
        with open(error_indicator_file, 'w') as f:
            json.dump(done_dict)


def process_target(project_root, task_spec):
    assert 'target' in task_spec
    tasks = get_blend_file_task_linearized_dag_from_target_task(project_root, task_spec)
    for task_spec in tasks:
        subprocess = process_blend_file(project_root, task_spec)
        returncode = subprocess.wait()
        finalize_blend_file_render(project_root, task_spec, returncode)


def check_for_new_tasks():
    # get the location of the file that were executing
    scripts_directory = os.path.dirname(os.path.realpath(__file__))

    # go to root of the render tasks folder
    os.chdir(scripts_directory)
    os.chdir('..')  # Render Tasks
    os.chdir('..')  # Animation Project

    animation_project_root_directory = os.getcwd()
    render_tasks_directory = join(animation_project_root_directory, 'Render Tasks')
    new_tasks_directory = join(render_tasks_directory, 'new')

    os.chdir(new_tasks_directory)

    task_filenames = glob.glob('*.json')

    if task_filenames:
        task_filename = task_filenames[0]

        with open(task_filename, 'r') as f:
            task_spec = json.load(f)
        os.remove(join(new_tasks_directory, task_filename))

        if 'target' in task_spec and 'blend_file' in task_spec:
            print('Please only specify one of either "target" or "blend_file" in your task_spec')
            sys.exit(2)

        if 'target' in task_spec:
            process_target(animation_project_root_directory, task_spec)
        elif 'blend_file' in task_spec:
            subprocess = process_blend_file(animation_project_root_directory, task_spec)
            returncode = subprocess.wait()
            finalize_blend_file_render(animation_project_root_directory, task_spec, returncode)
        else:
            # TODO(mattkeller): move this file from the directory
            sys.exit(3)


if __name__ == "__main__":
    check_for_new_tasks()
