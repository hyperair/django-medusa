from django.conf import settings
import logging


class ProxyLogHandler(logging.Handler):
    def __init__(self, logger):
        logging.Handler.__init__(self)
        self.__logger = logger

    def emit(self, record):
        self.__logger.handle(record)

listener = None

def get_logger():
    if not settings.MEDUSA_MULTITHREAD:
        return get_base_logger()

    from logutils.queue import QueueHandler, QueueListener
    from multiprocessing import Queue

    mplogger = logging.getLogger(__name__ + '.__multiprocessing__')
    if not getattr(mplogger, 'setup_done', False):
        base = get_base_logger()
        logqueue = Queue()

        mplogger.setLevel(logging.DEBUG)
        mplogger.addHandler(QueueHandler(logqueue))
        mplogger.setup_done = True
        mplogger.propagate = False

        global listener
        listener = QueueListener(logqueue, ProxyLogHandler(get_base_logger()))
        listener.start()

    return mplogger

def finalize_logger():
    global listener

    if listener is not None:
        mplogger = get_logger()
        mplogger.setup_done = False
        listener.stop()
        listener = None

def get_base_logger():
    return logging.getLogger(__name__)
