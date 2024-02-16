#!/usr/bin/env python3

import argparse
import base64
import http.client
import json
import logging
import subprocess
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from .settings import Settings


def base64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("utf-8")


def rs256_sign(data: str, private_key: Path) -> str:
    signature = subprocess.run(
        ["openssl", "dgst", "-binary", "-sha256", "-sign", private_key],
        input=data.encode("utf-8"),
        stdout=subprocess.PIPE,
        check=True,
    ).stdout
    return base64url(signature)


def build_jwt_payload(app_id: int) -> dict[str, Any]:
    jwt_iat_drift = 60
    jwt_exp_delta = 600
    now = int(time.time())
    iat = now - jwt_iat_drift
    jwt_payload = {"iat": iat, "exp": iat + jwt_exp_delta, "iss": str(app_id)}
    return jwt_payload


class HttpResponse:
    def __init__(self, raw: http.client.HTTPResponse) -> None:
        self.raw = raw

    def json(self) -> Any:
        return json.load(self.raw)

    def save(self, path: str) -> None:
        with open(path, "wb") as f:
            f.write(self.raw.read())

    def headers(self) -> http.client.HTTPMessage:
        return self.raw.headers


class GithubClientError(Exception):
    code: int
    reason: str
    url: str
    body: str


class GithubClient:
    def __init__(self, api_token: str | None) -> None:
        self.api_token = api_token
        self.token_age = time.time()

    def _request(
        self,
        path: str,
        method: str,
        data: dict[str, Any] | None = None,
        headers: dict[str, str] = {},
    ) -> HttpResponse:
        url = urllib.parse.urljoin("https://api.github.com/", path)
        headers = headers.copy()
        headers = {
            "Content-Type": "application/json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self.api_token:
            headers["Authorization"] = f"Bearer {self.api_token}"
        headers["User-Agent"] = "nixpkgs-merge-bot"

        body = None
        if data:
            body = json.dumps(data).encode("ascii")

        req = urllib.request.Request(url, headers=headers, method=method, data=body)
        try:
            resp = urllib.request.urlopen(req)
        except urllib.request.HTTPError as e:
            resp_body = ""
            try:
                resp_body = e.fp.read().decode("utf-8", "replace")
            except Exception:
                pass
            raise GithubClientError(e.code, e.reason, url, resp_body) from e
        return HttpResponse(resp)

    def get(self, path: str) -> HttpResponse:
        return self._request(path, "GET")

    def post(self, path: str, data: dict[str, str]) -> HttpResponse:
        return self._request(path, "POST", data)

    def put(self, path: str, data: dict[str, str]) -> HttpResponse:
        return self._request(path, "PUT")

    def app_installations(self) -> HttpResponse:
        return self.get("/app/installations")

    def pull_request(self, owner: str, repo: str, pr_number: int) -> HttpResponse:
        return self.get(f"/repos/{owner}/{repo}/pulls/{pr_number}")

    def pull_request_files(self, owner: str, repo: str, pr_number: int) -> HttpResponse:
        return self.get(f"/repos/{owner}/{repo}/pulls/{pr_number}/files")

    def create_issue_comment(
        self, owner: str, repo: str, issue_number: int, body: str
    ) -> HttpResponse:
        return self.post(
            f"/repos/{owner}/{repo}/issues/{issue_number}/comments", {"body": body}
        )

    def create_issue_reaction(
        self, owner: str, repo: str, issue_number: int, comment_id: int, reaction: str
    ) -> HttpResponse:
        return self.post(
            f"/repos/{owner}/{repo}/issues/comments/{comment_id}/reactions",
            {"content": reaction},
        )

    def merge_pull_request(
        self, owner: str, repo: str, pr_number: int, sha: str
    ) -> HttpResponse:
        return self.put(
            f"/repos/{owner}/{repo}/pulls/{pr_number}/merge", data={"sha": sha}
        )

    def create_installation_access_token(self, installation_id: int) -> HttpResponse:
        return self.post(f"/app/installations/{installation_id}/access_tokens", data={})


def request_access_token(app_login: str, app_id: int, app_private_key: Path) -> str:
    jwt_payload = json.dumps(build_jwt_payload(app_id)).encode("utf-8")
    json_headers = json.dumps({"alg": "RS256", "typ": "JWT"}).encode("utf-8")
    encoded_jwt_parts = f"{base64url(json_headers)}.{base64url(jwt_payload)}"
    encoded_mac = rs256_sign(encoded_jwt_parts, app_private_key)
    generated_jwt = f"{encoded_jwt_parts}.{encoded_mac}"

    client = GithubClient(generated_jwt)
    response = client.app_installations()

    installation_id = None
    logging.info(
        f"Searching for the NixOS Installation of our APP, searching for {app_login} and {app_id}"
    )
    for item in response.json():
        if item["account"]["login"] == app_login and item["app_id"] == app_id:
            installation_id = item["id"]
            break
    if not installation_id:
        logging.error(
            f"Installation not found for {app_login} and {app_id}, this is case sensitive!"
        )
        raise ValueError("Access token URL not found")

    resp = client.create_installation_access_token(installation_id)
    return resp.json()["token"]


CACHED_CLIENT = None


def get_github_client(settings: Settings) -> GithubClient:
    global CACHED_CLIENT
    if CACHED_CLIENT and CACHED_CLIENT.token_age + 300 > time.time():
        return CACHED_CLIENT
    token = request_access_token(
        settings.github_app_login,
        settings.github_app_id,
        settings.github_app_private_key,
    )
    CACHED_CLIENT = GithubClient(token)
    return CACHED_CLIENT


def main() -> None:
    parser = argparse.ArgumentParser(description="Get Github App Token")
    parser.add_argument(
        "--login",
        type=str,
        help="User or organization name that installed the app",
        required=True,
    )
    parser.add_argument("--app-id", type=int, help="Github App ID", required=True)
    parser.add_argument(
        "--app-private-key-file", type=str, help="Github App Private Key", required=True
    )
    args = parser.parse_args()
    token = request_access_token(args.login, args.app_id, args.app_private_key_file)
    print(token)


if __name__ == "__main__":
    main()
