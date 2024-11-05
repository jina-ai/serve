# Login & Token Management

To use Jina AI Cloud, you need to log in, either via a GitHub or Google account. This section describes how to log in Jina AI Cloud and manage the personal access token. You can do it via webpage, CLI or Python API.

## via Webpage

Visit [https://jina.ai](https://jina.ai) and click on the "login" button.

### Login

```{figure} login-1.png
```

After log in you can see your name and avatar in the top-right corner. 

```{figure} login-2.png
```


### Token Management

You can follow the GUI to create/delete personal access tokens for your Jina-serve applications.

```{figure} pat.png
```

To use a token, set it as the environment variable `JINA_AUTH_TOKEN`.

## via CLI

### Login

```shell
jina auth login
```

This will open browser automatically and login via 3rd party. Token will be saved locally.

### Logout

If there is a valid token locally, this will disable that token and remove it from local config.

```shell
jina auth logout
```

### Token Management

#### Create a new PAT

```shell
jina auth token create <name of PAT> -e <expiration days>
```

To use a token, set it as the environment variable `JINA_AUTH_TOKEN`.

#### List PATs

```shell
jina auth token list
```

#### Delete PAT

```shell
jina auth token delete <name of PAT>
```


## via Python API

Installed along with Jina-serve, you can leverage the `hubble` package to manage login from Python

### Login

```python
import hubble

# Log in via browser or PAT. The token is saved locally.
# In Jupyter/Google Colab, interactive login is used automatically.
# To disable this feature, run `hubble.login(interactive=False)`.
hubble.login() 
```

### Check login status

```python
import hubble

if hubble.is_logged_in():
    print('yeah')
else:
    print('no')
```

### Get a personal access token

Notice that the token you got from this function is always valid. If the token is invalid or expired, the result is `None`.

```python
import hubble

hubble.get_token()
```

If you are using inside an interactive environment, i.e. user can input via stdin:

```python
import hubble

hubble.get_token(interactive=True)
```

Mark a function as login required,

```python
import hubble


@hubble.login_required
def foo():
    pass
```


### Logout

```python
import hubble

# If there is a valid token locally,
# this will disable that token and remove it from local config.
hubble.logout()
```

### Token management

After calling `hubble.login()`, you can use the client:

```python
import hubble

client = hubble.Client(max_retries=None, jsonify=True)
# Get current user information.
response = client.get_user_info()
# Create a new personal access token for longer expiration period.
response = client.create_personal_access_token(name='my-pat', expiration_days=30)
# Query all personal access tokens.
response = client.list_personal_access_tokens()
```

### Artifact management

```python
import hubble
import io

client = hubble.Client(max_retries=None, jsonify=True)

# Upload artifact to Hubble Artifact Storage by providing path.
response = client.upload_artifact(f='~/Documents/my-model.onnx', is_public=False)

# Upload artifact to Hubble Artifact Storage by providing `io.BytesIO`
response = client.upload_artifact(
    f=io.BytesIO(b"some initial binary data: \x00\x01"), is_public=False
)

# Get current artifact information.
response = client.get_artifact_info(id='my-artifact-id')

# Download artifact to local directory.
response = client.download_artifact(id='my-artifact-id', f='my-local-filepath')
# Download artifact as an io.BytesIO object
response = client.download_artifact(id='my-artifact-id', f=io.BytesIO())

# Get list of artifacts.
response = client.list_artifacts(filter={'metaData.foo': 'bar'}, sort={'type': -1})

# Delete the artifact.
response = client.delete_artifact(id='my-artifact-id')
```

### Error handling

```python
import hubble

client = hubble.Client()

try:
    client.get_user_info()
except hubble.excepts.AuthenticationRequiredError:
    print('Please login first.')
except Exception:
    print('Unknown error')
```


