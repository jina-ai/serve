(create-hub-executor)=
# Create

To create your {class}`~jina.Executor`, run:

```bash
jina hub new
```

<script id="asciicast-T98aWaJLe0r0ul3cXGk7AzqUs" src="https://asciinema.org/a/T98aWaJLe0r0ul3cXGk7AzqUs.js" async></script>

For basic configuration (advanced configuration is optional but rarely necessary), you will be asked for: 

- Your Executor's name
- The path to the folder where it should be saved

After running the command, a project with the following structure will be generated:

```text
MyExecutor/
├── executor.py
├── config.yml
├── README.md
├── requirements.txt
└── Dockerfile
```

- `executor.py` contains your Executor's main logic.
- `config.yml` is the Executor's {ref}`configuration <executor-yaml-spec>` file, where you can define `__init__` arguments using the `with` keyword. You can also define meta annotations relevant to the Executor, for getting better exposure on Executor Hub.
- `requirements.txt` describes the Executor's Python dependencies.
- `README.md` describes how to use your Executor.
- `Dockerfile` is only generated if you choose advanced configuration.


## Tips

* Use `jina hub new` CLI to create an Executor

  To create an Executor, always use this command and follow the instructions. This ensures the correct file 
structure.

* You don't need to manually write a Dockerfile

  The build system automatically generates an optimized Dockerfile according to your Executor package.


```{tip}
In the `jina hub new` wizard you can choose from four Dockerfile templates: `cpu`, `tf-gpu`, `torch-gpu`, and `jax-gpu`.
```


* If you push your Executor to the [Executor Hub](https://cloud.jina.ai/executors), you don't need to bump the Jina-serve version

  Hub Executors are version-agnostic. When you pull an Executor from Executor Hub, it will select the right Jina-serve version for you. You don't need to upgrade your version of Jina-serve.


* Fill in metadata of your Executor correctly

  Information you include under the `metas` key in `config.yml` is displayed on Executor Hub. `The specification can be found here<config.yml>`.
