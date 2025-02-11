"""Server module level convenience functions and PbenchServerConfig class.
"""

from configparser import NoOptionError, NoSectionError
from datetime import datetime, timedelta, tzinfo
from enum import auto, Enum
from logging import Logger
from pathlib import Path
from time import time as _time
from typing import Dict, List, Optional, Union

from pbench import PbenchConfig
from pbench.common.exceptions import BadConfig

# A type defined to conform to the semantic definition of a JSON structure
# with Python syntax.
JSONSTRING = str
JSONNUMBER = Union[int, float]
JSONVALUE = Union["JSONOBJECT", "JSONARRAY", JSONSTRING, JSONNUMBER, bool, None]
JSONARRAY = List[JSONVALUE]
JSONOBJECT = Dict[JSONSTRING, JSONVALUE]
JSON = JSONVALUE


class OperationCode(Enum):
    """Enumeration for CRUD operations.

    The standard CRUD REST API operations:

        CREATE: Instantiate a new resource
        READ:   Retrieve the state of a resource
        UPDATE: Modify the state of a resource
        DELETE: Remove a resource
    """

    CREATE = auto()
    READ = auto()
    UPDATE = auto()
    DELETE = auto()


class SimpleUTC(tzinfo):
    """TZ Info class to help create a UTC datetime object."""

    def tzname(self, *args, **kwargs) -> str:
        return "UTC"

    def utcoffset(self, dt) -> timedelta:
        return timedelta(0)

    def dst(self, dt) -> timedelta:
        return timedelta(0)


UTC = SimpleUTC()


def utcnow(ts: float = None) -> datetime:
    """Convenience method for obtaining a datetime object with a UTC time zone.

    Args:
        ts : Optional seconds-since-the-epoch time stamp to use instead of the
            current time

    Returns:
        A datetime object with a UTC time zone.
    """
    tv = _time() if ts is None else ts
    return datetime.utcfromtimestamp(tv).replace(tzinfo=UTC)


def tstos(ts: float = None) -> str:
    """Convert a floating point seconds from the Epoch into a string.

    Returns:
        A string representation of a datetime object with a UTC time zone.
    """
    return utcnow(ts).strftime("%Y-%m-%dT%H:%M:%S-%Z")


def get_resolved_dir(
    env_name: str, dir_val: str, logger: Optional[Logger]
) -> Optional[Path]:
    """Get the resolved directory associated with the environment name.

    If a logger is given, will emit error logs when the directory is not
    found or the resolved name is not a directory.

    Args:
        env_name : Legacy environment name to display in error messages
        dir_val : A directory value to resolve to a real directory
        logger : Logger to use when low-level error messages should be
            emitted

    Returns:
        A Path directory object, None if the directory value does not
            resolve to a real directory.
    """
    try:
        dir_path = Path(dir_val).resolve(strict=True)
    except FileNotFoundError:
        if logger:
            logger.error(
                "The {} directory, '{}', does not resolve to a real location",
                env_name,
                dir_val,
            )
        dir_path = None
    else:
        if not dir_path.is_dir():
            if logger:
                logger.error(
                    "The {} directory, does not resolve to a directory ('{}')",
                    env_name,
                    dir_path,
                )
            dir_path = None
    return dir_path


def timestamp() -> str:
    """Generate a time stamp string.

    Returns:
        The current timestamp formatted as a string of the following form:
            <YYYY>-<MM>-<DD>T<hh>:<mm>:<ss>-<TZ>
    """
    return tstos()


class PbenchServerConfig(PbenchConfig):
    """An encapsulation of the configuration for the Pbench Server."""

    # Set of required properties.
    REQ_PROPS = frozenset(
        (
            "ARCHIVE",
            "BINDIR",
            "CACHE",
            "LIBDIR",
            "TMP",
            "TOP",
            "rest_uri",
        )
    )

    # Define a fallback default for dataset maximum retention, which we expect
    # to be defined in pbench-server-default.cfg, and one for the default
    # retention period.
    MAXIMUM_RETENTION_DAYS = 3650
    DEFAULT_RETENTION_DAYS = 90

    @classmethod
    def create(cls: "PbenchServerConfig", cfg_name: str) -> "PbenchServerConfig":
        """Construct a Pbench server configuration object and validate that all the
        required properties are present.

        Returns:
            A PbenchServerConfig instance.
        """
        sc = cls(cfg_name)

        # The following will reference all the required properties tripping a raise
        # of BadConfig if any of the properties are missing their base config value.
        req_props = [getattr(sc, attr) for attr in cls.REQ_PROPS]
        # The following assertion will always be True, but it keeps linters quiet.
        assert len(req_props) == len(cls.REQ_PROPS)

        return sc

    def __init__(self, cfg_name: str):
        """Constructor to add specific fields for the operation of the server.

        Args:
            cfg_name : The configuration file name to use
        """
        super().__init__(cfg_name)

        # The pbench server, unlike the pbench agent code, logs to separate
        # directories for each caller.
        self.log_using_caller_directory = True

        # Constants

        # Initial common timestamp format
        self.TS = f"run-{timestamp()}"

        # Server version
        self.version = None  # Defer discovery until needed

    @property
    def TOP(self) -> Path:
        return self._get_valid_dir_option("TOP", "pbench-server", "pbench-top-dir")

    @property
    def TMP(self) -> Path:
        return self._get_valid_dir_option("TMP", "pbench-server", "pbench-tmp-dir")

    @property
    def BINDIR(self) -> Path:
        return self._get_valid_dir_option("BINDIR", "pbench-server", "script-dir")

    @property
    def LIBDIR(self) -> Path:
        return self._get_valid_dir_option("LIBDIR", "pbench-server", "lib-dir")

    @property
    def ARCHIVE(self) -> Path:
        return self._get_valid_dir_option(
            "ARCHIVE", "pbench-server", "pbench-archive-dir"
        )

    @property
    def CACHE(self) -> Path:
        return self._get_valid_dir_option("CACHE", "pbench-server", "pbench-cache-dir")

    @property
    def PBENCH_ENV(self) -> str:
        return self.get("pbench-server", "environment", fallback="")

    @property
    def COMMIT_ID(self) -> str:
        if not self.version:
            install = Path(self.get("DEFAULT", "install-dir"))
            version = (install / "VERSION").read_text().strip()
            sha1 = (install / "SHA1").read_text().strip()
            self.version = f"{version}-{sha1}"
        return self.version

    @property
    def rest_uri(self) -> str:
        return self.get("pbench-server", "rest_uri")

    @property
    def max_retention_period(self) -> int:
        """Produce an integer representing the maximum number of days the server
        allows a dataset to be retained.

        Returns:
            An integer number of days representing the maximum retention period.
        """
        return self.getint(
            "pbench-server",
            "maximum-dataset-retention-days",
            fallback=self.MAXIMUM_RETENTION_DAYS,
        )

    @property
    def default_retention_period(self) -> int:
        """Produce an integer representing the default number of days the server
        allows a dataset to be retained.

        Returns:
            An integer number of days representing the default retention period.
        """
        return self.getint(
            "pbench-server",
            "default-dataset-retention-days",
            fallback=self.DEFAULT_RETENTION_DAYS,
        )

    def _get_valid_dir_option(self, env_name: str, section: str, option: str) -> Path:
        """Get the validated directory option from the given section.

        Args:
            env_name : Legacy environment name to display in error messages
            section : The configuration section name to find the option
            option : The option name to find in the given section

        Raises:
            BadConfig : if the directory option does not resolve to a directory
                on the file system, or if the option is missing, or if the
                section is missing

        Returns:
            A Path directory object.
        """
        try:
            dir_val = self.get(section, option)
        except (NoOptionError, NoSectionError) as exc:
            raise BadConfig(str(exc))
        else:
            if not dir_val:
                raise BadConfig(f"option {option} in section {section} is empty")
        dir_path = get_resolved_dir(env_name, dir_val, None)
        if not dir_path:
            raise BadConfig(f"Bad {env_name}={dir_val}")
        return dir_path
