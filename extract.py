"""
Pseudocode for dashpint data-collection

1. Parse command-line arguments for Grafana token, URL, and output directory
2. Connect to Grafana API using token and URL
3. List all dashboard folders via Grafana API
4. For each folder:
    a. List dashboards in the folder
    b. For each dashboard:
        i. Fetch dashboard JSON
        ii. List panels in the dashboard
        iii. For each panel:
            - Extract query expressions (targets)
        iv. Build a map: dashboard → list of panels → list of query exprs
5. Store results in a nested data structure (e.g., dict)
6. (Next step: write out YAML files, not covered here)
"""

import argparse
import requests
import logging
import os
import yaml
import re

def add_exprs_for_panel(panel, templateVars, exprs):
    """
    Extracts query expressions from a panel's targets.
    Returns a list of expressions.
    """
    logging.info("Searching panel: %s", panel)
    for target in panel.get("targets", []):
        expr = target.get("expr")
        if expr:
            for v in templateVars:
                expr = expr.replace(v, templateVars[v])
            exprs.append(expr)
    for panel in panel.get("panels", []):
        add_exprs_for_panel(panel, templateVars, exprs)

def exprs_for_dashboard(dash_json) -> list[str]:
    # logging.info("Dashboard keys: %s", dash_json.keys())
    panels = dash_json["spec"].get("panels", [])
    exprs = []
    templateVars = {"$__rate_interval": "1m", "$__interval": "1m", "$__interval_ms": "60000"}
    for v in dash_json["spec"]["templating"]["list"]:
        if v['type'] == "datasource":
            continue
        vals = v.get('current', {}).get('value', [])
        val = v['name']
        if vals:
            val = vals[0]
        if v['name'] == 'cluster':
            val = 'tales'
        if v['name'] == 'namespace' and val == '$__all':
            val = 'cilium'
        templateVars["$" + v['name']] = val
    for panel in panels:
        add_exprs_for_panel(panel, templateVars, exprs)
    return exprs


def main():
    parser = argparse.ArgumentParser(description="Extract Grafana dashboard queries")
    parser.add_argument("--grafana-token", required=True, help="Grafana API token")
    parser.add_argument("--grafana-url", required=True, help="Grafana base URL")
    parser.add_argument("--out-dir", required=True, help="Output directory for extracted rules")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)
    session = requests.Session()
    session.headers.update({"Authorization": f"Bearer {args.grafana_token}"})

    def get_page(url, page=1, params=None):
        """Helper function to get a single page of results."""
        local_params = params.copy() if params else {}
        local_params.update({"limit": 1000, "page": page})
        try:
            logging.debug("Fetching %s %s", url, local_params)
            resp = session.get(url, params=local_params)
            resp.raise_for_status()
            j = resp.json()
            logging.debug("Raw response: %s", j)
            return j
        except requests.RequestException as e:
            logging.error(f"Failed to fetch {url}: {e}")
            return []

    # Helper for paginated GET requests
    def paginated_get(url, params=None):
        results = []
        page = 1
        while True:
            page_data = get_page(url, page, params)
            if not page_data:
                break
            logging.info(f"Fetched {len(page_data)} items from page {page} of {url}")
            results.extend(page_data)
            page += 1
        return results

    # List dashboard folders (pagination not needed for /api/folders, but included for future-proofing)
    folders_url = f"{args.grafana_url}/apis/folder.grafana.app/v1beta1/namespaces/default/folders"
    resp = session.get(folders_url)
    resp.raise_for_status()
    folders = resp.json()

    if not folders:
        logging.error("No folders found or failed to fetch folders.")
        return
    logging.info(f"Found folders: {len(folders['items'])}")
    # Data structure: {folder_name: {dashboard_name: [query_exprs]}}
    dashboards_data = {}
    for folder in folders['items']:
        folder_title = folder['spec']['title']
        folder_old_uid = folder['metadata']['name']
        logging.info(f"Processing folder: {folder_title}: {folder}")
        dashboards_url = f"{args.grafana_url}/api/search"
        logging.info(f"Fetching {dashboards_url} for folder {folder_title} ({folder_old_uid})")
        dashboards = paginated_get(dashboards_url, params={"folderUIDs": [folder_old_uid], "type": "dash-db"})
        if not dashboards:
            logging.error(f"No dashboards found for folder {folder_title} ({folder_old_uid}).")
            continue

        dashboards_data[folder_title] = {}
        for dash in dashboards:
            dash_title = dash['title']
            logging.info(f"Processing dashboard: {dash_title}")
            dash_uid = dash['uid']
            dash_url = f"{args.grafana_url}/apis/dashboard.grafana.app/v1beta1/namespaces/default/dashboards/{dash_uid}"
            try:
                dash_resp = session.get(dash_url)
                dash_resp.raise_for_status()
                dash_json = dash_resp.json()
            except Exception as e:
                logging.error(f"Failed to fetch dashboard {dash_title}: {e}")
                continue
            dashboards_data[folder_title][dash_title] = exprs_for_dashboard(dash_json)

    print("Dashboards data collected:")
    print(dashboards_data)

    def sanitize_name(name):
        return re.sub(r'[^A-Za-z0-9]+', '-', name)

    # Write out YAML files
    for folder_title, dashboards in dashboards_data.items():
        safe_folder = sanitize_name(folder_title)
        folder_dir = os.path.join(args.out_dir, safe_folder)
        os.makedirs(folder_dir, exist_ok=True)
        for dash_title, exprs in dashboards.items():
            safe_dash = sanitize_name(dash_title)
            out_path = os.path.join(folder_dir, f"{safe_dash}.yaml")
            yaml_data = {
                "metadata": {"name": dash_title},
                "spec": {
                    "groups": [
                        {
                            "name": dash_title,
                            "rules": [
                                {"record": f"expr-{i+1}", "expr": expr}
                                for i, expr in enumerate(exprs)
                            ]
                        }
                    ]
                }
            }
            with open(out_path, "w") as f:
                yaml.safe_dump(yaml_data, f, sort_keys=False)
            logging.info(f"Wrote {out_path}")

if __name__ == "__main__":
    main()
