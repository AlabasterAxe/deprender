
import render_graph

def image_sequence(name, src, deps=None, assets=None):
  render_graph.targets[name] = {
    'src' : src,
    'deps' : deps,
    'assets' : assets,
  }

def asset(name, srcs):
  render_graph.assets[name] = {
    'srcs' : srcs,
  }


