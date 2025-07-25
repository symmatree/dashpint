# dashpint

I got sick of installing Grafana dashboards through the UI, monitoring-mixins, and
as ConfigMaps in Helm charts, and having them not work because the scrape labels
were not aligned.

Various tools help validate dashboards but I could not find one with the thoroughness
in testing Prometheus queries that `pint` has, so I figured I could bridge the gap.

## Related tools

[ContainerSolutions/prom-metrics-check](https://github.com/ContainerSolutions/prom-metrics-check) is a tool I used earlier. It worked reasonably well for me, but it has a few gaps. Primarily, the codebase is focused on finding series names in queries (and it is mostly a handmade parser). It does not check for missing _labels_ which is a common case. So I _could_ start from a fork of this tool but I don't think
it would gain me much.

[grafana/dashboard-linter](https://github.com/grafana/dashboard-linter) is handy but looks at the
dashboard in isolation; it wouldn't detect missing Rules or misnamed series.

[cloudflare/pint](https://github.com/cloudflare/pint) is a major component. This is a great runtime
tool that compares queries against a Prometheus (or Mimir) server and looks for problems. It can false
positive, especially on "missing labels" that would only appear when a failure occurs, but it has fewer
false negatives than other tools.

## Status

Working, no CI or testing.

Needs a better strategy for filling in a missing `namespace` var since that
helps a lot with reducing false positives. Right now I just run manually by
folder, and change the replacement value between runs.

## Basic operations

Basically, run extract.py to dig out expressions (with plausible replacements for
dashboard variables) and make pretend Recording Rules out of them, and then run
pint to actually check them against the server.

```
export TOKEN=$(op read op://tales-secrets/grafana-prom-metrics-check-token/TOKEN)
export GRAFANA=https://borgmon.local.symmatree.com
export OUT_DIR=/tmp/rules
rm -rf "$OUT_DIR"
mkdir -p "$OUT_DIR"
python extract.py "--grafana-token=$TOKEN" "--grafana-url=$GRAFANA" "--out-dir=$OUT_DIR"
pint -c ../tales/.pint.hcl -w 30 lint -n info "${OUT_DIR}"
```

This script first collects data:

- Connects to Grafana with the provided token and url
- Loops through dashboard folders in grafana
- Within each folder, loops through the dashboards and builds a map from
  dashboard to a list of panels, each of which consists of a list of query
  exprs used in that panel.

It then writes out:

- a directory under `out-dir` for each dashboard folder
- a yaml file for each dashboard, within its folder, structured as follows:

```
metadata:
  name: dashboard-name
spec:
  groups:
  - name: dashboard-panel-title
    rules:
    - record: expr-1
      expr: first-target-expression
    - record: expr-2
      expr: second-target-expression
```

We can then run `pint` against that output or a subset of it.
