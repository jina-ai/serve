> The best way to know more about contributing and how to get started is to **[join us on Discord](https://discord.jina.ai)** and ask questions in our public channels.

# Contributing to Jina

Thanks for your interest in contributing to Jina. We're grateful for your initiative! ❤️

In this guide, we're going to go through the steps for each kind of contribution, and good and bad examples of what to do. We look forward to your contributions!

<!-- START doctoc generated TOC please keep comment here to allow auto update -->
<!-- DON'T EDIT THIS SECTION, INSTEAD RE-RUN doctoc TO UPDATE -->

- [🐞 Bugs and Issues](#-bugs-and-issues)
- [🥇 Making Your First Submission](#-making-your-first-submission)
- [☑️ Naming Conventions](#-naming-conventions)
- [💥 Testing Jina Locally and on CI](#-testing-jina-locally-and-on-ci)
- [📖 Contributing Documentation](#-contributing-documentation)
- [🙏 Thank You](#-thank-you)

<!-- END doctoc generated TOC please keep comment here to allow auto update -->

<a name="-bugs-and-issues"></a>
## 🐞 Bugs and Issues

### Submitting Issues

We love to get issue reports. But we love it even more if they're in the right format. For any bugs you encounter, we need you to:

* **Describe your problem**: What exactly is the bug. Be as clear and concise as possible
* **Why do you think it's happening?** If you have any insight, here's where to share it

There are also a couple of nice to haves:

* **Environment:** You can find this with ``jina -vf``
* **Screenshots:** If they're relevant

<a name="-making-your-first-submission"></a>
## 🥇 Making Your First Submission

0. Associate your local git config with your GitHub account. If this is your first time using git you can follow [the steps](#associate-with-github-account).
1. Fork the Jina repo and clone onto your computer. 
1. Configure git pre-commit hooks. Please follow [the steps](#install-pre-commit-hooks)
1. Create a [new branch](#naming-your-branch), for example `fix-jina-typo-1`.
1. Work on this branch to do the fix/improvement.
1. Check if your code changes follow the [code review guidelines](.github/CODE_REVIEW_GUIDELINES.md).
1. Commit the changes with the [correct commit style](#writing-your-commit-message).
1. Make a pull request.
1. Submit your pull request and wait for all checks to pass.
1. Request reviews from one of [the code owners](.github/CODEOWNERS).
1. Get a LGTM 👍 and PR gets merged.

**Note:** If you're just fixing a typo or grammatical issue, you can go straight to a pull request.

### Associate with GitHub Account

- Confirm username and email on [your profile page](https://github.com/settings/profile).
- Set git config on your computer.

```shell
git config user.name "YOUR GITHUB NAME"
git config user.email "YOUR GITHUB EMAIL"
```

- (Optional) Reset the commit author if you made commits before you set the git config.

```shell
git checkout YOUR-WORKED-BRANCH
git commit --amend --author="YOUR-GITHUB-NAME <YOUR-GITHUB-EMAIL>" --no-edit
git log  # to confirm the change is effective
git push --force
```

What happens after the merge? [Understand the development stage and release cycles here.](RELEASE.md)

### Install pre-commit hooks

In Jina we use git's pre-commit hooks in order to make sure the code matches our standards of quality and documentation. At the moment we employ them for checking the style and the docstrings of the code. Documentation of code is crucial to maintaining productive developers and clear communication with new users. We also want to reduce all arguments about code styling.

It's easy to configure it:

1. `pip install pre-commit`
1. `pre-commit install`

Now you will be automatically reminded to add docstrings to your code. `black` will take care that your code will match our style. Note that `black` will fail your commit but reformat your code, so you just need to add the files again and commit **again**.

For more about our docstring style, refer to [this guide](./.github/DOCSTRINGS.rst).

#### Restoring correct git blame

Run `git config blame.ignoreRevsFile .github/.git-blame-ignore-revs`

<a name="-naming-conventions"></a>
## ☑️ Naming Conventions

For branches, commits, and PRs we follow some basic naming conventions:

* Be descriptive
* Use all lower-case
* Limit punctuation
* Include one of our specified [types](#specify-the-correct-types)
* Short (under 70 characters is best)
* In general, follow the [Conventional Commit](https://www.conventionalcommits.org/en/v1.0.0/#summary) guidelines

Note: If you don't follow naming conventions, your commit will be automatically flagged to be fixed.

### Specify the correct types

Type is an important prefix in PR, commit message. For each branch, commit, or PR, we need you to specify the type to help us keep things organized. For example,

```
feat: add hat wobble
^--^  ^------------^
|     |
|     +-> Summary in present tense.
|
+-------> Type: build, ci, chore, docs, feat, fix, refactor, style, or test.
```

- build: Changes that affect the build system or external dependencies (example scopes: gulp, broccoli, npm)
- ci: Changes to our CI configuration files and scripts (example scopes: Travis, Circle, BrowserStack, SauceLabs)
- docs: Documentation only changes
- feat: A new feature
- fix: A bug fix
- perf: A code change that improves performance
- refactor: A code change that neither fixes a bug nor adds a feature
- style: Changes that do not affect the meaning of the code (white-space, formatting, missing semi-colons, etc.)
- test: Adding missing tests or correcting existing tests
- chore: updating grunt tasks etc; no production code change

### Naming your Branch

Your branch name should follow the format `type-scope(-issue_id)`:

* `type` is one of the [types above](#specify-the-correct-types)
* `scope` is optional, and represents the module your branch is working on.
* `issue_id` is [the GitHub issue](https://github.com/jina-ai/jina/issues) number. Having the correct issue number will automatically link the Pull Request on this branch to that issue.

> Good examples:
>
```text
fix-executor-loader-113
chore-update-version
docs-add-cloud-section-33
```

> Bad examples:
>

| Branch name     | Feedback                                              |
| ---             | ---                                                   |
| `FIXAWESOME123` | Not descriptive enough, all caps, doesn't follow spec |
| `NEW-test-1`    | Should be lower case, not descriptive                 |
| `mybranch-1`    | No type, not descriptive                              |

### Writing your Commit Message

A good commit message helps us track Jina's development. A Pull Request with a bad commit message will be *rejected* automatically in the CI pipeline.

Commit messages should stick to our [naming conventions](#-naming-conventions) outlined above, and use the format `type(scope?): subject`:

* `type` is one of the [types above](#specify-the-correct-types).
* `scope` is optional, and represents the module your commit is working on.
* `subject` explains the commit, without an ending period`.`

For example, a commit that fixes a bug in the executor module should be phrased as: `fix(executor): fix the bad naming in init function`

> Good examples:
>
```text
fix(indexer): fix wrong sharding number in indexer
feat: add remote api
```

> Bad examples:
>

| Commit message                                                                                | Feedback                           |
| ---                                                                                           | ---                                |
| `doc(101): improved 101 document`                                                             | Should be `docs(101)`              |
| `tests(flow): add unit test for flow exception`                                               | Should be `test(flow)`             |
| `DOC(101): Improved 101 Documentation`                                                        | All letters should be in lowercase |
| `fix(pea): i fix this pea and this looks really awesome and everything should be working now` | Too long                           |
| `fix(pea):fix network receive of the pea`                                                     | Missing space after `:`            |
| `hello: add hello-world`                                                                      | Type `hello` is not allowed          |

#### What if I Mess Up?

We all make mistakes. GitHub has a guide on [rewriting commit messages](https://docs.github.com/en/free-pro-team@latest/github/committing-changes-to-your-project/changing-a-commit-message) so they can adhere to our standards.

You can also install [commitlint](https://commitlint.js.org/#/) onto your own machine and check your commit message by running:

```bash
echo "<commit message>" | commitlint
```

### Naming your Pull Request

We don't enforce naming of PRs and branches, but we recommend you follow the same style. It can simply be one of your commit messages, just copy/paste it, e.g. `fix(readme): improve the readability and move sections`.

<a name="-testing-jina-locally-and-on-ci"></a>
## 💥 Testing Jina Locally and on CI

You need to build a local docker image tagged 'jinaai/jina:test-pip' for all the tests to run as in the CI, via:

```bash
docker build --build-arg PIP_TAG="[devel]" -f ${PATH_TO_JINA}/Dockerfiles/pip.Dockerfile -t jinaai/jina:test-pip ${PATH_TO_JINA}
```

Locally you can do unittest via:

```bash
pip install ".[test]"
pytest -v -s --ignore-glob='tests/integration/hub_usage/dummyhub*' tests
```

Tips: If you want to run the k8s tests then you should install [linkerd cli](https://linkerd.io/2.11/getting-started/#step-1-install-the-cli) before.

When you add an executor or a driver, you may introduce new dependencies to Jina. You can verify the dependencies via:

```bash
jina check
```
, and via Docker container:

```bash
docker run jinaai/jina:my-local-version check
```

It prints a list of components the current version of Jina supports, and then exits. Make sure yours are not in red.

Once you submit the PR, your code will be tested in the environment of Python 3.7 and 3.8 with [full extra dependencies](extra-requirements.txt) (`pip install .[all]`) installed.

<a name="-contributing-documentation"></a>
## 📖 Contributing Documentation

Good docs make developers happy, and we love happy developers! We've got a few different types of docs:

* General documentation
* Tutorials/examples
* Docstrings in Python functions in RST format - generated by Sphinx

### Documentation guidelines

1. Decide if your page is a **guide or a tutorial**. Make sure it fits its section.
2. Use “**you**” instead of “we” or “I”. It **engages** the reader more.
3. **Sentence case** for headers. (Use [https://convertcase.net/](https://convertcase.net/) to check)
4. Keep sentences short. If possible, **fewer than 13 words**.
5. Only use `backticks` for direct references to code elements.
6. Jina product names should be capitalized and not backticked (Flow, Executor, Hub etc.).
7. All **acronyms** should be UPPERCASE (Ex. YAML, JSON, HTTP, SSL).
8. Think about the **structure** of the page beforehand. Split it into headers before writing the content.
9. If relevant, include a “**See also**” section at the end.
10. Link to any existing explanations of the concepts you are using.

Bonus: **Know when to break the rules**. Documentation writing is as much art as it is science. Sometimes you will have to deviate from these rules in order to write good documentation.


[MyST](https://myst-parser.readthedocs.io/en/latest/) Elements Usage

1. Use the `{tab}` element to show multiple ways of doing one thing. [Example](https://jina.ai/serve/concepts/flow/basics/#start-and-stop) 
2. Use the `{admonition}` boxes with care. We recommend restricting yourself to [Hint](https://jina.ai/serve/concepts/flow/basics/#create), [Caution](https://jina.ai/serve/concepts/gateway/customize-http-endpoints/#enable-graphql-endpoint) and [See Also](https://jina.ai/serve/concepts/gateway/customize-http-endpoints/#enable-graphql-endpoint).
3. Use `{dropdown}` to hide optional content, such as long code snippets or console output. [Example](https://jina.ai/serve/concepts/client/third-party-clients/#use-curl)

### Building documentation on your local machine

#### Requirements

* Python 3
* [jq](https://stedolan.github.io/jq/download/)

#### Steps to build locally

```bash
cd docs
pip install -r requirements.txt
export NUM_RELEASES=10
bash makedoc.sh local-only
```

Docs website will be generated in `_build/dirhtml`
To serve it, run

```bash
cd _build/dirhtml
python -m http.server
```

You can now see docs website on [http://localhost:8000](http://localhost:8000) on your browser.

## 🙏 Thank You

Once again, thanks so much for your interest in contributing to Jina. We're excited to see your contributions!
