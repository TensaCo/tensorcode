![](assets/img/logo-color.png)

# TensaCode: an open source neurosymbolic programming framework for learning structured programs

> TensaCode: Machine Learning + Software Engineering + Runtime Introspection and Code Generation = Programming 2.0

TensaCode is a framework that introduces simple abstractions and functions for encoding, decoding, querying, and manipulating arbitrary python objects, differentiable programming (including differentiable control flow), and intelligent runtime code generation and execution. Rather than just think about the underlying mathematical objects, TensaCode's abstractions enable you to draw on decades of software engineering patterns, paradigms, and derived concepts to concisely approach your underlying problem. If you’re building models that require highly structured inputs or outputs (ie, embarassingly multi-modal architectures), researching the next generation of end-to-end differentiable cognitive architectures, or just adding learning capability on top of an existing program, TensaCode may fit right into your stack!

## Introduction

### TensaCode allows you to do the following

1. encode, decode, query, and manipulate arbitrary objects
2. differentiable programming (including differentiable control flow)
3. intelligently generate and execute code at runtime for a given objective

### What's the Problem?

- ML is a math-heavy field, but the abstract problems we're trying to solve are not.
- Most general ML frameworks are verbose and require a lot of boilerplate
- Differentiable programs currently must be written from scratch in raw math using a framework like PyTorch, TensorFlow, or JAX
- These all make it difficult to prototype and experiment with new architectures

### How does TensaCode solve it?

- We introduce simple abstractions and functions for encoding, decoding, querying, and manipulating arbitrary python objects,
- we also provide a pythonic interface for making regular programs differentiable (including differentiable control flow),
- and we have an introspective runtime code generation and execution engine that can be used to solve a variety of problems.

### How does TensaCode work?

- Under the hood, objects are converted to an intermediate representation, which can be a natural language description, a 0, 1, or 2D-vector embedding, or a graph of embeddings.
- The operation is dynamically dispatched to the appropriate implementation depending on the python type, and intermediate representation type.
- Both gating and RL-based approaches are used for differentiable control flow.
- The program submits feedback to the TensaCode engine, which it uses to improve its performance over time via a combination of RL and synthetic self-supervision.
- Past examples also considtion prompt context, filters, and sampling strategies for runtime code generation and execution.

### Where would I use TensaCode?

- TensaCode is useful for semi-structured problems that require a combination of machine learning, software engineering, and/or runtime introspection and code generation.
- If you can write a complete and precise set of rules for your problem, you're probably better off with traditional software engineering. If your problem is totally unstructured, you're probably better off using a traditional ML framework.
- Examples use cases:
  - Model that require highly structured inputs or outputs (embarassingly multi-modal architectures)
  - End-to-end differentiable cognitive architectures
  - Adding learning capability on top of an existing program

## Getting Started

### Installation

```bash
pip install tensacode
```

### Usage

```python
import tensacode as tc

# encode, decode, query, and manipulate arbitrary objects
...

# differentiable programming (including differentiable control flow)
...

# intelligently generate and execute code at runtime for a given objective
...
```

### Examples

You can find more examples in the [examples](examples) directory.

### A game that learns to maximize user engagement

```python

```

### A GUI assistant (vision + language -> keyboard + mouse)

```python

```

### A self-improving cognitive architecture

```python
# the prompt should be "increase understanding, minimize suffering, maximize peace and prosperity"
# vision, language, STM, LTM, and motor control
```


## Architecture

### Code Organization

```
tensacode/
    __init__.py
    __main__.py
    __version__.py
    _base/
        engine.py
        ops/
            ...
    _text/
        engine.py
        ops/
            op_category/
                op_name.py (contains all op_name overloads):
                    def op(engine, *args, **kwargs):
                        ... # default implementation
                    @op.overload(type1, ...) # just use the python overloading library
                    def op(engine, *args, **kwargs):
                        ... # implementation for type1, ...
                    ...
                ...
            ...
    _vector/
        engine.py
        ops/
            ...
    _graph/
        engine.py
        ops/
            ...
    _utils/
        ...
    _external/
        inspect_mate.py # useful for code introspection
README
LICENSE
CONTRIBUTING
CHANGELOG
poetry.lock
pyproject.toml
.gitignore
```

### Python types

We recognize the following Python types:

- int
- bool
- float
- Range
- str
- bytes
- set (or set-like)
- tuple (or immutable list)
- list (or list-like)
- dict (or dict-like)
- code
- enums
- classes
- modules
- objects

### Intermediate Representation

The intermediate representation can be a natural language description or a 1D, 2D, or 3D-vector embedding, or a graph of homo/heterogenous embeddings.

### Operations

Operations are the core abstraction TensaCode provides. They take in an engine, and some number of arguments, and typically return a result. In some cases, the inputs and outputs can be passed as the annotated python type or as the intermediate representation. This is useful when you want to chain ops without loosing differentiability. Also, operation functions are decorated with the `autoencode` decorator (later).

```python
@autoencode
def op(engine, *args, **kwargs):
    ...
    return result
```

The operations are overloaded for each major type. So `encode` actually dispatches to `encode_bool`, `encode_int`, etc.

Raw operations are decorated with `@track_invocations`. The top level call happens at the engine stub link.

```python
def encode(
    engine,
    input: object,
    max_depth: int = 3,
    context: object = None,
    introspect=True
    ) -> R: ...

def encode_as_generator(
    engine,
    input: object,
    max_depth: int = 3,
    context: object = None,
    introspect=True
    ) -> Generator[R, None, None]: ...

def decode(
    engine,
    type: type[T],
    input: R,
    max_depth: int = 3,
    context: object = None,
    introspect=True
    ) -> T: ...

def decide(
    engine,
    instructions: R,
    context: object = None,
    introspect=True
    ): ...

def choice(
    engine,
    instructions: R,
    options: list[object],
    option_encs: list[R] = None,
    context: object = None,
    introspect=True
    ) -> object: ...

def codegen(
    engine,
    instructions: R,
    context: object = None,
    introspect=True
    ) -> Callable: ...

def exec(
    engine,
    instructions: R,
    context: object = None,
    introspect=True
    ) -> object or None: ...

def similarity(engine, a: R, b: R) -> float: ...

def combine(engine, dst: R, *srcs: list[object]) -> R: ...

def select(
    engine,
    instructions: R,
    *inputs: object = None, # inputs gathered via introspection if not provided
    introspect=True
    ) -> list[object]: ...

def modify(
    engine,
    instructions: R,
    *inputs: object = None, # inputs gathered via introspection if not provided
    introspect=True
    ) -> R: ...

def sort(
    engine,
    instructions: R,
    *inputs: object = None, # inputs gathered via introspection if not provided
    introspect=True
    ) -> object: ...

def anomalies(
    engine,
    instructions: R,
    *inputs: object = None, # inputs gathered via introspection if not provided
    introspect=True
    ) -> range[0, 1]: ...

def patterns(
    engine,
    instructions: R,
    *inputs: list[object] = None, # inputs gathered via introspection if not provided
    introspect=True
    ) -> str: ...

def group(
    engine,
    instructions: R,
    *inputs: object = None, # inputs gathered via introspection if not provided
    introspect=True
    ) -> object: ...

def filter(
    engine,
    instructions: R,
    inputs: list[object],
    ) -> object: ...

def predict(
    engine,
    inputs: list[object],
    ) -> object: ...

# differentiable predict
def predict(
    engine,
    inputs: list[R],
    ) -> R: ...

def combine(
    engine,
    inputs: list[object],
    ) -> object: ...

def fix(
    engine,
    error: Error,
    context: object = None, # inputs gathered via introspection if not provided
    introspect=True
    ) -> object: ...
    '''Useful in smart try-catch auto-debugging, especially when theres runtime code generation happening inside the try block.'''
```

### Engine

The engine is the core of TensaCode. It is responsible for dispatching operations to the appropriate implementation, for tracking calls and learning from feedback. It also stores the config parameters, eg, which LLM to use, what hidden state dimension, etc.

It looks like this:

```python
class Engine:
    model(self, input_nodes: list, output_nodes: list) -> Model: ...
    
    add_loss(self, loss: float) -> None: ...
    reward(self, reward: float) -> None: ...

class TextEngine(Engine): ...
class LocalTextEngine(TextEngine): ...
class RemoteTextEngine(TextEngine): ...

class VectorEngine(Engine): ...
class LocalVectorEngine(VectorEngine): ...
class RemoteVectorEngine(VectorEngine): ...

class Vector1DEngine(VectorEngine): ...
class LocalVector1DEngine(Vector1DEngine, LocalVectorEngine): ...
class RemoteVector1DEngine(Vector1DEngine, RemoteVectorEngine): ...

class Vector2DEngine(VectorEngine): ...
class LocalVector2DEngine(Vector2DEngine, LocalVectorEngine): ...
class RemoteVector2DEngine(Vector2DEngine, RemoteVectorEngine): ...

class Vector3DEngine(VectorEngine): ...
class LocalVector3DEngine(Vector3DEngine, LocalVectorEngine): ...
class RemoteVector3DEngine(Vector3DEngine, RemoteVectorEngine): ...

class GraphEngine(Engine): ...
class LocalGraphEngine(GraphEngine): ...
class RemoteGraphEngine(GraphEngine): ...
```

The engine manages
- instantiating weights / training / add_loss
- check-pointing/loading/saving
- authenticating with service / deploying NN's

Engines are context managed and can enter the focus via with a context manager,

```python
with engine:
    ...
```

or by calling `engine.setdefault()`. The global config also make a default engine available via `tc.engine`, which is used if no engine is specified. It also makes it possible to make top-level operation calls like `tc.encode()`.

### The computation graph

Graph data is stored in the `.__tensacode__` dict attr of the python object. We exploit this information to choose graph-based over tree-based algorithms when possible.

We attach various properties to the objects `.__tensacode__` dict attr. We artificially subclass the python primitives to make this possible. For example, `int` is actually `TensaCodeInt` which is a subclass of `int` that has a `.__tensacode__` dict attr. This allows us to attach properties to the object without having to wrap it in a class. We also use this to attach the engine to the object, so that we can dispatch operations to the appropriate implementation. However our code is designed to handle not having the ability to attach properties to objects, so we can also use a dict to store the graph.

### Export keras/torch/jax models

You can export your programs as ML models with `engine.model()`. And if you only want to export a subset of the op graph, just call `engine.model(input_nodes, output_nodes)`. **Note: the python native parts of the op graph are not exported, so you won't necesarily be able to run the model end-to-end.** For example, if you have a op chain like this: `vector -> vector ops -> decode -> python object -> python code -> encode -> vector -> more vector ops`, then only the vector ops will be exported.

### Arbitrary object encoding and decoding

As a convenience, we shadow the builtin types with our own such that their constructor will attempt to perform a decode(T, encode(arg)) operation when `T(arg)` is not valid for the builtin.

### Runtime code generation and execution

### Decorators

TensaCode provides a number of decorators to make your life easier.

- `@encode_inputs()`: Inputs that expect an IR can be passed a python object, and TensaCode will automatically encode it for you. This is increadibly convenient when you just want to pass a natural language description as a string. You may optionally specify the engine to use, otherwise the default engine will be used. You can also specify the input and output types, otherwise all parameters annotated with the engine's IR type will be used. For example:

    ```python
    from tensacode import Vector1DEngine, encode_inputs
    from python_functinoal_library import use_state, uses_state

    Dhidden = 128
    engine = Vector1DEngine(hidden_dim=Dhidden)

    @uses_state
    @encode_inputs()
    def brainstorm_new_ideas(*context: list[R], seed: R = "Something creative and origonal") -> str:
        print(f"Context: {context}") # context is a list of 1D-vector embeddings
        print(f"Seed: {seed}") # seed is a 1D-vector embedding

        # do some brainstorming
        will_this_work_nn, _ = use_state(lambda : MLP([(Dhidden, Dhidden), Dhidden]))
        if decide(will_this_work_nn(context, seed)):
            seed = engine.combine(seed, context)
    
        # decode the result
        return engine.create(str, seed)
    ```

- `encode_outputs` does the same thing as `encode_inputs`, but for outputs.
- `decode_inputs` is similar to `encode_inputs`, but instead it decodes the inputs with a python type annotation that are passed an IR.
- `decode_outputs` does the same thing as `decode_inputs`, but for outputs.

*You cann specify individual parameters to encode/decode by passing their name as a string to the decorator, eg, `@encode_inputs("context", "seed")`. You can also use the `enc[T]` and `dec[T]` generics to force the decorator's wrapper to only encode or decode specific parameters. Whichever approach you prefer, this is useful when you want to mix convenience encoding, decoding, and untouched args.*

### Common information flows

I need to provide a convenient way to perform many of the common information flows like:
- when a high layer filters information for a low layer
- when a representation charges up in a module before bursting downstream

Maybe these abstractions are best left to a future library.
