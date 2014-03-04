from __future__ import print_function
from django.conf import settings
from django.test.client import Client
import mimetypes
import os
from .base import COMMON_MIME_MAPS, BaseStaticSiteRenderer
from ..log import get_logger

__all__ = ('DiskStaticSiteRenderer', )


class DiskStaticSiteRenderer(BaseStaticSiteRenderer):
    def __init__(self):
        super(DiskStaticSiteRenderer, self).__init__()
        self.DEPLOY_DIR = settings.MEDUSA_DEPLOY_DIR

    def render_path(self, path=None, view=None):
        if path:
            resp = self._render(path, view)
            outpath = self.get_outpath(path, resp['Content-Type'])
            outpath = os.path.abspath(os.path.join(self.DEPLOY_DIR, outpath))

            # Ensure the directories exist
            try:
                os.makedirs(os.path.dirname(outpath))
            except OSError:
                pass

            self.logger.info("Saving file to: %s", outpath)
            with open(outpath, 'w') as f:
                f.write(resp.content)
