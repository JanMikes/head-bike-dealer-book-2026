# HEAD Bikes catalogue build pipeline.
#
# Two decoupled halves joined by bikes.json (see schema/bikes.schema.json):
#   data + images  --  PDF-dependent, change when the catalogue PDF changes
#   site           --  depends only on bikes.json, rarely changes
#
# Usage:  make all   (or run a single stage:  make data / images / site)

.PHONY: all data images validate site serve clean

all: data images validate site

## PDF -> bikes.json (models, specs, prices)
data:
	python3 parse.py

## PDF -> images/, then optimise + record dimensions into bikes.json
images:
	python3 extract_images.py
	python3 optimize_images.py

## fail loudly if bikes.json breaks the contract (run before building)
validate:
	python3 validate.py

## bikes.json -> index.html (prerender the catalogue)
site: validate
	python3 build.py

## preview locally
serve:
	python3 -m http.server 8000

clean:
	rm -f index.html.bak
