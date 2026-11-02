# Tree Leaf Quiz

A small browser quiz for students of the secondary woodwork and forestry school to learn to recognise tree leaves and needles by their Latin names.

Each question shows one image and three possible names. Keep guessing until the correct answer turns green, then continue to the next image.

## Run locally

No installation is needed. From this directory, run:

```sh
python3 -m http.server
```

Open [http://localhost:8000](http://localhost:8000) in a browser.

## Deploy

This is a static website. After the initial GitHub Pages configuration, deploy updates by pushing the repository to GitHub:

```sh
git push
```

GitHub Pages serves `index.html`, `trees.tsv`, and the `img/` directory directly.

## Contributing

Contributions are welcome, especially improved or additional leaf images.
