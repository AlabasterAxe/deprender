""" Utilities for working with blend files, target paths, etc."""
import os
from os.path import join, dirname, abspath, basename


# Target utility methods


def get_directory_for_target(project_root, target):
    try:
        [target_prefix, _] = target.split(':')
    except ValueError:
        raise ValueError('Invalid target name: %s. Too many colons?' % target)
    assert target_prefix.startswith('//')
    stripped_target_prefix = target_prefix.replace('//', '')

    # We use abspath here to make sure that the slashes are all going the right way.
    return abspath(join(project_root, stripped_target_prefix))


def get_render_directory_for_target(project_root, target):
    """

    :param project_root: the root directory for the whole project.
    :param target: A full target spec (e.g. "//some/path:target_name")
    :return: The absolute path to the render directory for the target.
    """
    [_, target_name] = target.split(":")
    return join(get_directory_for_target(project_root, target), 'renders', target_name)


def get_image_sequence_directory_for_target(project_root, target):
    return join(get_render_directory_for_target(project_root, target), 'image_sequences')


def get_latest_image_sequence_directory_for_target(project_root, target):
    return join(get_image_sequence_directory_for_target(project_root, target), 'latest')


def get_blend_files_directory_for_target(project_root, target):
    return join(get_directory_for_target(project_root, target), 'blend_files')


def get_target_for_latest_image_sequence_directory(project_root, latest_directory):
    image_sequence_directory = dirname(dirname(latest_directory))
    target_render_directory = dirname(image_sequence_directory)
    target_name = basename(target_render_directory)
    target_root = get_target_directory_from_latest_directory(latest_directory)

    relative_path = replace_absolute_project_prefix(project_root, target_root)

    return ':'.join([relative_path, target_name])


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


def get_absolute_blend_file(project_root, target, relative_blend_file):
    [relative_target_path, _] = target.split(':')
    absolute_target_path = replace_relative_project_prefix(project_root, relative_target_path)
    return join(absolute_target_path, relative_blend_file)


# Project root utility methods.


def replace_absolute_project_prefix(project_root, target_or_blend_file):
    relative_blend_file = os.path.relpath(target_or_blend_file, project_root)
    relative_blend_file = relative_blend_file.replace('\\', '/')
    return '//' + relative_blend_file


def replace_relative_project_prefix(project_root, target_or_blend_file):
    stripped_path = target_or_blend_file.replace('//', '')
    path = os.path.normpath(join(project_root, stripped_path))
    return path


def get_target_name_from_blend_file(project_root, blend_file):
    target_directory = get_target_root_for_blend_file(blend_file)
    blend_file_name = os.path.basename(blend_file)
    (extensionless_blend_file, _) = os.path.splitext(blend_file_name)
    relative_target_directory = replace_absolute_project_prefix(project_root, target_directory)
    return ':'.join([relative_target_directory, extensionless_blend_file])


def get_target_directory_from_latest_directory(latest_directory):
    if latest_directory.endswith('\\'):
        latest_directory = dirname(latest_directory)
    image_sequences_directory = dirname(latest_directory)
    target_name_directory = dirname(image_sequences_directory)
    renders_directory = dirname(target_name_directory)
    return dirname(renders_directory)
