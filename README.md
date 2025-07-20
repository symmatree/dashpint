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

## Basic operations

### Extract queries

The first step is to run `extract.py`:

```
export TOKEN=$(op read op://tales-secrets/grafana-prom-metrics-check-token/TOKEN)
export GRAFANA=https://borgmon.local.symmatree.com
mkdir -p /tmp/rules
extract.py "--grafana-token=$TOKEN" "--grafana-url=$GRAFANA" --out-dir=/tmp/rules
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

## Secrets

The tools expect to connect to Grafana with a service account
token, and mimir without auth (but with an address). The
connection info is stored in 1Password and the `.secrets`
folder.
