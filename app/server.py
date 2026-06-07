import json
import os
import ssl
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

SA_PATH = Path("/var/run/secrets/kubernetes.io/serviceaccount")
K8S_HOST = "https://kubernetes.default.svc"
PORT = int(os.environ.get("PORT", "8080"))
HTML_PATH = Path(__file__).parent / "index.html"

SKIP_NAMESPACES = {
    "kube-system", "kube-public", "kube-node-lease",
    "argocd", "gateway", "traefik", "monitoring",
    "headscale", "default", "cert-manager", "longhorn-system",
}


def k8s_get(path):
    token = (SA_PATH / "token").read_text()
    ctx = ssl.create_default_context(cafile=str(SA_PATH / "ca.crt"))
    req = urllib.request.Request(
        f"{K8S_HOST}{path}",
        headers={"Authorization": f"Bearer {token}"},
    )
    with urllib.request.urlopen(req, context=ctx) as resp:
        return json.loads(resp.read())


def get_node_ip():
    override = os.environ.get("NODE_IP", "")
    if override:
        return override
    data = k8s_get("/api/v1/nodes")
    for node in data.get("items", []):
        for addr in node.get("status", {}).get("addresses", []):
            if addr["type"] == "InternalIP":
                return addr["address"]
    return "127.0.0.1"


def _app_meta(meta):
    annotations = meta.get("annotations", {})
    labels = meta.get("labels", {})
    return {
        "name": (
            annotations.get("gateway.homelab/name")
            or labels.get("app.kubernetes.io/name")
            or meta["name"]
        ),
        "description": annotations.get("gateway.homelab/description", ""),
        "icon": annotations.get("gateway.homelab/icon", ""),
        "namespace": meta["namespace"],
        "annotations": annotations,
    }


def get_ingress_apps():
    data = k8s_get("/apis/networking.k8s.io/v1/ingresses")
    apps = []
    seen_hosts = set()

    for item in data.get("items", []):
        meta = item["metadata"]
        if meta["namespace"] in SKIP_NAMESPACES:
            continue

        m = _app_meta(meta)
        url_override = m["annotations"].get("gateway.homelab/url", "")

        if url_override:
            apps.append({
                "name": m["name"], "url": url_override,
                "description": m["description"], "icon": m["icon"],
                "namespace": m["namespace"],
            })
            continue

        for rule in item.get("spec", {}).get("rules", []):
            host = rule.get("host", "")
            if host and host not in seen_hosts:
                seen_hosts.add(host)
                apps.append({
                    "name": m["name"], "url": f"https://{host}",
                    "description": m["description"], "icon": m["icon"],
                    "namespace": m["namespace"],
                })
                break

    return apps


def get_nodeport_apps(node_ip, skip_namespaces):
    data = k8s_get("/api/v1/services")
    apps = []

    for item in data.get("items", []):
        if item["spec"].get("type") != "NodePort":
            continue
        meta = item["metadata"]
        if meta["namespace"] in skip_namespaces:
            continue

        m = _app_meta(meta)
        if m["annotations"].get("gateway.homelab/skip") == "true":
            continue

        node_port = None
        for port in item["spec"].get("ports", []):
            np = port.get("nodePort")
            if np:
                if port.get("port") == 80 or node_port is None:
                    node_port = np

        if node_port:
            apps.append({
                "name": m["name"], "url": f"http://{node_ip}:{node_port}",
                "description": m["description"], "icon": m["icon"],
                "namespace": m["namespace"],
            })

    return apps


def get_apps():
    ingress_apps = get_ingress_apps()
    ingress_namespaces = {a["namespace"] for a in ingress_apps}

    node_ip = get_node_ip()
    nodeport_apps = get_nodeport_apps(node_ip, SKIP_NAMESPACES | ingress_namespaces)

    all_apps = ingress_apps + nodeport_apps
    all_apps.sort(key=lambda x: x["name"].lower())
    return all_apps


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/api/apps":
            try:
                body = json.dumps(get_apps()).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", len(body))
                self.end_headers()
                self.wfile.write(body)
            except Exception as e:
                body = json.dumps({"error": str(e)}).encode()
                self.send_response(500)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(body)
        else:
            try:
                body = HTML_PATH.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", len(body))
                self.end_headers()
                self.wfile.write(body)
            except FileNotFoundError:
                self.send_response(404)
                self.end_headers()

    def log_message(self, format, *args):
        pass


if __name__ == "__main__":
    server = HTTPServer(("", PORT), Handler)
    print(f"Listening on :{PORT}")
    server.serve_forever()
