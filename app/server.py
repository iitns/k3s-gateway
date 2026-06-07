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


def k8s_get(path):
    token = (SA_PATH / "token").read_text()
    ctx = ssl.create_default_context(cafile=str(SA_PATH / "ca.crt"))
    req = urllib.request.Request(
        f"{K8S_HOST}{path}",
        headers={"Authorization": f"Bearer {token}"},
    )
    with urllib.request.urlopen(req, context=ctx) as resp:
        return json.loads(resp.read())


def get_apps():
    data = k8s_get("/apis/networking.k8s.io/v1/ingresses")
    apps = []
    seen_hosts = set()

    for item in data.get("items", []):
        meta = item["metadata"]
        annotations = meta.get("annotations", {})
        labels = meta.get("labels", {})

        name = (
            annotations.get("gateway.homelab/name")
            or labels.get("app.kubernetes.io/name")
            or meta["name"]
        )
        description = annotations.get("gateway.homelab/description", "")
        icon = annotations.get("gateway.homelab/icon", "")

        for rule in item.get("spec", {}).get("rules", []):
            host = rule.get("host", "")
            if host and host not in seen_hosts:
                seen_hosts.add(host)
                apps.append({
                    "name": name,
                    "url": f"https://{host}",
                    "description": description,
                    "icon": icon,
                    "namespace": meta["namespace"],
                })
                break

    apps.sort(key=lambda x: x["name"].lower())
    return apps


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
