from __future__ import print_function
try:
    import cStringIO
except ImportError:  # >=Python 3.
    from io import StringIO as cStringIO
from datetime import timedelta, datetime
from django.conf import settings
from django.test.client import Client
from ..log import get_logger
from .base import BaseStaticSiteRenderer

__all__ = ('S3StaticSiteRenderer', )


def _get_cf():
    from boto.cloudfront import CloudFrontConnection
    return CloudFrontConnection(
        aws_access_key_id=settings.AWS_ACCESS_KEY,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY
    )


def _get_distribution():
    if not getattr(settings, "AWS_DISTRIBUTION_ID", None):
        return None

    conn = _get_cf()
    try:
        return conn.get_distribution_info(settings.AWS_DISTRIBUTION_ID)
    except:
        return None


def _upload_to_s3(key, file):
    key.set_contents_from_file(file, policy="public-read")

    cache_time = 0
    now = datetime.now()
    expire_dt = now + timedelta(seconds=cache_time * 1.5)
    if cache_time != 0:
        key.set_metadata('Cache-Control',
            'max-age=%d, must-revalidate' % int(cache_time))
        key.set_metadata('Expires',
            expire_dt.strftime("%a, %d %b %Y %H:%M:%S GMT"))
    key.make_public()


class S3StaticSiteRenderer(BaseStaticSiteRenderer):
    """
    A variation of BaseStaticSiteRenderer that deploys directly to S3
    rather than to the local filesystem.

    Requires `boto`.

    Uses some of the same settings as `django-storages`:
      * AWS_ACCESS_KEY
      * AWS_SECRET_ACCESS_KEY
      * AWS_STORAGE_BUCKET_NAME
    """
    def __init__(self):
        self.conn = None
        self.bucket = None
        self.client = None

    @classmethod
    def initialize_output(cls):
        super(S3StaticSiteRenderer, self).initialize_output()
        cls.all_generated_paths = []

    def render_path(self, path=None, view=None):
        client = self.client or Client()
        bucket = self.bucket or self.get_bucket()

        # Render the view
        resp = self._render(path, view)
        content_type = resp['Content-Type']
        outpath = self.get_outpath(path, content_type)

        key = bucket.get_key(outpath) or bucket.new_key(outpath)
        key.content_type = content_type

        temp_file = cStringIO.StringIO(resp.content)
        md5 = key.compute_md5(temp_file)

        # If key is new, there's no etag yet
        if not key.etag:
            _upload_to_s3(key, temp_file)
            message = "Creating"

        else:
            etag = key.etag or ''
            # for some weird reason, etags are quoted, strip them
            etag = etag.strip('"\'')
            if etag not in md5:
                _upload_to_s3(key, temp_file)
                message = "Updating"
            else:
                message = "Skipping"

        self.logger.info("%s http://%s%s",
                         message, bucket.get_website_endpoint(), path)
        temp_file.close()
        return [path, outpath]

    def get_bucket(self):
        from boto.s3.connection import S3Connection

        conn = S3Connection(
            aws_access_key_id=settings.AWS_ACCESS_KEY,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY
        )

        bucket_name = (settings.MEDUSA_AWS_STORAGE_BUCKET_NAME
                       if hasattr(settings, 'MEDUSA_AWS_STORAGE_BUCKET_NAME')
                       else settings.AWS_STORAGE_BUCKET_NAME)
        bucket = bucket.get_bucket(bucket_name)
        bucket.configure_bucket("index.html", "500.html")
        # self.server_root_path = bucket.get_website_endpoint()

        return bucket

    def generate(self):
        if not getattr(settings, 'MEDUSA_MULTITHREAD', False):
            self.bucket = self.get_bucket()

        self.generated_paths = list(itertools.chain(
            super(S3StaticSiteRenderer, self).generate()))

        type(self).all_generated_paths += self.generated_paths

    @classmethod
    def finalize_output(cls):
        dist = _get_distribution()
        if dist and dist.in_progress_invalidation_batches < 3:
            cf = _get_cf()
            req = cf.create_invalidation_request(
                settings.AWS_DISTRIBUTION_ID,
                cls.all_generated_paths
            )
            cls.logger.info("Invalidation request ID: %s", req.id)
        super(S3StaticSiteRenderer, self).finalize_output()
