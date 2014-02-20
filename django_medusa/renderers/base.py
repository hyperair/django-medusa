from django.conf import settings

__all__ = ['COMMON_MIME_MAPS', 'BaseStaticSiteRenderer']


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


class BaseStaticSiteRenderer(object):
    """
    This default renderer writes the given URLs (defined in get_paths())
    into static files on the filesystem by getting the view's response
    through the Django testclient.
    """

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

    def render_path(self, path=None, view=None):
        raise NotImplementedError

    def generate(self):
        if getattr(settings, "MEDUSA_MULTITHREAD", False):
            from multiprocessing import Pool, cpu_count

            print "Generating with up to %d processes..." % cpu_count()
            pool = Pool(cpu_count())
            generator = PageGenerator(self)

            retval = pool.map(
                generator,
                ((path, None) for path in self.paths),
                chunksize=1
            )
            pool.close()

        else:
            self.client = Client()
            retval = map(self.render_path, self.paths)

        return retval


class PageGenerator(object):
    """
    Helper class to bounce things back into the renderer instance, since
    multiprocessing is unable to transfer a bound method object into a pickle.
    """
    def __init__(self, renderer):
        self.renderer = renderer

    def __call__(self, args):
        self.renderer.render_path(*args)
