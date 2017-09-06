from unittest import TestCase

import render_manager


class TestRenderManager(TestCase):
    def test_split_tasks(self):
        task = {
            'start_frame': 1,
            'end_frame': 3,
        }

        sub_tasks = render_manager.split_task(task, 3)

        assert len(sub_tasks) == 3

        first_sub_task = sub_tasks[0]
        assert first_sub_task['start_frame'] == 1
        assert first_sub_task['end_frame'] == 1

        second_sub_task = sub_tasks[1]
        assert second_sub_task['start_frame'] == 2
        assert second_sub_task['end_frame'] == 2

        third_sub_task = sub_tasks[2]
        assert third_sub_task['start_frame'] == 3
        assert third_sub_task['end_frame'] == 3


    def test_split_tasks(self):
        task = {
            'start_frame': 1,
            'end_frame': 4,
        }

        sub_tasks = render_manager.split_task(task, 3)

        assert len(sub_tasks) == 3

        last_sub_task = sub_tasks[-1]
        assert last_sub_task['end_frame'] == 4

