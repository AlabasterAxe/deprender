""" Utilities for working with blend files, target paths, etc."""
import os
import sys
from os.path import join

import render_graph


# Target utility methods


def get_directory_for_target(project_root, target):
    try:
        [target_prefix, _] = target.split(':')
    except ValueError:
        print('Invalid target name. Too many colons?')
        sys.exit(1)
    assert target_prefix.startswith('//')
    stripped_target_prefix = target_prefix.replace('//', '')
    return join(project_root, stripped_target_prefix)


def get_render_directory_for_target(project_root, target):
    return join(get_directory_for_target(project_root, target), 'renders')


def get_image_sequence_directory_for_target(project_root, target):
    return join(get_render_directory_for_target(project_root, target), 'image_sequences')


def get_latest_image_sequence_directory_for_target(project_root, target):
    return join(get_image_sequence_directory_for_target(project_root, target), 'latest')


def get_blend_files_directory_for_target(project_root, target):
    return join(get_directory_for_target(project_root, target), 'blend_files')


def get_blend_file_for_target(project_root, target):
    """
    This method requires that the target is available in the current render_graph context.

    TODO(mattkeller): maybe this should be updated to actually find and execute the RENDER.py file
                      instead of just hoping that it will available in the render_graph

    :param project_root: The directory which all targets are expressed relative to.
    :param target: The name of the target, starting with the "//".
    :return: The absolute path to the blend file associated with the target.
    """
    return join(get_directory_for_target(project_root, target), render_graph.targets[target]['src'])


# Blend file utility methods.


def get_target_root_for_blend_file(blend_file):
    """

    This method returns the "root" directory for the target that we assume this blend file is associated with.
    It was written under the assumption that we are given an absolute blend_file but it should still work as long as
    consumers of this method expect the behavior relative in -> relative out, absolute in -> absolute out.

    It assumes that targets follow the form:

        target_directory/
            blend_files/
                target_directory.blend

    In this example, the method will return the absolute path to target_directory.

    If we don't see the blend_files directory, we return None under the assumption that this is a blend file
    that doesn't live in a well defined target so we're sure where we should put the results of a render, for example.

    :param blend_file: blend file nested in a valid target structure.
    :return: the absolute path to the directory that contains the target that references that blend file.
    """
    (blend_files_directory, _) = os.path.split(blend_file)
    (target_root_directory, blend_files_directory_name) = os.path.split(blend_files_directory)
    if blend_files_directory_name != 'blend_files':
        return None
    else:
        return target_root_directory


def get_render_directory_for_blend_file(blend_file):
    target_root_directory = get_target_root_for_blend_file(blend_file)
    if target_root_directory:
        return join(target_root_directory, 'renders')
    else:
        return None


def get_image_sequence_directory_for_blend_file(blend_file):
    render_directory = get_render_directory_for_blend_file(blend_file)
    if render_directory:
        return join(render_directory, 'image_sequences')
    else:
        return None


def get_latest_image_sequence_directory_for_blend_file(blend_file):
    image_sequence_directory = get_image_sequence_directory_for_blend_file(blend_file)
    if image_sequence_directory:
        return join(image_sequence_directory, 'latest')
    else:
        return None


# Project root utility methods.


def replace_absolute_project_prefix(project_root, target_or_blend_file):
    relative_blend_file = os.path.relpath(target_or_blend_file, project_root)
    relative_blend_file = relative_blend_file.replace('\\', '/')
    return '//' + relative_blend_file


def replace_relative_project_prefix(project_root, target_or_blend_file):
    stripped_path = target_or_blend_file.replace('//', '')
    path = os.path.normpath(join(project_root, stripped_path))
    return path
