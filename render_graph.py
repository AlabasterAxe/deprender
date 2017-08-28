import json
from os.path import dirname

import path_utils


# Class to represent the dependencies of rendering a target.
class RenderGraph:
    def __init__(self):
        self.targets = {}

    def add_targets(self, project_root, render_file):
        """ Method to add the specified render_file to the render graph.

        This method accepts the render_file as opposed to the dictionary that the file represents so that we can
        fully qualify the target. That is so that when we have a target name "foo" inside a directory "//bar/baz"
        we can construct the full target name by which the target will be referred namely "//bar/baz:foo" without which
        file it came from we wouldn't have all the information to recover the full target name for this file.

        :param project_root: You know the drill.
        :param render_file: This is the absolute path to the RENDER.json file.
        :return: YOU GET NOTHING. YOU LOSE. GOOD DAY SIR.
        """
        with open(render_file, 'r') as f:
            render_file_dict = json.load(f)
        target_dicts = render_file_dict['targets']
        for target_dict in target_dicts:
            full_target_name = target_dict['name']

            # TODO(mattkeller): make it so that this fails when the name does start with '//'
            if not full_target_name.startswith('//'):
                target_root = dirname(render_file)
                relative_target_prefix = path_utils.replace_absolute_project_prefix(project_root, target_root)
                full_target_name = ':'.join([relative_target_prefix, full_target_name])

            self.targets[full_target_name] = target_dict

    def get_deps_for_target(self, target_name):
        return self.targets[target_name]['deps']

    def get_blend_file_for_target(self, target_name):
        return self.targets[target_name]['src']
