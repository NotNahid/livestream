.PHONY: help setup run dry stop doctor test lint site docker clean vtuber preview
help:           ## show this help
	@grep -E '^[a-z]+:.*##' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  make %-8s %s\n", $$1, $$2}'
setup:          ## install system deps + Chromium
	./setup.sh
run:            ## start streaming (reads .env)
	./run.sh
dry:            ## test everything without a stream key (records logs/dry-run.mkv)
	./run.sh --dry-run --minutes 1
stop:           ## stop everything
	./stop.sh
doctor:         ## preflight checks
	./doctor.sh
test:           ## run unit tests
	python3 -m unittest discover -s tests -v
lint:           ## ruff + bash syntax
	ruff check . && for f in *.sh scripts/*.sh; do bash -n $$f; done
site:           ## build the GitHub Pages site into ./site
	./scripts/build_site.sh
docker:         ## build the Docker image
	docker build -t livestream-proto .
clean:          ## remove logs and generated data
	rm -rf logs web/data.json site
vtuber:         ## run the VTuber director locally (open http://127.0.0.1:8080/vtuber.html)
	python3 server.py & python3 -m vtuber
preview:        ## screenshots of every VTuber emotion into output/
	python3 scripts/vtuber_preview.py
