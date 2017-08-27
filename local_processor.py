import json
import os
import time
from os.path import join
from subprocess import Popen

from path_utils import (
    get_image_sequence_directory_for_blend_file,
    get_latest_image_sequence_directory_for_blend_file,
    replace_relative_project_prefix
)


class SubprocessStatus:
    def __init__(self, project_root, task_spec, process):
        self.process = process
        self.returncode = None
        self.task_spec = task_spec
        self.project_root = project_root

    def is_done(self):
        # once we get a return code back, we hold onto it
        #
        # if we have non-None return code we assume that
        # we're done.
        if self.returncode is not None:
            return True

        self.returncode = self.process.poll()

        return self.returncode is not None

    # perform final clean-up work if necessary.
    # this should only be called in the case that
    # is_done returns true
    def finalize_task(self):
        assert self.is_done()
        finalize_blend_file_render(self.project_root, self.task_spec, self.returncode)


class LocalProcessor:
    def __init__(self, project_root):
        self.current_task = None
        self.project_root = project_root

    def process(self, task_spec):

        if 'target' in task_spec:
            raise ValueError('Execution of targets is not supported by this processor.')

        if 'blend_file' not in task_spec:
            raise ValueError('Please specify a blend_file to render.')

        subprocess = process_blend_file(self.project_root, task_spec)
        self.current_task = SubprocessStatus(self.project_root, task_spec, subprocess)
        return self.current_task

    def is_available(self):
        if self.current_task is None:
            return True
        if self.current_task.is_done():
            return True
        return False


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
            json.dump(done_dict, f)
