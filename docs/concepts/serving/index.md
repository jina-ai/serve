(serving)=
# {fas}`gears` Serving

As seen in the {ref}`architecture overview <architecture-overview>`, Jina-serve is organized in different layers.

The Serving layer is composed of concepts that allow developers to write their logic to be served by the objects in {ref}`orchestration <orchestration>` layer.

Two objects belong to this family:
- Executor ({class}`~jina.Executor`), serves your logic based on [docarray](https://docs.docarray.org/) data structures.
- Gateway ({class}`~jina.Gateway`), directs all the traffic when multiple Executors are combined inside a Flow.

```{toctree}
:hidden:

executor/index
gateway/index
```
