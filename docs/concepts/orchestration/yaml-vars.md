## Variables

Jina-serve Orchestration YAML supports variables and variable substitution according to the [GitHub Actions syntax](https://docs.github.com/en/actions/learn-github-actions/environment-variables).

### Environment variables

Use `${{ ENV.VAR }}` to refer to the environment variable `VAR`. You can find all {ref}`Jina environment variables here<jina-env-vars>`.

### Context variables

Use `${{ CONTEXT.VAR }}` to refer to the context variable `VAR`.
Context variables can be passed in the form of a Python dictionary:

````{tab} Deployment
```python
dep = Deployment.load_config('deployment.yml', context={...})
```
````
````{tab} Flow
```python
f = Flow.load_config('flow.yml', context={...})
```
````

### Relative paths

Use `${{root.path.to.var}}` to refer to the variable `var` within the same YAML file, found at the provided path in the file's structure.

```{admonition} Syntax: Environment variable vs relative path
:class: tip

The only difference between environment variable syntax and relative path syntax is the omission of spaces in the latter.
```
