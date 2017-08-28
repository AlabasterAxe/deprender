from unittest import TestCase

import local_processor


class TestLocalProcessor(TestCase):
    def test_process_blend_file(self):
        project_root = 'C:\\Users\\matth\\Google Drive\\projects\\deprender\\testing\\data\\fake_project_root'
        lp = local_processor.LocalProcessor(project_root)

        task_spec = {'blend_file': '//episode_1/subsequences/target_root_1/blend_files/simple_target.blend',
                     'output_directory': '//episode_1/subsequences/target_root_1/renders/seq/image_sequences/latest'}
        lp.process(task_spec)
