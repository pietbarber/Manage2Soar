How to vendor Tablesort locally

To host Tablesort locally (optional) and avoid the CDN, download the minified build and place it at:

  static/vendor/tablesort.min.js

You can get the file from the Tablesort project or CDN:

  curl -L -o static/vendor/tablesort.min.js https://cdn.jsdelivr.net/npm/tablesort@5.2.1/dist/tablesort.min.js

Once present, the site will load the local file automatically using `static/js/tablesort-loader.js`.
