from __future__ import annotations

from abc import ABC, abstractmethod
from contextlib import contextmanager
from copy import deepcopy
import functools
import inspect
from pathlib import Path
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    ClassVar,
    Generator,
    Generic,
    Literal,
    Sequence,
    TypeVar,
)
from uuid import uuid4
import attr
import loguru
from pydantic import Field
import typingx


import tensacode as tc
from tensacode.utils.decorators import Decorator, Default, dynamic_defaults
from tensacode.utils.oo import HasDefault, Namespace
from tensacode.utils.string import invokation
from tensacode.utils.user_types import (
    enc,
    T,
    R,
    atomic_types,
    container_types,
    composite_types,
    tree_types,
    tree,
)
from tensacode.utils.internal_types import nested_dict


class Engine(Generic[T, R], HasDefault, Namespace[R], ABC):
    #######################################
    ############# metadata ################
    #######################################

    T: ClassVar[type[T]] = T
    R: ClassVar[type[R]] = R

    class Proto(Generic[T, R], ABC):
        @abstractmethod
        @classmethod
        def __tc_is_encoded__(cls, engine: Engine, object: T | R) -> bool:
            ...

        @abstractmethod
        @classmethod
        def __tc_encode__(
            cls,
            engine: Engine,
            object: T,
            /,
            depth_limit: int,
            instructions: R,
            **kwargs,
        ) -> R:
            ...

        @abstractmethod
        @classmethod
        def __tc_decode__(
            cls,
            engine: Engine,
            object_enc: R,
            type: type[T],
            /,
            depth_limit: int,
            instructions: R,
            **kwargs,
        ) -> T:
            ...

        @abstractmethod
        @classmethod
        def __tc_retrieve__(
            cls,
            engine: Engine,
            object: composite_types[T],
            /,
            count: int,
            allowed_glob: str,
            disallowed_glob: str,
            depth_limit: int,
            instructions: R,
            **kwargs,
        ) -> T:
            ...

        @abstractmethod
        @classmethod
        def __tc_store__(
            cls,
            engine: Engine,
            object: composite_types[T],
            /,
            values: list[T],
            allowed_glob: str,
            disallowed_glob: str,
            depth_limit: int,
            instructions: R,
            **kwargs,
        ):
            ...

        @abstractmethod
        @classmethod
        def __tc_query__(
            cls,
            engine: Engine,
            object: T,
            /,
            query: enc[T],
            depth_limit: int,
            instructions: R,
            **kwargs,
        ) -> R:
            ...

        @abstractmethod
        @classmethod
        def __tc_modify__(
            cls,
            engine: Engine,
            object: T,
            /,
            depth_limit: int,
            instructions: R,
            **kwargs,
        ) -> T:
            ...

        @abstractmethod
        @classmethod
        def __tc_combine__(
            cls,
            engine: Engine,
            objects: Sequence[T],
            /,
            depth_limit: int,
            instructions: R,
            **kwargs,
        ) -> T:
            ...

        @abstractmethod
        @classmethod
        def __tc_split__(
            cls,
            engine: Engine,
            object: T,
            /,
            num_splits: int,
            depth_limit: int,
            instructions: R,
            **kwargs,
        ) -> tuple[T]:
            ...

        # the type of args supplied in choice_first_winner, choice_last_winner, and run are not ameable to overloading so we dont support it

        @abstractmethod
        @classmethod
        def __tc_similarity__(
            cls,
            engine: Engine,
            objects: tuple[T],
            /,
            depth_limit: int,
            instructions: R,
            **kwargs,
        ) -> float:
            ...

        @abstractmethod
        @classmethod
        def __tc_predict__(
            cls,
            engine: Engine,
            sequence: Sequence[T],
            /,
            steps: int,
            depth_limit: int,
            instructions: R,
            **kwargs,
        ) -> Generator[T, None, None]:
            ...

        @abstractmethod
        @classmethod
        def __tc_correct__(
            cls,
            engine: Engine,
            object: T,
            /,
            threshold: float,
            depth_limit: int,
            instructions: R,
            **kwargs,
        ) -> T:
            ...

    class _HasEngine(ABC):
        _engine: ClassVar[Engine]

    class _EngineDecorator(Decorator, _HasEngine, ABC):
        pass

    @attr.s(auto_attribs=True)
    class DefaultParam(Default, _HasEngine):
        initial_value: Any | None = attr.ib(default=None)
        initializer: Callable[[Engine], Any] | None = attr.ib(default=None)

        def __init__(self, initializer_or_initial_value: Any = None, /, **kw):
            if typingx.isinstance(self.default, Callable[[Engine], Any]):
                self.initializer = initializer_or_initial_value
            else:
                self.initial_value = initializer_or_initial_value
            self.kw = kw
            super().__init__(self.get)

        def get(self, *a, **kw) -> Any:
            initial_val: Any
            if self.initial_value is not None:
                initial_val = self.initial_value
            elif self.initializer is not None:
                initial_val = self.initializer(self._engine)
            else:
                initial_val = None
            return self._engine.param(initial_val, **self.kw)

    @attr.s(auto_attribs=True)
    class trace(_EngineDecorator):
        trace_args = attr.ib(default=True)
        trace_result = attr.ib(default=True)

        def prologue(self, *a, **kw):
            if self.trace_args:
                stacktrace = get_stacktrace(
                    skip_frames=3,
                    frames=self.engine.DefaultParam(
                        lambda engine: engine.trace.frames,
                        name="hparams.trace.frames",
                    ),
                )
                self._engine.inform(
                    [invokation(self.fn, a, kw)] + [... for frametrace in stacktrace]
                )
            return super().prologue(*a, **kw)

        def epilogue(self, retval, *a, **kw):
            if self.trace_result:
                stacktrace = get_stacktrace(
                    skip_frames=3,
                    frames=self.engine.DefaultParam(
                        lambda engine: engine.trace.frames,
                        name="hparams.trace.frames",
                    ),
                )
                self._engine.inform(
                    [invokation(self.fn, a, kw, retval)]
                    + [... for frametrace in stacktrace]
                )
            return super().epilogue(retval, *a, **kw)

    @attr.s(auto_attribs=True)
    class encoded_args(_EngineDecorator):
        encode_args: bool = attr.ib(True)
        decode_retval: bool = attr.ib(True)

        def prologue(self, *a, **kw):
            if self.encode_args:
                # bind params to their values
                signature = inspect.signature(self.fn)
                bound_args = signature.bind_partial(*a, **kw)
                bound_args.apply_defaults()
                bound_args = bound_args.arguments
                # encode the params that are annotated with `enc[...]`
                for param_name, param in signature.parameters.items():
                    if param.annotation is not param.empty and typingx.issubclassx(
                        param.annotation, enc
                    ):
                        if param_name in bound_args:
                            bound_args[param_name] = self._engine.encode(
                                bound_args[param_name]
                            )
                # unpack the bound args
                a, kw = [], {}
                for arg, value in bound_args.items():
                    if arg in signature.parameters:
                        if signature.parameters[arg].kind in (
                            signature.parameters[arg].POSITIONAL_ONLY,
                            signature.parameters[arg].POSITIONAL_OR_KEYWORD,
                        ):
                            a.append(value)
                        elif signature.parameters[arg].kind in (
                            signature.parameters[arg].VAR_POSITIONAL,
                            signature.parameters[arg].KEYWORD_ONLY,
                            signature.parameters[arg].VAR_KEYWORD,
                        ):
                            kw[arg] = value
                a = tuple(a)

            return super().prologue(*a, **kw)

        def epilogue(self, retval, *a, **kw):
            if self.decode_retval:
                # get the return annotation from the function signature
                signature = inspect.signature(self.fn)
                return_annotation = signature.return_annotation

                # check if the return value is annotated with `enc[...]`
                if return_annotation is not signature.empty and typingx.issubclassx(
                    return_annotation, enc
                ):
                    # decode the retval
                    retval = self._engine.decode(retval)

            return super().epilogue(retval, *a, **kw)

    def is_encoded(self, object: T | R) -> bool:
        if TYPE_CHECKING:
            return isinstance(object, R)
        return typingx.isinstancex(object, enc[T]) or self._is_encoded(object)

    #######################################
    ############### config ################
    #######################################

    PARAM_DEFAULTS: ClassVar[nested_dict[str, Any]] = {
        "hparams": {
            "defaults": (
                defaults := {
                    "depth_limit": 10,
                }
            ),
            "trace": {
                "frames": 10,
            },
            "encode": {
                "depth_limit": defaults["depth_limit"],
                "instructions": None,
            },
            "decode": {
                "depth_limit": defaults["depth_limit"],
                "instructions": None,
            },
            "retrieve": {
                "count": 5,
                "depth_limit": defaults["depth_limit"],
                "instructions": None,
            },
            "store": {
                "depth_limit": defaults["depth_limit"],
                "instructions": None,
            },
            "query": {
                "depth_limit": defaults["depth_limit"],
                "instructions": None,
            },
            "modify": {
                "depth_limit": defaults["depth_limit"],
                "instructions": None,
            },
            "combine": {
                "depth_limit": defaults["depth_limit"],
                "instructions": None,
            },
            "split": {
                "num_splits": 2,
                "depth_limit": defaults["depth_limit"],
                "instructions": None,
            },
            "choice": {
                "threshold": 0.5,
                "randomness": 0.1,
                "depth_limit": defaults["depth_limit"],
                "instructions": None,
            },
            "decide": {
                "threshold": 0.5,
                "randomness": 0.1,
                "depth_limit": defaults["depth_limit"],
                "instructions": None,
            },
            "run": {
                "instructions": None,
                "budget": 1.0,
            },
            "similarity": {
                "depth_limit": defaults["depth_limit"],
                "instructions": None,
            },
            "predict": {
                "depth_limit": defaults["depth_limit"],
                "instructions": None,
            },
            "correct": {
                "threshold": 0.5,
                "depth_limit": defaults["depth_limit"],
                "instructions": None,
            },
        },
    }

    params: nested_dict[str, Any]

    #######################################
    ######## intelligence methods #########
    #######################################

    def __init__(self, *args, **kwargs):
        self.params = deepcopy(self.PARAM_DEFAULTS)
        self._HasEngine._engine = self
        super().__init__(*args, **kwargs)

    @encoded_args()
    def param(
        self, initial_value: enc[T] = None, name: str = None, qualname: str = None
    ) -> Any:
        """
        Hook that returns a parameter value. (Aka, like react.use_state, but for parameters.)

        Args:
            initial_value: The initial value of the parameter.
                If the parameter already exists, this argument is ignored.
                If the parameter does not exist, it is initialized to this value.
                If no initial_value is provided, the parameter is initialized to the default value.
            name: The name of the parameter.
                Identifies the parameter in the local namespace.
                If no name is provided, the parameter is given a unique name.
                If a name is provided, and the parameter already exists, `param` returns the parameter value.
            qualname: The qualified name of the parameter.
                Identifies the parameter in the global namespace.
                If no qualname is provided, the qualified name is given by "{engine.qualpath}.{name}".
                If a qualname is provided, and the parameter already exists, `param` returns the parameter value.

        Returns:
            The parameter value.

        Notes:
            For named variables, the key is already known, but for unnamed variables, the key must be idempotently generated.
            `param` achieves this by tracking the order of calling in a given namespace.
            Each unnamed parameter is named in the order it is called like so `f"param_{i}"`
            Functions, classes, and modules all have their own namespace, given by their name relative to the module root.
            You can also manually create a namespace with `engine.namespace`.
            If you want to use param calls inside conditional blocks, you should declare a namespace for each block like so:

            ```
            if condition:
                with engine.namespace(True):
                    x = engine.param()
                    ...
            else:
                with engine.namespace(False):
                    a = engine.param()
                    b = engine.param()
                    c = engine.param()
                    ...
            ```

            This enables your anonymous `engine.param()` will be able to re-run and still use the same param values.

        """

        match name, qualname:
            case None, None:
                # TODO: I need to implement a use_state mechanism that tracks
                # the stack hierarchy and order of calling to make param calls idempotent
                name = ...
            case None, _:
                # keep qualname as is
                pass
            case _, None:
                qualname = self.qualpath + "." + name
            case _, _:
                # qualname overrides name
                pass
        self.params[qualname] = initial_value

    @encoded_args()
    @trace()
    def inform(self, message: enc[T]):
        pass

    @encoded_args()
    @trace()
    def chat(self, message: enc[T]) -> enc[T]:
        pass

    @trace()
    def self_reflect(self):
        pass

    @encoded_args()
    @trace()
    def reward(self, reward: enc[float]):
        pass

    @trace()
    def train(self):
        pass

    @abstractmethod
    @trace()
    def load(self, path: str | Path):
        pass

    @classmethod
    @abstractmethod
    def load(self, path: str | Path):
        pass

    #######################################
    ######## main operator methods ########
    #######################################

    @dynamic_defaults()
    @encoded_args()
    @trace()
    def encode(
        self,
        object: T,
        /,
        depth_limit: int = DefaultParam(
            lambda engine: engine.encode.depth_limit,
            name="hparams.encode.depth_limit",
        ),
        instructions: enc[str] = DefaultParam(
            lambda engine: engine.encode.instructions,
            name="hparams.encode.instructions",
        ),
        **kwargs,
    ) -> R:
        """
        Produces an encoded representation of the `object`.

        Encodings are useful for creating a common representation of objects that can be compared for similarity, fed into a neural network, or stored in a database. This method uses a specific encoding algorithm (which can be customized) to convert the input object into a format that is easier to process and analyze.

        You can customize the encoding algorithm by either subclassing `Engine` or adding a `__tc_encode__` classmethod to `object`'s type class. The `__tc_encode__` method should take in the same arguments as `Engine.encode` and return the encoded representation of the object. See `Engine.Proto.__tc_encode__` for an example.

        Args:
            object (T): The object to be encoded. This could be any data structure like a list, dictionary, custom class, etc.
            depth_limit (int): The maximum depth to which the encoding process should recurse. This is useful for controlling the complexity of the encoding, especially for deeply nested structures. Default is set in the engine's parameters.
            instructions (enc[str]): Additional instructions to the encoding algorithm. This could be used to customize the encoding process, for example by specifying certain features to focus on or ignore.
            **kwargs: Additional keyword arguments that might be needed for specific encoding algorithms. Varies by `Engine`.

        Returns:
            R: The encoded representation of the object. The exact type and structure of this depends on the `Engine` used.

        Examples:
            >>> engine = Engine()
            >>> obj = {"name": "John", "age": 30, "city": "New York"}
            >>> encoded_obj = engine.encode(obj)
            >>> print(encoded_obj)
            # Output: <encoded representation of obj>
        """
        try:
            return type(object).__tc_encode__(
                self,
                object,
                depth_limit=depth_limit,
                instructions=instructions,
                **kwargs,
            )
        except (NotImplementedError, AttributeError):
            pass

        self._encode(
            object, depth_limit=depth_limit, instructions=instructions, **kwargs
        )

    @dynamic_defaults()
    @encoded_args()
    @trace()
    def decode(
        self,
        object_enc: R,
        type: type[T],
        /,
        depth_limit: int = DefaultParam(
            lambda engine: engine.decode.depth_limit,
            name="hparams.decode.depth_limit",
        ),
        instructions: enc[str] = DefaultParam(
            lambda engine: engine.decode.instructions,
            name="hparams.decode.instructions",
        ),
        **kwargs,
    ) -> T:
        """
        Decodes an encoded representation of an object back into its original form or into a different form.

        One of the powerful features of this function is its ability to decode into a different type or modality than the original object. This is controlled by the `type` argument. For example, you could encode a text document into a vector representation, and then decode it into a different language or a summary.

        Args:
            object_enc (R): The encoded representation of the object to be decoded.
            type (type[T]): The expected type of the decoded object. This is used to guide the decoding process. It doesn't have to match the original type of the object before encoding.
            depth_limit (int): The maximum depth to which the decoding process should recurse. This is useful for controlling the complexity of the decoding, especially for deeply nested structures. Default is set in the engine's parameters.
            instructions (enc[str]): Additional instructions to the decoding algorithm. This could be used to customize the decoding process, for example by specifying certain features to focus on or ignore.
            **kwargs: Additional keyword arguments that might be needed for specific decoding algorithms.

        Returns:
            T: The decoded object. The exact type and structure of this depends on the decoding algorithm used and the `type` argument.

        Examples:
            >>> engine = Engine()
            >>> encoded_obj = <encoded representation of an object>
            >>> decoded_obj = engine.decode(encoded_obj, type=NewObjectType)
            >>> print(decoded_obj)
            # Output: <decoded representation of the object in the new type>
        """

        try:
            return type(object_enc).__tc_decode__(
                self,
                object_enc,
                type,
                depth_limit=depth_limit,
                instructions=instructions,
                **kwargs,
            )
        except (NotImplementedError, AttributeError):
            pass

        self._decode(
            object_enc,
            type,
            depth_limit=depth_limit,
            instructions=instructions,
            **kwargs,
        )

    @dynamic_defaults()
    @encoded_args()
    @trace()
    def retrieve(
        self,
        object: composite_types[T],
        /,
        count: int = DefaultParam(
            lambda engine: engine.retrieve.count,
            name="hparams.retrieve.count",
        ),
        allowed_glob: str = None,
        disallowed_glob: str = None,
        depth_limit: int = DefaultParam(
            lambda engine: engine.retrieve.depth_limit,
            name="hparams.retrieve.depth_limit",
        ),
        instructions: enc[str] = DefaultParam(
            lambda engine: engine.retrieve.instructions,
            name="hparams.retrieve.instructions",
        ),
        **kwargs,
    ) -> T:
        """
        Retrieves an object from the engine.

        This method is used to retrieve an object from the engine based on the provided parameters. The object is retrieved in the form specified by the 'object' parameter.

        Args:
            object (composite_types[T]): The type of object to be retrieved.
            count (int): The number of objects to retrieve. Default is set in the engine's hyperparameters.
            allowed_glob (str): A glob pattern that the retrieved object's qualname (relative to `object`) must match. If None, no name filtering is applied.
            disallowed_glob (str): A glob pattern that the retrieved object's qualname (relative to `object`) must not match. If None, no name filtering is applied.
            depth_limit (int): The maximum depth to which the retrieval process should recurse. This is useful for controlling the complexity of the retrieval, especially for deeply nested structures. Default is set in the engine's hyperparameters.
            instructions (enc[str]): Additional instructions to the retrieval algorithm. This could be used to customize the retrieval process, for example by specifying certain areas of the search space to prioritize or ignore.
            **kwargs: Additional keyword arguments that might be needed for specific retrieval algorithms. Varies by `Engine`.

        Returns:
            T: The retrieved object. The exact type and structure of this depends on the `Engine` used.

        Example:
            >>> engine = Engine()
            >>> class Person:
            ...    name: str
            ...    bio: str
            ...    thoughts: list[str]
            ...    friends: list[Person]
            >>> john, teyoni, huimin = ... # create people
            >>> person = engine.retrieve(john, instructions="find john's least favorite friend")
        """

        try:
            return type(object).__tc_retrieve__(
                self,
                object,
                count=count,
                allowed_glob=allowed_glob,
                disallowed_glob=disallowed_glob,
                depth_limit=depth_limit,
                instructions=instructions,
                **kwargs,
            )
        except (NotImplementedError, AttributeError):
            pass

        return self._retrieve(
            object,
            count=count,
            allowed_glob=allowed_glob,
            disallowed_glob=disallowed_glob,
            depth_limit=depth_limit,
            instructions=instructions,
            **kwargs,
        )

    @dynamic_defaults()
    @encoded_args()
    @trace()
    def store(
        self,
        object: composite_types[T],
        /,
        values: list[T] = None,
        allowed_glob: str = None,
        disallowed_glob: str = None,
        depth_limit: int = DefaultParam(
            lambda engine: engine.store.depth_limit,
            name="hparams.store.depth_limit",
        ),
        instructions: enc[str] = DefaultParam(
            lambda engine: engine.store.instructions,
            name="hparams.store.instructions",
        ),
        **kwargs,
    ):
        """
        Stores the `object` with the given `values`.

        This method uses a specific storage algorithm (which can be customized) to store the input object along with its values. The storage process can be controlled by the `allowed_glob`, `disallowed_glob`, and `depth_limit` parameters.

        You can customize the storage algorithm by either subclassing `Engine` or adding a `__tc_store__` classmethod to `object`'s type class. The `__tc_store__` method should take in the same arguments as `Engine.store` and perform the storage operation.

        Args:
            object (T): The object to be stored. This could be any data structure like a list, dictionary, custom class, etc.
            values (list[T]): The values to be stored along with the object.
            allowed_glob (str): A glob pattern that specifies which parts of the object are allowed to be stored. Default is None, which means all parts are allowed.
            disallowed_glob (str): A glob pattern that specifies which parts of the object are not allowed to be stored. Default is None, which means no parts are disallowed.
            depth_limit (int): The maximum depth to which the storage process should recurse. This is useful for controlling the complexity of the storage, especially for deeply nested structures. Default is set in the engine's parameters.
            instructions (enc[str]): Additional instructions to the storage algorithm. This could be used to customize the storage process, for example by specifying certain features to focus on or ignore.
            **kwargs: Additional keyword arguments that might be needed for specific storage algorithms.

        Returns:
            None

        Example:
            >>> engine = Engine()
            >>> class Person:
            ...    name: str
            ...    bio: str
            ...    thoughts: list[str]
            ...    friends: list[Person]
            >>> john, teyoni, huimin = ... # create people
            >>> person = engine.store(john, [huimin], instructions="she is his friend")
        """
        try:
            return type(object).__tc_store__(
                self,
                object,
                values=values,
                allowed_glob=allowed_glob,
                disallowed_glob=disallowed_glob,
                depth_limit=depth_limit,
                instructions=instructions,
                **kwargs,
            )
        except (NotImplementedError, AttributeError):
            pass

        return self._store(
            object,
            values=values,
            allowed_glob=allowed_glob,
            disallowed_glob=disallowed_glob,
            depth_limit=depth_limit,
            instructions=instructions,
            **kwargs,
        )

    @dynamic_defaults()
    @encoded_args()
    @trace()
    def query(
        self,
        object: T,
        /,
        query: enc[T],
        depth_limit: int = DefaultParam(
            lambda engine: engine.query.depth_limit,
            name="hparams.query.depth_limit",
        ),
        instructions: enc[str] = DefaultParam(
            lambda engine: engine.query.instructions,
            name="hparams.query.instructions",
        ),
        **kwargs,
    ) -> R:
        """
        Extracts latent information from the `object` based on the `query`.

        This method is used to extract information from the `object` based on the `query`. The `query` is a encoded string that specifies what information to extract from the `object`.

        Args:
            object (T): The object to extract information from.
            query (enc[T]): The query specifying what information to extract.
            depth_limit (int, optional): The maximum depth to which the extraction process should recurse. Defaults to engine's hyperparameters.
            instructions (enc[str], optional): Additional instructions to the extraction algorithm. Defaults to engine's hyperparameters.
            **kwargs: Additional keyword arguments that might be needed for specific extraction algorithms.

        Returns:
            R: The extracted information. The exact type and structure of this depends on the `Engine` used.

        Example:
            >>> engine = Engine()
            >>> class Person:
            ...    name: str
            ...    bio: str
            ...    thoughts: list[str]
            ...    friends: list[Person]
            >>> john, teyoni, huimin = ... # create people
            >>> info = engine.query(john, query="Does John know that Teyoni has a crush on him?")
            >>> engine.decode(info, type=bool)
            ... True
        """

        try:
            return type(object).__tc_query__(
                self,
                object,
                query=query,
                depth_limit=depth_limit,
                instructions=instructions,
                **kwargs,
            )
        except (NotImplementedError, AttributeError):
            pass

        return self._query(object, query=query, depth_limit=depth_limit, **kwargs)

    @dynamic_defaults()
    @encoded_args()
    @trace()
    def modify(
        self,
        object: T,
        /,
        depth_limit: int = DefaultParam(
            lambda engine: engine.modify.depth_limit,
            name="hparams.modify.depth_limit",
        ),
        instructions: enc[str] = DefaultParam(
            lambda engine: engine.modify.instructions,
            name="hparams.modify.instructions",
        ),
        **kwargs,
    ) -> T:
        """
        Modifies an object *in place* based on the `instructions`.

        Args:
            object (composite_types[T]): The type of object to be modified.
            depth_limit (int): The maximum depth to which the modification process should recurse. This is useful for controlling the complexity of the modification, especially for deeply nested structures. Default is set in the engine's hyperparameters.
            instructions (enc[str]): Additional instructions to the modification algorithm. This could be used to customize the modification process, for example by specifying certain areas of the search space to prioritize or ignore.
            **kwargs: Additional keyword arguments that might be needed for specific modification algorithms. Varies by `Engine`.

        Returns:
            T: The modified object. The exact type and structure of this depends on the `Engine` used.

        Example:
            >>> engine = Engine()
            >>> class Person:
            ...    name: str
            ...    bio: str
            ...    thoughts: list[str]
            ...    friends: list[Person]
            >>> john, teyoni, huimin = ... # create people
            >>> engine.modify(john, instructions="john's favorite color is blue")
        """
        try:
            return type(object).__tc_modify__(
                self,
                object,
                depth_limit=depth_limit,
                instructions=instructions,
                **kwargs,
            )
        except (NotImplementedError, AttributeError):
            pass

        return self._modify(object, depth_limit=depth_limit, instructions=instructions)

    @dynamic_defaults()
    @encoded_args()
    @trace()
    def combine(
        self,
        objects: Sequence[T],
        /,
        depth_limit: int = DefaultParam(
            lambda engine: engine.combine.depth_limit,
            name="hparams.combine.depth_limit",
        ),
        instructions: enc[str] = DefaultParam(
            lambda engine: engine.combine.instructions,
            name="hparams.combine.instructions",
        ),
        **kwargs,
    ) -> T:
        """
        Combines multiple objects into a single object.

        This method is used to combine multiple objects into a single object based on the provided parameters. The combined object is returned in the form specified by the 'objects' parameter.

        Args:
            objects (Sequence[T]): The sequence of objects to be combined.
            depth_limit (int): The maximum depth to which the combination process should recurse. This is useful for controlling the complexity of the combination, especially for deeply nested structures. Default is set in the engine's hyperparameters.
            instructions (enc[str]): Additional instructions to the combination algorithm. This could be used to customize the combination process, for example by specifying certain areas of the search space to prioritize or ignore.
            **kwargs: Additional keyword arguments that might be needed for specific combination algorithms. Varies by `Engine`.

        Returns:
            T: The combined object. The exact type and structure of this depends on the `Engine` used.

        Example:
            >>> engine = Engine()
            >>> class Person:
            ...    name: str
            ...    bio: str
            ...    thoughts: list[str]
            ...    friends: list[Person]
            >>> john, teyoni, huimin = ... # create people
            >>> group = engine.combine([john, teyoni, huimin], instructions="make them into a composite person")
            >>> print(group)
            ... Person(name="John, Teyoni, and Huimin", bio="...", thoughts=["...", "...", "..."], friends=[...])
        """
        try:
            return type(objects[0]).__tc_combine__(
                self,
                objects,
                depth_limit=depth_limit,
                instructions=instructions,
                **kwargs,
            )
        except (NotImplementedError, AttributeError):
            pass

        return self._combine(
            objects, depth_limit=depth_limit, instructions=instructions, **kwargs
        )

    @dynamic_defaults()
    @encoded_args()
    @trace()
    def split(
        self,
        object: T,
        /,
        num_splits: int = DefaultParam(
            lambda engine: engine.split.num_splits,
            name="hparams.split.num_splits",
        ),
        depth_limit: int = DefaultParam(
            lambda engine: engine.split.depth_limit,
            name="hparams.split.depth_limit",
        ),
        instructions: enc[str] = DefaultParam(
            lambda engine: engine.split.instructions,
            name="hparams.split.instructions",
        ),
        **kwargs,
    ) -> tuple[T]:
        """
        Splits an object into a specified number of parts.

        This method is used to split an object into a specified number of parts based on the provided parameters. The object is split in the form specified by the 'object' parameter.

        Args:
            object (T): The object to be split.
            num_splits (int): The number of parts to split the object into. Default is set in the engine's hyperparameters.
            depth_limit (int): The maximum depth to which the splitting process should recurse. This is useful for controlling the complexity of the splitting, especially for deeply nested structures. Default is set in the engine's hyperparameters.
            instructions (enc[str]): Additional instructions to the splitting algorithm. This could be used to customize the splitting process, for example by specifying certain areas of the search space to prioritize or ignore.
            **kwargs: Additional keyword arguments that might be needed for specific splitting algorithms. Varies by `Engine`.

        Returns:
            tuple[T]: The split parts of the object. The exact type and structure of this depends on the `Engine` used.

        Example:
            >>> engine = Engine()
            >>> class Person:
            ...    name: str
            ...    bio: str
            ...    thoughts: list[str]
            ...    friends: list[Person]
            >>> john, teyoni, huimin = ... # create people
            >>> group = engine.combine([john, teyoni, huimin], instructions="make them into a composite person")
            >>> john_split, teyoni_split, huimin_split = engine.split(group, instructions="split them into their original forms")
            >>> print(john_split)
            ... Person(name="John", bio="...", thoughts=["..."], friends=[...])
        """
        try:
            return type(object).__tc_split__(
                self,
                object,
                num_splits=num_splits,
                depth_limit=depth_limit,
                instructions=instructions,
                **kwargs,
            )
        except (NotImplementedError, AttributeError):
            pass

        return self._split(
            object,
            num_splits=num_splits,
            depth_limit=depth_limit,
            instructions=instructions,
            **kwargs,
        )

    @dynamic_defaults()
    @encoded_args()
    @trace()
    def choice(
        self,
        conditions_and_functions: tuple[Callable[..., bool], Callable[..., T]],
        /,
        mode: Literal["first-winner", "last-winner"] = "first-winner",
        default_case_idx: int | None = None,
        threshold: float = DefaultParam(
            lambda engine: engine.hparams.choice.threshold,
            "hparams.choice.threshold",
        ),
        randomness: float = DefaultParam(
            lambda engine: engine.hparams.choice.randomness,
            "hparams.choice.randomness",
        ),
        depth_limit: int = DefaultParam(
            lambda engine: engine.hparams.choice.depth_limit,
            name="hparams.choice.depth_limit",
        ),
        instructions: enc[str] = DefaultParam(
            lambda engine: engine.hparams.choice.instructions,
            name="hparams.choice.instructions",
        ),
        **kwargs,
    ) -> T:
        """
        Executes a choice operation based on the provided conditions and functions.

        Args:
            conditions_and_functions (tuple): A tuple of callables representing conditions and corresponding functions.
            mode (str): The mode of operation. Can be either "first-winner" or "last-winner".
            default_case_idx (int, optional): The index of the default case to use if no condition surpasses the threshold. Defaults to None.
            threshold (float): The threshold value for condition evaluation.
            randomness (float): The randomness factor in choice selection.
            depth_limit (int): The maximum depth for recursion.
            instructions (str): Additional instructions for the choice operation.
            **kwargs: Additional keyword arguments.

        Returns:
            T: The result of the executed function corresponding to the winning condition.
        """
        match mode:
            case "first-winner":
                # evaluate the conditions in order
                # pick first one to surpass threshold
                # default to default_case or raise ValueError if no default_case
                return self._choice_first_winner(
                    conditions_and_functions,
                    default_case_idx=default_case_idx,
                    threshold=threshold,
                    randomness=randomness,
                    depth_limit=depth_limit,
                    instructions=instructions,
                    **kwargs,
                )
            case "last-winner":
                # evaluate all conditions
                # pick global max
                # default to default_case or raise ValueError if no default_case
                return self._choice_last_winner(
                    conditions_and_functions,
                    default_case_idx=default_case_idx,
                    threshold=threshold,
                    randomness=randomness,
                    depth_limit=depth_limit,
                    instructions=instructions,
                    **kwargs,
                )
            case _:
                raise ValueError(f"Invalid mode: {mode}")

    @dynamic_defaults()
    @encoded_args()
    @trace()
    def decide(
        self,
        condition: T,
        if_true: Callable = lambda *a, **kw: True,
        if_false: Callable = lambda *a, **kw: False,
        *,
        threshold: float = DefaultParam(
            lambda engine: engine.hparams.choice.threshold,
            "hparams.choice.threshold",
        ),
        randomness: float = DefaultParam(
            lambda engine: engine.hparams.choice.randomness,
            "hparams.choice.randomness",
        ),
        depth_limit: int = DefaultParam(
            lambda engine: engine.hparams.choice.depth_limit,
            name="hparams.choice.depth_limit",
        ),
        instructions: enc[str] = DefaultParam(
            lambda engine: engine.hparams.choice.instructions,
            name="hparams.choice.instructions",
        ),
        **kwargs,
    ):
        """
        Makes a decision based on the provided condition. If the condition is met, the `if_true` function is called. Otherwise, the `if_false` function is called.

        Can be called in two ways:
        - `fn_result = engine.decide(condition, if_true=..., if_false=..., ...)`: in this case, you define the true and false branches as separate functions and pass them in as arguments. `engine.decide` then calls the appropriate function based on the condition.
        - `bool_result = engine.decide(condition, ...)`: in this case, you don't define the true and false branches, and `engine.decide` returns a boolean value based on the condition.

        Args:
            condition (T): The condition to evaluate.
            if_true (Callable): The function to call if the condition is met.
            if_false (Callable): The function to call if the condition is not met.
            threshold (float): The threshold for making the decision.
            randomness (float): The randomness factor in the decision making.
            depth_limit (int): The maximum depth to which the decision process should recurse.
            instructions (enc[str]): Additional instructions to the decision algorithm.
            **kwargs: Additional keyword arguments that might be needed for specific decision algorithms.

        Returns:
            The result of the `if_true` function if the condition is met, or the result of the `if_false` function if the condition is not met.

        Example:
            >>> engine = Engine()
            >>> class Person:
            ...    name: str
            ...    bio: str
            ...    thoughts: list[str]
            ...    friends: list[Person]
            >>> john, teyoni, huimin = ... # create people
            >>> person = engine.retrieve(john, instructions="find john's least favorite friend")
            ... # based on John's friends, decide if he is a jerk or not
            >>> engine.decide(person, if_true=lambda: print("John is a jerk"), if_false=lambda: print("John is a nice guy"))
            ... John is a jerk
        """
        return self.choice(
            [
                (condition, if_true),
                (lambda *a, **kw: not condition(*a, **kw), if_false),
            ],
            mode="last-winner",
            threshold=threshold,
            randomness=randomness,
            depth_limit=depth_limit,
            instructions=instructions,
            **kwargs,
        )

    @dynamic_defaults()
    @encoded_args()
    @trace()
    def run(
        self,
        instructions: enc[str] = DefaultParam(
            lambda engine: engine.run.instructions,
            name="hparams.run.instructions",
        ),
        /,
        budget: float = DefaultParam(
            lambda engine: engine.run.budget,
            name="hparams.run.budget",
        ),
        **kwargs,
    ) -> Any:
        # TODO: write docstring
        return self._run(instructions, budget=budget, **kwargs)

    @dynamic_defaults()
    @encoded_args()
    @trace()
    def similarity(
        self,
        objects: tuple[T],
        /,
        depth_limit: int = DefaultParam(
            lambda engine: engine.similarity.depth_limit,
            name="hparams.similarity.depth_limit",
        ),
        instructions: enc[str] = DefaultParam(
            lambda engine: engine.similarity.instructions,
            name="hparams.similarity.instructions",
        ),
        **kwargs,
    ) -> float:
        # TODO: write docstring
        try:
            return type(objects[0]).__tc_similarity__(
                self,
                objects,
                depth_limit=depth_limit,
                instructions=instructions,
                **kwargs,
            )
        except (NotImplementedError, AttributeError):
            pass

        return self._similarity(
            objects, depth_limit=depth_limit, instructions=instructions, **kwargs
        )

    @dynamic_defaults()
    @encoded_args()
    @trace()
    def predict(
        self,
        sequence: Sequence[T],
        /,
        steps: int = 1,
        depth_limit: int = DefaultParam(
            lambda engine: engine.predict.depth_limit,
            name="hparams.predict.depth_limit",
        ),
        instructions: enc[str] = DefaultParam(
            lambda engine: engine.predict.instructions,
            name="hparams.predict.instructions",
        ),
        **kwargs,
    ) -> Generator[T, None, None]:
        # TODO: write docstring
        try:
            return type(sequence[0]).__tc_predict__(
                self,
                sequence,
                steps=steps,
                depth_limit=depth_limit,
                instructions=instructions,
                **kwargs,
            )
        except (NotImplementedError, AttributeError):
            pass

        return self._predict(
            sequence,
            steps=steps,
            depth_limit=depth_limit,
            instructions=instructions,
            **kwargs,
        )

    @dynamic_defaults()
    @encoded_args()
    @trace()
    def correct(
        self,
        object: T,
        /,
        threshold: float = DefaultParam(
            lambda engine: engine.correct.threshold,
            name="hparams.correct.threshold",
        ),
        depth_limit: int = DefaultParam(
            lambda engine: engine.correct.depth_limit,
            name="hparams.correct.depth_limit",
        ),
        instructions: enc[str] = DefaultParam(
            lambda engine: engine.correct.instructions,
            name="hparams.correct.instructions",
        ),
        **kwargs,
    ) -> T:
        # TODO: write docstring
        try:
            return type(object).__tc_correct__(
                self,
                object,
                threshold=threshold,
                depth_limit=depth_limit,
                instructions=instructions,
                **kwargs,
            )
        except (NotImplementedError, AttributeError):
            pass

        return self._correct(
            object,
            threshold=threshold,
            depth_limit=depth_limit,
            instructions=instructions,
            **kwargs,
        )

    #######################################
    ######## core operator methods ########
    ##### (subclasasaes override here) ####
    #######################################

    @abstractmethod
    def _is_encoded(self, object: T | R) -> bool:
        ...

    @abstractmethod
    def _encode(
        self,
        object: T,
        /,
        depth_limit: int,
        instructions: R,
        **kwargs,
    ) -> R:
        ...

    @abstractmethod
    def _decode(
        self,
        object_enc: R,
        type: type[T],
        /,
        depth_limit: int,
        instructions: R,
        **kwargs,
    ) -> T:
        ...

    @abstractmethod
    def _retrieve(
        self,
        object: composite_types[T],
        /,
        count: int,
        allowed_glob: str,
        disallowed_glob: str,
        depth_limit: int,
        instructions: R,
        **kwargs,
    ) -> T:
        ...

    @abstractmethod
    def _store(
        self,
        object: composite_types[T],
        /,
        values: list[T],
        allowed_glob: str,
        disallowed_glob: str,
        depth_limit: int,
        instructions: R,
        **kwargs,
    ):
        ...

    @abstractmethod
    def _query(
        self,
        object: T,
        /,
        query: enc[T],
        depth_limit: int,
        instructions: R,
        **kwargs,
    ) -> R:
        ...

    @abstractmethod
    def _modify(
        self,
        object: T,
        /,
        depth_limit: int,
        instructions: R,
        **kwargs,
    ) -> T:
        ...

    @abstractmethod
    def _combine(
        self,
        objects: Sequence[T],
        /,
        depth_limit: int,
        instructions: R,
        **kwargs,
    ) -> T:
        ...

    @abstractmethod
    def _split(
        self,
        object: T,
        /,
        num_splits: int,
        depth_limit: int,
        instructions: R,
        **kwargs,
    ) -> tuple[T]:
        ...

    @abstractmethod
    def _choice_first_winner(
        self,
        conditions_and_functions: tuple[Callable[..., bool], Callable[..., T]],
        /,
        default_case_idx: int | None,
        threshold: float,
        randomness: float,
        depth_limit: int,
        instructions: R,
        **kwargs,
    ) -> T:
        ...

    @abstractmethod
    def _choice_last_winner(
        self,
        conditions_and_functions: tuple[Callable[..., bool], Callable[..., T]],
        /,
        default_case_idx: int | None,
        threshold: float,
        randomness: float,
        depth_limit: int,
        instructions: R,
        **kwargs,
    ) -> T:
        ...

    @abstractmethod
    def _run(
        self,
        instructions: R,
        /,
        budget: float | None,
        **kwargs,
    ) -> Any:
        ...

    @abstractmethod
    def _similarity(
        self,
        objects: tuple[T],
        /,
        depth_limit: int,
        instructions: R,
        **kwargs,
    ) -> float:
        ...

    @abstractmethod
    def _predict(
        self,
        sequence: Sequence[T],
        /,
        steps: int,
        depth_limit: int,
        instructions: R,
        **kwargs,
    ) -> Generator[T, None, None]:
        ...

    @abstractmethod
    def _correct(
        self,
        object: T,
        /,
        threshold: float,
        depth_limit: int,
        instructions: R,
        **kwargs,
    ) -> T:
        ...
