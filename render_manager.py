import autorender
import queue

class RenderManager:

    def __init__(self, project_root, task_spec, processors):
      self.task_spec = task_spec
      self.processors = processors
      self.current_task_statuses = []
      
      # TODO(mattkeller): this seems pretty heavy to do in the constructor.
      if 'target' in task_spec:
        task_list = autorender.get_blend_file_task_linearized_dag_from_target_task(project_root, task_spec)
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

    # Gives some indication of how far along we are.
    def status(self):
      pass

