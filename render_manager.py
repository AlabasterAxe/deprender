import copy
import json
import math
import os
import queue
import time
from os.path import join

import render_graph
from path_utils import (
    get_directory_for_target,
    get_latest_image_sequence_directory_for_target,
    replace_absolute_project_prefix,
    get_absolute_blend_file,
    replace_relative_project_prefix)


class RenderManager:
    def __init__(self, project_root, task_spec, processors):
        self.task_spec = task_spec
        self.processors = processors
        self.current_task_statuses = []

        # TODO(mattkeller): this seems pretty heavy to do in the constructor.
        if 'target' in task_spec:
            task_list = get_blend_file_task_linearized_dag_from_target_task(project_root, task_spec)
        elif 'blend_file' in task_spec:
            task_list = [task_spec]
        else:
            raise AssertionError('You dun goofed.')

        self.task_queue = queue.Queue()

        # The Queue class doesn't have a putall method, I swear.
        for task in task_list:
            self.task_queue.put(task)

    def is_done(self):
        if not self.current_task_statuses and self.task_queue.empty():
            return True
        return False

    # This method looks at the work left to process
    # and the available workers and assigns a task
    # to a worker, if possible.
    #
    # This method does not wait for the tasks to complete.
    def launch_next_tasks(self):

        # Check if there are newly completed tasks
        still_running_statuses = []
        for status in self.current_task_statuses:
            if status.is_done():
                status.finalize_task()
            else:
                still_running_statuses.append(status)
        self.current_task_statuses = still_running_statuses

        # Check if there are workers available to perform tasks
        available_processors = [processor for processor in self.processors if processor.is_available()]

        # Check if there are remaining tasks
        # Give those tasks to those workers, keeping the references to the ongoing
        # tasks
        if not self.task_queue.empty() and available_processors:

            # TODO(mattkeller): find a less gross way to phrase this code.
            if self.task_queue.qsize() == 1:
                task_spec = self.task_queue.get()
                split_tasks = split_task(task_spec, len(available_processors))
                for index, processor in enumerate(available_processors):
                    self.current_task_statuses.append(processor.process(split_tasks[index]))
            else:
                for processor in available_processors:
                    task_spec = self.task_queue.get()
                    self.current_task_statuses.append(processor.process(task_spec))

    def blocking_render(self):
        while not self.is_done():
            self.launch_next_tasks()

            # TODO(mattkeller): feelsbadman.jpg
            time.sleep(5)

    # Gives some indication of how far along we are.
    def status(self):
        pass

    def cancel(self):
        for status in self.current_task_statuses:
            status.cancel()


def get_blend_file_task_linearized_dag_from_target_task(project_root, target_task, graph=None):
    rg = graph
    if rg is None:
        rg = render_graph.RenderGraph()

    assert 'target' in target_task
    target = target_task['target']

    # forgive the overly verbose name.
    # this is the set of reasons why a dependency will be rerendered
    # this should be a list of strings.
    #
    # An empty list means that we won't rerender our dependencies

    dependency_invalidation_types = target_task['dependency_invalidation_types']

    new_task_template = copy.copy(target_task)
    del new_task_template['target']

    absolute_target_directory = get_directory_for_target(project_root, target)
    render_file = join(absolute_target_directory, 'RENDER.json')
    rg.add_targets(project_root, render_file)
    blend_files = []

    if dependency_invalidation_types:
        for dep_target in rg.get_deps_for_target(target):
            dep_task = copy.copy(new_task_template)
            dep_task['target'] = dep_target
            for dep_blend_file_task in get_blend_file_task_linearized_dag_from_target_task(project_root, dep_task, rg):
                scheduled = False

                # if dep_blend_file_task is in blend_files already we don't need to add it again.
                # we can probably do this more efficiently some how, possibly we build the graph and produce the dag
                # in two passes?
                for blend_file in blend_files:
                    if dep_blend_file_task == blend_file:
                        scheduled = True
                        break
                if scheduled:
                    continue
                else:
                    blend_files.append(dep_blend_file_task)

    # Basically, there are three reasons we'll rerender the blend file:
    #  - the source blend file for the target has changed since the start time of the latest render
    #  - any of this blend files dependencies have declared that they need to be rerendered (indicated by returning us
    #    a list of blender file tasks)
    #  - the dependency_invalidation_types list is empty (indicating a fast rerender requested)

    if needs_rerender(project_root, rg, target_task) or blend_files or not dependency_invalidation_types:
        new_task = copy.copy(new_task_template)
        absolute_blend_file = get_absolute_blend_file(project_root, target, rg.get_blend_file_for_target(target))
        new_task['blend_file'] = replace_absolute_project_prefix(project_root, absolute_blend_file)
        absolute_output_directory = get_latest_image_sequence_directory_for_target(project_root, target)
        new_task['output_directory'] = replace_absolute_project_prefix(project_root, absolute_output_directory)
        blend_files.append(new_task)
    return blend_files


def split_task(task_spec, num_sub_tasks):
    if 'start_frame' not in task_spec or 'end_frame' not in task_spec:
        return task_spec
    start_frame = task_spec['start_frame']
    end_frame = task_spec['end_frame']

    frame_range = end_frame - start_frame
    segment_size = math.ceil(frame_range / num_sub_tasks)

    new_frame_ranges = []
    for i in range(num_sub_tasks):
        seg_frame_start = start_frame + segment_size * i
        seg_frame_end = end_frame if i == num_sub_tasks - 1 else seg_frame_start + segment_size - 1
        new_frame_ranges.append((seg_frame_start, seg_frame_end))

    # second element of last tuple is end_frame
    print(new_frame_ranges)
    assert new_frame_ranges[-1][1] == end_frame

    new_tasks = []
    for frame_range in new_frame_ranges:
        new_task = copy.copy(task_spec)
        new_task['start_frame'] = frame_range[0]
        new_task['end_frame'] = frame_range[1]
        new_tasks.append(new_task)

    return new_tasks


# rg: RenderGraph
def needs_rerender(project_root, rg, target_task):
    target = target_task['target']
    blend_file_mtime = os.path.getmtime(
        get_absolute_blend_file(project_root, target, rg.get_blend_file_for_target(target)))

    relevant_mtimes = [blend_file_mtime]
    for asset in rg.get_assets_for_target(target):
        relevant_mtimes.append(os.path.getmtime(replace_relative_project_prefix(project_root, asset)))

    latest_image_sequence_directory = get_latest_image_sequence_directory_for_target(project_root, target)
    done_file = join(latest_image_sequence_directory, 'DONE.json')

    # TODO(mattkeller): pull this out into a helper function
    if not os.path.exists(done_file):
        return True
    else:
        dependency_invalidation_types = target_task['dependency_invalidation_types']

        with open(done_file, 'r') as f:
            completion_metadata_file = json.load(f)

        latest_render = completion_metadata_file['start_time']

        # If task_spec is not in completion_metadata_file maybe we should rerender?
        if 'task_spec' in completion_metadata_file and 'RESOLUTION_CHANGE' in dependency_invalidation_types:
            # possibly use computed dimensions here...
            # TODO(jbedard): should we only reprocess if target dimensions are higher?
            if 'resolution_x' in completion_metadata_file and 'resolution_x' in target_task and \
                            completion_metadata_file['resolution_x'] != target_task['resolution_x']:
                return True
            elif 'resolution_y' in completion_metadata_file and 'resolution_y' in target_task and \
                            completion_metadata_file['resolution_y'] != target_task['resolution_y']:
                return True
            elif 'resolution_percentage' in completion_metadata_file and 'resolution_percentage' in target_task and \
                            completion_metadata_file['resolution_percentage'] != target_task['resolution_percentage']:
                return True

        if latest_render < max(relevant_mtimes) and 'FILE_MODIFICATION_TIME' in dependency_invalidation_types:
            return True

    return False
