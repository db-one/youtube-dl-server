#! /usr/bin/env sh

# Download required web frontend libraries
wget -q https://code.jquery.com/jquery-3.4.1.min.js -O ydl_server/static/js/jquery.min.js
wget -q https://unpkg.com/@popperjs/core@2.1.1/dist/umd/popper.min.js -O ydl_server/static/js/popper.min.js
wget -q https://github.com/twbs/bootstrap/releases/download/v4.4.1/bootstrap-4.4.1-dist.zip
unzip -jo bootstrap-4.4.1-dist.zip *.css *.css.map -d ydl_server/static/css/
unzip -jo bootstrap-4.4.1-dist.zip *.js *.js.map -d ydl_server/static/js/
rm -f bootstrap-4.4.1-dist.zip
