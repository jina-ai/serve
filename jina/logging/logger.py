import copy
import logging
import logging.handlers
import os
import platform
import sys
from typing import Optional

from rich.logging import LogRender as _LogRender
from rich.logging import RichHandler as _RichHandler

from jina.constants import __resources_path__, __uptime__, __windows__
from jina.enums import LogVerbosity
from jina.jaml import JAML
from jina.logging import formatter


class _MyLogRender(_LogRender):
    """Override the original rich log record for more compact layout."""

    def __call__(
        self,
        console,
        renderables,
        log_time=None,
        time_format=None,
        level=None,
        path=None,
        line_no=None,
        link_path=None,
    ):
        from rich.containers import Renderables
        from rich.table import Table
        from rich.text import Text

        output = Table.grid(padding=(0, 1))
        output.expand = True
        if self.show_level:
            output.add_column(style="log.level", width=5)

        output.add_column(ratio=1, style='log.message', overflow='ellipsis')

        if self.show_time:
            output.add_column(style="log.path")
        row = []

        if self.show_level:
            row.append(level)

        row.append(Renderables(renderables))

        if self.show_time:
            log_time = log_time or console.get_datetime()
            time_format = time_format or self.time_format
            if callable(time_format):
                log_time_display = time_format(log_time)
            else:
                log_time_display = Text(log_time.strftime(time_format))
            if log_time_display == self._last_time and self.omit_repeated_times:
                row.append(Text(" " * len(log_time_display)))
            else:
                row.append(log_time_display)
                self._last_time = log_time_display
        output.add_row(*row)
        return output


class RichHandler(_RichHandler):
    """Override the original rich handler for more compact layout."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._log_render = _MyLogRender(
            show_time=self._log_render.show_time,
            show_level=self._log_render.show_level,
            show_path=self._log_render.show_path,
            time_format=self._log_render.time_format,
            omit_repeated_times=self._log_render.omit_repeated_times,
            level_width=None,
        )


class SysLogHandlerWrapper(logging.handlers.SysLogHandler):
    """
    Override the priority_map :class:`SysLogHandler`.

    .. warning::
        This messages at DEBUG and INFO are therefore not stored by ASL, (ASL = Apple System Log)
        which in turn means they can't be printed by syslog after the fact. You can confirm it via :command:`syslog` or
        :command:`tail -f /var/log/system.log`.
    """

    priority_map = {
        'DEBUG': 'debug',
        'INFO': 'info',
        'WARNING': 'warning',
        'ERROR': 'error',
        'CRITICAL': 'critical',
    }


class JinaLogger:
    """
    Build a logger for a context.

    :param context: The context identifier of the class, module or method.
    :param log_config: The configuration file for the logger.
    :return:: an executor object.
    """

    supported = {'FileHandler', 'StreamHandler', 'SysLogHandler', 'RichHandler', 'TimedRotatingFileHandler', 'RotatingFileHandler'}

    def __init__(
        self,
        context: str,
        name: Optional[str] = None,
        log_config: Optional[str] = None,
        quiet: bool = False,
        **kwargs,
    ):

        log_config = os.getenv(
            'JINA_LOG_CONFIG',
            log_config or 'default',
        )

        if quiet or os.getenv('JINA_LOG_CONFIG', None) == 'QUIET':
            log_config = 'quiet'

        if not name:
            name = os.getenv('JINA_DEPLOYMENT_NAME', context)
        self.logger = logging.getLogger(context)
        self.logger.propagate = False

        context_vars = {
            'name': name,
            'uptime': __uptime__,
            'context': context,
        }
        self.add_handlers(log_config, **context_vars)
        self.debug = self.logger.debug
        self.warning = self.logger.warning
        self.critical = self.logger.critical
        self.error = self.logger.error
        self.info = self.logger.info
        self._is_closed = False
        self.debug_enabled = self.logger.isEnabledFor(logging.DEBUG)

    def success(self, *args):
        """
        Provides an API to print success messages

        :param args: the args to be forwarded to the log
        """
        self.logger.log(LogVerbosity.SUCCESS, *args)

    @property
    def handlers(self):
        """
        Get the handlers of the logger.

        :return:: Handlers of logger.
        """
        return self.logger.handlers

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def close(self):
        """Close all the handlers."""
        if not self._is_closed:
            for handler in self.logger.handlers:
                handler.close()
            self._is_closed = True

    def add_handlers(self, config_path: Optional[str] = None, **kwargs):
        """
        Add handlers from config file.

        :param config_path: Path of config file.
        :param kwargs: Extra parameters.
        """

        self.logger.handlers = []

        if not os.path.exists(config_path):
            old_config_path = config_path
            if 'logging.' in config_path and '.yml' in config_path:
                config_path = os.path.join(__resources_path__, config_path)
            else:
                config_path = os.path.join(
                    __resources_path__, f'logging.{config_path}.yml'
                )
            if not os.path.exists(config_path):
                config_path = old_config_path

        with open(config_path, encoding='utf-8') as fp:
            config = JAML.load(fp)

        for h in config['handlers']:
            cfg = config['configs'].get(h, None)
            fmt = getattr(formatter, cfg.get('formatter', 'Formatter'))

            if h not in self.supported or not cfg:
                raise ValueError(
                    f'can not find configs for {h}, maybe it is not supported'
                )

            handler = None
            if h == 'StreamHandler':
                handler = logging.StreamHandler(sys.stdout)
                handler.setFormatter(fmt(cfg['format'].format_map(kwargs)))
            elif h == 'RichHandler':
                kwargs_handler = copy.deepcopy(cfg)
                kwargs_handler.pop('format')

                handler = RichHandler(**kwargs_handler)
                handler.setFormatter(fmt(cfg['format'].format_map(kwargs)))

            elif h == 'SysLogHandler' and not __windows__:
                if cfg['host'] and cfg['port']:
                    handler = SysLogHandlerWrapper(address=(cfg['host'], cfg['port']))
                else:
                    # a UNIX socket is used
                    if platform.system() == 'Darwin':
                        handler = SysLogHandlerWrapper(address='/var/run/syslog')
                    else:
                        handler = SysLogHandlerWrapper(address='/dev/log')
                if handler:
                    handler.ident = cfg.get('ident', '')
                    handler.setFormatter(fmt(cfg['format'].format_map(kwargs)))

                try:
                    handler._connect_unixsocket(handler.address)
                except OSError:
                    handler = None
                    pass
            elif h == 'FileHandler':
                filename = cfg['output'].format_map(kwargs)
                if __windows__:
                    # colons are not allowed in filenames
                    filename = filename.replace(':', '.')
                handler = logging.FileHandler(filename, delay=True)
                handler.setFormatter(fmt(cfg['format'].format_map(kwargs)))

            elif h == 'TimedRotatingFileHandler':
                filename = cfg['filename'].format_map(kwargs)
                handler = logging.handlers.TimedRotatingFileHandler(
                    filename=filename,
                    when=cfg['when'],
                    interval=cfg['interval'],
                    backupCount=cfg['backupCount'],
                    encoding=cfg.get('encoding', 'utf-8')
                )
                handler.setFormatter(fmt(cfg['format'].format_map(kwargs)))

            elif h == 'RotatingFileHandler':
                filename = cfg['filename'].format_map(kwargs)
                handler = logging.handlers.RotatingFileHandler(
                    filename=filename,
                    maxBytes=cfg['maxBytes'],
                    backupCount=cfg['backupCount'],
                    encoding=cfg.get('encoding', 'utf-8')
                )
                handler.setFormatter(fmt(cfg['format'].format_map(kwargs)))
            
            if handler:
                self.logger.addHandler(handler)

        verbose_level = LogVerbosity.from_string(config['level'])
        if 'JINA_LOG_LEVEL' in os.environ:
            verbose_level = LogVerbosity.from_string(os.environ['JINA_LOG_LEVEL'])
        self.logger.setLevel(verbose_level.value)
