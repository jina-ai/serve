(executor-file-structure)=
# File Structure

Besides organizing your {class}`~jina.Executor` code inline, you can also write it as an "external" module and then use it via YAML. This is useful when your Executor's logic is too complicated to fit into a single file.

```{tip}
The best practice is to use `jina hub new` to create a new Executor. It automatically generates the files you need in the correct structure.
```

## Single Python file + YAML

When you are only working with a single Python file (let's call it `my_executor.py`), you can put it at the root of your repository, and import it directly in `config.yml`

```yaml
jtype: MyExecutor
py_modules:
  - my_executor.py
```

## Multiple Python files + YAML

When you are working with multiple Python files, you should organize them as a **Python package** and put them in a special folder inside
your repository (as you would normally do with Python packages). Specifically, you should do the following:

- Put all Python files (as well as an `__init__.py`) inside a special folder (called `executor` by convention.)
  - Because of how Jina-serve registers Executors, ensure you import your Executor in this `__init__.py` (see the contents of `executor/__init__.py` in the example below).
- Use relative imports (`from .bar import foo`, and not `from bar import foo`) inside the Python modules in this folder.
- Only list `executor/__init__.py` under `py_modules` in `config.yml` - this way Python knows that you are importing a package, and ensures that all relative imports within your package work properly.

To make things more specific, take this repository structure as an example:

```
.
├── config.yml
└── executor
    ├── helper.py
    ├── __init__.py
    └── my_executor.py
```

The contents of `executor/__init__.py` is:

```python
from .my_executor import MyExecutor
```

the contents of `executor/helper.py` is:

```python
def print_something():
    print('something')
```

and the contents of `executor/my_executor.py` is:

```python
from jina import Executor, requests

from .helper import print_something


class MyExecutor(Executor):
    @requests
    def foo(self, **kwargs):
        print_something()
```

Finally, the contents of `config.yml`: 

```yaml
jtype: MyExecutor
py_modules:
  - executor/__init__.py
```

Note that only `executor/__init__.py` needs to be listed under `py_modules`

This is a relatively simple example, but this way of structuring Python modules works for any Python package structure, however complex. Consider this slightly more complicated example:

```
.
├── config.yml           # Remains exactly the same as before
└── executor
    ├── helper.py
    ├── __init__.py
    ├── my_executor.py
    └── utils/
        ├── __init__.py  # Required inside all executor sub-folders
        ├── data.py
        └── io.py
```

You can then import from `utils/data.py` in `my_executor.py` like this: `from .utils.data import foo`, and perform any other kinds of relative imports that Python enables.

The best thing is that no matter how complicated your package structure, "importing" it in your `config.yml` file is simple - you always put only `executor/__init__.py` under `py_modules`.
