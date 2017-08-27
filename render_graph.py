import json

from os.path import dirname

targets = {}
assets = {}

import path_utils


# New class to represent the dependencies of rendering a target.
class RenderGraph:

    def __init__(self):
        self.targets = {}

    def add_targets(self, project_root, render_file):
        with open(render_file, 'r') as f:
            render_file_dict = json.load(f)
        target_dicts = render_file_dict['targets']
        for target_dict in target_dicts:
            full_target_name = target_dict['name']
            if not full_target_name.startswith('//'):
                target_root = dirname(render_file)
                relative_target_prefix = path_utils.replace_absolute_project_prefix(project_root, target_root)
                full_target_name = ':'.join([relative_target_prefix, full_target_name])

            self.targets[full_target_name] = target_dict

    def get_deps_for_target(self, target_name):
        return self.targets[target_name]['deps']

    def get_blend_file_for_target(self, target_name):
        return self.targets[target_name]['src']