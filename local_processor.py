
import autorender

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
    if self.returncode != None:
      return True

    self.returncode = self.process.poll()

    return self.returncode != None

  # perform final clean-up work if necessary.
  # this should only be called in the case that
  # is_done returns true
  def finalize_task(self):
    assert self.is_done()
    autorender.finalize_blend_file_render(self.project_root, self.task_spec, self.returncode)


class LocalProcessor:
  def __init__(self, project_root):
    self.current_task = None
    self.project_root = project_root

  def process(self, task_spec):
    
    if 'target' in task_spec:
      raise ValueError('Execution of targets is not supported by this processor.')

    if 'blend_file' not in task_spec:
      raise ValueError('Please specify a blend_file to render.')

    subprocess = autorender.process_blend_file(self.project_root, task_spec)
    self.current_task = SubprocessStatus(self.project_root, task_spec, subprocess)
    return self.current_task

  def is_available(self):
    if self.current_task == None:
      return True
    if self.current_task.is_done():
      return True
    return False

