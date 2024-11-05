(flow-yaml-spec)=
# {octicon}`file-code` YAML specification

To generate a YAML configuration from an Orchestration, use {meth}`~jina.jaml.JAMLCompatible.save_config`.

## YAML completion in IDE

We provide a [JSON Schema](https://json-schema.org/) for your IDE to enable code completion, syntax validation, members listing and displaying help text.

### PyCharm users

1. Click menu `Preferences` -> `JSON Schema mappings`;
2. Add a new schema, in the `Schema File or URL` write `https://schemas.jina.ai/schemas/latest.json`; select `JSON Schema Version 7`;
3. Add a file path pattern and link it to `*.jaml` or `*.jina.yml` or any suffix you commonly used for Jina-serve Flow's YAML.

### VSCode users

1. Install the extension: `YAML Language Support by Red Hat`;
2. In IDE-level `settings.json` add:

```json
"yaml.schemas": {
    "https://schemas.jina.ai/schemas/latest.json": ["/*.jina.yml", "/*.jaml"],
}
```

You can bind Schema to any file suffix you commonly used for Jina-serve Flow's YAML.

## Example YAML

````{tab} Deployment
```yaml
jtype: Deployment
version: '1'
with:
  protocol: http
name: firstexec
uses:
  jtype: MyExec
  py_modules:
    - executor.py
```
````
````{tab} Flow
```yaml
jtype: Flow
version: '1'
with:
  protocol: http
executors:
# inline Executor YAML
- name: firstexec
  uses:
    jtype: MyExec
    py_modules:
      - executor.py
# reference to Executor YAML
- name: secondexec
  uses: indexer.yml
  workspace: /home/my/workspace
# reference to Executor Python class
- name: thirdexec
  uses: CustomExec  # located in executor.py
```
````

## Fields

### `jtype`
String that is always set to either "Flow" or "Deployment", indicating the corresponding Python class.

### `version`
String indicating the version of the Flow or Deployment.

### `with`

Keyword arguments are passed to a Flow's `__init__()` method. You can set Flow-specific arguments and Gateway-specific arguments here:

#### Orchestration arguments

````{tab} Deployment
```{include} deployment-args.md
```
````
````{tab} Flow
```{include} flow-args.md
```
##### Gateway arguments
These apply only to Flows, not Deployments

```{include} gateway-args.md
```
````

(executor-args)=
### `executors`
Collection of Executors used in the Orchestration. In the case of a Deployment, this is a single Executor, while a Flow can have an arbitrary amount.

Each item in the collection specifies one Executor and can be used via:

````{tab} Deployment
```python
dep = Deployment(uses=MyExec, arg1="foo", arg2="bar")
```
````
````{tab} Deployment
```python
f = Flow().add(uses=MyExec, arg1="foo", arg2="bar")
```
````

```{include} executor-args.md
```

```{include} yaml-vars.md
```
