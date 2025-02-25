"""
Miscellaneous enums used in Jina.

To use these enums in YAML config, following the example below:

.. highlight:: yaml
.. code-block:: yaml

      chunk_idx:
        uses: index/chunk.yml
        parallel: ${{PARALLEL}}
        parallel_type: !PollingType ANY
        # or
        parallel_type: ANY
        # or
        parallel_type: any
"""

from enum import Enum, EnumMeta, Flag, IntEnum
from typing import List, Union


class EnumType(EnumMeta):
    """The metaclass for BetterEnum."""

    def __new__(cls, *args, **kwargs):
        """Register a new EnumType

        :param args: args passed to super()
        :param kwargs: kwargs passed to super()
        :return: the registry class
        """
        _cls = super().__new__(cls, *args, **kwargs)
        return cls.register_class(_cls)

    @staticmethod
    def register_class(cls):
        """
        Register the class for dumping loading.

        :param cls: Target class.
        :return: Registered class.
        """
        reg_cls_set = getattr(cls, '_registered_class', set())
        if cls.__name__ not in reg_cls_set:
            reg_cls_set.add(cls.__name__)
            setattr(cls, '_registered_class', reg_cls_set)
        from jina.jaml import JAML

        JAML.register(cls)
        return cls


class BetterEnum(IntEnum, metaclass=EnumType):
    """The base class of Enum used in Jina."""

    def __str__(self):
        return self.to_string()

    def to_string(self):
        """
        Convert the Enum to string representation
        :return: the string representation of the enum
        """
        return self.name

    def __format__(self, format_spec):  # noqa
        """
        override format method for python 3.7
        :parameter format_spec: format_spec
        :return: format using actual value type unless __str__ has been overridden.
        """
        # credit python 3.9 : https://github.com/python/cpython/blob/612019e60e3a5340542122dabbc7ce5a27a8c635/Lib/enum.py#L755
        # fix to enum BetterEnum not correctly formated
        str_overridden = type(self).__str__ not in (Enum.__str__, Flag.__str__)
        if self._member_type_ is object or str_overridden:
            cls = str
            val = str(self)
        # mix-in branch
        else:
            cls = self._member_type_
            val = self._value_
        return cls.__format__(val, format_spec)

    @classmethod
    def from_string(cls, s: str):
        """
        Parse the enum from a string.

        :param s: string representation of the enum value
        :return: enum value
        """
        try:
            return cls[s.upper()]
        except KeyError:
            raise ValueError(
                f'{s.upper()} is not a valid enum for {cls!r}, must be one of {list(cls)}'
            )

    @classmethod
    def _to_yaml(cls, representer, data):
        """Required by :mod:`pyyaml`.

        .. note::
            In principle, this should inherit from :class:`JAMLCompatible` directly,
            however, this method is too simple and thus replaced the parent method.
        :param representer: pyyaml representer
        :param data: enum value
        :return: yaml representation
        """
        return representer.represent_scalar(
            'tag:yaml.org,2002:str', str(data), style='"'
        )

    @classmethod
    def _from_yaml(cls, constructor, node):
        """Required by :mod:`pyyaml`.

        .. note::
            In principle, this should inherit from :class:`JAMLCompatible` directly,
            however, this method is too simple and thus replaced the parent method.
        :param constructor: unused
        :param node: node to derive the enum value from
        :return: enum value
        """
        return cls.from_string(node.value)


class PollingType(BetterEnum):
    """The enum for representing the parallel type of pods in a deployment."""

    ANY = 1  #: one of the shards will receive the message
    ALL = 2  #: all shards will receive the message, blocked until all done with the message
    ALL_ASYNC = 3  #: (reserved) all replica will receive the message, but any one of them can return, useful in backup

    @property
    def is_push(self) -> bool:
        """
        Check if :class:`PollingType` is using `push` protocol.

        :return: True if this :class:`PollingType` is using `push` protocol else False.
        """
        return self.value == 1

    @property
    def is_block(self) -> bool:
        """
        Check if :class:`PollingType` is using `block` protocol.

        :return: True if this :class:`PollingType` is requiring `block` protocol else False.
        """
        return self.value == 2


class LogVerbosity(BetterEnum):
    """Verbosity level of the logger."""

    DEBUG = 10
    INFO = 20
    SUCCESS = 25
    WARNING = 30
    ERROR = 40
    CRITICAL = 50


class FlowBuildLevel(BetterEnum):
    """
    The enum for representing a flow's build level.

    Some :class:`jina.orchestrate.flow.Flow` class functions require certain build level to run.
    """

    EMPTY = 0  #: Nothing is built
    GRAPH = 1  #: The underlying graph is built, you may visualize the flow
    RUNNING = 2  #: the graph is started and all deployment are running


class DockerNetworkMode(BetterEnum):
    """Potential forced network modes"""

    AUTO = 0
    HOST = 1
    BRIDGE = 2
    NONE = 3


class ProtocolType(BetterEnum):
    """
    Gateway communication protocol
    """

    GRPC = 0
    HTTP = 1
    WEBSOCKET = 2

    @classmethod
    def from_string_list(cls, string_list: List[Union[str, 'ProtocolType']]):
        """
        Returns a list of Enums from a list of strings or enums
        :param string_list: list of strings or enums
        :return: a list of Enums
        """
        return [cls.from_string(s) if isinstance(s, str) else s for s in string_list]


class PodRoleType(BetterEnum):
    """The enum of a Pod role."""

    HEAD = 0
    WORKER = 1
    GATEWAY = 2


class DeploymentRoleType(BetterEnum):
    """The enum of a Deploymen role for visualization."""

    DEPLOYMENT = 0
    JOIN = 1
    INSPECT = 2
    GATEWAY = 3
    INSPECT_AUX_PASS = 4
    JOIN_INSPECT = 5

    @property
    def is_inspect(self) -> bool:
        """
        If the role is inspect deployment related.

        :return: True if the Deployment role is inspect related else False.
        """
        return self.value in {2, 4}


class FlowInspectType(BetterEnum):
    """Inspect strategy in the flow."""

    HANG = 0  # keep them hanging there
    REMOVE = 1  # remove them in the build
    COLLECT = 2  # spawn a new deployment and collect them before build

    @property
    def is_keep(self) -> bool:
        """
        Check if the target is inspected.

        :return: True if the target is inspected else False.
        """
        return self.value in {0, 2}


class DataInputType(BetterEnum):
    """Data input type in the request generator."""

    AUTO = 0  # auto inference the input type from data (!WARN: could be slow as it relies on try-execept)
    DOCUMENT = 1  # the input is a full document
    CONTENT = 2  # the input is just the content of the document
    DICT = 3  # the input is a dictionary representing a Document, needed while pydantic model not available


class WebsocketSubProtocols(str, Enum):
    """Subprotocol supported with Websocket Gateway"""

    JSON = 'json'
    BYTES = 'bytes'


class ProviderType(BetterEnum):
    """Provider type."""

    NONE = 0  #: no provider
    SAGEMAKER = 1  #: AWS SageMaker
    AZURE = 2 #: AZURE


def replace_enum_to_str(obj):
    """
    Transform BetterEnum type into string.

    :param obj: Target obj.
    :return: Transformed obj with string type values.
    """
    for k, v in obj.items():
        if isinstance(v, dict):
            obj[k] = replace_enum_to_str(v)
        elif isinstance(v, BetterEnum):
            obj[k] = str(v)
    return obj
