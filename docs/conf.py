import os
import re
import sys
from os import path


# Centralize environment variables
JINA_VERSION = os.environ.get('JINA_VERSION', None)

sys.path.insert(0, path.abspath('..'))

project = 'Jina'
slug = re.sub(r'\W+', '-', project.lower())
author = 'Jina AI'
copyright = 'Jina AI Limited. All rights reserved.'
source_suffix = ['.rst', '.md']
master_doc = 'index'
language = 'en'
repo_dir = '../'

try:
    if not JINA_VERSION:
        pkg_name = 'jina'
        libinfo_py = path.join(repo_dir, pkg_name, '__init__.py')
        libinfo_content = open(libinfo_py, 'r', encoding='utf-8').readlines()
        version_line = [
            l.strip() for l in libinfo_content if l.startswith('__version__')
        ][0]
        exec(version_line)
    else:
        __version__ = JINA_VERSION
except FileNotFoundError:
    __version__ = '0.0.0'

version = __version__
release = __version__
SPHINX_MULTIVERSION_VERSION = os.environ.get('SPHINX_MULTIVERSION_VERSION', version)

templates_path = ['_templates']
exclude_patterns = [
    '_build',
    'Thumbs.db',
    '.DS_Store',
    'tests',
    'page_templates',
    '.github',
]
pygments_style = 'rainbow_dash'
html_theme = 'furo'

base_url = '/'
html_baseurl = 'https://jina.ai/serve'
sitemap_url_scheme = '{link}'
sitemap_locales = [None]
sitemap_filename = "sitemap.xml"
autodoc_default_options = {
    "members": True,
    "inherited-members": True,
    'class-doc-from': '__init__',
}

html_theme_options = {
    'light_logo': 'logo-light.svg',
    'dark_logo': 'logo-dark.svg',
    "sidebar_hide_name": True,
    "light_css_variables": {
        "color-brand-primary": "#009191",
        "color-brand-content": "#009191",
    },
    "dark_css_variables": {
        "color-brand-primary": "#FBCB67",
        "color-brand-content": "#FBCB67",
    },
    # PLEASE DO NOT DELETE the empty line between `start-announce` and `end-announce`
    # PLEASE DO NOT DELETE `start-announce`/ `end-announce` it is used for our dev bot to inject announcement from GH
    # start-announce
    # end-announce
}

html_static_path = ['_static']
html_extra_path = ['html_extra']
html_css_files = [
    'main.css',
    'docbot.css',
    'https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.1.1/css/all.min.css',
]
htmlhelp_basename = slug
html_show_sourcelink = False
html_favicon = '_static/favicon.ico'

latex_documents = [(master_doc, f'{slug}.tex', project, author, 'manual')]
man_pages = [(master_doc, slug, project, [author], 1)]
texinfo_documents = [
    (master_doc, slug, project, author, slug, project, 'Miscellaneous')
]
epub_title = project
epub_exclude_files = ['search.html']

# -- Extension configuration -------------------------------------------------

extensions = [
    'sphinx.ext.autodoc',
    'sphinx.ext.autosummary',
    'sphinx_autodoc_typehints',
    'sphinx.ext.viewcode',
    'sphinx.ext.coverage',
    'sphinxcontrib.apidoc',
    'sphinxcontrib.redirects',
    'sphinxarg.ext',
    'sphinx_copybutton',
    'sphinx_sitemap',
    'sphinx.ext.intersphinx',
    'sphinxext.opengraph',
    'notfound.extension',
    'myst_parser',
    'sphinx_design',
    'sphinx_inline_tabs',
]

intersphinx_mapping = {'docarray': ('https://docs.docarray.org/', None)}
myst_enable_extensions = ['colon_fence']
autosummary_generate = True
redirects_file = 'redirects.txt'
# -- Custom 404 page

# sphinx-notfound-page
# https://github.com/readthedocs/sphinx-notfound-page
notfound_context = {
    'title': 'Page Not Found',
    'body': '''
<h1>Page Not Found</h1>
<p>Oops, we couldn't find that page. </p>
<p>You can try "asking our docs" on the right corner of the page to find answer.</p>
<p>Otherwise, <a href="https://github.com/jina-ai/jina/">please create a Github issue</a> and one of our team will respond.</p>

''',
}
notfound_no_urls_prefix = True

apidoc_module_dir = repo_dir
apidoc_output_dir = 'api'
apidoc_excluded_paths = ['tests', 'legacy', 'hub', 'toy*', 'setup.py']
apidoc_separate_modules = True
apidoc_extra_args = ['-t', 'template/']
autodoc_member_order = 'bysource'
autodoc_mock_imports = ['argparse', 'numpy', 'np', 'tensorflow', 'torch', 'scipy']
autoclass_content = 'both'
set_type_checking_flag = False
html_last_updated_fmt = ''
nitpicky = True
nitpick_ignore = [('py:class', 'type')]
linkcheck_ignore = [
    # Avoid link check on local uri
    'http://0.0.0.0:*',
    'pods/encode.yml',
    'https://github.com/jina-ai/jina/commit/*',
    '.github/*',
    'extra-requirements.txt',
    'fastentrypoints.py' '../../101',
    '../../102',
    'http://www.twinsun.com/tz/tz-link.htm',  # Broken link from pytz library
    'https://urllib3.readthedocs.io/en/latest/contrib.html#google-app-engine',  # Broken link from urllib3 library
    'https://linuxize.com/post/how-to-add-swap-space-on-ubuntu-20-04/',
    # This link works but gets 403 error on linkcheck
]
linkcheck_timeout = 20
linkcheck_retries = 2
linkcheck_anchors = False

ogp_site_url = 'https://jina.ai/serve/'
ogp_image = 'https://jina.ai/serve/_static/banner.png'
ogp_use_first_image = True
ogp_description_length = 300
ogp_type = 'website'
ogp_site_name = (
    f'Jina {SPHINX_MULTIVERSION_VERSION} Documentation'
)

ogp_custom_meta_tags = [
    '<meta name="twitter:card" content="summary_large_image">',
    '<meta name="twitter:site" content="@JinaAI_">',
    '<meta name="twitter:creator" content="@JinaAI_">',
    '<meta name="description" content="Build multimodal AI services via cloud native technologies · Neural Search · Generative AI · Cloud Native · MLOps">',
    '<meta property="og:description" content="Build multimodal AI services via cloud native technologies · Neural Search · Generative AI · Cloud Native · MLOps">',
    '''
    <!-- Global site tag (gtag.js) - Google Analytics -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-48ZDWC8GT6"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());

  gtag('config', 'G-48ZDWC8GT6');
</script>

<script async defer src="https://buttons.github.io/buttons.js"></script>
    ''',
]


def setup(app):
    from sphinx.domains.python import PyField
    from sphinx.locale import _
    from sphinx.util.docfields import Field

    app.add_object_type(
        'confval',
        'confval',
        objname='configuration value',
        indextemplate='pair: %s; configuration value',
        doc_field_types=[
            PyField(
                'type',
                label=_('Type'),
                has_arg=False,
                names=('type',),
                bodyrolename='class',
            ),
            Field(
                'default',
                label=_('Default'),
                has_arg=False,
                names=('default',),
            ),
        ],
    )
