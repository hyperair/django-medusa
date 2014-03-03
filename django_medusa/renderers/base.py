from __future__ import print_function
from django.conf import settings
from django.test.client import Client
from django_medusa.log import get_logger
import mimetypes
import os

__all__ = ['COMMON_MIME_MAPS', 'BaseStaticSiteRenderer']
logger = get_logger()


# Since mimetypes.get_extension() gets the "first known" (alphabetically),
# we get supid behavior like "text/plain" mapping to ".bat". This list
# overrides some file types we will surely use, to eliminate a call to
# mimetypes.get_extension() except in unusual cases.
COMMON_MIME_MAPS = {
    "text/plain": ".txt",
    "text/html": ".html",
    "text/javascript": ".js",
    "application/javascript": ".js",
    "text/json": ".json",
    "application/json": ".json",
    "text/css": ".css",
}

class RenderError(Exception):
    """
    Exception thrown during a rendering error.
    """
    pass

class BaseStaticSiteRenderer(object):
    """
    This default renderer writes the given URLs (defined in get_paths())
    into static files on the filesystem by getting the view's response
    through the Django testclient.
    """
    def __init__(self):
        self.client = None

    @classmethod
    def initialize_output(cls):
        """
        Things that should be done only once to the output directory BEFORE
        rendering occurs (i.e. setting up a config file, creating dirs,
        creating an external resource, starting an atomic deploy, etc.)

        Management command calls this once before iterating over all
        renderer instances.
        """
        pass

    @classmethod
    def finalize_output(cls):
        """
        Things that should be done only once to the output directory AFTER
        rendering occurs (i.e. writing end of config file, setting up
        permissions, calling an external "deploy" method, finalizing an
        atomic deploy, etc.)

        Management command calls this once after iterating over all
        renderer instances.
        """
        pass

    def get_paths(self):
        """ Override this in a subclass to define the URLs to process """
        raise NotImplementedError

    @property
    def paths(self):
        """ Property that memoizes get_paths. """
        p = getattr(self, "_paths", None)
        if not p:
            p = self.get_paths()
            self._paths = p
        return p

    def _render(self, path=None, view=None):
        client = self.client

        if not client:
            client = Client()

        response = client.get(path)
        if response.status_code != 200:
            raise RenderError(
                "Path {0} did not return status 200".format(path))

        return response

    @classmethod
    def get_outpath(cls, path, content_type):
        # Get non-absolute path
        path = path[1:] if path.startswith('/') else path

        # Resolves to a file, not a directory
        if not path.endswith('/'):
            return path

        return os.path.join(path, cls.get_dirsuffix(content_type))

    @classmethod
    def get_dirsuffix(cls, content_type):
        mime = content_type.split(';', 1)[0]

        return ('index' +
                (COMMON_MIME_MAPS.get(mime, mimetypes.guess_extension(mime)) or
                 '.html'))

    def render_path(self, path=None, view=None):
        raise NotImplementedError

    def generate(self):
        arglist = ((path, None) for path in self.paths)

        if getattr(settings, "MEDUSA_MULTITHREAD", False):
            from multiprocessing import Pool, cpu_count, Queue

            generator = PageGenerator(self)

            logger.info("Generating with up to %s processes...", cpu_count())
            pool = Pool(cpu_count())
            retval = pool.map(generator, arglist, chunksize=1)
            pool.close()

        else:
            self.client = Client()
            generator = PageGenerator(self)

            retval = map(generator, arglist)

        return retval


class PageGenerator(object):
    """
    Helper class to bounce things back into the renderer instance, since
    multiprocessing is unable to transfer a bound method object into a pickle.
    """
    def __init__(self, renderer):
        self.renderer = renderer

    def __call__(self, args):
        path = args[0]

        try:
            logger.info("Generating %s...", path)
            retval = self.renderer.render_path(*args)
            logger.info("Generated %s successfully", path)
            return retval

        except:
            logger.error("Could not generate %s", path, exc_info=True)
