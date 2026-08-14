# rm -rf /cancer

Source for [jim-bo.github.io/rmrfcancer](https://jim-bo.github.io/rmrfcancer/) — a
Quarto blog on cancer genomics, AI, and clinical informatics.

## Local development

Always run Quarto through the project environment. Bare `quarto render` picks up
whatever Python happens to be on `PATH`, which has silently pulled in an
unrelated project's virtualenv and broken the build:

```bash
pipenv sync          # once, and after any Pipfile change
pipenv run quarto preview
```

Render the full site to `_site/`:

```bash
pipenv run quarto render
```

## Deployment

Pushing to `main` triggers [.github/workflows/publish.yml](.github/workflows/publish.yml),
which renders the site and deploys it to GitHub Pages. Build output (`_site/`) is
never committed.

## Layout

| Path | Purpose |
| --- | --- |
| `index.qmd` | Post listing / home page |
| `about.qmd` | About page |
| `posts/<slug>/index.qmd` | One directory per published post, assets alongside |
| `_wip/<slug>/` | Parked drafts — present in the repo, never built or published |
| `_style_guide.md` | Quanta-style writing guide the posts are held to |
| `_quarto.yml` | Site config, including the explicit `render:` allowlist |

Files and directories starting with `_` are ignored by Quarto. The `render:`
allowlist in `_quarto.yml` is deliberate — without it, any stray `.md` dropped in
the repo root gets built and published (this is how an internal notes file once
ended up live on the site).

That underscore rule is what parks a draft: anything under `_wip/` stays in the
repo and in git history but is never rendered, listed, indexed, or put in the RSS
feed. To publish a parked piece, move its directory back under `posts/`. To work
on one, move it back temporarily — Quarto will not preview it from `_wip/`.

## Regenerating post data

`_wip/ai-doctor-patient-relationship/_data_generator.ipynb` produces
`example_embedding.csv`. It reads upstream `synthetic_*_embeddings.parquet` files
that are **not** in this repo, and needs the dev dependencies:

```bash
pipenv sync --dev
```

Post data is stored as CSV, not parquet: the dataset is 33 rows, and a committed
parquet broke rendering whenever the reader's `pyarrow` was older than the Arrow
version that wrote it.
