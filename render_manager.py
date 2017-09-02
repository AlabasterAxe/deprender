import copy
import json
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
            blend_files.extend(get_blend_file_task_linearized_dag_from_target_task(project_root, dep_task, rg))

    # Basically, there are three reasons we'll rerender the blend file:
    #  - the source blend file for the target has changed since the start time of the latest render
    #  - any of this blend files dependencies have declared that they need to be rerendered (indicated by returning us
    #    a list of blender file tasks)
    #  - the dependency_invalidation_types list is empty (indicating a fast rerender requested)

    if needs_rerender(project_root, rg, target) or blend_files or not dependency_invalidation_types:
        new_task = copy.copy(new_task_template)
        absolute_blend_file = get_absolute_blend_file(project_root, target, rg.get_blend_file_for_target(target))
        new_task['blend_file'] = replace_absolute_project_prefix(project_root, absolute_blend_file)
        absolute_output_directory = get_latest_image_sequence_directory_for_target(project_root, target)
        new_task['output_directory'] = replace_absolute_project_prefix(project_root, absolute_output_directory)
        blend_files.append(new_task)
    return blend_files


def needs_rerender(project_root, rg, target):

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
        with open(done_file, 'r') as f:
            completion_metadata_file = json.load(f)

        latest_render = completion_metadata_file['start_time']

    return latest_render < max(relevant_mtimes)
